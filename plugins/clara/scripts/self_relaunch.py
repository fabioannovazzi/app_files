"""Run documented CLIs with their declared, managed Python dependencies."""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from pathlib import Path

__all__ = ["ensure_running_in_managed_venv"]


def ensure_running_in_managed_venv(entrypoint: str) -> None:
    """Relaunch before workflow imports, preserving arguments, cwd and exit status."""
    script = Path(entrypoint).resolve()
    root = next(
        (
            parent
            for parent in script.parents
            if (parent / "scripts" / "managed_python_runtime.py").is_file()
        ),
        Path(__file__).resolve().parents[1],
    )
    runtime_path = root / "scripts" / "managed_python_runtime.py"
    spec = importlib.util.spec_from_file_location(
        "entrypoint_managed_runtime", runtime_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load managed runtime: {runtime_path}")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    component = script.parent.parent
    if script.is_relative_to(root):
        relative = script.relative_to(root)
        module = relative.parts[1] if relative.parts[0] == "modules" else None
    else:
        module = component.name
    requirements = ["requirements.txt"]
    if module == "reporting-engine" and script.name in {
        "render_capability.py",
        "run_capability.py",
        "mechanical_acceptance.py",
    }:
        requirements.append("requirements-render.txt")
    target = runtime.activate_runtime(root, module, requirements)
    # Compare virtual-environment prefixes, never resolved interpreter symlinks:
    # multiple venv executables can resolve to the same system Python binary.
    if target is not None and Path(sys.prefix).resolve() == target.resolve():
        return
    ready, target, detail = runtime.ensure_runtime(
        root, module, requirements=requirements
    )
    if not ready:
        logging.error("Managed Python runtime setup failed: %s", detail)
        raise SystemExit(1)
    if Path(sys.prefix).resolve() == target.resolve():
        return
    completed = subprocess.run(
        [str(runtime.runtime_python(target)), str(script), *sys.argv[1:]],
        cwd=Path.cwd(),
        env=runtime.runtime_environment(target),
        check=False,
    )
    raise SystemExit(completed.returncode)
