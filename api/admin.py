"""Admin API for the UPI fraud detection prototype.

Endpoints:
    POST /api/admin/login         — Authenticate with username/password
    GET  /api/admin/payments      — Live payments feed
    GET  /api/admin/payments/{id} — Payment detail with scoring
    GET  /api/admin/review-count  — Count of payments needing review
    GET  /api/admin/reviews       — List reviews for a payment
    POST /api/admin/reviews/{id}  — Submit review verdict
    GET  /api/admin/settings      — Get current thresholds
    PUT  /api/admin/settings      — Update thresholds
    POST /api/admin/simulate      — Simulate batch payments
    POST /api/admin/reset         — Reset all demo data
    GET  /api/admin/accounts      — List all test accounts

Authentication:
    POST /api/admin/login returns a session token.
    All other admin endpoints require: Authorization: Bearer <token>
    Credentials: ADMIN_USERNAME / ADMIN_PASSWORD env vars.
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT), str(_ROOT / "api")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import APIRouter, Header, HTTPException

from api.database import (
    count_reviews_pending,
    create_review,
    get_payment,
    get_thresholds,
    list_accounts,
    list_payments,
    list_reviews,
    reset_demo,
    update_setting,
)
from api.schema import (
    LoginRequest,
    LoginResponse,
    ReviewRequest,
    ReviewResponse,
    SimulateRequest,
    ThresholdSettings,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "demo1234")

# Simple in-memory session store. Tokens expire after 24 hours.
# Good enough for a demo — not production auth.
_sessions: dict[str, dict[str, Any]] = {}
_SESSION_TTL = 86400  # 24 hours


def _create_session(username: str) -> str:
    """Create a new session token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "username": username,
        "created_at": time.time(),
    }
    return token


def _validate_session(authorization: Optional[str]) -> str:
    """Validate the session token and return the username."""
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(401, "Authorization must be: Bearer <token>")

    token = parts[1]
    session = _sessions.get(token)
    if session is None:
        raise HTTPException(401, "Invalid or expired session token")

    # Check expiry.
    if time.time() - session["created_at"] > _SESSION_TTL:
        del _sessions[token]
        raise HTTPException(401, "Session expired — please log in again")

    return str(session["username"])


# ── Auth ─────────────────────────────────────────────────────────────────────


@router.post("/login")
def login(body: LoginRequest) -> LoginResponse:
    """Authenticate with admin credentials."""
    if body.username != ADMIN_USERNAME or body.password != ADMIN_PASSWORD:
        raise HTTPException(401, "Invalid credentials")
    token = _create_session(body.username)
    return LoginResponse(token=token, username=body.username)


# ── Payments feed ────────────────────────────────────────────────────────────


@router.get("/payments")
def admin_list_payments(
    limit: int = 50,
    status: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Live payments feed for the admin dashboard."""
    _validate_session(authorization)
    payments = list_payments(limit=limit, status_filter=status)
    return {"payments": payments, "total": len(payments)}


@router.get("/payments/{payment_id}")
def admin_get_payment(
    payment_id: str,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Payment detail with full scoring breakdown."""
    _validate_session(authorization)
    payment = get_payment(payment_id)
    if payment is None:
        raise HTTPException(404, f"Payment not found: {payment_id}")

    # Also get any reviews for this payment.
    payment_reviews = list_reviews(payment_id=payment_id)
    return {"payment": payment, "reviews": payment_reviews}


# ── Review queue ─────────────────────────────────────────────────────────────


@router.get("/review-count")
def admin_review_count(
    authorization: Optional[str] = Header(default=None),
) -> dict[str, int]:
    """Count of payments needing review — powers the bell icon badge."""
    _validate_session(authorization)
    return {"count": count_reviews_pending()}


@router.get("/reviews")
def admin_list_reviews(
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """List all payments in requires_review status with their details."""
    _validate_session(authorization)
    payments = list_payments(status_filter="requires_review")
    return {"payments": payments, "total": len(payments)}


@router.post("/reviews/{payment_id}")
def admin_submit_review(
    payment_id: str,
    body: ReviewRequest,
    authorization: Optional[str] = Header(default=None),
) -> ReviewResponse:
    """Submit a review verdict (approve or confirm fraud)."""
    username = _validate_session(authorization)

    payment = get_payment(payment_id)
    if payment is None:
        raise HTTPException(404, f"Payment not found: {payment_id}")
    if payment["status"] != "requires_review":
        raise HTTPException(
            400, f"Payment {payment_id} is {payment['status']}, not requires_review"
        )

    review = create_review(
        payment_id=payment_id,
        reviewer=username,
        verdict=body.verdict,
        note=body.note,
    )
    if review is None:
        raise HTTPException(500, "Failed to save review")

    return ReviewResponse(**review)


# ── Settings ─────────────────────────────────────────────────────────────────


@router.get("/settings")
def admin_get_settings(
    authorization: Optional[str] = Header(default=None),
) -> ThresholdSettings:
    """Get current threshold settings."""
    _validate_session(authorization)
    thresholds = get_thresholds()
    return ThresholdSettings(**thresholds)


@router.put("/settings")
def admin_update_settings(
    body: ThresholdSettings,
    authorization: Optional[str] = Header(default=None),
) -> ThresholdSettings:
    """Update threshold settings."""
    _validate_session(authorization)

    if body.review_threshold >= body.block_threshold:
        raise HTTPException(
            400, "review_threshold must be less than block_threshold"
        )

    update_setting("block_threshold", body.block_threshold)
    update_setting("review_threshold", body.review_threshold)
    return body


# ── Accounts ─────────────────────────────────────────────────────────────────


@router.get("/accounts")
def admin_list_accounts(
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """List all test accounts with balances."""
    _validate_session(authorization)
    accounts = list_accounts()
    return {"accounts": accounts}


# ── Simulation ───────────────────────────────────────────────────────────────


@router.post("/simulate")
def admin_simulate(
    body: SimulateRequest = SimulateRequest(),
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Simulate a batch of payments through the gateway with realistic risk distribution."""
    _validate_session(authorization)

    import json
    import random
    from datetime import datetime, timezone

    from api.database import (
        _MEMORY_ACCOUNTS,
        _MEMORY_PAYMENTS,
        _connection,
        get_thresholds,
        list_accounts,
    )
    from api.gateway import _generate_pi_id, _score_transaction
    from api.index import _MODEL, _PREPROCESSOR

    if _MODEL is None or _PREPROCESSOR is None:
        raise HTTPException(503, "Model artifacts are not loaded")

    thresholds = get_thresholds()
    accounts = {a["vpa"]: dict(a) for a in list_accounts()}

    scenarios = [
        # (sender, receiver, amount_range, hour_range, tag, weight)
        ("alice@testpay", "bob@testpay", (250, 2500), (9, 19), "normal", 35),
        ("alice@testpay", "carol@testpay", (400, 3500), (10, 18), "normal", 20),
        ("bob@testpay", "carol@testpay", (150, 1800), (11, 17), "normal", 10),
        ("eve@testpay", "mallory@testpay", (35000, 75000), (12, 16), "review", 15),
        ("eve@testpay", "mallory@testpay", (15000, 50000), (1, 4), "night_drain", 10),
        ("eve@testpay", "mallory@testpay", (9999, 9999), (2, 4), "rapid_repeat", 10),
    ]

    weights = [s[5] for s in scenarios]
    total_weight = sum(weights)
    probs = [w / total_weight for w in weights]

    results = {"succeeded": 0, "requires_review": 0, "blocked": 0, "errors": 0}
    payment_rows = []

    for i in range(body.count):
        idx = random.choices(range(len(scenarios)), weights=probs, k=1)[0]
        sender, receiver, amount_range, hour_range, tag, _ = scenarios[idx]

        amount = round(random.uniform(amount_range[0], amount_range[1]), 2)
        hour = random.randint(hour_range[0], hour_range[1]) % 24

        # Ensure demo sender has sufficient balance
        if accounts[sender]["wallet_balance"] < amount:
            accounts[sender]["wallet_balance"] += 100000.0

        old_orig = float(accounts[sender]["wallet_balance"])
        new_orig = max(old_orig - amount, 0.0)
        old_dest = float(accounts[receiver]["wallet_balance"])

        if tag in ["night_drain", "rapid_repeat"]:
            old_dest = 0.0
            new_dest = 0.0
        elif tag == "review":
            new_dest = max(old_dest + amount - 12.5, 0.0)
        else:
            new_dest = old_dest + amount

        prob, label, risk_band, reasons = _score_transaction(
            amount=amount,
            hour=hour,
            old_balance_orig=old_orig,
            new_balance_orig=new_orig,
            old_balance_dest=old_dest,
            new_balance_dest=new_dest,
            model=_MODEL,
            preprocessor=_PREPROCESSOR,
        )

        if prob >= thresholds["block_threshold"]:
            status = "blocked"
            decline_reason = f"Fraud score {prob:.2f} exceeds block threshold {thresholds['block_threshold']:.2f}"
        elif prob >= thresholds["review_threshold"]:
            status = "requires_review"
            decline_reason = None
        else:
            status = "succeeded"
            decline_reason = None
            accounts[sender]["wallet_balance"] -= amount
            accounts[sender]["total_sent"] += amount
            accounts[sender]["tx_count"] += 1
            accounts[receiver]["wallet_balance"] += amount
            accounts[receiver]["total_received"] += amount
            accounts[receiver]["tx_count"] += 1

        results[status] = results.get(status, 0) + 1
        now = datetime.now(timezone.utc)
        payment_rows.append((
            _generate_pi_id(),
            None,
            amount,
            "INR",
            sender,
            receiver,
            f"Simulated {tag} payment #{i+1}",
            prob,
            label,
            risk_band,
            json.dumps(reasons),
            status,
            decline_reason,
            now,
            now,
            hour,
            tag,
        ))

    # Fast single batch write with execute_values (1 roundtrip)
    try:
        from psycopg2.extras import execute_values

        with _connection() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO payments (
                        id, idempotency_key, amount, currency, sender_vpa, receiver_vpa,
                        description, fraud_probability, fraud_label, risk_band, reasons,
                        status, decline_reason, created_at, confirmed_at, simulated_hour, scenario_tag
                    ) VALUES %s
                    """,
                    payment_rows,
                )
                for vpa, acc in accounts.items():
                    cur.execute(
                        """
                        UPDATE accounts
                        SET wallet_balance = %s, total_sent = %s, total_received = %s, tx_count = %s, updated_at = NOW()
                        WHERE vpa = %s
                        """,
                        (acc["wallet_balance"], acc["total_sent"], acc["total_received"], acc["tx_count"], vpa),
                    )
    except Exception:
        results["errors"] += body.count
        for row in payment_rows:
            p_id = row[0]
            _MEMORY_PAYMENTS[p_id] = {
                "id": p_id,
                "idempotency_key": row[1],
                "amount": row[2],
                "currency": row[3],
                "sender_vpa": row[4],
                "receiver_vpa": row[5],
                "description": row[6],
                "fraud_probability": row[7],
                "fraud_label": row[8],
                "risk_band": row[9],
                "reasons": json.loads(row[10]) if isinstance(row[10], str) else row[10],
                "status": row[11],
                "decline_reason": row[12],
                "created_at": row[13].isoformat() if hasattr(row[13], "isoformat") else str(row[13]),
                "confirmed_at": row[14].isoformat() if hasattr(row[14], "isoformat") else str(row[14]),
                "simulated_hour": row[15],
                "scenario_tag": row[16],
            }
        for vpa, acc in accounts.items():
            if vpa in _MEMORY_ACCOUNTS:
                _MEMORY_ACCOUNTS[vpa].update(acc)

    return {
        "simulated": body.count,
        "results": results,
    }


# ── Demo reset ───────────────────────────────────────────────────────────────


@router.post("/reset")
def admin_reset(
    authorization: Optional[str] = Header(default=None),
) -> dict[str, str]:
    """Reset all demo data and restore wallet balances."""
    _validate_session(authorization)

    if reset_demo():
        return {"status": "ok", "message": "Demo data reset. Wallet balances restored."}
    raise HTTPException(500, "Failed to reset demo data")


# ── Warmup ───────────────────────────────────────────────────────────────────


@router.get("/warmup")
def admin_warmup() -> dict[str, str]:
    """Warm up model artifacts without requiring auth (for pre-demo scripts)."""
    from api.index import _MODEL, _PREPROCESSOR

    if _MODEL is None or _PREPROCESSOR is None:
        raise HTTPException(503, "Model artifacts are not loaded")
    return {"status": "warm", "model": "loaded", "preprocessor": "loaded"}
