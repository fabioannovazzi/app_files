#!/usr/bin/env python3
"""Manage the persistent PaddleOCR runtime shared by Vera workflows."""

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
]

OCR_SETUP_PROMPT = (
    "PaddleOCR is required to read this document. Shall Codex install it now? "
    "The download is about 500 MB."
)
INSTALL_SUCCESS_MESSAGE = "PaddleOCR is ready. Retrying the document now."
INSTALL_FAILURE_MESSAGE = (
    "I couldn't install PaddleOCR right now. Shall I try the installation again?"
)
REQUIRED_MODULES = ("PIL", "cv2", "numpy", "paddleocr", "paddle")
OCR_MODEL_NAMES = (
    "PP-OCRv5_mobile_det",
    "latin_PP-OCRv5_mobile_rec",
    "en_PP-OCRv5_mobile_rec",
)
RUNTIME_ROOT_ENV = "MPARANZA_SHARED_OCR_RUNTIME"
RUNTIME_DIR_NAME = "paddleocr"
READY_MARKER = ".mparanza-ocr-ready.json"

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SetupResult:
    """One managed setup result suitable for the host orchestration layer."""

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


def _requirements_fingerprint(requirements_path: Path) -> str:
    normalized = sorted(
        line.split("#", 1)[0].strip().lower()
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    )
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()[:16]


def _runtime_target(requirements_path: Path) -> Path:
    return _runtime_root() / _requirements_fingerprint(requirements_path)


def _modules_present(target: Path) -> bool:
    """Check a mechanical installation contract without importing OCR engines."""

    return target.is_dir() and all(
        importlib.machinery.PathFinder.find_spec(module, [str(target)]) is not None
        for module in REQUIRED_MODULES
    )


def _model_cache(target: Path) -> Path:
    return target / "model-cache"


def _models_present(target: Path) -> bool:
    official_models = _model_cache(target) / "official_models"
    return all(
        (official_models / model / "inference.json").is_file()
        and (official_models / model / "inference.pdiparams").is_file()
        for model in OCR_MODEL_NAMES
    )


def _runtime_ready(target: Path) -> bool:
    return (
        (target / READY_MARKER).is_file()
        and _modules_present(target)
        and _models_present(target)
    )


def _activate_path(target: Path) -> None:
    target_text = str(target)
    if target_text not in sys.path:
        sys.path.insert(0, target_text)
    existing = [
        part for part in os.environ.get("PYTHONPATH", "").split(os.pathsep) if part
    ]
    if target_text not in existing:
        os.environ["PYTHONPATH"] = os.pathsep.join([target_text, *existing])
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(_model_cache(target))


def _prefetch_models(target: Path, runner: Runner) -> None:
    """Download the declared public OCR models inside the approved install step."""

    _activate_path(target)
    code = (
        "from paddleocr import PaddleOCR\n"
        f"models = {OCR_MODEL_NAMES[1:]!r}\n"
        "for model in models:\n"
        "    PaddleOCR(text_detection_model_name='PP-OCRv5_mobile_det', "
        "text_recognition_model_name=model, use_doc_orientation_classify=False, "
        "use_doc_unwarping=False, use_textline_orientation=False, "
        "enable_mkldnn=False)\n"
    )
    completed = runner(
        [sys.executable, "-c", code],
        cwd=target,
        env=dict(os.environ),
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0 or not _models_present(target):
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(detail or "The OCR model download was incomplete")


def activate_ocr_runtime(requirements_path: Path) -> Path | None:
    """Activate the exact managed runtime only when its receipt is complete."""

    target = _runtime_target(requirements_path.resolve())
    if not _runtime_ready(target):
        return None
    _activate_path(target)
    return target


def install_ocr_runtime(
    requirements_path: Path,
    *,
    runner: Runner = subprocess.run,
    model_runner: Runner = subprocess.run,
) -> SetupResult:
    """Install optional OCR dependencies after the user's explicit approval."""

    source = requirements_path.expanduser().resolve()
    target = _runtime_target(source)
    if _runtime_ready(target):
        _activate_path(target)
        return SetupResult("ready", INSTALL_SUCCESS_MESSAGE, str(target), True)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent)
    ).resolve()
    completed = runner(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--target",
            str(temporary),
            "-r",
            str(source),
        ],
        cwd=source.parent,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0 or not _modules_present(temporary):
        shutil.rmtree(temporary)
        detail = (completed.stderr or completed.stdout).strip()
        return SetupResult(
            "failed",
            INSTALL_FAILURE_MESSAGE,
            str(target),
            False,
            detail or "The managed OCR installation was incomplete.",
        )
    try:
        _prefetch_models(temporary, model_runner)
    except (OSError, RuntimeError) as exc:
        shutil.rmtree(temporary)
        return SetupResult(
            "failed",
            INSTALL_FAILURE_MESSAGE,
            str(target),
            False,
            f"The declared OCR models could not be prepared: {exc}",
        )
    (temporary / READY_MARKER).write_text(
        json.dumps(
            {
                "requirements_fingerprint": _requirements_fingerprint(source),
                "modules": list(REQUIRED_MODULES),
                "models": list(OCR_MODEL_NAMES),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if target.exists():
        shutil.rmtree(target)
    temporary.replace(target)
    _activate_path(target)
    return SetupResult("ready", INSTALL_SUCCESS_MESSAGE, str(target), False)


def main(argv: list[str] | None = None) -> int:
    """Report or install the optional runtime through one machine-readable CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "install"))
    parser.add_argument("--requirements", type=Path)
    args = parser.parse_args(argv)
    requirements_path = (
        args.requirements.expanduser().resolve()
        if args.requirements is not None
        else Path(__file__).resolve().parents[1] / "requirements-ocr.txt"
    )
    if args.action == "status":
        target = activate_ocr_runtime(requirements_path)
        result = (
            SetupResult("ready", INSTALL_SUCCESS_MESSAGE, str(target), True)
            if target is not None
            else SetupResult(
                "requires_install",
                OCR_SETUP_PROMPT,
                str(_runtime_target(requirements_path)),
                False,
            )
        )
        sys.stdout.write(json.dumps(asdict(result)) + "\n")
        return 0 if result.status == "ready" else 1
    result = install_ocr_runtime(requirements_path)
    sys.stdout.write(json.dumps(asdict(result)) + "\n")
    return 0 if result.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
