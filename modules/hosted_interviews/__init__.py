"""Hosted interview services with lazy HTTP router exports."""

from __future__ import annotations

from typing import Any

__all__ = ["admin_router", "public_router", "site_router"]


def __getattr__(name: str) -> Any:
    """Initialize HTTP adapters only when the application requests a router."""
    if name not in __all__:
        raise AttributeError(name)
    from modules.hosted_interviews import api

    return getattr(api, name)
