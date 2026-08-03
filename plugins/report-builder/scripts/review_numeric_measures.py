"""Bind Report Builder measure columns to an exact inspected source."""

from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__report_builder_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/report-builder"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Report Builder implementation bootstrap is not a real file.")
with open(_BOOTSTRAP_PATH, "rb") as _bootstrap_handle:
    _BOOTSTRAP_BEFORE = _bootstrap_os.fstat(_bootstrap_handle.fileno())
    _BOOTSTRAP_BYTES = _bootstrap_handle.read()
    _BOOTSTRAP_AFTER = _bootstrap_os.fstat(_bootstrap_handle.fileno())
_BOOTSTRAP_IDENTITY = (
    _BOOTSTRAP_ENTRY.st_dev,
    _BOOTSTRAP_ENTRY.st_ino,
    _BOOTSTRAP_ENTRY.st_size,
    _BOOTSTRAP_ENTRY.st_mtime_ns,
)
if (
    _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_BEFORE.st_dev,
        _BOOTSTRAP_BEFORE.st_ino,
        _BOOTSTRAP_BEFORE.st_size,
        _BOOTSTRAP_BEFORE.st_mtime_ns,
    )
    or _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_AFTER.st_dev,
        _BOOTSTRAP_AFTER.st_ino,
        _BOOTSTRAP_AFTER.st_size,
        _BOOTSTRAP_AFTER.st_mtime_ns,
    )
    or len(_BOOTSTRAP_BYTES) != _BOOTSTRAP_AFTER.st_size
):
    raise RuntimeError("Report Builder implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_report_builder_implementation_bootstrap",
}
# The exact stable single-link bootstrap source is verified above.
exec(  # nosec B102
    compile(_BOOTSTRAP_BYTES, _BOOTSTRAP_PATH, "exec"), _BOOTSTRAP_NAMESPACE
)
_BOOTSTRAP_NAMESPACE["activate_implementation_boundary"]()
_SCRIPTS_DIR = _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__))
if _SCRIPTS_DIR not in _bootstrap_sys.path:
    _bootstrap_sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

from report_builder_core import review_numeric_measure_columns, write_json
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _cell_dispositions(values: list[str]) -> dict[str, dict[int, str]]:
    """Parse exact COLUMN:ROW:include|exclude reviewer dispositions."""

    parsed: dict[str, dict[int, str]] = defaultdict(dict)
    for value in values:
        try:
            column, row_text, disposition = value.rsplit(":", 2)
            row = int(row_text)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "--cell-disposition must use COLUMN:ROW:include|exclude"
            ) from exc
        column = column.strip()
        disposition = disposition.strip().lower()
        if not column or row < 1 or disposition not in {"include", "exclude"}:
            raise ValueError("--cell-disposition must use COLUMN:ROW:include|exclude")
        if row in parsed[column]:
            raise ValueError(f"Duplicate cell disposition for {column} row {row}")
        parsed[column][row] = disposition
    return dict(parsed)


def _header_row(value: str) -> int | None:
    """Parse an explicit header-row choice."""

    if value.strip().lower() == "none":
        return None
    try:
        row = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--header-row must be a positive row number or 'none'"
        ) from exc
    if row < 1:
        raise argparse.ArgumentTypeError(
            "--header-row must be a positive row number or 'none'"
        )
    return row


def main() -> int:
    """Record one reviewed numeric-measure mapping in a report recipe."""

    parser = argparse.ArgumentParser(
        description=(
            "Bind explicitly reviewed measure columns to the source receipt "
            "recorded by Report Builder inspection."
        )
    )
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--section", required=True)
    parser.add_argument(
        "--header-row",
        required=True,
        type=_header_row,
        help="Reviewed one-based header row, or 'none' for a headerless table.",
    )
    parser.add_argument(
        "--columns",
        required=True,
        help="Comma-separated included columns, or 'none' when all candidates are excluded.",
    )
    parser.add_argument(
        "--exclude-columns",
        required=True,
        help="Comma-separated exact numeric candidate columns excluded by review, or 'none'.",
    )
    parser.add_argument(
        "--cell-disposition",
        action="append",
        default=[],
        help=(
            "Repeat for every nonblank cell of every included column using "
            "COLUMN:ROW:include|exclude."
        ),
    )
    parser.add_argument("--reviewer-ref", required=True)
    parser.add_argument("--reviewed-on", required=True)
    parser.add_argument(
        "--numeric-locale",
        required=True,
        choices=("it", "en", "fr", "de", "es"),
        help="Reviewed syntax locale for every selected numeric cell.",
    )
    parser.add_argument(
        "--currency",
        required=True,
        help="Reviewed ISO currency, or 'none' for non-currency units.",
    )
    parser.add_argument(
        "--unit",
        required=True,
        choices=("currency", "number", "count", "ratio", "percentage"),
    )
    parser.add_argument(
        "--scale",
        required=True,
        help="Positive canonical Decimal multiplier applied to every source value.",
    )
    parser.add_argument(
        "--parse-policy",
        required=True,
        choices=("strict_all_nonblank_v1",),
        help="Reviewed fail-closed parsing policy.",
    )
    parser.add_argument(
        "--sign-policy",
        required=True,
        choices=("as_presented_v1", "invert_v1"),
        help="Explicit sign treatment for included source cells.",
    )
    args = parser.parse_args()
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="report-builder",
            input_paths=[args.inspection, args.recipe],
            output_dir=args.output,
        )
    except AssuranceContractError as exc:
        parser.error(str(exc))
    included_columns = (
        []
        if args.columns.strip().lower() == "none"
        else [item.strip() for item in args.columns.split(",") if item.strip()]
    )
    excluded_columns = (
        []
        if args.exclude_columns.strip().lower() == "none"
        else [item.strip() for item in args.exclude_columns.split(",") if item.strip()]
    )
    updated = review_numeric_measure_columns(
        _json_object(args.inspection),
        _json_object(args.recipe),
        section_key=args.section,
        header_row=args.header_row,
        columns=included_columns,
        excluded_columns=excluded_columns,
        cell_dispositions=_cell_dispositions(args.cell_disposition),
        reviewer_ref=args.reviewer_ref,
        reviewed_on=args.reviewed_on,
        numeric_locale=args.numeric_locale,
        currency=None if args.currency.lower() == "none" else args.currency,
        unit=args.unit,
        scale=args.scale,
        parse_policy=args.parse_policy,
        sign_policy=args.sign_policy,
    )
    write_json(args.output, updated)
    LOGGER.info("Wrote source-bound numeric-measure review to %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
