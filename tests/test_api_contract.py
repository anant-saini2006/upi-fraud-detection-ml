"""Fast, local checks for the saved-model FastAPI contract.

These tests call route functions directly, so they do not need a TCP port or a
running PostgreSQL instance. They assume ``python src/train_model.py`` has
already generated the committed model artifacts.
"""

from __future__ import annotations

import asyncio
import io
import unittest

from pydantic import ValidationError
from starlette.datastructures import UploadFile

from api import index


def _payload_from_row(row):
    """Map a dataset row into the public prediction request schema."""
    return {
        "amount": float(row["amount"]),
        "transaction_type": str(row["type"]),
        "hour_of_day": int(row["step"] % 24),
        "old_balance_orig": float(row["oldbalanceOrg"]),
        "new_balance_orig": float(row["newbalanceOrig"]),
        "old_balance_dest": float(row["oldbalanceDest"]),
        "new_balance_dest": float(row["newbalanceDest"]),
    }


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = index._require_dataset()

    def test_health_reports_loaded_artifacts(self):
        status = index.health()
        self.assertTrue(status["model_loaded"])
        self.assertTrue(status["preprocessor_loaded"])
        self.assertTrue(status["dataset_loaded"])

    def test_prediction_accepts_raw_schema_and_returns_probability(self):
        # Use a real input row instead of fixture-specific hard-coded amounts,
        # keeping the test valid after a documented dataset replacement.
        row = self.dataset.iloc[0]
        response = index.predict(index.TransactionInput(**_payload_from_row(row)))

        self.assertIn(response.prediction, {"FRAUD", "LEGITIMATE"})
        self.assertIn(response.risk_level, {"LOW", "MEDIUM", "HIGH"})
        self.assertGreaterEqual(response.fraud_probability, 0.0)
        self.assertLessEqual(response.fraud_probability, 1.0)

    def test_transaction_type_is_normalised_and_checked(self):
        row = self.dataset.iloc[0]
        payload = _payload_from_row(row)
        payload["transaction_type"] = payload["transaction_type"].lower()
        request = index.TransactionInput(**payload)
        self.assertEqual(request.transaction_type, str(row["type"]).upper())

        with self.assertRaises(ValidationError):
            index.TransactionInput(**{**payload, "transaction_type": "NOT_A_TYPE"})

    def test_dashboard_and_evaluation_routes_return_real_data(self):
        stats = index.stats()
        self.assertEqual(stats["total_transactions"], len(self.dataset))
        self.assertGreaterEqual(stats["fraud_count"], 0)
        self.assertGreater(len(index.chart_fraud_by_type()), 0)
        self.assertGreater(len(index.chart_fraud_by_hour()), 0)

        evaluation = index.model_performance()
        self.assertEqual(
            set(evaluation["metrics"]),
            {"accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "false_positive_rate"},
        )
        self.assertEqual(set(evaluation["confusion_matrix"]), {"tn", "fp", "fn", "tp"})

    def test_csv_analysis_keeps_uploaded_data_separate_from_model_training(self):
        async def analyse_sample():
            upload = UploadFile(
                filename="sample.csv",
                file=io.BytesIO(
                    b"type,amount,isFraud\nPAYMENT,20,0\nTRANSFER,500,1\n"
                ),
            )
            return await index.analyse_csv(upload)

        result = asyncio.run(analyse_sample())
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["fraud_count"], 1)
        self.assertEqual(result["fraud_rate"], 50.0)

    def test_admin_auth_stateless_tokens(self):
        from api import admin
        from api.schema import LoginRequest
        from fastapi import HTTPException

        # 1. Valid login produces a signed token containing dot separator
        resp = admin.login(LoginRequest(username="admin", password="demo1234"))
        token = resp.token
        self.assertIn(".", token)
        self.assertEqual(resp.username, "admin")

        # 2. Token can be validated across simulated fresh containers (empty _sessions)
        admin._sessions.clear()
        validated_user = admin._validate_session(f"Bearer {token}")
        self.assertEqual(validated_user, "admin")

        # 3. Invalid credentials reject with 401
        with self.assertRaises(HTTPException) as cm:
            admin.login(LoginRequest(username="admin", password="wrongpassword"))
        self.assertEqual(cm.exception.status_code, 401)

        # 4. Tampered token signature fails with 401
        tampered_token = token[:-4] + "xxxx"
        with self.assertRaises(HTTPException) as cm:
            admin._validate_session(f"Bearer {tampered_token}")
        self.assertEqual(cm.exception.status_code, 401)

        # 5. Missing or invalid header fails with 401
        with self.assertRaises(HTTPException) as cm:
            admin._validate_session(None)
        self.assertEqual(cm.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
