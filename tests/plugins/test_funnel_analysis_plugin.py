from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "funnel-analysis"
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
CORE_PATH = SCRIPT_DIR / "funnel_core.py"
DEPENDENCY_CHECKER_PATH = SCRIPT_DIR / "check_dependencies.py"
HARNESS_ROOT = ROOT / "plugins" / "_shared" / "vendor" / "modules"


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("funnel_core", CORE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_dependency_checker() -> Any:
    spec = importlib.util.spec_from_file_location(
        "funnel_check_dependencies", DEPENDENCY_CHECKER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_harness() -> Any:
    package_init = HARNESS_ROOT / "chart_harness" / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "modules.chart_harness",
        package_init,
        submodule_search_locations=[str(package_init.parent)],
    )
    assert spec and spec.loader
    modules_spec = importlib.util.spec_from_file_location(
        "modules", ROOT / "modules" / "__init__.py"
    )
    assert modules_spec and modules_spec.loader
    modules_package = importlib.util.module_from_spec(modules_spec)
    modules_spec.loader.exec_module(modules_package)
    sys.modules.setdefault("modules", modules_package)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_lead_fixture(path: Path) -> None:
    fieldnames = [
        "Company owner",
        "Original Source Type",
        "Last Activity Date",
        "Country/Region",
        "Industry",
        "Annual Revenue",
        "Lifecycle Stage",
    ]
    rows = [
        {
            "Company owner": "Owner A",
            "Original Source Type": "Organic Search",
            "Last Activity Date": "2026-01-01",
            "Country/Region": "Italy",
            "Industry": "Beauty",
            "Annual Revenue": "1000",
            "Lifecycle Stage": "Sales Accepted Lead",
        },
        {
            "Company owner": "Owner B",
            "Original Source Type": "Paid Search",
            "Last Activity Date": "2026-01-02",
            "Country/Region": "",
            "Industry": "Beauty",
            "Annual Revenue": "500",
            "Lifecycle Stage": "Prospect",
        },
        {
            "Company owner": "Owner C",
            "Original Source Type": "",
            "Last Activity Date": "2026-01-03",
            "Country/Region": "France",
            "Industry": "",
            "Annual Revenue": "0",
            "Lifecycle Stage": "Prospect",
        },
        {
            "Company owner": "",
            "Original Source Type": "Offline",
            "Last Activity Date": "",
            "Country/Region": "Spain",
            "Industry": "Retail",
            "Annual Revenue": "250",
            "Lifecycle Stage": "Prospect",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_funnel_stage_table_run_writes_deterministic_artifacts(tmp_path: Path) -> None:
    core = load_core()
    source_file = tmp_path / "leads.csv"
    output_dir = tmp_path / "funnel"
    _write_lead_fixture(source_file)

    result = core.run_funnel_analysis(source_file, output_dir, language="es")

    assert result.html_path.exists()
    assert result.csv_path.exists()
    assert result.context_path.exists()
    assert result.manifest_path.exists()
    assert result.rows[0]["stage"] == "Created records"
    assert result.rows[0]["pass_count"] == 4
    assert result.rows[2]["stage"] == "Source classified"
    assert result.rows[2]["drop_off"] == -1
    assert result.rows[4]["stage"] == "Country identified"
    assert result.rows[4]["pass_count"] == 1
    assert result.rows[-1]["stage"] == "Sales accepted"
    assert result.rows[-1]["pass_count"] == 1

    context = json.loads(result.context_path.read_text(encoding="utf-8"))
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    html = result.html_path.read_text(encoding="utf-8")
    used_recipe = json.loads(
        (output_dir / "used_recipe.json").read_text(encoding="utf-8")
    )

    assert context["capability_id"] == "funnel.stage_table"
    assert used_recipe["language"] == "es"
    assert context["table_key"] == "funnel_stage_table"
    assert context["metric_label"] == "Lead readiness funnel"
    assert context["chart_title_lines"] == [
        "Baby CRM extract",
        "Lead readiness funnel in records",
        "Sequential gates",
    ]
    assert context["title_contract"]["when"] == "Sequential gates"
    table_artifact = manifest["artifacts"][0]
    assert table_artifact["capability_id"] == "funnel.stage_table"
    assert table_artifact["table_spec_name"] == "funnel_stage_table"
    assert table_artifact["artifact_type"] == "table"
    assert result.manifest_path.name == "artifact_manifest.json"
    assert "table_definition_hash" not in table_artifact
    assert '<main class="page" data-gallery-screenshot>' in html
    assert "IBCS" not in html


def test_funnel_stage_table_rejects_missing_predicate_column(tmp_path: Path) -> None:
    core = load_core()
    source_file = tmp_path / "leads.csv"
    source_file.write_text("A,B\n1,2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing stage predicate columns"):
        core.run_funnel_analysis(source_file, tmp_path / "funnel")


def test_funnel_stage_table_accepts_explicit_stage_count_mappings(
    tmp_path: Path,
) -> None:
    core = load_core()
    source_file = tmp_path / "stage_counts.csv"
    source_file.write_text(
        "funnel_stage,entered,passed\n"
        "Awareness,100,70\n"
        "Consideration,70,30\n"
        "Purchase,30,12\n",
        encoding="utf-8",
    )
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "stage_table_mappings": {
                    "stage_column": "funnel_stage",
                    "start_count_column": "entered",
                    "pass_count_column": "passed",
                }
            }
        ),
        encoding="utf-8",
    )

    result = core.run_funnel_analysis(
        source_file, tmp_path / "mapped_funnel", recipe_path
    )

    assert [row["stage"] for row in result.rows] == [
        "Awareness",
        "Consideration",
        "Purchase",
    ]
    assert result.rows[0]["drop_off"] == -30
    assert result.rows[-1]["stage_conversion"] == pytest.approx(0.4)
    assert {stage["source"] for stage in result.context["stage_definitions"]} == {
        "stage_table_mappings"
    }


def test_dependency_checker_accepts_explicit_requirements() -> None:
    checker = load_dependency_checker()

    assert checker.main(["--requirements", "requirements.txt"]) == 0
