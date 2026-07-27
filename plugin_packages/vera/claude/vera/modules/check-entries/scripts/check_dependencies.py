"""Check Python dependencies declared by this Claude plugin."""

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
import importlib.util
import re
from pathlib import Path

PACKAGE_IMPORTS = {
    "fastexcel": "fastexcel",
    "openpyxl": "openpyxl",
    "pdfplumber": "pdfplumber",
    "polars": "polars",
    "xlsxwriter": "xlsxwriter",
}


def plugin_root() -> Path:
    """Return the plugin root directory."""

    return Path(__file__).resolve().parents[1]


def requirement_name(line: str) -> str:
    """Return the package name from one requirements.txt line."""

    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def import_name(package_name: str) -> str:
    """Return the import module name for a package name."""

    return PACKAGE_IMPORTS.get(package_name.lower(), package_name.replace("-", "_"))


def selected_requirement_files(explicit_files: list[str]) -> list[Path]:
    """Return requirement files to check."""

    root = plugin_root()
    files = (
        [root / name for name in explicit_files]
        if explicit_files
        else [root / "requirements.txt"]
    )
    return [path for path in files if path.exists()]


def main() -> int:
    """Run dependency checks."""

    parser = argparse.ArgumentParser(
        description="Check this Claude plugin's Python dependencies."
    )
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Specific requirements file under the plugin root. May be passed more than once.",
    )
    args = parser.parse_args()

    files = selected_requirement_files(args.requirements)
    if not files:
        print(
            "MISSING_REQUIREMENTS_FILE: no requirements file found in this plugin package"
        )
        return 1

    missing: list[tuple[str, str, str]] = []
    for requirements_file in files:
        for line in requirements_file.read_text(encoding="utf-8").splitlines():
            package = requirement_name(line)
            if not package:
                continue
            module_name = import_name(package)
            if importlib.util.find_spec(module_name) is None:
                missing.append((requirements_file.name, package, module_name))

    if missing:
        print("MISSING_DEPENDENCIES")
        for source_file, package, module_name in missing:
            print(f"- {package} ({module_name}) from {source_file}")
        install_files = " ".join(f"-r {path.name}" for path in files)
        print(
            f"Suggested install from plugin directory: python -m pip install {install_files}"
        )
        return 1

    print("OK: all selected plugin dependencies are importable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
