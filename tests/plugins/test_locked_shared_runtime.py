"""Regression coverage for equivalent fresh installs and serialized reuse."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from test_single_shared_runtime import ROOT, fixture_runtime


def lock_reader():
    spec = importlib.util.spec_from_file_location(
        "lock_reader_test", ROOT / "plugins/vera/scripts/_locked_dependencies.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "platform,machine",
    [
        ("linux", "x86_64"),
        ("linux", "aarch64"),
        ("darwin", "arm64"),
        ("darwin", "x86_64"),
        ("win32", "AMD64"),
    ],
)
def test_every_platform_has_complete_compatible_core_and_ocr_pins(platform, machine):
    environment = {
        "sys_platform": platform,
        "platform_machine": machine,
        "python_version": "3.12",
        "python_full_version": "3.12.13",
        "implementation_name": "cpython",
        "platform_python_implementation": "CPython",
    }
    root = ROOT / "plugins/vera"
    reader = lock_reader()
    core = reader.locked_versions(root / "requirements-shared-core.lock", environment)
    ocr = reader.locked_versions(root / "requirements-shared-ocr.lock", environment)
    assert core.items() <= ocr.items()
    assert core["numpy"] == "2.2.6"
    assert core["plotly"] == "7.0.0"
    for feature, resolved in (("core", core), ("ocr", ocr)):
        for line in (
            (root / f"requirements-shared-{feature}.txt").read_text().splitlines()
        ):
            if not line.strip() or line.startswith("#"):
                continue
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            assert (
                resolved[canonicalize_name(requirement.name)] in requirement.specifier
            )


@pytest.mark.parametrize("requirement", ["numpy>=2", "numpy==2.*", "numpy==2.2.6"])
def test_lock_reader_rejects_unpinned_or_unhashed_dependencies(tmp_path, requirement):
    lock = tmp_path / "bad.lock"
    lock.write_text(requirement + "\n")
    with pytest.raises(ValueError, match="pin versions and SHA-256"):
        lock_reader().locked_versions(lock)


def test_missing_lock_stops_before_installing_anything(tmp_path):
    shared, selection, api, runner, calls = fixture_runtime(tmp_path)
    (selection.plugin_root / "requirements-shared-core.lock").unlink()
    ok, _, detail = shared.ensure(selection, tmp_path / "runtime/venv", api, runner)
    assert not ok
    assert "dependency lock is missing" in detail
    assert not calls


def test_inventory_drift_requires_repair_and_install_uses_hash_lock(tmp_path):
    shared, selection, api, runner, calls = fixture_runtime(tmp_path)
    path = tmp_path / "runtime/venv"
    assert shared.ensure(selection, path, api, runner)[0]
    assert shared.ready(selection, path, api)
    api._resolved_dependencies = lambda _: [{"name": "numpy", "version": "999"}]
    assert not shared.ready(selection, path, api)
    install = next(call for call in calls if "install" in call)
    assert "--require-hashes" in install
    assert install[-1].endswith("requirements-shared-core.lock")


def test_wrong_installed_version_never_gets_a_ready_receipt(tmp_path):
    shared, selection, api, runner, _ = fixture_runtime(tmp_path)
    api._resolved_dependencies = lambda _: [{"name": "numpy", "version": "999"}]

    def wrong(command, **kwargs):
        if any("_locked_dependencies.py" in str(arg) for arg in command):
            return subprocess.CompletedProcess(command, 0, '{"numpy":"2.2.6"}', "")
        return runner(command, **kwargs)

    path = tmp_path / "runtime/venv"
    ok, _, detail = shared.ensure(selection, path, api, wrong)
    assert not ok
    assert "numpy: expected 2.2.6, found 999" in detail
    assert not (path / shared.RECEIPT).exists()


def test_upgrade_removes_obsolete_managed_packages_and_retains_installer(tmp_path):
    shared, selection, api, runner, _ = fixture_runtime(tmp_path)
    distributions = [
        {"name": "old-plugin-dep", "version": "1"},
        {"name": "pip", "version": "1"},
    ]
    api._resolved_dependencies = lambda _: distributions.copy()
    removed = []

    def install(command, **kwargs):
        if "uninstall" in command:
            removed.append(command)
            distributions.pop(0)
        return runner(command, **kwargs)

    path = tmp_path / "runtime/venv"
    ok, _, detail = shared.ensure(selection, path, api, install)
    assert ok, detail
    assert removed[0][-1] == "old-plugin-dep"
    assert shared.ready(selection, path, api)


def test_concurrent_setup_waits_then_reuses_completed_install(tmp_path):
    shared, selection, api, runner, calls = fixture_runtime(tmp_path)
    started, release = threading.Event(), threading.Event()

    def held(command, **kwargs):
        if "install" in command:
            started.set()
            assert release.wait(5)
        return runner(command, **kwargs)

    path = tmp_path / "runtime/venv"
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(shared.ensure, selection, path, api, held)
        assert started.wait(5)
        second = pool.submit(shared.ensure, selection, path, api, held)
        release.set()
        assert first.result(timeout=5)[0]
        assert second.result(timeout=5)[0]
    assert sum("install" in command for command in calls) == 1
    assert json.loads((path / shared.RECEIPT).read_text())["features"] == ["core"]


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_managed_helpers_cannot_inherit_pythonpath(tmp_path, monkeypatch, product):
    spec = importlib.util.spec_from_file_location(
        "env_test_" + product,
        ROOT / f"plugins/{product}/scripts/_managed_python_runtime.py",
    )
    import sys

    api = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = api
    spec.loader.exec_module(api)
    monkeypatch.setenv("PYTHONPATH", "/unrelated/site-packages")
    env = api.runtime_environment(tmp_path / "runtime")
    assert "PYTHONPATH" not in env
    assert env["PYTHONNOUSERSITE"] == "1"
