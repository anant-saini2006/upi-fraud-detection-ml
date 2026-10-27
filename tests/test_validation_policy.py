"""Unit and API-level tests for transaction validation and risk-policy logic.

Covers Task F requirements:
1. Normal transaction with consistent balances.
2. Origin balance that increases unexpectedly during an outgoing transaction.
3. Destination balance inconsistent with the submitted amount.
4. Amount beyond a configured policy limit (standard vs verified vs max permissible).
5. Invalid transaction type, invalid hour, negative balances, and non-finite inputs.
6. A valid transaction that the existing model classifies as fraudulent, ensuring
   no rule incorrectly overrides it.
7. The distinction between an ML estimate and a rule-based review outcome.
8. The repeat-transfer scenario (velocity monitoring).
9. Transaction-type specific balance semantics (CASH_IN vs TRANSFER vs PAYMENT).
"""

from __future__ import annotations

import math
import unittest

from pydantic import ValidationError

from api import index
from src.risk_policy import (
    RC_AMOUNT_EXCEEDS_BALANCE,
    RC_BALANCE_MISMATCH,
    RC_CLEAN_TRANSACTION,
    RC_EXCEEDS_TRANSACTION_LIMIT,
    RC_HIGH_TRANSACTION_VELOCITY,
    RC_IMPOSSIBLE_BALANCE_MOVEMENT,
    RC_INVALID_AMOUNT,
    RC_INVALID_BALANCE,
    RC_INVALID_HOUR,
    RC_INVALID_TRANSACTION_TYPE,
    RC_MODEL_HIGH_FRAUD_RISK,
    RC_UNSUPPORTED_TRANSACTION_POLICY,
    RC_UNSUPPORTED_TRANSACTION_TYPE,
    assess_balance_semantics,
    assess_upi_policy,
    evaluate_transaction_risk_policy,
    validate_transaction_inputs,
)


class TransactionValidationAndRiskPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = index._require_dataset()

    # 1. Normal transaction with consistent balances
    def test_normal_transaction_with_consistent_balances(self):
        val = validate_transaction_inputs(
            amount=1000.0,
            transaction_type="TRANSFER",
            hour_of_day=14,
            old_balance_orig=5000.0,
            new_balance_orig=4000.0,
            old_balance_dest=1000.0,
            new_balance_dest=2000.0,
        )
        self.assertTrue(val.is_valid)
        self.assertEqual(len(val.errors), 0)

        bal = assess_balance_semantics(
            amount=1000.0,
            transaction_type="TRANSFER",
            old_balance_orig=5000.0,
            new_balance_orig=4000.0,
            old_balance_dest=1000.0,
            new_balance_dest=2000.0,
        )
        self.assertTrue(bal.is_consistent)
        self.assertFalse(bal.has_impossible_movement)
        self.assertFalse(bal.amount_exceeds_balance)
        self.assertAlmostEqual(bal.error_balance_orig, 0.0)
        self.assertAlmostEqual(bal.error_balance_dest, 0.0)

        policy = evaluate_transaction_risk_policy(
            amount=1000.0,
            transaction_type="TRANSFER",
            hour_of_day=14,
            old_balance_orig=5000.0,
            new_balance_orig=4000.0,
            old_balance_dest=1000.0,
            new_balance_dest=2000.0,
            model_probability=0.0001,
            model_prediction="LEGITIMATE",
            model_risk_level="LOW",
        )
        self.assertEqual(policy.policy_verdict, "PASS")
        self.assertEqual(policy.policy_action, "ALLOW")
        self.assertIn(RC_CLEAN_TRANSACTION, policy.reason_codes)

        # API-level check
        req = index.TransactionInput(
            amount=1000.0,
            transaction_type="TRANSFER",
            hour_of_day=14,
            old_balance_orig=5000.0,
            new_balance_orig=4000.0,
            old_balance_dest=1000.0,
            new_balance_dest=2000.0,
        )
        res = index.predict(req)
        self.assertTrue(res.input_valid)
        self.assertEqual(res.policy_verdict, "PASS")
        self.assertEqual(res.policy_action, "ALLOW")
        self.assertEqual(res.prediction, "LEGITIMATE")

    # 2. Origin balance that increases unexpectedly during an outgoing transaction
    def test_origin_balance_increases_unexpectedly_outgoing_transaction(self):
        bal = assess_balance_semantics(
            amount=500.0,
            transaction_type="PAYMENT",
            old_balance_orig=1000.0,
            new_balance_orig=1500.0,  # Impossible increase!
            old_balance_dest=0.0,
            new_balance_dest=0.0,
        )
        self.assertFalse(bal.is_consistent)
        self.assertTrue(bal.has_impossible_movement)
        self.assertIn(RC_IMPOSSIBLE_BALANCE_MOVEMENT, bal.reason_codes)

        policy = evaluate_transaction_risk_policy(
            amount=500.0,
            transaction_type="PAYMENT",
            hour_of_day=12,
            old_balance_orig=1000.0,
            new_balance_orig=1500.0,
            old_balance_dest=0.0,
            new_balance_dest=0.0,
            model_probability=0.0001,
            model_prediction="LEGITIMATE",
            model_risk_level="LOW",
        )
        self.assertEqual(policy.policy_verdict, "REJECTED")
        self.assertEqual(policy.policy_action, "REJECT")
        self.assertIn(RC_IMPOSSIBLE_BALANCE_MOVEMENT, policy.reason_codes)
        self.assertIsNotNone(policy.reconciliation_note)

    # 3. Destination balance inconsistent with submitted amount
    def test_destination_balance_inconsistent_with_amount(self):
        bal = assess_balance_semantics(
            amount=50000.0,
            transaction_type="TRANSFER",
            old_balance_orig=60000.0,
            new_balance_orig=10000.0,
            old_balance_dest=1000.0,
            new_balance_dest=2000.0,  # Only +1000 credited instead of +50000
        )
        self.assertFalse(bal.is_consistent)
        self.assertAlmostEqual(bal.error_balance_dest, 49000.0)
        self.assertIn(RC_BALANCE_MISMATCH, bal.reason_codes)

        policy = evaluate_transaction_risk_policy(
            amount=50000.0,
            transaction_type="TRANSFER",
            hour_of_day=14,
            old_balance_orig=60000.0,
            new_balance_orig=10000.0,
            old_balance_dest=1000.0,
            new_balance_dest=2000.0,
            model_probability=0.02,
            model_prediction="LEGITIMATE",
            model_risk_level="LOW",
        )
        self.assertEqual(policy.policy_verdict, "FLAGGED_FOR_REVIEW")
        self.assertEqual(policy.policy_action, "REVIEW")
        self.assertIn(RC_BALANCE_MISMATCH, policy.reason_codes)

    # 4. Amount beyond configured policy limit
    def test_amount_beyond_configured_policy_limit(self):
        # (a) Beyond standard ₹1 Lakh limit without category
        upi_unspec = assess_upi_policy(
            amount=150000.0,
            transaction_type="TRANSFER",
            merchant_category=None,
        )
        self.assertEqual(upi_unspec.status, "CATEGORY_VERIFICATION_REQUIRED")
        self.assertIn(RC_UNSUPPORTED_TRANSACTION_POLICY, upi_unspec.reason_codes)

        policy_unspec = evaluate_transaction_risk_policy(
            amount=150000.0,
            transaction_type="TRANSFER",
            hour_of_day=14,
            old_balance_orig=200000.0,
            new_balance_orig=50000.0,
            old_balance_dest=1000.0,
            new_balance_dest=151000.0,
            model_probability=0.01,
            model_prediction="LEGITIMATE",
            model_risk_level="LOW",
        )
        self.assertEqual(policy_unspec.policy_verdict, "FLAGGED_FOR_REVIEW")
        self.assertEqual(policy_unspec.policy_action, "REVIEW")
        self.assertIn(RC_UNSUPPORTED_TRANSACTION_POLICY, policy_unspec.reason_codes)

        # (b) Beyond maximum permissible ₹5 Lakh limit across all categories
        upi_max = assess_upi_policy(
            amount=600000.0,
            transaction_type="PAYMENT",
            merchant_category="healthcare",
        )
        self.assertEqual(upi_max.status, "EXCEEDS_MAX_LIMIT")
        self.assertIn(RC_EXCEEDS_TRANSACTION_LIMIT, upi_max.reason_codes)

        # (c) Documented higher category within limits (e.g. ₹3 Lakh for healthcare)
        upi_cat = assess_upi_policy(
            amount=300000.0,
            transaction_type="PAYMENT",
            merchant_category="healthcare",
        )
        self.assertEqual(upi_cat.status, "PASS")

    # 5. Invalid inputs, invalid hour, negative balances, and non-finite inputs
    def test_invalid_inputs_and_non_finite_values(self):
        # Negative amount
        val_neg_amt = validate_transaction_inputs(
            amount=-100.0,
            transaction_type="TRANSFER",
            hour_of_day=12,
            old_balance_orig=1000.0,
            new_balance_orig=900.0,
            old_balance_dest=100.0,
            new_balance_dest=200.0,
        )
        self.assertFalse(val_neg_amt.is_valid)
        self.assertIn(RC_INVALID_AMOUNT, val_neg_amt.reason_codes)

        # Non-finite amount (NaN / Inf)
        val_nan_amt = validate_transaction_inputs(
            amount=float("nan"),
            transaction_type="TRANSFER",
            hour_of_day=12,
            old_balance_orig=1000.0,
            new_balance_orig=900.0,
            old_balance_dest=100.0,
            new_balance_dest=200.0,
        )
        self.assertFalse(val_nan_amt.is_valid)
        self.assertIn(RC_INVALID_AMOUNT, val_nan_amt.reason_codes)

        # Invalid transaction type
        val_type = validate_transaction_inputs(
            amount=100.0,
            transaction_type="UNSUPPORTED_TYPE",
            hour_of_day=12,
            old_balance_orig=1000.0,
            new_balance_orig=900.0,
            old_balance_dest=100.0,
            new_balance_dest=200.0,
        )
        self.assertFalse(val_type.is_valid)
        self.assertIn(RC_INVALID_TRANSACTION_TYPE, val_type.reason_codes)

        # Invalid hour (< 0 or > 23 or non-integer)
        val_hour = validate_transaction_inputs(
            amount=100.0,
            transaction_type="TRANSFER",
            hour_of_day=25,
            old_balance_orig=1000.0,
            new_balance_orig=900.0,
            old_balance_dest=100.0,
            new_balance_dest=200.0,
        )
        self.assertFalse(val_hour.is_valid)
        self.assertIn(RC_INVALID_HOUR, val_hour.reason_codes)

        # Negative balance
        val_neg_bal = validate_transaction_inputs(
            amount=100.0,
            transaction_type="TRANSFER",
            hour_of_day=12,
            old_balance_orig=-50.0,
            new_balance_orig=900.0,
            old_balance_dest=100.0,
            new_balance_dest=200.0,
        )
        self.assertFalse(val_neg_bal.is_valid)
        self.assertIn(RC_INVALID_BALANCE, val_neg_bal.reason_codes)

        # API contract enforcement via Pydantic
        with self.assertRaises(ValidationError):
            index.TransactionInput(
                amount=float("inf"),
                transaction_type="TRANSFER",
                hour_of_day=12,
            )

        with self.assertRaises(ValidationError):
            index.TransactionInput(
                amount=100.0,
                transaction_type="INVALID_CATEGORY",
                hour_of_day=12,
            )

    # 6. Valid transaction that the existing model classifies as fraudulent
    def test_valid_fraud_transaction_not_overridden_by_policy(self):
        # Row 1293 from transactions.csv: TRANSFER, amount=5000, isFraud=1
        fraud_row = self.dataset[self.dataset["isFraud"] == 1].iloc[0]
        payload = {
            "amount": float(fraud_row["amount"]),
            "transaction_type": str(fraud_row["type"]),
            "hour_of_day": int(fraud_row["step"] % 24),
            "step": int(fraud_row["step"]),
            "old_balance_orig": float(fraud_row["oldbalanceOrg"]),
            "new_balance_orig": float(fraud_row["newbalanceOrig"]),
            "old_balance_dest": float(fraud_row["oldbalanceDest"]),
            "new_balance_dest": float(fraud_row["newbalanceDest"]),
        }
        res = index.predict(index.TransactionInput(**payload))

        # Model correctly identified fraud
        self.assertEqual(res.prediction, "FRAUD")
        self.assertEqual(res.risk_level, "HIGH")
        self.assertGreaterEqual(res.fraud_probability, 0.5)

        # Policy did NOT override the fraud classification to ALLOW or LEGITIMATE
        self.assertNotEqual(res.policy_action, "ALLOW")
        self.assertIn(RC_MODEL_HIGH_FRAUD_RISK, res.reason_codes)
        self.assertEqual(res.prediction, "FRAUD")

    # 7. Distinction between ML estimate and rule-based review outcome
    def test_distinction_between_ml_estimate_and_rule_based_review(self):
        # Motivating scenario: ₹1 Crore amount, origin balance 5 -> 4000 (increase!), destination 1000 -> 2000
        req = index.TransactionInput(
            amount=10_000_000.0,
            transaction_type="PAYMENT",
            hour_of_day=12,
            old_balance_orig=5.0,
            new_balance_orig=4000.0,
            old_balance_dest=1000.0,
            new_balance_dest=2000.0,
        )
        res = index.predict(req)

        # 1. Model estimate is preserved as-is (low probability on synthetic PAYMENT)
        self.assertEqual(res.prediction, "LEGITIMATE")
        self.assertEqual(res.risk_level, "LOW")
        self.assertLess(res.fraud_probability, 0.05)

        # 2. Risk policy assessment caught the severe anomalies and rejected the transaction
        self.assertEqual(res.policy_verdict, "REJECTED")
        self.assertEqual(res.policy_action, "REJECT")
        self.assertIn(RC_AMOUNT_EXCEEDS_BALANCE, res.reason_codes)
        self.assertIn(RC_IMPOSSIBLE_BALANCE_MOVEMENT, res.reason_codes)
        self.assertIn(RC_BALANCE_MISMATCH, res.reason_codes)
        self.assertIn(RC_EXCEEDS_TRANSACTION_LIMIT, res.reason_codes)

        # 3. Reconciliation note explains why the two assessments differ
        self.assertIsNotNone(res.reconciliation_note)
        self.assertIn("REJECTED by policy", res.reconciliation_note)

    # 8. Repeat-transfer scenario (velocity monitoring)
    def test_repeat_transfer_velocity_monitoring(self):
        # Transaction with rapid velocity count of 5
        policy = evaluate_transaction_risk_policy(
            amount=9999.0,
            transaction_type="TRANSFER",
            hour_of_day=14,
            old_balance_orig=50000.0,
            new_balance_orig=40001.0,
            old_balance_dest=1000.0,
            new_balance_dest=10999.0,
            model_probability=0.01,
            model_prediction="LEGITIMATE",
            model_risk_level="LOW",
            recent_velocity_count=5,
            velocity_threshold=3,
        )
        self.assertEqual(policy.policy_verdict, "FLAGGED_FOR_REVIEW")
        self.assertEqual(policy.policy_action, "REVIEW")
        self.assertIn(RC_HIGH_TRANSACTION_VELOCITY, policy.reason_codes)
        self.assertTrue(any("Velocity spike" in r for r in policy.reasons))

    # 9. CASH_IN balance semantics
    def test_cash_in_balance_semantics(self):
        # Consistent deposit: origin increases by amount
        bal_ok = assess_balance_semantics(
            amount=2000.0,
            transaction_type="CASH_IN",
            old_balance_orig=1000.0,
            new_balance_orig=3000.0,  # 1000 + 2000 = 3000
            old_balance_dest=0.0,
            new_balance_dest=0.0,
        )
        self.assertTrue(bal_ok.is_consistent)
        self.assertFalse(bal_ok.has_impossible_movement)
        self.assertFalse(bal_ok.amount_exceeds_balance)

        # Impossible deposit: origin decreases during deposit!
        bal_bad = assess_balance_semantics(
            amount=2000.0,
            transaction_type="CASH_IN",
            old_balance_orig=1000.0,
            new_balance_orig=500.0,  # Decreased on deposit!
            old_balance_dest=0.0,
            new_balance_dest=0.0,
        )
        self.assertFalse(bal_bad.is_consistent)
        self.assertTrue(bal_bad.has_impossible_movement)
        self.assertIn(RC_IMPOSSIBLE_BALANCE_MOVEMENT, bal_bad.reason_codes)


if __name__ == "__main__":
    unittest.main()
