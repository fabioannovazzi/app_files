"""Freshly re-perform Journal Sampling normalization from retained provenance."""

from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__journal_sampling_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/journal-sampling"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Journal Sampling implementation bootstrap is not a real file.")
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
    raise RuntimeError("Journal Sampling implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_journal_sampling_implementation_bootstrap",
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
import logging
from pathlib import Path

from journal_sampling_core import (
    configure_logging,
    replay_normalization_from_provenance,
    write_json,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Replay normalization and write one machine-readable receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normalized_csv", type=Path)
    parser.add_argument("--diagnostics", type=Path)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument(
        "--read-only-upstream",
        action="store_true",
        help=(
            "Validate a finalized upstream run while writing only the caller's "
            "private replay receipt."
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    input_paths = [args.normalized_csv]
    if args.diagnostics is not None:
        input_paths.append(args.diagnostics)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="journal-sampling",
            input_paths=input_paths,
            output_dir=None if args.read_only_upstream else args.receipt_out,
            allowed_statuses=(
                ("ready_for_review", "completed")
                if args.read_only_upstream
                else ("running",)
            ),
        )
    except AssuranceContractError as exc:
        parser.error(str(exc))
    receipt = replay_normalization_from_provenance(
        args.normalized_csv,
        args.diagnostics,
    )
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.receipt_out, receipt)
    LOGGER.info("wrote %s", args.receipt_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
