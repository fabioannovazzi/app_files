"""Create one bounded Report Builder model-context expansion packet."""

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
exec(  # nosec B102
    compile(_BOOTSTRAP_BYTES, _BOOTSTRAP_PATH, "exec"), _BOOTSTRAP_NAMESPACE
)
_BOOTSTRAP_NAMESPACE["activate_implementation_boundary"]()
_SCRIPTS_DIR = _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__))
if _SCRIPTS_DIR not in _bootstrap_sys.path:
    _bootstrap_sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import json
from pathlib import Path

from report_builder_core import build_model_context_expansion, write_json
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)


def _json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _header_row(value: str) -> int | None:
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
    """Write a purpose-labelled, hash-receipted table slice."""

    parser = argparse.ArgumentParser(
        description=(
            "Expand one exact Report Builder table/range from private control "
            "without exposing the full source inventory."
        )
    )
    parser.add_argument("--inspection-control", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--table-id", required=True)
    parser.add_argument("--header-row", required=True, type=_header_row)
    parser.add_argument(
        "--columns",
        required=True,
        help="Comma-separated exact column names (maximum sixteen).",
    )
    parser.add_argument("--row-start", required=True, type=int)
    parser.add_argument("--row-limit", required=True, type=int)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="report-builder",
            input_paths=[args.inspection_control],
            output_dir=args.output,
        )
        packet = build_model_context_expansion(
            _json_object(args.inspection_control),
            table_id=args.table_id,
            header_row=args.header_row,
            columns=[item.strip() for item in args.columns.split(",")],
            row_start=args.row_start,
            row_limit=args.row_limit,
            purpose=args.purpose,
        )
    except (AssuranceContractError, ValueError) as exc:
        parser.error(str(exc))
    write_json(args.output, packet)
    print(
        "OK: wrote bounded model-context expansion "
        f"{args.output} ({len(packet['rows'])} rows)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
