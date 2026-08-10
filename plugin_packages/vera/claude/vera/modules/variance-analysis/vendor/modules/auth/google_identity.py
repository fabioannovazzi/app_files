from __future__ import annotations

"""Utilities for verifying Google Identity tokens."""

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping


class Request:
    """Lazy proxy for ``google.auth.transport.requests.Request``."""

    def __new__(cls, *args: object, **kwargs: object) -> Any:
        request_class, _id_token = _google_auth_dependencies()
        return request_class(*args, **kwargs)


class _IdTokenProxy:
    """Lazy proxy for ``google.oauth2.id_token``."""

    def verify_oauth2_token(self, *args: object, **kwargs: object) -> Any:
        _request_class, id_token_module = _google_auth_dependencies()
        return id_token_module.verify_oauth2_token(*args, **kwargs)


id_token = _IdTokenProxy()

__all__ = [
    "GoogleUserInfo",
    "InvalidGoogleTokenError",
    "UnauthorizedGoogleUserError",
    "sanitize_google_user_info",
    "verify_google_identity_token",
]


class InvalidGoogleTokenError(ValueError):
    """Raised when the provided Google Identity token is invalid."""


class UnauthorizedGoogleUserError(PermissionError):
    """Raised when a verified user fails the authorization policy."""


@dataclass(frozen=True)
class GoogleUserInfo:
    """Minimal, sanitised representation of a Google user."""

    email: str
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    picture: str | None = None


def verify_google_identity_token(
    token: str,
    client_id: str,
    *,
    allowed_domains: Iterable[str] | None = None,
    allowed_emails: Iterable[str] | None = None,
    request: Any | None = None,
) -> GoogleUserInfo:
    """Validate *token* and return sanitised user information."""

    try:
        verification_request = request or Request()
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing
        raise InvalidGoogleTokenError(
            "Google authentication dependencies not installed."
        ) from exc

    try:
        id_info = id_token.verify_oauth2_token(token, verification_request, client_id)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise InvalidGoogleTokenError("Google token verification failed.") from exc
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing
        raise InvalidGoogleTokenError(
            "Google authentication dependencies not installed."
        ) from exc

    if not _is_email_verified(id_info):
        raise InvalidGoogleTokenError("Google account email is not verified.")

    user_info = sanitize_google_user_info(id_info)

    _enforce_email_restrictions(
        user_info.email,
        allowed_domains or (),
        allowed_emails or (),
    )

    return user_info


def _google_auth_dependencies() -> tuple[type[Any], Any]:
    """Import Google auth dependencies only when token verification is used."""

    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import id_token as google_id_token
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing
        raise ModuleNotFoundError(
            "google-auth is required to verify Google Identity tokens."
        ) from exc
    return GoogleAuthRequest, google_id_token


def sanitize_google_user_info(claims: Mapping[str, object]) -> GoogleUserInfo:
    """Extract and normalise safe fields from Google *claims*."""

    email = _clean_optional_str(claims.get("email"))
    if not email:
        raise InvalidGoogleTokenError(
            "Google token payload is missing an email address."
        )

    return GoogleUserInfo(
        email=email.lower(),
        full_name=_clean_optional_str(claims.get("name")),
        given_name=_clean_optional_str(claims.get("given_name")),
        family_name=_clean_optional_str(claims.get("family_name")),
        picture=_clean_optional_str(claims.get("picture")),
    )


def _is_email_verified(
    claims: MutableMapping[str, object] | Mapping[str, object],
) -> bool:
    """Return ``True`` when the email contained in *claims* is verified."""

    verified = claims.get("email_verified")
    if isinstance(verified, bool):
        return verified
    if isinstance(verified, str):
        return verified.lower() in {"1", "true", "yes"}
    return False


def _clean_optional_str(value: object) -> str | None:
    """Return a trimmed string or ``None`` when *value* is falsy."""

    if not isinstance(value, str):
        return None
    result = value.strip()
    return result or None


def _enforce_email_restrictions(
    email: str,
    allowed_domains: Iterable[str],
    allowed_emails: Iterable[str],
) -> None:
    """Validate *email* against allowed lists, raising on failure."""

    normalised_email = email.lower()
    allowed_email_set = {
        entry.strip().lower()
        for entry in allowed_emails
        if isinstance(entry, str) and entry.strip()
    }
    if allowed_email_set and normalised_email not in allowed_email_set:
        raise UnauthorizedGoogleUserError("Email address is not permitted to sign in.")

    allowed_domain_set = {
        entry.strip().lower()
        for entry in allowed_domains
        if isinstance(entry, str) and entry.strip()
    }
    if allowed_domain_set:
        domain = normalised_email.split("@")[-1]
        if domain not in allowed_domain_set:
            raise UnauthorizedGoogleUserError(
                "Email domain is not permitted to sign in."
            )
