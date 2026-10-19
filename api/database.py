"""Mandatory PostgreSQL persistence for the payment gateway.

DATABASE_URL *must* point to a Neon pooled connection string.  The API
will fail fast at startup if it is missing — serverless keeps no local
state, so an in-memory fallback is not an option for the gateway.

Tables managed by this module:
    accounts    — simulated VPA wallets (fake, @testpay domain)
    payments    — Stripe-style payment-intent ledger
    reviews     — admin review verdicts
    settings    — threshold sliders, feature flags
    predictions — backward-compatible prediction history (existing)
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

_ROOT = Path(__file__).resolve().parent.parent

for _env_path in [_ROOT / ".env", _ROOT / ".env.local"]:
    if _env_path.is_file():
        try:
            with _env_path.open(encoding="utf-8") as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        _k = _k.strip()
                        _v = _v.strip().strip("'\"")
                        if _k not in os.environ and _v:
                            os.environ[_k] = _v
        except Exception:
            pass

DATABASE_URL = os.getenv("DATABASE_URL")
_last_error: str | None = None


def is_configured() -> bool:
    """Return whether a PostgreSQL connection string has been supplied."""
    global DATABASE_URL
    if not DATABASE_URL:
        DATABASE_URL = os.getenv("DATABASE_URL")
    return bool(DATABASE_URL)


@contextmanager
def _connection() -> Iterator[Any]:
    """Open one short-lived PostgreSQL connection.

    Short-lived connections are a simple, reliable default for a small
    capstone API and work with Neon connection pooling URLs.
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it to a Neon pooled connection "
            "string (the one with -pooler in the hostname). The gateway requires "
            "PostgreSQL — there is no in-memory fallback."
        )

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


# ── Schema migration ─────────────────────────────────────────────────────────

_MIGRATION_SQL = """
-- Existing predictions table (backward compat)
CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    amount NUMERIC NOT NULL,
    transaction_type TEXT NOT NULL,
    hour_of_day INTEGER NOT NULL,
    prediction TEXT NOT NULL,
    fraud_probability NUMERIC NOT NULL,
    risk_level TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Simulated VPA wallets
CREATE TABLE IF NOT EXISTS accounts (
    id              BIGSERIAL PRIMARY KEY,
    vpa             TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    wallet_balance  NUMERIC(14,2) NOT NULL DEFAULT 10000.00,
    total_sent      NUMERIC(14,2) NOT NULL DEFAULT 0.00,
    total_received  NUMERIC(14,2) NOT NULL DEFAULT 0.00,
    tx_count        INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Stripe-style payment-intent ledger
CREATE TABLE IF NOT EXISTS payments (
    id                  TEXT PRIMARY KEY,
    idempotency_key     TEXT UNIQUE,
    amount              NUMERIC(14,2) NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'INR',
    sender_vpa          TEXT NOT NULL,
    receiver_vpa        TEXT NOT NULL,
    description         TEXT,
    fraud_probability   NUMERIC(8,6),
    fraud_label         TEXT,
    risk_band           TEXT,
    reasons             JSONB,
    status              TEXT NOT NULL DEFAULT 'requires_payment_method',
    decline_reason      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at        TIMESTAMPTZ,
    reviewed_at         TIMESTAMPTZ,
    simulated_hour      INTEGER,
    scenario_tag        TEXT
);

-- Admin review verdicts
CREATE TABLE IF NOT EXISTS reviews (
    id              BIGSERIAL PRIMARY KEY,
    payment_id      TEXT NOT NULL,
    reviewer        TEXT,
    verdict         TEXT NOT NULL,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Threshold sliders, feature flags
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_SEED_ACCOUNTS = [
    ("alice@testpay", "Alice Demo", 50000.00),
    ("bob@testpay", "Bob's Shop", 25000.00),
    ("carol@testpay", "Carol Merchant", 100000.00),
    ("eve@testpay", "Eve (Fraudster)", 80000.00),
    ("mallory@testpay", "Mallory Mule", 5000.00),
]

_DEFAULT_SETTINGS = {
    "block_threshold": 0.70,
    "review_threshold": 0.30,
}


def initialise_database() -> bool:
    """Create all tables and seed data when PostgreSQL is configured.

    Returns ``False`` instead of preventing the API from starting when the
    database is temporarily unavailable.
    """
    global _last_error
    if not is_configured():
        _last_error = "DATABASE_URL is not configured"
        return False

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(_MIGRATION_SQL)

                # Seed accounts (idempotent — skip existing VPAs).
                for vpa, name, balance in _SEED_ACCOUNTS:
                    cursor.execute(
                        """
                        INSERT INTO accounts (vpa, display_name, wallet_balance)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (vpa) DO NOTHING
                        """,
                        (vpa, name, balance),
                    )

                # Seed default settings (idempotent).
                for key, value in _DEFAULT_SETTINGS.items():
                    cursor.execute(
                        """
                        INSERT INTO settings (key, value)
                        VALUES (%s, %s)
                        ON CONFLICT (key) DO NOTHING
                        """,
                        (key, json.dumps(value)),
                    )

        _last_error = None
        return True
    except Exception as exc:  # pragma: no cover
        _last_error = str(exc)
        return False


# ── Prediction history (backward compat) ─────────────────────────────────────


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
    except Exception as exc:  # pragma: no cover
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
    except Exception as exc:  # pragma: no cover
        _last_error = str(exc)
        return []


# ── Account operations ───────────────────────────────────────────────────────


def get_account(vpa: str) -> Optional[dict[str, Any]]:
    """Return account info for a VPA, or None if not found."""
    if not is_configured():
        return None
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT vpa, display_name, wallet_balance, total_sent,
                           total_received, tx_count
                    FROM accounts WHERE vpa = %s
                    """,
                    (vpa,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return {
            "vpa": str(row[0]),
            "display_name": str(row[1]),
            "wallet_balance": float(row[2]),
            "total_sent": float(row[3]),
            "total_received": float(row[4]),
            "tx_count": int(row[5]),
        }
    except Exception:
        return None


def list_accounts() -> list[dict[str, Any]]:
    """Return all accounts."""
    if not is_configured():
        return []
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT vpa, display_name, wallet_balance, total_sent,
                           total_received, tx_count
                    FROM accounts ORDER BY vpa
                    """
                )
                rows = cursor.fetchall()
        return [
            {
                "vpa": str(r[0]),
                "display_name": str(r[1]),
                "wallet_balance": float(r[2]),
                "total_sent": float(r[3]),
                "total_received": float(r[4]),
                "tx_count": int(r[5]),
            }
            for r in rows
        ]
    except Exception:
        return []


def update_balances(
    sender_vpa: str,
    receiver_vpa: str,
    amount: float,
) -> bool:
    """Move money between two simulated wallets. Returns False on failure."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE accounts
                    SET wallet_balance = wallet_balance - %s,
                        total_sent = total_sent + %s,
                        tx_count = tx_count + 1,
                        updated_at = NOW()
                    WHERE vpa = %s AND wallet_balance >= %s
                    """,
                    (amount, amount, sender_vpa, amount),
                )
                if cursor.rowcount == 0:
                    return False
                cursor.execute(
                    """
                    UPDATE accounts
                    SET wallet_balance = wallet_balance + %s,
                        total_received = total_received + %s,
                        tx_count = tx_count + 1,
                        updated_at = NOW()
                    WHERE vpa = %s
                    """,
                    (amount, amount, receiver_vpa),
                )
        return True
    except Exception:
        return False


# ── Payment operations ───────────────────────────────────────────────────────


def create_payment(
    *,
    payment_id: str,
    idempotency_key: Optional[str],
    amount: float,
    currency: str,
    sender_vpa: str,
    receiver_vpa: str,
    description: Optional[str],
    scenario_tag: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Create a payment intent. Returns the payment record or None on failure."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                # Check idempotency first.
                if idempotency_key:
                    cursor.execute(
                        "SELECT id FROM payments WHERE idempotency_key = %s",
                        (idempotency_key,),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        return get_payment(existing[0])

                now = datetime.now(timezone.utc)
                cursor.execute(
                    """
                    INSERT INTO payments (
                        id, idempotency_key, amount, currency,
                        sender_vpa, receiver_vpa, description, created_at, scenario_tag
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        payment_id,
                        idempotency_key,
                        amount,
                        currency,
                        sender_vpa,
                        receiver_vpa,
                        description,
                        now,
                        scenario_tag,
                    ),
                )
        return get_payment(payment_id)
    except Exception:
        return None


def get_payment(payment_id: str) -> Optional[dict[str, Any]]:
    """Return a single payment record."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, idempotency_key, amount, currency,
                           sender_vpa, receiver_vpa, description,
                           fraud_probability, fraud_label, risk_band,
                           reasons, status, decline_reason,
                           created_at, confirmed_at, reviewed_at,
                           simulated_hour, scenario_tag
                    FROM payments WHERE id = %s
                    """,
                    (payment_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        reasons_raw = row[10]
        if isinstance(reasons_raw, str):
            reasons_raw = json.loads(reasons_raw)
        return {
            "id": str(row[0]),
            "idempotency_key": row[1],
            "amount": float(row[2]),
            "currency": str(row[3]),
            "sender_vpa": str(row[4]),
            "receiver_vpa": str(row[5]),
            "description": row[6],
            "fraud_probability": float(row[7]) if row[7] is not None else None,
            "fraud_label": row[8],
            "risk_band": row[9],
            "reasons": reasons_raw if reasons_raw else [],
            "status": str(row[11]),
            "decline_reason": row[12],
            "created_at": row[13].isoformat() if row[13] else None,
            "confirmed_at": row[14].isoformat() if row[14] else None,
            "reviewed_at": row[15].isoformat() if row[15] else None,
            "simulated_hour": row[16],
            "scenario_tag": row[17],
        }
    except Exception:
        return None


def update_payment_scoring(
    payment_id: str,
    *,
    status: str,
    fraud_probability: float,
    fraud_label: str,
    risk_band: str,
    reasons: list[str],
    decline_reason: Optional[str] = None,
    simulated_hour: Optional[int] = None,
    scenario_tag: Optional[str] = None,
) -> bool:
    """Update a payment with scoring results after confirm."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE payments
                    SET status = %s,
                        fraud_probability = %s,
                        fraud_label = %s,
                        risk_band = %s,
                        reasons = %s,
                        decline_reason = %s,
                        confirmed_at = NOW(),
                        simulated_hour = %s,
                        scenario_tag = %s
                    WHERE id = %s
                    """,
                    (
                        status,
                        round(fraud_probability, 6),
                        fraud_label,
                        risk_band,
                        json.dumps(reasons),
                        decline_reason,
                        simulated_hour,
                        scenario_tag,
                        payment_id,
                    ),
                )
        return True
    except Exception:
        return False


def list_payments(
    *,
    limit: int = 50,
    status_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return recent payments, optionally filtered by status."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                if status_filter:
                    cursor.execute(
                        """
                        SELECT id, amount, currency, sender_vpa, receiver_vpa,
                               description, fraud_probability, fraud_label,
                               risk_band, status, created_at, confirmed_at,
                               simulated_hour, scenario_tag
                        FROM payments
                        WHERE status = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (status_filter, min(limit, 200)),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, amount, currency, sender_vpa, receiver_vpa,
                               description, fraud_probability, fraud_label,
                               risk_band, status, created_at, confirmed_at,
                               simulated_hour, scenario_tag
                        FROM payments
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (min(limit, 200),),
                    )
                rows = cursor.fetchall()
        return [
            {
                "id": str(r[0]),
                "amount": float(r[1]),
                "currency": str(r[2]),
                "sender_vpa": str(r[3]),
                "receiver_vpa": str(r[4]),
                "description": r[5],
                "fraud_probability": float(r[6]) if r[6] is not None else None,
                "fraud_label": r[7],
                "risk_band": r[8],
                "status": str(r[9]),
                "created_at": r[10].isoformat() if r[10] else None,
                "confirmed_at": r[11].isoformat() if r[11] else None,
                "simulated_hour": r[12],
                "scenario_tag": r[13],
            }
            for r in rows
        ]
    except Exception:
        return []


def count_reviews_pending() -> int:
    """Count payments in requires_review status."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM payments WHERE status = 'requires_review'"
                )
                row = cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


# ── Review operations ────────────────────────────────────────────────────────


def create_review(
    *,
    payment_id: str,
    reviewer: str,
    verdict: str,
    note: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Record an admin review verdict and update the payment status."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO reviews (payment_id, reviewer, verdict, note)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, created_at
                    """,
                    (payment_id, reviewer, verdict, note),
                )
                row = cursor.fetchone()
                review_id = int(row[0])
                created_at = row[1]

                # Update the payment status based on verdict.
                new_status = (
                    "succeeded" if verdict == "approved" else "blocked"
                )
                cursor.execute(
                    """
                    UPDATE payments
                    SET status = %s, reviewed_at = NOW()
                    WHERE id = %s
                    """,
                    (new_status, payment_id),
                )

                # If approved, also move the money.
                if verdict == "approved":
                    cursor.execute(
                        "SELECT amount, sender_vpa, receiver_vpa FROM payments WHERE id = %s",
                        (payment_id,),
                    )
                    pi = cursor.fetchone()
                    if pi:
                        amount, sender, receiver = float(pi[0]), str(pi[1]), str(pi[2])
                        cursor.execute(
                            """
                            UPDATE accounts
                            SET wallet_balance = wallet_balance - %s,
                                total_sent = total_sent + %s,
                                tx_count = tx_count + 1,
                                updated_at = NOW()
                            WHERE vpa = %s
                            """,
                            (amount, amount, sender),
                        )
                        cursor.execute(
                            """
                            UPDATE accounts
                            SET wallet_balance = wallet_balance + %s,
                                total_received = total_received + %s,
                                tx_count = tx_count + 1,
                                updated_at = NOW()
                            WHERE vpa = %s
                            """,
                            (amount, amount, receiver),
                        )

        return {
            "id": review_id,
            "payment_id": payment_id,
            "reviewer": reviewer,
            "verdict": verdict,
            "note": note,
            "created_at": created_at.isoformat() if created_at else None,
        }
    except Exception:
        return None


def list_reviews(payment_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Return reviews, optionally filtered by payment ID."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                if payment_id:
                    cursor.execute(
                        """
                        SELECT id, payment_id, reviewer, verdict, note, created_at
                        FROM reviews WHERE payment_id = %s
                        ORDER BY created_at DESC
                        """,
                        (payment_id,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, payment_id, reviewer, verdict, note, created_at
                        FROM reviews ORDER BY created_at DESC LIMIT 100
                        """
                    )
                rows = cursor.fetchall()
        return [
            {
                "id": int(r[0]),
                "payment_id": str(r[1]),
                "reviewer": r[2],
                "verdict": str(r[3]),
                "note": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
            }
            for r in rows
        ]
    except Exception:
        return []


# ── Settings operations ──────────────────────────────────────────────────────


def get_setting(key: str) -> Any:
    """Return a setting value, or None if not found."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT value FROM settings WHERE key = %s", (key,))
                row = cursor.fetchone()
        if row is None:
            return None
        value = row[0]
        if isinstance(value, str):
            return json.loads(value)
        return value
    except Exception:
        return None


def get_thresholds() -> dict[str, float]:
    """Return current block/review thresholds with defaults."""
    block = get_setting("block_threshold")
    review = get_setting("review_threshold")
    return {
        "block_threshold": float(block) if block is not None else 0.70,
        "review_threshold": float(review) if review is not None else 0.30,
    }


def update_setting(key: str, value: Any) -> bool:
    """Upsert a setting value."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO settings (key, value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (key)
                    DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                    """,
                    (key, json.dumps(value)),
                )
        return True
    except Exception:
        return False


# ── Demo reset ───────────────────────────────────────────────────────────────


def reset_demo() -> bool:
    """Reset all demo data: clear payments/reviews, restore wallet balances."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM reviews")
                cursor.execute("DELETE FROM payments")
                cursor.execute("DELETE FROM predictions")

                # Reset all accounts to seed values.
                for vpa, name, balance in _SEED_ACCOUNTS:
                    cursor.execute(
                        """
                        UPDATE accounts
                        SET wallet_balance = %s,
                            total_sent = 0,
                            total_received = 0,
                            tx_count = 0,
                            updated_at = NOW()
                        WHERE vpa = %s
                        """,
                        (balance, vpa),
                    )
        return True
    except Exception:
        return False


# ── Health status ────────────────────────────────────────────────────────────


def status() -> dict[str, Any]:
    """Return safe persistence status for the health endpoint."""
    return {
        "configured": is_configured(),
        "available": is_configured() and _last_error is None,
        "last_error": _last_error if is_configured() else None,
    }
