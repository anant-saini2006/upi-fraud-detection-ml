"""Stripe-style payment gateway API for the UPI fraud detection prototype.

Endpoints:
    POST /v1/payment_intents           — Create a payment intent
    POST /v1/payment_intents/{id}/confirm — Score, decide, and settle
    GET  /v1/payment_intents/{id}      — Retrieve payment state

Authentication:
    Bearer token: sk_test_demo_key_001 (or GATEWAY_TEST_KEY env var)
    Header: Authorization: Bearer <key>

Idempotency:
    POST requests accept an Idempotency-Key header.
    Duplicate keys return the existing payment without side effects.
"""

from __future__ import annotations

import os
import secrets
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT), str(_ROOT / "api")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pandas as pd
from fastapi import APIRouter, Header, HTTPException, Request

from api.database import (
    cancel_payment,
    create_payment,
    get_account,
    get_payment,
    get_recent_sender_payment_count,
    get_thresholds,
    update_balances,
    update_payment_scoring,
)
from api.risk_policy import evaluate_transaction_risk_policy
from api.schema import (
    ConfirmPaymentIntent,
    CreatePaymentIntent,
    PaymentIntentResponse,
    ScoringResponse,
)

router = APIRouter(prefix="/v1", tags=["gateway"])

# Test API key — only test-mode keys are accepted.
GATEWAY_TEST_KEY = os.getenv("GATEWAY_TEST_KEY", "sk_test_demo_key_001")


def _generate_pi_id() -> str:
    """Generate a Stripe-style payment intent ID."""
    return "pi_" + secrets.token_urlsafe(16)


def _require_auth(authorization: Optional[str]) -> None:
    """Validate the Bearer token."""
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(401, "Authorization header must be: Bearer <key>")
    if parts[1] != GATEWAY_TEST_KEY:
        raise HTTPException(401, "Invalid API key")


def _payment_to_response(payment: dict[str, Any]) -> PaymentIntentResponse:
    """Convert a database payment record to the API response shape."""
    scoring = None
    if payment.get("fraud_probability") is not None:
        scoring = ScoringResponse(
            probability=payment["fraud_probability"],
            label=payment["fraud_label"],
            risk_band=payment["risk_band"],
            reasons=payment.get("reasons", []),
        )
    return PaymentIntentResponse(
        id=payment["id"],
        amount=payment["amount"],
        currency=payment["currency"],
        sender_vpa=payment["sender_vpa"],
        receiver_vpa=payment["receiver_vpa"],
        description=payment.get("description"),
        status=payment["status"],
        scoring=scoring,
        decline_reason=payment.get("decline_reason"),
        created_at=payment["created_at"],
        confirmed_at=payment.get("confirmed_at"),
        simulated_hour=payment.get("simulated_hour"),
        scenario_tag=payment.get("scenario_tag"),
    )


def _score_transaction(
    *,
    amount: float,
    hour: int,
    old_balance_orig: float,
    new_balance_orig: float,
    old_balance_dest: float,
    new_balance_dest: float,
    model: Any,
    preprocessor: Any,
) -> tuple[float, str, str, list[str]]:
    """Score a transaction using the loaded model artifacts.

    Returns (probability, label, risk_band, reasons).

    CRITICAL: We score all checkout payments as TRANSFER (not PAYMENT).
    PaySim fraud only exists in TRANSFER and CASH_OUT types. UPI is
    account-to-account via VPAs, which is semantically a TRANSFER.
    Scoring as PAYMENT would always produce a low fraud score.
    """
    from api.index import _fraud_probabilities, _risk_level

    step_value = 15 * 24 + hour
    raw_input = pd.DataFrame(
        [
            {
                "step": step_value,
                "type": "TRANSFER",  # Score as TRANSFER, not PAYMENT
                "amount": amount,
                "oldbalanceOrg": old_balance_orig,
                "newbalanceOrig": new_balance_orig,
                "oldbalanceDest": old_balance_dest,
                "newbalanceDest": new_balance_dest,
            }
        ]
    )

    # Get the raw feature columns from the loaded metadata.
    from api.index import _raw_feature_columns

    expected = _raw_feature_columns()
    raw_input = raw_input.loc[:, expected].copy()

    transformed = preprocessor.transform(raw_input)
    probability = float(_fraud_probabilities(model, transformed)[0])

    # Determine label.
    from api.index import _META

    threshold = float(_META.get("prediction_threshold", 0.5))
    label = "FRAUD" if probability >= threshold else "LEGITIMATE"
    risk_band = _risk_level(probability)

    # Generate human-readable reasons from feature contributions.
    reasons = _generate_reasons(
        amount=amount,
        hour=hour,
        old_balance_orig=old_balance_orig,
        new_balance_orig=new_balance_orig,
        old_balance_dest=old_balance_dest,
        new_balance_dest=new_balance_dest,
        probability=probability,
    )

    return probability, label, risk_band, reasons


def _generate_reasons(
    *,
    amount: float,
    hour: int,
    old_balance_orig: float,
    new_balance_orig: float,
    old_balance_dest: float,
    new_balance_dest: float,
    probability: float,
    receiver_vpa: str = "",
) -> list[str]:
    """Generate top-3 human-readable explanations for the scoring decision.

    These are heuristic explanations derived from the feature values, designed
    to be useful in the admin review queue and checkout result page.
    """
    reasons: list[str] = []

    # Priority 1: High risk reasons (probability >= 0.70)
    if probability >= 0.70:
        if hour < 6 or hour >= 23:
            reasons.append(f"Transaction at unusual hour ({hour}:00)")
        if old_balance_dest == 0 and new_balance_dest == 0:
            reasons.append("Destination flagged: unverified mule routing (zero ledger credit)")
        elif abs(old_balance_dest + amount - new_balance_dest) > 1.0:
            reasons.append(
                f"Destination balance not updated (₹{abs(old_balance_dest + amount - new_balance_dest):,.0f} mismatch)"
            )
        if new_balance_orig == 0 and old_balance_orig > 0:
            reasons.append("Origin account fully drained to zero")
        if amount > 10000:
            reasons.append(f"High-value transfer: ₹{amount:,.0f}")
        return reasons[:3]

    # Priority 2: Review reasons (0.30 <= probability < 0.70)
    if probability >= 0.30:
        if amount > 50000:
            reasons.append(f"High-value transfer: ₹{amount:,.0f}")
        elif amount > 10000:
            reasons.append(f"Moderate transfer amount: ₹{amount:,.0f}")
        if receiver_vpa == "mallory@testpay" or abs(old_balance_dest + amount - new_balance_dest) > 1.0:
            reasons.append("Destination flagged: unverified counterparty VPA")
        if new_balance_orig == 0 and old_balance_orig > 0:
            reasons.append("Origin account fully drained to zero")
        if hour < 7 or hour >= 22:
            reasons.append(f"Transaction at unusual hour ({hour}:00)")
        else:
            reasons.append(f"Transaction during business hours ({hour}:00)")
        return reasons[:3]

    # Priority 3: Legitimate reasons
    error_balance_orig = new_balance_orig + amount - old_balance_orig
    if abs(error_balance_orig) > 1.0:
        reasons.append(
            f"Balance mismatch: origin account shows ₹{abs(error_balance_orig):,.0f} discrepancy"
        )
    elif new_balance_orig == 0 and old_balance_orig > 0:
        reasons.append("Origin account fully drained to zero")

    if hour < 6 or hour >= 23:
        reasons.append(f"Transaction at unusual hour ({hour}:00)")
    else:
        reasons.append(f"Transaction during business hours ({hour}:00)")

    if amount > 10000:
        reasons.append(f"High-value transfer: ₹{amount:,.0f}")
    elif amount > 5000:
        reasons.append(f"Moderate transfer amount: ₹{amount:,.0f}")
    else:
        reasons.append(f"Amount within normal range: ₹{amount:,.0f}")

    if amount > old_balance_orig:
        reasons.append("Amount exceeds sender's available balance")

    return reasons[:3]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/payment_intents", status_code=201)
def create_intent(
    body: CreatePaymentIntent,
    authorization: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(
        default=None, alias="idempotency-key"
    ),
) -> PaymentIntentResponse:
    """Create a payment intent. Returns status requires_payment_method."""
    _require_auth(authorization)

    # Validate accounts exist.
    sender = get_account(body.sender_vpa)
    if sender is None:
        raise HTTPException(400, f"Sender VPA not found: {body.sender_vpa}")

    receiver = get_account(body.receiver_vpa)
    if receiver is None:
        raise HTTPException(400, f"Receiver VPA not found: {body.receiver_vpa}")

    if body.sender_vpa == body.receiver_vpa:
        raise HTTPException(400, "Sender and receiver cannot be the same")

    payment_id = _generate_pi_id()
    payment = create_payment(
        payment_id=payment_id,
        idempotency_key=idempotency_key,
        amount=body.amount,
        currency=body.currency,
        sender_vpa=body.sender_vpa,
        receiver_vpa=body.receiver_vpa,
        description=body.description,
        scenario_tag=body.scenario_tag,
    )

    if payment is None:
        raise HTTPException(500, "Failed to create payment intent")

    return _payment_to_response(payment)


@router.post("/payment_intents/{payment_id}/confirm")
def confirm_intent(
    payment_id: str,
    body: ConfirmPaymentIntent = ConfirmPaymentIntent(),
    authorization: Optional[str] = Header(default=None),
) -> PaymentIntentResponse:
    """Score the payment, apply thresholds, and settle."""
    _require_auth(authorization)

    payment = get_payment(payment_id)
    if payment is None:
        raise HTTPException(404, f"Payment intent not found: {payment_id}")

    if payment["status"] != "requires_payment_method":
        if payment["status"] in ("succeeded", "requires_review", "blocked"):
            # Idempotent return: do not re-score or duplicate ledger entries
            return _payment_to_response(payment)
        if payment["status"] == "cancelled":
            raise HTTPException(
                400,
                f"Payment {payment_id} has been cancelled and cannot be confirmed",
            )
        raise HTTPException(
            400,
            f"Payment {payment_id} is already {payment['status']} and cannot be confirmed again",
        )

    # Load model artifacts lazily on demand if not yet initialized.
    from api.index import _MODEL, _PREPROCESSOR, _load_artifacts

    if _MODEL is None or _PREPROCESSOR is None:
        _load_artifacts()
        from api.index import _MODEL, _PREPROCESSOR

    if _MODEL is None or _PREPROCESSOR is None:
        raise HTTPException(
            503, "Model artifacts are not loaded. Cannot score this payment."
        )

    # Build features from the simulated ledger.
    sender = get_account(payment["sender_vpa"])
    receiver = get_account(payment["receiver_vpa"])

    if sender is None or receiver is None:
        raise HTTPException(500, "Account lookup failed during scoring")

    hour = (
        body.simulated_hour
        if body.simulated_hour is not None
        else (payment.get("simulated_hour") if payment.get("simulated_hour") is not None else datetime.now(timezone.utc).hour)
    )

    old_balance_orig = float(sender["wallet_balance"])
    new_balance_orig = max(old_balance_orig - payment["amount"], 0.0)
    old_balance_dest = float(receiver["wallet_balance"])
    new_balance_dest = old_balance_dest + payment["amount"]

    # Real velocity monitoring: count recent payments from this sender in the database
    recent_count = get_recent_sender_payment_count(payment["sender_vpa"], window_seconds=60)

    # Score transaction with the actual features
    probability, label, risk_band, model_reasons = _score_transaction(
        amount=payment["amount"],
        hour=hour,
        old_balance_orig=old_balance_orig,
        new_balance_orig=new_balance_orig,
        old_balance_dest=old_balance_dest,
        new_balance_dest=new_balance_dest,
        model=_MODEL,
        preprocessor=_PREPROCESSOR,
    )

    # Evaluate risk policy (combines accounting integrity, UPI limits, velocity, and ML score)
    policy = evaluate_transaction_risk_policy(
        amount=payment["amount"],
        transaction_type="TRANSFER",
        hour_of_day=hour,
        old_balance_orig=old_balance_orig,
        new_balance_orig=new_balance_orig,
        old_balance_dest=old_balance_dest,
        new_balance_dest=new_balance_dest,
        model_probability=probability,
        model_prediction=label,
        model_risk_level=risk_band,
        recent_velocity_count=recent_count,
        velocity_threshold=3,
    )

    # Apply thresholds & policy verdict
    thresholds = get_thresholds()
    if policy.policy_action == "REJECT":
        status = "blocked"
        decline_reason = f"Payment blocked: {'; '.join(policy.reasons[:2])}"
    elif probability >= thresholds["block_threshold"]:
        status = "blocked"
        decline_reason = f"Fraud score {probability:.2f} exceeds block threshold {thresholds['block_threshold']:.2f}"
    elif policy.policy_action == "REVIEW" or probability >= thresholds["review_threshold"]:
        status = "requires_review"
        decline_reason = None
    else:
        if old_balance_orig < payment["amount"]:
            status = "blocked"
            decline_reason = "Insufficient balance in sender's wallet"
        else:
            status = "succeeded"
            decline_reason = None
            if not update_balances(
                payment["sender_vpa"], payment["receiver_vpa"], payment["amount"]
            ):
                status = "blocked"
                decline_reason = "Insufficient balance in sender's wallet"

    # Merge reasons to ensure high-priority policy and model signals are surfaced
    final_reasons = policy.reasons[:3] if policy.reasons else model_reasons[:3]

    # Persist scoring result.
    update_payment_scoring(
        payment_id,
        status=status,
        fraud_probability=probability,
        fraud_label=label,
        risk_band=risk_band,
        reasons=final_reasons,
        decline_reason=decline_reason,
        simulated_hour=hour,
        scenario_tag=payment.get("scenario_tag"),
    )

    updated = get_payment(payment_id)
    if updated is None:
        raise HTTPException(500, "Failed to retrieve updated payment")

    return _payment_to_response(updated)


@router.get("/payment_intents/{payment_id}")
def get_intent(
    payment_id: str,
    authorization: Optional[str] = Header(default=None),
) -> PaymentIntentResponse:
    """Retrieve the current state of a payment intent."""
    _require_auth(authorization)

    payment = get_payment(payment_id)
    if payment is None:
        raise HTTPException(404, f"Payment intent not found: {payment_id}")

    return _payment_to_response(payment)
 
 
@router.post("/payment_intents/{payment_id}/cancel")
def cancel_intent(
    payment_id: str,
    authorization: Optional[str] = Header(default=None),
) -> PaymentIntentResponse:
    """Cancel an unconfirmed payment intent."""
    _require_auth(authorization)

    payment = get_payment(payment_id)
    if payment is None:
        raise HTTPException(404, f"Payment intent not found: {payment_id}")

    if payment["status"] == "cancelled":
        return _payment_to_response(payment)

    if payment["status"] != "requires_payment_method":
        raise HTTPException(
            400,
            f"Cannot cancel payment {payment_id} with status '{payment['status']}'",
        )

    cancelled = cancel_payment(payment_id, decline_reason="Cancelled by user")
    if cancelled is None:
        raise HTTPException(500, "Failed to cancel payment intent")

    return _payment_to_response(cancelled)

