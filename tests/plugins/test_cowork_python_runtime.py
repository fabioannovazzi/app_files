"""Opt-in cold-start integration check against the distributed Cowork ZIP."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.environ.get("RUN_COWORK_PYTHON_INTEGRATION") != "1",
    reason="Cold managed setup needs access to the published package registry",
)
def test_cowork_zip_provisions_declared_dependencies_and_loads_variance_engine(
    tmp_path: Path,
) -> None:
    """Catch missing requirements/imports hidden by the developer environment."""
    plugin_root = tmp_path / "vera"
    with ZipFile(ROOT / "plugin_packages/vera/vera-claude-plugin.zip") as archive:
        archive.extractall(plugin_root)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["CLAUDE_PLUGIN_DATA"] = str(tmp_path / "plugin-data")
    setup = subprocess.run(
        [
            sys.executable,
            "scripts/check_dependencies.py",
            "--module",
            "variance-analysis",
        ],
        cwd=plugin_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert setup.returncode == 0, setup.stdout + setup.stderr

    result = subprocess.run(
        [
            sys.executable,
            "scripts/managed_python_runtime.py",
            "--module",
            "variance-analysis",
            "run",
            "scripts/run_variance.py",
            "--help",
        ],
        cwd=plugin_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--artifact-mode" in result.stdout
