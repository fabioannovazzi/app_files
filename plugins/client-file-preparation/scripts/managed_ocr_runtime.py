#!/usr/bin/env python3
"""Manage the persistent PaddleOCR runtime shared by Clara and Vera."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import json
import os
import subprocess
import sys
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
RUNTIME_ROOT_ENV = "MPARANZA_RUNTIME_ROOT"
_RUNTIME_LEASES = {}

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SetupResult:
    """One managed OCR runtime setup result."""

    status: str
    message: str
    runtime_path: str
    reused: bool
    detail: str = ""


def _manager(requirements_path: Path):
    """Find the owning product without using a client-project dependency path."""
    import importlib.util

    roots = [requirements_path.parent, *requirements_path.parents]
    roots.append(requirements_path.parent.parent / "vera")
    owner = next(
        (root for root in roots if (root / "requirements-shared-core.txt").is_file()),
        None,
    )
    if owner is None:
        raise ValueError(
            "Install the current Vera, Clara or Lucia package to use shared OCR."
        )
    source = owner / "scripts" / "_managed_python_runtime.py"
    spec = importlib.util.spec_from_file_location("mparanza_ocr_manager", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Shared Python runtime manager unavailable")
    manager = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = manager
    spec.loader.exec_module(manager)
    return owner, manager


def requirements_fingerprint(requirements_path: Path) -> str:
    """Fingerprint the product-independent OCR recipe."""
    owner, _ = _manager(requirements_path)
    return hashlib.sha256(
        (owner / "requirements-shared-ocr.txt").read_bytes()
    ).hexdigest()[:16]


def runtime_target(requirements_path: Path) -> Path:
    """Return OCR's site-packages in the sole shared environment."""
    owner, manager = _manager(requirements_path)
    selection = manager.select_runtime(
        owner, requirements=["requirements-shared-ocr.txt"]
    )
    environment = manager.dependency_target(selection)
    return environment / (
        "Lib/site-packages"
        if sys.platform == "win32"
        else "lib/python3.12/site-packages"
    )


def _modules_present(target: Path) -> bool:
    return target.is_dir() and all(
        importlib.machinery.PathFinder.find_spec(module, [str(target)]) is not None
        for module in REQUIRED_MODULES
    )


def _prepend_pythonpath(target: Path) -> None:
    text = str(target)
    if text not in sys.path:
        sys.path.insert(0, text)
    paths = [
        part for part in os.environ.get("PYTHONPATH", "").split(os.pathsep) if part
    ]
    if text not in paths:
        os.environ["PYTHONPATH"] = os.pathsep.join([text, *paths])


def _hold_lease(environment: Path) -> bool:
    """Keep externally activated native OCR packages unchanged until process exit."""
    if environment in _RUNTIME_LEASES:
        return True
    lock = environment.parent / "runtime.lock"
    if lock.is_symlink():
        return False
    try:
        handle = lock.open("rb")
    except OSError:
        return False
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBRLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _RUNTIME_LEASES[environment] = handle
    return True


def activate_ocr_runtime(requirements_path: Path) -> Path | None:
    """Activate OCR only when the shared environment has a valid OCR receipt."""
    owner, manager = _manager(requirements_path)
    ready = manager.activate_runtime(
        owner, requirements=["requirements-shared-ocr.txt"]
    )
    target = runtime_target(requirements_path)
    if ready is None or not _modules_present(target):
        return None
    if not _hold_lease(ready):
        return None
    # Recheck after acquiring the lease to close the setup/activation race.
    if (
        manager.activate_runtime(owner, requirements=["requirements-shared-ocr.txt"])
        is None
    ):
        _RUNTIME_LEASES.pop(ready).close()
        return None
    _prepend_pythonpath(target)
    return target


def install_ocr_runtime(
    requirements_path: Path, *, runner: Runner = subprocess.run
) -> SetupResult:
    """Enable OCR in the existing shared environment, never a separate one."""
    try:
        owner, manager = _manager(requirements_path)
        reused = (
            manager.activate_runtime(
                owner, requirements=["requirements-shared-ocr.txt"]
            )
            is not None
        )
        ready, _, detail = manager.ensure_runtime(
            owner, requirements=["requirements-shared-ocr.txt"], runner=runner
        )
        target = runtime_target(requirements_path)
        ready = ready and _modules_present(target)
        if ready:
            ready = activate_ocr_runtime(requirements_path) is not None
        return SetupResult(
            "ready" if ready else "failed",
            INSTALL_SUCCESS_MESSAGE if ready else INSTALL_FAILURE_MESSAGE,
            str(target),
            reused if ready else False,
            "" if ready else detail,
        )
    except (OSError, ValueError) as error:
        return SetupResult("failed", INSTALL_FAILURE_MESSAGE, "", False, str(error))


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
