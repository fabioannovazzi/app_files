"""No-op plot interpretation helpers for headless plugin packaging."""

from __future__ import annotations

from typing import Any

__all__ = [
    "explain_metrics_for_barmekko_prompt",
    "explain_metrics_for_stacked_column_prompt",
]


def explain_metrics_for_barmekko_prompt(*args: Any, **_kwargs: Any) -> Any:
    """Return the unchanged chart dictionary in the deterministic runtime."""

    return args[0] if args else {}


def explain_metrics_for_stacked_column_prompt(*args: Any, **_kwargs: Any) -> Any:
    """Return the unchanged chart dictionary in the deterministic runtime."""

    return args[0] if args else {}
