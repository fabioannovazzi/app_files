"""No-op chart-comment helpers for headless plugin packaging."""

from __future__ import annotations

from typing import Any

__all__ = [
    "get_comments_from_data",
    "get_comments_from_data_fragment",
    "get_comments_from_images",
]


def get_comments_from_data(*_args: Any, **_kwargs: Any) -> str:
    """Return no chart comment in the headless plugin runtime."""

    return ""


def get_comments_from_data_fragment(*_args: Any, **_kwargs: Any) -> str:
    """Return no chart comment in the headless plugin runtime."""

    return ""


def get_comments_from_images(*_args: Any, **_kwargs: Any) -> str:
    """Return no chart comment in the headless plugin runtime."""

    return ""
