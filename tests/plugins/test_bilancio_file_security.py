from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "bilancio-xbrl-it" / "scripts"


def _load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


file_security = _load_module("file_security")


def test_command_scanner_appends_file_as_one_argument(tmp_path: Path) -> None:
    source = tmp_path / "source with spaces.csv"
    source.write_text("safe", encoding="utf-8")
    command = json.dumps(
        [sys.executable, "-c", "import sys; assert len(sys.argv) == 2"]
    )
    scanner = file_security.scanner_from_json(
        command,
        engine="test-engine",
        signature_version="sig-1",
    )

    verdict = scanner(source)

    assert verdict == {
        "status": "CLEAN",
        "engine": "test-engine",
        "signature_version": "sig-1",
    }


def test_command_scanner_rejects_nonzero_verdict(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("unsafe", encoding="utf-8")
    scanner = file_security.scanner_from_json(
        json.dumps([sys.executable, "-c", "raise SystemExit(1)"]),
        engine="test-engine",
        signature_version="sig-1",
    )

    with pytest.raises(ValueError, match="rejected the file"):
        scanner(source)


@pytest.mark.parametrize(
    "raw_command",
    [json.dumps("scanner --flag"), json.dumps(["scanner", 1]), "not-json"],
)
def test_scanner_configuration_rejects_unsafe_shapes(raw_command: str) -> None:
    with pytest.raises((ValueError, json.JSONDecodeError)):
        file_security.scanner_from_json(
            raw_command,
            engine="test-engine",
            signature_version="sig-1",
        )
