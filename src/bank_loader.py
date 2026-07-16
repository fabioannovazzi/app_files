"""Bank statement parsing API.

This module is a thin wrapper around the historical implementation in
``check_statements_logic``.  It exposes ``load_bank_files`` so that the UI
can depend on a focused module.
"""

from __future__ import annotations

from .check_statements import load_bank_files

__all__ = ["load_bank_files"]
