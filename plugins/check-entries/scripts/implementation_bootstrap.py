"""Pre-import implementation boundary for Check Entries.

This module deliberately uses only interpreter-provided ``sys`` and ``os``
services.  The exact executable/rendering tree is closed before any local
module is imported because an existing timestamp-valid bytecode cache can
otherwise execute before ordinary receipt validation starts.  This is a
mechanically verifiable execution-safety control; it does not authenticate the
package publisher or establish professional review authority.
"""

from __future__ import annotations

import sys as _sys

_sys.dont_write_bytecode = True
_sys.pycache_prefix = (
    r"Z:\__check_entries_no_local_bytecode__"
    if _sys.platform == "win32"
    else "/dev/null/check-entries"
)

import os as _os

__all__ = [
    "IMPLEMENTATION_CONTRACT",
    "activate_implementation_boundary",
    "load_assurance_package",
    "validate_implementation_tree",
    "repair_vendor_bytecode",
]

IMPLEMENTATION_CONTRACT = (
    ("implementation", ".app.json"),
    ("implementation", ".codex-plugin/plugin.json"),
    ("implementation", ".mcp.json"),
    ("implementation", "assets/check-entries-review-widget.html"),
    ("implementation", "assets/icon.svg"),
    ("implementation", "assets/review-workbench-adapter.json"),
    ("implementation", "mcp/server.cjs"),
    ("implementation", "scripts/apply_review_edits.py"),
    ("implementation", "scripts/check_dependencies.py"),
    ("implementation", "scripts/check_entries_core.py"),
    ("implementation", "scripts/implementation_bootstrap.py"),
    ("implementation", "scripts/implementation_contract.py"),
    ("implementation", "scripts/inspect_entries.py"),
    ("implementation", "scripts/invoice_support.py"),
    ("implementation", "scripts/physical_output_set.py"),
    ("implementation", "scripts/review_session.py"),
    ("implementation", "scripts/run_checks.py"),
    ("implementation", "scripts/stable_ooxml.py"),
    ("assurance_implementation", "__init__.py"),
    ("assurance_implementation", "contracts.py"),
    ("assurance_implementation", "decisions.py"),
    ("assurance_implementation", "envelope.py"),
    ("assurance_implementation", "money.py"),
    ("assurance_implementation", "relationships.py"),
    ("assurance_implementation", "review_output_transaction.cjs"),
    ("assurance_implementation", "serialization.py"),
)

_DIRECTORY_MODE = 0o040000
_FILE_MODE = 0o100000
_TYPE_MASK = 0o170000


def _is_real_directory(path: str) -> bool:
    try:
        observed = _os.lstat(path)
    except FileNotFoundError:
        return False
    return observed.st_mode & _TYPE_MASK == _DIRECTORY_MODE


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


def _expected_directories(
    specifications: tuple[tuple[str, str], ...],
) -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    for root_id, relative_path in specifications:
        parent = _os.path.dirname(relative_path)
        while parent:
            expected.add((root_id, parent.replace(_os.sep, "/")))
            parent = _os.path.dirname(parent)
    return expected


def _scan_tree(
    *,
    root_id: str,
    root: str,
    scan_root: str,
    observed_files: set[tuple[str, str]],
    observed_directories: set[tuple[str, str]],
) -> None:
    root_entry = _os.lstat(scan_root)
    if root_entry.st_mode & _TYPE_MASK != _DIRECTORY_MODE:
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
            observed = entry.stat(follow_symlinks=False)
            entry_type = observed.st_mode & _TYPE_MASK
            if entry.is_symlink():
                raise RuntimeError("implementation entries must not be symlinks")
            if entry_type == _DIRECTORY_MODE:
                if entry.name == "__pycache__":
                    continue
                observed_directories.add((root_id, relative))
                pending.append(entry.path)
                continue
            if entry_type != _FILE_MODE or observed.st_nlink != 1:
                raise RuntimeError(
                    "implementation files must be ordinary single-link regular files"
                )
            if entry.name.endswith((".pyc", ".pyo")):
                continue
            observed_files.add((root_id, relative))


def _validate_root_file(
    root_id: str,
    root: str,
    relative_path: str,
    observed_files: set[tuple[str, str]],
) -> None:
    path = _os.path.join(root, *relative_path.split("/"))
    observed = _os.lstat(path)
    if observed.st_mode & _TYPE_MASK != _FILE_MODE or observed.st_nlink != 1:
        raise RuntimeError(
            "implementation files must be ordinary single-link regular files"
        )
    observed_files.add((root_id, relative_path))


def validate_implementation_tree(
    plugin_root: str,
    *,
    shared_assurance_root: str | None = None,
) -> dict[str, str]:
    """Reject every executable/rendering entry outside the exact contract."""

    root = _os.path.abspath(plugin_root)
    shared_root = (
        _os.path.abspath(shared_assurance_root)
        if shared_assurance_root is not None
        else _shared_assurance_root(root)
    )
    roots = {
        "implementation": root,
        "assurance_implementation": shared_root,
    }
    observed_files: set[tuple[str, str]] = set()
    observed_directories: set[tuple[str, str]] = set()
    for root_id, scan_root in (
        ("implementation", _os.path.join(root, "assets")),
        ("implementation", _os.path.join(root, "mcp")),
        ("implementation", _os.path.join(root, "scripts")),
        ("assurance_implementation", shared_root),
    ):
        _scan_tree(
            root_id=root_id,
            root=roots[root_id],
            scan_root=scan_root,
            observed_files=observed_files,
            observed_directories=observed_directories,
        )
    for relative_path in (".app.json", ".mcp.json"):
        _validate_root_file(
            "implementation",
            root,
            relative_path,
            observed_files,
        )
    plugin_manifest_directory = _os.path.join(root, ".codex-plugin")
    _scan_tree(
        root_id="implementation",
        root=root,
        scan_root=plugin_manifest_directory,
        observed_files=observed_files,
        observed_directories=observed_directories,
    )

    if observed_files != set(IMPLEMENTATION_CONTRACT):
        raise RuntimeError(
            "implementation filesystem does not match the exact 26-file contract"
        )
    if observed_directories != _expected_directories(IMPLEMENTATION_CONTRACT):
        raise RuntimeError("implementation directories do not match the exact contract")
    return roots


def activate_implementation_boundary() -> dict[str, str]:
    """Disable local bytecode and validate the canonical implementation tree."""

    script_path = _os.path.abspath(__file__)
    plugin_root = _os.path.dirname(_os.path.dirname(script_path))
    return validate_implementation_tree(plugin_root)


def load_assurance_package(shared_assurance_root: str) -> None:
    """Load only the validated package without exposing its vendor parent."""

    shared_root = _os.path.abspath(shared_assurance_root)
    expected_init = _os.path.join(shared_root, "__init__.py")
    existing = _sys.modules.get("vera_assurance")
    if existing is not None:
        existing_file = getattr(existing, "__file__", None)
        if (
            not isinstance(existing_file, str)
            or _os.path.abspath(existing_file) != expected_init
        ):
            raise RuntimeError(
                "An unexpected vera_assurance package is already loaded."
            )
        return

    import importlib.util as _importlib_util

    specification = _importlib_util.spec_from_file_location(
        "vera_assurance",
        expected_init,
        submodule_search_locations=[shared_root],
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("The validated vera_assurance package cannot be loaded.")
    package = _importlib_util.module_from_spec(specification)
    _sys.modules["vera_assurance"] = package
    loaded = False
    try:
        specification.loader.exec_module(package)
        loaded = True
    finally:
        if not loaded:
            _sys.modules.pop("vera_assurance", None)
    loaded_file = getattr(package, "__file__", None)
    if (
        not isinstance(loaded_file, str)
        or _os.path.abspath(loaded_file) != expected_init
    ):
        _sys.modules.pop("vera_assurance", None)
        raise RuntimeError("The loaded vera_assurance package is outside the contract.")


def repair_vendor_bytecode() -> int:
    """Remove only regular .pyc files directly inside own vendor cache folders."""

    from pathlib import Path

    root = Path(__file__).absolute().parents[1]
    vendor = root / "vendor"
    # Never fall back to a shared vendor tree or traverse a linked ancestor.
    for ancestor in (root, vendor):
        if ancestor.is_symlink():
            raise RuntimeError(
                "bytecode repair requires real plugin/vendor directories"
            )
    if not vendor.exists():
        return 0
    removed = 0
    pending = [vendor]
    while pending:
        directory = pending.pop()
        with _os.scandir(directory) as iterator:
            entries = list(iterator)
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                pending.append(Path(entry.path))
            elif (
                directory.name == "__pycache__"
                and entry.name.endswith(".pyc")
                and entry.is_file(follow_symlinks=False)
                and entry.stat(follow_symlinks=False).st_nlink == 1
            ):
                Path(entry.path).unlink()
                removed += 1
    return removed


if __name__ == "__main__":
    import argparse
    import logging

    parser = argparse.ArgumentParser(description="Safely clean own vendor bytecode.")
    parser.add_argument("--repair", action="store_true", required=True)
    parser.parse_args()
    activate_implementation_boundary()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Removed %s vendor cache .pyc files", repair_vendor_bytecode())
