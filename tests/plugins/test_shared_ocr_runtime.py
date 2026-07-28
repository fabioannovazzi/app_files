from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
VERA_ENGINE_ROOT = ROOT / "plugins" / "client-file-preparation"
PROMPT = (
    "PaddleOCR is required to read this document. Shall Codex install it now? "
    "The download is about 500 MB."
)


def load_runtime(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def populate_install_target(command: list[str]) -> None:
    target = Path(command[command.index("--target") + 1])
    for module_name in ("PIL", "cv2", "paddleocr", "paddle"):
        module_dir = target / module_name
        module_dir.mkdir(parents=True)
        (module_dir / "__init__.py").write_text("", encoding="utf-8")


def successful_runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
    populate_install_target(command)
    return subprocess.CompletedProcess(command, 0, "", "")


def test_clara_install_is_reused_by_vera(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MPARANZA_SHARED_OCR_RUNTIME", str(tmp_path / "runtime"))
    clara = load_runtime(
        "clara_managed_ocr_runtime",
        CLARA_ROOT / "scripts" / "managed_ocr_runtime.py",
    )
    vera = load_runtime(
        "vera_managed_ocr_runtime",
        VERA_ENGINE_ROOT / "scripts" / "managed_ocr_runtime.py",
    )
    clara_requirements = CLARA_ROOT / "requirements-ocr.txt"
    vera_requirements = VERA_ENGINE_ROOT / "requirements-ocr.txt"
    first = clara.install_ocr_runtime(
        clara_requirements,
        runner=successful_runner,
    )

    def unexpected_runner(
        command: list[str], **_: Any
    ) -> subprocess.CompletedProcess[str]:
        pytest.fail(f"Persistent runtime should be reused, not installed: {command}")

    reused = vera.install_ocr_runtime(
        vera_requirements,
        runner=unexpected_runner,
    )

    assert first.status == "ready"
    assert first.reused is False
    assert reused.status == "ready"
    assert reused.reused is True
    assert first.runtime_path == reused.runtime_path


def test_managed_install_failure_returns_friendly_retry_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MPARANZA_SHARED_OCR_RUNTIME", str(tmp_path / "runtime"))
    runtime = load_runtime(
        "failed_managed_ocr_runtime",
        CLARA_ROOT / "scripts" / "managed_ocr_runtime.py",
    )

    def failed_runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "network unavailable")

    result = runtime.install_ocr_runtime(
        CLARA_ROOT / "requirements-ocr.txt",
        runner=failed_runner,
    )

    assert result.status == "failed"
    assert result.message == (
        "I couldn't install PaddleOCR right now. " "Shall I try the installation again?"
    )
    assert result.detail == "network unavailable"
    assert not Path(result.runtime_path).exists()


def test_status_uses_plain_language_first_use_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MPARANZA_SHARED_OCR_RUNTIME", str(tmp_path / "runtime"))
    runtime = load_runtime(
        "status_managed_ocr_runtime",
        CLARA_ROOT / "scripts" / "managed_ocr_runtime.py",
    )

    return_code = runtime.main(
        [
            "status",
            "--requirements",
            str(CLARA_ROOT / "requirements-ocr.txt"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert return_code == 1
    assert payload["status"] == "requires_install"
    assert payload["message"] == PROMPT
    assert all(
        technical_word not in payload["message"].lower()
        for technical_word in ("pip", "python", "terminal")
    )


def test_clara_and_vera_runtime_sources_are_identical() -> None:
    clara_source = (CLARA_ROOT / "scripts" / "managed_ocr_runtime.py").read_text(
        encoding="utf-8"
    )
    vera_source = (VERA_ENGINE_ROOT / "scripts" / "managed_ocr_runtime.py").read_text(
        encoding="utf-8"
    )

    assert clara_source == vera_source
