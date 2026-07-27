#!/usr/bin/env python3
"""Install Clara's declared Python requirements into user-scoped plugin data."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
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

    configured = os.environ.get("CLAUDE_PLUGIN_DATA") or os.environ.get("PLUGIN_DATA")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".cache" / "mparanza" / "clara").resolve()


def _included_requirement_files(
    path: Path,
    *,
    seen: set[Path] | None = None,
) -> list[Path]:
    """Return a requirement file and its local recursive ``-r`` includes."""

    visited = seen if seen is not None else set()
    resolved = path.resolve()
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
        if not include:
            continue
        included_path = (resolved.parent / include).resolve()
        files.extend(_included_requirement_files(included_path, seen=visited))
    return files


def requirements_fingerprint(root: Path) -> str:
    """Return a stable fingerprint for Clara's required Python packages."""

    digest = hashlib.sha256()
    for path in _included_requirement_files(root / "requirements.txt"):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def dependency_target(root: Path, data_dir: Path) -> Path:
    """Return the fingerprinted user-scoped dependency directory."""

    return data_dir / DEPENDENCY_DIR_NAME / requirements_fingerprint(root)


def _python_environment(target: Path) -> dict[str, str]:
    """Return an environment that imports packages from ``target`` first."""

    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{target}{os.pathsep}{existing}" if existing else str(target)
    )
    return environment


def _dependencies_ready(
    root: Path,
    target: Path,
    *,
    runner: Runner = subprocess.run,
) -> bool:
    """Return whether Clara's complete required dependency set is importable."""

    if not target.is_dir():
        return False
    completed = runner(
        [sys.executable, str(root / "scripts" / "check_dependencies.py")],
        cwd=root,
        env=_python_environment(target),
        capture_output=True,
        check=False,
        text=True,
    )
    return completed.returncode == 0


def write_pythonpath(target: Path, env_file: Path | None) -> None:
    """Expose the dependency target to subsequent Claude shell commands."""

    if env_file is None:
        return
    env_file.parent.mkdir(parents=True, exist_ok=True)
    marker = "# Clara Python dependencies"
    existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    if marker in existing:
        return
    quoted_target = shlex.quote(str(target))
    with env_file.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(
            f"{marker}\n"
            f"export PYTHONPATH={quoted_target}${{PYTHONPATH:+:${{PYTHONPATH}}}}\n"
        )


def bootstrap_dependencies(
    root: Path,
    data_dir: Path,
    env_file: Path | None,
    *,
    runner: Runner = subprocess.run,
) -> tuple[bool, str]:
    """Install and expose declared dependencies, returning status and detail."""

    target = dependency_target(root, data_dir)
    if _dependencies_ready(root, target, runner=runner):
        write_pythonpath(target, env_file)
        return True, f"Clara dependencies ready at {target}"

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent)
    ).resolve()
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--target",
        str(temporary),
        "-r",
        str(root / "requirements.txt"),
    ]
    completed = runner(
        command,
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        shutil.rmtree(temporary)
        detail = (completed.stderr or completed.stdout).strip()
        return False, detail or "pip install returned a non-zero exit status"
    if not _dependencies_ready(root, temporary, runner=runner):
        shutil.rmtree(temporary)
        return False, "declared requirements remained unavailable after installation"

    if target.exists():
        shutil.rmtree(target)
    temporary.replace(target)
    write_pythonpath(target, env_file)
    return True, f"Clara dependencies installed at {target}"


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
            "Clara could not install its declared Python requirements in the "
            f"user sandbox: {detail}. File-based work remains available, but "
            "Python-backed workflows must rerun the dependency bootstrap."
        )
        print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
