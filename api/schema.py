"""Shared Pydantic models for the gateway API and admin endpoints.

These models define the frozen scoring contract and the Stripe-style
PaymentIntent shape.  The gateway and checkout depend on this schema;
the model can be swapped out without changing these shapes.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

GATEWAY_SUPPORTED_OPERATIONS: frozenset[str] = frozenset({"PAYMENT", "TRANSFER"})


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

    amount: float = Field(..., gt=0, le=10_000_000.0, description="Amount in INR")
    currency: str = Field(default="INR", description="Currency code (e.g. INR)")
    sender_vpa: str = Field(..., min_length=3, max_length=64, description="Sender VPA (e.g. alice@testpay)")
    receiver_vpa: str = Field(..., min_length=3, max_length=64, description="Receiver VPA (e.g. bob@testpay)")
    transaction_type: Optional[str] = Field(
        default="TRANSFER",
        description="Checkout operation type: TRANSFER (P2P) or PAYMENT (P2M)",
    )
    description: Optional[str] = Field(default=None, max_length=255, description="Payment description")
    scenario_tag: Optional[str] = Field(default=None, max_length=64, description="Preset scenario tag")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Amount must be a finite number.")
        if value <= 0:
            raise ValueError("Amount must be greater than 0.")
        if value > 10_000_000.0:
            raise ValueError("Amount exceeds maximum permissible gateway limit of ₹1,00,00,000.")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        norm = value.strip().upper()
        if norm != "INR":
            raise ValueError(f"Unsupported currency '{value}'. Only 'INR' is supported.")
        return norm

    @field_validator("sender_vpa", "receiver_vpa")
    @classmethod
    def validate_vpa(cls, value: str) -> str:
        norm = value.strip().lower()
        if "@" not in norm or len(norm) < 3 or norm.startswith("@") or norm.endswith("@"):
            raise ValueError(f"Invalid UPI VPA format: '{value}'. Expected format: user@bank.")
        return norm

    @field_validator("transaction_type")
    @classmethod
    def validate_transaction_type(cls, value: Optional[str]) -> str:
        if value is None:
            return "TRANSFER"
        norm = value.strip().upper()
        if norm not in GATEWAY_SUPPORTED_OPERATIONS:
            accepted = ", ".join(sorted(GATEWAY_SUPPORTED_OPERATIONS))
            raise ValueError(
                f"Unsupported checkout operation '{value}'. Supported gateway operations are: {accepted}"
            )
        return norm

    @model_validator(mode="after")
    def validate_distinct_accounts(self) -> CreatePaymentIntent:
        if self.sender_vpa == self.receiver_vpa:
            raise ValueError("Sender and receiver cannot be the same VPA.")
        return self


class ConfirmPaymentIntent(BaseModel):
    """Request body for POST /v1/payment_intents/{id}/confirm."""

    simulated_hour: Optional[int] = Field(
        default=None, ge=0, le=23, description="Override the real clock (0–23)"
    )

    @field_validator("simulated_hour")
    @classmethod
    def validate_hour(cls, value: Optional[int]) -> Optional[int]:
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("simulated_hour must be an integer between 0 and 23.")
            if value < 0 or value > 23:
                raise ValueError("simulated_hour must be between 0 and 23.")
        return value


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

    @field_validator("block_threshold", "review_threshold")
    @classmethod
    def validate_finite_threshold(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Threshold must be a finite number.")
        if value < 0.0 or value > 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0.")
        return value

    @model_validator(mode="after")
    def validate_threshold_order(self) -> ThresholdSettings:
        if self.block_threshold < self.review_threshold:
            raise ValueError("block_threshold must be greater than or equal to review_threshold.")
        return self


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
