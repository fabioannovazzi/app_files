"""Exercise the installed Vera verifier against final release ZIP bytes."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

__all__ = ["verify_vera_execution_zip"]

ASSURED_MODULES = (
    "check-entries",
    "concordato-plan-review",
    "journal-bank-reconciliation",
    "journal-sampling",
    "open-item-reconciliation",
    "report-builder",
)


def _verify_release_references(archive_path: Path, root: Path, prefix: str) -> None:
    """Compare exact course bytes and stored ZIP times, not extraction times."""
    index = json.loads((root / "execution-files.json").read_text())["files"]
    with ZipFile(archive_path) as archive:
        sealed_at = archive.getinfo(f"{prefix}execution-files.json").date_time
        for name in index:
            if archive.getinfo(f"{prefix}{name}").date_time > sealed_at:
                raise ValueError(
                    f"execution-files.json is older than indexed file: {name}"
                )
    for course in sorted(root.glob("assets/courses/*/course.json")):
        for source in json.loads(course.read_text())["sources"]:
            path = (root / source["path"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError(f"Unsafe course source path: {source['path']}")
            if not path.is_file():
                raise ValueError(f"Missing course source: {source['path']}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError(
                    f"Course source hash mismatch: {course.relative_to(root)}: "
                    f"{source['path']}"
                )


def verify_vera_execution_zip(archive_path: Path, plugin_root: str) -> None:
    """Reject releases that the real installation boundary cannot execute.

    Exact byte, timestamp and exit-code checks are mechanically verifiable.
    Preflight through the packaged API before exercising each real CLI, so
    known integrity failures cannot generate synthetic customer incidents.
    """
    with tempfile.TemporaryDirectory(prefix="vera-release-integrity-") as temporary:
        staging = Path(temporary).resolve()
        with ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                destination = (staging / entry.filename).resolve()
                if not destination.is_relative_to(staging):
                    raise ValueError(f"Unsafe ZIP entry: {entry.filename}")
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError(f"Symlink in ZIP: {entry.filename}")
            archive.extractall(staging)
        root = (staging / plugin_root).resolve()
        if not root.is_relative_to(staging):
            raise ValueError(f"Unsafe plugin root: {plugin_root}")
        verifier = root / "scripts/verified_execution.py"
        if not verifier.is_file():
            raise ValueError("Vera release has no installed execution verifier")
        code = (
            "import pathlib, runpy, sys; "
            "namespace = runpy.run_path(sys.argv[1]); "
            "root = pathlib.Path(sys.argv[2]); "
            "[namespace['prepare_execution_root'](root, module) "
            "for module in sorted(namespace['ASSURED_MODULES'])]"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", code, str(verifier), str(root)],
                cwd=staging,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError(
                "Vera packaged execution verification timed out"
            ) from error
        if result.returncode:
            raise ValueError(
                "Vera packaged execution verification failed: " + result.stderr.strip()
            )
        prefix = "" if root == staging else root.relative_to(staging).as_posix() + "/"
        _verify_release_references(archive_path, root, prefix)
        # Keep unexpected CLI incident reports local to this build fixture.
        environment = {
            **os.environ,
            "MPARANZA_INCIDENT_STATE_DIR": str(staging / "incidents"),
            "https_proxy": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "no_proxy": "",
            "NO_PROXY": "",
        }
        for module in ASSURED_MODULES:
            try:
                result = subprocess.run(
                    [sys.executable, "-I", "-B", str(verifier), "--module", module],
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                )
            except subprocess.TimeoutExpired as error:
                raise ValueError(
                    f"Vera packaged CLI verification timed out: {module}"
                ) from error
            if result.returncode:
                raise ValueError(
                    f"Vera packaged CLI verification failed: {module} "
                    f"(exit {result.returncode}): {result.stderr.strip()}"
                )
