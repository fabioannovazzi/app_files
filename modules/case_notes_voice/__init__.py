"""Voice service package; HTTP routers load only when requested."""

from __future__ import annotations

from typing import Any

__all__ = ["router", "site_router"]


def __getattr__(name: str) -> Any:
    """Keep service imports independent of FastAPI adapter initialization."""
    if name not in __all__:
        raise AttributeError(name)
    from modules.case_notes_voice import api

    return getattr(api, name)
