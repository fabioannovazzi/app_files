"""Helpers for processing review feedback outside the legacy UI."""

from __future__ import annotations

from typing import Mapping

import polars as pl


def pdf_bytes_for(
    movement: str, pdf_map: Mapping[str, object]
) -> tuple[bytes | None, str]:
    """Return the PDF bytes and filename for *movement* from ``pdf_map``."""
    pdf_file = pdf_map.get(movement)
    if not pdf_file:
        return None, ""
    name = getattr(pdf_file, "name", f"{movement}.pdf")
    if hasattr(pdf_file, "getvalue"):
        data = pdf_file.getvalue()
    else:
        if hasattr(pdf_file, "seek"):
            try:
                pdf_file.seek(0)
            except (OSError, ValueError):
                pass
        data = pdf_file.read()
        if hasattr(pdf_file, "seek"):
            try:
                pdf_file.seek(0)
            except (OSError, ValueError):
                pass
    return data, name


def merge_review_feedback(
    df: pl.DataFrame,
    status: Mapping[str, str],
    reasons: Mapping[str, str],
) -> pl.DataFrame:
    """Merge review *status* and *reasons* into *df*.

    Parameters
    ----------
    df:
        DataFrame containing the automatic check results.
    status:
        Mapping of movement numbers to the reviewer decision (``"ok"`` or
        ``"mismatch"``).
    reasons:
        Mapping of movement numbers to free-text override reasons.
    """

    rows: list[dict[str, object]] = []
    for row in df.to_dicts():
        movement = str(row.get("movement_number", ""))
        row["review_status"] = status.get(movement, row.get("check_status", ""))
        row["review_reason"] = reasons.get(movement, "")
        rows.append(row)
    infer_len = len(rows)
    return pl.DataFrame(rows, orient="row", infer_schema_length=infer_len)


__all__ = ["pdf_bytes_for", "merge_review_feedback"]
