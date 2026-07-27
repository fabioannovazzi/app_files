"""Run deterministic entry-vs-support checks for professional review."""

from __future__ import annotations

import sys as _bootstrap_sys

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__check_entries_no_local_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/check-entries"
)

import os as _bootstrap_os

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_check_entries_implementation_bootstrap",
}
_bootstrap_lstat = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _bootstrap_lstat.st_mode & 0o170000 != 0o100000 or _bootstrap_lstat.st_nlink != 1:
    raise RuntimeError(
        "implementation bootstrap must be an ordinary single-link regular file"
    )
_bootstrap_flags = _bootstrap_os.O_RDONLY
_bootstrap_flags |= getattr(_bootstrap_os, "O_NOFOLLOW", 0)
_bootstrap_flags |= getattr(_bootstrap_os, "O_NONBLOCK", 0)
_bootstrap_fd = _bootstrap_os.open(_BOOTSTRAP_PATH, _bootstrap_flags)
try:
    _bootstrap_before = _bootstrap_os.fstat(_bootstrap_fd)
    _bootstrap_identity = (
        _bootstrap_before.st_dev,
        _bootstrap_before.st_ino,
        _bootstrap_before.st_mode,
        _bootstrap_before.st_nlink,
        _bootstrap_before.st_size,
        _bootstrap_before.st_mtime_ns,
        _bootstrap_before.st_ctime_ns,
    )
    if _bootstrap_identity != (
        _bootstrap_lstat.st_dev,
        _bootstrap_lstat.st_ino,
        _bootstrap_lstat.st_mode,
        _bootstrap_lstat.st_nlink,
        _bootstrap_lstat.st_size,
        _bootstrap_lstat.st_mtime_ns,
        _bootstrap_lstat.st_ctime_ns,
    ):
        raise RuntimeError("implementation bootstrap changed before open")
    _bootstrap_chunks = []
    _bootstrap_remaining = _bootstrap_before.st_size
    while _bootstrap_remaining:
        _bootstrap_chunk = _bootstrap_os.read(
            _bootstrap_fd,
            min(_bootstrap_remaining, 1024 * 1024),
        )
        if not _bootstrap_chunk:
            raise RuntimeError("implementation bootstrap ended during snapshot")
        _bootstrap_chunks.append(_bootstrap_chunk)
        _bootstrap_remaining -= len(_bootstrap_chunk)
    _bootstrap_after = _bootstrap_os.fstat(_bootstrap_fd)
    if _bootstrap_identity != (
        _bootstrap_after.st_dev,
        _bootstrap_after.st_ino,
        _bootstrap_after.st_mode,
        _bootstrap_after.st_nlink,
        _bootstrap_after.st_size,
        _bootstrap_after.st_mtime_ns,
        _bootstrap_after.st_ctime_ns,
    ):
        raise RuntimeError("implementation bootstrap changed during snapshot")
finally:
    _bootstrap_os.close(_bootstrap_fd)
_bootstrap_path_after = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _bootstrap_identity != (
    _bootstrap_path_after.st_dev,
    _bootstrap_path_after.st_ino,
    _bootstrap_path_after.st_mode,
    _bootstrap_path_after.st_nlink,
    _bootstrap_path_after.st_size,
    _bootstrap_path_after.st_mtime_ns,
    _bootstrap_path_after.st_ctime_ns,
):
    raise RuntimeError("implementation bootstrap path changed during snapshot")
# The snapshot is the exact no-follow, identity-stable local bootstrap bytes.
exec(  # nosec B102
    compile(b"".join(_bootstrap_chunks), _BOOTSTRAP_PATH, "exec"),
    _BOOTSTRAP_NAMESPACE,
)
_BOOTSTRAP_ROOTS = _BOOTSTRAP_NAMESPACE["activate_implementation_boundary"]()
_BOOTSTRAP_NAMESPACE["load_assurance_package"](
    _BOOTSTRAP_ROOTS["assurance_implementation"]
)
_bootstrap_path_final = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _bootstrap_identity != (
    _bootstrap_path_final.st_dev,
    _bootstrap_path_final.st_ino,
    _bootstrap_path_final.st_mode,
    _bootstrap_path_final.st_nlink,
    _bootstrap_path_final.st_size,
    _bootstrap_path_final.st_mtime_ns,
    _bootstrap_path_final.st_ctime_ns,
):
    raise RuntimeError("implementation bootstrap changed during validation")

import argparse
import logging
import sys
from pathlib import Path

_scripts_module_root = _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__))
if _scripts_module_root not in sys.path:
    sys.path.insert(0, _scripts_module_root)

from check_entries_core import add_common_args, configure_logging, run_entry_checks

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run deterministic entry checks."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path, help="Journal/sample-entry file.")
    parser.add_argument(
        "support",
        type=Path,
        help="FatturaPA ZIP/XML, authorized connector export, or supporting PDF folder.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where check outputs will be written.",
    )
    parser.add_argument("--recipe", type=Path, help="Optional recipe JSON.")
    parser.add_argument(
        "--amount-tolerance",
        default="0",
        help="Allowed exact absolute amount difference as decimal text.",
    )
    parser.add_argument(
        "--date-window-days",
        type=int,
        default=0,
        help="Allowed date difference in calendar days.",
    )
    parser.add_argument(
        "--connector-name",
        help="Authorized system that produced the local export; no credentials are accepted.",
    )
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    result = run_entry_checks(
        args.journal,
        args.support,
        args.output_dir,
        args.recipe,
        amount_tolerance=args.amount_tolerance,
        date_window_days=args.date_window_days,
        language=args.language,
        document_language=args.document_language,
        connector_name=args.connector_name,
    )
    LOGGER.info("checked_rows=%s", result.frame.height)
    LOGGER.info("status_counts=%s", result.audit["status_counts"])
    LOGGER.info("wrote %s", args.output_dir / "check_results.csv")
    LOGGER.info("wrote %s", args.output_dir / "check_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
