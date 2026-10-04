"""Exact restoration from Rizzo's native per-analysis dictionary."""

from __future__ import annotations

import re

__all__ = ["restore"]


def restore(text: str, mapping: dict[str, str]) -> str:
    """Replace canonical native tokens once, without identity inference or repair.

    A single pass prevents restored values containing another token from being
    replaced again. Canonical brackets also keep FULLNAME_1 distinct from 10.
    Rizzo's desktop reverse() uses the same dictionary lookup and single-pass
    principle; this adapter requires unchanged canonical tokens.
    """
    if not mapping:
        return text
    pattern = re.compile("|".join(re.escape(key) for key in mapping))
    return pattern.sub(lambda match: mapping[match.group(0)], text)
