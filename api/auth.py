"""Authentication and authorization module for UPI Fraud Detection.

Provides user registration (signup), login, session token validation,
and role-based access control (RBAC) for 'user' and 'admin' roles.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT), str(_ROOT / "api")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from api.database import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    create_user,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    list_users,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

AUTH_SECRET = os.getenv(
    "AUTH_SECRET",
    os.getenv("ADMIN_SESSION_SECRET", "upi-fraud-detection-admin-secret-2026"),
)
_TOKEN_TTL = 86400 * 7  # 7 days

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


# ── Schemas ──────────────────────────────────────────────────────────────────


class UserSignupRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100, description="Full name")
    email: str = Field(..., min_length=5, max_length=120, description="Email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        norm = v.strip().lower()
        if not EMAIL_REGEX.match(norm):
            raise ValueError("Please provide a valid email address (e.g. user@example.com).")
        return norm

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        norm = v.strip()
        if len(norm) < 2:
            raise ValueError("Full name must be at least 2 characters.")
        return norm

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if v.isspace():
            raise ValueError("Password cannot consist solely of whitespace.")
        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_letter and has_digit):
            raise ValueError("Password must contain at least one letter and one number.")
        return v


class UserLoginRequest(BaseModel):
    email: str = Field(..., description="Email address or username")
    password: str = Field(..., description="Account password")


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    created_at: Optional[str] = None


class AuthResponse(BaseModel):
    status: str = "success"
    user: UserResponse
    token: str


# ── Stateless Token Helpers ──────────────────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    padding = (4 - (len(s) % 4)) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def create_access_token(user: dict[str, Any]) -> str:
    """Generate an HMAC-SHA256 signed stateless session token."""
    now = int(time.time())
    payload = {
        "sub": user.get("id"),
        "email": user.get("email"),
        "name": user.get("full_name") or user.get("email"),
        "role": user.get("role", "user"),
        "iat": now,
        "exp": now + _TOKEN_TTL,
        "nonce": secrets.token_hex(8),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    sig = hmac.new(
        AUTH_SECRET.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature and return token payload or raise HTTPException."""
    if not token or "." not in token:
        raise HTTPException(401, "Invalid session token format")

    parts = token.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(401, "Malformed session token")

    payload_b64, sig_b64 = parts
    expected_sig = hmac.new(
        AUTH_SECRET.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    expected_sig_b64 = _b64url_encode(expected_sig)

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        # Also check against ADMIN_SESSION_SECRET if different
        alt_secret = os.getenv("ADMIN_SESSION_SECRET")
        if alt_secret and alt_secret != AUTH_SECRET:
            alt_sig = hmac.new(
                alt_secret.encode("utf-8"),
                payload_b64.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(sig_b64, _b64url_encode(alt_sig)):
                raise HTTPException(401, "Invalid session token signature")
        else:
            raise HTTPException(401, "Invalid session token signature")

    try:
        raw_payload = _b64url_decode(payload_b64).decode("utf-8")
        payload = json.loads(raw_payload)
    except Exception:
        raise HTTPException(401, "Could not decode session token")

    exp = int(payload.get("exp", 0))
    if time.time() > exp:
        raise HTTPException(401, "Session expired — please log in again")

    return payload


# ── Dependency Functions ─────────────────────────────────────────────────────


def get_token_from_request(
    request: Request = None,
    authorization: Any = Header(None),
    auth_token_cookie: Any = Cookie(None, alias="auth_token"),
    session_token_cookie: Any = Cookie(None, alias="session_token"),
) -> Optional[str]:
    """Extract token from Authorization header or cookie."""
    if authorization and isinstance(authorization, str):
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return authorization.strip()
    if auth_token_cookie and isinstance(auth_token_cookie, str):
        return auth_token_cookie.strip()
    if session_token_cookie and isinstance(session_token_cookie, str):
        return session_token_cookie.strip()
    # Check headers directly if proxy stripped Header param
    if request and hasattr(request, "headers"):
        auth_hdr = request.headers.get("authorization")
        if auth_hdr and isinstance(auth_hdr, str):
            parts = auth_hdr.split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1].strip()
    return None


def get_current_user(
    request: Request = None,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Require valid authenticated user from token or cookie."""
    token = get_token_from_request(request, authorization)
    if not token:
        raise HTTPException(401, "Authentication required. Please log in.")

    payload = decode_access_token(token)
    email = payload.get("email") or payload.get("sub")
    if not email:
        raise HTTPException(401, "Invalid token claims")

    # If user exists in DB or memory, return latest record, else use token payload
    user = get_user_by_email(str(email))
    if user:
        return user

    # Fallback to token payload representation
    return {
        "id": payload.get("sub", 0),
        "email": payload.get("email", str(email)),
        "full_name": payload.get("name", "User"),
        "role": payload.get("role", "user"),
        "created_at": None,
    }


def get_optional_user(
    request: Request = None,
    authorization: Optional[str] = Header(None),
) -> Optional[dict[str, Any]]:
    """Return authenticated user if present and valid; None otherwise."""
    token = get_token_from_request(request, authorization)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        email = payload.get("email") or payload.get("sub")
        if not email:
            return None
        user = get_user_by_email(str(email))
        if user:
            return user
        return {
            "id": payload.get("sub", 0),
            "email": payload.get("email", str(email)),
            "full_name": payload.get("name", "User"),
            "role": payload.get("role", "user"),
            "created_at": None,
        }
    except Exception:
        return None


def require_admin(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Require administrator role."""
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Forbidden: Administrator privileges required")
    return current_user


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/signup", response_model=AuthResponse)
def signup(req: UserSignupRequest, response: Response) -> AuthResponse:
    """Register a new user account. Always assigns 'user' role."""
    norm_email = req.email.strip().lower()

    # Check if user already exists
    existing = get_user_by_email(norm_email)
    if existing:
        raise HTTPException(409, f"An account with email '{norm_email}' already exists. Please log in.")

    # Create user with secure PBKDF2 hash
    pw_hash = hash_password(req.password)
    try:
        user_record = create_user(
            email=norm_email,
            password_hash=pw_hash,
            full_name=req.full_name,
            role="user",  # Public registration strictly forces user role
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))

    token = create_access_token(user_record)

    # Set auth cookie for browser requests
    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=_TOKEN_TTL,
        path="/",
    )

    return AuthResponse(
        status="success",
        user=UserResponse(
            id=user_record["id"],
            email=user_record["email"],
            full_name=user_record["full_name"],
            role=user_record["role"],
            created_at=user_record.get("created_at"),
        ),
        token=token,
    )


@router.post("/login", response_model=AuthResponse)
def login(req: UserLoginRequest, response: Response) -> AuthResponse:
    """Authenticate with email/username and password."""
    identifier = req.email.strip().lower()
    plain_password = req.password

    # 1. Check administrator credentials from environment
    if identifier in {ADMIN_USERNAME.lower(), ADMIN_EMAIL.lower()} and plain_password == ADMIN_PASSWORD:
        admin_user = {
            "id": 1,
            "email": ADMIN_EMAIL.lower(),
            "full_name": "System Administrator",
            "role": "admin",
            "created_at": None,
        }
        token = create_access_token(admin_user)
        response.set_cookie(
            key="auth_token",
            value=token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=_TOKEN_TTL,
            path="/",
        )
        return AuthResponse(
            status="success",
            user=UserResponse(**admin_user),
            token=token,
        )

    # 2. Look up in users table / memory
    user_record = get_user_by_email(identifier)
    if not user_record:
        raise HTTPException(401, "Invalid email or password")

    # 3. Verify password hash
    stored_hash = user_record.get("password_hash", "")
    if not verify_password(plain_password, stored_hash):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token(user_record)

    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=_TOKEN_TTL,
        path="/",
    )

    return AuthResponse(
        status="success",
        user=UserResponse(
            id=user_record["id"],
            email=user_record["email"],
            full_name=user_record["full_name"],
            role=user_record["role"],
            created_at=user_record.get("created_at"),
        ),
        token=token,
    )


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    """Log out current user and clear auth cookies."""
    response.delete_cookie(key="auth_token", path="/")
    response.delete_cookie(key="session_token", path="/")
    return {"status": "logged_out", "message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
def get_me(user: dict[str, Any] = Depends(get_current_user)) -> UserResponse:
    """Return currently authenticated user information."""
    return UserResponse(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        created_at=user.get("created_at"),
    )


@router.get("/users", response_model=list[UserResponse])
def get_all_users(_: dict[str, Any] = Depends(require_admin)) -> list[UserResponse]:
    """List all registered users (Administrator only)."""
    users = list_users()
    return [
        UserResponse(
            id=u["id"],
            email=u["email"],
            full_name=u["full_name"],
            role=u["role"],
            created_at=u.get("created_at"),
        )
        for u in users
    ]
