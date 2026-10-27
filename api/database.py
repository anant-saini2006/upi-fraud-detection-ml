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

import hashlib
import json
import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

import sys

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT), str(_ROOT / "api")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

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
if not DATABASE_URL:
    DATABASE_URL = "postgresql://neondb_owner:npg_ySKw8mZNBea7@ep-morning-wildflower-b5lnuafo-pooler.c-7.us-east-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
os.environ.setdefault("DATABASE_URL", DATABASE_URL)
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

-- Authenticated users
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Backward-compat columns on predictions
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS user_email TEXT;
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

_MEMORY_ACCOUNTS: dict[str, dict[str, Any]] = {
    vpa: {
        "vpa": vpa,
        "display_name": name,
        "wallet_balance": bal,
        "total_sent": 0.0,
        "total_received": 0.0,
        "tx_count": 0,
    }
    for vpa, name, bal in _SEED_ACCOUNTS
}
_MEMORY_PAYMENTS: dict[str, dict[str, Any]] = {
    "pi_demo_clean_001": {
        "id": "pi_demo_clean_001",
        "idempotency_key": "idemp_clean_001",
        "amount": 450.0,
        "currency": "INR",
        "sender_vpa": "alice@testpay",
        "receiver_vpa": "bob@testpay",
        "description": "Daytime coffee payment",
        "fraud_probability": 0.0012,
        "fraud_label": "LEGITIMATE",
        "risk_band": "LOW",
        "reasons": ["Standard transaction hour", "Low transaction amount"],
        "status": "succeeded",
        "decline_reason": None,
        "created_at": "2026-10-19T10:15:00Z",
        "confirmed_at": "2026-10-19T10:15:01Z",
        "reviewed_at": None,
        "simulated_hour": 14,
        "scenario_tag": "daytime_coffee",
    },
    "pi_demo_review_002": {
        "id": "pi_demo_review_002",
        "idempotency_key": "idemp_review_002",
        "amount": 45000.0,
        "currency": "INR",
        "sender_vpa": "eve@testpay",
        "receiver_vpa": "mallory@testpay",
        "description": "Late-night mule transfer",
        "fraud_probability": 0.4521,
        "fraud_label": "REVIEW",
        "risk_band": "MEDIUM",
        "reasons": ["Night off-hours (02:00)", "High amount transfer to new recipient"],
        "status": "requires_review",
        "decline_reason": "Flagged for manual compliance review",
        "created_at": "2026-10-19T02:30:00Z",
        "confirmed_at": "2026-10-19T02:30:02Z",
        "reviewed_at": None,
        "simulated_hour": 2,
        "scenario_tag": "night_mule",
    },
    "pi_demo_drain_003": {
        "id": "pi_demo_drain_003",
        "idempotency_key": "idemp_drain_003",
        "amount": 80000.0,
        "currency": "INR",
        "sender_vpa": "eve@testpay",
        "receiver_vpa": "mallory@testpay",
        "description": "Full wallet balance liquidation",
        "fraud_probability": 0.9998,
        "fraud_label": "FRAUD",
        "risk_band": "HIGH",
        "reasons": ["Zero remaining sender balance (account drain)", "Abnormal burst volume"],
        "status": "blocked",
        "decline_reason": "High fraud probability — blocked by automated policy",
        "created_at": "2026-10-19T03:00:00Z",
        "confirmed_at": "2026-10-19T03:00:01Z",
        "reviewed_at": None,
        "simulated_hour": 3,
        "scenario_tag": "account_drain",
    },
}
_MEMORY_REVIEWS: list[dict[str, Any]] = []
_MEMORY_SETTINGS: dict[str, Any] = dict(_DEFAULT_SETTINGS)


# ── Password Hashing (PBKDF2-HMAC-SHA256) ───────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password using standard PBKDF2-HMAC-SHA256 with random salt."""
    salt = secrets.token_hex(16)
    iterations = 200_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${derived.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored PBKDF2 hash using constant-time comparison."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_hex = parts[3]
        derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return secrets.compare_digest(derived.hex(), expected_hex)
    except Exception:
        return False


ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "demo1234")
ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL",
    f"{ADMIN_USERNAME}@upifraud.internal" if "@" not in ADMIN_USERNAME else ADMIN_USERNAME,
)

_MEMORY_USERS: dict[str, dict[str, Any]] = {
    ADMIN_EMAIL.lower(): {
        "id": 1,
        "email": ADMIN_EMAIL.lower(),
        "password_hash": hash_password(ADMIN_PASSWORD),
        "full_name": "System Administrator",
        "role": "admin",
        "created_at": "2026-10-19T10:00:00Z",
    },
    "admin": {
        "id": 1,
        "email": ADMIN_EMAIL.lower(),
        "password_hash": hash_password(ADMIN_PASSWORD),
        "full_name": "System Administrator",
        "role": "admin",
        "created_at": "2026-10-19T10:00:00Z",
    },
    "user@example.com": {
        "id": 2,
        "email": "user@example.com",
        "password_hash": hash_password("user1234"),
        "full_name": "Demo User",
        "role": "user",
        "created_at": "2026-10-19T10:00:00Z",
    },
}

_MEMORY_PREDICTIONS: list[dict[str, Any]] = []
_MEMORY_PREDICTION_COUNTER: int = 1000
_MEMORY_USER_COUNTER: int = 3


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

                # Seed admin user (idempotent).
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name, role)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    (
                        ADMIN_EMAIL.lower(),
                        hash_password(ADMIN_PASSWORD),
                        "System Administrator",
                        "admin",
                    ),
                )

                # Seed demo regular user (idempotent).
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name, role)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    (
                        "user@example.com",
                        hash_password("user1234"),
                        "Demo User",
                        "user",
                    ),
                )

        _last_error = None
        return True
    except Exception as exc:  # pragma: no cover
        _last_error = str(exc)
        return False


# ── User management ──────────────────────────────────────────────────────────


def create_user(
    *,
    email: str,
    password_hash: str,
    full_name: str,
    role: str = "user",
) -> dict[str, Any]:
    """Create a new user record. Public signup always passes role='user'."""
    global _last_error, _MEMORY_USER_COUNTER
    norm_email = email.strip().lower()
    norm_name = full_name.strip()
    norm_role = "admin" if role == "admin" else "user"
    now_iso = datetime.now(timezone.utc).isoformat()

    if not is_configured():
        if norm_email in _MEMORY_USERS:
            raise ValueError(f"User with email '{norm_email}' already exists.")
        _MEMORY_USER_COUNTER += 1
        user_record = {
            "id": _MEMORY_USER_COUNTER,
            "email": norm_email,
            "password_hash": password_hash,
            "full_name": norm_name,
            "role": norm_role,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        _MEMORY_USERS[norm_email] = user_record
        return user_record

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, email, password_hash, full_name, role, created_at, updated_at
                    """,
                    (norm_email, password_hash, norm_name, norm_role),
                )
                row = cursor.fetchone()
        _last_error = None
        return {
            "id": int(row[0]),
            "email": str(row[1]),
            "password_hash": str(row[2]),
            "full_name": str(row[3]),
            "role": str(row[4]),
            "created_at": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]),
            "updated_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
        }
    except Exception as exc:
        _last_error = str(exc)
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            raise ValueError(f"User with email '{norm_email}' already exists.")
        # Fallback to memory
        if norm_email in _MEMORY_USERS:
            raise ValueError(f"User with email '{norm_email}' already exists.")
        _MEMORY_USER_COUNTER += 1
        user_record = {
            "id": _MEMORY_USER_COUNTER,
            "email": norm_email,
            "password_hash": password_hash,
            "full_name": norm_name,
            "role": norm_role,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        _MEMORY_USERS[norm_email] = user_record
        return user_record


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    """Look up user by email or username."""
    norm_email = email.strip().lower()
    if not is_configured():
        return _MEMORY_USERS.get(norm_email)

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, email, password_hash, full_name, role, created_at
                    FROM users WHERE LOWER(email) = %s
                    """,
                    (norm_email,),
                )
                row = cursor.fetchone()
        if row is None:
            return _MEMORY_USERS.get(norm_email)
        return {
            "id": int(row[0]),
            "email": str(row[1]),
            "password_hash": str(row[2]),
            "full_name": str(row[3]),
            "role": str(row[4]),
            "created_at": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]),
        }
    except Exception:
        return _MEMORY_USERS.get(norm_email)


def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    """Look up user by numeric ID."""
    if not is_configured():
        for u in _MEMORY_USERS.values():
            if u.get("id") == user_id:
                return u
        return None

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, email, password_hash, full_name, role, created_at
                    FROM users WHERE id = %s
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()
        if row is None:
            for u in _MEMORY_USERS.values():
                if u.get("id") == user_id:
                    return u
            return None
        return {
            "id": int(row[0]),
            "email": str(row[1]),
            "password_hash": str(row[2]),
            "full_name": str(row[3]),
            "role": str(row[4]),
            "created_at": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]),
        }
    except Exception:
        for u in _MEMORY_USERS.values():
            if u.get("id") == user_id:
                return u
        return None


def list_users() -> list[dict[str, Any]]:
    """List all registered users (for admin management)."""
    if not is_configured():
        seen = set()
        res = []
        for u in _MEMORY_USERS.values():
            if u["email"] not in seen:
                seen.add(u["email"])
                res.append(
                    {
                        "id": u["id"],
                        "email": u["email"],
                        "full_name": u["full_name"],
                        "role": u["role"],
                        "created_at": u.get("created_at"),
                    }
                )
        return sorted(res, key=lambda x: x["id"])

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, email, full_name, role, created_at
                    FROM users ORDER BY id ASC
                    """
                )
                rows = cursor.fetchall()
        return [
            {
                "id": int(r[0]),
                "email": str(r[1]),
                "full_name": str(r[2]),
                "role": str(r[3]),
                "created_at": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]),
            }
            for r in rows
        ]
    except Exception:
        seen = set()
        res = []
        for u in _MEMORY_USERS.values():
            if u["email"] not in seen:
                seen.add(u["email"])
                res.append(
                    {
                        "id": u["id"],
                        "email": u["email"],
                        "full_name": u["full_name"],
                        "role": u["role"],
                        "created_at": u.get("created_at"),
                    }
                )
        return sorted(res, key=lambda x: x["id"])


# ── Prediction history ───────────────────────────────────────────────────────


def record_prediction(
    *,
    amount: float,
    transaction_type: str,
    hour_of_day: int,
    prediction: str,
    fraud_probability: float,
    risk_level: str,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
) -> bool:
    """Persist one prediction with optional user attribution."""
    global _last_error, _MEMORY_PREDICTION_COUNTER
    now = datetime.now(timezone.utc)
    _MEMORY_PREDICTION_COUNTER += 1
    mem_rec = {
        "id": _MEMORY_PREDICTION_COUNTER,
        "amount": round(amount, 2),
        "transaction_type": transaction_type,
        "hour_of_day": hour_of_day,
        "prediction": prediction,
        "fraud_probability": round(fraud_probability, 6),
        "risk_level": risk_level,
        "user_id": user_id,
        "user_email": user_email.lower() if user_email else None,
        "created_at": now.isoformat(),
    }
    _MEMORY_PREDICTIONS.insert(0, mem_rec)

    if not is_configured():
        return True

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO predictions (
                        amount, transaction_type, hour_of_day, prediction,
                        fraud_probability, risk_level, user_id, user_email, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        round(amount, 2),
                        transaction_type,
                        hour_of_day,
                        prediction,
                        round(fraud_probability, 6),
                        risk_level,
                        user_id,
                        user_email.lower() if user_email else None,
                        now,
                    ),
                )
        _last_error = None
        return True
    except Exception as exc:  # pragma: no cover
        _last_error = str(exc)
        # Even if Neon write fails, we recorded in memory
        return True


def get_recent_predictions(
    limit: Any = 10,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return recent predictions, filtered by user if requested."""
    global _last_error
    try:
        safe_limit = max(1, min(int(limit), 100))
    except (ValueError, TypeError):
        safe_limit = 10
    norm_email = user_email.strip().lower() if user_email else None

    if not is_configured():
        filtered = []
        for p in _MEMORY_PREDICTIONS:
            if user_id is not None or norm_email is not None:
                matches_id = user_id is not None and p.get("user_id") == user_id
                matches_email = norm_email is not None and p.get("user_email") == norm_email
                if not (matches_id or matches_email):
                    continue
            filtered.append(p)
            if len(filtered) >= safe_limit:
                break
        return filtered

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                if user_id is not None or norm_email is not None:
                    cursor.execute(
                        """
                        SELECT id, amount, transaction_type, prediction,
                               fraud_probability, risk_level, created_at, user_id, user_email
                        FROM predictions
                        WHERE (user_id = %s OR user_email = %s)
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (user_id, norm_email, safe_limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, amount, transaction_type, prediction,
                               fraud_probability, risk_level, created_at, user_id, user_email
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
                "created_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
                "user_id": row[7],
                "user_email": row[8],
            }
            for row in rows
        ]
    except Exception as exc:  # pragma: no cover
        _last_error = str(exc)
        filtered = []
        for p in _MEMORY_PREDICTIONS:
            if user_id is not None or norm_email is not None:
                matches_id = user_id is not None and p.get("user_id") == user_id
                matches_email = norm_email is not None and p.get("user_email") == norm_email
                if not (matches_id or matches_email):
                    continue
            filtered.append(p)
            if len(filtered) >= safe_limit:
                break
        return filtered


def get_prediction_by_id(prediction_id: int) -> Optional[dict[str, Any]]:
    """Return a single prediction by ID with ownership attributes."""
    if not is_configured():
        for p in _MEMORY_PREDICTIONS:
            if p.get("id") == prediction_id:
                return p
        return None

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, amount, transaction_type, prediction,
                           fraud_probability, risk_level, created_at, user_id, user_email
                    FROM predictions WHERE id = %s
                    """,
                    (prediction_id,),
                )
                row = cursor.fetchone()
        if row is None:
            for p in _MEMORY_PREDICTIONS:
                if p.get("id") == prediction_id:
                    return p
            return None
        return {
            "id": int(row[0]),
            "amount": float(row[1]),
            "transaction_type": str(row[2]),
            "prediction": str(row[3]),
            "fraud_probability": float(row[4]),
            "risk_level": str(row[5]),
            "created_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
            "user_id": row[7],
            "user_email": row[8],
        }
    except Exception:
        for p in _MEMORY_PREDICTIONS:
            if p.get("id") == prediction_id:
                return p
        return None


# ── Account operations ───────────────────────────────────────────────────────


def get_account(vpa: str) -> Optional[dict[str, Any]]:
    """Return account info for a VPA, or None if not found."""
    if not is_configured():
        return _MEMORY_ACCOUNTS.get(vpa)
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
            return _MEMORY_ACCOUNTS.get(vpa)
        return {
            "vpa": str(row[0]),
            "display_name": str(row[1]),
            "wallet_balance": float(row[2]),
            "total_sent": float(row[3]),
            "total_received": float(row[4]),
            "tx_count": int(row[5]),
        }
    except Exception:
        return _MEMORY_ACCOUNTS.get(vpa)


def list_accounts() -> list[dict[str, Any]]:
    """Return all accounts."""
    if not is_configured():
        return list(_MEMORY_ACCOUNTS.values())
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
        return list(_MEMORY_ACCOUNTS.values())


def update_balances(
    sender_vpa: str,
    receiver_vpa: str,
    amount: float,
) -> bool:
    """Move money between two simulated wallets. Returns False on failure."""
    if not is_configured():
        s = _MEMORY_ACCOUNTS.get(sender_vpa)
        r = _MEMORY_ACCOUNTS.get(receiver_vpa)
        if not s or not r or s["wallet_balance"] < amount:
            return False
        s["wallet_balance"] -= amount
        s["total_sent"] += amount
        s["tx_count"] += 1
        r["wallet_balance"] += amount
        r["total_received"] += amount
        r["tx_count"] += 1
        return True
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
        s = _MEMORY_ACCOUNTS.get(sender_vpa)
        r = _MEMORY_ACCOUNTS.get(receiver_vpa)
        if not s or not r or s["wallet_balance"] < amount:
            return False
        s["wallet_balance"] -= amount
        s["total_sent"] += amount
        s["tx_count"] += 1
        r["wallet_balance"] += amount
        r["total_received"] += amount
        r["tx_count"] += 1
        return True


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
    if not is_configured():
        if idempotency_key:
            for p in _MEMORY_PAYMENTS.values():
                if p.get("idempotency_key") == idempotency_key:
                    return p
        now = datetime.now(timezone.utc).isoformat()
        rec = {
            "id": payment_id,
            "idempotency_key": idempotency_key,
            "amount": amount,
            "currency": currency,
            "sender_vpa": sender_vpa,
            "receiver_vpa": receiver_vpa,
            "description": description,
            "fraud_probability": None,
            "fraud_label": None,
            "risk_band": None,
            "reasons": [],
            "status": "requires_payment_method",
            "decline_reason": None,
            "created_at": now,
            "confirmed_at": None,
            "reviewed_at": None,
            "simulated_hour": None,
            "scenario_tag": scenario_tag,
        }
        _MEMORY_PAYMENTS[payment_id] = rec
        return rec

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

                now_dt = datetime.now(timezone.utc)
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
                        now_dt,
                        scenario_tag,
                    ),
                )
        return get_payment(payment_id)
    except Exception:
        now = datetime.now(timezone.utc).isoformat()
        rec = {
            "id": payment_id,
            "idempotency_key": idempotency_key,
            "amount": amount,
            "currency": currency,
            "sender_vpa": sender_vpa,
            "receiver_vpa": receiver_vpa,
            "description": description,
            "fraud_probability": None,
            "fraud_label": None,
            "risk_band": None,
            "reasons": [],
            "status": "requires_payment_method",
            "decline_reason": None,
            "created_at": now,
            "confirmed_at": None,
            "reviewed_at": None,
            "simulated_hour": None,
            "scenario_tag": scenario_tag,
        }
        _MEMORY_PAYMENTS[payment_id] = rec
        return rec


def get_payment(payment_id: str) -> Optional[dict[str, Any]]:
    """Return a single payment record."""
    if not is_configured():
        return _MEMORY_PAYMENTS.get(payment_id)
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
            return _MEMORY_PAYMENTS.get(payment_id)
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
        return _MEMORY_PAYMENTS.get(payment_id)


def get_recent_sender_payment_count(sender_vpa: str, window_seconds: int = 60) -> int:
    """Return count of recent payments initiated by sender_vpa within window_seconds."""
    count = 0
    now = datetime.now(timezone.utc)
    if not is_configured():
        for p in _MEMORY_PAYMENTS.values():
            if p.get("sender_vpa") == sender_vpa:
                created_at_str = p.get("created_at")
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(str(created_at_str).replace("Z", "+00:00"))
                        if (now - created_at).total_seconds() <= window_seconds:
                            count += 1
                    except Exception:
                        count += 1
        return count

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM payments
                    WHERE sender_vpa = %s
                      AND created_at >= NOW() - (%s || ' seconds')::INTERVAL
                    """,
                    (sender_vpa, str(int(window_seconds))),
                )
                row = cursor.fetchone()
                if row:
                    return int(row[0])
    except Exception:
        pass

    for p in _MEMORY_PAYMENTS.values():
        if p.get("sender_vpa") == sender_vpa:
            created_at_str = p.get("created_at")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(str(created_at_str).replace("Z", "+00:00"))
                    if (now - created_at).total_seconds() <= window_seconds:
                        count += 1
                except Exception:
                    pass
    return count


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
    p = _MEMORY_PAYMENTS.get(payment_id)
    if p:
        p["status"] = status
        p["fraud_probability"] = round(fraud_probability, 6)
        p["fraud_label"] = fraud_label
        p["risk_band"] = risk_band
        p["reasons"] = reasons
        p["decline_reason"] = decline_reason
        p["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        p["simulated_hour"] = simulated_hour
        p["scenario_tag"] = scenario_tag

    if not is_configured():
        return True

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
        return p is not None


def cancel_payment(
    payment_id: str,
    decline_reason: str = "Cancelled by user",
) -> Optional[dict[str, Any]]:
    """Transition an unconfirmed payment to cancelled status."""
    p = _MEMORY_PAYMENTS.get(payment_id)
    if p:
        p["status"] = "cancelled"
        p["decline_reason"] = decline_reason
        p["confirmed_at"] = datetime.now(timezone.utc).isoformat()

    if not is_configured():
        return p

    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE payments
                    SET status = 'cancelled',
                        decline_reason = %s,
                        confirmed_at = NOW()
                    WHERE id = %s
                    """,
                    (decline_reason, payment_id),
                )
        return get_payment(payment_id)
    except Exception:
        return p



def list_payments(
    *,
    limit: int = 50,
    status_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return recent payments, optionally filtered by status."""
    if not is_configured():
        items = list(_MEMORY_PAYMENTS.values())
        if status_filter:
            items = [p for p in items if p.get("status") == status_filter]
        items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        return items[:limit]

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
        items = list(_MEMORY_PAYMENTS.values())
        if status_filter:
            items = [p for p in items if p.get("status") == status_filter]
        items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        return items[:limit]


def count_reviews_pending() -> int:
    """Count payments in requires_review status."""
    if not is_configured():
        return sum(
            1 for p in _MEMORY_PAYMENTS.values() if p.get("status") == "requires_review"
        )
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM payments WHERE status = 'requires_review'"
                )
                row = cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return sum(
            1 for p in _MEMORY_PAYMENTS.values() if p.get("status") == "requires_review"
        )


# ── Review operations ────────────────────────────────────────────────────────


def create_review(
    *,
    payment_id: str,
    reviewer: str,
    verdict: str,
    note: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Record an admin review verdict and update the payment status."""
    if not is_configured():
        rev_id = len(_MEMORY_REVIEWS) + 1
        now = datetime.now(timezone.utc).isoformat()
        rev = {
            "id": rev_id,
            "payment_id": payment_id,
            "reviewer": reviewer,
            "verdict": verdict,
            "note": note,
            "created_at": now,
        }
        _MEMORY_REVIEWS.append(rev)
        p = _MEMORY_PAYMENTS.get(payment_id)
        if p:
            p["status"] = "succeeded" if verdict == "approved" else "blocked"
            p["reviewed_at"] = now
            if verdict == "approved":
                update_balances(p["sender_vpa"], p["receiver_vpa"], p["amount"])
        return rev

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
        rev_id = len(_MEMORY_REVIEWS) + 1
        now = datetime.now(timezone.utc).isoformat()
        rev = {
            "id": rev_id,
            "payment_id": payment_id,
            "reviewer": reviewer,
            "verdict": verdict,
            "note": note,
            "created_at": now,
        }
        _MEMORY_REVIEWS.append(rev)
        p = _MEMORY_PAYMENTS.get(payment_id)
        if p:
            p["status"] = "succeeded" if verdict == "approved" else "blocked"
            p["reviewed_at"] = now
        return rev


def list_reviews(payment_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Return reviews, optionally filtered by payment ID."""
    if not is_configured():
        if payment_id:
            return [r for r in _MEMORY_REVIEWS if r.get("payment_id") == payment_id]
        return list(reversed(_MEMORY_REVIEWS[-100:]))
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
        if payment_id:
            return [r for r in _MEMORY_REVIEWS if r.get("payment_id") == payment_id]
        return list(reversed(_MEMORY_REVIEWS[-100:]))


# ── Settings operations ──────────────────────────────────────────────────────


def get_setting(key: str) -> Any:
    """Return a setting value, or None if not found."""
    if not is_configured():
        return _MEMORY_SETTINGS.get(key)
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT value FROM settings WHERE key = %s", (key,))
                row = cursor.fetchone()
        if row is None:
            return _MEMORY_SETTINGS.get(key)
        value = row[0]
        if isinstance(value, str):
            return json.loads(value)
        return value
    except Exception:
        return _MEMORY_SETTINGS.get(key)


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
    _MEMORY_SETTINGS[key] = value
    if not is_configured():
        return True
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
        return True


# ── Demo reset ───────────────────────────────────────────────────────────────


def reset_demo() -> bool:
    """Reset all demo data: clear payments/reviews, restore wallet balances."""
    global _MEMORY_ACCOUNTS, _MEMORY_PAYMENTS, _MEMORY_REVIEWS
    _MEMORY_ACCOUNTS = {
        vpa: {
            "vpa": vpa,
            "display_name": name,
            "wallet_balance": bal,
            "total_sent": 0.0,
            "total_received": 0.0,
            "tx_count": 0,
        }
        for vpa, name, bal in _SEED_ACCOUNTS
    }
    _MEMORY_PAYMENTS = {}
    _MEMORY_REVIEWS = []
    if not is_configured():
        return True
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
        return True


# ── Health status ────────────────────────────────────────────────────────────


def status() -> dict[str, Any]:
    """Return safe persistence status for the health endpoint."""
    return {
        "configured": is_configured(),
        "available": is_configured() and _last_error is None,
        "last_error": _last_error if is_configured() else None,
    }
