from __future__ import annotations

"""Helpers for storing authentication data in session-aware state storage."""

from dataclasses import asdict
from typing import Iterable

from modules.utilities.session_context import session_state

from modules.auth.google_identity import GoogleUserInfo

__all__ = [
    "AUTH_USER_SESSION_KEY",
    "clear_app_session_state",
    "get_authenticated_user",
    "set_authenticated_user",
]

AUTH_USER_SESSION_KEY = "auth_user"


def get_authenticated_user() -> GoogleUserInfo | None:
    """Return the authenticated user stored in session state, if any."""

    stored = session_state.get(AUTH_USER_SESSION_KEY)
    if isinstance(stored, GoogleUserInfo):
        return stored
    if isinstance(stored, dict):
        try:
            return GoogleUserInfo(**stored)
        except TypeError:
            return None
    return None


def set_authenticated_user(user: GoogleUserInfo) -> None:
    """Persist *user* details in session state."""

    session_state[AUTH_USER_SESSION_KEY] = asdict(user)


def clear_app_session_state(*, preserve_keys: Iterable[str] | None = None) -> None:
    """Remove session-context entries except those listed in *preserve_keys*."""

    preserved = set(preserve_keys or ())
    for key in list(session_state.keys()):
        if key in preserved:
            continue
        session_state.pop(key, None)
