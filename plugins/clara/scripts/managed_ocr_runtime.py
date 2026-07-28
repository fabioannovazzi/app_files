#!/usr/bin/env python3
"""Manage the persistent PaddleOCR runtime shared by Clara and Vera."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

__all__ = [
    "INSTALL_FAILURE_MESSAGE",
    "INSTALL_SUCCESS_MESSAGE",
    "OCR_SETUP_PROMPT",
    "SetupResult",
    "activate_ocr_runtime",
    "install_ocr_runtime",
    "main",
    "requirements_fingerprint",
    "runtime_target",
]

OCR_SETUP_PROMPT = (
    "PaddleOCR is required to read this document. Shall Codex install it now? "
    "The download is about 500 MB."
)
INSTALL_SUCCESS_MESSAGE = "PaddleOCR is ready. Retrying the document now."
INSTALL_FAILURE_MESSAGE = (
    "I couldn't install PaddleOCR right now. Shall I try the installation again?"
)
REQUIRED_MODULES = ("PIL", "cv2", "paddleocr", "paddle")
RUNTIME_ROOT_ENV = "MPARANZA_SHARED_OCR_RUNTIME"
RUNTIME_DIR_NAME = "paddleocr"
READY_MARKER = ".mparanza-ocr-ready.json"

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SetupResult:
    """One managed OCR runtime setup result."""

    status: str
    message: str
    runtime_path: str
    reused: bool
    detail: str = ""


def _runtime_root() -> Path:
    configured = os.environ.get(RUNTIME_ROOT_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (
        Path.home() / ".cache" / "mparanza" / "shared-runtimes" / RUNTIME_DIR_NAME
    ).resolve()


def requirements_fingerprint(requirements_path: Path) -> str:
    """Return a stable fingerprint for the declared shared OCR packages."""

    normalized = sorted(
        line.split("#", 1)[0].strip().lower()
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    )
    digest = hashlib.sha256("\n".join(normalized).encode("utf-8"))
    return digest.hexdigest()[:16]


def runtime_target(requirements_path: Path) -> Path:
    """Return the persistent runtime used by both Clara and Vera."""

    return _runtime_root() / requirements_fingerprint(requirements_path)


def _modules_present(target: Path) -> bool:
    """Check exact top-level modules in the managed target.

    This deterministic presence check is appropriate because package
    installation is a mechanical filesystem contract, not semantic judgment.
    """

    if not target.is_dir():
        return False
    return all(
        importlib.machinery.PathFinder.find_spec(module, [str(target)]) is not None
        for module in REQUIRED_MODULES
    )


def _runtime_ready(target: Path) -> bool:
    return (target / READY_MARKER).is_file() and _modules_present(target)


def _prepend_pythonpath(target: Path) -> None:
    target_text = str(target)
    if target_text not in sys.path:
        sys.path.insert(0, target_text)
    existing = os.environ.get("PYTHONPATH", "")
    paths = [part for part in existing.split(os.pathsep) if part]
    if target_text not in paths:
        os.environ["PYTHONPATH"] = os.pathsep.join([target_text, *paths])


def activate_ocr_runtime(requirements_path: Path) -> Path | None:
    """Activate the persistent shared runtime when it is already ready."""

    target = runtime_target(requirements_path)
    if not _runtime_ready(target):
        return None
    _prepend_pythonpath(target)
    return target


def _installation_command(requirements_path: Path, target: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--target",
        str(target),
        "-r",
        str(requirements_path),
    ]


def install_ocr_runtime(
    requirements_path: Path,
    *,
    runner: Runner = subprocess.run,
) -> SetupResult:
    """Install PaddleOCR once into the shared persistent runtime."""

    requirements_path = requirements_path.expanduser().resolve()
    target = runtime_target(requirements_path)
    if _runtime_ready(target):
        _prepend_pythonpath(target)
        return SetupResult(
            status="ready",
            message=INSTALL_SUCCESS_MESSAGE,
            runtime_path=str(target),
            reused=True,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent)
    ).resolve()
    completed = runner(
        _installation_command(requirements_path, temporary),
        cwd=requirements_path.parent,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        shutil.rmtree(temporary)
        detail = (completed.stderr or completed.stdout).strip()
        return SetupResult(
            status="failed",
            message=INSTALL_FAILURE_MESSAGE,
            runtime_path=str(target),
            reused=False,
            detail=detail or "The managed installer returned an error.",
        )
    if not _modules_present(temporary):
        shutil.rmtree(temporary)
        return SetupResult(
            status="failed",
            message=INSTALL_FAILURE_MESSAGE,
            runtime_path=str(target),
            reused=False,
            detail="The downloaded runtime did not contain every required module.",
        )

    marker = {
        "requirements_fingerprint": requirements_fingerprint(requirements_path),
        "modules": list(REQUIRED_MODULES),
    }
    (temporary / READY_MARKER).write_text(
        json.dumps(marker, indent=2) + "\n",
        encoding="utf-8",
    )
    if target.exists():
        shutil.rmtree(target)
    temporary.replace(target)
    _prepend_pythonpath(target)
    return SetupResult(
        status="ready",
        message=INSTALL_SUCCESS_MESSAGE,
        runtime_path=str(target),
        reused=False,
    )


def _requirements_path(value: Path | None) -> Path:
    return (
        value.expanduser().resolve()
        if value is not None
        else Path(__file__).resolve().parents[1] / "requirements-ocr.txt"
    )


def main(argv: list[str] | None = None) -> int:
    """Report or install the shared OCR runtime using a machine-readable result."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "install"))
    parser.add_argument("--requirements", type=Path)
    args = parser.parse_args(argv)
    requirements_path = _requirements_path(args.requirements)

    if args.action == "status":
        target = activate_ocr_runtime(requirements_path)
        if target is None:
            result = SetupResult(
                status="requires_install",
                message=OCR_SETUP_PROMPT,
                runtime_path=str(runtime_target(requirements_path)),
                reused=False,
            )
            print(json.dumps(asdict(result)))
            return 1
        result = SetupResult(
            status="ready",
            message=INSTALL_SUCCESS_MESSAGE,
            runtime_path=str(target),
            reused=True,
        )
        print(json.dumps(asdict(result)))
        return 0

    result = install_ocr_runtime(requirements_path)
    print(json.dumps(asdict(result)))
    return 0 if result.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
