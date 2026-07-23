"""Security primitives for Meta webhooks, tenancy, and OAuth PKCE."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
from collections.abc import Mapping, Sequence
from urllib.parse import urlparse

from modules.whatsapp_business.config import WhatsAppBusinessConfig

__all__ = [
    "OAUTH_SCOPE",
    "build_consent_token",
    "build_www_authenticate",
    "is_allowed_mcp_origin",
    "is_allowed_redirect_uri",
    "is_valid_pkce_verifier",
    "normalize_phone_number",
    "owner_key_for_email",
    "pkce_challenge",
    "verify_consent_token",
    "verify_meta_signature",
]

OAUTH_SCOPE = "whatsapp:read"
_PHONE_PATTERN = re.compile(r"^\+[1-9][0-9]{7,14}$")
_CHATGPT_CALLBACK_PREFIX = "https://chatgpt.com/connector/oauth/"
_CHATGPT_LEGACY_CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
_DEFAULT_MCP_ORIGINS = frozenset(
    {
        "https://chatgpt.com",
        "https://chat.openai.com",
    }
)
_PKCE_VERIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


def owner_key_for_email(email: str, secret: str) -> str:
    """Return a stable pseudonymous owner key or fail closed."""

    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("A verified account email is required.")
    if not secret:
        raise ValueError("WhatsApp tenant isolation is not configured.")
    digest = hmac.new(
        secret.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"wa_owner_{digest}"


def normalize_phone_number(value: str) -> str:
    """Normalize one Cloud API phone value to strict E.164 notation."""

    compact = "".join(character for character in value.strip() if character.isdigit())
    candidate = f"+{compact}"
    if not _PHONE_PATTERN.fullmatch(candidate):
        raise ValueError("Phone number must contain 8 to 15 digits in E.164 form.")
    return candidate


def verify_meta_signature(raw_body: bytes, signature: str, app_secret: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 over the exact request bytes."""

    if not app_secret or not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    supplied = signature.removeprefix("sha256=").strip().lower()
    return bool(supplied) and hmac.compare_digest(expected, supplied)


def pkce_challenge(verifier: str) -> str:
    """Return the RFC 7636 S256 challenge for a verifier."""

    if not is_valid_pkce_verifier(verifier):
        raise ValueError("PKCE verifier must use 43 to 128 unreserved characters.")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def is_valid_pkce_verifier(verifier: str) -> bool:
    """Return whether a verifier satisfies the RFC 7636 syntax."""

    return bool(_PKCE_VERIFIER_PATTERN.fullmatch(verifier))


def is_allowed_redirect_uri(
    redirect_uri: str,
    *,
    allowed_origins: Sequence[str] = (),
) -> bool:
    """Allow only ChatGPT callbacks or explicitly configured HTTPS origins."""

    parsed = urlparse(redirect_uri)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        return False
    if redirect_uri == _CHATGPT_LEGACY_CALLBACK:
        return True
    if redirect_uri.startswith(_CHATGPT_CALLBACK_PREFIX):
        suffix = redirect_uri.removeprefix(_CHATGPT_CALLBACK_PREFIX)
        return bool(suffix) and "/" not in suffix and "?" not in suffix
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return origin in set(allowed_origins)


def is_allowed_mcp_origin(
    origin: str | None,
    *,
    config: WhatsAppBusinessConfig,
) -> bool:
    """Allow absent server-to-server Origin or an exact trusted HTTPS origin."""

    if origin is None:
        return True
    parsed = urlparse(origin)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in {None, 443}:
        return False
    hostname = parsed.hostname
    if hostname is None:
        return False
    canonical = f"https://{hostname.casefold()}"
    trusted = set(_DEFAULT_MCP_ORIGINS)
    for candidate in (config.base_url, *config.allowed_mcp_origins):
        candidate_parts = urlparse(candidate)
        candidate_host = candidate_parts.hostname
        if candidate_parts.scheme == "https" and candidate_host:
            trusted.add(f"https://{candidate_host.casefold()}")
    return canonical in trusted


def build_www_authenticate(config: WhatsAppBusinessConfig) -> str:
    """Return the OAuth discovery challenge used by ChatGPT."""

    return (
        'Bearer resource_metadata="'
        f'{config.protected_resource_metadata_url}", '
        f'scope="{OAUTH_SCOPE}", '
        'error="invalid_token", '
        'error_description="Authentication required"'
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def build_consent_token(
    payload: Mapping[str, str],
    *,
    owner_key: str,
    secret: str,
    ttl_seconds: int = 600,
) -> str:
    """Sign one short-lived OAuth consent form against parameter tampering."""

    if not secret:
        raise ValueError("WhatsApp OAuth consent signing is not configured.")
    body = {
        "owner_key": owner_key,
        "payload": dict(payload),
        "expires_at": int(time.time()) + max(int(ttl_seconds), 60),
    }
    serialized = json.dumps(
        body,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"),
        serialized,
        hashlib.sha256,
    ).digest()
    return f"{_b64encode(serialized)}.{_b64encode(signature)}"


def verify_consent_token(
    token: str,
    *,
    owner_key: str,
    secret: str,
) -> dict[str, str] | None:
    """Return signed OAuth parameters when the consent token is valid."""

    if not secret:
        return None
    try:
        body_part, signature_part = token.split(".", 1)
        serialized = _b64decode(body_part)
        supplied_signature = _b64decode(signature_part)
        payload = json.loads(serialized)
    except (
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ):
        return None
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        serialized,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected_signature, supplied_signature):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("owner_key") != owner_key:
        return None
    try:
        expires_at = int(payload.get("expires_at") or 0)
    except (TypeError, ValueError):
        return None
    if expires_at < int(time.time()):
        return None
    raw_parameters = payload.get("payload")
    if not isinstance(raw_parameters, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in raw_parameters.items()
    ):
        return None
    return dict(raw_parameters)
