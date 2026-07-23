"""Configuration for the hosted WhatsApp Business connector."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

__all__ = ["WhatsAppBusinessConfig", "get_whatsapp_business_config"]

_DEFAULT_BASE_URL = "https://mparanza.com"
_DEFAULT_RETENTION_DAYS = 90
_DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
_MIN_CONNECTOR_SECRET_BYTES = 32
_TRUTHY_VALUES = {"1", "on", "true", "yes"}


def _clean_https_url(value: str, *, field: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(f"{field} must be an absolute HTTPS URL.")
    return candidate


def _clean_https_origin(value: str, *, field: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlparse(candidate)
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
        raise ValueError(f"{field} must contain absolute HTTPS origins.")
    return candidate


def _positive_int(value: str | None, *, default: int, field: str) -> int:
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be positive.")
    return parsed


def _bounded_int(
    value: str | None,
    *,
    default: int,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    parsed = _positive_int(value, default=default, field=field)
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}.")
    return parsed


def _optional_connector_secret(value: str, *, field: str) -> str:
    """Allow an absent connector, but reject weak configured secrets."""

    cleaned = value.strip()
    if cleaned and len(cleaned.encode("utf-8")) < _MIN_CONNECTOR_SECRET_BYTES:
        raise ValueError(
            f"{field} must contain at least {_MIN_CONNECTOR_SECRET_BYTES} bytes."
        )
    return cleaned


def _optional_challenge_token(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) > 2_048 or any(ord(character) < 33 for character in cleaned):
        raise ValueError("OPENAI_APPS_CHALLENGE_TOKEN must be a single bounded token.")
    return cleaned


@dataclass(frozen=True, slots=True)
class WhatsAppBusinessConfig:
    """Environment-derived connector settings."""

    base_url: str
    resource_url: str
    webhook_verify_token: str
    meta_app_secret: str
    tenant_secret: str
    oauth_secret: str
    retention_days: int
    access_token_ttl_seconds: int
    sqlite_path: str
    allowed_redirect_origins: tuple[str, ...]
    allowed_mcp_origins: tuple[str, ...]
    setup_allowed_emails: tuple[str, ...]
    browser_auth_enabled: bool
    openai_apps_challenge_token: str

    @property
    def protected_resource_metadata_url(self) -> str:
        return f"{self.base_url}/.well-known/oauth-protected-resource"

    @property
    def authorization_server_metadata_url(self) -> str:
        return f"{self.base_url}/.well-known/oauth-authorization-server"

    @property
    def authorization_endpoint(self) -> str:
        return f"{self.base_url}/whatsapp/oauth/authorize"

    @property
    def token_endpoint(self) -> str:
        return f"{self.base_url}/whatsapp/oauth/token"

    @property
    def registration_endpoint(self) -> str:
        return f"{self.base_url}/whatsapp/oauth/register"

    @property
    def issuer_url(self) -> str:
        return self.base_url


@lru_cache(maxsize=1)
def get_whatsapp_business_config() -> WhatsAppBusinessConfig:
    """Return validated connector settings.

    Secrets may remain empty while the application boots. Security-sensitive
    routes fail closed when a required secret is absent.
    """

    base_url = _clean_https_url(
        os.getenv("WHATSAPP_MCP_BASE_URL", _DEFAULT_BASE_URL),
        field="WHATSAPP_MCP_BASE_URL",
    )
    resource_url = f"{base_url}/whatsapp/mcp"
    raw_origins = os.getenv("WHATSAPP_OAUTH_ALLOWED_REDIRECT_ORIGINS", "")
    allowed_origins = tuple(
        _clean_https_url(item, field="WHATSAPP_OAUTH_ALLOWED_REDIRECT_ORIGINS")
        for item in raw_origins.split(",")
        if item.strip()
    )
    allowed_mcp_origins = tuple(
        _clean_https_origin(item, field="WHATSAPP_MCP_ALLOWED_ORIGINS")
        for item in os.getenv("WHATSAPP_MCP_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    )
    setup_allowed_emails = tuple(
        item.strip().lower()
        for item in os.getenv("WHATSAPP_SETUP_ALLOWED_EMAILS", "").split(",")
        if item.strip()
    )
    tenant_secret = _optional_connector_secret(
        os.getenv("WHATSAPP_TENANT_SECRET", ""),
        field="WHATSAPP_TENANT_SECRET",
    )
    oauth_secret = _optional_connector_secret(
        os.getenv("WHATSAPP_OAUTH_SECRET", ""),
        field="WHATSAPP_OAUTH_SECRET",
    )
    if tenant_secret and oauth_secret and tenant_secret == oauth_secret:
        raise ValueError(
            "WHATSAPP_TENANT_SECRET and WHATSAPP_OAUTH_SECRET must be distinct."
        )
    return WhatsAppBusinessConfig(
        base_url=base_url,
        resource_url=resource_url,
        webhook_verify_token=os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip(),
        meta_app_secret=os.getenv("WHATSAPP_META_APP_SECRET", "").strip(),
        tenant_secret=tenant_secret,
        oauth_secret=oauth_secret,
        retention_days=_bounded_int(
            os.getenv("WHATSAPP_RETENTION_DAYS"),
            default=_DEFAULT_RETENTION_DAYS,
            field="WHATSAPP_RETENTION_DAYS",
            minimum=_DEFAULT_RETENTION_DAYS,
            maximum=_DEFAULT_RETENTION_DAYS,
        ),
        access_token_ttl_seconds=_bounded_int(
            os.getenv("WHATSAPP_OAUTH_ACCESS_TOKEN_TTL_SECONDS"),
            default=_DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
            field="WHATSAPP_OAUTH_ACCESS_TOKEN_TTL_SECONDS",
            minimum=5 * 60,
            maximum=_DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        ),
        sqlite_path=os.getenv("WHATSAPP_DB_PATH", "").strip(),
        allowed_redirect_origins=allowed_origins,
        allowed_mcp_origins=allowed_mcp_origins,
        setup_allowed_emails=setup_allowed_emails,
        browser_auth_enabled=(
            os.getenv("AUTH_ENABLED", "").strip().lower() in _TRUTHY_VALUES
        ),
        openai_apps_challenge_token=_optional_challenge_token(
            os.getenv("OPENAI_APPS_CHALLENGE_TOKEN", "")
        ),
    )
