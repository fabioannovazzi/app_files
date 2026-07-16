"""Utility helper re-exports."""

from __future__ import annotations

from typing import Any


def parse_date_column(*args: Any, **kwargs: Any):
    """Lazily import and call :func:`parse_date_column`."""

    from .date_utils import parse_date_column as _parse

    return _parse(*args, **kwargs)


__all__ = ["parse_date_column"]
