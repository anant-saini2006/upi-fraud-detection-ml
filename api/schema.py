"""Shared Pydantic models for the gateway API and admin endpoints.

These models define the frozen scoring contract and the Stripe-style
PaymentIntent shape.  The gateway and checkout depend on this schema;
the model can be swapped out without changing these shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Frozen scoring contract v1 ───────────────────────────────────────────────
# The gateway and checkout depend on this shape.  The model can be retrained
# and swapped in without changing any of these fields.


class ScoringResponse(BaseModel):
    """Frozen scoring contract — gateway and checkout depend on this shape."""

    probability: float = Field(..., ge=0.0, le=1.0, description="Class-1 posterior")
    label: Literal["FRAUD", "LEGITIMATE"] = Field(..., description="Binary label")
    risk_band: Literal["LOW", "MEDIUM", "HIGH"] = Field(..., description="Risk tier")
    reasons: list[str] = Field(
        ..., description="Top human-readable feature explanations"
    )


# ── PaymentIntent models ─────────────────────────────────────────────────────


class CreatePaymentIntent(BaseModel):
    """Request body for POST /v1/payment_intents."""

    amount: float = Field(..., gt=0, description="Amount in INR")
    currency: str = Field(default="INR", description="Currency code")
    sender_vpa: str = Field(..., description="Sender VPA (e.g. alice@testpay)")
    receiver_vpa: str = Field(..., description="Receiver VPA (e.g. bob@testpay)")
    description: Optional[str] = Field(default=None, description="Payment description")
    scenario_tag: Optional[str] = Field(default=None, description="Preset scenario tag (e.g. normal, review, night_drain, rapid_repeat)")


class ConfirmPaymentIntent(BaseModel):
    """Request body for POST /v1/payment_intents/{id}/confirm."""

    simulated_hour: Optional[int] = Field(
        default=None, ge=0, le=23, description="Override the real clock (0–23)"
    )


class PaymentIntentResponse(BaseModel):
    """Response shape for all PaymentIntent endpoints."""

    id: str
    amount: float
    currency: str
    sender_vpa: str
    receiver_vpa: str
    description: Optional[str] = None
    status: str
    scoring: Optional[ScoringResponse] = None
    decline_reason: Optional[str] = None
    created_at: str
    confirmed_at: Optional[str] = None
    simulated_hour: Optional[int] = None
    scenario_tag: Optional[str] = None


# ── Admin models ─────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


class ReviewRequest(BaseModel):
    verdict: Literal["approved", "confirmed_fraud"]
    note: Optional[str] = None


class ReviewResponse(BaseModel):
    id: int
    payment_id: str
    reviewer: str
    verdict: str
    note: Optional[str]
    created_at: str


class ThresholdSettings(BaseModel):
    """Admin-adjustable thresholds for the scoring decision policy."""

    block_threshold: float = Field(
        ..., ge=0.0, le=1.0, description="Probability >= this → blocked"
    )
    review_threshold: float = Field(
        ..., ge=0.0, le=1.0, description="Probability >= this → requires_review"
    )


class AccountInfo(BaseModel):
    vpa: str
    display_name: str
    wallet_balance: float
    total_sent: float
    total_received: float
    tx_count: int


class SimulateRequest(BaseModel):
    """Request body for the simulate-50-payments endpoint."""

    count: int = Field(default=50, ge=1, le=200, description="Number of payments")
