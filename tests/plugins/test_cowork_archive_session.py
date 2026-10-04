"""Regression checks for Cowork process continuity and Windows bootstrap."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZipFile

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "plugins/vera/scripts/studio_archive_session.py"
WINDOWS = ROOT / "plugins/vera/scripts/studio_archive_windows.ps1"


def load_entry() -> Any:
    """Import only the lightweight session entrypoint."""
    spec = importlib.util.spec_from_file_location("cowork_session_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def package(tmp_path: Path) -> Path:
    """Use the real archive CLI with a runtime shim to avoid installation/network."""
    root = tmp_path / "Vera package with spaces"
    (root / "scripts").mkdir(parents=True)
    component = root / "modules/studio-archive/scripts"
    component.mkdir(parents=True)
    shutil.copyfile(SOURCE, root / "scripts/studio_archive_session.py")
    (component / "studio_archive.py").write_text("# Package readability sentinel\n")
    (root / "components.json").write_text('{"plugins":["studio-archive"]}')
    (root / "scripts/check_dependencies.py").write_text("raise SystemExit(0)\n")
    archive = ROOT / "plugins/studio-archive/scripts/studio_archive.py"
    (root / "scripts/managed_python_runtime.py").write_text(
        "import sys, runpy\n"
        f"sys.path.insert(0, {str(archive.parent)!r})\n"
        "sys.argv = [sys.argv[0], *sys.argv[5:]]\n"
        f"runpy.run_path({str(archive)!r}, run_name='__main__')\n"
    )
    return root


def invoke(root: Path, session: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run an independent shell-equivalent process with isolated user state."""
    environment = dict(os.environ)
    environment.pop("VERA_STUDIO_ARCHIVE_STATE_DIR", None)
    environment.pop("VERA_STUDIO_ARCHIVE_SESSION_ID", None)
    environment.pop("CODEX_THREAD_ID", None)
    environment.update(
        HOME=str(root.parent), USERPROFILE=str(root.parent), PYTHONDONTWRITEBYTECODE="1"
    )
    return subprocess.run(
        [
            sys.executable,
            str(root / "scripts/studio_archive_session.py"),
            "--session-id",
            session,
            *args,
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_separate_commands_reuse_config_and_new_session_recovers_same_client(
    tmp_path: Path,
) -> None:
    root = package(tmp_path)
    archive = tmp_path / "Existing Studio"
    archive.mkdir()
    first, second = str(uuid4()), str(uuid4())
    configured = invoke(root, first, "configure", "--archive-root", str(archive))
    assert configured.returncode == 0, configured.stderr + configured.stdout
    created = invoke(root, first, "create-client", "--legal-name", "Synthetic Client")
    assert created.returncode == 0, created.stderr + created.stdout
    initial = invoke(root, first, "clients")
    assert initial.returncode == 0, initial.stdout + initial.stderr
    first_clients = json.loads(initial.stdout)["clients"]
    assert len(first_clients) == 1
    # A new task must select the root, not silently adopt another task's pointer.
    fresh = invoke(root, second, "clients")
    assert '"configured": false' in fresh.stdout
    assert (
        invoke(root, second, "configure", "--archive-root", str(archive)).returncode
        == 0
    )
    recovery = invoke(root, second, "recover-ledger")
    assert recovery.returncode == 0, recovery.stdout + recovery.stderr
    recovered = invoke(root, second, "clients")
    assert (
        json.loads(recovered.stdout)["clients"][0]["client_id"]
        == first_clients[0]["client_id"]
    )
    assert len(list(archive.glob("*/Vera/client.json"))) == 1


def test_missing_package_stops_before_managed_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = load_entry()
    monkeypatch.setattr(entry, "ROOT", tmp_path)
    result = entry.main(
        ["--session-id", str(uuid4()), "configure", "--archive-root", "unused"]
    )
    assert result == 2
    assert "archive_package_unreadable" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_diagnose_does_not_provision_runtime_or_write_archive(tmp_path: Path) -> None:
    root = package(tmp_path)
    result = invoke(root, str(uuid4()), "diagnose")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "package_readable": True,
        "runtime_checked": False,
    }
    assert not (tmp_path / ".mparanza").exists()


def test_invalid_session_is_rejected_before_execution(tmp_path: Path) -> None:
    result = invoke(package(tmp_path), "not-a-task-uuid", "clients")
    assert result.returncode == 2
    assert not (tmp_path / ".mparanza").exists()


def test_diagnose_reads_package_without_starting_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = load_entry()
    monkeypatch.setattr(entry, "ROOT", package(tmp_path))
    result = entry.main(["--session-id", str(uuid4()), "diagnose"])
    assert result == 0
    assert json.loads(capsys.readouterr().out)["runtime_checked"] is False


@pytest.mark.parametrize("command", ["check", "clients"])
def test_session_forwarding_keeps_managed_runtime_and_return_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    entry = load_entry()
    root = package(tmp_path)
    monkeypatch.setattr(entry, "ROOT", root)
    session = str(uuid4())
    captured: dict[str, Any] = {}

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 7)

    monkeypatch.setattr(entry.subprocess, "run", run)
    result = entry.main(["--session-id", session, command])
    assert result == 7
    assert captured["env"]["VERA_STUDIO_ARCHIVE_SESSION_ID"] == session
    expected_script = (
        "check_dependencies.py" if command == "check" else "managed_python_runtime.py"
    )
    assert captured["argv"][:4] == [
        sys.executable,
        str(root / "scripts" / expected_script),
        "--module",
        "studio-archive",
    ]


@pytest.mark.skipif(
    sys.platform != "win32", reason="Exercises native Windows PowerShell process launch"
)
@pytest.mark.parametrize("explicit", [True, False])
def test_windows_launcher_uses_verified_python_with_spaces(
    tmp_path: Path, explicit: bool
) -> None:
    root = package(tmp_path)
    launcher = root / "scripts/studio_archive_windows.ps1"
    shutil.copyfile(WINDOWS, launcher)
    shell = shutil.which("powershell.exe")
    assert shell
    command = [shell, "-NoProfile", "-File", str(launcher), "-SessionId", str(uuid4())]
    if explicit:
        command += ["-PythonExecutable", sys.executable]
    archive = tmp_path / "Existing studio with spaces"
    archive.mkdir()
    command += ["configure", "--archive-root", str(archive)]
    environment = dict(os.environ)
    # No py or python3 needed: PATH provides the actual python.exe directory.
    environment["PATH"] = str(Path(sys.executable).parent)
    environment["USERPROFILE"] = str(tmp_path)
    environment.pop("VERA_STUDIO_ARCHIVE_STATE_DIR", None)
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["configured"] is True


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Exercises native Windows missing-interpreter handling",
)
def test_windows_launcher_reports_unavailable_without_archive_writes(
    tmp_path: Path,
) -> None:
    root = package(tmp_path)
    launcher = root / "scripts/studio_archive_windows.ps1"
    shutil.copyfile(WINDOWS, launcher)
    shell = shutil.which("powershell.exe")
    assert shell
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(launcher),
            "-SessionId",
            str(uuid4()),
            "-PythonExecutable",
            str(tmp_path / "absent.exe"),
            "diagnose",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode != 0
    assert "archive_bootstrap_unavailable" in result.stderr
    assert not (tmp_path / ".mparanza").exists()


@pytest.mark.parametrize("product", ["vera", "lucia"])
def test_distributed_archive_skill_ships_callable_session_helpers(
    tmp_path: Path, product: str
) -> None:
    root = tmp_path / "package"
    with ZipFile(
        ROOT / "plugin_packages" / product / f"{product}-claude-plugin.zip"
    ) as archive:
        archive.extractall(root)
    assert (
        root / "scripts/studio_archive_windows.ps1"
    ).read_bytes() == WINDOWS.read_bytes()
    assert (
        root / "scripts/studio_archive_session.py"
    ).read_bytes() == SOURCE.read_bytes()
    result = invoke(root, str(uuid4()), "diagnose")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["package_readable"] is True
