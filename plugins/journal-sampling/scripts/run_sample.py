"""Run deterministic journal sampling from canonical normalized rows."""

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
    add_common_args,
    comma_list,
    configure_logging,
    load_client_engagement_context,
    run_sample,
)

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run sampling."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "normalized_csv", type=Path, help="normalized_journal.csv path."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where journal_sample.* and sampling_audit.json will be written.",
    )
    parser.add_argument(
        "--method",
        default="random",
        choices=["random", "systematic", "stratified", "mus"],
        help="Deterministic sampling method.",
    )
    parser.add_argument("--size", type=int, default=25, help="Requested sample size.")
    parser.add_argument(
        "--group-column",
        default="account",
        help="Group column for stratified sampling.",
    )
    parser.add_argument(
        "--include-accounts", help="Comma-separated account allow-list."
    )
    parser.add_argument(
        "--exclude-accounts", help="Comma-separated account block-list."
    )
    parser.add_argument("--date-start", help="Inclusive ISO date lower bound.")
    parser.add_argument("--date-end", help="Inclusive ISO date upper bound.")
    parser.add_argument(
        "--min-abs",
        help="Minimum absolute amount as exact localized decimal text.",
    )
    parser.add_argument(
        "--normalization-diagnostics",
        type=Path,
        help=(
            "Optional normalization_diagnostics.json path. Defaults beside the "
            "normalized CSV."
        ),
    )
    parser.add_argument("--keyword", help="Case-insensitive line-description filter.")
    parser.add_argument(
        "--client-engagement",
        type=Path,
        required=True,
        help="Studio Archive client workflow context JSON.",
    )
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    result = run_sample(
        args.normalized_csv,
        args.output_dir,
        method=args.method,
        size=args.size,
        group_column=args.group_column,
        include_accounts=comma_list(args.include_accounts),
        exclude_accounts=comma_list(args.exclude_accounts),
        date_start=args.date_start,
        date_end=args.date_end,
        min_abs=args.min_abs,
        keyword=args.keyword,
        language=args.language,
        normalization_diagnostics=args.normalization_diagnostics,
        client_engagement=load_client_engagement_context(args.client_engagement),
    )
    LOGGER.info("sample_rows=%s", result.frame.height)
    LOGGER.info("wrote %s", args.output_dir / "journal_sample.csv")
    LOGGER.info("wrote %s", args.output_dir / "sampling_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
