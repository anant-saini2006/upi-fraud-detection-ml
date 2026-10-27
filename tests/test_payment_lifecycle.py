"""Tests for payment lifecycle: checkout simulation, verification, state transitions, and admin console reconciliation."""

from __future__ import annotations

import hashlib
import hmac
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError

from api.database import (
    _MEMORY_ACCOUNTS,
    _MEMORY_PAYMENTS,
    cancel_payment,
    create_payment,
    get_account,
    get_payment,
    list_payments,
)
from api.gateway import (
    cancel_intent,
    confirm_intent,
    create_intent,
)
from api.payment_integration.razorpay_integration import (
    CreateOrderRequest,
    MOCK_KEY_SECRET,
    VerifyPaymentRequest,
    create_order,
    get_order,
    verify_payment,
)
from api.schema import ConfirmPaymentIntent, CreatePaymentIntent


class PaymentLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        # Patch is_configured to False so unit tests execute deterministically
        # in memory without making slow remote network connections to Neon PostgreSQL.
        self._db_patch = patch("api.database.is_configured", return_value=False)
        self._db_patch.start()
        self.addCleanup(self._db_patch.stop)

        # Patch razorpay_integration to in-memory SQLite to prevent network timeouts during test runs
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

        # Reset in-memory test state
        _MEMORY_PAYMENTS.clear()
        _MEMORY_ACCOUNTS["alice@testpay"] = {
            "vpa": "alice@testpay",
            "display_name": "Alice Demo",
            "wallet_balance": 50000.0,
            "total_sent": 0.0,
            "total_received": 0.0,
            "tx_count": 0,
        }
        _MEMORY_ACCOUNTS["bob@testpay"] = {
            "vpa": "bob@testpay",
            "display_name": "Bob's Shop",
            "wallet_balance": 25000.0,
            "total_sent": 0.0,
            "total_received": 0.0,
            "tx_count": 0,
        }

    # -------------------------------------------------------------------------
    # 1. Simulated Razorpay Checkout and Verification Flow
    # -------------------------------------------------------------------------

    def test_successful_simulated_checkout_and_verification(self) -> None:
        """Simulate checkout order creation, authentic HMAC signing, and server verification."""
        order_res = create_order(CreateOrderRequest(product_id="prod_1"))
        self.assertIn("order_id", order_res)
        self.assertTrue(order_res["order_id"].startswith("order_mock_"))
        self.assertEqual(order_res["amount"], 49900)  # ₹499 in paise

        # Compute valid HMAC-SHA256 signature
        order_id = order_res["order_id"]
        payment_id = "pay_mock_test_12345"
        valid_signature = hmac.new(
            MOCK_KEY_SECRET.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        # Verify through backend endpoint
        verify_req = VerifyPaymentRequest(
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
            razorpay_signature=valid_signature,
        )
        verify_res = verify_payment(verify_req)

        self.assertTrue(verify_res["verified"])
        self.assertEqual(verify_res["gateway_status"], "captured")
        self.assertEqual(verify_res["payment_id"], payment_id)

        # Confirm persisted order state
        saved_order = get_order(order_id)
        self.assertEqual(saved_order["gateway_status"], "captured")
        self.assertEqual(saved_order["amount_paise"], 49900)

    def test_backend_verification_failure_on_tampered_signature(self) -> None:
        """Verification must reject tampered or forged signatures."""
        order_res = create_order(CreateOrderRequest(product_id="prod_1"))
        order_id = order_res["order_id"]

        verify_req = VerifyPaymentRequest(
            razorpay_order_id=order_id,
            razorpay_payment_id="pay_mock_tampered_999",
            razorpay_signature="bad_signature_0000000000000000000000000000000000000000000000000000000000000000",
        )
        with self.assertRaises(HTTPException) as ctx:
            verify_payment(verify_req)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid mock payment signature", ctx.exception.detail)

    def test_verification_failure_for_nonexistent_order(self) -> None:
        """Verification must reject orders not found in the database."""
        verify_req = VerifyPaymentRequest(
            razorpay_order_id="order_mock_nonexistent_99999",
            razorpay_payment_id="pay_mock_12345",
            razorpay_signature="any_sig",
        )
        with self.assertRaises(HTTPException) as ctx:
            verify_payment(verify_req)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Order not found in database", ctx.exception.detail)

    def test_malformed_verification_payload_rejected(self) -> None:
        """Pydantic schema must reject empty or blank verification fields."""
        with self.assertRaises(ValidationError):
            VerifyPaymentRequest(
                razorpay_order_id="   ",
                razorpay_payment_id="pay_mock_123",
                razorpay_signature="sig_123",
            )
        with self.assertRaises(ValidationError):
            VerifyPaymentRequest(
                razorpay_order_id="order_123",
                razorpay_payment_id="",
                razorpay_signature="sig_123",
            )

    def test_duplicate_verification_requests_idempotent(self) -> None:
        """Repeating verification for the same order must succeed without side effects."""
        order_res = create_order(CreateOrderRequest(product_id="prod_1"))
        order_id = order_res["order_id"]
        payment_id = "pay_mock_dup_001"
        signature = hmac.new(
            MOCK_KEY_SECRET.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        req = VerifyPaymentRequest(
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
            razorpay_signature=signature,
        )
        first_res = verify_payment(req)
        second_res = verify_payment(req)

        self.assertTrue(first_res["verified"])
        self.assertTrue(second_res["verified"])
        self.assertEqual(first_res["gateway_status"], second_res["gateway_status"])

    # -------------------------------------------------------------------------
    # 2. Payment Intent Lifecycle, State Transitions & Idempotency
    # -------------------------------------------------------------------------

    def test_payment_intent_success_flow_and_idempotent_confirm(self) -> None:
        """Payment intent progresses from requires_payment_method to succeeded, and repeat confirm is idempotent."""
        auth_header = "Bearer sk_test_demo_key_001"
        created = create_intent(
            CreatePaymentIntent(
                amount=499.0,
                sender_vpa="alice@testpay",
                receiver_vpa="bob@testpay",
                description="Earbuds test purchase",
            ),
            authorization=auth_header,
        )
        self.assertEqual(created.status, "requires_payment_method")
        self.assertIsNone(created.scoring)

        # Confirm intent at business hours
        confirmed = confirm_intent(
            payment_id=created.id,
            body=ConfirmPaymentIntent(simulated_hour=14),
            authorization=auth_header,
        )
        self.assertEqual(confirmed.status, "succeeded")
        self.assertIsNotNone(confirmed.scoring)

        # Balances must be transferred
        alice = get_account("alice@testpay")
        self.assertIsNotNone(alice)
        self.assertEqual(alice["wallet_balance"], 50000.0 - 499.0)

        # Idempotent repeat confirmation
        repeat_confirmed = confirm_intent(
            payment_id=created.id,
            body=ConfirmPaymentIntent(simulated_hour=14),
            authorization=auth_header,
        )
        self.assertEqual(repeat_confirmed.status, "succeeded")
        # Ensure ledger balances were NOT deducted twice
        alice_after_repeat = get_account("alice@testpay")
        self.assertIsNotNone(alice_after_repeat)
        self.assertEqual(alice_after_repeat["wallet_balance"], 50000.0 - 499.0)

    def test_payment_intent_cancellation(self) -> None:
        """Unconfirmed payment intent transitions to cancelled and cannot be confirmed."""
        auth_header = "Bearer sk_test_demo_key_001"
        created = create_intent(
            CreatePaymentIntent(
                amount=499.0,
                sender_vpa="alice@testpay",
                receiver_vpa="bob@testpay",
                description="Cancelled purchase test",
            ),
            authorization=auth_header,
        )
        self.assertEqual(created.status, "requires_payment_method")

        # Cancel intent
        cancelled = cancel_intent(payment_id=created.id, authorization=auth_header)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(cancelled.decline_reason, "Cancelled by user")

        # Repeat cancel is idempotent
        repeat_cancelled = cancel_intent(payment_id=created.id, authorization=auth_header)
        self.assertEqual(repeat_cancelled.status, "cancelled")

        # Attempt to confirm a cancelled intent must be rejected
        with self.assertRaises(HTTPException) as ctx:
            confirm_intent(
                payment_id=created.id,
                body=ConfirmPaymentIntent(simulated_hour=14),
                authorization=auth_header,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cancelled and cannot be confirmed", ctx.exception.detail)

    def test_client_cannot_force_success_status(self) -> None:
        """ConfirmPaymentIntent does not accept client status field; server computes status."""
        body = ConfirmPaymentIntent(simulated_hour=14)
        self.assertFalse(hasattr(body, "status"))

    def test_admin_list_payments_includes_unconfirmed_and_cancelled(self) -> None:
        """Admin payment list includes all lifecycle states including requires_payment_method and cancelled."""
        p1 = create_payment(
            payment_id="pi_lifecycle_unconfirmed",
            idempotency_key=None,
            amount=499.0,
            currency="INR",
            sender_vpa="alice@testpay",
            receiver_vpa="bob@testpay",
            description="Pending Checkout Test",
        )
        p2 = create_payment(
            payment_id="pi_lifecycle_cancelled",
            idempotency_key=None,
            amount=1499.0,
            currency="INR",
            sender_vpa="alice@testpay",
            receiver_vpa="bob@testpay",
            description="Aborted Checkout Test",
        )
        cancel_payment(p2["id"], "Cancelled by user")

        all_payments = list_payments(limit=100)
        payment_ids = [p["id"] for p in all_payments]
        self.assertIn("pi_lifecycle_unconfirmed", payment_ids)
        self.assertIn("pi_lifecycle_cancelled", payment_ids)

        unconfirmed = [p for p in all_payments if p["id"] == "pi_lifecycle_unconfirmed"][0]
        self.assertEqual(unconfirmed["status"], "requires_payment_method")

        cancelled = [p for p in all_payments if p["id"] == "pi_lifecycle_cancelled"][0]
        self.assertEqual(cancelled["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
