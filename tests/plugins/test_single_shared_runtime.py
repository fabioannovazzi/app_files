from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


def backend():
    source = ROOT / "plugins/vera/scripts/_shared_python_runtime.py"
    spec = importlib.util.spec_from_file_location("single_runtime_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_runtime(tmp_path):
    module = backend()
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "requirements-shared-core.txt").write_text("# core\n")
    (root / "requirements-shared-ocr.txt").write_text("# ocr\n")
    selection = SimpleNamespace(
        plugin_root=root, requirements_files=[root / "requirements.txt"]
    )
    api = SimpleNamespace(
        _python312_executable=lambda runner: sys.executable,
        runtime_key=lambda: "test-runtime",
        runtime_python=lambda p: p
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
        _bootstrap_pip=lambda p, runner: ([str(p / "bin/python"), "-m", "pip"], {}, ""),
        _process_detail=lambda r: r.stderr or r.stdout,
        _network_permission_detail=lambda s: s,
        _dependencies_ready=lambda *args, **kwargs: True,
        _resolved_dependencies=lambda p: [],
    )
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if "venv" in command:
            return subprocess.run(command, **kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    return module, selection, api, runner, calls


def test_all_products_and_modules_select_one_environment(tmp_path, monkeypatch):
    module = backend()
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "shared"))
    assert (
        module.target(tmp_path / "vera")
        == module.target(tmp_path / "clara")
        == module.target(tmp_path / "lucia")
        == tmp_path / "shared/venv"
    )


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_host_plugin_data_directory_does_not_split_shared_runtime(
    tmp_path, monkeypatch, product
):
    source = ROOT / f"plugins/{product}/scripts/_managed_python_runtime.py"
    spec = importlib.util.spec_from_file_location(f"shared_manager_{product}", source)
    manager = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = manager
    spec.loader.exec_module(manager)
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "shared"))
    selection = manager.select_runtime(ROOT / f"plugins/{product}")

    target = manager.dependency_target(selection, tmp_path / f"{product}-host-data")

    assert target == tmp_path / "shared/venv"


def test_ocr_upgrade_reuses_interpreter_and_remains_enabled(tmp_path):
    module, selection, api, runner, calls = fixture_runtime(tmp_path)
    path = module.target(selection.plugin_root, tmp_path / "shared")
    assert module.ensure(selection, path, api, runner)[0]
    selection.requirements_files = [selection.plugin_root / "requirements-ocr.txt"]
    assert module.ensure(selection, path, api, runner)[0]
    selection.requirements_files = [selection.plugin_root / "requirements.txt"]
    assert module.ensure(selection, path, api, runner)[0]
    assert sum("venv" in call for call in calls) == 1
    assert json.loads((path / module.RECEIPT).read_text())["features"] == [
        "core",
        "ocr",
    ]
    assert len(list(path.parent.glob("venv*"))) == 1


def test_failed_package_update_invalidates_ready_receipt_and_keeps_features(tmp_path):
    module, selection, api, runner, calls = fixture_runtime(tmp_path)
    path = module.target(selection.plugin_root, tmp_path / "shared")
    assert module.ensure(selection, path, api, runner)[0]
    selection.requirements_files = [selection.plugin_root / "requirements-ocr.txt"]

    def failed(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "simulated failure")

    assert not module.ensure(selection, path, api, failed)[0]
    assert not module.ready(selection, path, api)
    assert not (path / module.RECEIPT).exists()
    assert json.loads((path.parent / module.POLICY).read_text())["features"] == [
        "core",
        "ocr",
    ]
    assert module.ensure(selection, path, api, runner)[0]


def test_changed_shared_recipe_is_not_silently_reused(tmp_path):
    module, selection, api, runner, calls = fixture_runtime(tmp_path)
    path = module.target(selection.plugin_root, tmp_path / "shared")
    assert module.ensure(selection, path, api, runner)[0]
    (selection.plugin_root / "requirements-shared-core.txt").write_text("# changed\n")
    assert not module.ready(selection, path, api)


def test_older_plugin_cannot_downgrade_shared_policy(tmp_path):
    module, selection, api, runner, calls = fixture_runtime(tmp_path)
    path = module.target(selection.plugin_root, tmp_path / "shared")
    assert module.ensure(selection, path, api, runner)[0]
    module.POLICY_REVISION += 1
    (selection.plugin_root / "requirements-shared-core.txt").write_text("# upgraded\n")
    assert module.ensure(selection, path, api, runner)[0]
    module.POLICY_REVISION -= 1
    (selection.plugin_root / "requirements-shared-core.txt").write_text("# core\n")

    ready, _, detail = module.ensure(selection, path, api, runner)

    assert not ready
    assert "newer runtime policy" in detail
    assert (path / module.RECEIPT).is_file()


def test_conflicting_recipe_at_same_revision_is_rejected_before_mutation(tmp_path):
    module, selection, api, runner, calls = fixture_runtime(tmp_path)
    path = module.target(selection.plugin_root, tmp_path / "shared")
    assert module.ensure(selection, path, api, runner)[0]
    receipt = (path / module.RECEIPT).read_bytes()
    (selection.plugin_root / "requirements-shared-core.txt").write_text("# conflict\n")

    ready, _, detail = module.ensure(selection, path, api, runner)

    assert not ready
    assert "Conflicting shared recipes" in detail
    assert (path / module.RECEIPT).read_bytes() == receipt


def test_runtime_root_symlink_rejected(tmp_path):
    module = backend()
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(OSError, match="symlink"):
        module.target(tmp_path, link)


def test_running_python_prevents_package_update(tmp_path):
    module, selection, api, runner, calls = fixture_runtime(tmp_path)
    path = module.target(selection.plugin_root, tmp_path / "shared")
    assert module.ensure(selection, path, api, runner)[0]
    env = dict(os.environ)
    env.pop(module.INSTALLING, None)
    env.pop("PYTHONPATH", None)
    child = subprocess.Popen(
        [
            str(api.runtime_python(path)),
            "-u",
            "-c",
            'import sys; print("ready", flush=True); sys.stdin.read()',
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(OSError, match="busy"):
            with module._writer(path.parent / "runtime.lock", timeout=0.1):
                pytest.fail("Writer acquired a live reader lease")
    finally:
        child.communicate("", timeout=10)
    assert child.returncode == 0
    with module._writer(path.parent / "runtime.lock", timeout=0.1):
        assert (path / module.RECEIPT).is_file()


def test_unready_interpreter_refuses_workflow_execution(tmp_path):
    module, selection, api, runner, calls = fixture_runtime(tmp_path)
    path = module.target(selection.plugin_root, tmp_path / "shared")
    assert module.ensure(selection, path, api, runner)[0]
    (path / module.RECEIPT).unlink()
    env = dict(os.environ)
    env.pop(module.INSTALLING, None)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            str(api.runtime_python(path)),
            "-c",
            'raise RuntimeError("workflow executed")',
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "shared runtime is not ready" in result.stderr
    assert "workflow executed" not in result.stderr


@pytest.mark.parametrize(
    "filename",
    [
        "requirements-shared-core.txt",
        "requirements-shared-ocr.txt",
        "constraints-shared-macos-py312.txt",
        "scripts/_shared_python_runtime.py",
    ],
)
def test_products_ship_identical_shared_policy(filename):
    assert (
        (ROOT / "plugins/vera" / filename).read_bytes()
        == (ROOT / "plugins/clara" / filename).read_bytes()
        == (ROOT / "plugins/lucia" / filename).read_bytes()
    )


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("host", ["plugin", "claude-plugin", "chatgpt-upload"])
def test_every_host_package_contains_the_shared_runtime_policy(product, host):
    prefix = f"{product}-codex-plugin/plugins/{product}/" if host == "plugin" else ""
    expected = {
        prefix + name: (ROOT / "plugins" / product / name).read_bytes()
        for name in (
            "requirements-shared-core.txt",
            "requirements-shared-ocr.txt",
            "constraints-shared-macos-py312.txt",
            "scripts/_shared_python_runtime.py",
        )
    }
    with ZipFile(ROOT / f"plugin_packages/{product}/{product}-{host}.zip") as archive:
        actual = {name: archive.read(name) for name in expected}

    assert actual == expected


def requirement_lines(path):
    lines = set()
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("-r "):
            lines.update(requirement_lines(path.parent / line[3:].strip()))
        elif line:
            lines.add(line)
    return lines


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("feature", ["core", "ocr"])
def test_shared_recipe_covers_every_declared_component_requirement(product, feature):
    root = ROOT / "plugins" / product
    scopes = [root]
    for component in json.loads((root / "components.json").read_text())["plugins"]:
        packaged = root / "modules" / component
        scopes.append(packaged if packaged.is_dir() else root.parent / component)
    declared = set()
    for scope in scopes:
        for path in scope.glob("requirements*.txt"):
            if "shared" in path.name:
                continue
            if ("ocr" in path.name) == (feature == "ocr"):
                declared.update(requirement_lines(path))
    recipe = requirement_lines(root / f"requirements-shared-{feature}.txt")

    assert declared <= recipe, sorted(declared - recipe)
