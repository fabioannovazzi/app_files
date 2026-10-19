"""Minimal inherited environment for local workflow helper processes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

__all__ = ["local_helper_environment"]


def local_helper_environment(
    *, python: str | None = None, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Copy runtime names and identify a private child, preserving Windows casing."""
    source = os.environ if environ is None else environ
    names = set(json.loads(Path(__file__).with_suffix(".json").read_text()))
    result = {key: value for key, value in source.items() if key.upper() in names}
    if python is not None:
        result = {
            key: value for key, value in result.items() if key.upper() != "PYTHON"
        }
        result["PYTHON"] = python
    # This helper builds internal subprocesses whose results are consumed locally.
    # Their enclosing CLI or MCP boundary records the payload it actually returns.
    result["VERA_REPORTING_INTERNAL"] = "1"
    return result
