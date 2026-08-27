from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SOURCE = ROOT / "plugins" / "vera" / "scripts" / "_managed_python_runtime.py"
VERA_MANAGER = ROOT / "plugins" / "vera" / "scripts" / "managed_python_runtime.py"


def load_runtime() -> Any:
    spec = importlib.util.spec_from_file_location(
        "managed_plugin_python_runtime_test",
        RUNTIME_SOURCE,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_clara_and_vera_share_the_same_runtime_implementation() -> None:
    clara_runtime = (
        ROOT / "plugins" / "clara" / "scripts" / "_managed_python_runtime.py"
    )

    assert clara_runtime.read_bytes() == RUNTIME_SOURCE.read_bytes()


def make_packaged_component(root: Path) -> Path:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    manifest_dir = root / ".codex-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": "vera", "version": "0.1.129"}) + "\n",
        encoding="utf-8",
    )
    (scripts / "managed_python_runtime.py").write_bytes(VERA_MANAGER.read_bytes())
    (scripts / "_managed_python_runtime.py").write_bytes(RUNTIME_SOURCE.read_bytes())
    (root / "components.json").write_text(
        json.dumps({"schema_version": 1, "plugins": ["studio-archive"]}) + "\n",
        encoding="utf-8",
    )
    component = root / "modules" / "studio-archive"
    component_scripts = component / "scripts"
    component_scripts.mkdir(parents=True)
    (component / "requirements.txt").write_text(
        "demo-dependency==1.0\n",
        encoding="utf-8",
    )
    (component_scripts / "check_dependencies.py").write_text(
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    return component


def create_fake_virtualenv(target: Path, *, windows: bool = False) -> Path:
    python = target / "Scripts" / "python.exe" if windows else target / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return python


def site_packages(target: Path) -> Path:
    return (
        target
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )


def test_missing_target_is_installed_before_dependency_validation(
    tmp_path: Path,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    make_packaged_component(plugin_root)
    data_dir = tmp_path / "plugin-data"
    commands: list[list[str]] = []

    def fake_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            create_fake_virtualenv(Path(command[-1]))
        return subprocess.CompletedProcess(command, 0, "", "")

    ready, target, detail = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        data_dir=data_dir,
        runner=fake_runner,
    )

    assert ready is True
    assert detail == f"Python runtime installed at {target}"
    assert commands[0] == [
        sys.executable,
        "-m",
        "venv",
        "--without-pip",
        str(target),
    ]
    assert commands[1][:5] == [
        sys.executable,
        "-m",
        "pip",
        "--python",
        str(runtime.runtime_python(target)),
    ]
    assert commands[1][-1] == "--version"
    assert commands[2][:6] == [*commands[1][:-1], "install"]
    assert commands[3][1].endswith("scripts/check_dependencies.py")
    assert json.loads((target / runtime.READY_FILENAME).read_text())["scope"] == (
        "modules/studio-archive"
    )


def test_selected_optional_requirements_are_installed_before_validation(
    tmp_path: Path,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    component = make_packaged_component(plugin_root)
    optional_name = "requirements-portal-recorder.txt"
    optional_file = component / optional_name
    optional_file.write_text("playwright>=1.48.0\n", encoding="utf-8")
    data_dir = tmp_path / "plugin-data"
    commands: list[list[str]] = []

    def fake_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            create_fake_virtualenv(Path(command[-1]))
        return subprocess.CompletedProcess(command, 0, "", "")

    ready, target, detail = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        requirements=[optional_name],
        data_dir=data_dir,
        runner=fake_runner,
    )

    assert ready is True, detail
    assert commands[2][-2:] == ["-r", str(optional_file)]
    assert commands[3][-2:] == ["--requirements", optional_name]
    default_selection = runtime.select_runtime(plugin_root, "studio-archive")
    default_target = runtime.dependency_target(default_selection, data_dir)
    assert target != default_target


def test_optional_requirements_cannot_escape_component_root(tmp_path: Path) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    make_packaged_component(plugin_root)

    with pytest.raises(ValueError) as raised:
        runtime.select_runtime(
            plugin_root,
            "studio-archive",
            ["../requirements.txt"],
        )

    assert str(raised.value) == (
        "Requirements file is outside component: ../requirements.txt"
    )


def test_included_requirements_cannot_escape_component_root(tmp_path: Path) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    component = make_packaged_component(plugin_root)
    outside_requirements = component.parent / "outside.txt"
    outside_requirements.write_text("outside-dependency==1.0\n", encoding="utf-8")
    (component / "requirements.txt").write_text(
        "-r ../outside.txt\n",
        encoding="utf-8",
    )
    selection = runtime.select_runtime(plugin_root, "studio-archive")

    with pytest.raises(ValueError) as raised:
        runtime.requirements_fingerprint(selection)

    assert "Included requirements file is outside component" in str(raised.value)


def test_requirement_fingerprint_is_stable_between_source_and_package_layouts(
    tmp_path: Path,
) -> None:
    runtime = load_runtime()
    source_vera = tmp_path / "source" / "vera"
    source_component = make_packaged_component(source_vera)
    sibling_component = source_vera.parent / "studio-archive"
    source_component.rename(sibling_component)
    packaged_vera = tmp_path / "package" / "vera"
    make_packaged_component(packaged_vera)
    source_selection = runtime.select_runtime(source_vera, "studio-archive")
    packaged_selection = runtime.select_runtime(packaged_vera, "studio-archive")

    source_fingerprint = runtime.requirements_fingerprint(source_selection)

    assert source_fingerprint == runtime.requirements_fingerprint(packaged_selection)


def test_first_setup_prevents_nested_google_probe_from_crashing(
    tmp_path: Path,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    component = make_packaged_component(plugin_root)
    data_dir = tmp_path / "plugin-data"
    (component / "requirements.txt").write_text(
        "google-api-core>=2.11,<2.25\n",
        encoding="utf-8",
    )
    checker = component / "scripts" / "check_dependencies.py"
    checker.write_text(
        "import importlib.util\n"
        "raise SystemExit(0 if importlib.util.find_spec('google.api_core') else 1)\n",
        encoding="utf-8",
    )

    def install_then_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if command[1:3] == ["-m", "venv"]:
            return subprocess.run(command, **kwargs)
        if command[1:3] == ["-m", "pip"]:
            if "install" not in command:
                return subprocess.CompletedProcess(command, 0, "pip ready", "")
            target_python = Path(command[command.index("--python") + 1])
            target = target_python.parents[1]
            google = site_packages(target) / "google" / "api_core"
            google.mkdir(parents=True)
            (google.parent / "__init__.py").write_text("", encoding="utf-8")
            (google / "__init__.py").write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.run(command, **kwargs)

    ready, _, detail = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        data_dir=data_dir,
        runner=install_then_run,
    )

    assert ready is True, detail


def test_unknown_component_is_rejected_before_target_creation(tmp_path: Path) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    make_packaged_component(plugin_root)

    with pytest.raises(ValueError) as raised:
        runtime.select_runtime(plugin_root, "../unregistered")

    assert str(raised.value) == "Unknown plugin component: ../unregistered"


def test_runtime_target_is_partitioned_by_windows_platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "clara"
    make_packaged_component(plugin_root)
    monkeypatch.setattr(runtime.sysconfig, "get_platform", lambda: "win-amd64")
    selection = runtime.select_runtime(plugin_root, "studio-archive")

    target = runtime.dependency_target(selection, tmp_path / "plugin-data")

    assert f"{sys.implementation.cache_tag}-win-amd64" in target.parts


def test_windows_runtime_avoids_ensurepip_when_base_pip_is_available(
    tmp_path: Path,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    make_packaged_component(plugin_root)
    commands: list[list[str]] = []

    def windows_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            create_fake_virtualenv(Path(command[-1]), windows=True)
        return subprocess.CompletedProcess(command, 0, "", "")

    ready, target, detail = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        data_dir=tmp_path / "plugin-data",
        runner=windows_runner,
    )

    target_python = target / "Scripts" / "python.exe"
    assert ready is True, detail
    assert "--without-pip" in commands[0]
    assert commands[1][-2:] == [str(target_python), "--version"]
    assert commands[2][:5] == [
        sys.executable,
        "-m",
        "pip",
        "--python",
        str(target_python),
    ]
    assert all("ensurepip" not in command for command in commands)


def test_base_pip_unavailable_falls_back_to_direct_ensurepip(tmp_path: Path) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    make_packaged_component(plugin_root)
    commands: list[list[str]] = []

    def fallback_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            create_fake_virtualenv(Path(command[-1]), windows=True)
            return subprocess.CompletedProcess(command, 0, "", "")
        if "--python" in command:
            return subprocess.CompletedProcess(command, 1, "", "No module named pip")
        return subprocess.CompletedProcess(command, 0, "", "")

    ready, target, detail = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        data_dir=tmp_path / "plugin-data",
        runner=fallback_runner,
    )

    target_python = str(target / "Scripts" / "python.exe")
    assert ready is True, detail
    assert commands[2] == [
        target_python,
        "-m",
        "ensurepip",
        "--upgrade",
        "--default-pip",
    ]
    assert commands[3][:3] == [target_python, "-m", "pip"]


def test_ensurepip_failure_returns_complete_windows_diagnostics(
    tmp_path: Path,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    make_packaged_component(plugin_root)

    def blocked_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        if command[1:3] == ["-m", "venv"]:
            create_fake_virtualenv(Path(command[-1]), windows=True)
            return subprocess.CompletedProcess(command, 0, "", "")
        if "--python" in command:
            return subprocess.CompletedProcess(
                command,
                1,
                "base pip output",
                "base pip could not launch target Python",
            )
        return subprocess.CompletedProcess(
            command,
            1,
            "ensurepip output",
            "Access is denied while unpacking bundled wheels",
        )

    ready, target, detail = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        data_dir=tmp_path / "plugin-data",
        runner=blocked_runner,
    )

    assert ready is False
    assert not target.exists()
    assert "Managed pip bootstrap failed." in detail
    assert "Base pip probe returned exit status 1" in detail
    assert "base pip output" in detail
    assert "base pip could not launch target Python" in detail
    assert "Target ensurepip returned exit status 1" in detail
    assert "ensurepip output" in detail
    assert "Access is denied while unpacking bundled wheels" in detail


def test_codex_runtime_uses_stable_private_temp_data_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    plugin_root.mkdir()
    codex_temp = tmp_path / "codex-temp"
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.delenv("PLUGIN_DATA", raising=False)
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    monkeypatch.setattr(runtime.tempfile, "gettempdir", lambda: str(codex_temp))

    result = runtime.plugin_data_dir(plugin_root)

    assert result == (
        codex_temp / "mparanza-managed-python" / f"uid-{os.getuid()}" / "vera"
    )
    assert stat.S_IMODE(result.stat().st_mode) == 0o700
    assert list(result.glob(".mparanza-write-probe-*")) == []


def test_marketplace_version_folder_uses_stable_manifest_plugin_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "marketplace" / "vera" / "0.1.129"
    make_packaged_component(plugin_root)
    codex_temp = tmp_path / "codex-temp"
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.delenv("PLUGIN_DATA", raising=False)
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    monkeypatch.setattr(runtime.tempfile, "gettempdir", lambda: str(codex_temp))

    result = runtime.plugin_data_dir(plugin_root)

    assert result.name == "vera"
    assert "0.1.129" not in result.parts


def test_network_resolution_failure_requests_codex_host_approval(
    tmp_path: Path,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    make_packaged_component(plugin_root)

    def network_blocked_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        if command[1:3] == ["-m", "venv"]:
            create_fake_virtualenv(Path(command[-1]))
            return subprocess.CompletedProcess(command, 0, "", "")
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "pip ready", "")
        return subprocess.CompletedProcess(
            command,
            1,
            "",
            "NameResolutionError: Failed to resolve 'pypi.org'",
        )

    ready, _, detail = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        data_dir=tmp_path / "plugin-data",
        runner=network_blocked_runner,
    )

    assert ready is False
    assert detail.startswith(f"{runtime.NETWORK_PERMISSION_REQUIRED}:")
    assert "host network access approval" in detail


def test_invalid_distribution_is_not_mislabeled_as_network_denial(
    tmp_path: Path,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    make_packaged_component(plugin_root)
    package_error = "ERROR: No matching distribution found for unavailable-demo"

    def invalid_distribution_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        if command[1:3] == ["-m", "venv"]:
            create_fake_virtualenv(Path(command[-1]))
            return subprocess.CompletedProcess(command, 0, "", "")
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "pip ready", "")
        return subprocess.CompletedProcess(command, 1, "", package_error)

    ready, _, detail = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        data_dir=tmp_path / "plugin-data",
        runner=invalid_distribution_runner,
    )

    assert ready is False
    assert detail == package_error
    assert runtime.NETWORK_PERMISSION_REQUIRED not in detail


def test_ready_target_is_reused_without_reinstalling(tmp_path: Path) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    make_packaged_component(plugin_root)
    data_dir = tmp_path / "plugin-data"
    commands: list[list[str]] = []

    def fake_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            create_fake_virtualenv(Path(command[-1]))
        return subprocess.CompletedProcess(command, 0, "", "")

    first_ready, _, _ = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        data_dir=data_dir,
        runner=fake_runner,
    )
    commands.clear()

    ready, _, detail = runtime.ensure_runtime(
        plugin_root,
        "studio-archive",
        data_dir=data_dir,
        runner=fake_runner,
    )

    assert first_ready is True
    assert ready is True
    assert detail.startswith("Python runtime ready at ")
    assert len(commands) == 1
    assert "pip" not in commands[0]


def test_managed_launcher_imports_ready_component_target(
    tmp_path: Path,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    component = make_packaged_component(plugin_root)
    data_dir = tmp_path / "plugin-data"
    selection = runtime.select_runtime(plugin_root, "studio-archive")
    target = runtime.dependency_target(selection, data_dir)
    subprocess.run(
        [sys.executable, "-m", "venv", str(target)],
        check=True,
        capture_output=True,
        text=True,
    )
    managed_site_packages = site_packages(target)
    (managed_site_packages / "demo_dependency.py").write_text("VALUE = 'managed'\n")
    receipt = {
        "schema_version": 1,
        "plugin": "vera",
        "scope": "modules/studio-archive",
        "requirements_fingerprint": runtime.requirements_fingerprint(selection),
        "runtime_key": runtime.runtime_key(),
    }
    (target / runtime.READY_FILENAME).write_text(
        json.dumps(receipt, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    script = component / "scripts" / "use_dependency.py"
    script.write_text(
        "import demo_dependency\nprint(demo_dependency.VALUE)\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["PLUGIN_DATA"] = str(data_dir)

    completed = subprocess.run(
        [
            sys.executable,
            str(plugin_root / "scripts" / "managed_python_runtime.py"),
            "--module",
            "studio-archive",
            "run",
            "scripts/use_dependency.py",
        ],
        cwd=plugin_root,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "managed"


def test_managed_launcher_installs_optional_requirements_and_runs_helper_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = load_runtime()
    plugin_root = tmp_path / "vera"
    component = make_packaged_component(plugin_root)
    optional_name = "requirements-portal-recorder.txt"
    (component / optional_name).write_text(
        "# Synthetic empty optional environment.\n",
        encoding="utf-8",
    )
    marker = tmp_path / "recorder-started.txt"
    script = component / "scripts" / "record_probe.py"
    script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[1]).write_text('started', encoding='utf-8')\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "plugin-data"))

    result = runtime.main(
        plugin_root,
        [
            "--module",
            "studio-archive",
            "--requirements",
            optional_name,
            "run",
            "scripts/record_probe.py",
            str(marker),
        ],
    )

    assert result == 0
    assert marker.read_text(encoding="utf-8") == "started"
