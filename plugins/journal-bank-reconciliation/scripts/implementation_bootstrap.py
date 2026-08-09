"""Pre-import execution boundary for assured Journal–Bank commands.

Only interpreter-provided modules are used before the exact plugin and shared
assurance tree is closed. The boundary proves execution/receipt consistency;
it does not authenticate a package publisher, reviewer, or accounting
conclusion.
"""

from __future__ import annotations

import sys as _sys

_sys.dont_write_bytecode = True
_sys.pycache_prefix = (
    r"Z:\__journal_bank_no_bytecode__"
    if _sys.platform == "win32"
    else "/dev/null/journal-bank-reconciliation"
)

import os as _os

__all__ = [
    "CHATGPT_IMPLEMENTATION_CONTRACT",
    "IMPLEMENTATION_CONTRACT",
    "activate_implementation_boundary",
    "implementation_contract",
    "validate_implementation_tree",
]

IMPLEMENTATION_CONTRACT = (
    ("plugin", ".codex-plugin/plugin.json"),
    ("plugin", ".app.json"),
    ("plugin", ".mcp.json"),
    ("plugin", "assets/icon.svg"),
    ("plugin", "assets/journal-bank-review-widget.html"),
    ("plugin", "assets/review-workbench-adapter.json"),
    ("plugin", "mcp/server.cjs"),
    ("plugin", "scripts/apply_review_edits.py"),
    ("plugin", "scripts/check_dependencies.py"),
    ("plugin", "scripts/excel_sanitization.py"),
    ("plugin", "scripts/implementation_bootstrap.py"),
    ("plugin", "scripts/inspect_inputs.py"),
    ("plugin", "scripts/journal_bank_core.py"),
    ("plugin", "scripts/review_session.py"),
    ("plugin", "scripts/run_reconciliation.py"),
    ("plugin", "scripts/semantic_review.py"),
    ("shared_assurance", "__init__.py"),
    ("shared_assurance", "contracts.py"),
    ("shared_assurance", "decisions.py"),
    ("shared_assurance", "envelope.py"),
    ("shared_assurance", "money.py"),
    ("shared_assurance", "relationships.py"),
    ("shared_assurance", "review_output_transaction.cjs"),
    ("shared_assurance", "serialization.py"),
)
CHATGPT_IMPLEMENTATION_CONTRACT = tuple(
    entry
    for entry in IMPLEMENTATION_CONTRACT
    if entry
    not in {
        ("plugin", ".app.json"),
        ("plugin", ".mcp.json"),
        ("plugin", "mcp/server.cjs"),
    }
) + (
    ("plugin", "scripts/review_mcp_server.cjs"),
    ("plugin", "scripts/review_server.py"),
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


def implementation_contract(plugin_root: str) -> tuple[tuple[str, str], ...]:
    """Select the exact mechanically verifiable contract for one host layout."""

    full_paths = (".app.json", ".mcp.json", "mcp/server.cjs")
    projected_paths = (
        "scripts/review_mcp_server.cjs",
        "scripts/review_server.py",
    )
    full_present = any(
        _os.path.lexists(_os.path.join(plugin_root, path)) for path in full_paths
    )
    projected_present = any(
        _os.path.lexists(_os.path.join(plugin_root, path)) for path in projected_paths
    )
    if full_present and projected_present:
        raise RuntimeError("implementation host layouts cannot be mixed")
    if full_present:
        return IMPLEMENTATION_CONTRACT
    if projected_present:
        return CHATGPT_IMPLEMENTATION_CONTRACT
    raise RuntimeError("implementation host layout is not recognized")


def _expected_directories(
    contract: tuple[tuple[str, str], ...],
) -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    for root_id, relative_path in contract:
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
            observed = entry.stat(follow_symlinks=False)
            entry_type = observed.st_mode & _TYPE_MASK
            if entry.is_symlink():
                raise RuntimeError("implementation entries must not be symlinks")
            if entry_type == _DIRECTORY_MODE:
                observed_directories.add((root_id, relative))
                pending.append(entry.path)
                continue
            if entry_type != _FILE_MODE or observed.st_nlink != 1:
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
    contract = implementation_contract(root)
    observed_files: set[tuple[str, str]] = set()
    observed_directories: set[tuple[str, str]] = set()
    for root_id, relative_path in contract:
        if root_id != "plugin" or _os.path.dirname(relative_path):
            continue
        _record_file(
            root_id="plugin",
            root=root,
            path=_os.path.join(root, relative_path),
            observed_files=observed_files,
        )
    scan_roots = [
        ("plugin", _os.path.join(root, ".codex-plugin")),
        ("plugin", _os.path.join(root, "assets")),
        ("plugin", _os.path.join(root, "scripts")),
        ("shared_assurance", shared_root),
    ]
    if contract == IMPLEMENTATION_CONTRACT:
        scan_roots.insert(2, ("plugin", _os.path.join(root, "mcp")))
    for root_id, scan_root in scan_roots:
        _scan_tree(
            root_id=root_id,
            root=roots[root_id],
            scan_root=scan_root,
            observed_files=observed_files,
            observed_directories=observed_directories,
        )
    if observed_files != set(contract):
        raise RuntimeError(
            "implementation filesystem does not match the exact "
            f"{len(contract)}-file contract"
        )
    if observed_directories != _expected_directories(contract):
        raise RuntimeError("implementation directories do not match the exact contract")
    return roots


def activate_implementation_boundary() -> dict[str, str]:
    """Disable local bytecode and validate the canonical implementation tree."""

    script_path = _os.path.abspath(__file__)
    plugin_root = _os.path.dirname(_os.path.dirname(script_path))
    return validate_implementation_tree(plugin_root)
