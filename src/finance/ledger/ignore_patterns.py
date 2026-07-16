"""Load ledger description ignore patterns from config."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

__all__ = ["load_ignore_patterns"]

_DEFAULT_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "ledger_ignore_patterns.json"
)


def load_ignore_patterns(path: Path | None = None) -> list[re.Pattern[str]]:
    """Return compiled regex patterns of ledger descriptions to ignore.

    Parameters
    ----------
    path:
        Optional path to a JSON file defining ``ignore_descriptions``.
        If omitted, defaults to the repository config file.
    """
    config_path = path or _DEFAULT_PATH
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    patterns: Iterable[str] = data.get("ignore_descriptions", [])
    return [re.compile(pat, re.IGNORECASE) for pat in patterns]
