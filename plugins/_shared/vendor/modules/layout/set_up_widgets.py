"""Headless widget stubs used by vendored variance code."""

from __future__ import annotations

from typing import Any

__all__ = ["download_merged_file", "download_plot_file", "submit_variance_charts"]


def download_merged_file(*_args: Any, **_kwargs: Any) -> None:
    """No-op replacement for the legacy UI download side effect."""

    return None


def download_plot_file(*_args: Any, **_kwargs: Any) -> None:
    """No-op replacement for legacy chart data download widgets."""

    return None


def submit_variance_charts(
    _column_array: list[str],
    _param_dict: dict[str, Any],
    chart_dict: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    """Return a submitted state without invoking legacy UI widgets."""

    return True, chart_dict
