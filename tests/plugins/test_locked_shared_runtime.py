"""Regression coverage for equivalent fresh installs and serialized reuse."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]


def fixture_runtime(tmp_path):
    """Reuse the installer fixture under both pytest import modes."""
    spec = importlib.util.spec_from_file_location(
        "locked_runtime_fixture",
        Path(__file__).with_name("test_single_shared_runtime.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.fixture_runtime(tmp_path)


def lock_reader():
    spec = importlib.util.spec_from_file_location(
        "lock_reader_test", ROOT / "plugins/vera/scripts/_locked_dependencies.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "platform,machine,expected_cryptography",
    [
        ("linux", "x86_64", "50.0.1"),
        ("linux", "aarch64", "50.0.1"),
        ("darwin", "arm64", "50.0.1"),
        ("darwin", "x86_64", "48.0.1"),
        ("win32", "AMD64", "50.0.1"),
    ],
)
def test_every_platform_has_complete_compatible_core_and_ocr_pins(
    platform, machine, expected_cryptography
):
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
    assert core["cryptography"] == expected_cryptography
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
    assert shared.ready(selection, path, api, runner)
    api._resolved_dependencies = lambda _: [{"name": "numpy", "version": "999"}]
    assert not shared.ready(selection, path, api, runner)
    install = next(call for call in calls if "install" in call)
    assert "--only-binary=cryptography" in install
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
    assert shared.ready(selection, path, api, runner)


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


def _local_probe_wheel(directory: Path, version: str) -> Path:
    """Build a tiny dependency fixture without a compiler, network or build tool."""
    wheel = directory / f"recovery_probe-{version}-py3-none-any.whl"
    metadata = f"recovery_probe-{version}.dist-info"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("recovery_probe.py", f"VERSION = {version!r}\n")
        archive.writestr(
            f"{metadata}/METADATA",
            f"Metadata-Version: 2.1\nName: recovery-probe\nVersion: {version}\n",
        )
        archive.writestr(
            f"{metadata}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{metadata}/RECORD", "")
    return wheel


@pytest.mark.parametrize("setting", ["dry-run", "target"])
@pytest.mark.parametrize("source", ["environment", "configuration"])
@pytest.mark.parametrize("fallback", [False, True])
def test_shared_setup_repairs_drift_despite_ambient_pip_settings(
    tmp_path, monkeypatch, setting, source, fallback
):
    shared, selection, api, _, _ = fixture_runtime(tmp_path)
    spec = importlib.util.spec_from_file_location(
        "pip_isolation_manager",
        ROOT / "plugins/clara/scripts/_managed_python_runtime.py",
    )
    manager = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, manager)
    spec.loader.exec_module(manager)
    path = tmp_path / "runtime/venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(path)], check=True
    )
    old_wheel = _local_probe_wheel(tmp_path, "2.0")
    locked_wheel = _local_probe_wheel(tmp_path, "1.0")
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("PIP_")
    }
    clean_env["PIP_CONFIG_FILE"] = os.devnull
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "--python",
            str(api.runtime_python(path)),
            "install",
            "--no-index",
            "--disable-pip-version-check",
            str(old_wheel),
        ],
        env=clean_env,
        capture_output=True,
        text=True,
        check=True,
    )
    lock = selection.plugin_root / "requirements-shared-core.lock"
    lock.write_text(
        f"--no-index\n--find-links {tmp_path.as_uri()}\nrecovery-probe==1.0 "
        f"--hash=sha256:{hashlib.sha256(locked_wheel.read_bytes()).hexdigest()}\n"
    )
    redirected = tmp_path / "unrelated-target"
    value = "true" if setting == "dry-run" else str(redirected)
    if source == "environment":
        monkeypatch.setenv("PIP_" + setting.upper().replace("-", "_"), value)
    else:
        config = tmp_path / "ambient-pip.ini"
        config.write_text(f"[install]\n{setting} = {value}\n")
        monkeypatch.setenv("PIP_CONFIG_FILE", str(config))
    api._bootstrap_pip = manager._bootstrap_pip
    api._resolved_dependencies = manager._resolved_dependencies
    api._dependencies_ready = lambda *args, **kwargs: True

    def run(command, **kwargs):
        if fallback and "--python" in command:
            return subprocess.CompletedProcess(command, 1, "", "No base pip")
        if any("_locked_dependencies.py" in str(arg) for arg in command):
            return subprocess.CompletedProcess(
                command, 0, '{"recovery-probe":"1.0"}', ""
            )
        return subprocess.run(command, **kwargs)

    ok, _, detail = shared.ensure(selection, path, api, run)

    assert ok, detail
    versions = {
        item["name"]: item["version"] for item in manager._resolved_dependencies(path)
    }
    assert versions["recovery-probe"] == "1.0"
    assert not redirected.exists()
    assert (path / shared.RECEIPT).is_file()
