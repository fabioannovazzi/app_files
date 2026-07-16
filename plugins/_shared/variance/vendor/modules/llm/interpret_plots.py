"""No-op plot interpretation helpers for headless plugin packaging."""

from __future__ import annotations

from typing import Any

__all__ = [
    "explain_metrics_for_barmekko_prompt",
    "explain_metrics_for_stacked_column_prompt",
]


def explain_metrics_for_barmekko_prompt(*_args: Any, **_kwargs: Any) -> str:
    """Return no prompt text in the deterministic chart runtime."""

    return ""


def explain_metrics_for_stacked_column_prompt(*_args: Any, **_kwargs: Any) -> str:
    """Return no prompt text in the deterministic chart runtime."""

    return ""
