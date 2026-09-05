"""Keep component dependency gates compatible with Vera's Python 3.10 runtime."""

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
)


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize(
    "tree", ["plugins", "plugin_packages/vera/claude/vera/modules"]
)
@pytest.mark.parametrize("version, expected", [((3, 9), 1), ((3, 10), 0), ((3, 11), 0)])
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
    monkeypatch.setattr(
        checker, "sys", SimpleNamespace(version_info=version, stderr=sys.stderr)
    )
    monkeypatch.setattr(checker.importlib.util, "find_spec", lambda name: object())
    if component == "studio-archive":
        monkeypatch.setattr(checker, "_fts5_available", lambda: True)

    result = checker.main([])

    assert result == expected
    if expected:
        assert "Python 3.10 or newer" in caplog.text + capsys.readouterr().err
