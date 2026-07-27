"""Pre-import implementation boundary for Audit Reconciliation.

This module deliberately uses only ``sys`` and the interpreter-provided
``os`` module until the complete implementation tree has been inspected.
Local bytecode is disabled before that inspection, so an unreceipted cache
entry cannot execute while the validator is still starting.
"""

from __future__ import annotations

import sys as _sys

_sys.dont_write_bytecode = True
_sys.pycache_prefix = (
    r"Z:\__audit_reconciliation_no_bytecode__"
    if _sys.platform == "win32"
    else "/dev/null/audit-reconciliation"
)

import os as _os

__all__ = [
    "IMPLEMENTATION_CONTRACT",
    "activate_implementation_boundary",
    "validate_implementation_tree",
]

IMPLEMENTATION_CONTRACT = (
    ("plugin", "assets/audit-reconciliation-review-widget.html"),
    ("plugin", "assets/icon.svg"),
    ("plugin", "assets/review-workbench-adapter.json"),
    ("plugin", "mcp/server.cjs"),
    ("plugin", "scripts/audit_assurance.py"),
    ("plugin", "scripts/build_missing_evidence_requests.py"),
    ("plugin", "scripts/build_review_sample.py"),
    ("plugin", "scripts/check_dependencies.py"),
    ("plugin", "scripts/implementation_bootstrap.py"),
    ("plugin", "scripts/raw_input_runner.py"),
    ("plugin", "scripts/reconciliation_workflow.py"),
    ("plugin", "scripts/retained_sources/accountant_report.source"),
    ("plugin", "scripts/retained_sources/locale_support.source"),
    ("plugin", "scripts/retained_sources/reconciliation_helpers.source"),
    ("plugin", "scripts/retained_sources/review_session.source"),
    ("plugin", "scripts/retained_sources/workpaper_outputs.source"),
    ("plugin", "scripts/review_server.py"),
    ("shared_assurance", "__init__.py"),
    ("shared_assurance", "contracts.py"),
    ("shared_assurance", "decisions.py"),
    ("shared_assurance", "envelope.py"),
    ("shared_assurance", "money.py"),
    ("shared_assurance", "relationships.py"),
    ("shared_assurance", "review_output_transaction.cjs"),
    ("shared_assurance", "serialization.py"),
)

_RETAINED_MODULES = (
    ("locale_support", "scripts/retained_sources/locale_support.source"),
    (
        "reconciliation_helpers",
        "scripts/retained_sources/reconciliation_helpers.source",
    ),
    ("accountant_report", "scripts/retained_sources/accountant_report.source"),
    ("review_session", "scripts/retained_sources/review_session.source"),
    ("workpaper_outputs", "scripts/retained_sources/workpaper_outputs.source"),
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
                raise RuntimeError(
                    "implementation entries must be ordinary and must not be symlinks"
                )
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
    """Reject every implementation entry outside the exact ordered contract."""

    root = _os.path.abspath(plugin_root)
    shared_root = (
        _os.path.abspath(shared_assurance_root)
        if shared_assurance_root is not None
        else _shared_assurance_root(root)
    )
    roots = {"plugin": root, "shared_assurance": shared_root}
    observed_files: set[tuple[str, str]] = set()
    observed_directories: set[tuple[str, str]] = set()
    for root_id, scan_root in (
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
            "implementation filesystem does not match the exact 25-file contract"
        )
    if observed_directories != _expected_directories():
        raise RuntimeError("implementation directories do not match the exact contract")
    return roots


def _read_stable_regular_file(path: str) -> bytes:
    """Read one ordinary single-link file without following a replacement link."""

    before = _os.lstat(path)
    if before.st_mode & _TYPE_MASK != _FILE_MODE or before.st_nlink != 1:
        raise RuntimeError(
            "retained implementation source must be an ordinary single-link file"
        )
    descriptor = _os.open(
        path,
        _os.O_RDONLY | getattr(_os, "O_NOFOLLOW", 0),
    )
    try:
        opened = _os.fstat(descriptor)
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_nlink,
        )
        if identity != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_nlink,
        ):
            raise RuntimeError("retained implementation source changed before read")
        with _os.fdopen(descriptor, "rb", closefd=False) as handle:
            source = handle.read()
        after = _os.fstat(descriptor)
        if (
            identity
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_nlink,
            )
            or len(source) != after.st_size
        ):
            raise RuntimeError("retained implementation source changed during read")
        return source
    finally:
        _os.close(descriptor)


def _load_retained_module(
    plugin_root: str,
    module_name: str,
    relative_path: str,
) -> None:
    """Execute retained source only after the enclosing tree was validated."""

    retained_path = _os.path.join(plugin_root, *relative_path.split("/"))
    source = _read_stable_regular_file(retained_path)
    logical_path = _os.path.join(plugin_root, "scripts", f"{module_name}.py")
    module = type(_sys)(module_name)
    module.__dict__.update(
        {
            "__file__": logical_path,
            "__package__": "",
            "__loader__": None,
            "__spec__": None,
            "__cached__": None,
            "_AUDIT_RECONCILIATION_RETAINED_SOURCE": relative_path,
        }
    )
    _sys.modules[module_name] = module
    loaded = False
    try:
        # These are exact stable bytes from the validated implementation contract.
        exec(  # nosec B102
            compile(source, logical_path, "exec"),
            module.__dict__,
        )
        loaded = True
    finally:
        if not loaded:
            _sys.modules.pop(module_name, None)


def activate_implementation_boundary(
    retained_module_names: tuple[str, ...] | None = None,
) -> dict[str, str]:
    """Validate the tree, then load retained modules from exact stable bytes."""

    script_path = _os.path.abspath(__file__)
    plugin_root = _os.path.dirname(_os.path.dirname(script_path))
    roots = validate_implementation_tree(plugin_root)
    retained_by_name = dict(_RETAINED_MODULES)
    selected_names = (
        tuple(retained_by_name)
        if retained_module_names is None
        else retained_module_names
    )
    if len(selected_names) != len(set(selected_names)) or any(
        name not in retained_by_name for name in selected_names
    ):
        raise RuntimeError("retained implementation module selection is invalid")
    for module_name in selected_names:
        relative_path = retained_by_name[module_name]
        _load_retained_module(plugin_root, module_name, relative_path)
    return roots
