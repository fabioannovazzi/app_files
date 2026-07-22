from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "statement-analysis"
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
CORE_PATH = SCRIPT_DIR / "statement_core.py"
DEPENDENCY_CHECKER_PATH = SCRIPT_DIR / "check_dependencies.py"
HARNESS_ROOT = ROOT / "plugins" / "_shared" / "vendor" / "modules"


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("statement_core", CORE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_dependency_checker() -> Any:
    spec = importlib.util.spec_from_file_location(
        "statement_check_dependencies", DEPENDENCY_CHECKER_PATH
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


def _statement_rows() -> list[dict[str, Any]]:
    return [
        {
            "key": "product_revenue",
            "label": "Product revenue",
            "prefix": "+",
            "source_key": "product_revenue",
        },
        {
            "key": "service_revenue",
            "label": "Service revenue",
            "prefix": "+",
            "source_key": "service_revenue",
        },
        {
            "key": "revenue",
            "label": "Revenue",
            "line_type": "subtotal",
            "prefix": "=",
            "formula": [
                {"row": "product_revenue", "factor": 1},
                {"row": "service_revenue", "factor": 1},
            ],
        },
        {
            "key": "cost_of_sales",
            "label": "Cost of sales",
            "prefix": "-",
            "source_key": "cost_of_sales",
        },
        {
            "key": "gross_profit",
            "label": "Gross profit",
            "line_type": "subtotal",
            "prefix": "=",
            "formula": [
                {"row": "revenue", "factor": 1},
                {"row": "cost_of_sales", "factor": -1},
            ],
        },
        {
            "key": "income_tax",
            "label": "Income tax",
            "prefix": "-",
            "source_key": "income_tax",
        },
        {
            "key": "net_income",
            "label": "Net income",
            "line_type": "total",
            "prefix": "=",
            "formula": [
                {"row": "gross_profit", "factor": 1},
                {"row": "income_tax", "factor": -1},
            ],
        },
    ]


def _write_statement_fixture(path: Path) -> None:
    rows = [
        ("product_revenue", "2025", "PL", 100),
        ("product_revenue", "2025", "AC", 120),
        ("service_revenue", "2025", "PL", 25),
        ("service_revenue", "2025", "AC", 30),
        ("cost_of_sales", "2025", "PL", 40),
        ("cost_of_sales", "2025", "AC", 48),
        ("income_tax", "2025", "PL", 17),
        ("income_tax", "2025", "AC", 20),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row_key", "period", "scenario", "value"])
        writer.writerows(rows)


def _write_recipe(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "title": "Baby P&L Inc.",
                "statement_label": "Profit and loss statement",
                "unit": "mEUR",
                "scope_label": "2025 PL, AC",
                "periods": ["2025"],
                "scenarios_by_period": {"2025": ["PL", "AC"]},
                "statement_rows": _statement_rows(),
            }
        ),
        encoding="utf-8",
    )


def test_pnl_statement_table_run_writes_deterministic_artifacts(
    tmp_path: Path,
) -> None:
    core = load_core()
    source_file = tmp_path / "pnl_values.csv"
    recipe_path = tmp_path / "recipe.json"
    output_dir = tmp_path / "statement"
    _write_statement_fixture(source_file)
    _write_recipe(recipe_path)

    result = core.run_statement_analysis(
        source_file,
        output_dir,
        recipe_path,
        language="es",
    )

    assert result.html_path.exists()
    assert result.csv_path.exists()
    assert result.context_path.exists()
    assert result.manifest_path.exists()
    assert result.rows[2]["key"] == "revenue"
    assert result.rows[2]["values"] == {"2025_PL": 125.0, "2025_AC": 150.0}
    assert result.rows[4]["key"] == "gross_profit"
    assert result.rows[4]["values"] == {"2025_PL": 85.0, "2025_AC": 102.0}
    assert result.rows[-1]["key"] == "net_income"
    assert result.rows[-1]["values"] == {"2025_PL": 68.0, "2025_AC": 82.0}

    context = json.loads(result.context_path.read_text(encoding="utf-8"))
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    html = result.html_path.read_text(encoding="utf-8")
    used_recipe = json.loads(
        (output_dir / "used_recipe.json").read_text(encoding="utf-8")
    )

    assert context["capability_id"] == "statement.pnl_table"
    assert used_recipe["language"] == "es"
    assert context["table_key"] == "pnl_statement_table"
    assert context["statement_label"] == "Profit and loss statement"
    table_artifact = manifest["artifacts"][0]
    assert table_artifact["capability_id"] == "statement.pnl_table"
    assert table_artifact["table_spec_name"] == "pnl_statement_table"
    assert table_artifact["artifact_type"] == "table"
    assert result.manifest_path.name == "artifact_manifest.json"
    assert "table_definition_hash" not in table_artifact
    assert '<main class="page" data-gallery-screenshot>' in html
    assert "IBCS" not in html


def test_pnl_statement_table_rejects_missing_source_value(tmp_path: Path) -> None:
    core = load_core()
    source_file = tmp_path / "pnl_values.csv"
    recipe_path = tmp_path / "recipe.json"
    _write_statement_fixture(source_file)
    _write_recipe(recipe_path)
    text = source_file.read_text(encoding="utf-8")
    source_file.write_text(
        text.replace("income_tax,2025,AC,20\n", ""),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing value for income_tax, 2025, AC"):
        core.run_statement_analysis(source_file, tmp_path / "statement", recipe_path)


def test_pnl_statement_table_honors_source_column_mappings(tmp_path: Path) -> None:
    core = load_core()
    source_file = tmp_path / "mapped_values.csv"
    source_file.write_text(
        "line_item,fiscal_period,case_name,amount\n"
        "product_revenue,2025,PL,100\n"
        "product_revenue,2025,AC,120\n"
        "service_revenue,2025,PL,25\n"
        "service_revenue,2025,AC,30\n"
        "cost_of_sales,2025,PL,40\n"
        "cost_of_sales,2025,AC,48\n"
        "income_tax,2025,PL,17\n"
        "income_tax,2025,AC,20\n",
        encoding="utf-8",
    )
    recipe_path = tmp_path / "mapped_recipe.json"
    _write_recipe(recipe_path)
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["mappings"] = {
        "row_key_column": "line_item",
        "period_column": "fiscal_period",
        "scenario_column": "case_name",
        "value_column": "amount",
    }
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    result = core.run_statement_analysis(
        source_file, tmp_path / "mapped_statement", recipe_path
    )

    assert result.rows[2]["values"] == {"2025_PL": 125.0, "2025_AC": 150.0}
    used_recipe = json.loads(
        (result.output_dir / "used_recipe.json").read_text(encoding="utf-8")
    )
    assert used_recipe["mappings"]["value_column"] == "amount"


def test_dependency_checker_accepts_explicit_requirements() -> None:
    checker = load_dependency_checker()

    assert checker.main(["--requirements", "requirements.txt"]) == 0
