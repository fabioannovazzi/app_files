"""Require the single supported Python 3.12 workflow runtime."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = (
    "browser-automation",
    "studio-archive",
    "bilancio-xbrl-it",
    "registro-imprese-sari",
    "prompt-optimizer",
    "new-client",
    "bandi-agevolazioni",
    "previdenza-inps",
    "deep-research-validator",
)


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize(
    "tree", ["plugins", "plugin_packages/vera/claude/vera/modules"]
)
@pytest.mark.parametrize(
    "version, expected", [((3, 10), 1), ((3, 11), 1), ((3, 12), 0), ((3, 13), 1)]
)
def test_dependency_gate_accepts_managed_runtime(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    component: str,
    tree: str,
    version: tuple[int, int],
    expected: int,
) -> None:
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    path = ROOT / tree / component / "scripts" / "check_dependencies.py"
    spec = importlib.util.spec_from_file_location("component_dependency_gate", path)
    assert spec and spec.loader
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(sys, "argv", [str(path)])
    monkeypatch.setattr(
        checker, "sys", SimpleNamespace(**{**vars(sys), "version_info": version})
    )
    if hasattr(checker, "importlib"):
        monkeypatch.setattr(checker.importlib.util, "find_spec", lambda name: object())
    if component == "studio-archive":
        monkeypatch.setattr(checker, "_fts5_available", lambda: True)

    result = checker.main()

    assert result == expected
    if expected:
        captured = capsys.readouterr()
        assert "Python 3.12" in caplog.text + captured.err + captured.out
