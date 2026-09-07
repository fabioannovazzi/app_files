#!/usr/bin/env python3
"""Manage the persistent PaddleOCR runtime shared by Vera workflows."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.metadata
import json
import os
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
    "PaddleOCR is required to read this document. Shall Claude install it now? "
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
RUNTIME_ROOT_ENV = "MPARANZA_RUNTIME_ROOT"
_RUNTIME_LEASES = {}
RUNTIME_DIR_NAME = "paddleocr"
READY_MARKER = ".mparanza-ocr-ready.json"
READY_SCHEMA_VERSION = 2
MODEL_FILES = ("inference.json", "inference.pdiparams")

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SetupResult:
    """One managed setup result suitable for the host orchestration layer."""

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


def _normalize_package_name(value: str) -> str:
    return "-".join(filter(None, value.lower().replace("_", "-").split("-")))


def _locked_requirements(requirements_path: Path) -> dict[str, str]:
    """Return exact package pins; managed runtimes must not resolve version ranges."""

    locked: dict[str, str] = {}
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.count("==") != 1 or any(
            marker in line for marker in (";", "[", "]", "<", ">", "~", ",", "@")
        ):
            raise ValueError(
                "Managed OCR requirements must use exact package==version pins"
            )
        package, version = (part.strip() for part in line.split("==", 1))
        normalized = _normalize_package_name(package)
        if not normalized or not version or normalized in locked:
            raise ValueError("Managed OCR requirements contain an invalid package pin")
        locked[normalized] = version
    if not locked:
        raise ValueError("Managed OCR requirements contain no package pins")
    return locked


def _requirements_digest(requirements_path: Path) -> str:
    locked = _locked_requirements(requirements_path)
    content = "\n".join(f"{name}=={locked[name]}" for name in sorted(locked))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _requirements_fingerprint(requirements_path: Path) -> str:
    return _requirements_digest(requirements_path)[:16]


def _runtime_target(requirements_path: Path) -> Path:
    _locked_requirements(requirements_path)
    return runtime_target(requirements_path)


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
        all(
            (official_models / model / file_name).is_file() for file_name in MODEL_FILES
        )
        for model in OCR_MODEL_NAMES
    )


def _installed_package_versions(target: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions(path=[str(target)]):
        name = distribution.metadata.get("Name")
        if name:
            versions[_normalize_package_name(str(name))] = distribution.version
    return versions


def _package_receipt(target: Path, requirements_path: Path) -> dict[str, str]:
    locked = _locked_requirements(requirements_path)
    installed = _installed_package_versions(target)
    if any(installed.get(name) != version for name, version in locked.items()):
        raise ValueError("Managed OCR package versions do not match the lock")
    # Preserve the complete resolved environment, not only the direct pins, so
    # transitive dependency drift is visible and invalidates later reuse.
    return {name: installed[name] for name in sorted(installed)}


def _file_receipt(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "size_bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _model_receipt(target: Path) -> dict[str, dict[str, dict[str, object]]]:
    official_models = _model_cache(target) / "official_models"
    receipt: dict[str, dict[str, dict[str, object]]] = {}
    for model in OCR_MODEL_NAMES:
        directory = official_models / model
        files = {
            file_name: _file_receipt(directory / file_name) for file_name in MODEL_FILES
        }
        receipt[model] = files
    return receipt


def _runtime_ready(target: Path, requirements_path: Path) -> bool:
    marker = target / READY_MARKER
    if (
        not marker.is_file()
        or not _modules_present(target)
        or not _models_present(target)
    ):
        return False
    try:
        receipt = json.loads(marker.read_text(encoding="utf-8"))
        return (
            receipt.get("schema_version") == READY_SCHEMA_VERSION
            and receipt.get("requirements_sha256")
            == _requirements_digest(requirements_path)
            and receipt.get("packages") == _package_receipt(target, requirements_path)
            and receipt.get("models") == _model_receipt(target)
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


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


def _prefetch_models(target: Path, runner: Runner, python: Path) -> None:
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
        [str(python), "-c", code],
        cwd=target,
        env={**os.environ, "MPARANZA_RUNTIME_INSTALLING": "1"},
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0 or not _models_present(target):
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(detail or "The OCR model download was incomplete")


def activate_ocr_runtime(requirements_path: Path) -> Path | None:
    """Verify the shared packages and XBRL model integrity before activation."""
    source = requirements_path.resolve()
    target = _runtime_target(source)
    owner, manager = _manager(source)
    environment = manager.activate_runtime(
        owner, requirements=["requirements-shared-ocr.txt"]
    )
    if environment is None or not _runtime_ready(target, source):
        return None
    if not _hold_lease(environment):
        return None
    if (
        not _runtime_ready(target, source)
        or manager.activate_runtime(owner, requirements=["requirements-shared-ocr.txt"])
        is None
    ):
        _RUNTIME_LEASES.pop(environment).close()
        return None
    _activate_path(target)
    return target


def install_ocr_runtime(
    requirements_path: Path,
    *,
    runner: Runner = subprocess.run,
    model_runner: Runner = subprocess.run,
) -> SetupResult:
    """Enable shared OCR and retain the XBRL model integrity contract."""
    source = requirements_path.expanduser().resolve()
    target = _runtime_target(source)
    if activate_ocr_runtime(source) is not None:
        return SetupResult("ready", INSTALL_SUCCESS_MESSAGE, str(target), True)
    owner, manager = _manager(source)
    ready, environment, detail = manager.ensure_runtime(
        owner,
        requirements=["requirements-shared-ocr.txt"],
        runner=runner,
    )
    if not ready:
        return SetupResult(
            "failed", INSTALL_FAILURE_MESSAGE, str(target), False, detail
        )
    if (
        Path(sys.prefix).resolve() == environment.resolve()
        or environment in _RUNTIME_LEASES
    ):
        return SetupResult(
            "failed",
            INSTALL_FAILURE_MESSAGE,
            str(target),
            False,
            "Exit running OCR workflows and run model setup from base Python.",
        )
    shared = manager._shared_runtime()
    try:
        with shared._writer(environment.parent / "runtime.lock"):
            (target / READY_MARKER).unlink(missing_ok=True)
            # Only model assets are staged; no second Python environment is created.
            with tempfile.TemporaryDirectory(
                prefix="ocr-models-", dir=environment.parent
            ) as temporary:
                staging = Path(temporary)
                _prefetch_models(
                    staging, model_runner, manager.runtime_python(environment)
                )
                models = _model_receipt(staging)
                receipt = {
                    "schema_version": READY_SCHEMA_VERSION,
                    "requirements_fingerprint": _requirements_fingerprint(source),
                    "requirements_sha256": _requirements_digest(source),
                    "modules": list(REQUIRED_MODULES),
                    "packages": _package_receipt(target, source),
                    "models": models,
                }
                cache = _model_cache(target)
                if cache.is_symlink():
                    raise OSError("OCR model cache cannot be a symlink")
                if cache.exists():
                    cache.replace(staging / "previous-model-cache")
                _model_cache(staging).replace(cache)
                shared._write(target / READY_MARKER, receipt)
    except (OSError, RuntimeError, ValueError, TypeError) as error:
        return SetupResult(
            "failed", INSTALL_FAILURE_MESSAGE, str(target), False, str(error)
        )
    if activate_ocr_runtime(source) is None:
        return SetupResult(
            "failed",
            INSTALL_FAILURE_MESSAGE,
            str(target),
            False,
            "The managed OCR integrity receipt could not be verified.",
        )
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
