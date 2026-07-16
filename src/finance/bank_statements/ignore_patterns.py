from __future__ import annotations

"""Helpers for non-transaction regex patterns.

This module loads and compiles the shared set of regex patterns used to
identify non-transaction lines in bank statements.  Patterns are defined in
``config/statement_ignore_patterns.json`` and are loaded once at import time.
"""

import json
import re
from pathlib import Path
from typing import Dict, List

__all__ = ["DROP_PATTERNS", "ALL_PATTERNS"]

_CFG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "statement_ignore_patterns.json"
)


def _load_patterns() -> Dict[str, List[re.Pattern[str]]]:
    try:
        data = json.loads(_CFG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    compiled: Dict[str, List[re.Pattern[str]]] = {}
    for name, patterns in data.items():
        compiled[name] = [re.compile(pat, re.IGNORECASE) for pat in patterns]
    return compiled


DROP_PATTERNS: Dict[str, List[re.Pattern[str]]] = _load_patterns()
ALL_PATTERNS: List[re.Pattern[str]] = [
    pat for patterns in DROP_PATTERNS.values() for pat in patterns
]
