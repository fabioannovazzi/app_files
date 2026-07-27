"""Session helpers for signed authentication cookies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

from modules.auth.config import AuthConfig
from modules.auth.google_identity import GoogleUserInfo

__all__ = [
    "AuthenticatedUser",
    "InvalidSessionError",
    "SessionExpiredError",
    "create_session_cookie",
    "decode_session_cookie",
]


@dataclass(frozen=True)
class AuthenticatedUser:
    email: str
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    picture: str | None = None


class InvalidSessionError(ValueError):
    """Raised when a session cookie cannot be decoded or verified."""


class SessionExpiredError(InvalidSessionError):
    """Raised when the session cookie has expired."""


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _clean_optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result or None


def _payload_from_user(user: GoogleUserInfo, ttl_seconds: int) -> dict[str, Any]:
    now = int(time.time())
    return {
        "sub": user.email,
        "email": user.email,
        "name": user.full_name,
        "given_name": user.given_name,
        "family_name": user.family_name,
        "picture": user.picture,
        "iat": now,
        "exp": now + ttl_seconds,
    }


def _serialize(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sign(message: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()


def create_session_cookie(user: GoogleUserInfo, config: AuthConfig) -> tuple[str, int]:
    """Return the cookie value and expiry timestamp."""

    payload = _payload_from_user(user, config.session_ttl_seconds)
    body = _serialize(payload)
    signature = _sign(body, config.session_secret)
    token = f"{_b64_encode(body)}.{_b64_encode(signature)}"
    return token, payload["exp"]


def _split_cookie(value: str) -> tuple[bytes, bytes]:
    try:
        body_b64, sig_b64 = value.split(".", 1)
    except ValueError as exc:
        raise InvalidSessionError("Malformed session cookie.") from exc
    return _b64_decode(body_b64), _b64_decode(sig_b64)


def decode_session_cookie(cookie_value: str, config: AuthConfig) -> AuthenticatedUser:
    """Validate *cookie_value* and return the stored user."""

    if not cookie_value:
        raise InvalidSessionError("Session cookie missing.")

    body, signature = _split_cookie(cookie_value)
    expected_sig = _sign(body, config.session_secret)
    if not hmac.compare_digest(signature, expected_sig):
        raise InvalidSessionError("Session signature mismatch.")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise InvalidSessionError("Session payload corrupted.") from exc

    exp = int(payload.get("exp", 0))
    if exp < int(time.time()):
        raise SessionExpiredError("Session expired.")

    email = payload.get("email") or payload.get("sub")
    if not isinstance(email, str) or not email.strip():
        raise InvalidSessionError("Session payload missing email.")

    return AuthenticatedUser(
        email=email.lower(),
        full_name=_clean_optional_str(payload.get("name")),
        given_name=_clean_optional_str(payload.get("given_name")),
        family_name=_clean_optional_str(payload.get("family_name")),
        picture=_clean_optional_str(payload.get("picture")),
    )
