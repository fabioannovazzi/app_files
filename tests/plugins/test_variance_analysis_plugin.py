from __future__ import annotations

import importlib.util
import json
import logging
import shutil
import subprocess
import sys
import warnings
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

import polars as pl
import pytest

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "plugins" / "variance-analysis" / "scripts"
CORE_PATH = SCRIPT_DIR / "variance_core.py"
MCP_SERVER_PATH = ROOT / "plugins" / "variance-analysis" / "mcp" / "server.cjs"
RUN_VARIANCE_PATH = SCRIPT_DIR / "run_variance.py"
LEGACY_ADAPTER_PATH = SCRIPT_DIR / "legacy_adapter.py"
DEPENDENCY_CHECKER_PATH = SCRIPT_DIR / "check_dependencies.py"
ROOT_CAUSE_BRIDGE_CHART_PATH = SCRIPT_DIR / "root_cause_bridge_chart.py"
ROOT_CAUSE_CLIENT_REPORT_PATH = SCRIPT_DIR / "root_cause_client_report.py"
TOTAL_BY_DIMENSION_BRIDGE_CHART_PATH = SCRIPT_DIR / "total_by_dimension_bridge_chart.py"
IBCS_TITLES_PATH = SCRIPT_DIR / "ibcs_titles.py"
SHARED_VARIANCE_DRAW_WATERFALL_PATH = (
    ROOT
    / "plugins"
    / "_shared"
    / "variance"
    / "vendor"
    / "modules"
    / "charting"
    / "draw_waterfall.py"
)


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("variance_core", CORE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_dependency_checker() -> Any:
    spec = importlib.util.spec_from_file_location(
        "check_dependencies", DEPENDENCY_CHECKER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_run_variance() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("run_variance", RUN_VARIANCE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_legacy_adapter() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("legacy_adapter", LEGACY_ADAPTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_root_cause_bridge_chart() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "root_cause_bridge_chart", ROOT_CAUSE_BRIDGE_CHART_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_root_cause_client_report() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "root_cause_client_report", ROOT_CAUSE_CLIENT_REPORT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_total_by_dimension_bridge_chart() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "total_by_dimension_bridge_chart", TOTAL_BY_DIMENSION_BRIDGE_CHART_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_ibcs_titles() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("ibcs_titles", IBCS_TITLES_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_vendor_draw_waterfall() -> Any:
    spec = importlib.util.spec_from_file_location(
        "variance_plugin_vendor_draw_waterfall",
        SHARED_VARIANCE_DRAW_WATERFALL_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the Variance Analysis MCP server.")
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def _write_sales_fixture(path: Path) -> None:
    df = pl.DataFrame(
        {
            "product": ["A", "A", "B", "B"],
            "category": ["Cat", "Cat", "Dog", "Dog"],
            "period": ["2023", "2024", "2023", "2024"],
            "sales": [100.0, 150.0, 200.0, 180.0],
            "units": [10.0, 12.0, 20.0, 18.0],
            "discount": [5.0, 6.0, 10.0, 12.0],
            "cogs": [60.0, 84.0, 120.0, 110.0],
        }
    )
    df.write_csv(path)


def _write_variable_bridge_fixture(path: Path) -> None:
    df = pl.DataFrame(
        {
            "region": [
                "North",
                "North",
                "South",
                "South",
                "North",
                "North",
                "South",
                "South",
            ],
            "subregion": [
                "North",
                "North",
                "South",
                "South",
                "North",
                "North",
                "South",
                "South",
            ],
            "product": ["A", "A", "A", "A", "B", "B", "B", "B"],
            "period": ["2023", "2024", "2023", "2024"] * 2,
            "sales": [100.0, 130.0, 80.0, 70.0, 150.0, 120.0, 90.0, 150.0],
            "units": [10.0, 13.0, 8.0, 7.0, 15.0, 10.0, 9.0, 15.0],
        }
    )
    df.write_csv(path)


def _write_multi_dimension_variance_fixture(path: Path) -> None:
    df = pl.DataFrame(
        {
            "product_line": [
                "Road",
                "Road",
                "Road",
                "Road",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
            "product_name": [
                "Road A",
                "Road A",
                "Road B",
                "Road B",
                "Mountain A",
                "Mountain A",
                "Mountain B",
                "Mountain B",
            ],
            "region": [
                "North",
                "North",
                "South",
                "South",
                "North",
                "North",
                "South",
                "South",
            ],
            "period": ["2023", "2024"] * 4,
            "sales": [100.0, 145.0, 90.0, 120.0, 80.0, 90.0, 70.0, 75.0],
            "units": [10.0, 12.0, 9.0, 10.0, 8.0, 9.0, 7.0, 6.0],
        }
    )
    df.write_csv(path)


def _write_dense_exploded_bridge_fixture(path: Path) -> None:
    parent_names = [
        "North America Professional Channel",
        "Western Europe Retail Channel",
        "Eastern Europe Distributor Channel",
        "Latin America Marketplace Channel",
        "Middle East Franchise Channel",
        "Asia Pacific Salon Channel",
        "Global Travel Retail Channel",
    ]
    child_names = [
        "Color Revival Permanent Creme",
        "Gloss Repair Treatment Kit",
        "Hydration Rescue Styling Foam",
        "Volume Control Root Spray",
    ]
    rows: list[dict[str, Any]] = []
    for parent_index, parent in enumerate(parent_names, start=1):
        parent_direction = 1 if parent_index % 2 else -1
        for child_index, child in enumerate(child_names, start=1):
            baseline = 80.0 + parent_index * 12.0 + child_index * 3.0
            delta = parent_direction * (parent_index * 6.0 + child_index * 2.0)
            rows.append(
                {
                    "segment": parent,
                    "sku": child,
                    "period": "2023",
                    "sales": baseline,
                }
            )
            rows.append(
                {
                    "segment": parent,
                    "sku": child,
                    "period": "2024",
                    "sales": baseline + delta,
                }
            )
    pl.DataFrame(rows).write_csv(path)


def _write_period_window_fixture(path: Path) -> None:
    df = pl.DataFrame(
        {
            "product": [
                "A",
                "A",
                "A",
                "A",
                "A",
                "A",
                "A",
            ],
            "date": [
                date(2023, 10, 31),
                date(2023, 11, 30),
                date(2023, 12, 31),
                date(2024, 9, 30),
                date(2024, 10, 31),
                date(2024, 11, 30),
                date(2024, 12, 31),
            ],
            "sales": [100.0, 100.0, 100.0, 999.0, 200.0, 200.0, 200.0],
            "units": [10.0, 10.0, 10.0, 99.0, 10.0, 10.0, 10.0],
        }
    )
    df.write_csv(path)


def test_ibcs_title_uses_who_what_when_for_scenario_recipe() -> None:
    titles = load_ibcs_titles()
    recipe = {
        "source_file": "/tmp/adventureworks.xlsx",
        "language": "en",
        "mappings": {
            "baseline_period": "PL",
            "comparison_period": "AC",
        },
        "options": {"currency": "EUR", "comparison_basis": "scenario"},
    }

    title = titles.build_ibcs_title(recipe, chart_kind="standard_variance")

    assert title.lines() == ["AdventureWorks", "Sales variance | EUR", "AC vs PL"]


def test_ibcs_title_describes_rolling_period_and_small_multiples() -> None:
    titles = load_ibcs_titles()
    recipe = {
        "source_file": "/tmp/adventureworks.xlsx",
        "language": "en",
        "mappings": {
            "baseline_period": "~Jun-2018",
            "comparison_period": "~Jun-2019",
        },
        "options": {
            "currency": "EUR",
            "comparison_basis": "period",
            "period_comparison_mode": "rolling_period",
            "period_window": {"rolling_window_months": 12},
        },
    }

    title = titles.build_ibcs_title(
        recipe,
        chart_kind="standard_small_multiples",
        dimension="Productline",
    )

    assert title.lines() == [
        "AdventureWorks",
        "Sales variance by Productline | EUR",
        "~Jun-2019 vs ~Jun-2018, rolling 12 months",
    ]


@pytest.mark.parametrize(
    ("chart_kind", "expected_what"),
    [
        ("standard_variance", "Varianza de ventas | EUR"),
        (
            "pvm_decomposition_ladder",
            "Varianza de ventas: precio, unidades y mix | EUR",
        ),
        ("standard_small_multiples", "Varianza de ventas por dimensión | EUR"),
        ("total_by_dimension", "Varianza total de ventas por dimensión | EUR"),
        ("root_cause", "Varianza de ventas por causa raíz | EUR"),
        ("root_cause_total", "Varianza total de ventas por causa raíz | EUR"),
        (
            "variable_root_cause_total",
            "Varianza total de ventas por causa raíz y dimensión variable | EUR",
        ),
        (
            "root_cause_component",
            "Varianza de componentes de ventas por causa raíz | EUR",
        ),
        (
            "variable_root_cause",
            "Varianza de ventas por causa raíz y dimensión variable | EUR",
        ),
        (
            "root_cause_drilldown",
            "Desglose de causa raíz de ventas | EUR",
        ),
    ],
)
def test_ibcs_title_localizes_spanish_chart_kinds(
    chart_kind: str,
    expected_what: str,
) -> None:
    titles = load_ibcs_titles()
    recipe = {
        "language": "es",
        "mappings": {"baseline_period": "PL", "comparison_period": "AC"},
        "options": {"currency": "EUR", "comparison_basis": "scenario"},
    }

    title = titles.build_ibcs_title(recipe, chart_kind=chart_kind)

    assert title.lines() == ["Ventas", expected_what, "AC vs PL"]


def test_ibcs_title_localizes_spanish_rolling_period_framework_text() -> None:
    titles = load_ibcs_titles()
    recipe = {
        "source_file": "/tmp/adventureworks.xlsx",
        "language": "es_ES",
        "mappings": {
            "baseline_period": "~Jun-2018",
            "comparison_period": "~Jun-2019",
        },
        "options": {
            "currency": "EUR",
            "comparison_basis": "period",
            "period_comparison_mode": "rolling_period",
            "period_window": {"rolling_window_months": 12},
        },
    }

    title = titles.build_ibcs_title(
        recipe,
        chart_kind="standard_small_multiples",
        dimension="Línea de producto",
    )

    assert title.lines() == [
        "AdventureWorks",
        "Varianza de ventas por Línea de producto | EUR",
        "~Jun-2019 vs ~Jun-2018, periodo móvil de 12 meses",
    ]


@pytest.mark.parametrize(
    ("baseline", "comparison", "period_options", "expected_when"),
    [
        (
            "2023 YTD",
            "2024 YTD",
            {
                "period_comparison_mode": "year_to_date",
                "period_window": {"current": {"end_date": "2024-06-30"}},
            },
            "2024 YTD vs 2023 YTD, acumulado del año hasta 2024-06-30",
        ),
        (
            "2023",
            "2024",
            {"period_comparison_mode": "calendar_period"},
            "2024 vs 2023, periodo natural",
        ),
        (
            "2023",
            "2024",
            {"period_comparison_mode": "custom"},
            "2024 vs 2023, comparación personalizada",
        ),
    ],
)
def test_ibcs_title_localizes_spanish_period_modes(
    baseline: str,
    comparison: str,
    period_options: dict[str, Any],
    expected_when: str,
) -> None:
    titles = load_ibcs_titles()
    recipe = {
        "language": "es",
        "mappings": {
            "baseline_period": baseline,
            "comparison_period": comparison,
        },
        "options": {"comparison_basis": "period", **period_options},
    }

    title = titles.build_ibcs_title(recipe, chart_kind="standard_variance")

    assert title.when == expected_when


def test_ibcs_title_html_emphasizes_only_sales_measure_subject() -> None:
    titles = load_ibcs_titles()
    title = titles.IBCSTitle(
        "Mexico hair color",
        "Sales root-cause variance | EUR",
        "2015-09-06 vs 2015-08-30, calendar period",
    )

    assert titles.measure_line_segments(title.what) == (
        ("Sales", True),
        (" root-cause variance | EUR", False),
    )
    assert (
        titles.ibcs_title_html(title)
        == "Mexico hair color<br><b>Sales</b> root-cause variance | EUR<br>"
        "2015-09-06 vs 2015-08-30, calendar period"
    )


def test_variance_plugin_can_disable_waterfall_chart(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    variance_dir = tmp_path / "variance"
    _write_sales_fixture(input_path)

    result = core.run_variance_analysis(
        input_path,
        variance_dir,
        language="en",
        waterfall_chart=False,
    )

    assert not (variance_dir / "waterfall.png").exists()
    assert "waterfall.png" not in result.audit["outputs"]
    assert result.audit["legacy_runtime"]["waterfall_chart"]["status"] == "disabled"


def test_variance_plugin_applies_like_for_like_recipe_cohort(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    pl.DataFrame(
        {
            "product": ["Common", "Common", "New", "Lost", "Zero PY", "Zero PY"],
            "category": ["Core", "Core", "Core", "Core", "Core", "Core"],
            "period": ["PY", "AC", "AC", "PY", "AC", "PY"],
            "sales": [10.0, 12.0, 5.0, 7.0, 3.0, 0.0],
            "units": [10.0, 12.0, 5.0, 7.0, 3.0, 1.0],
        }
    ).write_csv(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_file": str(input_path),
                "language": "en",
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "PY",
                    "comparison_period": "AC",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["product"],
                    "calculation_grain": ["product"],
                },
                "options": {
                    "comparison_basis": "period",
                    "period_comparison_mode": "not_applicable",
                    "waterfall_chart": False,
                    "waterfall_small_multiples": False,
                    "root_cause_bridge": False,
                    "root_cause_bridge_alternative_sweep": False,
                    "like_for_like": {"source_dimension": "product"},
                },
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        language="en",
        waterfall_chart=False,
        waterfall_small_multiples=False,
        root_cause_bridge=False,
        root_cause_bridge_alternative_sweep=False,
    )

    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    retained_products = set(
        result.frame.select("product").unique().to_series().to_list()
    )
    cohort_audit = used_recipe["options"]["recipe_cohort_audit"]
    assert retained_products == {"Common"}
    assert cohort_audit["like_for_like"]["retained_entity_count"] == 1
    assert cohort_audit["like_for_like"]["removed_entity_count"] == 3
    assert used_recipe["options"]["cohort_definition"]["activity_rule"] == "sales > 0.0"


def test_variance_plugin_cleans_up_vendored_module_imports(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    variance_dir = tmp_path / "variance"
    _write_sales_fixture(input_path)

    core.run_variance_analysis(input_path, variance_dir, language="en")

    vendor_root = ROOT / "plugins" / "variance-analysis" / "vendor"
    shared_root = ROOT / "plugins" / "_shared" / "variance" / "vendor"
    assert str(vendor_root) not in sys.path
    assert str(shared_root) not in sys.path
    vendored_modules = [
        name
        for name, module in sys.modules.items()
        if (name == "modules" or name.startswith("modules."))
        and getattr(module, "__file__", "")
        and (
            Path(getattr(module, "__file__"))
            .resolve()
            .is_relative_to(vendor_root.resolve())
            or Path(getattr(module, "__file__"))
            .resolve()
            .is_relative_to(shared_root.resolve())
        )
    ]
    assert vendored_modules == []


def test_variance_plugin_records_waterfall_export_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    variance_dir = tmp_path / "variance"
    _write_sales_fixture(input_path)

    def fake_write_waterfall_png(
        _result: pl.DataFrame,
        _recipe: dict[str, Any],
        _output_dir: Path,
        **_kwargs: Any,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            paths=[],
            audit={
                "enabled": True,
                "artifact": "waterfall.png",
                "status": "not_written",
                "error": "export failed",
            },
        )

    monkeypatch.setattr(core, "write_waterfall_png", fake_write_waterfall_png)

    result = core.run_variance_analysis(input_path, variance_dir, language="en")

    assert (variance_dir / "variance_results.csv").exists()
    assert not (variance_dir / "waterfall.png").exists()
    assert result.audit["outputs"]["waterfall.png"] == "not_written: export failed"
    assert result.audit["legacy_runtime"]["waterfall_chart"]["error"] == "export failed"


def test_variance_plugin_writes_waterfall_small_multiples(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    variance_dir = tmp_path / "variance"
    _write_sales_fixture(input_path)

    result = core.run_variance_analysis(
        input_path,
        variance_dir,
        language="en",
        waterfall_small_multiples=True,
        waterfall_small_multiples_dimension="product",
    )

    chart_audit = result.audit["legacy_runtime"]["waterfall_chart"]
    assert (variance_dir / "waterfall.png").exists()
    assert (variance_dir / "waterfall_small_multiples.png").exists()
    assert (variance_dir / "waterfall_small_multiples_summary.csv").exists()
    assert (variance_dir / "waterfall_small_multiples_context.json").exists()
    assert chart_audit["status"] == "written"
    assert chart_audit["mode"] == "legacy_component_single"
    assert chart_audit["panel_bridge"] == "standard_variance_components"
    assert chart_audit["chart_title_lines"][1] == "Sales variance | EUR"
    assert chart_audit["small_multiples_status"] == "written"
    assert (
        chart_audit["small_multiples_audit"]["mode"]
        == "legacy_variance_small_multiples"
    )
    assert (
        chart_audit["small_multiples_audit"]["small_multiples_panel_bridge"]
        == "legacy_price_units_mix"
    )
    assert (
        chart_audit["small_multiples_audit"]["legacy_reference_function_call_mode"]
        == "executed_headless"
    )
    assert (
        chart_audit["small_multiples_audit"]["legacy_reference_function"]
        == "modules.charting.plot_charts.plot_waterfall_small_multiples"
    )
    assert chart_audit["small_multiples_audit"]["captured_chart_output_count"] == 1
    assert chart_audit["small_multiples_audit"]["captured_plotly_chart_count"] == 1
    assert (
        "modules.utilities.ui_notifier.HeadlessChartCapture"
        in chart_audit["small_multiples_audit"]["source_functions"]
    )
    assert (
        chart_audit["small_multiples_audit"]["small_multiples_dimension"] == "product"
    )
    assert (
        chart_audit["small_multiples_audit"]["chart_title_lines"][1]
        == "Sales variance by product | EUR"
    )
    assert chart_audit["small_multiples_audit"]["small_multiples_count"] == 2
    context = json.loads(
        (variance_dir / "waterfall_small_multiples_context.json").read_text()
    )
    standard_context = json.loads(
        (variance_dir / "standard_variance_context.json").read_text()
    )
    pvm_context = json.loads(
        (variance_dir / "pvm_decomposition_ladder_context.json").read_text()
    )
    summary_frame = pl.read_csv(variance_dir / "waterfall_small_multiples_summary.csv")
    assert context["status"] == "written"
    assert context["dimension"] == "product"
    assert context["chart_title_lines"] == [
        "Sales",
        "Sales variance by product | EUR",
        "2024 vs 2023, calendar period",
    ]
    assert context["title_contract"]["what"] == "Sales variance by product | EUR"
    assert standard_context["chart_title_lines"] == [
        "Sales",
        "Sales variance | EUR",
        "2024 vs 2023, calendar period",
    ]
    assert standard_context["title_contract"]["when"] == (
        "2024 vs 2023, calendar period"
    )
    assert pvm_context["chart_title_lines"] == [
        "Sales",
        "Sales variance: price, units, mix | EUR",
        "2024 vs 2023, calendar period",
    ]
    assert context["codex_interpretation_contract"]["must_review_when_written"] is True
    assert set(summary_frame["variance_type"].to_list()) == {
        "Price",
        "Units & mix",
        "Balance",
    }
    assert summary_frame.filter(pl.col("is_residual_balance")).height == 2


def test_variance_exploded_bridge_clamps_dense_dataset_for_readability(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "dense_sales.csv"
    variance_dir = tmp_path / "variance"
    _write_dense_exploded_bridge_fixture(input_path)

    result = core.run_variance_analysis(
        input_path,
        variance_dir,
        language="en",
        root_cause_bridge=False,
        root_cause_bridge_alternative_sweep=False,
        waterfall_chart=False,
        waterfall_small_multiples=False,
        total_by_dimension_bridge=True,
        total_by_dimension_bridge_dimension="segment",
        total_by_dimension_bridge_top_n=30,
        exploded_variance_bridge=True,
        exploded_variance_bridge_parent_dimension="segment",
        exploded_variance_bridge_child_dimension="sku",
        exploded_variance_bridge_parent_top_n=30,
        exploded_variance_bridge_child_top_n=9,
        exploded_variance_bridge_max_drilldowns=5,
    )

    exploded_spec = json.loads(
        (variance_dir / "exploded_variance_bridge_spec.json").read_text(
            encoding="utf-8"
        )
    )
    exploded_context = json.loads(
        (variance_dir / "exploded_variance_bridge_context.json").read_text(
            encoding="utf-8"
        )
    )
    exploded_audit = result.audit["legacy_runtime"]["exploded_variance_bridge"]
    quality_checks = {
        check["name"]: check for check in exploded_spec["visual_quality"]["checks"]
    }

    assert (variance_dir / "exploded_variance_bridge.png").exists()
    assert exploded_audit["requested_parent_top_n"] == 20
    assert exploded_audit["requested_child_top_n"] == 8
    assert exploded_audit["parent_top_n"] == 18
    assert exploded_audit["child_top_n"] == 5
    assert exploded_audit["max_drilldowns"] == 2
    assert exploded_audit["selected_drilldown_count"] == 2
    assert exploded_audit["visual_quality_status"] == "pass"
    assert exploded_audit["visual_quality_flags"] == []
    assert exploded_spec["parent"]["top_n"] == 18
    assert len(exploded_spec["children"]) == 2
    assert all(len(child["rows"]) <= 6 for child in exploded_spec["children"])
    assert exploded_context["visual_quality"]["status"] == "pass"
    assert exploded_spec["visual_quality"]["status"] == "pass"
    assert exploded_spec["visual_quality"]["flags"] == []
    assert quality_checks["parent_rows_readable"]["status"] == "pass"
    assert quality_checks["child_rows_readable_drilldown_1"]["status"] == "pass"
    assert quality_checks["child_rows_readable_drilldown_2"]["status"] == "pass"
    assert quality_checks["rendered_png_not_blank"]["status"] == "pass"
    assert quality_checks["rendered_png_not_cropped"]["status"] == "pass"


def test_waterfall_fallback_renders_plan_total_as_white_bar(tmp_path: Path) -> None:
    import plotly.graph_objects as go
    from PIL import Image
    from plotly.subplots import make_subplots

    waterfall = load_vendor_draw_waterfall()
    plan_path = tmp_path / "plan.png"
    prior_path = tmp_path / "prior.png"

    def write_chart(path: Path, baseline_label: str) -> None:
        fig = make_subplots(rows=1, cols=1, specs=[[{"type": "waterfall"}]])
        fig.add_trace(
            go.Waterfall(
                orientation="h",
                measure=["absolute", "relative", "total"],
                y=[baseline_label, "Price", "AC"],
                x=[100.0, 20.0, 120.0],
            ),
            row=1,
            col=1,
        )
        fig.update_layout(width=1000, height=380, title="AC vs baseline")
        waterfall.write_waterfall_fallback_png(fig, str(path))

    write_chart(plan_path, "PL")
    write_chart(prior_path, "PY")

    with Image.open(plan_path) as plan_image:
        plan_rgb = plan_image.convert("RGB")
        assert plan_rgb.getpixel((300, 110)) == (255, 255, 255)
        assert plan_rgb.getpixel((279, 101)) == (52, 52, 52)
    with Image.open(prior_path) as prior_image:
        prior_rgb = prior_image.convert("RGB")
        assert prior_rgb.getpixel((300, 110)) == (166, 166, 166)


def test_waterfall_fallback_decodes_title_entities() -> None:
    waterfall = load_vendor_draw_waterfall()

    assert waterfall._clean_html("Company = L&#x27;Oreal<br><b>Sales</b> variance") == (
        "Company = L'Oreal Sales variance"
    )
    assert waterfall._clean_html_lines("Company = L&#x27;Oreal<br><b>Sales</b>") == [
        "Company = L'Oreal",
        "Sales",
    ]


def test_variance_plugin_selects_small_multiples_dimension_from_ranked_candidates(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    inspection_dir = tmp_path / "inspection"
    variance_dir = tmp_path / "variance"
    _write_multi_dimension_variance_fixture(input_path)

    inspection = core.inspect_variance_inputs(input_path, inspection_dir, language="en")
    result = core.run_variance_analysis(
        input_path,
        variance_dir,
        language="en",
    )

    suggested_recipe = json.loads(
        (inspection_dir / "suggested_recipe.json").read_text()
    )
    used_recipe = json.loads((variance_dir / "used_recipe.json").read_text())
    selection = used_recipe["options"]["waterfall_small_multiples_dimension_selection"]
    chart_audit = result.audit["legacy_runtime"]["waterfall_chart"]

    assert inspection.recipe["options"]["waterfall_small_multiples"] is True
    assert suggested_recipe["options"]["waterfall_small_multiples"] is True
    assert suggested_recipe["options"]["waterfall_small_multiples_dimension"] is None
    assert used_recipe["options"]["waterfall_small_multiples"] is True
    assert (
        used_recipe["options"]["waterfall_small_multiples_dimension"] == "product_line"
    )
    assert selection["status"] == "selected_ranked_candidate"
    assert selection["dimension"] == "product_line"
    assert selection["candidates"][0]["dimension"] == "product_line"
    assert (variance_dir / "waterfall.png").exists()
    assert (variance_dir / "waterfall_small_multiples.png").exists()
    assert (variance_dir / "waterfall_small_multiples_context.json").exists()
    assert chart_audit["small_multiples_status"] == "written"
    assert (
        chart_audit["small_multiples_audit"]["small_multiples_dimension"]
        == "product_line"
    )


def test_variance_plugin_summarizes_small_multiples_other_member_panel(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    variance_dir = tmp_path / "variance"
    rows: list[dict[str, Any]] = []
    for index in range(13):
        rows.append(
            {
                "product": f"P{index:02d}",
                "period": "2023",
                "sales": 100.0,
                "units": 10.0,
            }
        )
        rows.append(
            {
                "product": f"P{index:02d}",
                "period": "2024",
                "sales": 101.0 + index,
                "units": 10.0,
            }
        )
    pl.DataFrame(rows).write_csv(input_path)

    def fake_write_waterfall_png(
        _result: pl.DataFrame,
        _recipe: dict[str, Any],
        _output_dir: Path,
        **_kwargs: Any,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            paths=[],
            audit={
                "enabled": True,
                "status": "written",
                "small_multiples_status": "written",
            },
        )

    monkeypatch.setattr(core, "write_waterfall_png", fake_write_waterfall_png)

    result = core.run_variance_analysis(input_path, variance_dir, language="en")

    context = json.loads(
        (variance_dir / "waterfall_small_multiples_context.json").read_text()
    )
    other_panel = next(
        panel for panel in context["panels"] if panel["panel_type"] == "other_members"
    )

    assert context["has_other_member_panel"] is True
    assert context["panel_count"] == 12
    assert other_panel["dimension_value"] == "Others aggregated"
    assert other_panel["included_member_count"] == 2
    assert (
        result.audit["legacy_runtime"]["waterfall_small_multiples_chart_data"][
            "has_other_member_panel"
        ]
        is True
    )


def test_variance_plugin_warns_when_inspection_output_dir_is_reused(
    tmp_path: Path,
    caplog: Any,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    inspection_dir = tmp_path / "inspection"
    _write_sales_fixture(input_path)
    inspection_dir.mkdir()
    (inspection_dir / "old_review.md").write_text("stale", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=core.LOGGER.name):
        core.inspect_variance_inputs(input_path, inspection_dir, language="en")

    assert "Inspection output directory already contains files" in caplog.text
    assert "old_review.md" in caplog.text


def test_variance_plugin_warns_when_variance_output_dir_is_reused(
    tmp_path: Path,
    caplog: Any,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "variance"
    _write_sales_fixture(input_path)
    output_dir.mkdir()
    (output_dir / "old_chart.html").write_text("stale", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=core.LOGGER.name):
        core.run_variance_analysis(input_path, output_dir, language="en")

    assert "Variance output directory already contains files" in caplog.text
    assert "old_chart.html" in caplog.text


def test_dependency_checker_collects_import_warnings(monkeypatch: Any) -> None:
    checker = load_dependency_checker()

    def fake_import_module(_module_name: str) -> object:
        warnings.warn("dependency pins are inconsistent", RuntimeWarning, stacklevel=2)
        return object()

    monkeypatch.setattr(checker.importlib, "import_module", fake_import_module)

    assert checker.collect_import_warnings("requests") == [
        "RuntimeWarning: dependency pins are inconsistent"
    ]


def test_variance_plugin_inspects_xlsx_dates_and_plan_actual_scenario(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "scenario_sales.xlsx"
    inspection_dir = tmp_path / "inspection"
    df = pl.DataFrame(
        {
            "Scenario": ["PL", "AC"],
            "Orderdate": [date(2024, 1, 1), date(2024, 1, 1)],
            "Customer": ["Buyer", "Buyer"],
            "Gender": ["F", "F"],
            "Category": ["Bikes", "Bikes"],
            "Subcategory": ["Road Bikes", "Road Bikes"],
            "Productline": ["R", "R"],
            "Region": ["Australia", "Australia"],
            "Product": ["Bike", "Bike"],
            "Units": [1.0, 1.0],
            "Salesamount": [100.0, 120.0],
            "Discount": [5.0, 6.0],
            "Cogs": [60.0, 72.0],
        }
    )
    df.write_excel(input_path)

    inspection = core.inspect_variance_inputs(input_path, inspection_dir, language="en")

    inspection_payload = json.loads((inspection_dir / "inspection.json").read_text())
    recipe_payload = json.loads((inspection_dir / "suggested_recipe.json").read_text())

    assert inspection.payload["warnings"] == []
    assert inspection_payload["sample_rows"][0]["Orderdate"] == "2024-01-01"
    assert recipe_payload["mappings"]["period_column"] == "Scenario"
    assert recipe_payload["mappings"]["baseline_period"] == "PL"
    assert recipe_payload["mappings"]["comparison_period"] == "AC"
    assert recipe_payload["options"]["comparison_basis"] == "scenario"
    assert recipe_payload["options"]["period_comparison_mode"] == "not_applicable"
    assert recipe_payload["options"]["currency"] == "EUR"
    assert recipe_payload["mappings"]["amount_column"] == "Salesamount"
    assert recipe_payload["mappings"]["units_column"] == "Units"
    assert recipe_payload["mappings"]["dimensions"] == [
        "Category",
        "Subcategory",
        "Productline",
        "Region",
    ]
    assert recipe_payload["mappings"]["calculation_grain"] == ["Product", "Customer"]


def test_variance_plugin_prepares_legacy_rolling_window_buckets(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "rolling.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    _write_period_window_fixture(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "date",
                    "date_column": "date",
                    "baseline_period": "placeholder_baseline",
                    "comparison_period": "placeholder_comparison",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["product"],
                    "calculation_grain": ["product"],
                },
                "options": {
                    "comparison_basis": "period",
                    "period_comparison_mode": "rolling_period",
                    "rolling_window_months": 3,
                    "rolling_comparison": "prior_year",
                },
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        language="en",
    )

    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    period_window = used_recipe["options"]["period_window"]
    row = result.frame.to_dicts()[0]

    assert used_recipe["mappings"]["period_column"] == "__variance_period_bucket"
    assert used_recipe["mappings"]["baseline_period"] == "~Dec-2023"
    assert used_recipe["mappings"]["comparison_period"] == "~Dec-2024"
    assert period_window["baseline"]["start_date"] == "2023-10-01"
    assert period_window["comparison"]["start_date"] == "2024-10-01"
    assert period_window["row_counts"] == {"~Dec-2023": 3, "~Dec-2024": 3}
    assert row["amount_baseline"] == 300.0
    assert row["amount_comparison"] == 600.0
    assert row["total_delta"] == 300.0


def test_variance_plugin_accepts_period_type_rolling_alias(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "rolling_alias.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    _write_period_window_fixture(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "date",
                    "date_column": "date",
                    "baseline_period": "placeholder_baseline",
                    "comparison_period": "placeholder_comparison",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["product"],
                    "calculation_grain": ["product"],
                },
                "options": {
                    "comparison_basis": "period",
                    "period_type": "rolling",
                    "rolling_window_months": 3,
                    "rolling_comparison": "prior_year",
                },
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        language="en",
    )

    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    row = result.frame.to_dicts()[0]

    assert used_recipe["options"]["period_type"] == "rolling"
    assert used_recipe["options"]["period_comparison_mode"] == "rolling_period"
    assert used_recipe["mappings"]["baseline_period"] == "~Dec-2023"
    assert used_recipe["mappings"]["comparison_period"] == "~Dec-2024"
    assert row["amount_baseline"] == 300.0
    assert row["amount_comparison"] == 600.0


def test_variance_plugin_derives_rolling_week_window_from_period_grain(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "rolling_week.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    pl.DataFrame(
        {
            "product": ["A", "A", "A", "A", "A", "A"],
            "date": [
                date(2023, 1, 1),
                date(2023, 1, 7),
                date(2023, 1, 8),
                date(2024, 1, 1),
                date(2024, 1, 7),
                date(2023, 12, 31),
            ],
            "sales": [10.0, 20.0, 999.0, 30.0, 40.0, 888.0],
            "units": [1.0, 1.0, 99.0, 1.0, 1.0, 88.0],
        }
    ).write_csv(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "date",
                    "date_column": "date",
                    "baseline_period": "placeholder_baseline",
                    "comparison_period": "placeholder_comparison",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["product"],
                    "calculation_grain": ["product"],
                },
                "options": {
                    "comparison_basis": "period",
                    "period_type": "rolling",
                    "period_grain": "week",
                    "rolling_comparison": "prior_year",
                },
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        language="en",
    )

    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    period_window = used_recipe["options"]["period_window"]
    row = result.frame.to_dicts()[0]

    assert used_recipe["options"]["rolling_window_days"] == 7
    assert "rolling_window_months" not in used_recipe["options"]
    assert used_recipe["mappings"]["baseline_period"] == (
        "prior_year_7d_2023-01-01_2023-01-07"
    )
    assert used_recipe["mappings"]["comparison_period"] == (
        "rolling_7d_2024-01-01_2024-01-07"
    )
    assert period_window["baseline"]["start_date"] == "2023-01-01"
    assert period_window["comparison"]["start_date"] == "2024-01-01"
    assert period_window["row_counts"] == {
        "prior_year_7d_2023-01-01_2023-01-07": 2,
        "rolling_7d_2024-01-01_2024-01-07": 2,
    }
    assert row["amount_baseline"] == 30.0
    assert row["amount_comparison"] == 70.0


def test_variance_plugin_prepares_legacy_ytd_window_buckets(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "ytd.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    df = pl.DataFrame(
        {
            "product": ["A", "A", "A", "A", "A", "A", "A"],
            "date": [
                date(2023, 1, 31),
                date(2023, 2, 28),
                date(2023, 3, 31),
                date(2023, 4, 30),
                date(2024, 1, 31),
                date(2024, 2, 29),
                date(2024, 3, 31),
            ],
            "sales": [100.0, 100.0, 100.0, 999.0, 150.0, 150.0, 150.0],
            "units": [10.0, 10.0, 10.0, 99.0, 10.0, 10.0, 10.0],
        }
    )
    df.write_csv(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "date",
                    "date_column": "date",
                    "baseline_period": "placeholder_baseline",
                    "comparison_period": "placeholder_comparison",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["product"],
                    "calculation_grain": ["product"],
                },
                "options": {
                    "comparison_basis": "period",
                    "period_comparison_mode": "year_to_date",
                },
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        language="en",
    )

    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    period_window = used_recipe["options"]["period_window"]
    row = result.frame.to_dicts()[0]

    assert used_recipe["mappings"]["baseline_period"] == "_Mar-2023"
    assert used_recipe["mappings"]["comparison_period"] == "_Mar-2024"
    assert period_window["baseline"]["start_date"] == "2023-01-01"
    assert period_window["comparison"]["end_date"] == "2024-03-31"
    assert period_window["row_counts"] == {"_Mar-2023": 3, "_Mar-2024": 3}
    assert row["amount_baseline"] == 300.0
    assert row["amount_comparison"] == 450.0
    assert row["total_delta"] == 150.0


def test_variance_plugin_prepares_fiscal_ytd_window_buckets(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "fiscal_ytd.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    pl.DataFrame(
        {
            "product": ["A", "A", "A", "A", "A", "A"],
            "date": [
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 31),
                date(2025, 3, 31),
                date(2025, 4, 30),
                date(2025, 5, 31),
            ],
            "sales": [999.0, 100.0, 120.0, 888.0, 150.0, 180.0],
            "units": [99.0, 10.0, 10.0, 88.0, 10.0, 10.0],
        }
    ).write_csv(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "date",
                    "date_column": "date",
                    "baseline_period": "placeholder_baseline",
                    "comparison_period": "placeholder_comparison",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["product"],
                    "calculation_grain": ["product"],
                },
                "options": {
                    "comparison_basis": "period",
                    "period_type": "fiscal",
                    "fiscal_start_month": 4,
                },
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        language="en",
    )

    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    period_window = used_recipe["options"]["period_window"]
    row = result.frame.to_dicts()[0]

    assert used_recipe["options"]["period_type"] == "fiscal"
    assert used_recipe["options"]["period_comparison_mode"] == "year_to_date"
    assert period_window["baseline"]["start_date"] == "2024-04-01"
    assert period_window["comparison"]["start_date"] == "2025-04-01"
    assert period_window["row_counts"] == {"_May-2024": 2, "_May-2025": 2}
    assert row["amount_baseline"] == 220.0
    assert row["amount_comparison"] == 330.0
    assert row["total_delta"] == 110.0


def test_variance_plugin_rejects_rolling_without_parseable_dates(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    pl.DataFrame(
        {
            "product": ["A", "A"],
            "period": ["base", "actual"],
            "sales": [100.0, 120.0],
            "units": [10.0, 10.0],
        }
    ).write_csv(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "2023",
                    "comparison_period": "2024",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["product"],
                },
                "options": {
                    "comparison_basis": "period",
                    "period_comparison_mode": "rolling_period",
                },
            }
        ),
        encoding="utf-8",
    )

    try:
        core.run_variance_analysis(
            input_path,
            output_dir,
            recipe_path,
            language="en",
        )
    except ValueError as exc:
        assert "Could not parse any dates" in str(exc)
    else:
        raise AssertionError("Expected rolling mode without dates to raise ValueError")


def test_variance_plugin_uses_forecast_as_scenario_baseline() -> None:
    core = load_core()
    df = pl.DataFrame(
        {
            "Scenario": ["AC", "FC"],
            "period": ["2023", "2024"],
            "sales": [100.0, 120.0],
        }
    )

    recipe = core.build_recipe(Path("sales.csv"), df, language="en")

    assert recipe["mappings"]["period_column"] == "Scenario"
    assert recipe["mappings"]["baseline_period"] == "FC"
    assert recipe["mappings"]["comparison_period"] == "AC"
    assert recipe["options"]["comparison_basis"] == "scenario"
    assert recipe["options"]["period_comparison_mode"] == "not_applicable"
    assert recipe["options"]["period_type"] == "custom"


def test_variance_plugin_does_not_treat_actual_prior_year_as_scenario() -> None:
    core = load_core()
    df = pl.DataFrame(
        {
            "Scenario": ["AC", "PY"],
            "period": ["2023", "2024"],
            "sales": [100.0, 120.0],
        }
    )

    recipe = core.build_recipe(Path("sales.csv"), df, language="en")

    assert recipe["mappings"]["period_column"] == "period"
    assert recipe["mappings"]["baseline_period"] == "2023"
    assert recipe["mappings"]["comparison_period"] == "2024"
    assert recipe["options"]["comparison_basis"] == "period"


def test_root_cause_bridge_chart_uses_mixed_legacy_rows() -> None:
    chart = load_root_cause_bridge_chart()
    bridge = pl.DataFrame(
        {
            "Category": [
                "Bikes",
                "Bikes",
                "All",
                "Bikes",
                "Bikes",
            ],
            "Productline": ["R", "M", "All", "R", "M"],
            "Region": [
                "All",
                "All",
                "Australia",
                "Australia",
                "Australia",
            ],
            "bridge_level": [2, 2, 1, 3, 3],
            "bridge_dimensions": [
                "Category,Productline",
                "Category,Productline",
                "Region",
                "Category,Productline,Region",
                "Category,Productline,Region",
            ],
            "variance_type": ["Price"] * 5,
            "variance_amount": [60.0, 5.0, 50.0, 10.0, 5.0],
            "amount_baseline": [1_000.0, 100.0, 1_000.0, 50.0, 50.0],
            "amount_comparison": [1_060.0, 105.0, 1_050.0, 60.0, 55.0],
            "units_baseline": [0.0] * 5,
            "units_comparison": [0.0] * 5,
            "bridge_unique_value_weight": [6, 6, 10, 16, 16],
        }
    )
    result = pl.DataFrame(
        {"amount_baseline": [1_000.0], "amount_comparison": [1_100.0]}
    )
    recipe = {
        "source_file": "/tmp/adventureworks.xlsx",
        "mappings": {
            "baseline_period": "PL",
            "comparison_period": "AC",
        },
        "options": {"comparison_basis": "scenario"},
    }

    rows, audit = chart.build_root_cause_bridge_chart_rows(
        bridge,
        result,
        recipe,
        max_drivers=5,
    )

    labels = rows["label"].to_list()
    assert labels[0] == "PL"
    assert labels[-1] == "AC"
    assert labels[1:6] == [
        "Bikes / R - Price",
        "Bikes / M - Price",
        "Australia - Price",
        "Bikes / R / Australia - Price",
        "Bikes / M / Australia - Price",
    ]
    assert audit["selection_strategy"] == "legacy_process_node_combinations"
    assert audit["selected_bridge_dimensions"] == "legacy_sequence"
    assert set(audit["selected_bridge_levels"]) == {1, 2, 3}
    assert audit["selected_sequence_has_mixed_dimensions"] is True
    assert abs(audit["chart_reconciliation_delta"]) < 0.000001
    assert rows["row_number"].to_list()[1:6] == [1, 2, 3, 4, 5]
    assert rows["percent_label"].to_list()[1:6] == [
        "+6.0",
        "+5.0",
        "+5.0",
        "+20",
        "+10",
    ]


def test_root_cause_bridge_chart_limits_displayed_legacy_rows() -> None:
    chart = load_root_cause_bridge_chart()
    bridge = pl.DataFrame(
        {
            "Category": ["Bikes", "Bikes", "Bikes"],
            "Productline": ["R", "M", "T"],
            "bridge_level": [2, 2, 2],
            "bridge_dimensions": [
                "Category,Productline",
                "Category,Productline",
                "Category,Productline",
            ],
            "variance_type": ["Price", "Price", "Price"],
            "variance_amount": [60.0, 30.0, 10.0],
        }
    )
    result = pl.DataFrame(
        {"amount_baseline": [1_000.0], "amount_comparison": [1_100.0]}
    )
    recipe = {
        "source_file": "/tmp/adventureworks.xlsx",
        "mappings": {
            "baseline_period": "PL",
            "comparison_period": "AC",
        },
        "options": {"comparison_basis": "scenario"},
    }

    rows, audit = chart.build_root_cause_bridge_chart_rows(
        bridge,
        result,
        recipe,
        max_drivers=2,
    )

    assert rows["label"].to_list() == [
        "PL",
        "Bikes / R - Price",
        "Bikes / M - Price",
        "Other",
        "AC",
    ]
    assert audit["selected_driver_count"] == 3
    assert audit["displayed_legacy_driver_count"] == 2
    assert audit["selected_sequence_has_mixed_dimensions"] is False
    assert audit["selection_truncated"] is True
    assert abs(audit["chart_reconciliation_delta"]) < 0.000001


def test_root_cause_drilldown_chart_uses_drilldown_title(tmp_path: Path) -> None:
    chart = load_root_cause_bridge_chart()
    bridge = pl.DataFrame(
        {
            "Category": ["Bikes", "Bikes"],
            "Productline": ["R", "M"],
            "bridge_level": [2, 2],
            "bridge_dimensions": ["Category,Productline", "Category,Productline"],
            "variance_type": ["Price", "Price"],
            "variance_amount": [60.0, 40.0],
        }
    )
    result = pl.DataFrame(
        {"amount_baseline": [1_000.0], "amount_comparison": [1_100.0]}
    )
    recipe = {
        "source_file": "/tmp/adventureworks.xlsx",
        "mappings": {
            "baseline_period": "PL",
            "comparison_period": "AC",
        },
        "options": {"comparison_basis": "scenario"},
    }

    export = chart.write_root_cause_bridge_png(
        bridge,
        result,
        recipe,
        tmp_path,
        artifact_name="root_cause_bridge_drilldown_row_1.png",
    )

    assert export.audit["chart_kind"] == "root_cause_drilldown"
    assert export.audit["chart_title_lines"] == [
        "AdventureWorks",
        "Sales root-cause drilldown | EUR",
        "AC vs PL",
    ]
    assert export.audit["selected_sequence_has_mixed_dimensions"] is False
    from PIL import Image

    with Image.open(export.paths[0]) as image:
        assert image.convert("RGB").getpixel((617, 160)) == (255, 255, 255)


def test_root_cause_client_report_uses_period_comparison_labels(
    tmp_path: Path,
) -> None:
    report = load_root_cause_client_report()
    summary_rows = [
        {
            "alternative_result": 1,
            "selected_labels": "A - Volume",
            "selected_amounts": "300",
            "other_residual": "0",
            "row_count": 1,
            "chart_path": "",
        }
    ]
    recipe = {
        "language": "en",
        "source_file": "sales.csv",
        "mappings": {
            "baseline_period": "~Dec-2023",
            "comparison_period": "~Dec-2024",
        },
        "options": {
            "comparison_basis": "period",
            "period_comparison_mode": "rolling_period",
            "currency": "EUR",
        },
    }

    _paths, audit = report.write_root_cause_client_report(
        summary_rows=summary_rows,
        recipe=recipe,
        output_dir=tmp_path,
    )

    client_report = (tmp_path / "root_cause_client_report.md").read_text(
        encoding="utf-8"
    )
    assert audit["status"] == "written"
    assert (
        "current period vs prior-year period (~Dec-2024 vs ~Dec-2023)" in client_report
    )
    assert "Actual vs Plan" not in client_report


def test_root_cause_client_report_localizes_spanish_markdown_and_docx(
    tmp_path: Path,
) -> None:
    report = load_root_cause_client_report()
    summary_rows = [
        {
            "alternative_result": 1,
            "selected_labels": "Producto A - Volume",
            "selected_amounts": "300",
            "other_residual": "0",
            "row_count": 1,
            "chart_path": "",
        }
    ]
    recipe = {
        "language": "es-ES",
        "source_file": "ventas.csv",
        "mappings": {
            "baseline_period": "~Dec-2023",
            "comparison_period": "~Dec-2024",
        },
        "options": {
            "comparison_basis": "period",
            "period_comparison_mode": "rolling_period",
            "currency": "EUR",
        },
    }

    _paths, audit = report.write_root_cause_client_report(
        summary_rows=summary_rows,
        recipe=recipe,
        output_dir=tmp_path,
    )

    client_report = (tmp_path / "root_cause_client_report.md").read_text(
        encoding="utf-8"
    )
    assert audit["status"] == "written"
    assert set(report._text("en")) <= set(report._text("es"))
    assert (
        report._comparison_metadata(
            {
                "mappings": {"baseline_period": "PL", "comparison_period": "AC"},
                "options": {"comparison_basis": "scenario"},
            },
            "es",
        )["comparison"]
        == "Real frente a Plan (AC frente a PL)"
    )
    assert "# Análisis de las causas de la varianza de ventas" in client_report
    assert "## Datos de soporte principales" in client_report
    assert "## Notas de lectura" in client_report
    assert (
        "periodo actual frente a periodo del año anterior "
        "(~Dec-2024 frente a ~Dec-2023)" in client_report
    )
    assert "Producto A - Volumen" in client_report
    assert "Los importes se presentan en EUR" in client_report
    for english_text in (
        "Sales Variance Root-Cause Analysis",
        "Key Source Data",
        "Reading Notes",
        "current period",
        "prior-year period",
        "Producto A - Volume +",
    ):
        assert english_text not in client_report
    with ZipFile(tmp_path / "root_cause_client_report.docx") as docx_file:
        document_xml = docx_file.read("word/document.xml").decode("utf-8")
    assert "Análisis de las causas de la varianza de ventas" in document_xml
    assert "periodo actual frente a periodo del año anterior" in document_xml


def test_variance_plugin_root_cause_alternative_result_uses_legacy_option(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    default_output_dir = tmp_path / "variance_default"
    output_dir = tmp_path / "variance_alt2"
    default_recipe_path = tmp_path / "default_recipe.json"
    recipe_path = tmp_path / "recipe.json"
    _write_variable_bridge_fixture(input_path)
    default_recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "2023",
                    "comparison_period": "2024",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["region", "subregion", "product"],
                    "calculation_grain": ["region", "subregion", "product"],
                }
            }
        ),
        encoding="utf-8",
    )
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "2023",
                    "comparison_period": "2024",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["region", "subregion", "product"],
                    "calculation_grain": ["region", "subregion", "product"],
                },
                "options": {"root_cause_bridge_alternative_result": 2},
            }
        ),
        encoding="utf-8",
    )

    core.run_variance_analysis(
        input_path,
        default_output_dir,
        default_recipe_path,
        root_cause_bridge=True,
        language="en",
    )
    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        root_cause_bridge=True,
        language="en",
    )
    default_audit = json.loads((default_output_dir / "variance_audit.json").read_text())
    bridge_audit = result.audit["legacy_runtime"]["variable_dimension_bridge"]

    assert (
        default_audit["legacy_runtime"]["variable_dimension_bridge"][
            "alternative_result"
        ]
        == 1
    )
    assert bridge_audit["alternative_result"] == 2
    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    assert used_recipe["options"]["root_cause_bridge_alternative_result"] == 2


def test_variance_plugin_respects_recipe_disabled_root_cause_bridge(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    _write_variable_bridge_fixture(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "2023",
                    "comparison_period": "2024",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["region", "subregion", "product"],
                    "calculation_grain": ["region", "subregion", "product"],
                },
                "options": {
                    "root_cause_bridge": False,
                    "root_cause_bridge_alternative_sweep": False,
                    "root_cause_bridge_auto_drilldown": "none",
                    "waterfall_small_multiples": False,
                },
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        language="en",
    )
    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())

    assert used_recipe["options"]["root_cause_bridge"] is False
    assert used_recipe["options"]["root_cause_bridge_alternative_sweep"] is False
    assert used_recipe["options"]["root_cause_bridge_auto_drilldown"] == "none"
    assert used_recipe["options"]["waterfall_small_multiples"] is False
    assert (
        result.audit["legacy_runtime"]["waterfall_small_multiples_dimension_selection"][
            "status"
        ]
        == "disabled"
    )
    assert result.audit["legacy_runtime"]["variable_dimension_bridge"] is None
    assert not (output_dir / "root_cause_client_report.docx").exists()
    assert not (output_dir / "waterfall_small_multiples.png").exists()


def test_variance_plugin_root_cause_reports_selected_dimension_sequence(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    _write_variable_bridge_fixture(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "2023",
                    "comparison_period": "2024",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["region", "subregion", "product"],
                    "calculation_grain": ["region", "subregion", "product"],
                },
                "options": {"root_cause_bridge_alternative_result": 3},
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        root_cause_bridge=True,
        language="en",
    )
    bridge = pl.read_csv(output_dir / "root_cause_total_bridge.csv")
    bridge_audit = result.audit["legacy_runtime"]["variable_dimension_bridge"]
    selected_unique_dimensions = list(
        dict.fromkeys(bridge["bridge_dimensions"].to_list())
    )

    assert bridge_audit["alternative_result"] == 3
    assert bridge_audit["legacy_sequence_run"] == "Main Report"
    assert bridge_audit["selected_sequence_has_mixed_dimensions"] is (
        len(selected_unique_dimensions) > 1
    )
    assert (
        bridge_audit["selected_sequence_unique_bridge_dimensions"]
        == selected_unique_dimensions
    )


def test_variance_root_cause_candidates_keep_parent_and_leaf_metrics(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    _write_variable_bridge_fixture(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "2023",
                    "comparison_period": "2024",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["region", "subregion", "product"],
                    "calculation_grain": ["region", "subregion", "product"],
                },
                "options": {"root_cause_bridge_alternative_result": 3},
            }
        ),
        encoding="utf-8",
    )

    core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        root_cause_bridge=True,
        language="en",
    )

    candidates = pl.read_csv(output_dir / "root_cause_bridge_candidates.csv")
    parent_a = candidates.filter(
        (pl.col("product") == "A") & (pl.col("subregion") == "All")
    ).row(0, named=True)
    leaf_a_south = candidates.filter(
        (pl.col("product") == "A") & (pl.col("subregion") == "South")
    ).row(0, named=True)
    parent_north = candidates.filter(
        (pl.col("product") == "All") & (pl.col("subregion") == "North")
    ).row(0, named=True)
    leaf_b_north = candidates.filter(
        (pl.col("product") == "B") & (pl.col("subregion") == "North")
    ).row(0, named=True)
    assert candidates.height == 8
    assert (
        parent_a["amount_baseline"],
        parent_a["amount_comparison"],
        parent_a["variance_amount"],
    ) == (180.0, 200.0, 20.0)
    assert (
        leaf_a_south["amount_baseline"],
        leaf_a_south["amount_comparison"],
        leaf_a_south["variance_amount"],
    ) == (80.0, 70.0, -10.0)
    assert (
        parent_north["amount_baseline"],
        parent_north["amount_comparison"],
        parent_north["variance_amount"],
    ) == (250.0, 250.0, 0.0)
    assert (
        leaf_b_north["amount_baseline"],
        leaf_b_north["amount_comparison"],
        leaf_b_north["variance_amount"],
    ) == (150.0, 120.0, -30.0)


def test_variance_plugin_root_cause_drilldown_unavailable_rows_are_audited(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    _write_variable_bridge_fixture(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "2023",
                    "comparison_period": "2024",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["region", "subregion", "product"],
                    "calculation_grain": ["region", "subregion", "product"],
                },
                "options": {
                    "root_cause_bridge_drilldown_rows": [1],
                    "root_cause_bridge_move_rows": {"1": [1]},
                },
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        root_cause_bridge=True,
        language="en",
    )
    bridge_audit = result.audit["legacy_runtime"]["variable_dimension_bridge"]

    assert bridge_audit["drilldown_requested_rows"] == [1]
    assert bridge_audit["drilldown_status"] in {
        "not_written_details_empty",
        "not_written_no_rows",
    }
    assert bridge_audit["moved_rows_status"] == "not_written_no_insert_rows"
    assert not (output_dir / "root_cause_bridge_drilldown_row_1.csv").exists()
    assert not (output_dir / "root_cause_bridge_moved_rows.csv").exists()
    assert (output_dir / "root_cause_bridge_snapshot.csv").exists()
    assert "root_cause_bridge_snapshot.csv" in result.audit["outputs"]


def test_root_cause_move_rows_builds_legacy_insert_filters() -> None:
    adapter = load_legacy_adapter()
    drilldown_run = adapter.LegacyVariableBridgeSequence(
        frame=pl.DataFrame(
            {
                "Category": ["Bikes", "Bikes"],
                "Productline": ["R", "M"],
                "Region": ["All", "All"],
                "variance_type": ["Price", "Price"],
            }
        ),
        legacy_frame=pl.DataFrame(),
        details_frame=pl.DataFrame(),
        snapshot_frame=pl.DataFrame(),
        param={},
        audit={},
    )

    insert_dict, audit = adapter._build_insert_at_row_dict(
        move_rows={1: [1, 2]},
        drilldown_runs={1: drilldown_run},
        bridge_dimensions=["Category", "Productline", "Region"],
        names={"nanFillValue": "All", "varianceTypeName": "Variance Type"},
    )

    assert insert_dict == {
        0: {"Category": "Bikes", "Productline": "R", "Variance Type": "Price"},
        1: {"Category": "Bikes", "Productline": "M", "Variance Type": "Price"},
    }
    assert audit["inserted"] == {"1": [1, 2]}
    assert audit["insert_slots"] == {"1": [0, 1]}
    assert audit["invalid"] == {}


def test_run_variance_cli_passes_root_cause_legacy_options(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    runner = load_run_variance()
    captured: dict[str, Any] = {}

    def _fake_run_variance_analysis(*args: Any, **kwargs: Any) -> Any:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            frame=pl.DataFrame({"x": [1]}),
            audit={"outputs": {}},
            summary_markdown="",
            artifact_paths=[],
        )

    monkeypatch.setattr(runner, "run_variance_analysis", _fake_run_variance_analysis)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_variance.py",
            str(tmp_path / "sales.csv"),
            "--output-dir",
            str(tmp_path / "variance"),
            "--language",
            "es",
            "--root-cause-bridge",
            "--root-cause-bridge-alternative-result",
            "3",
            "--root-cause-bridge-drilldown-row",
            "1",
            "--root-cause-bridge-drilldown-row",
            "2",
            "--root-cause-bridge-drilldown-all",
            "--root-cause-bridge-move-row",
            "1:1,2",
            "--root-cause-bridge-move-row",
            "3:1",
            "--root-cause-bridge-alternative-sweep",
            "--root-cause-bridge-alternative-sweep-start",
            "2",
            "--root-cause-bridge-alternative-sweep-end",
            "5",
            "--root-cause-bridge-auto-drilldown",
            "dominant-row",
            "--root-cause-bridge-auto-drilldown-min-share",
            "0.6",
            "--total-by-dimension-bridge",
            "--total-by-dimension-bridge-dimension",
            "company",
            "--total-by-dimension-bridge-top-n",
            "6",
            "--currency",
            "USD",
        ],
    )

    assert runner.main() == 0
    assert captured["kwargs"]["language"] == "es"
    assert captured["kwargs"]["root_cause_bridge"] is True
    assert captured["kwargs"]["root_cause_bridge_alternative_result"] == 3
    assert captured["kwargs"]["root_cause_bridge_drilldown_rows"] == [1, 2]
    assert captured["kwargs"]["root_cause_bridge_drilldown_all"] is True
    assert captured["kwargs"]["root_cause_bridge_move_rows"] == {
        1: [1, 2],
        3: [1],
    }
    assert captured["kwargs"]["root_cause_bridge_alternative_sweep"] is True
    assert captured["kwargs"]["root_cause_bridge_alternative_sweep_start"] == 2
    assert captured["kwargs"]["root_cause_bridge_alternative_sweep_end"] == 5
    assert captured["kwargs"]["root_cause_bridge_auto_drilldown"] == "dominant_row"
    assert captured["kwargs"]["root_cause_bridge_auto_drilldown_min_share"] == 0.6
    assert captured["kwargs"]["total_by_dimension_bridge"] is True
    assert captured["kwargs"]["total_by_dimension_bridge_dimension"] == "company"
    assert captured["kwargs"]["total_by_dimension_bridge_top_n"] == 6
    assert captured["kwargs"]["currency"] == "USD"


def test_variance_plugin_uses_bottom_up_mix_for_coarser_reporting(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "variance"
    recipe_path = tmp_path / "recipe.json"
    df = pl.DataFrame(
        {
            "category": ["All", "All", "All", "All"],
            "product": ["A", "A", "B", "B"],
            "period": ["2023", "2024", "2023", "2024"],
            "sales": [100.0, 150.0, 200.0, 100.0],
            "units": [10.0, 15.0, 10.0, 5.0],
        }
    )
    df.write_csv(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "2023",
                    "comparison_period": "2024",
                    "amount_column": "sales",
                    "units_column": "units",
                    "dimensions": ["category"],
                    "calculation_grain": ["category", "product"],
                }
            }
        ),
        encoding="utf-8",
    )

    result = core.run_variance_analysis(
        input_path,
        output_dir,
        recipe_path,
        language="en",
    )
    row = result.frame.to_dicts()[0]

    assert row["category"] == "All"
    assert row["total_delta"] == -50.0
    assert row["price_variance"] == 0.0
    assert row["volume_variance"] == -50.0
    assert row["mix_variance"] == 0.0
    assert abs(row["component_reconciliation_delta"]) < 0.000001


def test_variance_plugin_rejects_missing_required_mapping(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "variance"
    _write_sales_fixture(input_path)
    recipe_path = tmp_path / "bad_recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "period_column": "period",
                    "baseline_period": "2023",
                    "comparison_period": "2024",
                    "amount_column": None,
                    "dimensions": ["product"],
                }
            }
        ),
        encoding="utf-8",
    )

    try:
        core.run_variance_analysis(input_path, output_dir, recipe_path, language="en")
    except ValueError as exc:
        assert "amount_column" in str(exc)
    else:
        raise AssertionError("Expected missing amount mapping to raise ValueError")


def test_skill_and_scripts_keep_codex_as_interpretation_layer() -> None:
    skill_text = (
        ROOT
        / "plugins"
        / "variance-analysis"
        / "skills"
        / "variance-analysis"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    script_text = "\n".join(
        path.read_text(encoding="utf-8") for path in SCRIPT_DIR.glob("*.py")
    )
    requirements_text = (
        ROOT / "plugins" / "variance-analysis" / "requirements.txt"
    ).read_text(encoding="utf-8")

    assert "The user should not interact directly with CLI scripts" in skill_text
    assert "must not make direct OpenAI API calls" in skill_text
    assert "scripts/check_dependencies.py" in skill_text
    assert "requirements" in skill_text.lower()
    assert "Keep the improvement note local to chat or run artifacts." in skill_text
    assert "request_user_input" in skill_text
    assert "year-to-date" in skill_text
    assert "rolling" in skill_text
    assert "Root-Cause Alternative Sweep" in skill_text
    assert "residual after previous selected rows" in skill_text
    assert "selected_sequence_has_mixed_dimensions" in skill_text
    assert "root_cause_sweep_interpretation_brief.md" in skill_text
    assert "root_cause_client_report.docx" in skill_text
    assert "codex_root_cause_sweep_analysis.md" in skill_text
    assert "OPTIONAL_EXPORT_FALLBACK" in skill_text
    assert "OPTIONAL_EXPORT_FALLBACK" in script_text
    assert "requests" not in requirements_text.lower()
    assert "modules.llm" not in script_text
    assert "model_router" not in script_text
