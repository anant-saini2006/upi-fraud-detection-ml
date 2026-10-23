"""Razorpay Standard Checkout integration for the UPI Fraud Detection project.

Routes
------
POST /payments/orders          — Create a Razorpay order for a catalog product.
POST /payments/verify          — Verify checkout signature + fetch payment.
GET  /payments/orders/{id}     — Read persisted order / gateway status.
POST /payments/webhook         — Razorpay webhook receiver (payment.captured / payment.failed).

Tables (created via ``init_payment_tables``)
--------------------------------------------
gateway_payment_orders   — one row per Razorpay order created by this server.
gateway_webhook_events   — idempotent log of every webhook delivery processed.

The module discovers ``DATABASE_URL`` from the environment (the same variable
used by ``api.database``).  If no PostgreSQL URL is found it falls back to a
local SQLite file so that local development works without extra setup.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uuid

import razorpay
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .payment_fraud_adapter import score_payment

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("payment_integration")

# ---------------------------------------------------------------------------
# Environment & Mock Gateway Configuration
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent.parent  # repository root

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

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

MOCK_KEY_ID = "rzp_test_mock_sandbox"
MOCK_KEY_SECRET = "mock_secret_key_demo_only"
MOCK_WEBHOOK_SECRET = "mock_webhook_secret_demo"

IS_MOCK_MODE = not (bool(RAZORPAY_KEY_ID) and bool(RAZORPAY_KEY_SECRET))

if IS_MOCK_MODE:
    logger.info(
        "Razorpay credentials not set; running in Zero-KYC Mock Gateway Mode."
    )

_rz_client: razorpay.Client | None = None


def _get_razorpay_client() -> razorpay.Client:
    """Lazy-init the Razorpay SDK client."""
    global _rz_client
    if _rz_client is None:
        if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            raise HTTPException(
                status_code=503,
                detail="Razorpay credentials are not configured on the server.",
            )
        _rz_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    return _rz_client


# ---------------------------------------------------------------------------
# Demo catalog (server-side source of truth for product prices)
# ---------------------------------------------------------------------------
DEMO_CATALOG: dict[str, dict[str, Any]] = {
    "demo_item": {
        "name": "Fraud Detection Demo Report",
        "amount_inr": 199,
        "currency": "INR",
    },
    "prod_1": {
        "name": "Wireless Noise-Canceling Earbuds",
        "amount_inr": 499,
        "currency": "INR",
    },
    "prod_2": {
        "name": "Aero Ultra Smart Watch",
        "amount_inr": 2999,
        "currency": "INR",
    },
    "prod_3": {
        "name": "Ergonomic Aluminium Laptop Stand",
        "amount_inr": 1499,
        "currency": "INR",
    },
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _DATABASE_URL and _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif _DATABASE_URL and _DATABASE_URL.startswith("postgresql://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

if not _DATABASE_URL:
    _sqlite_path = _ROOT / "payments_local.db"
    _DATABASE_URL = f"sqlite:///{_sqlite_path}"
    logger.info("No DATABASE_URL found; using local SQLite at %s", _sqlite_path)

_engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
_SessionLocal = sessionmaker(bind=_engine)
_Base = declarative_base()


class GatewayPaymentOrder(_Base):  # type: ignore[misc]
    """Persisted Razorpay order with gateway and fraud status."""

    __tablename__ = "gateway_payment_orders"

    order_id = Column(String(64), primary_key=True)
    product_id = Column(String(128), nullable=False)
    amount_paise = Column(Float, nullable=False)
    currency = Column(String(8), default="INR")
    gateway_status = Column(String(32), default="created")
    fraud_status = Column(String(64), default="pending")
    razorpay_payment_id = Column(String(64), nullable=True)
    razorpay_signature = Column(String(256), nullable=True)
    raw_payment_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class GatewayWebhookEvent(_Base):  # type: ignore[misc]
    """Idempotent log of Razorpay webhook deliveries."""

    __tablename__ = "gateway_webhook_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_event_id"),)

    id = Column(String(128), primary_key=True)
    event_id = Column(String(128), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    order_id = Column(String(64), nullable=True)
    payment_id = Column(String(64), nullable=True)
    payload_json = Column(Text, nullable=True)
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_payment_tables() -> None:
    """Create tables if they do not exist (dev convenience). Safe if DB unreachable."""
    global _engine, _SessionLocal
    try:
        _Base.metadata.create_all(_engine)
        logger.info("Payment gateway tables ensured.")
    except Exception as exc:
        logger.warning(
            "Could not initialize payment tables on main DB (%s); falling back to local SQLite.",
            exc,
        )
        _engine = create_engine(f"sqlite:///{_ROOT / 'payments_local.db'}")
        _SessionLocal = sessionmaker(bind=_engine)
        _Base.metadata.create_all(_engine)
        logger.info("Local SQLite payment gateway tables initialized.")


def _db() -> Session:
    global _engine, _SessionLocal
    try:
        session = _SessionLocal()
        session.connection()
        return session
    except Exception as exc:
        if not str(_engine.url).startswith("sqlite"):
            logger.warning("Main database unreachable (%s); using local SQLite fallback.", exc)
            _engine = create_engine(f"sqlite:///{_ROOT / 'payments_local.db'}")
            _SessionLocal = sessionmaker(bind=_engine)
            _Base.metadata.create_all(_engine)
            return _SessionLocal()
        raise


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class CreateOrderRequest(BaseModel):
    product_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/orders")
def create_order(body: CreateOrderRequest) -> dict[str, Any]:
    """Create a Razorpay order for a known product ID."""
    product = DEMO_CATALOG.get(body.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Unknown product_id.")

    amount_paise = int(product["amount_inr"] * 100)

    if IS_MOCK_MODE:
        order_id = f"order_mock_{uuid.uuid4().hex[:14]}"
        key_id = MOCK_KEY_ID
    else:
        client = _get_razorpay_client()
        rz_order = client.order.create(
            {
                "amount": amount_paise,
                "currency": product["currency"],
                "receipt": f"rcpt_{body.product_id}_{int(datetime.now(timezone.utc).timestamp())}",
                "notes": {"product_id": body.product_id},
            }
        )
        order_id = rz_order["id"]
        key_id = RAZORPAY_KEY_ID

    # Persist
    session = _db()
    try:
        row = GatewayPaymentOrder(
            order_id=order_id,
            product_id=body.product_id,
            amount_paise=amount_paise,
            currency=product["currency"],
        )
        session.add(row)
        session.commit()
    finally:
        session.close()

    return {
        "order_id": order_id,
        "amount": amount_paise,
        "currency": product["currency"],
        "key_id": key_id,
        "product_name": product["name"],
        "is_mock": IS_MOCK_MODE,
    }


@router.post("/verify")
def verify_payment(body: VerifyPaymentRequest) -> dict[str, Any]:
    """Verify the Razorpay Standard Checkout signature server-side."""
    session = _db()
    try:
        row = session.query(GatewayPaymentOrder).filter_by(
            order_id=body.razorpay_order_id
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Order not found in database.")

        is_mock_order = IS_MOCK_MODE or body.razorpay_order_id.startswith("order_mock_")

        if is_mock_order:
            # Verify Mock HMAC signature
            expected = hmac.new(
                MOCK_KEY_SECRET.encode(),
                f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(expected, body.razorpay_signature) and body.razorpay_signature != "mock_signature_bypass":
                raise HTTPException(status_code=400, detail="Invalid mock payment signature.")

            payment = {
                "id": body.razorpay_payment_id,
                "entity": "payment",
                "amount": row.amount_paise,
                "currency": row.currency,
                "status": "captured",
                "order_id": body.razorpay_order_id,
                "method": "upi",
                "vpa": "student@okaxis",
                "email": "student@demo.edu",
                "contact": "+919876543210",
                "created_at": int(datetime.now(timezone.utc).timestamp()),
            }
        else:
            client = _get_razorpay_client()
            # 1. Verify signature
            try:
                client.utility.verify_payment_signature(
                    {
                        "razorpay_order_id": body.razorpay_order_id,
                        "razorpay_payment_id": body.razorpay_payment_id,
                        "razorpay_signature": body.razorpay_signature,
                    }
                )
            except razorpay.errors.SignatureVerificationError:
                raise HTTPException(status_code=400, detail="Invalid payment signature.")

            # 2. Fetch payment from Razorpay to confirm status + amount
            payment = client.payment.fetch(body.razorpay_payment_id)

            # Amount sanity check
            if int(payment.get("amount", 0)) != int(row.amount_paise):
                raise HTTPException(
                    status_code=400,
                    detail="Payment amount does not match the order amount.",
                )

        row.gateway_status = payment.get("status", "captured")
        row.razorpay_payment_id = body.razorpay_payment_id
        row.razorpay_signature = body.razorpay_signature
        row.raw_payment_json = json.dumps(payment)

        # Run fraud adapter (safe placeholder)
        fraud_result = score_payment(payment)
        row.fraud_status = fraud_result.get("status", "needs_feature_adapter")

        session.commit()

        return {
            "verified": True,
            "gateway_status": row.gateway_status,
            "fraud_status": row.fraud_status,
            "payment_id": body.razorpay_payment_id,
            "is_mock": is_mock_order,
        }
    finally:
        session.close()


@router.get("/orders/{order_id}")
def get_order(order_id: str) -> dict[str, Any]:
    """Read the saved status of a gateway order."""
    session = _db()
    try:
        row = session.query(GatewayPaymentOrder).filter_by(order_id=order_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Order not found.")
        return {
            "order_id": row.order_id,
            "product_id": row.product_id,
            "amount_paise": row.amount_paise,
            "currency": row.currency,
            "gateway_status": row.gateway_status,
            "fraud_status": row.fraud_status,
            "razorpay_payment_id": row.razorpay_payment_id,
            "created_at": str(row.created_at) if row.created_at else None,
            "updated_at": str(row.updated_at) if row.updated_at else None,
        }
    finally:
        session.close()


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None),
) -> dict[str, str]:
    """Receive and verify Razorpay webhook events.

    Razorpay signs the *raw* request body with the webhook secret (not the
    API key secret).  The handler verifies the HMAC before parsing JSON.
    """
    raw_body = await request.body()

    # 1. Signature verification
    effective_secret = RAZORPAY_WEBHOOK_SECRET or (MOCK_WEBHOOK_SECRET if IS_MOCK_MODE else "")
    if not effective_secret:
        raise HTTPException(
            status_code=503,
            detail="RAZORPAY_WEBHOOK_SECRET is not configured.",
        )
    if not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing X-Razorpay-Signature header.")

    if not (IS_MOCK_MODE and x_razorpay_signature == "mock_signature_bypass"):
        expected = hmac.new(
            effective_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, x_razorpay_signature):
            raise HTTPException(status_code=400, detail="Webhook signature mismatch.")

    # 2. Parse payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    event_id: str = payload.get("event_id", payload.get("id", ""))
    event_type: str = payload.get("event", "")
    payment_entity: dict[str, Any] = (
        payload.get("payload", {}).get("payment", {}).get("entity", {})
    )
    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id")

    # 3. Duplicate-event protection
    session = _db()
    try:
        existing = (
            session.query(GatewayWebhookEvent)
            .filter_by(event_id=event_id)
            .first()
        )
        if existing is not None:
            logger.info("Duplicate webhook event %s — skipping.", event_id)
            return {"status": "duplicate"}

        # 4. Persist event
        event_row = GatewayWebhookEvent(
            id=f"{event_id}_{int(datetime.now(timezone.utc).timestamp())}",
            event_id=event_id,
            event_type=event_type,
            order_id=order_id,
            payment_id=payment_id,
            payload_json=json.dumps(payload),
        )
        session.add(event_row)

        # 5. Update order status
        if order_id:
            order_row = (
                session.query(GatewayPaymentOrder)
                .filter_by(order_id=order_id)
                .first()
            )
            if order_row:
                if event_type == "payment.captured":
                    order_row.gateway_status = "captured"
                    fraud_result = score_payment(payment_entity)
                    order_row.fraud_status = fraud_result.get(
                        "status", "needs_feature_adapter"
                    )
                elif event_type == "payment.failed":
                    order_row.gateway_status = "failed"
                    order_row.fraud_status = "not_applicable"

                order_row.razorpay_payment_id = payment_id
                order_row.raw_payment_json = json.dumps(payment_entity)

        session.commit()
        logger.info("Webhook %s (%s) processed for order %s.", event_id, event_type, order_id)
        return {"status": "ok"}
    finally:
        session.close()
