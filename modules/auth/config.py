"""Configuration helpers for Google Identity verification."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import unquote, urlparse, urlsplit

__all__ = ["AuthConfig", "get_auth_config"]

_TRUTHY_VALUES = {"1", "true", "yes", "on"}
_ENV_AUTH_ENABLED = "AUTH_ENABLED"
_ENV_GOOGLE_CLIENT_ID = "GOOGLE_CLIENT_ID"
_ENV_GOOGLE_AUTHORIZED_ORIGINS = "GOOGLE_AUTHORIZED_ORIGINS"
_ENV_GOOGLE_ALLOWED_DOMAINS = "GOOGLE_ALLOWED_DOMAINS"
_ENV_GOOGLE_ALLOWED_EMAILS = "GOOGLE_ALLOWED_EMAILS"
# Environment-variable name, never credential material.
_ENV_SESSION_SECRET = "AUTH_SESSION_SECRET"  # nosec B105
_ENV_SESSION_TTL = "AUTH_SESSION_TTL_SECONDS"
_ENV_COOKIE_SECURE = "AUTH_COOKIE_SECURE"
_ENV_MAGIC_LINK_TTL = "AUTH_MAGIC_LINK_TTL_SECONDS"
_ENV_MAGIC_LINK_REDIRECT = "AUTH_MAGIC_LINK_DEFAULT_REDIRECT"
_ENV_PUBLIC_BASE_URL = "AUTH_PUBLIC_BASE_URL"
_ENV_TRUSTED_HOSTS = "AUTH_TRUSTED_HOSTS"

_DEFAULT_SESSION_TTL_SECONDS = 12 * 3600
_DEFAULT_COOKIE_NAME = "mp_auth"
_DEFAULT_MAGIC_LINK_TTL_SECONDS = 15 * 60
_DEFAULT_MAGIC_LINK_REDIRECT = "/"
_DEFAULT_PUBLIC_BASE_URL = "https://mparanza.com"
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testserver"}


@dataclass(frozen=True)
class AuthConfig:
    """Authentication settings derived from environment variables."""

    google_client_id: str
    google_authorized_origins: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    allowed_emails: tuple[str, ...]
    authentication_enabled: bool
    session_secret: str
    session_cookie_name: str
    session_ttl_seconds: int
    cookie_secure: bool
    magic_link_ttl_seconds: int
    magic_link_default_redirect: str
    public_base_url: str = _DEFAULT_PUBLIC_BASE_URL
    trusted_hosts: tuple[str, ...] = ("mparanza.com", "testserver")


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in _TRUTHY_VALUES


def _parse_csv(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return ()
    return tuple(
        entry.strip().lower() for entry in raw_value.split(",") if entry.strip()
    )


def _parse_session_ttl(raw_value: str | None) -> int:
    if not raw_value:
        return _DEFAULT_SESSION_TTL_SECONDS
    try:
        ttl = int(raw_value)
    except ValueError as exc:
        raise ValueError("AUTH_SESSION_TTL_SECONDS must be an integer.") from exc
    if ttl <= 0:
        raise ValueError("AUTH_SESSION_TTL_SECONDS must be positive.")
    return ttl


def _parse_magic_ttl(raw_value: str | None) -> int:
    if not raw_value:
        return _DEFAULT_MAGIC_LINK_TTL_SECONDS
    try:
        ttl = int(raw_value)
    except ValueError as exc:
        raise ValueError("AUTH_MAGIC_LINK_TTL_SECONDS must be an integer.") from exc
    if ttl <= 0:
        raise ValueError("AUTH_MAGIC_LINK_TTL_SECONDS must be positive.")
    return ttl


def _parse_magic_redirect(raw_value: str | None) -> str:
    if not raw_value:
        return _DEFAULT_MAGIC_LINK_REDIRECT
    candidate = raw_value.strip()
    if not candidate:
        return _DEFAULT_MAGIC_LINK_REDIRECT
    decoded = unquote(candidate)
    parsed = urlsplit(decoded)
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or decoded.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or "\\" in decoded
        or any(ord(character) < 32 for character in decoded)
    ):
        raise ValueError("AUTH_MAGIC_LINK_DEFAULT_REDIRECT must be a local path.")
    return candidate


def _parse_public_base_url(raw_value: str | None) -> str:
    candidate = (raw_value or _DEFAULT_PUBLIC_BASE_URL).strip().rstrip("/")
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
        raise ValueError("AUTH_PUBLIC_BASE_URL must be an HTTPS origin.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("AUTH_PUBLIC_BASE_URL has an invalid port.") from exc
    if port not in {None, 443}:
        raise ValueError("AUTH_PUBLIC_BASE_URL must use the standard HTTPS port.")
    return candidate


def _parse_trusted_hosts(raw_value: str | None) -> tuple[str, ...]:
    hosts = _parse_csv(raw_value)
    if any(
        "*" in host
        or "/" in host
        or "\\" in host
        or any(ord(character) < 33 for character in host)
        for host in hosts
    ):
        raise ValueError("AUTH_TRUSTED_HOSTS must contain explicit host names.")
    return hosts


@lru_cache(maxsize=1)
def get_auth_config() -> AuthConfig:
    """Read Google Identity settings from the environment."""

    authentication_enabled = _parse_bool(os.environ.get(_ENV_AUTH_ENABLED))
    google_client_id = (os.environ.get(_ENV_GOOGLE_CLIENT_ID) or "").strip()
    google_authorized_origins = _parse_csv(
        os.environ.get(_ENV_GOOGLE_AUTHORIZED_ORIGINS)
    )
    allowed_domains = _parse_csv(os.environ.get(_ENV_GOOGLE_ALLOWED_DOMAINS))
    allowed_emails = _parse_csv(os.environ.get(_ENV_GOOGLE_ALLOWED_EMAILS))
    session_secret = (os.environ.get(_ENV_SESSION_SECRET) or "").strip()
    session_ttl_seconds = _parse_session_ttl(os.environ.get(_ENV_SESSION_TTL))
    cookie_secure = _parse_bool(os.environ.get(_ENV_COOKIE_SECURE), default=True)
    magic_link_ttl_seconds = _parse_magic_ttl(os.environ.get(_ENV_MAGIC_LINK_TTL))
    magic_link_default_redirect = _parse_magic_redirect(
        os.environ.get(_ENV_MAGIC_LINK_REDIRECT)
    )
    public_base_url = _parse_public_base_url(os.environ.get(_ENV_PUBLIC_BASE_URL))
    public_hostname = (urlparse(public_base_url).hostname or "").casefold()
    trusted_hosts = tuple(
        dict.fromkeys(
            (
                public_hostname,
                *_parse_trusted_hosts(os.environ.get(_ENV_TRUSTED_HOSTS)),
                "testserver",
                "localhost",
                "127.0.0.1",
                "[::1]",
            )
        )
    )

    if authentication_enabled:
        if not google_client_id:
            raise ValueError(
                "GOOGLE_CLIENT_ID is required when authentication is enabled."
            )
        if len(session_secret.encode("utf-8")) < 32:
            raise ValueError(
                "AUTH_SESSION_SECRET must contain at least 32 bytes when "
                "authentication is enabled."
            )
        if not cookie_secure and public_hostname not in _LOCAL_HOSTS:
            raise ValueError(
                "AUTH_COOKIE_SECURE must remain enabled for a production HTTPS origin."
            )

    return AuthConfig(
        google_client_id=google_client_id,
        google_authorized_origins=google_authorized_origins,
        allowed_domains=allowed_domains,
        allowed_emails=allowed_emails,
        authentication_enabled=authentication_enabled,
        session_secret=session_secret,
        session_cookie_name=_DEFAULT_COOKIE_NAME,
        session_ttl_seconds=session_ttl_seconds,
        cookie_secure=cookie_secure,
        magic_link_ttl_seconds=magic_link_ttl_seconds,
        magic_link_default_redirect=magic_link_default_redirect,
        public_base_url=public_base_url,
        trusted_hosts=trusted_hosts,
    )
