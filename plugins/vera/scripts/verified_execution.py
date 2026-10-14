"""Verify installed package bytes and materialize hardlinks outside host caches.

The host-installed package remains the trust anchor; its embedded digest index
detects drift, not publisher authenticity. No case files or network are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

__all__ = [
    "ASSURED_MODULES",
    "InstallationContentMismatch",
    "MANIFEST",
    "prepare_execution_root",
    "report_preparation_failure",
    "main",
]

ASSURED_MODULES = frozenset(
    {
        "journal-bank-reconciliation",
        "open-item-reconciliation",
        "journal-sampling",
        "report-builder",
        "check-entries",
        "concordato-plan-review",
    }
)
MANIFEST = "execution-files.json"
LOGGER = logging.getLogger(__name__)


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        # CPython 3.12 Windows lstat uses creation time for ctime, while
        # fstat uses change time. Birthtime is comparable across both APIs.
        (
            getattr(info, "st_birthtime_ns", info.st_ctime_ns)
            if os.name == "nt"
            else info.st_ctime_ns
        ),
        info.st_nlink,
    )


def _read_regular(path: Path) -> tuple[bytes, int]:
    """Read a stable regular file, permitting hardlinks only as copy sources."""

    _real_ancestors(path.parent)
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or _reparse_point(before)
        or before.st_nlink < 1
    ):
        raise ValueError(f"Non-regular installation file: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if _identity(before) != _identity(opened):
            raise ValueError(f"Installation file changed before read: {path}")
        data = handle.read()
        after = os.fstat(handle.fileno())
        if (
            _identity(before) != _identity(after)
            or opened.st_ctime_ns != after.st_ctime_ns
            or _identity(before) != _identity(path.lstat())
        ):
            raise ValueError(f"Installation file changed during read: {path}")
    _real_ancestors(path.parent)
    return data, before.st_nlink


def _reparse_point(info: os.stat_result) -> bool:
    return bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _real_ancestors(root: Path) -> None:
    for path in (root, *root.parents):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or _reparse_point(info):
            raise ValueError(f"Installation ancestor must be a real directory: {path}")


def _validate_host_use_markers(directory: Path) -> None:
    """Accept only numeric regular host leases; none become executable inputs.

    Exact filesystem rules distinguish the reported host bookkeeping from code
    without allowing an arbitrary ignored subtree in the integrity boundary.
    """

    for marker in directory.iterdir():
        info = marker.lstat()
        if (
            not marker.name.isascii()
            or not marker.name.isdecimal()
            or not stat.S_ISREG(info.st_mode)
            or _reparse_point(info)
            or info.st_nlink != 1
        ):
            raise ValueError(f"Invalid host use marker: {marker}")


def _inventory(root: Path) -> tuple[dict[str, Path], set[str]]:
    """Reject unexpected filesystem types before reading any installed code."""

    files: dict[str, Path] = {}
    directories: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if _reparse_point(info):
                raise ValueError(f"Reparse installation entry: {path}")
            if stat.S_ISDIR(info.st_mode):
                if relative == ".in_use":
                    _validate_host_use_markers(path)
                    continue
                if path.name != "__pycache__":
                    directories.add(relative)
                    pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                if path.suffix in {".pyc", ".pyo"}:
                    if info.st_nlink != 1:
                        raise ValueError(
                            f"Hardlinked bytecode is not repairable: {path}"
                        )
                    continue
                files[relative] = path
            else:
                raise ValueError(f"Non-regular installation entry: {path}")
    return files, directories


def _manifest(data: bytes) -> dict[str, str]:
    payload = json.loads(data)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("files"), dict)
    ):
        raise ValueError("Invalid execution digest index")
    files = payload["files"]
    for name, digest in files.items():
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or PureWindowsPath(name).drive
            or path.as_posix() != name
            or name == MANIFEST
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("Invalid execution digest index entry")
    return files


def _validate_module(root: Path, module: str) -> None:
    """Run the unchanged module boundary only after package-byte verification."""

    component = root / "modules" / module
    bootstrap = component / "scripts" / "implementation_bootstrap.py"
    code = (
        "import runpy, sys; "
        "namespace = runpy.run_path(sys.argv[1]); "
        "namespace['validate_implementation_tree'](sys.argv[2])"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, str(bootstrap), str(component)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"Module integrity check failed: {result.stderr.strip()}")


def prepare_execution_root(root: Path, module: str | None) -> Path:
    """Return verified code; recover only authentic-to-index hardlinked bytes.

    Fixed digests and exact file inventory are mechanical execution controls.
    Recovery never weakens a module's own single-link validation.
    """

    if module not in ASSURED_MODULES:
        return root
    root = root.absolute()
    # Repository component sources use sibling roots, not installed modules.
    if (
        not (root / "modules").exists()
        and root.parent.name == "plugins"
        and (root.parent.parent / ".git").exists()
        and (root.parent / module).is_dir()
    ):
        return root
    _real_ancestors(root)
    observed, directories = _inventory(root)
    if MANIFEST not in observed:
        raise ValueError("Installed Vera has no execution digest index; update Vera.")
    manifest_bytes, manifest_links = _read_regular(observed.pop(MANIFEST))
    expected = _manifest(manifest_bytes)
    expected_directories = {
        parent.as_posix()
        for name in expected
        for parent in PurePosixPath(name).parents
        if parent != PurePosixPath(".")
    }
    if directories != expected_directories:
        raise ValueError("Installation directories do not match the digest index")
    if observed.keys() != expected.keys():
        missing = sorted(expected.keys() - observed.keys())
        extra = sorted(observed.keys() - expected.keys())
        raise ValueError(
            f"Installation inventory mismatch; missing={missing}, extra={extra}"
        )
    contents = {}
    hardlinks = manifest_links > 1
    for name, digest in expected.items():
        data, links = _read_regular(observed[name])
        if hashlib.sha256(data).hexdigest() != digest:
            raise InstallationContentMismatch(
                name, digest, hashlib.sha256(data).hexdigest()
            )
        contents[name] = data
        hardlinks = hardlinks or links > 1
    if not hardlinks:
        _validate_module(root, module)
        return root

    # mkdtemp creates a fresh private directory. Never mutate the installed tree
    # or an alias, never reuse an unverified cache, never copy client material.
    private = Path(
        tempfile.mkdtemp(
            prefix="vera-verified-", dir=Path(tempfile.gettempdir()).resolve()
        )
    )
    try:
        for name, data in {**contents, MANIFEST: manifest_bytes}.items():
            path = private / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(data)
            installed, links = _read_regular(path)
            if installed != data or links != 1:
                raise ValueError(f"Private execution copy failed verification: {name}")
        _validate_module(private, module)
    except (OSError, ValueError):
        shutil.rmtree(private)
        raise
    LOGGER.warning("Vera ha preparato una copia privata verificata del codice.")
    return private


class InstallationContentMismatch(ValueError):
    """Carry exact build-relative evidence, never client content or file excerpts."""

    def __init__(self, name: str, expected: str, observed: str) -> None:
        self.name = name
        self.expected = expected
        self.observed = observed
        super().__init__(f"Installation content mismatch: {name}")


def report_preparation_failure(
    root: Path, module: str | None, error: Exception
) -> None:
    """Report through independently index-verified code while keeping work blocked.

    Exact byte checks are mechanical trust controls, not a semantic classifier.
    The reporter uses only stdlib; snapshot it and product metadata before loading
    so altered workflow code and host-cache aliases never execute for telemetry.
    """
    try:
        manifest, _ = _read_regular(root / MANIFEST)
        expected = _manifest(manifest)
        metadata = next(
            name
            for name in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json")
            if name in expected
        )
        contents = {}
        for name in (
            "scripts/verified_execution.py",
            "scripts/operational_incidents.py",
            metadata,
        ):
            data, _ = _read_regular(root / name)
            if hashlib.sha256(data).hexdigest() != expected[name]:
                raise ValueError(
                    "Incident reporting component failed byte verification"
                )
            contents[name] = data
        # Detect an index replacement during the independent verification too.
        if _read_regular(root / MANIFEST)[0] != manifest:
            raise ValueError("Incident reporting index changed during verification")
        detail = "Installed Vera failed its installation preparation check."
        if isinstance(error, InstallationContentMismatch):
            detail = (
                f"Installation content mismatch: {error.name}; "
                f"expected SHA-256={error.expected}; observed SHA-256={error.observed}."
            )
        with tempfile.TemporaryDirectory(prefix="vera-incident-verified-") as directory:
            snapshot = Path(directory)
            for name, data in contents.items():
                target = snapshot / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(data)
            # -I excludes the original script directory, cwd and PYTHONPATH:
            # an unindexed module cannot shadow a stdlib reporter dependency.
            program = (
                "import json, runpy, sys; "
                "reporter = runpy.run_path(sys.argv[1]); "
                "receipt = reporter['report_failure'](**json.load(sys.stdin)); "
                "receipt['outbox_path'] = reporter['local_context']()['outbox_path'] "
                "if receipt['reporting'] in ('queued', 'delivered') else None; "
                "sys.stdout.write(json.dumps(receipt))"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    program,
                    str(snapshot / "scripts/operational_incidents.py"),
                ],
                input=json.dumps(
                    {
                        "workflow": module or "unknown",
                        "stage": "installation-preparation",
                        "message": detail,
                        "error_type": type(error).__name__,
                        "exit_code": 1,
                        "errno": getattr(error, "errno", None),
                    }
                ),
                text=True,
                capture_output=True,
                check=False,
                timeout=45,
            )
            if result.returncode:
                raise ValueError("Verified incident reporting process failed")
            receipt = json.loads(result.stdout)
        LOGGER.error("VERA_INSTALLATION_INCIDENT: %s", json.dumps(receipt))
        if receipt["reporting"] == "delivered":
            return
        # The queued original envelope keeps its stable UUID for remote retries.
    except (
        OSError,
        ValueError,
        KeyError,
        StopIteration,
        sqlite3.Error,
        subprocess.SubprocessError,
    ) as reporting_error:
        LOGGER.error(
            "Incident reporting verification unavailable: %s",
            type(reporting_error).__name__,
        )
    LOGGER.error(
        "VERA_REMOTE_INCIDENT_REQUIRED: workflow=%s stage=installation-preparation error_type=%s. "
        "Use the saved veraIncidents connector automatically. Deliver the exact queued "
        "original envelope when available; otherwise report the observed technical failure "
        "without running unverified plugin code. Verify recorded:true before claiming delivery. "
        "Do not ask the professional to report it or consent again.",
        module or "unknown",
        type(error).__name__,
    )


def main(argv: list[str] | None = None) -> int:
    """Prepare the workflow internally; the professional does not run a terminal."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, choices=sorted(ASSURED_MODULES))
    args = parser.parse_args(argv)
    root = Path(__file__).absolute().parents[1]
    try:
        prepared = prepare_execution_root(root, args.module)
    except (OSError, ValueError) as error:
        LOGGER.error("Preparazione di Vera bloccata: %s", error)
        report_preparation_failure(root, args.module, error)
        return 1
    sys.stdout.write(json.dumps({"execution_root": str(prepared)}) + "\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
