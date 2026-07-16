from __future__ import annotations

from modules.auth.config import AuthConfig
from modules.auth.google_identity import (
    GoogleUserInfo,
    InvalidGoogleTokenError,
    UnauthorizedGoogleUserError,
    verify_google_identity_token,
)

__all__ = [
    "allowed_domains_hint",
    "authenticate_google_token",
    "format_user_display",
    "InvalidGoogleTokenError",
    "UnauthorizedGoogleUserError",
]


def allowed_domains_hint(domains: tuple[str, ...]) -> str:
    """Return a human-friendly hint about allowed email domains."""

    if not domains:
        return ""
    if len(domains) == 1:
        return f"Only addresses from **{domains[0]}** may sign in."
    domain_list = ", ".join(domains)
    return f"Only addresses from **{domain_list}** may sign in."


def authenticate_google_token(token: str, config: AuthConfig) -> GoogleUserInfo:
    """Validate the Google Identity token and return the authenticated user."""

    return verify_google_identity_token(
        token,
        config.google_client_id,
        allowed_domains=config.allowed_domains,
    )


def format_user_display(user: GoogleUserInfo) -> tuple[str, str]:
    """Return primary and secondary display text for the authenticated user."""

    primary = user.full_name or user.given_name or user.email
    secondary = user.email
    return primary, secondary
