from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping

__all__ = ["build_pdf_map", "movement_from_filename"]


def movement_from_filename(filename: str) -> str | None:
    """Extract the first sequence of digits from *filename* (stem only)."""
    stem = Path(filename).stem
    match = re.search(r"\d+", stem)
    return match.group() if match else None


def build_pdf_map(pdf_files: Iterable) -> Mapping[str, object]:
    """Return ``{movement_number: uploaded_file}`` mapping, ignoring filename duplicates.

    Parameters
    ----------
    pdf_files:
        Iterable of uploaded PDF objects. Each object must expose a ``name``
        attribute or be convertible to ``str``.

    Raises
    ------
    ValueError
        If two different filenames resolve to the same movement number.
    """

    mapping: dict[str, object] = {}
    seen_names: set[str] = set()
    for f in pdf_files:
        name = getattr(f, "name", str(f))
        if name in seen_names:
            continue
        seen_names.add(name)

        move = movement_from_filename(name)
        if not move:
            continue

        existing = mapping.get(move)
        if existing and getattr(existing, "name", str(existing)) != name:
            raise ValueError(f"Duplicate row number {move}")

        mapping[move] = f

    return mapping
