from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class LayoutConfig:
    """Recipe describing journal layout."""

    drop_rules: Dict[str, bool]
    entry_header_regex: str
    detail_regex: str
    number_format: Dict[str, Any]
    date_formats: List[str]
    column_bounds: Optional[List[int]] = None
    table_area: Optional[List[float]] = None
    shapes: Dict[str, str] = field(default_factory=dict)
