from __future__ import annotations

import re
from typing import Any

__all__ = ["excel_safe_value", "sanitize_excel_string"]

EXCEL_ILLEGAL_CHARACTERS_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")


def sanitize_excel_string(value: str) -> str:
    """Remove control characters rejected by openpyxl cell exports."""

    return EXCEL_ILLEGAL_CHARACTERS_RE.sub("", value)


def excel_safe_value(value: Any) -> Any:
    """Return a cell value that openpyxl can write safely."""

    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return sanitize_excel_string(value)
    if hasattr(value, "isoformat"):
        return sanitize_excel_string(value.isoformat())
    return sanitize_excel_string(str(value))
