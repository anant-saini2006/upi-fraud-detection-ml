"""Optional PostgreSQL persistence for FastAPI prediction history.

The API works without a database for local model development.  Set
``DATABASE_URL`` to a Neon/PostgreSQL connection string in the API deployment
to enable durable prediction history.  The driver is imported lazily so a
developer can run the prediction endpoint before provisioning Neon.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


DATABASE_URL = os.getenv("DATABASE_URL")
_last_error: str | None = None


def is_configured() -> bool:
    """Return whether a PostgreSQL connection string has been supplied."""
    return bool(DATABASE_URL)


@contextmanager
def _connection() -> Iterator[Any]:
    """Open one short-lived PostgreSQL connection.

    Short-lived connections are a simple, reliable default for a small
    capstone API and work with Neon connection pooling URLs.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover - depends on local setup
        raise RuntimeError(
            "PostgreSQL driver is unavailable. Install api/requirements.txt."
        ) from exc

    connection = psycopg2.connect(DATABASE_URL, connect_timeout=5)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialise_database() -> bool:
    """Create the prediction-history table when PostgreSQL is configured.

    Returns ``False`` instead of preventing the model API from starting when
    the optional database is absent or temporarily unavailable.
    """
    global _last_error
    if not is_configured():
        return False

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS predictions (
                        id BIGSERIAL PRIMARY KEY,
                        amount NUMERIC NOT NULL,
                        transaction_type TEXT NOT NULL,
                        hour_of_day INTEGER NOT NULL,
                        prediction TEXT NOT NULL,
                        fraud_probability NUMERIC NOT NULL,
                        risk_level TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
        _last_error = None
        return True
    except Exception as exc:  # pragma: no cover - needs an external database
        _last_error = str(exc)
        return False


def record_prediction(
    *,
    amount: float,
    transaction_type: str,
    hour_of_day: int,
    prediction: str,
    fraud_probability: float,
    risk_level: str,
) -> bool:
    """Persist one prediction, returning False if persistence is unavailable."""
    global _last_error
    if not is_configured():
        return False

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO predictions (
                        amount, transaction_type, hour_of_day, prediction,
                        fraud_probability, risk_level, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        round(amount, 2),
                        transaction_type,
                        hour_of_day,
                        prediction,
                        round(fraud_probability, 6),
                        risk_level,
                        datetime.now(timezone.utc),
                    ),
                )
        _last_error = None
        return True
    except Exception as exc:  # pragma: no cover - needs an external database
        _last_error = str(exc)
        return False


def get_recent_predictions(limit: int = 10) -> list[dict[str, Any]]:
    """Return recent predictions, or an empty list without an active database."""
    global _last_error
    if not is_configured():
        return []

    safe_limit = max(1, min(int(limit), 100))
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, amount, transaction_type, prediction,
                           fraud_probability, risk_level, created_at
                    FROM predictions
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
                rows = cursor.fetchall()

        _last_error = None
        return [
            {
                "id": int(row[0]),
                "amount": float(row[1]),
                "transaction_type": str(row[2]),
                "prediction": str(row[3]),
                "fraud_probability": float(row[4]),
                "risk_level": str(row[5]),
                "created_at": row[6].isoformat(),
            }
            for row in rows
        ]
    except Exception as exc:  # pragma: no cover - needs an external database
        _last_error = str(exc)
        return []


def status() -> dict[str, Any]:
    """Return safe persistence status for the health endpoint."""
    return {
        "configured": is_configured(),
        "available": is_configured() and _last_error is None,
        "last_error": _last_error if is_configured() else None,
    }
