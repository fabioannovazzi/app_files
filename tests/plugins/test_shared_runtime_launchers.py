from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APPLE_PYTHON = Path("/Library/Developer/CommandLineTools/usr/bin/python3")


def manager(product="vera"):
    spec = importlib.util.spec_from_file_location(
        "launcher_test_" + product,
        ROOT / f"plugins/{product}/scripts/_managed_python_runtime.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def installed_fixture(tmp_path, product, monkeypatch):
    root = tmp_path / product
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for filename in (
        "_managed_python_runtime.py",
        "_shared_python_runtime.py",
        "managed_python_runtime.py",
        "check_dependencies.py",
    ):
        shutil.copyfile(
            ROOT / f"plugins/{product}/scripts/{filename}", scripts / filename
        )
    if product == "clara":
        shutil.copyfile(
            ROOT / "plugins/clara/scripts/managed_ocr_runtime.py",
            scripts / "managed_ocr_runtime.py",
        )
    component = "reporting-engine" if product == "clara" else "studio-archive"
    (root / "components.json").write_text(json.dumps({"plugins": [component]}))
    for name in (
        "requirements.txt",
        "requirements-shared-core.txt",
        "requirements-shared-ocr.txt",
    ):
        (root / name).write_text("# isolated empty recipe\n")
    child = root / "modules" / component
    (child / "scripts").mkdir(parents=True)
    (child / "requirements.txt").write_text("# no dependencies\n")
    if product == "clara":
        (child / "requirements-render.txt").write_text("# no optional dependencies\n")
    (child / "scripts/check_dependencies.py").write_text(
        "import json,sys\nprint(json.dumps({'version':list(sys.version_info[:2]), 'prefix':sys.prefix}))\n"
    )
    api = manager(product)
    shared = api._shared_runtime()
    path = tmp_path / "runtime/venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(path)], check=True
    )
    (path.parent / "runtime.lock").write_bytes(b"1")
    site = path / (
        "Lib/site-packages" if os.name == "nt" else "lib/python3.12/site-packages"
    )
    (site / "_mparanza_runtime_guard.py").write_text(shared.GUARD)
    (site / "00_mparanza_runtime.pth").write_text("import _mparanza_runtime_guard\n")
    data = {
        "features": ["core", "ocr"],
        "recipes": shared._recipes(root, {"core", "ocr"}),
        "runtime_key": api.runtime_key(str(api.runtime_python(path))),
        "revision": shared.POLICY_REVISION,
    }
    (path / shared.RECEIPT).write_text(json.dumps(data))
    (path.parent / shared.POLICY).write_text(json.dumps(data))
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(path.parent))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.delenv(shared.INSTALLING, raising=False)
    return root, component, api, shared, path


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("launcher", ["host", "apple39"])
@pytest.mark.parametrize("entrypoint", ["check", "status", "run"])
def test_product_entrypoint_reuses_existing_python312(
    tmp_path, monkeypatch, product, launcher, entrypoint
):
    if launcher == "apple39" and not APPLE_PYTHON.is_file():
        pytest.skip("Apple Command Line Tools Python is unavailable on this host")
    root, component, api, shared, path = installed_fixture(
        tmp_path, product, monkeypatch
    )
    interpreter = str(APPLE_PYTHON) if launcher == "apple39" else sys.executable
    receipt = (path / shared.RECEIPT).read_bytes()
    policy = (path.parent / shared.POLICY).read_bytes()
    args = (
        [
            str(root / "scripts/check_dependencies.py"),
            "--module",
            component,
            "--include-optional",
        ]
        if entrypoint == "check"
        else [
            str(root / "scripts/managed_python_runtime.py"),
            "--module",
            component,
            entrypoint,
        ]
    )
    if entrypoint == "run":
        args.append("scripts/check_dependencies.py")
    monkeypatch.setenv("PATH", "")

    result = subprocess.run(
        [interpreter, *args], capture_output=True, text=True, timeout=15, check=False
    )

    assert result.returncode == 0, result.stdout + result.stderr
    if entrypoint != "status":
        assert json.loads(result.stdout) == {"version": [3, 12], "prefix": str(path)}
    assert (path / shared.RECEIPT).read_bytes() == receipt
    assert (path.parent / shared.POLICY).read_bytes() == policy


def test_identity_probe_does_not_take_reader_lease_or_load_site(tmp_path, monkeypatch):
    root, _, api, shared, path = installed_fixture(tmp_path, "vera", monkeypatch)
    expected = json.loads((path / shared.RECEIPT).read_text())["runtime_key"]
    (path / shared.RECEIPT).unlink()
    # An ordinary startup would block on this writer, then reject missing readiness.
    with shared._writer(path.parent / "runtime.lock", timeout=0.1):
        actual = api.runtime_key(api.runtime_python(path))
    assert actual == expected
    assert not (path / shared.RECEIPT).exists()


def test_unavailable_interpreter_is_rejected_without_changing_metadata(
    tmp_path, monkeypatch
):
    root, _, api, shared, path = installed_fixture(tmp_path, "vera", monkeypatch)
    receipt = (path / shared.RECEIPT).read_bytes()
    policy = (path.parent / shared.POLICY).read_bytes()
    for executable in (path / "bin").glob("python*"):
        executable.unlink()
    (path / "Scripts/python.exe").unlink(missing_ok=True)

    ready, _, detail = api.ensure_runtime(root)

    assert not ready
    assert detail
    assert (path / shared.RECEIPT).read_bytes() == receipt
    assert (path.parent / shared.POLICY).read_bytes() == policy


@pytest.mark.parametrize("mode", ["cold", "upgrade"])
def test_native_install_records_managed_identity_from_apple_launcher(
    tmp_path, monkeypatch, mode
):
    if not APPLE_PYTHON.is_file():
        pytest.skip("Apple Command Line Tools Python is unavailable on this host")
    root, _, api, shared, path = installed_fixture(tmp_path, "vera", monkeypatch)
    expected = json.loads((path / shared.RECEIPT).read_text())["runtime_key"]
    if mode == "cold":
        shutil.rmtree(path)
        (path.parent / shared.POLICY).unlink()
    else:
        (root / "requirements-shared-core.txt").write_text("# upgrade\n")
        policy = json.loads((path.parent / shared.POLICY).read_text())
        policy["revision"] -= 1
        (path.parent / shared.POLICY).write_text(json.dumps(policy))
    # The empty recipe needs no downloads. Keep real discovery, venv creation,
    # identity probes and writer/reader locks; isolate package-index operations.
    code = """import importlib.util, json, subprocess, sys
from pathlib import Path
root=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('native_install',root/'scripts/_managed_python_runtime.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
m._bootstrap_pip=lambda p, runner: (['isolated-pip'], {}, '')
m._dependencies_ready=lambda *args, **kwargs: True
def run(command, **kwargs):
    if command[0]=='isolated-pip':
        return subprocess.CompletedProcess(command, 0, '', '')
    return subprocess.run(command, **kwargs)
ok,path,detail=m.ensure_runtime(root,runner=run)
if not ok: raise RuntimeError(detail)
print((path/m._shared_runtime().RECEIPT).read_text())
"""
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent))

    result = subprocess.run(
        [str(APPLE_PYTHON), "-B", "-c", code, str(root)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["runtime_key"] == expected
    assert json.loads(result.stdout)["features"] == (
        ["core"] if mode == "cold" else ["core", "ocr"]
    )
