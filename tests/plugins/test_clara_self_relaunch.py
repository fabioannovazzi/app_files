"""The direct CLI launcher must not trust an ambient venv or hook marker."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]


def launcher(monkeypatch, tmp_path):
    namespace = runpy.run_path(str(ROOT / "plugins/clara/scripts/self_relaunch.py"))
    launch = namespace["ensure_running_in_managed_venv"]
    runtime = SimpleNamespace(
        activate_runtime=Mock(return_value=tmp_path / "managed"),
        ensure_runtime=Mock(return_value=(True, tmp_path / "managed", "ready")),
        runtime_python=Mock(return_value=tmp_path / "managed/bin/python"),
        runtime_environment=Mock(return_value={"PATH": "managed/bin"}),
    )
    monkeypatch.setattr(
        namespace["importlib"].util,
        "spec_from_file_location",
        lambda *a: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda m: None)),
    )
    monkeypatch.setattr(
        namespace["importlib"].util, "module_from_spec", lambda s: runtime
    )
    child = Mock(return_value=SimpleNamespace(returncode=7))
    monkeypatch.setattr(namespace["subprocess"], "run", child)
    monkeypatch.setattr(
        namespace["sys"],
        "argv",
        ["script.py", "relative.csv", "--output", "relative-output"],
    )
    return launch, runtime, child


def test_relaunch_preserves_relative_paths_arguments_and_child_failure(
    monkeypatch, tmp_path
):
    launch, runtime, child = launcher(monkeypatch, tmp_path)
    monkeypatch.setenv("MPARANZA_MANAGED_RUNTIME_VERIFY", "1")
    script = ROOT / "plugins/clara/modules/reporting-engine/scripts/profile_dataset.py"

    with pytest.raises(SystemExit) as stopped:
        launch(str(script))

    assert stopped.value.code == 7
    child.assert_called_once_with(
        [
            str(tmp_path / "managed/bin/python"),
            str(script),
            "relative.csv",
            "--output",
            "relative-output",
        ],
        cwd=Path.cwd(),
        env={"PATH": "managed/bin"},
        check=False,
    )
    runtime.ensure_runtime.assert_called_once()


def test_current_managed_prefix_does_not_relaunch(monkeypatch, tmp_path):
    launch, runtime, child = launcher(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.prefix", str(tmp_path / "managed"))

    launch(str(ROOT / "plugins/clara/scripts/init_case.py"))

    child.assert_not_called()
    runtime.ensure_runtime.assert_not_called()


def test_failed_setup_stops_before_imports(monkeypatch, tmp_path):
    launch, runtime, child = launcher(monkeypatch, tmp_path)
    runtime.ensure_runtime.return_value = (False, tmp_path / "managed", "offline")

    with pytest.raises(SystemExit) as stopped:
        launch(str(ROOT / "plugins/clara/scripts/init_case.py"))

    assert stopped.value.code == 1
    child.assert_not_called()


def test_render_entrypoint_selects_published_render_dependencies(monkeypatch, tmp_path):
    launch, runtime, child = launcher(monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        launch(
            str(
                ROOT
                / "plugins/clara/modules/reporting-engine/scripts/render_capability.py"
            )
        )
    assert runtime.ensure_runtime.call_args.kwargs["requirements"] == [
        "requirements.txt",
        "requirements-render.txt",
    ]


def test_nested_skill_uses_core_runtime_instead_of_unknown_component(
    monkeypatch, tmp_path
):
    launch, runtime, child = launcher(monkeypatch, tmp_path)

    with pytest.raises(SystemExit):
        launch(
            str(ROOT / "plugins/clara/skills/research-video/scripts/research_video.py")
        )

    assert runtime.ensure_runtime.call_args.args == (ROOT / "plugins/clara", None)
