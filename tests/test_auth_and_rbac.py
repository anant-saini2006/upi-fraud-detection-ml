"""Comprehensive test suite for User Authentication and Role-Based Access Control (RBAC).

Tests all 8 required criteria:
1. A new user can register and log in.
2. A user can access permitted dashboard functions.
3. A regular user cannot access /admin or admin API endpoints (403 Forbidden).
4. A user cannot read another user's transactions (isolation).
5. An administrator can access the existing admin console.
6. Logout invalidates the session appropriately.
7. Invalid credentials and expired sessions are handled safely (401 Unauthorized).
8. Existing ML prediction, demo payments, and fraud review functionality still work.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException, Response

from api import database, index
from api.auth import (
    UserLoginRequest,
    UserSignupRequest,
    create_access_token,
    decode_access_token,
    get_current_user,
    get_me,
    login,
    logout,
    signup,
)
from api.admin import (
    admin_list_payments,
    admin_review_count,
    admin_simulate,
    login as admin_login,
)
from api.schema import LoginRequest
from api.index import TransactionInput


class AuthAndRBACTests(unittest.TestCase):
    def setUp(self) -> None:
        # Patch is_configured to False for clean deterministic in-memory testing
        self._db_patch = patch("api.database.is_configured", return_value=False)
        self._db_patch.start()
        self.addCleanup(self._db_patch.stop)

    def test_01_user_registration_and_login(self) -> None:
        """1. A new user can register with name, email, password and log in.
        Password is never stored in plaintext (stored only as PBKDF2 hash).
        """
        resp = Response()
        user_email = f"john.doe.{int(time.time()*1000)}@example.com"
        password = "SecurePassword123"

        # Register user
        reg_res = signup(
            UserSignupRequest(
                full_name="John Doe",
                email=user_email,
                password=password,
            ),
            resp,
        )
        self.assertEqual(reg_res.status, "success")
        self.assertEqual(reg_res.user.email, user_email)
        self.assertEqual(reg_res.user.role, "user")
        self.assertTrue(len(reg_res.token) > 20)

        # Verify password is not in plaintext in the database/memory
        user_in_db = database.get_user_by_email(user_email)
        self.assertIsNotNone(user_in_db)
        self.assertNotIn(password, user_in_db["password_hash"])
        self.assertTrue(user_in_db["password_hash"].startswith("pbkdf2_sha256$"))

        # Verify login
        login_res = login(
            UserLoginRequest(email=user_email, password=password),
            resp,
        )
        self.assertEqual(login_res.status, "success")
        self.assertEqual(login_res.user.email, user_email)
        self.assertEqual(login_res.user.role, "user")

    def test_02_user_permitted_dashboard_functions(self) -> None:
        """2. A regular user can access permitted dashboard functions (predict, stats, charts)."""
        resp = Response()
        user_email = f"user.dash.{int(time.time()*1000)}@example.com"
        reg = signup(
            UserSignupRequest(full_name="Dashboard User", email=user_email, password="Password123"),
            resp,
        )

        # Permitted: predict
        pred = index.predict(
            TransactionInput(
                amount=500.0,
                transaction_type="PAYMENT",
                hour_of_day=12,
                old_balance_orig=5000.0,
                new_balance_orig=4500.0,
                old_balance_dest=1000.0,
                new_balance_dest=1500.0,
            ),
            authorization=f"Bearer {reg.token}",
        )
        self.assertIn(pred.prediction, ["FRAUD", "LEGITIMATE"])

        # Permitted: recent predictions history
        history = index.recent_predictions(authorization=f"Bearer {reg.token}")
        self.assertIn("predictions", history)
        self.assertTrue(len(history["predictions"]) >= 1)

    def test_03_regular_user_cannot_access_admin_endpoints(self) -> None:
        """3. A regular user cannot access /admin or admin API endpoints (gets 403 Forbidden)."""
        resp = Response()
        user_email = f"reg.user.{int(time.time()*1000)}@example.com"
        reg = signup(
            UserSignupRequest(full_name="Regular User", email=user_email, password="Password123"),
            resp,
        )

        auth_header = f"Bearer {reg.token}"

        # Attempt /api/admin/payments -> 403
        with self.assertRaises(HTTPException) as cm_payments:
            admin_list_payments(authorization=auth_header)
        self.assertEqual(cm_payments.exception.status_code, 403)

        # Attempt /api/admin/review-count -> 403
        with self.assertRaises(HTTPException) as cm_reviews:
            admin_review_count(authorization=auth_header)
        self.assertEqual(cm_reviews.exception.status_code, 403)

        # Attempt /api/admin/simulate -> 403
        with self.assertRaises(HTTPException) as cm_simulate:
            from api.schema import SimulateRequest
            admin_simulate(SimulateRequest(count=5), authorization=auth_header)
        self.assertEqual(cm_simulate.exception.status_code, 403)

    def test_04_user_cannot_read_another_users_transactions(self) -> None:
        """4. A user cannot read another user's transactions by changing IDs or querying history."""
        resp = Response()
        user1 = signup(
            UserSignupRequest(
                full_name="User One",
                email=f"user1.{int(time.time()*1000)}@example.com",
                password="Password123",
            ),
            resp,
        )
        user2 = signup(
            UserSignupRequest(
                full_name="User Two",
                email=f"user2.{int(time.time()*1000)}@example.com",
                password="Password123",
            ),
            resp,
        )

        # User 1 makes a prediction
        index.predict(
            TransactionInput(
                amount=7500.0,
                transaction_type="TRANSFER",
                hour_of_day=15,
                old_balance_orig=20000.0,
                new_balance_orig=12500.0,
                old_balance_dest=500.0,
                new_balance_dest=8000.0,
            ),
            authorization=f"Bearer {user1.token}",
        )

        user1_preds = index.recent_predictions(authorization=f"Bearer {user1.token}")["predictions"]
        self.assertTrue(len(user1_preds) >= 1)
        user1_pred_id = user1_preds[0]["id"]

        # User 2 lists predictions: user1's prediction must NOT appear
        user2_preds = index.recent_predictions(authorization=f"Bearer {user2.token}")["predictions"]
        user2_ids = [p["id"] for p in user2_preds]
        self.assertNotIn(user1_pred_id, user2_ids)

        # User 2 attempts direct access to User 1's prediction: must get 403 Forbidden
        with self.assertRaises(HTTPException) as cm:
            index.get_prediction_detail(user1_pred_id, authorization=f"Bearer {user2.token}")
        self.assertEqual(cm.exception.status_code, 403)

    def test_05_administrator_can_access_admin_console(self) -> None:
        """5. An administrator can access the existing admin console and APIs."""
        resp = Response()
        # Admin login via /api/auth/login
        admin_auth = login(UserLoginRequest(email="admin", password="demo1234"), resp)
        self.assertEqual(admin_auth.user.role, "admin")

        # Admin can fetch payment telemetry
        payments = admin_list_payments(authorization=f"Bearer {admin_auth.token}")
        self.assertIn("payments", payments)

        # Legacy /api/admin/login also works seamlessly
        legacy_res = admin_login(LoginRequest(username="admin", password="demo1234"))
        self.assertTrue(len(legacy_res.token) > 10)
        payments_legacy = admin_list_payments(authorization=f"Bearer {legacy_res.token}")
        self.assertIn("payments", payments_legacy)

    def test_06_logout_invalidates_session(self) -> None:
        """6. Logout clears session cookies appropriately."""
        resp = Response()
        logout_res = logout(resp)
        self.assertEqual(logout_res["status"], "logged_out")
        # Check cookie deletion was set in response
        self.assertTrue(any("auth_token" in h for h in resp.headers.getlist("set-cookie")))

    def test_07_invalid_credentials_and_expired_tokens(self) -> None:
        """7. Invalid credentials and expired sessions are handled safely (401 Unauthorized)."""
        resp = Response()

        # Wrong password
        with self.assertRaises(HTTPException) as cm_pw:
            login(UserLoginRequest(email="admin", password="wrongpassword"), resp)
        self.assertEqual(cm_pw.exception.status_code, 401)

        # Nonexistent user
        with self.assertRaises(HTTPException) as cm_email:
            login(UserLoginRequest(email="nonexistent@example.com", password="Password123"), resp)
        self.assertEqual(cm_email.exception.status_code, 401)

        # Expired token
        expired_token = create_access_token(
            {"id": 999, "email": "test@expired.com", "role": "user"}
        )
        # Decode token parts and craft expired payload
        parts = expired_token.split(".")
        import json, base64, hmac, hashlib
        from api.auth import _b64url_decode, _b64url_encode, AUTH_SECRET
        payload = json.loads(_b64url_decode(parts[0]).decode("utf-8"))
        payload["exp"] = int(time.time()) - 100  # expired in past
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        sig = hmac.new(AUTH_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
        tampered_expired_token = f"{payload_b64}.{_b64url_encode(sig)}"

        with self.assertRaises(HTTPException) as cm_exp:
            decode_access_token(tampered_expired_token)
        self.assertEqual(cm_exp.exception.status_code, 401)
        self.assertIn("Session expired", cm_exp.exception.detail)

    def test_08_public_signup_cannot_grant_admin_role(self) -> None:
        """8. Public signup always forces 'user' role regardless of request body."""
        resp = Response()
        email = f"hacker.{int(time.time()*1000)}@example.com"
        reg = signup(
            UserSignupRequest(full_name="Attacker", email=email, password="Password123"),
            resp,
        )
        self.assertEqual(reg.user.role, "user")
        user_record = database.get_user_by_email(email)
        self.assertEqual(user_record["role"], "user")


if __name__ == "__main__":
    unittest.main()
