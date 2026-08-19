"""Password hashing and JWT issuance (§58)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
TokenType = Literal["access", "refresh", "verify_email", "reset_password"]


# --------------------------------------------------------------- passwords --

def hash_password(raw: str) -> str:
    # bcrypt silently truncates at 72 bytes; pre-hash so long passwords keep
    # their full entropy instead of collapsing to the same 72-byte prefix.
    return _pwd.hash(_prehash(raw))


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _pwd.verify(_prehash(raw), hashed)
    except ValueError:
        return False


def _prehash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ tokens --

def create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = _default_ttl(token_type)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Raises jwt.PyJWTError on anything invalid, expired, or of the wrong type."""
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    if expected_type and payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError(
            f"expected {expected_type} token, got {payload.get('typ')!r}"
        )
    return payload


def _default_ttl(token_type: TokenType) -> timedelta:
    return {
        "access": timedelta(minutes=settings.access_token_ttl_minutes),
        "refresh": timedelta(days=settings.refresh_token_ttl_days),
        "verify_email": timedelta(hours=24),
        "reset_password": timedelta(hours=1),
    }[token_type]


# ------------------------------------------------------------ misc helpers --

def new_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def constant_time_equals(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)
