from __future__ import annotations

import polars as pl

from modules.layout.memoization import hash_polars_df, hash_polars_lf
from modules.utilities.utils import get_row_count
from src.hierarchy_fix_logic import (
    _build_chains,
    detect_hierarchies,
    get_ambiguous_rows,
    order_hierarchy_pairs,
    resolve_hierarchies,
)

__all__ = [
    "_build_chains",
    "detect_hierarchies",
    "get_ambiguous_rows",
    "order_hierarchy_pairs",
    "pairs_to_chains",
    "resolve_hierarchies",
    "frame_hash",
    "frame_shape",
]


def pairs_to_chains(pairs_df: pl.DataFrame) -> pl.DataFrame:
    """Return full hierarchy chains as a single column."""

    if pairs_df.height == 0:
        return pl.DataFrame({"hierarchy": []})

    pairs = [(r["child"], r["parent"]) for r in pairs_df.to_dicts()]

    seen: set[str] = set()
    chains: list[str] = []
    for chain in _build_chains(pairs):
        text = " ➜ ".join(reversed(chain))
        if text not in seen:
            seen.add(text)
            chains.append(text)

    return pl.DataFrame({"hierarchy": chains})


def frame_shape(frame: pl.DataFrame | pl.LazyFrame) -> tuple[int, int]:
    """Return ``(rows, columns)`` for ``frame`` without materializing."""

    if isinstance(frame, pl.DataFrame):
        return get_row_count(frame), frame.width

    rows = frame.select(pl.len()).collect(engine="streaming")[0, 0]
    cols = frame.width
    return rows, cols


def frame_hash(frame: pl.DataFrame | pl.LazyFrame) -> str:
    """Return stable MD5 hash for ``frame``."""

    return hash_polars_df(frame) if isinstance(frame, pl.DataFrame) else hash_polars_lf(frame)
