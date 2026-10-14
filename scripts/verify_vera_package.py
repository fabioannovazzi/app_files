"""Exercise the installed Vera verifier against final release ZIP bytes."""

from __future__ import annotations

import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

__all__ = ["verify_vera_execution_zip"]


def verify_vera_execution_zip(archive_path: Path, plugin_root: str) -> None:
    """Reject releases that the real installation boundary cannot execute.

    Exact byte/inventory checks are mechanically verifiable. Call the packaged
    preparation API in isolation, without CLI incident reporting or client data.
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
