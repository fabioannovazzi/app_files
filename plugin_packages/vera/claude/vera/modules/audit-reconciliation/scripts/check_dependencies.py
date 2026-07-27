"""Check Python dependencies declared by this Claude plugin.

This helper is intentionally small and local to the plugin package. Claude can
run it before starting a workflow and either install the declared requirements
or explain the missing libraries to a non-technical user.
"""

from __future__ import annotations

import sys as _bootstrap_sys

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__audit_reconciliation_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/audit-reconciliation"
)

import os as _bootstrap_os

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_audit_reconciliation_implementation_bootstrap",
}
_bootstrap_stat = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _bootstrap_stat.st_mode & 0o170000 != 0o100000 or _bootstrap_stat.st_nlink != 1:
    raise RuntimeError(
        "implementation bootstrap must be an ordinary single-link regular file"
    )
_bootstrap_descriptor = _bootstrap_os.open(
    _BOOTSTRAP_PATH,
    _bootstrap_os.O_RDONLY | getattr(_bootstrap_os, "O_NOFOLLOW", 0),
)
try:
    _bootstrap_open_stat = _bootstrap_os.fstat(_bootstrap_descriptor)
    _bootstrap_identity = (
        _bootstrap_stat.st_dev,
        _bootstrap_stat.st_ino,
        _bootstrap_stat.st_size,
        _bootstrap_stat.st_mtime_ns,
        _bootstrap_stat.st_nlink,
    )
    if _bootstrap_identity != (
        _bootstrap_open_stat.st_dev,
        _bootstrap_open_stat.st_ino,
        _bootstrap_open_stat.st_size,
        _bootstrap_open_stat.st_mtime_ns,
        _bootstrap_open_stat.st_nlink,
    ):
        raise RuntimeError("implementation bootstrap changed before it was read")
    with _bootstrap_os.fdopen(
        _bootstrap_descriptor,
        "rb",
        closefd=False,
    ) as _bootstrap_handle:
        _bootstrap_source = _bootstrap_handle.read()
    _bootstrap_after_stat = _bootstrap_os.fstat(_bootstrap_descriptor)
    if (
        _bootstrap_identity
        != (
            _bootstrap_after_stat.st_dev,
            _bootstrap_after_stat.st_ino,
            _bootstrap_after_stat.st_size,
            _bootstrap_after_stat.st_mtime_ns,
            _bootstrap_after_stat.st_nlink,
        )
        or len(_bootstrap_source) != _bootstrap_after_stat.st_size
    ):
        raise RuntimeError("implementation bootstrap changed while it was read")
finally:
    _bootstrap_os.close(_bootstrap_descriptor)
# Execute only the pre-opened single-link bootstrap source.
exec(  # nosec B102
    compile(_bootstrap_source, _BOOTSTRAP_PATH, "exec"),
    _BOOTSTRAP_NAMESPACE,
)
_BOOTSTRAP_NAMESPACE["activate_implementation_boundary"](())

import argparse
import importlib.util
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "build_dependency_check",
    "declared_requirements",
    "import_name",
    "main",
    "plugin_root",
    "requirement_name",
    "selected_requirement_files",
]


PACKAGE_IMPORTS = {
    "beautifulsoup4": "bs4",
    "opencv-python": "cv2",
    "paddlepaddle": "paddle",
    "pillow": "PIL",
    "pymupdf": "fitz",
    "python-docx": "docx",
}


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def import_name(package_name: str) -> str:
    return PACKAGE_IMPORTS.get(package_name.lower(), package_name.replace("-", "_"))


def declared_requirements(requirement_files: list[Path]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for requirements_file in requirement_files:
        for line in requirements_file.read_text(encoding="utf-8").splitlines():
            package = requirement_name(line)
            if package:
                rows.append((requirements_file.name, package, import_name(package)))
    return rows


def selected_requirement_files(
    include_optional: bool, explicit_files: list[str]
) -> list[Path]:
    root = plugin_root()
    if explicit_files:
        files = [root / name for name in explicit_files]
    elif include_optional:
        files = sorted(root.glob("requirements*.txt"))
    else:
        files = [root / "requirements.txt"]
    return [path for path in files if path.exists()]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_dependency_check(
    *,
    include_optional: bool = False,
    explicit_files: list[str] | None = None,
) -> dict[str, Any]:
    """Return a JSON-serializable dependency-check contract for run intake."""

    requested_files = explicit_files or []
    files = selected_requirement_files(include_optional, requested_files)
    command_parts = ["python", "scripts/check_dependencies.py"]
    if include_optional:
        command_parts.append("--include-optional")
    for name in requested_files:
        command_parts.extend(["--requirements", name])
    if not files:
        return {
            "status": "missing_requirements_file",
            "checked_at": _utc_now(),
            "command": " ".join(command_parts),
            "requirement_files": requested_files,
            "missing": [],
            "note": "No selected requirements file was found in this plugin package.",
        }

    missing: list[dict[str, str]] = []
    checked: list[dict[str, str]] = []
    for source_file, package, module_name in declared_requirements(files):
        row = {
            "requirements_file": source_file,
            "package": package,
            "module": module_name,
        }
        checked.append(row)
        if importlib.util.find_spec(module_name) is None:
            missing.append(row)

    return {
        "status": "missing_dependencies" if missing else "ok",
        "checked_at": _utc_now(),
        "command": " ".join(command_parts),
        "requirement_files": [path.name for path in files],
        "checked": checked,
        "checked_count": len(checked),
        "missing": missing,
        "missing_count": len(missing),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check this Claude plugin's Python dependencies."
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Check every requirements*.txt file, including optional OCR/browser extras.",
    )
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Specific requirements file under the plugin root. May be passed more than once.",
    )
    args = parser.parse_args()

    result = build_dependency_check(
        include_optional=args.include_optional,
        explicit_files=args.requirements,
    )
    if result["status"] == "missing_requirements_file":
        print(
            "MISSING_REQUIREMENTS_FILE: no requirements file found in this plugin package"
        )
        return 1

    if result["missing"]:
        print("MISSING_DEPENDENCIES")
        for row in result["missing"]:
            print(
                f"- {row['package']} ({row['module']}) from {row['requirements_file']}"
            )
        install_files = " ".join(f"-r {name}" for name in result["requirement_files"])
        print(
            f"Suggested install from plugin directory: python -m pip install {install_files}"
        )
        return 1

    print("OK: all selected plugin dependencies are importable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
