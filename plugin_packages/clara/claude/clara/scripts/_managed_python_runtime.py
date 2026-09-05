#!/usr/bin/env python3
"""Manage persistent Python dependency targets for packaged plugins."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

__all__ = [
    "READY_FILENAME",
    "NETWORK_PERMISSION_REQUIRED",
    "RuntimeSelection",
    "activate_runtime",
    "dependency_target",
    "ensure_runtime",
    "main",
    "plugin_data_dir",
    "requirements_fingerprint",
    "runtime_environment",
    "runtime_key",
    "runtime_python",
    "select_runtime",
]

Runner = Callable[..., subprocess.CompletedProcess[str]]
READY_FILENAME = ".mparanza-python-runtime.json"
NETWORK_PERMISSION_REQUIRED = "MPARANZA_NETWORK_PERMISSION_REQUIRED"
DEPENDENCY_DIR_NAME = "python-dependencies"
LOGGER = logging.getLogger(__name__)

_NETWORK_FAILURE_MARKERS = (
    "failed to resolve",
    "name or service not known",
    "nodename nor servname provided",
    "temporary failure in name resolution",
    "network is unreachable",
    "connection refused",
    "newconnectionerror",
    "proxyerror",
)
_PLUGIN_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class RuntimeSelection:
    """One plugin or component dependency scope."""

    plugin_root: Path
    requirement_root: Path
    requirements_files: tuple[Path, ...]
    scope: str

    @property
    def requirements_file(self) -> Path:
        """Return the first selected requirements file for compatibility."""

        return self.requirements_files[0]


def _included_requirement_files(
    path: Path,
    *,
    requirement_root: Path | None = None,
    seen: set[Path] | None = None,
) -> list[Path]:
    """Return a requirement file and its recursive local includes."""

    visited = seen if seen is not None else set()
    resolved = path.resolve()
    if requirement_root is not None and not resolved.is_relative_to(
        requirement_root.resolve()
    ):
        raise ValueError(f"Included requirements file is outside component: {path}")
    if resolved in visited:
        return []
    visited.add(resolved)
    files = [resolved]
    for raw_line in resolved.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        include = ""
        if line.startswith("-r "):
            include = line[3:].strip()
        elif line.startswith("--requirement "):
            include = line[len("--requirement ") :].strip()
        if include:
            files.extend(
                _included_requirement_files(
                    resolved.parent / include,
                    requirement_root=requirement_root,
                    seen=visited,
                )
            )
    return files


def select_runtime(
    plugin_root: Path,
    module: str | None = None,
    requirements: Sequence[str | Path] | None = None,
) -> RuntimeSelection:
    """Resolve the requirements owned by a plugin or embedded component."""

    root = plugin_root.resolve()
    if module is None:
        requirement_root = root
        scope = "core"
    else:
        try:
            registry = json.loads(
                (root / "components.json").read_text(encoding="utf-8")
            )
            components = registry["plugins"] + registry.get("internal_modules", [])
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("Plugin component registry is unavailable") from error
        if not isinstance(components, list) or not all(
            isinstance(name, str) for name in components
        ):
            raise ValueError("Plugin component registry is unavailable")
        if module not in components:
            raise ValueError(f"Unknown plugin component: {module}")
        packaged = root / "modules" / module
        source = root.parent / module
        requirement_root = packaged if packaged.is_dir() else source
        scope = f"modules/{module}"
    if not requirement_root.is_dir():
        raise ValueError(f"Unknown plugin component: {module}")
    selected_names = requirements or ("requirements.txt",)
    requirements_files: list[Path] = []
    for name in selected_names:
        candidate = Path(name)
        if candidate.is_absolute():
            raise ValueError(f"Requirements file must be relative: {candidate}")
        resolved = (requirement_root / candidate).resolve()
        if not resolved.is_relative_to(requirement_root):
            raise ValueError(f"Requirements file is outside component: {candidate}")
        if not resolved.is_file():
            raise ValueError(f"Requirements file not found: {resolved}")
        if resolved not in requirements_files:
            requirements_files.append(resolved)
    return RuntimeSelection(
        plugin_root=root,
        requirement_root=requirement_root.resolve(),
        requirements_files=tuple(requirements_files),
        scope=scope,
    )


def requirements_fingerprint(selection: RuntimeSelection) -> str:
    """Return a stable fingerprint for the selected requirement graph."""

    digest = hashlib.sha256()
    seen: set[Path] = set()
    for requirements_file in selection.requirements_files:
        for path in _included_requirement_files(
            requirements_file,
            requirement_root=selection.requirement_root,
            seen=seen,
        ):
            relative = path.relative_to(selection.requirement_root)
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()[:16]


def runtime_key() -> str:
    """Return the Python ABI and platform key for native wheel compatibility."""

    implementation = getattr(sys.implementation, "cache_tag", None) or "python"
    platform = sysconfig.get_platform().replace("/", "-").replace("\\", "-")
    return f"{implementation}-{platform}"


def _plugin_name(plugin_root: Path) -> str:
    """Return a path-safe stable name instead of a marketplace version folder."""

    root = plugin_root.resolve()
    name = root.name
    for manifest_directory in (".codex-plugin", ".claude-plugin"):
        manifest = root / manifest_directory / "plugin.json"
        try:
            name = json.loads(manifest.read_text(encoding="utf-8"))["name"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            continue
        break
    if not isinstance(name, str) or _PLUGIN_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError("Plugin manifest name is not path-safe")
    return name


def _codex_data_dir(plugin_root: Path) -> Path:
    """Return a stable user-private path that Claude permits runtime writes to."""

    if hasattr(os, "getuid"):
        user_key = f"uid-{os.getuid()}"
    else:
        home_fingerprint = hashlib.sha256(
            str(Path.home().resolve()).casefold().encode("utf-8")
        ).hexdigest()[:12]
        user_key = f"user-{home_fingerprint}"
    return (
        Path(tempfile.gettempdir())
        / "mparanza-managed-python"
        / user_key
        / _plugin_name(plugin_root)
    ).resolve()


def _directory_is_writable(path: Path, *, private: bool) -> bool:
    """Probe actual write access because sandbox permissions are not inferable."""

    probe_path: Path | None = None
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if private:
            path.chmod(0o700)
        with tempfile.NamedTemporaryFile(
            dir=path,
            prefix=".mparanza-write-probe-",
            delete=False,
        ) as probe:
            probe_path = Path(probe.name)
        probe_path.unlink()
    except OSError:
        if probe_path is not None:
            try:
                probe_path.unlink()
            except OSError:
                pass
        return False
    return True


def plugin_data_dir(plugin_root: Path) -> Path:
    """Return a writable, user-scoped data directory for one plugin."""

    configured = os.environ.get("CLAUDE_PLUGIN_DATA") or os.environ.get("PLUGIN_DATA")
    candidates: list[tuple[Path, bool]] = []
    if configured:
        candidates.append((Path(configured).expanduser().resolve(), False))
    if os.environ.get("CODEX_SANDBOX"):
        candidates.append((_codex_data_dir(plugin_root), True))
    candidates.append(
        (
            (Path.home() / ".cache" / "mparanza" / _plugin_name(plugin_root)).resolve(),
            True,
        )
    )
    for candidate, private in candidates:
        if _directory_is_writable(candidate, private=private):
            return candidate
    return candidates[0][0]


def _network_permission_detail(detail: str) -> str:
    """Tag mechanically identifiable network denial for a Claude approval retry."""

    normalized = detail.casefold()
    if not any(marker in normalized for marker in _NETWORK_FAILURE_MARKERS):
        return detail
    return (
        f"{NETWORK_PERMISSION_REQUIRED}: the declared package index could not be "
        "reached. In Claude, retry this exact managed-runtime command with host "
        f"network access approval.\n{detail}"
    )


def _process_detail(completed: subprocess.CompletedProcess[str]) -> str:
    """Return all non-empty captured output from a failed subprocess."""

    return "\n".join(
        output.strip()
        for output in (completed.stdout, completed.stderr)
        if output and output.strip()
    )


def _bootstrap_pip(
    target: Path,
    *,
    runner: Runner,
) -> tuple[list[str] | None, dict[str, str], str]:
    """Return a pip command that installs into a pip-less virtual environment."""

    target_python = runtime_python(target)
    base_environment = dict(os.environ)
    base_environment.pop("PYTHONHOME", None)
    base_environment.pop("PYTHONPATH", None)
    base_pip = [
        sys.executable,
        "-m",
        "pip",
        "--python",
        str(target_python),
    ]
    probe = runner(
        [*base_pip, "--version"],
        cwd=target,
        env=base_environment,
        capture_output=True,
        check=False,
        text=True,
    )
    if probe.returncode == 0:
        return base_pip, base_environment, ""

    target_environment = runtime_environment(target)
    target_environment.pop("PYTHONPATH", None)
    ensured = runner(
        [
            str(target_python),
            "-m",
            "ensurepip",
            "--upgrade",
            "--default-pip",
        ],
        cwd=target,
        env=target_environment,
        capture_output=True,
        check=False,
        text=True,
    )
    if ensured.returncode == 0:
        return [str(target_python), "-m", "pip"], target_environment, ""

    probe_detail = _process_detail(probe) or "no captured output"
    ensurepip_detail = _process_detail(ensured) or "no captured output"
    return (
        None,
        target_environment,
        (
            "Managed pip bootstrap failed.\n"
            f"Base pip probe returned exit status {probe.returncode}:\n{probe_detail}\n"
            f"Target ensurepip returned exit status {ensured.returncode}:\n"
            f"{ensurepip_detail}"
        ),
    )


def dependency_target(
    selection: RuntimeSelection,
    data_dir: Path | None = None,
) -> Path:
    """Return the selected fingerprinted dependency target."""

    base = (
        data_dir.resolve()
        if data_dir is not None
        else plugin_data_dir(selection.plugin_root)
    )
    return (
        base
        / DEPENDENCY_DIR_NAME
        / selection.scope
        / runtime_key()
        / requirements_fingerprint(selection)
    )


def runtime_environment(target: Path) -> dict[str, str]:
    """Return an environment bound to the managed virtual environment."""

    environment = dict(os.environ)
    executable = runtime_python(target)
    existing_path = environment.get("PATH")
    environment["PATH"] = (
        f"{executable.parent}{os.pathsep}{existing_path}"
        if existing_path
        else str(executable.parent)
    )
    environment["VIRTUAL_ENV"] = str(target)
    environment.pop("PYTHONHOME", None)
    environment["MPARANZA_MANAGED_RUNTIME_VERIFY"] = "1"
    return environment


def runtime_python(target: Path) -> Path:
    """Return the Python executable inside a managed virtual environment."""

    candidates = (
        target / "Scripts" / "python.exe",
        target / "bin" / "python3",
        target / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if os.name == "nt" else candidates[-1]


def _receipt_payload(selection: RuntimeSelection) -> dict[str, object]:
    return {
        "schema_version": 1,
        "plugin": _plugin_name(selection.plugin_root),
        "scope": selection.scope,
        "requirements_fingerprint": requirements_fingerprint(selection),
        "runtime_key": runtime_key(),
    }


def _receipt_matches(selection: RuntimeSelection, target: Path) -> bool:
    try:
        payload = json.loads((target / READY_FILENAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload == _receipt_payload(selection)


def _validation_command(selection: RuntimeSelection, target: Path) -> list[str]:
    checker = selection.requirement_root / "scripts" / "check_dependencies.py"
    if not checker.is_file():
        raise ValueError(f"Dependency checker not found: {checker}")
    command = [str(runtime_python(target)), str(checker)]
    if selection.scope == "core":
        command.append("--managed-verify")
    relative_requirements = [
        path.relative_to(selection.requirement_root).as_posix()
        for path in selection.requirements_files
    ]
    if relative_requirements != ["requirements.txt"]:
        for requirement in relative_requirements:
            command.extend(("--requirements", requirement))
    return command


def _dependencies_ready(
    selection: RuntimeSelection,
    target: Path,
    *,
    runner: Runner,
    require_receipt: bool,
) -> bool:
    """Return whether the target satisfies the selected dependency checker."""

    if not target.is_dir():
        return False
    if not runtime_python(target).is_file():
        return False
    if require_receipt and not _receipt_matches(selection, target):
        return False
    try:
        completed = runner(
            _validation_command(selection, target),
            cwd=selection.requirement_root,
            env=runtime_environment(target),
            capture_output=True,
            check=False,
            text=True,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return completed.returncode == 0


def ensure_runtime(
    plugin_root: Path,
    module: str | None = None,
    *,
    requirements: Sequence[str | Path] | None = None,
    data_dir: Path | None = None,
    runner: Runner = subprocess.run,
) -> tuple[bool, Path, str]:
    """Install or reuse one persistent managed dependency target."""

    selection = select_runtime(plugin_root, module, requirements)
    target = dependency_target(selection, data_dir)
    if _dependencies_ready(
        selection,
        target,
        runner=runner,
        require_receipt=True,
    ):
        return True, target, f"Python runtime ready at {target}"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
    except OSError as error:
        return False, target, str(error)
    try:
        created = runner(
            [sys.executable, "-m", "venv", "--without-pip", str(target)],
            cwd=selection.requirement_root,
            capture_output=True,
            check=False,
            text=True,
        )
        if created.returncode != 0:
            detail = _process_detail(created)
            shutil.rmtree(target, ignore_errors=True)
            return False, target, detail or "virtual environment creation failed"
        pip_command, pip_environment, bootstrap_detail = _bootstrap_pip(
            target,
            runner=runner,
        )
        if pip_command is None:
            shutil.rmtree(target, ignore_errors=True)
            return False, target, bootstrap_detail
        install_command = [
            *pip_command,
            "install",
            "--disable-pip-version-check",
            "--no-input",
        ]
        for requirements_file in selection.requirements_files:
            install_command.extend(("-r", str(requirements_file)))
        installed = runner(
            install_command,
            cwd=selection.requirement_root,
            env=pip_environment,
            capture_output=True,
            check=False,
            text=True,
        )
        if installed.returncode != 0:
            detail = _process_detail(installed)
            shutil.rmtree(target, ignore_errors=True)
            return (
                False,
                target,
                (
                    _network_permission_detail(detail)
                    if detail
                    else "pip install returned a non-zero status"
                ),
            )
        if not _dependencies_ready(
            selection,
            target,
            runner=runner,
            require_receipt=False,
        ):
            shutil.rmtree(target, ignore_errors=True)
            return (
                False,
                target,
                "Declared requirements remained unavailable after installation",
            )
        (target / READY_FILENAME).write_text(
            json.dumps(_receipt_payload(selection), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return True, target, f"Python runtime installed at {target}"
    except (OSError, subprocess.SubprocessError) as error:
        shutil.rmtree(target, ignore_errors=True)
        return False, target, str(error)


def activate_runtime(
    plugin_root: Path,
    module: str | None = None,
    requirements: Sequence[str | Path] | None = None,
) -> Path | None:
    """Return a ready managed virtual environment without installing anything."""

    try:
        selection = select_runtime(plugin_root, module, requirements)
        target = dependency_target(selection)
    except (OSError, ValueError):
        return None
    if not _receipt_matches(selection, target):
        return None
    return target


def main(plugin_root: Path, argv: list[str] | None = None) -> int:
    """Run the managed runtime command-line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module")
    parser.add_argument(
        "--requirements",
        action="append",
        help="Requirements file relative to the selected plugin or component.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("install")
    subparsers.add_parser("status")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("script", type=Path)
    run_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "status":
        target = activate_runtime(plugin_root, args.module, args.requirements)
        if target is None:
            LOGGER.error("Managed Python runtime is not ready.")
            return 1
        LOGGER.info("Managed Python runtime is ready at %s", target)
        return 0

    ready, target, detail = ensure_runtime(
        plugin_root,
        args.module,
        requirements=args.requirements,
    )
    if not ready:
        LOGGER.error("Managed Python runtime setup failed: %s", detail)
        return 1
    if args.command == "install":
        LOGGER.info("%s", detail)
        return 0

    selection = select_runtime(plugin_root, args.module, args.requirements)
    script = (selection.requirement_root / args.script).resolve()
    if not script.is_relative_to(selection.requirement_root) or not script.is_file():
        LOGGER.error("Managed runtime script not found: %s", script)
        return 2
    completed = subprocess.run(
        [str(runtime_python(target)), str(script), *args.arguments],
        cwd=selection.requirement_root,
        env=runtime_environment(target),
        check=False,
    )
    return completed.returncode
