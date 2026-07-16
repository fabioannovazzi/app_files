from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_PDP_STORE_PATH = Path("data/pdp/pdp")

PDP_STORE_PATH_HELP = (
    "PDP store anchor path used for local cache locations "
    "(default: data/pdp/pdp). Runtime PDP data is stored in Postgres via "
    "PDP_DATABASE_URL."
)


def enforce_default_pdp_store_path(path: Path | str | None = None) -> Path:
    """Return the canonical PDP store anchor path."""

    canonical = DEFAULT_PDP_STORE_PATH.resolve()
    requested = canonical if path is None else Path(path).resolve()
    if requested != canonical:
        raise ValueError(f"Only the canonical PDP store path is supported: {canonical}")
    canonical.parent.mkdir(parents=True, exist_ok=True)
    return canonical


def add_pdp_store_path_argument(
    parser: argparse.ArgumentParser,
    *,
    default: Path | None = DEFAULT_PDP_STORE_PATH,
    required: bool = False,
    help_text: str = PDP_STORE_PATH_HELP,
    dest: str = "pdp_store_path",
) -> None:
    """Add the visible PDP store anchor flag."""

    parser.add_argument(
        "--pdp-store-path",
        dest=dest,
        metavar="PDP_STORE_PATH",
        type=Path,
        default=default,
        required=required,
        help=help_text,
    )


__all__ = [
    "DEFAULT_PDP_STORE_PATH",
    "PDP_STORE_PATH_HELP",
    "add_pdp_store_path_argument",
    "enforce_default_pdp_store_path",
]
