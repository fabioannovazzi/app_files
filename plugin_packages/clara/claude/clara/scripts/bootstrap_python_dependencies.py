#!/usr/bin/env python3
"""Prepare Clara's persistent managed Python runtime for Claude Cowork."""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable

__all__ = [
    "bootstrap_dependencies",
    "dependency_target",
    "main",
    "plugin_data_dir",
    "plugin_root",
    "requirements_fingerprint",
    "write_pythonpath",
]

Runner = Callable[..., subprocess.CompletedProcess[str]]
DEPENDENCY_DIR_NAME = "python-dependencies"


def _load_runtime():
    path = Path(__file__).with_name("managed_python_runtime.py")
    spec = importlib.util.spec_from_file_location("clara_bootstrap_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load managed Python runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_RUNTIME = _load_runtime()


def plugin_root() -> Path:
    """Return the installed Clara plugin root."""

    configured = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("PLUGIN_ROOT")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else Path(__file__).resolve().parents[1]
    )


def plugin_data_dir() -> Path:
    """Return Clara's user-scoped persistent data directory."""

    return _RUNTIME.plugin_data_dir(plugin_root())


def requirements_fingerprint(root: Path) -> str:
    """Return the fingerprint for Clara's core requirement graph."""

    return _RUNTIME.requirements_fingerprint(_RUNTIME.select_runtime(root))


def dependency_target(root: Path, data_dir: Path) -> Path:
    """Return Clara's core managed dependency target."""

    return _RUNTIME.dependency_target(_RUNTIME.select_runtime(root), data_dir)


def write_pythonpath(target: Path, env_file: Path | None) -> None:
    """Expose the virtual environment to subsequent Claude shell commands."""

    if env_file is None:
        return
    env_file.parent.mkdir(parents=True, exist_ok=True)
    marker = "# Clara Python dependencies"
    existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    if marker in existing:
        return
    quoted_target = shlex.quote(str(target))
    quoted_scripts = shlex.quote(str(_RUNTIME.runtime_python(target).parent))
    with env_file.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(
            f"{marker}\n"
            f"export VIRTUAL_ENV={quoted_target}\n"
            f"export PATH={quoted_scripts}${{PATH:+:${{PATH}}}}\n"
        )


def bootstrap_dependencies(
    root: Path,
    data_dir: Path,
    env_file: Path | None,
    *,
    runner: Runner = subprocess.run,
) -> tuple[bool, str]:
    """Install or reuse Clara's managed core target and expose it to Cowork."""

    ready, target, detail = _RUNTIME.ensure_runtime(
        root,
        data_dir=data_dir,
        runner=runner,
    )
    if ready:
        write_pythonpath(target, env_file)
    return ready, detail


def main() -> int:
    """Run the fail-open SessionStart dependency bootstrap."""

    root = plugin_root()
    data_dir = plugin_data_dir()
    env_file_value = os.environ.get("CLAUDE_ENV_FILE")
    env_file = Path(env_file_value).resolve() if env_file_value else None
    try:
        ready, detail = bootstrap_dependencies(root, data_dir, env_file)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        ready, detail = False, str(error)
    if not ready:
        message = (
            "Clara could not prepare its managed Python runtime in the user "
            f"sandbox: {detail}. File-based work remains available, but "
            "Python-backed workflows must rerun the dependency bootstrap."
        )
        print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
