from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_codex_plugin_zip import (
    load_vendor_module_config,
    shared_vendor_module_entries,
)

ROOT = Path(__file__).resolve().parents[2]

COMPONENT_RUNNERS = (
    (
        "distribution-analysis",
        "run_distribution.py",
        "legacy_distribution_charting",
        "cleanup_legacy_imports",
    ),
    (
        "period-comparison",
        "run_period_comparison.py",
        "period_core",
        "cleanup_legacy_imports",
    ),
    (
        "scatter-bubble-analysis",
        "run_scatter_bubble.py",
        "legacy_scatter_bubble_charting",
        "cleanup_legacy_imports",
    ),
    (
        "set-overlap-analysis",
        "run_set_overlap.py",
        "set_overlap_core",
        "_cleanup_legacy_imports",
    ),
)

ISOLATED_RUNNER_PROBE = r"""
import importlib
import runpy
import sys
from pathlib import Path

component_root = Path(sys.argv[1]).resolve()
runner_path = component_root / "scripts" / sys.argv[2]
cleanup_module_name = sys.argv[3]
cleanup_function_name = sys.argv[4]
repo_root = Path(sys.argv[5]).resolve()
vendor_root = (component_root / "vendor").resolve()
vendor_modules_root = vendor_root / "modules"

repo_paths = [
    Path(item).resolve()
    for item in sys.path
    if item and Path(item).exists()
]
if repo_root in repo_paths:
    raise AssertionError(f"repository leaked into isolated sys.path: {repo_paths}")

stale_root = component_root.parent / f"{component_root.name}-stale"
stale_modules = stale_root / "modules"
stale_modules.mkdir(parents=True)
(stale_modules / "__init__.py").write_text("ORIGIN = 'stale'\n", encoding="utf-8")
sys.path.insert(0, str(stale_root))
import modules

if getattr(modules, "ORIGIN", None) != "stale":
    raise AssertionError("failed to preload the stale modules package")
sys.path.remove(str(stale_root))

sys.path.insert(0, str(component_root / "scripts"))
sys.argv = [str(runner_path), "--help"]
try:
    runpy.run_path(str(runner_path), run_name="__main__")
except SystemExit as exc:
    if exc.code not in (None, 0):
        raise

chart_harness = importlib.import_module("modules.chart_harness")
module_path = Path(chart_harness.__file__).resolve()
if not module_path.is_relative_to(vendor_modules_root):
    raise AssertionError(f"runner used the wrong modules tree: {module_path}")

cleanup_module = importlib.import_module(cleanup_module_name)
getattr(cleanup_module, cleanup_function_name)()
leaked_modules = [
    name
    for name, module in sys.modules.items()
    if (name == "modules" or name.startswith("modules."))
    and getattr(module, "__file__", None)
    and Path(module.__file__).resolve().is_relative_to(vendor_modules_root)
]
if leaked_modules:
    raise AssertionError(f"vendored modules were not cleaned up: {leaked_modules}")
if str(vendor_root) in sys.path:
    raise AssertionError("component vendor path was not cleaned up")
"""


def _copy_packaged_component(component_name: str, destination: Path) -> Path:
    """Copy a component and inject the same vendor files as the ZIP builder."""

    component_root = destination / component_name
    shutil.copytree(ROOT / "plugins" / component_name, component_root)

    vendor_config = load_vendor_module_config()[component_name]
    for relative, source in shared_vendor_module_entries(vendor_config).items():
        target = component_root / "vendor" / "modules" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return component_root


@pytest.mark.parametrize(
    ("component_name", "runner_name", "cleanup_module", "cleanup_function"),
    COMPONENT_RUNNERS,
)
def test_packaged_chart_component_runner_uses_local_vendor_without_repo_pythonpath(
    tmp_path: Path,
    component_name: str,
    runner_name: str,
    cleanup_module: str,
    cleanup_function: str,
) -> None:
    component_root = _copy_packaged_component(component_name, tmp_path)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            ISOLATED_RUNNER_PROBE,
            str(component_root),
            runner_name,
            cleanup_module,
            cleanup_function,
            str(ROOT),
        ],
        cwd=component_root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert "usage:" in completed.stdout
