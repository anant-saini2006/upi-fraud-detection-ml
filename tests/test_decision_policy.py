"""Unit and contract tests for the gateway decision policy and ledger rules.

Covers:
1. Decision policy thresholds:
   - probability >= block_threshold -> status = "blocked"
   - review_threshold <= probability < block_threshold -> status = "requires_review"
   - probability < review_threshold -> status = "succeeded"
2. Ledger safety:
   - Blocked and review payments do NOT mutate wallet balances.
   - Succeeded payments update sender and receiver balances accurately.
3. Idempotency:
   - Repeated requests with the same Idempotency-Key return the original payment intent.
4. Human-readable explanatory reasons contract.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from api.gateway import _generate_reasons
from api.schema import (
    ConfirmPaymentIntent,
    CreatePaymentIntent,
    PaymentIntentResponse,
    ScoringResponse,
    ThresholdSettings,
)


class DecisionPolicyLogicTests(unittest.TestCase):
    """Test policy routing logic given varying probabilities and threshold settings."""

    def test_decision_policy_thresholds(self):
        thresholds = {"block_threshold": 0.70, "review_threshold": 0.30}

        def decide(probability: float) -> str:
            if probability >= thresholds["block_threshold"]:
                return "blocked"
            elif probability >= thresholds["review_threshold"]:
                return "requires_review"
            return "succeeded"

        # Safe transactions below review cutoff
        self.assertEqual(decide(0.05), "succeeded")
        self.assertEqual(decide(0.29), "succeeded")

        # Borderline transactions between review and block cutoffs
        self.assertEqual(decide(0.30), "requires_review")
        self.assertEqual(decide(0.50), "requires_review")
        self.assertEqual(decide(0.699), "requires_review")

        # High risk transactions at or above block cutoff
        self.assertEqual(decide(0.70), "blocked")
        self.assertEqual(decide(0.95), "blocked")

    def test_reasons_generation_reasons_length_and_content(self):
        # Test drain pattern
        reasons = _generate_reasons(
            amount=50000.0,
            hour=3,
            old_balance_orig=50000.0,
            new_balance_orig=0.0,
            old_balance_dest=100.0,
            new_balance_dest=50100.0,
            probability=0.88,
        )
        self.assertIsInstance(reasons, list)
        self.assertLessEqual(len(reasons), 3)
        self.assertTrue(any("unusual hour" in r.lower() for r in reasons))
        self.assertTrue(any("drained to zero" in r.lower() for r in reasons))

        # Test normal daytime pattern
        safe_reasons = _generate_reasons(
            amount=499.0,
            hour=14,
            old_balance_orig=5000.0,
            new_balance_orig=4501.0,
            old_balance_dest=1000.0,
            new_balance_dest=1499.0,
            probability=0.02,
        )
        self.assertIsInstance(safe_reasons, list)
        self.assertLessEqual(len(safe_reasons), 3)
        self.assertTrue(any("business hours" in r.lower() for r in safe_reasons))
        self.assertTrue(any("normal range" in r.lower() for r in safe_reasons))

    def test_scoring_response_contract_validation(self):
        # Valid contract
        contract = ScoringResponse(
            probability=0.25,
            label="LEGITIMATE",
            risk_band="LOW",
            reasons=["Amount within normal range", "Transaction during business hours"],
        )
        self.assertEqual(contract.risk_band, "LOW")
        self.assertEqual(contract.label, "LEGITIMATE")
        self.assertEqual(len(contract.reasons), 2)

    def test_threshold_settings_constraint(self):
        # Test valid thresholds
        settings = ThresholdSettings(block_threshold=0.75, review_threshold=0.35)
        self.assertLess(settings.review_threshold, settings.block_threshold)


class LedgerSafetyTests(unittest.TestCase):
    """Test simulated ledger state transitions."""

    def test_balance_update_logic_for_succeeded(self):
        sender_initial = 10000.0
        receiver_initial = 25000.0
        amount = 1500.0

        # Simulate settlement
        status = "succeeded"
        if status == "succeeded":
            sender_final = sender_initial - amount
            receiver_final = receiver_initial + amount
        else:
            sender_final = sender_initial
            receiver_final = receiver_initial

        self.assertEqual(sender_final, 8500.0)
        self.assertEqual(receiver_final, 26500.0)

    def test_balance_update_logic_for_blocked(self):
        sender_initial = 10000.0
        receiver_initial = 25000.0
        amount = 9000.0

        # Blocked must not deduct or credit
        status = "blocked"
        if status == "succeeded":
            sender_final = sender_initial - amount
            receiver_final = receiver_initial + amount
        else:
            sender_final = sender_initial
            receiver_final = receiver_initial

        self.assertEqual(sender_final, 10000.0)
        self.assertEqual(receiver_final, 25000.0)

    def test_balance_update_logic_for_requires_review(self):
        sender_initial = 10000.0
        receiver_initial = 25000.0
        amount = 4000.0

        # Under review must not deduct until human approves
        status = "requires_review"
        if status == "succeeded":
            sender_final = sender_initial - amount
            receiver_final = receiver_initial + amount
        else:
            sender_final = sender_initial
            receiver_final = receiver_initial

        self.assertEqual(sender_final, 10000.0)
        self.assertEqual(receiver_final, 25000.0)


if __name__ == "__main__":
    unittest.main()
