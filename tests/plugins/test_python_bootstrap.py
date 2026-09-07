from __future__ import annotations

import hashlib
import importlib.util
import io
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def bootstrap():
    spec = importlib.util.spec_from_file_location(
        "bootstrap_test", ROOT / "plugins/vera/scripts/_python_bootstrap.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wheel():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("uv-0.12.10.data/scripts/uv", b"official uv binary")
    return output.getvalue()


def mock_download(module, monkeypatch, payload, digest):
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        module,
        "ASSETS",
        {"darwin:arm64": ("https://files.pythonhosted.org/example.whl", digest)},
    )
    monkeypatch.setattr(
        module.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(payload)
    )


def test_bootstrap_accepts_only_pinned_wheel(tmp_path, monkeypatch):
    module = bootstrap()
    payload = wheel()
    mock_download(module, monkeypatch, payload, hashlib.sha256(payload).hexdigest())
    result = module._uv(tmp_path)
    assert result.read_bytes() == b"official uv binary"


def test_bootstrap_rejects_checksum_mismatch_before_writing_executable(
    tmp_path, monkeypatch
):
    module = bootstrap()
    mock_download(module, monkeypatch, wheel(), "0" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        module._uv(tmp_path)
    assert not (tmp_path / "uv").exists()


@pytest.mark.parametrize("failure", ["download", "wrong_interpreter", "outside"])
def test_bootstrap_rejects_failed_or_wrong_interpreter(tmp_path, monkeypatch, failure):
    module = bootstrap()
    monkeypatch.setattr(module, "_uv", lambda base: base / "uv")
    python = tmp_path / (
        "outside/python" if failure == "outside" else "python/bin/python3.12"
    )
    python.parent.mkdir(parents=True)
    python.touch()

    def runner(command, **kwargs):
        code = int(
            failure == "download"
            or (failure == "wrong_interpreter" and "-c" in command)
        )
        return subprocess.CompletedProcess(command, code, str(python), "failed")

    with pytest.raises(ValueError):
        module.provision(tmp_path, runner)


def test_bootstrap_ignores_host_environment_and_never_changes_global_python(
    tmp_path, monkeypatch
):
    module = bootstrap()
    monkeypatch.setattr(module, "_uv", lambda base: base / "uv")
    monkeypatch.setenv("VIRTUAL_ENV", "/some/project")
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", "/global/python")
    python = tmp_path / "python/bin/python3.12"
    python.parent.mkdir(parents=True)
    python.touch()
    commands = []

    def runner(command, **kwargs):
        commands.append((command, kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, str(python), "")

    assert module.provision(tmp_path, runner) == str(python)
    assert "--no-bin" in commands[0][0]
    assert "--no-project" in commands[1][0]
    assert "--system" in commands[1][0]
    assert "VIRTUAL_ENV" not in commands[0][1]
    assert commands[0][1]["UV_PYTHON_INSTALL_DIR"] == str(tmp_path / "python")


@pytest.mark.parametrize("product", ["clara", "lucia"])
def test_products_ship_identical_bootstrap(product):
    assert (ROOT / f"plugins/{product}/scripts/_python_bootstrap.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/_python_bootstrap.py"
    ).read_bytes()


def test_bootstrap_rejects_unsupported_architecture(monkeypatch, tmp_path):
    module = bootstrap()
    monkeypatch.setattr(module.platform, "machine", lambda: "unsupported")
    with pytest.raises(ValueError, match="unavailable"):
        module._uv(tmp_path)


def test_bootstrap_reports_network_failure(monkeypatch, tmp_path):
    module = bootstrap()
    mock_download(module, monkeypatch, b"", "0" * 64)

    def offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(module.urllib.request, "urlopen", offline)
    with pytest.raises(ValueError, match="network access"):
        module._uv(tmp_path)


def test_bootstrap_rejects_wheel_without_executable(monkeypatch, tmp_path):
    module = bootstrap()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("unexpected", b"data")
    payload = output.getvalue()
    mock_download(module, monkeypatch, payload, hashlib.sha256(payload).hexdigest())
    with pytest.raises(ValueError, match="invalid uv wheel"):
        module._uv(tmp_path)


@pytest.mark.parametrize("directory", ["bootstrap", "python"])
def test_bootstrap_rejects_linked_storage(tmp_path, directory):
    module = bootstrap()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / directory).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        module.provision(tmp_path)
