from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins" / "clara" / "scripts" / "bootstrap_python_dependencies.py"


def load_bootstrap() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_dependency_bootstrap",
        SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_requirements(root: Path, nested_requirement: str = "polars>=1.0") -> None:
    module_dir = root / "modules" / "reporting-engine"
    module_dir.mkdir(parents=True)
    (root / "requirements.txt").write_text(
        "-r modules/reporting-engine/requirements.txt\n",
        encoding="utf-8",
    )
    (module_dir / "requirements.txt").write_text(
        f"{nested_requirement}\n",
        encoding="utf-8",
    )
    scripts_dir = root / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "check_dependencies.py").write_text("", encoding="utf-8")


def completed(
    command: list[str], returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, "", "")


def test_requirements_fingerprint_includes_recursive_requirement_files(
    tmp_path: Path,
) -> None:
    bootstrap = load_bootstrap()
    write_requirements(tmp_path)
    first = bootstrap.requirements_fingerprint(tmp_path)
    nested = tmp_path / "modules" / "reporting-engine" / "requirements.txt"
    nested.write_text("polars>=2.0\n", encoding="utf-8")

    second = bootstrap.requirements_fingerprint(tmp_path)

    assert first != second


def test_bootstrap_installs_validates_and_exposes_dependencies(
    tmp_path: Path,
) -> None:
    bootstrap = load_bootstrap()
    plugin_root = tmp_path / "plugin"
    data_dir = tmp_path / "plugin-data"
    env_file = tmp_path / "claude-env"
    write_requirements(plugin_root)
    commands: list[list[str]] = []

    def fake_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return completed(command)

    ready, detail = bootstrap.bootstrap_dependencies(
        plugin_root,
        data_dir,
        env_file,
        runner=fake_runner,
    )

    target = bootstrap.dependency_target(plugin_root, data_dir)
    assert ready is True
    assert detail == f"Clara dependencies installed at {target}"
    assert target.is_dir()
    assert commands[0][:4] == [sys.executable, "-m", "pip", "install"]
    assert commands[1] == [
        sys.executable,
        str(plugin_root / "scripts" / "check_dependencies.py"),
    ]
    assert env_file.read_text(encoding="utf-8") == (
        "# Clara Python dependencies\n"
        f"export PYTHONPATH={target}${{PYTHONPATH:+:${{PYTHONPATH}}}}\n"
    )


def test_bootstrap_reuses_valid_fingerprinted_dependencies(
    tmp_path: Path,
) -> None:
    bootstrap = load_bootstrap()
    plugin_root = tmp_path / "plugin"
    data_dir = tmp_path / "plugin-data"
    env_file = tmp_path / "claude-env"
    write_requirements(plugin_root)
    target = bootstrap.dependency_target(plugin_root, data_dir)
    target.mkdir(parents=True)
    commands: list[list[str]] = []

    def fake_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return completed(command)

    ready, detail = bootstrap.bootstrap_dependencies(
        plugin_root,
        data_dir,
        env_file,
        runner=fake_runner,
    )

    assert ready is True
    assert detail == f"Clara dependencies ready at {target}"
    assert commands == [
        [
            sys.executable,
            str(plugin_root / "scripts" / "check_dependencies.py"),
        ]
    ]
    assert (
        env_file.read_text(encoding="utf-8").count("# Clara Python dependencies") == 1
    )


def test_bootstrap_fails_open_when_pip_fails(tmp_path: Path) -> None:
    bootstrap = load_bootstrap()
    plugin_root = tmp_path / "plugin"
    data_dir = tmp_path / "plugin-data"
    env_file = tmp_path / "claude-env"
    write_requirements(plugin_root)

    def fake_runner(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "network unavailable")

    ready, detail = bootstrap.bootstrap_dependencies(
        plugin_root,
        data_dir,
        env_file,
        runner=fake_runner,
    )

    assert ready is False
    assert detail == "network unavailable"
    assert not env_file.exists()
    dependency_root = data_dir / bootstrap.DEPENDENCY_DIR_NAME
    assert dependency_root.is_dir()
    assert list(dependency_root.iterdir()) == []
