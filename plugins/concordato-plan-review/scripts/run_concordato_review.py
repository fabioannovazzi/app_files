from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__concordato_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/concordato-plan-review"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Concordato implementation bootstrap is not a real file.")
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
    raise RuntimeError("Concordato implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_concordato_implementation_bootstrap",
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

from concordato_plan_core import configure_logging, run_concordato_review

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run the concordato plan deterministic review helper."""

    parser = argparse.ArgumentParser(
        description="Inspect a concordato plan folder and prepare tie-out workpapers."
    )
    parser.add_argument("input_dir", type=Path, help="Folder containing plan sources.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where review artifacts will be written.",
    )
    parser.add_argument(
        "--reference-date",
        default="",
        help="Reference date or cut-off, for example 2026-03-31.",
    )
    parser.add_argument("--language", default="it", help="Working language.")
    parser.add_argument(
        "--document-language",
        default="auto",
        help="Source document language, or auto.",
    )
    parser.add_argument(
        "--tolerance",
        default="1",
        help="Maximum absolute difference for candidate amount matches.",
    )
    parser.add_argument(
        "--recipe",
        type=Path,
        help="Reviewed, source-bound role and numeric-disposition recipe.",
    )
    parser.add_argument(
        "--max-rows-per-sheet",
        type=int,
        default=5000,
        help="Maximum rows to scan in each workbook sheet.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    configure_logging(args.verbose)
    run = run_concordato_review(
        args.input_dir,
        args.output_dir,
        reference_date=args.reference_date,
        language=args.language,
        document_language=args.document_language,
        tolerance=args.tolerance,
        max_rows_per_sheet=args.max_rows_per_sheet,
        recipe=args.recipe,
    )
    LOGGER.info("wrote review artifacts to %s", run.output_dir)
    LOGGER.info("files_inspected=%s", len(run.inventory))
    LOGGER.info("amount_candidates=%s", len(run.amount_candidates))
    LOGGER.info("candidate_matches=%s", len(run.exact_matches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
