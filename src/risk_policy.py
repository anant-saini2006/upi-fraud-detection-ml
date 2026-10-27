"""Transaction validation and risk-policy assessment layer.

Operates alongside the machine learning classifier, cleanly separating:
  1. Input validation (structural correctness, finite bounds, accepted types).
  2. Transaction-type-specific balance semantics (accounting integrity, impossible
     movements, amounts exceeding origin balance).
  3. UPI transaction limits & category-aware policy checks (NPCI per-transaction caps).
  4. Final risk-policy synthesis (reconciliation between ML estimate and policy rules).

Crucial design principles:
  - Never mutates or overrides the machine learning model's estimated probability.
  - Distinguishes model estimates from input anomalies and policy violations.
  - Emits concise, deterministic reason codes (e.g. BALANCE_MISMATCH,
    IMPOSSIBLE_BALANCE_MOVEMENT, AMOUNT_EXCEEDS_ORIGIN_BALANCE,
    EXCEEDS_TRANSACTION_LIMIT, UNSUPPORTED_TRANSACTION_POLICY).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Sequence


# ── Configuration & Constants ────────────────────────────────────────────────

SUPPORTED_TRANSACTION_TYPES: frozenset[str] = frozenset({
    "CASH_IN",
    "CASH_OUT",
    "DEBIT",
    "PAYMENT",
    "TRANSFER",
})

# Types native to UPI network account-to-account flows vs PaySim synthetic fixtures
UPI_NATIVE_TYPES: frozenset[str] = frozenset({"PAYMENT", "TRANSFER", "DEBIT"})

# NPCI per-transaction limits in INR
DEFAULT_STANDARD_UPI_LIMIT: float = 100_000.0  # ₹1 Lakh standard P2P/P2M limit
MAX_PERMISSIBLE_UPI_LIMIT: float = 500_000.0   # ₹5 Lakh max under verified institutional caps

DOCUMENTED_CATEGORY_LIMITS: dict[str, float] = {
    "standard": 100_000.0,
    "p2p": 100_000.0,
    "general_merchant": 100_000.0,
    "capital_markets": 200_000.0,
    "credit_card": 200_000.0,
    "loan_repayment": 200_000.0,
    "insurance": 200_000.0,
    "hospital_educational": 500_000.0,
    "healthcare": 500_000.0,
    "education": 500_000.0,
    "tax_ipo": 500_000.0,
    "government": 500_000.0,
}

# Reason code constants
RC_INVALID_AMOUNT = "INVALID_AMOUNT"
RC_INVALID_TRANSACTION_TYPE = "INVALID_TRANSACTION_TYPE"
RC_INVALID_HOUR = "INVALID_HOUR"
RC_INVALID_BALANCE = "INVALID_BALANCE"

RC_AMOUNT_EXCEEDS_BALANCE = "AMOUNT_EXCEEDS_ORIGIN_BALANCE"
RC_IMPOSSIBLE_BALANCE_MOVEMENT = "IMPOSSIBLE_BALANCE_MOVEMENT"
RC_BALANCE_MISMATCH = "BALANCE_MISMATCH"
RC_DESTINATION_UNRECORDED = "DESTINATION_LEDGER_UNRECORDED"

RC_EXCEEDS_TRANSACTION_LIMIT = "EXCEEDS_TRANSACTION_LIMIT"
RC_UNSUPPORTED_TRANSACTION_POLICY = "UNSUPPORTED_TRANSACTION_POLICY"
RC_UNSUPPORTED_TRANSACTION_TYPE = "UNSUPPORTED_TRANSACTION_TYPE"
RC_OFF_HOURS_ACTIVITY = "OFF_HOURS_ACTIVITY"
RC_HIGH_TRANSACTION_VELOCITY = "HIGH_TRANSACTION_VELOCITY"

RC_MODEL_HIGH_FRAUD_RISK = "MODEL_HIGH_FRAUD_RISK"
RC_MODEL_MEDIUM_FRAUD_RISK = "MODEL_MEDIUM_FRAUD_RISK"
RC_CLEAN_TRANSACTION = "CLEAN_TRANSACTION"


# ── Assessment Data Structures ───────────────────────────────────────────────

@dataclass(frozen=True)
class InputValidationResult:
    """Outcome of structural input validation."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BalanceAssessmentResult:
    """Outcome of transaction-type-specific balance consistency analysis."""
    is_consistent: bool
    has_impossible_movement: bool
    amount_exceeds_balance: bool
    error_balance_orig: float
    error_balance_dest: float
    reason_codes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UpiPolicyAssessmentResult:
    """Outcome of UPI limits and category eligibility check."""
    status: Literal["PASS", "CATEGORY_VERIFICATION_REQUIRED", "EXCEEDS_MAX_LIMIT", "UNSUPPORTED_TYPE"]
    standard_limit: float
    applicable_limit: float
    category: str
    reason_codes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskPolicyAssessment:
    """Synthesized risk-policy verdict combining validation, policy, and model."""
    policy_verdict: Literal["PASS", "WARNING", "FLAGGED_FOR_REVIEW", "REJECTED", "OUT_OF_SCOPE"]
    policy_action: Literal["ALLOW", "REVIEW", "REJECT"]
    reason_codes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reconciliation_note: Optional[str] = None


# ── Validation Functions ─────────────────────────────────────────────────────

def validate_transaction_inputs(
    *,
    amount: Any,
    transaction_type: Any,
    hour_of_day: Any,
    old_balance_orig: Any,
    new_balance_orig: Any,
    old_balance_dest: Any,
    new_balance_dest: Any,
) -> InputValidationResult:
    """Validate raw transaction inputs before any model or policy evaluation.

    Ensures:
      - Amount is finite, non-null, and strictly positive (> 0).
      - Transaction type is a non-empty string in SUPPORTED_TRANSACTION_TYPES.
      - Hour of day is an integer between 0 and 23 inclusive.
      - Origin and destination balances are finite, non-null, and non-negative (>= 0).
    """
    errors: list[str] = []
    reason_codes: list[str] = []

    # Validate amount
    try:
        amt_float = float(amount)
        if not math.isfinite(amt_float):
            errors.append("Transaction amount must be a finite number.")
            reason_codes.append(RC_INVALID_AMOUNT)
        elif amt_float <= 0.0:
            errors.append("Transaction amount must be strictly positive (greater than ₹0.00).")
            reason_codes.append(RC_INVALID_AMOUNT)
    except (TypeError, ValueError):
        errors.append("Transaction amount is missing or not a valid number.")
        reason_codes.append(RC_INVALID_AMOUNT)

    # Validate transaction_type
    if not isinstance(transaction_type, str) or not transaction_type.strip():
        errors.append("Transaction type is required and must be a string.")
        reason_codes.append(RC_INVALID_TRANSACTION_TYPE)
    else:
        normalized_type = transaction_type.strip().upper()
        if normalized_type not in SUPPORTED_TRANSACTION_TYPES:
            allowed = ", ".join(sorted(SUPPORTED_TRANSACTION_TYPES))
            errors.append(f"Transaction type '{transaction_type}' is unsupported. Must be one of: {allowed}.")
            reason_codes.append(RC_INVALID_TRANSACTION_TYPE)

    # Validate hour_of_day
    try:
        # Check that it represents an integer
        hour_int = int(hour_of_day)
        if float(hour_of_day) != hour_int:
            errors.append("Hour of day must be an integer.")
            reason_codes.append(RC_INVALID_HOUR)
        elif not (0 <= hour_int <= 23):
            errors.append("Hour of day must be an integer between 0 and 23 inclusive.")
            reason_codes.append(RC_INVALID_HOUR)
    except (TypeError, ValueError):
        errors.append("Hour of day is missing or not a valid integer.")
        reason_codes.append(RC_INVALID_HOUR)

    # Validate balances
    balance_fields = [
        ("old_balance_orig", old_balance_orig, "Sender's balance before"),
        ("new_balance_orig", new_balance_orig, "Sender's balance after"),
        ("old_balance_dest", old_balance_dest, "Receiver's balance before"),
        ("new_balance_dest", new_balance_dest, "Receiver's balance after"),
    ]
    for field_name, value, label in balance_fields:
        try:
            bal_float = float(value)
            if not math.isfinite(bal_float):
                errors.append(f"{label} ({field_name}) must be a finite number.")
                if RC_INVALID_BALANCE not in reason_codes:
                    reason_codes.append(RC_INVALID_BALANCE)
            elif bal_float < 0.0:
                errors.append(f"{label} ({field_name}) cannot be negative.")
                if RC_INVALID_BALANCE not in reason_codes:
                    reason_codes.append(RC_INVALID_BALANCE)
        except (TypeError, ValueError):
            errors.append(f"{label} ({field_name}) is missing or not a valid number.")
            if RC_INVALID_BALANCE not in reason_codes:
                reason_codes.append(RC_INVALID_BALANCE)

    return InputValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        reason_codes=reason_codes,
    )


# ── Balance Semantics Assessment ─────────────────────────────────────────────

def assess_balance_semantics(
    *,
    amount: float,
    transaction_type: str,
    old_balance_orig: float,
    new_balance_orig: float,
    old_balance_dest: float,
    new_balance_dest: float,
    discrepancy_tolerance: float = 1.0,
) -> BalanceAssessmentResult:
    """Analyze balance integrity based on transaction-type-specific mechanics.

    Semantics by transaction type:
      - TRANSFER:
          Sender (Origin): Outgoing. Expected new = old - amount.
            * If old < amount: Amount exceeds available balance.
            * If new > old: Impossible movement (balance increased on outgoing transfer).
          Receiver (Dest): Incoming. Expected new = old + amount.
            * If new < old: Impossible movement (balance decreased on incoming transfer).
            * If old == 0 and new == 0: Unrecorded external destination ledger.
      - PAYMENT:
          Sender (Origin): Outgoing. Same as TRANSFER sender.
          Receiver (Dest): Merchant. Often unrecorded (0 -> 0) in PaySim.
            * If tracked (old > 0 or new > 0) and new < old: Impossible movement.
      - CASH_OUT:
          Sender (Origin): Outgoing cash withdrawal. Same as TRANSFER sender.
      - CASH_IN:
          Sender (Origin): Cash deposit INTO origin account.
            * Expected new = old + amount (origin balance must INCREASE).
            * If new < old: Impossible movement (origin balance decreased on cash deposit).
      - DEBIT:
          Sender (Origin): Direct debit/charge.
            * If new > old: Impossible movement.
            * If old < amount: Overdraft / amount exceeds balance.
    """
    t_type = transaction_type.strip().upper()
    reason_codes: list[str] = []
    reasons: list[str] = []

    has_impossible_movement = False
    amount_exceeds_balance = False

    # 1. Origin analysis
    if t_type == "CASH_IN":
        # In CASH_IN, money is deposited into the origin account; balance must grow
        if new_balance_orig < old_balance_orig - 0.01:
            has_impossible_movement = True
            reason_codes.append(RC_IMPOSSIBLE_BALANCE_MOVEMENT)
            reasons.append(
                f"Origin balance decreased from ₹{old_balance_orig:,.2f} to ₹{new_balance_orig:,.2f} "
                f"during a cash deposit (CASH_IN)."
            )
        error_balance_orig = new_balance_orig - (old_balance_orig + amount)
    else:
        # Outgoing from origin: TRANSFER, PAYMENT, CASH_OUT, DEBIT
        if amount > old_balance_orig + 0.01:
            amount_exceeds_balance = True
            reason_codes.append(RC_AMOUNT_EXCEEDS_BALANCE)
            reasons.append(
                f"Transaction amount (₹{amount:,.2f}) exceeds sender's available balance (₹{old_balance_orig:,.2f})."
            )

        if new_balance_orig > old_balance_orig + 0.01:
            has_impossible_movement = True
            reason_codes.append(RC_IMPOSSIBLE_BALANCE_MOVEMENT)
            reasons.append(
                f"Origin balance increased from ₹{old_balance_orig:,.2f} to ₹{new_balance_orig:,.2f} "
                f"during an outgoing {t_type} transaction."
            )

        # Standard PaySim calculation: new + amount - old
        error_balance_orig = new_balance_orig + amount - old_balance_orig

    # Flag significant origin discrepancy
    if abs(error_balance_orig) > discrepancy_tolerance:
        if RC_BALANCE_MISMATCH not in reason_codes:
            reason_codes.append(RC_BALANCE_MISMATCH)
        reasons.append(
            f"Origin balance discrepancy of ₹{abs(error_balance_orig):,.2f} detected "
            f"(expected ₹{old_balance_orig - amount if t_type != 'CASH_IN' else old_balance_orig + amount:,.2f}, "
            f"recorded ₹{new_balance_orig:,.2f})."
        )

    # 2. Destination analysis
    # Standard PaySim formula: old + amount - new
    error_balance_dest = old_balance_dest + amount - new_balance_dest

    if t_type in ("TRANSFER", "PAYMENT", "CASH_OUT"):
        # Incoming to destination or unrecorded merchant/agent
        dest_is_unrecorded = (old_balance_dest == 0.0 and new_balance_dest == 0.0)

        if dest_is_unrecorded:
            # PaySim merchant accounts frequently do not track balance
            pass
        else:
            if new_balance_dest < old_balance_dest - 0.01:
                has_impossible_movement = True
                if RC_IMPOSSIBLE_BALANCE_MOVEMENT not in reason_codes:
                    reason_codes.append(RC_IMPOSSIBLE_BALANCE_MOVEMENT)
                reasons.append(
                    f"Destination balance decreased from ₹{old_balance_dest:,.2f} to ₹{new_balance_dest:,.2f} "
                    f"during an incoming {t_type} transaction."
                )

            if abs(error_balance_dest) > discrepancy_tolerance:
                if RC_BALANCE_MISMATCH not in reason_codes:
                    reason_codes.append(RC_BALANCE_MISMATCH)
                reasons.append(
                    f"Destination balance discrepancy of ₹{abs(error_balance_dest):,.2f} detected "
                    f"(expected ₹{old_balance_dest + amount:,.2f}, recorded ₹{new_balance_dest:,.2f})."
                )

    is_consistent = (
        not has_impossible_movement
        and not amount_exceeds_balance
        and abs(error_balance_orig) <= discrepancy_tolerance
        and (
            (old_balance_dest == 0.0 and new_balance_dest == 0.0)
            or abs(error_balance_dest) <= discrepancy_tolerance
        )
    )

    return BalanceAssessmentResult(
        is_consistent=is_consistent,
        has_impossible_movement=has_impossible_movement,
        amount_exceeds_balance=amount_exceeds_balance,
        error_balance_orig=error_balance_orig,
        error_balance_dest=error_balance_dest,
        reason_codes=reason_codes,
        reasons=reasons,
    )


# ── UPI Transaction Limits & Policy ──────────────────────────────────────────

def assess_upi_policy(
    *,
    amount: float,
    transaction_type: str,
    merchant_category: Optional[str] = None,
    standard_limit: float = DEFAULT_STANDARD_UPI_LIMIT,
    max_permissible_limit: float = MAX_PERMISSIBLE_UPI_LIMIT,
) -> UpiPolicyAssessmentResult:
    """Evaluate amount against NPCI UPI per-transaction limit circulars.

    Rules:
      - Native UPI types: PAYMENT, TRANSFER, DEBIT.
      - CASH_IN and CASH_OUT are unsupported on live UPI protocols.
      - Standard P2P/P2M limit: ₹1,00,000.
      - Amounts between ₹1,00,000 and ₹5,00,000 require documented category eligibility
        (e.g., educational institutions, healthcare, capital markets, tax/IPO).
        If the category is unverified or unspecified, this is flagged for review/verification
        rather than labeled as fraud.
      - Amounts > ₹5,00,000 exceed the maximum permissible limit across all UPI categories.
    """
    t_type = transaction_type.strip().upper()
    reasons: list[str] = []
    reason_codes: list[str] = []

    # Check transaction type support
    if t_type not in SUPPORTED_TRANSACTION_TYPES:
        status: Literal[
            "PASS", "CATEGORY_VERIFICATION_REQUIRED", "EXCEEDS_MAX_LIMIT", "UNSUPPORTED_TYPE"
        ] = "UNSUPPORTED_TYPE"
        reason_codes.append(RC_UNSUPPORTED_TRANSACTION_TYPE)
        reasons.append(
            f"Transaction type '{t_type}' is unsupported by the risk policy."
        )
    else:
        if t_type not in UPI_NATIVE_TYPES:
            reason_codes.append(RC_UNSUPPORTED_TRANSACTION_TYPE)
            reasons.append(
                f"Transaction type '{t_type}' is not a native UPI transaction protocol; "
                f"evaluated under PaySim synthetic development schema."
            )

    # Resolve category and limit
    normalized_cat = (merchant_category or "standard").strip().lower()
    applicable_limit = DOCUMENTED_CATEGORY_LIMITS.get(normalized_cat, standard_limit)

    if t_type not in SUPPORTED_TRANSACTION_TYPES:
        status = "UNSUPPORTED_TYPE"
    elif amount > max_permissible_limit:
        status = "EXCEEDS_MAX_LIMIT"
        reason_codes.append(RC_EXCEEDS_TRANSACTION_LIMIT)
        reasons.append(
            f"Transaction amount of ₹{amount:,.2f} exceeds the maximum permissible limit of "
            f"₹{max_permissible_limit:,.2f} for any UPI transaction category under NPCI guidelines."
        )
    elif amount > standard_limit:
        # P2P transfers (TRANSFER) are strictly capped at standard_limit (₹1 Lakh) under NPCI rules.
        # Enhanced category caps apply strictly to verified merchant transactions (PAYMENT).
        if t_type == "PAYMENT" and merchant_category and normalized_cat in DOCUMENTED_CATEGORY_LIMITS and amount <= applicable_limit:
            status = "PASS"
            reasons.append(
                f"Amount ₹{amount:,.2f} is within documented category limit for '{normalized_cat}' "
                f"(₹{applicable_limit:,.2f})."
            )
        else:
            status = "CATEGORY_VERIFICATION_REQUIRED"
            reason_codes.append(RC_UNSUPPORTED_TRANSACTION_POLICY)
            if t_type == "TRANSFER":
                reasons.append(
                    f"P2P transfer amount of ₹{amount:,.2f} exceeds the standard UPI limit of ₹{standard_limit:,.2f}. "
                    f"Enhanced category caps apply strictly to verified merchant transactions."
                )
            else:
                reasons.append(
                    f"Transaction amount of ₹{amount:,.2f} exceeds the standard UPI limit of ₹{standard_limit:,.2f}. "
                    f"Higher limits (up to ₹{max_permissible_limit:,.2f}) require documented category eligibility "
                    f"(e.g., educational, healthcare, tax, capital markets); category not verified."
                )
    else:
        status = "PASS"

    return UpiPolicyAssessmentResult(
        status=status,
        standard_limit=standard_limit,
        applicable_limit=applicable_limit,
        category=normalized_cat,
        reason_codes=reason_codes,
        reasons=reasons,
    )


# ── Full Risk-Policy Synthesis ───────────────────────────────────────────────

def evaluate_transaction_risk_policy(
    *,
    amount: float,
    transaction_type: str,
    hour_of_day: int,
    old_balance_orig: float,
    new_balance_orig: float,
    old_balance_dest: float,
    new_balance_dest: float,
    model_probability: float,
    model_prediction: str,
    model_risk_level: str,
    merchant_category: Optional[str] = None,
    recent_velocity_count: int = 0,
    velocity_threshold: int = 4,
) -> RiskPolicyAssessment:
    """Synthesize input validation, balance semantics, UPI limits, and ML estimates.

    CRITICAL RULES:
      1. Model probability is NEVER altered to make a classification look safer.
      2. If validation or accounting balance rules fail, do not present a clean bill of health.
      3. If the model classifies as FRAUD, policy does NOT override it to ALLOW.
      4. Distinguish ML statistical estimates from rule-based policy reviews.
    """
    all_reason_codes: list[str] = []
    all_reasons: list[str] = []
    warnings: list[str] = []

    # 1. Balance assessment
    bal = assess_balance_semantics(
        amount=amount,
        transaction_type=transaction_type,
        old_balance_orig=old_balance_orig,
        new_balance_orig=new_balance_orig,
        old_balance_dest=old_balance_dest,
        new_balance_dest=new_balance_dest,
    )
    all_reason_codes.extend(bal.reason_codes)
    all_reasons.extend(bal.reasons)

    # 2. UPI limit & category policy
    upi = assess_upi_policy(
        amount=amount,
        transaction_type=transaction_type,
        merchant_category=merchant_category,
    )
    for rc in upi.reason_codes:
        if rc not in all_reason_codes:
            all_reason_codes.append(rc)
    all_reasons.extend(upi.reasons)

    # 3. Velocity policy (if tracked)
    if recent_velocity_count >= velocity_threshold:
        all_reason_codes.append(RC_HIGH_TRANSACTION_VELOCITY)
        all_reasons.append(
            f"Velocity spike: {recent_velocity_count} transactions detected in rapid succession "
            f"(rule-based velocity monitoring)."
        )

    # 4. Off-hours assessment (labeled explicitly as rule-based, not ML)
    if hour_of_day < 6 or hour_of_day >= 23:
        warnings.append(
            f"Transaction initiated during late-night off-hours ({hour_of_day}:00); "
            f"evaluated as a rule-based advisory indicator."
        )

    # 5. Incorporate model outcome into reason codes without changing model outputs
    if model_prediction == "FRAUD" or model_risk_level == "HIGH":
        if RC_MODEL_HIGH_FRAUD_RISK not in all_reason_codes:
            all_reason_codes.append(RC_MODEL_HIGH_FRAUD_RISK)
        all_reasons.append(
            f"Machine learning model identified elevated fraud probability ({model_probability * 100:.2f}%)."
        )
    elif model_risk_level == "MEDIUM":
        if RC_MODEL_MEDIUM_FRAUD_RISK not in all_reason_codes:
            all_reason_codes.append(RC_MODEL_MEDIUM_FRAUD_RISK)
        all_reasons.append(
            f"Machine learning model flagged moderate risk score ({model_probability * 100:.2f}%)."
        )

    # 6. Determine policy verdict and action
    reconciliation_note: Optional[str] = None

    if (
        bal.has_impossible_movement
        or bal.amount_exceeds_balance
        or upi.status == "EXCEEDS_MAX_LIMIT"
        or upi.status == "UNSUPPORTED_TYPE"
    ):
        policy_verdict = "REJECTED"
        policy_action = "REJECT"
        if upi.status == "UNSUPPORTED_TYPE":
            reconciliation_note = (
                f"Transaction rejected: unsupported transaction type '{transaction_type}'."
            )
        elif model_prediction == "LEGITIMATE" and model_risk_level == "LOW":
            reconciliation_note = (
                "The ML classifier predicted LOW risk (0.00%) based on synthetic feature patterns, "
                "but the transaction violates physical balance constraints or UPI limits and is REJECTED by policy."
            )
    elif (
        not bal.is_consistent
        or upi.status == "CATEGORY_VERIFICATION_REQUIRED"
        or recent_velocity_count >= velocity_threshold
        or model_prediction == "FRAUD"
        or model_risk_level == "HIGH"
    ):
        policy_verdict = "FLAGGED_FOR_REVIEW"
        policy_action = "REVIEW"
        if model_prediction == "LEGITIMATE" and not bal.is_consistent:
            reconciliation_note = (
                "The ML model returned a low fraud score, but accounting balance discrepancies require manual review."
            )
        elif model_prediction == "FRAUD":
            reconciliation_note = (
                "Transaction flagged for review due to elevated machine learning fraud score."
            )
    elif model_risk_level == "MEDIUM":
        policy_verdict = "WARNING"
        policy_action = "REVIEW"
        reconciliation_note = "Transaction processed with advisory policy warnings."
    else:
        policy_verdict = "PASS"
        policy_action = "ALLOW"
        if not all_reason_codes:
            all_reason_codes.append(RC_CLEAN_TRANSACTION)
            all_reasons.append("Transaction passed all input, balance integrity, and policy checks.")

    return RiskPolicyAssessment(
        policy_verdict=policy_verdict,
        policy_action=policy_action,
        reason_codes=all_reason_codes,
        reasons=all_reasons,
        warnings=warnings,
        reconciliation_note=reconciliation_note,
    )
