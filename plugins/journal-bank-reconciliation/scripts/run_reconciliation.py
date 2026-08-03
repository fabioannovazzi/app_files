"""Run deterministic journal-to-bank reconciliation for Codex review."""

from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__journal_bank_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/journal-bank-reconciliation"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Journal–Bank implementation bootstrap is not a real file.")
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
    raise RuntimeError("Journal–Bank implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_journal_bank_implementation_bootstrap",
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

from journal_bank_core import add_common_args, configure_logging, run_reconciliation
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run reconciliation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", type=Path, help="Bank statement file or folder.")
    parser.add_argument("journal", type=Path, help="Journal/ledger file or folder.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where reconciliation outputs will be written.",
    )
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--sample", type=Path, help="Optional sample movements file.")
    parser.add_argument("--recipe", type=Path, help="Optional recipe JSON.")
    parser.add_argument(
        "--tolerance",
        default="1",
        help="Allowed exact absolute amount difference in canonical/localized decimal text.",
    )
    parser.add_argument(
        "--date-window-days",
        type=int,
        default=7,
        help="Allowed date difference in calendar days.",
    )
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    input_paths = [args.bank, args.journal]
    input_paths.extend(path for path in (args.sample, args.recipe) if path is not None)
    try:
        client_context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="journal-bank-reconciliation",
            input_paths=input_paths,
            output_dir=args.output_dir,
        )
    except AssuranceContractError as exc:
        LOGGER.error("CLIENT_ENGAGEMENT_BLOCKED: %s", exc)
        return 2

    result = run_reconciliation(
        args.bank,
        args.journal,
        args.output_dir,
        args.recipe,
        sample_path=args.sample,
        tolerance=args.tolerance,
        date_window_days=args.date_window_days,
        language=args.language,
        document_language=args.document_language,
        client_run_id=str(client_context["run_id"]),
        client_run_root=Path(str(client_context["run_root"])),
    )
    LOGGER.info("matched=%s", result.matches.height)
    LOGGER.info("unmatched_bank=%s", result.unmatched_bank.height)
    LOGGER.info("unmatched_journal=%s", result.unmatched_journal.height)
    LOGGER.info("stage_counts=%s", result.audit["stage_counts"])
    LOGGER.info("wrote %s", args.output_dir / "journal_bank_reconciliation.xlsx")
    LOGGER.info("wrote %s", args.output_dir / "reconciliation_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
