"""Utilities for deterministic static Plotly exports."""

from __future__ import annotations

from typing import Any

import plotly.io as pio

__all__ = ["normalize_plotly_figure_for_static_export"]


def normalize_plotly_figure_for_static_export(fig: Any) -> tuple[Any, dict[str, Any]]:
    """Return a plain Plotly figure for static export.

    Legacy chart builders sometimes leave figure objects with live array/layout
    state that Kaleido handles poorly. A JSON roundtrip keeps the analytical and
    visual specification but detaches it from those runtime objects.
    """

    try:
        normalized = pio.from_json(pio.to_json(fig, validate=False), skip_invalid=False)
        normalized = pio.from_json(
            pio.to_json(normalized, validate=False), skip_invalid=False
        )
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        return fig, {
            "status": "failed",
            "method": "plotly_json_double_roundtrip",
            "error": str(exc),
        }
    return normalized, {
        "status": "applied",
        "method": "plotly_json_double_roundtrip",
    }
