"""Regression tests for Phase 2 audit remediation blockers.

Verifies:
1. Razorpay/Demo Store checkout order creation and mock verification contracts.
2. Unreachable policy-rejection path fix for unsupported transaction types.
3. Gateway input-validation enforcement (non-finite numbers, unsupported operations, VPA checks).
4. Direct endpoint calls attempting validation bypass return 422/ValidationError.
5. Separation of synthetic PaySim types vs gateway checkout operations.
"""

from __future__ import annotations

import math
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError

from api.schema import (
    ConfirmPaymentIntent,
    CreatePaymentIntent,
    ThresholdSettings,
)
from api.gateway import create_intent
from api.payment_integration.razorpay_integration import (
    CreateOrderRequest,
    VerifyPaymentRequest,
    create_order,
    verify_payment,
    DEMO_CATALOG,
    IS_MOCK_MODE,
)
from src.risk_policy import (
    RC_EXCEEDS_TRANSACTION_LIMIT,
    RC_UNSUPPORTED_TRANSACTION_POLICY,
    RC_UNSUPPORTED_TRANSACTION_TYPE,
    SUPPORTED_TRANSACTION_TYPES,
    UPI_NATIVE_TYPES,
    assess_upi_policy,
    evaluate_transaction_risk_policy,
)


class RemediationBlockerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._db_patch = patch("api.database.is_configured", return_value=False)
        self._db_patch.start()
        self.addCleanup(self._db_patch.stop)

        import api.payment_integration.razorpay_integration as rz
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        rz._Base.metadata.create_all(test_engine)
        self._rz_engine_patch = patch.object(rz, "_engine", test_engine)
        self._rz_session_patch = patch.object(rz, "_SessionLocal", sessionmaker(bind=test_engine))
        self._rz_engine_patch.start()
        self._rz_session_patch.start()
        self.addCleanup(self._rz_engine_patch.stop)
        self.addCleanup(self._rz_session_patch.stop)

    # ── Blocker 1: Checkout & Order Creation ─────────────────────────────────

    def test_payment_order_creation_success(self):
        """Verify successful order creation for catalog products in test/mock mode."""
        req = CreateOrderRequest(product_id="demo_item")
        res = create_order(req)

        self.assertIn("order_id", res)
        self.assertTrue(res["order_id"].startswith("order_"))
        self.assertEqual(res["amount"], 19900)  # ₹199 in paise
        self.assertEqual(res["currency"], "INR")
        self.assertEqual(res["product_name"], "Fraud Detection Demo Report")
        self.assertIn("key_id", res)
        self.assertIsInstance(res["is_mock"], bool)

    def test_payment_order_creation_unknown_product(self):
        """Unknown product_id must raise 404 with clean detail, no secret exposure."""
        req = CreateOrderRequest(product_id="non_existent_sku_999")
        with self.assertRaises(HTTPException) as cm:
            create_order(req)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(cm.exception.detail, "Unknown product_id.")

    def test_payment_order_creation_blank_product_id(self):
        """Blank or whitespace-only product_id must fail validation."""
        with self.assertRaises(ValidationError):
            CreateOrderRequest(product_id="   ")

    def test_mock_payment_verification_success_and_tampered_rejection(self):
        """Mock checkout signature verification works and rejects tampered signatures."""
        import hashlib
        import hmac

        order_res = create_order(CreateOrderRequest(product_id="demo_item"))
        order_id = order_res["order_id"]
        payment_id = "pay_mock_test_12345"

        # Generate valid mock signature
        from api.payment_integration.razorpay_integration import MOCK_KEY_SECRET
        valid_sig = hmac.new(
            MOCK_KEY_SECRET.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        # 1. Valid signature verifies successfully
        verify_res = verify_payment(
            VerifyPaymentRequest(
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=valid_sig,
            )
        )
        self.assertTrue(verify_res["verified"])
        self.assertEqual(verify_res["gateway_status"], "captured")
        self.assertEqual(verify_res["payment_id"], payment_id)

        # 2. Tampered signature fails
        with self.assertRaises(HTTPException) as cm:
            verify_payment(
                VerifyPaymentRequest(
                    razorpay_order_id=order_id,
                    razorpay_payment_id=payment_id,
                    razorpay_signature="tampered_signature_hex",
                )
            )
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Invalid mock payment signature", str(cm.exception.detail))

    # ── Blocker 2: Unreachable Policy-Rejection Path ─────────────────────────

    def test_unsupported_transaction_type_rejection_path_reached(self):
        """Unsupported transaction types must reach the REJECTED policy verdict."""
        # 1. assess_upi_policy sets status = UNSUPPORTED_TYPE
        upi = assess_upi_policy(
            amount=500.0,
            transaction_type="CRYPTO",
        )
        self.assertEqual(upi.status, "UNSUPPORTED_TYPE")
        self.assertIn(RC_UNSUPPORTED_TRANSACTION_TYPE, upi.reason_codes)

        # 2. evaluate_transaction_risk_policy rejects it deterministically
        policy = evaluate_transaction_risk_policy(
            amount=500.0,
            transaction_type="CRYPTO",
            hour_of_day=14,
            old_balance_orig=1000.0,
            new_balance_orig=500.0,
            old_balance_dest=100.0,
            new_balance_dest=600.0,
            model_probability=0.01,
            model_prediction="LEGITIMATE",
            model_risk_level="LOW",
        )
        self.assertEqual(policy.policy_verdict, "REJECTED")
        self.assertEqual(policy.policy_action, "REJECT")
        self.assertIn(RC_UNSUPPORTED_TRANSACTION_TYPE, policy.reason_codes)
        self.assertIn("unsupported transaction type", (policy.reconciliation_note or "").lower())

    def test_synthetic_paysim_types_not_rejected_simply_as_non_upi(self):
        """CASH_IN and CASH_OUT are valid PaySim synthetic types and not rejected simply for being non-UPI."""
        # CASH_IN with consistent deposit balance movement
        policy_cash_in = evaluate_transaction_risk_policy(
            amount=500.0,
            transaction_type="CASH_IN",
            hour_of_day=14,
            old_balance_orig=1000.0,
            new_balance_orig=1500.0,  # Correct deposit
            old_balance_dest=0.0,
            new_balance_dest=0.0,
            model_probability=0.01,
            model_prediction="LEGITIMATE",
            model_risk_level="LOW",
        )
        # Should not be rejected solely because CASH_IN is non-UPI
        self.assertNotEqual(policy_cash_in.policy_verdict, "REJECTED")
        self.assertIn(RC_UNSUPPORTED_TRANSACTION_TYPE, policy_cash_in.reason_codes)

    def test_p2p_transfer_cannot_bypass_standard_limit_with_merchant_category(self):
        """P2P transfers (TRANSFER) are strictly capped at ₹1 Lakh even if category is supplied."""
        upi_p2p = assess_upi_policy(
            amount=150000.0,
            transaction_type="TRANSFER",
            merchant_category="healthcare",
        )
        self.assertEqual(upi_p2p.status, "CATEGORY_VERIFICATION_REQUIRED")
        self.assertIn(RC_UNSUPPORTED_TRANSACTION_POLICY, upi_p2p.reason_codes)
        self.assertIn("P2P transfer", " ".join(upi_p2p.reasons))

        # P2M payment (PAYMENT) CAN use verified category up to ₹5 Lakh
        upi_p2m = assess_upi_policy(
            amount=150000.0,
            transaction_type="PAYMENT",
            merchant_category="healthcare",
        )
        self.assertEqual(upi_p2m.status, "PASS")

    # ── Blocker 3: Gateway Input-Validation Bypasses ─────────────────────────

    def test_gateway_schema_rejects_non_finite_amounts(self):
        """CreatePaymentIntent must reject Infinity, -Infinity, and NaN with ValidationError."""
        with self.assertRaises(ValidationError):
            CreatePaymentIntent(
                amount=float("inf"),
                sender_vpa="alice@testpay",
                receiver_vpa="bob@testpay",
            )

        with self.assertRaises(ValidationError):
            CreatePaymentIntent(
                amount=float("-inf"),
                sender_vpa="alice@testpay",
                receiver_vpa="bob@testpay",
            )

        with self.assertRaises(ValidationError):
            CreatePaymentIntent(
                amount=float("nan"),
                sender_vpa="alice@testpay",
                receiver_vpa="bob@testpay",
            )

    def test_gateway_schema_rejects_out_of_range_and_negative_amounts(self):
        """CreatePaymentIntent must reject <= 0 and excessive amounts."""
        with self.assertRaises(ValidationError):
            CreatePaymentIntent(amount=0.0, sender_vpa="alice@testpay", receiver_vpa="bob@testpay")

        with self.assertRaises(ValidationError):
            CreatePaymentIntent(amount=-50.0, sender_vpa="alice@testpay", receiver_vpa="bob@testpay")

        with self.assertRaises(ValidationError):
            CreatePaymentIntent(amount=20_000_000.0, sender_vpa="alice@testpay", receiver_vpa="bob@testpay")

    def test_gateway_schema_validates_vpa_format_and_distinctness(self):
        """VPA must be non-empty, contain @, and sender != receiver."""
        # Missing @
        with self.assertRaises(ValidationError):
            CreatePaymentIntent(amount=100.0, sender_vpa="invalidvpa", receiver_vpa="bob@testpay")

        # Sender == receiver
        with self.assertRaises(ValidationError):
            CreatePaymentIntent(amount=100.0, sender_vpa="alice@testpay", receiver_vpa="alice@testpay")

    def test_gateway_schema_rejects_unsupported_checkout_operations(self):
        """Gateway only supports TRANSFER and PAYMENT; reject CASH_OUT, CRYPTO, etc."""
        # Unsupported checkout operation CASH_OUT
        with self.assertRaises(ValidationError):
            CreatePaymentIntent(
                amount=100.0,
                sender_vpa="alice@testpay",
                receiver_vpa="bob@testpay",
                transaction_type="CASH_OUT",
            )

        # Unsupported checkout operation CRYPTO
        with self.assertRaises(ValidationError):
            CreatePaymentIntent(
                amount=100.0,
                sender_vpa="alice@testpay",
                receiver_vpa="bob@testpay",
                transaction_type="CRYPTO",
            )

        # Supported operations work
        pi_transfer = CreatePaymentIntent(
            amount=100.0,
            sender_vpa="alice@testpay",
            receiver_vpa="bob@testpay",
            transaction_type="TRANSFER",
        )
        self.assertEqual(pi_transfer.transaction_type, "TRANSFER")

        pi_payment = CreatePaymentIntent(
            amount=100.0,
            sender_vpa="alice@testpay",
            receiver_vpa="bob@testpay",
            transaction_type="PAYMENT",
        )
        self.assertEqual(pi_payment.transaction_type, "PAYMENT")

    def test_gateway_endpoint_rejects_unauthorized_and_validates_intents(self):
        """create_intent endpoint validates authentication and persists valid intents."""
        # 1. Missing auth rejects with 401
        with self.assertRaises(HTTPException) as cm:
            create_intent(
                body=CreatePaymentIntent(amount=100.0, sender_vpa="alice@testpay", receiver_vpa="bob@testpay"),
                authorization=None,
            )
        self.assertEqual(cm.exception.status_code, 401)

        # 2. Valid auth and valid body succeeds
        valid_intent = create_intent(
            body=CreatePaymentIntent(amount=100.0, sender_vpa="alice@testpay", receiver_vpa="bob@testpay"),
            authorization="Bearer sk_test_demo_key_001",
        )
        self.assertEqual(valid_intent.amount, 100.0)
        self.assertEqual(valid_intent.sender_vpa, "alice@testpay")
        self.assertEqual(valid_intent.status, "requires_payment_method")

    def test_threshold_settings_validation(self):
        """ThresholdSettings must enforce finite floats and block >= review."""
        # Non-finite
        with self.assertRaises(ValidationError):
            ThresholdSettings(block_threshold=float("nan"), review_threshold=0.3)

        # Inverted thresholds (block < review)
        with self.assertRaises(ValidationError):
            ThresholdSettings(block_threshold=0.2, review_threshold=0.5)

        # Valid thresholds
        ts = ThresholdSettings(block_threshold=0.7, review_threshold=0.3)
        self.assertEqual(ts.block_threshold, 0.7)


if __name__ == "__main__":
    unittest.main()
