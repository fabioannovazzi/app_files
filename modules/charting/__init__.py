"""Charting module public API."""
import logging
from typing import Any

from .plot_horizontal_bar import plot_horizontal_bar

try:  # pragma: no cover - during tests this import may fail
    from .polars_helpers import unique_values_lazy
except Exception as e:  # pragma: no cover - provide a stub if helpers are patched
    logging.exception(e)

    def unique_values_lazy(*args: Any, **kwargs: Any) -> None:
        """Placeholder used when :mod:`polars_helpers` is not fully available."""
        raise NotImplementedError("unique_values_lazy unavailable")


__all__ = ["plot_horizontal_bar", "unique_values_lazy"]
