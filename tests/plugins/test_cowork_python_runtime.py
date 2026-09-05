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
@pytest.mark.parametrize(
    "plugin,module,entrypoint",
    [
        ("vera", "variance-analysis", "run_variance.py"),
        ("clara", "period-comparison", "run_period_comparison.py"),
        ("clara", "reporting-engine", "dataset_intake.py"),
        ("clara", "business-planning", "run_business_plan.py"),
        ("clara", "distribution-analysis", "run_distribution.py"),
        ("clara", "mix-contribution-analysis", "run_mix_contribution.py"),
        ("clara", "scatter-bubble-analysis", "run_scatter_bubble.py"),
        ("clara", "set-overlap-analysis", "run_set_overlap.py"),
        ("vera", "passive-invoice-audit", "run_audit.py"),
        ("vera", "bilancio-xbrl-it", "xbrl_case.py"),
        ("vera", "bandi-agevolazioni", "validate_application.py"),
    ],
)
def test_cowork_zip_provisions_declared_dependencies_and_loads_variance_engine(
    tmp_path: Path,
    plugin: str,
    module: str,
    entrypoint: str,
) -> None:
    """Catch missing requirements/imports hidden by the developer environment."""
    plugin_root = tmp_path / f"{plugin}~g2"
    with ZipFile(
        ROOT / f"plugin_packages/{plugin}/{plugin}-claude-plugin.zip"
    ) as archive:
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
            module,
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
            module,
            "run",
            f"scripts/{entrypoint}",
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
    assert "usage:" in result.stdout.lower()


@pytest.mark.skipif(
    os.environ.get("RUN_COWORK_PYTHON_INTEGRATION") != "1",
    reason="Cold managed setup needs access to the published package registry",
)
@pytest.mark.parametrize(
    "capability,bindings,artifact",
    [
        (
            "period_comparison.trend",
            {"period_axis": "Date", "comparison_metric": "Sales"},
            "year_over_year_line.html",
        ),
        (
            "distribution.boxplot",
            {"distribution_metric": "Sales", "panel_dimension": "Brand"},
            "boxplot.html",
        ),
    ],
)
def test_cowork_zip_renders_through_component_managed_runtime(
    tmp_path: Path, capability: str, bindings: dict[str, str], artifact: str
) -> None:
    """Exercise lazy chart imports absent from entrypoint --help checks."""
    import json

    plugin_root = tmp_path / "clara~g2"
    with ZipFile(ROOT / "plugin_packages/clara/clara-claude-plugin.zip") as archive:
        archive.extractall(plugin_root)
    dataset = tmp_path / "synthetic_sales.csv"
    dataset.write_text(
        "Date,Brand,Sales\n"
        "2025-01-31,Alpha,100\n2025-02-28,Alpha,110\n2025-03-31,Alpha,120\n"
        "2026-01-31,Alpha,110\n2026-02-28,Alpha,120\n2026-03-31,Alpha,130\n"
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["CLAUDE_PLUGIN_DATA"] = str(tmp_path / "plugin-data")
    output = tmp_path / "output"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/managed_python_runtime.py",
            "--module",
            "reporting-engine",
            "run",
            "scripts/render_capability.py",
            capability,
            str(dataset),
            "--output-dir",
            str(output),
            "--role-bindings-json",
            json.dumps(bindings),
            "--options-json",
            json.dumps(
                {
                    "current_period_label": "2026",
                    "previous_period_label": "2025",
                    "period_window": {
                        "current": {"year": 2026, "month_cutoff": 3},
                        "previous": {"year": 2025, "month_cutoff": 3},
                    },
                }
            ),
            "--currency",
            "EUR",
            "--artifact-mode",
            "data_and_render",
        ],
        cwd=plugin_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((output / "render_manifest.json").read_text())
    assert manifest["runner"]["status"] == "ok"
    chart_path = next(
        path
        for path in (output / artifact, output / Path(artifact).with_suffix(".png"))
        if path.is_file()
    )
    content = chart_path.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n") or b"Plotly.newPlot" in content
