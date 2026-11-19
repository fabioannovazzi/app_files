from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.plugins.test_single_shared_runtime import backend


@pytest.mark.parametrize("exit_code", [0, 1])
@pytest.mark.parametrize(
    "settings", [None, {"delivery": "local-only", "recovery_active": True}]
)
def test_base_handoff_releases_only_the_launcher_lease_and_propagates_result(
    tmp_path, monkeypatch, exit_code, settings
):
    module = backend()
    root = tmp_path / "product"
    script = root / "scripts/check_dependencies.py"
    script.parent.mkdir(parents=True)
    script.touch()
    (root / "requirements-shared-core.txt").touch()
    target = tmp_path / "runtime/venv"
    base = tmp_path / "base-python"
    base.touch()
    lease = (tmp_path / "lease").open("w")
    monkeypatch.setattr(module, "target", lambda root: target)
    monkeypatch.setattr(
        module,
        "sys",
        SimpleNamespace(
            prefix=str(target),
            executable=str(target / "bin/python"),
            _base_executable=str(base),
            modules={
                "_mparanza_runtime_guard": SimpleNamespace(_mpr_lease=lease),
                "operational_incidents": SimpleNamespace(_SETTINGS=settings),
            },
        ),
    )
    calls = []

    def run(command, **kwargs):
        assert lease.closed
        assert module.INSTALLING not in kwargs["env"]
        calls.append(command)
        return subprocess.CompletedProcess(command, exit_code)

    monkeypatch.setattr(module.subprocess, "run", run)

    result = module.reenter_base(script, ["--module", "studio-archive"])

    assert result == exit_code
    if settings:
        assert calls[0][4] == "-c"
        assert json.loads(calls[0][7]) == settings
        assert calls[0][8:] == ["--module", "studio-archive"]
        return
    assert calls == [
        [str(base), "-X", "utf8", "-s", str(script), "--module", "studio-archive"]
    ]
