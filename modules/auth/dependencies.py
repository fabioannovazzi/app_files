"""FastAPI dependencies for cookie-based authentication."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from fastapi import HTTPException, Request, status

from modules.auth.config import get_auth_config
from modules.auth.session import (
    AuthenticatedUser,
    InvalidSessionError,
    decode_session_cookie,
)

__all__ = [
    "get_allowed_page_keys_for_email",
    "get_permission_key_for_path",
    "get_permission_structure",
    "get_site_permissions",
    "maybe_current_user",
    "require_authenticated_user",
    "require_authenticated_user_for_site",
    "require_site_permission",
    "require_site_permission_for_request",
]

LOGGER = logging.getLogger(__name__)
_ALL_AUTHENTICATED_USERS = "*"


def _resolve_config_path(filename: str) -> Path:
    """Resolve config paths relative to the project root when possible."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent / "config" / filename
    return Path("config") / filename


def maybe_current_user(request: Request) -> AuthenticatedUser | None:
    """Return the authenticated user or ``None`` when unauthenticated."""

    config = get_auth_config()
    if not config.authentication_enabled:
        return None

    cookie_value = request.cookies.get(config.session_cookie_name)
    if not cookie_value:
        return None
    try:
        return decode_session_cookie(cookie_value, config)
    except InvalidSessionError:
        return None


def require_authenticated_user(request: Request) -> AuthenticatedUser | None:
    """FastAPI dependency enforcing authentication when enabled."""

    config = get_auth_config()
    if not config.authentication_enabled:
        return None

    cookie_value = request.cookies.get(config.session_cookie_name)
    if not cookie_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    try:
        return decode_session_cookie(cookie_value, config)
    except InvalidSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        ) from exc


def require_authenticated_user_for_site(request: Request) -> AuthenticatedUser | None:
    """Require authentication for HTML pages, redirecting to sign-in when missing."""

    config = get_auth_config()
    if not config.authentication_enabled:
        return None

    cookie_value = request.cookies.get(config.session_cookie_name)
    if cookie_value:
        try:
            return decode_session_cookie(cookie_value, config)
        except InvalidSessionError:
            pass

    lang = request.query_params.get("lang")
    target = request.url.path or "/"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    params: list[tuple[str, str]] = [("redirect", target)]
    if lang:
        params.insert(0, ("lang", lang))
    location = f"/auth/page?{urlencode(params)}"
    raise HTTPException(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        detail="Authentication required.",
        headers={"Location": location},
    )


_SITE_PERMISSIONS_FILE = _resolve_config_path("site_page_permissions.json")
_PERMISSION_STRUCTURE_FILE = _resolve_config_path("permission_structure.json")


def _site_permissions_cache_key() -> tuple[str, int, int]:
    """Return a cache key that changes whenever the permissions file changes."""

    path = _SITE_PERMISSIONS_FILE
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return (os.fspath(path), 0, 0)
    except OSError:
        return (os.fspath(path), 0, 0)
    return (os.fspath(path), int(stat_result.st_mtime_ns), int(stat_result.st_size))


def _permission_structure_cache_key() -> tuple[str, int, int]:
    """Return a cache key that changes whenever the structure file changes."""

    path = _PERMISSION_STRUCTURE_FILE
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return (os.fspath(path), 0, 0)
    except OSError:
        return (os.fspath(path), 0, 0)
    return (os.fspath(path), int(stat_result.st_mtime_ns), int(stat_result.st_size))


@lru_cache(maxsize=4)
def _get_site_permissions(cache_key: tuple[str, int, int]) -> dict[str, set[str]]:
    permissions_path, _mtime_ns, _size = cache_key
    path = Path(permissions_path)
    if not path.exists():
        LOGGER.warning("Site permissions file not found at %s; allowing all pages.", path)
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}") from exc
    permissions: dict[str, set[str]] = {}
    now = datetime.now(timezone.utc)
    for page, entries in raw.items():
        if not isinstance(page, str):
            continue
        page_key = page.strip().lower()
        if not page_key:
            continue
        if not isinstance(entries, list):
            continue
        normalized: set[str] = set()
        for entry in entries:
            email = _normalize_permission_entry(entry, now=now)
            if email:
                normalized.add(email)
        permissions[page_key] = normalized
    return permissions


def _normalize_permission_entry(entry: object, *, now: datetime) -> str | None:
    if isinstance(entry, str):
        email = entry.strip().lower()
        return email or None
    if isinstance(entry, dict):
        email_value = entry.get("email")
        if not isinstance(email_value, str):
            return None
        email = email_value.strip().lower()
        if not email:
            return None
        expires_value = entry.get("expires_at") or entry.get("expires")
        if expires_value is None:
            return email
        if not isinstance(expires_value, str):
            LOGGER.warning("Invalid expires_at value for %s; ignoring expiry.", email)
            return email
        expires_at = _parse_expiry_timestamp(expires_value.strip())
        if expires_at is None:
            LOGGER.warning("Invalid expires_at value for %s; ignoring expiry.", email)
            return email
        if expires_at <= now:
            return None
        return email
    return None


def _parse_expiry_timestamp(raw_value: str) -> datetime | None:
    if not raw_value:
        return None
    candidate = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@lru_cache(maxsize=4)
def _get_permission_structure(
    cache_key: tuple[str, int, int],
) -> dict[str, tuple[str, ...]]:
    path_str, _mtime_ns, _size = cache_key
    path = Path(path_str)
    if not path.exists():
        LOGGER.warning("Permission structure file not found at %s; allowing all pages.", path)
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}") from exc
    structure: dict[str, tuple[str, ...]] = {}
    for page_key, prefixes in raw.items():
        if not isinstance(page_key, str):
            continue
        if not isinstance(prefixes, list):
            continue
        normalized: list[str] = []
        for prefix in prefixes:
            if not isinstance(prefix, str):
                continue
            candidate = prefix.strip()
            if not candidate:
                continue
            if not candidate.startswith("/"):
                candidate = f"/{candidate}"
            normalized.append(candidate)
        if normalized:
            structure[page_key.strip().lower()] = tuple(normalized)
    return structure


def get_site_permissions() -> dict[str, set[str]]:
    """Return the cached site permission map."""

    return _get_site_permissions(_site_permissions_cache_key())


def get_permission_structure() -> dict[str, tuple[str, ...]]:
    """Return the cached permission structure mapping."""

    return _get_permission_structure(_permission_structure_cache_key())


def get_permission_key_for_path(path: str) -> str | None:
    """Return the permission key that matches the request path."""

    if not path:
        return None
    normalized_path = path if path.startswith("/") else f"/{path}"
    matches: list[tuple[int, str]] = []
    for page_key, prefixes in get_permission_structure().items():
        for prefix in prefixes:
            if normalized_path.startswith(prefix):
                matches.append((len(prefix), page_key))
    if not matches:
        return None
    matches.sort(reverse=True)
    if len(matches) > 1:
        LOGGER.debug(
            "Multiple permission prefixes matched path %s; using %s",
            normalized_path,
            matches[0][1],
        )
    return matches[0][1]


def get_allowed_page_keys_for_email(email: str) -> set[str]:
    """Return the allowed page keys for a given email."""

    normalized = (email or "").strip().lower()
    if not normalized:
        return set()
    permissions = get_site_permissions()
    return {
        page
        for page, allowed in permissions.items()
        if normalized in allowed or _ALL_AUTHENTICATED_USERS in allowed
    }


def _email_has_site_permission(email: str, allowed: set[str]) -> bool:
    """Return whether an email or the authenticated-user wildcard is allowed."""

    return email in allowed or _ALL_AUTHENTICATED_USERS in allowed


def require_site_permission(page_key: str):
    """Return a dependency enforcing per-page access control."""

    page_key = page_key.strip().lower()

    def _dependency(request: Request) -> AuthenticatedUser:
        user = require_authenticated_user_for_site(request)
        if user is None:
            return None
        permissions = _get_site_permissions(_site_permissions_cache_key())
        if not permissions:
            return user
        normalized_email = user.email.strip().lower()
        allowed = permissions.get(page_key)
        if allowed is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": "You are not authorized to see this page.",
                    "page": page_key,
                    "email": user.email,
                },
            )
        if not _email_has_site_permission(normalized_email, allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": "You are not authorized to see this page.",
                    "page": page_key,
                    "email": user.email,
                },
            )
        return user

    return _dependency


def require_site_permission_for_request(request: Request) -> AuthenticatedUser | None:
    """FastAPI dependency enforcing access using permission_structure.json."""

    user = require_authenticated_user_for_site(request)
    if user is None:
        return None
    page_key = get_permission_key_for_path(request.url.path)
    if page_key is None:
        return user
    permissions = _get_site_permissions(_site_permissions_cache_key())
    if not permissions:
        return user
    normalized_email = user.email.strip().lower()
    allowed = permissions.get(page_key)
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": "You are not authorized to see this page.",
                "page": page_key,
                "email": user.email,
            },
        )
    if not _email_has_site_permission(normalized_email, allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": "You are not authorized to see this page.",
                "page": page_key,
                "email": user.email,
            },
        )
    return user
