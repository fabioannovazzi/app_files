from __future__ import annotations

import csv
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_codex_plugin_zip.py"


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "variance_packaged_runtime_builder",
        BUILD_SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _extract_variance_component(tmp_path: Path) -> Path:
    builder = _load_builder()
    package = {item.plugin: item for item in builder.load_packages()}["clara"]
    entries = builder.expected_zip_entries(package)
    archive_path = tmp_path / "clara-plugin.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    install_root = tmp_path / "install"
    with ZipFile(archive_path) as archive:
        archive.extractall(install_root)
    return (
        install_root
        / package.package_root
        / "plugins"
        / "clara"
        / "modules"
        / "variance-analysis"
    )


def _isolated_environment(tmp_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "MPLCONFIGDIR": str(tmp_path / "matplotlib-cache"),
            "NUMBA_CACHE_DIR": str(tmp_path / "numba-cache"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    return environment


def _write_sales_fixture(path: Path) -> None:
    rows = (
        ("A", "Core", "2023", 100.0, 10.0, 5.0, 60.0),
        ("A", "Core", "2024", 150.0, 12.0, 6.0, 84.0),
        ("B", "Growth", "2023", 200.0, 20.0, 10.0, 120.0),
        ("B", "Growth", "2024", 180.0, 18.0, 12.0, 110.0),
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("product", "category", "period", "sales", "units", "discount", "cogs")
        )
        writer.writerows(rows)


def test_extracted_clara_variance_runner_imports_packaged_vendor(
    tmp_path: Path,
) -> None:
    component_root = _extract_variance_component(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    result = subprocess.run(
        [sys.executable, str(component_root / "scripts" / "run_variance.py"), "--help"],
        cwd=work_dir,
        env=_isolated_environment(tmp_path),
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "usage: run_variance.py" in result.stdout
    packaged_titles = (
        component_root / "vendor" / "modules" / "chart_harness" / "reporting_titles.py"
    )
    packaged_waterfall = (
        component_root / "vendor" / "modules" / "charting" / "draw_waterfall.py"
    )
    assert (
        packaged_titles.read_bytes()
        == (
            ROOT
            / "plugins"
            / "_shared"
            / "vendor"
            / "modules"
            / "chart_harness"
            / "reporting_titles.py"
        ).read_bytes()
    )
    assert (
        packaged_waterfall.read_bytes()
        == (
            ROOT
            / "plugins"
            / "_shared"
            / "variance"
            / "vendor"
            / "modules"
            / "charting"
            / "draw_waterfall.py"
        ).read_bytes()
    )


def test_extracted_clara_variance_runner_completes_data_only_run(
    tmp_path: Path,
) -> None:
    component_root = _extract_variance_component(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    input_path = work_dir / "sales.csv"
    output_dir = work_dir / "output"
    _write_sales_fixture(input_path)

    result = subprocess.run(
        [
            sys.executable,
            str(component_root / "scripts" / "run_variance.py"),
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--artifact-mode",
            "data_only",
        ],
        cwd=work_dir,
        env=_isolated_environment(tmp_path),
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "variance_results.csv").stat().st_size > 0
    assert (output_dir / "variance_audit.json").stat().st_size > 0
