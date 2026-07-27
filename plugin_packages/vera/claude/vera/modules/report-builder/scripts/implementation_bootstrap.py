"""Pre-import execution boundary for assured Report Builder commands.

The bootstrap intentionally uses only the interpreter-provided ``sys`` and
``os`` modules.  It moves Python's cache lookup outside the plugin before any
local import and rejects every implementation entry outside the exact
receipted contract.  This proves execution/receipt consistency; it does not
authenticate the installed package or a reviewer.
"""

from __future__ import annotations

import sys as _sys

_sys.dont_write_bytecode = True
_sys.pycache_prefix = (
    r"Z:\__report_builder_no_bytecode__"
    if _sys.platform == "win32"
    else "/dev/null/report-builder"
)

import os as _os

__all__ = [
    "IMPLEMENTATION_CONTRACT",
    "activate_implementation_boundary",
    "validate_implementation_tree",
]

IMPLEMENTATION_CONTRACT = (
    ("plugin", ".codex-plugin/plugin.json"),
    ("plugin", ".app.json"),
    ("plugin", ".mcp.json"),
    ("plugin", "assets/icon.svg"),
    ("plugin", "assets/report-builder-review-widget.html"),
    ("plugin", "assets/review-workbench-adapter.json"),
    ("plugin", "mcp/server.cjs"),
    ("plugin", "scripts/apply_review_edits.py"),
    ("plugin", "scripts/build_report.py"),
    ("plugin", "scripts/check_dependencies.py"),
    ("plugin", "scripts/implementation_bootstrap.py"),
    ("plugin", "scripts/implementation_contract.py"),
    ("plugin", "scripts/inspect_inputs.py"),
    ("plugin", "scripts/physical_output_set.py"),
    ("plugin", "scripts/prepared_contract.py"),
    ("plugin", "scripts/report_builder_core.py"),
    ("plugin", "scripts/report_builder_integrity.py"),
    ("plugin", "scripts/report_gates.py"),
    ("plugin", "scripts/review_successor.py"),
    ("plugin", "scripts/review_numeric_measures.py"),
    ("plugin", "scripts/review_session.py"),
    ("plugin", "scripts/seal_review_integrity.py"),
    ("plugin", "scripts/validate_review_integrity.py"),
    ("shared_assurance", "__init__.py"),
    ("shared_assurance", "contracts.py"),
    ("shared_assurance", "decisions.py"),
    ("shared_assurance", "envelope.py"),
    ("shared_assurance", "money.py"),
    ("shared_assurance", "relationships.py"),
    ("shared_assurance", "review_output_transaction.cjs"),
    ("shared_assurance", "serialization.py"),
)

_DIRECTORY_MODE = 0o040000
_FILE_MODE = 0o100000
_TYPE_MASK = 0o170000


def _is_real_directory(path: str) -> bool:
    try:
        current = _os.lstat(path)
    except FileNotFoundError:
        return False
    return current.st_mode & _TYPE_MASK == _DIRECTORY_MODE


def _shared_assurance_root(plugin_root: str) -> str:
    candidates = (
        _os.path.join(plugin_root, "vendor", "modules", "vera_assurance"),
        _os.path.join(
            _os.path.dirname(_os.path.dirname(plugin_root)),
            "vendor",
            "modules",
            "vera_assurance",
        ),
        _os.path.join(
            _os.path.dirname(plugin_root),
            "_shared",
            "vendor",
            "modules",
            "vera_assurance",
        ),
    )
    for candidate in candidates:
        if _is_real_directory(candidate):
            return _os.path.abspath(candidate)
    raise RuntimeError("The required vera_assurance module is not available.")


def _expected_directories() -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    for root_id, relative_path in IMPLEMENTATION_CONTRACT:
        parent = _os.path.dirname(relative_path)
        while parent:
            expected.add((root_id, parent.replace(_os.sep, "/")))
            parent = _os.path.dirname(parent)
    return expected


def _record_file(
    *,
    root_id: str,
    root: str,
    path: str,
    observed_files: set[tuple[str, str]],
) -> None:
    current = _os.lstat(path)
    if current.st_mode & _TYPE_MASK != _FILE_MODE or current.st_nlink != 1:
        raise RuntimeError(
            "implementation files must be ordinary single-link regular files"
        )
    relative = _os.path.relpath(path, root).replace(_os.sep, "/")
    observed_files.add((root_id, relative))


def _scan_tree(
    *,
    root_id: str,
    root: str,
    scan_root: str,
    observed_files: set[tuple[str, str]],
    observed_directories: set[tuple[str, str]],
) -> None:
    current = _os.lstat(scan_root)
    if current.st_mode & _TYPE_MASK != _DIRECTORY_MODE:
        raise RuntimeError("implementation root must be a real directory")
    scan_relative = _os.path.relpath(scan_root, root).replace(_os.sep, "/")
    if scan_relative != ".":
        observed_directories.add((root_id, scan_relative))
    pending = [scan_root]
    while pending:
        directory = pending.pop()
        with _os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        for entry in entries:
            relative = _os.path.relpath(entry.path, root).replace(_os.sep, "/")
            current = entry.stat(follow_symlinks=False)
            entry_type = current.st_mode & _TYPE_MASK
            if entry.is_symlink():
                raise RuntimeError("implementation entries must not be symlinks")
            if entry_type == _DIRECTORY_MODE:
                observed_directories.add((root_id, relative))
                pending.append(entry.path)
                continue
            if entry_type != _FILE_MODE or current.st_nlink != 1:
                raise RuntimeError(
                    "implementation files must be ordinary single-link regular files"
                )
            observed_files.add((root_id, relative))


def validate_implementation_tree(
    plugin_root: str,
    *,
    shared_assurance_root: str | None = None,
) -> dict[str, str]:
    """Reject every executable/configuration entry outside the exact contract."""

    root = _os.path.abspath(plugin_root)
    if not _is_real_directory(root):
        raise RuntimeError("implementation plugin root must be a real directory")
    shared_root = (
        _os.path.abspath(shared_assurance_root)
        if shared_assurance_root is not None
        else _shared_assurance_root(root)
    )
    roots = {"plugin": root, "shared_assurance": shared_root}
    observed_files: set[tuple[str, str]] = set()
    observed_directories: set[tuple[str, str]] = set()
    for relative_path in (".app.json", ".mcp.json"):
        _record_file(
            root_id="plugin",
            root=root,
            path=_os.path.join(root, relative_path),
            observed_files=observed_files,
        )
    for root_id, scan_root in (
        ("plugin", _os.path.join(root, ".codex-plugin")),
        ("plugin", _os.path.join(root, "assets")),
        ("plugin", _os.path.join(root, "mcp")),
        ("plugin", _os.path.join(root, "scripts")),
        ("shared_assurance", shared_root),
    ):
        _scan_tree(
            root_id=root_id,
            root=roots[root_id],
            scan_root=scan_root,
            observed_files=observed_files,
            observed_directories=observed_directories,
        )
    if observed_files != set(IMPLEMENTATION_CONTRACT):
        raise RuntimeError(
            "implementation filesystem does not match the exact "
            f"{len(IMPLEMENTATION_CONTRACT)}-file contract"
        )
    if observed_directories != _expected_directories():
        raise RuntimeError("implementation directories do not match the exact contract")
    return roots


def activate_implementation_boundary() -> dict[str, str]:
    """Disable local bytecode and validate the canonical implementation tree."""

    script_path = _os.path.abspath(__file__)
    plugin_root = _os.path.dirname(_os.path.dirname(script_path))
    return validate_implementation_tree(plugin_root)
