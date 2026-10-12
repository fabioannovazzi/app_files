from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("exit_code", [0, 1])
def test_dependency_check_reenters_base_interpreter_and_propagates_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
) -> None:
    scripts = ROOT / "plugins/vera/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "vera_dependency_reentry", scripts / "check_dependencies.py"
    )
    assert spec and spec.loader
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    root = tmp_path / "vera"
    component = root / "modules/journal-sampling/scripts"
    component.mkdir(parents=True)
    (component / "check_dependencies.py").touch()
    base = tmp_path / "base-python"
    base.touch()
    monkeypatch.setattr(checker, "PLUGIN_ROOT", root)
    monkeypatch.setattr(checker, "COMPONENTS", ("journal-sampling",))
    monkeypatch.setattr(checker, "prepare_execution_root", lambda *args: root)
    monkeypatch.setattr(
        checker,
        "ensure_runtime",
        lambda *args, **kwargs: (
            False,
            tmp_path,
            "Shared runtime update requires the base Python interpreter. Exit this workflow",
        ),
    )
    monkeypatch.setattr(checker.sys, "_base_executable", str(base))
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, exit_code)

    monkeypatch.setattr(checker.subprocess, "run", run)
    result = checker.main(["--module", "journal-sampling"])

    assert result == exit_code
    assert calls == [
        [
            str(base),
            str(root / "scripts/check_dependencies.py"),
            "--module",
            "journal-sampling",
        ]
    ]
