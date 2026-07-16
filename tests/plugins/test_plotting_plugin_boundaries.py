from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]

DEPRECATED_SALES_APP_PATHS = (
    ROOT / "modules" / "sales",
    ROOT / "templates" / "sales_analysis.html",
    ROOT / "templates" / "charting.html",
    ROOT / "static" / "js" / "sales_analysis.js",
    ROOT / "modules" / "charting" / "api.py",
)

NON_PLUGIN_MEKKO_APP_PATHS = (
    ROOT / "modules" / "charting" / "mekko_pipeline.py",
    ROOT / "tests" / "modules" / "charting" / "test_mekko_pipeline.py",
    ROOT / "tests" / "modules" / "charting" / "test_barmekko_pipeline.py",
)

NON_PLUGIN_DUPLICATE_PIPELINE_PATHS = (
    ROOT / "modules" / "charting" / "area_pipeline.py",
    ROOT / "modules" / "charting" / "stacked_column_pipeline.py",
    ROOT / "modules" / "charting" / "scatter_pipeline.py",
    ROOT / "modules" / "charting" / "bubble_pipeline.py",
    ROOT / "modules" / "charting" / "top_items.py",
    ROOT / "tests" / "modules" / "charting" / "test_area_pipeline.py",
    ROOT / "tests" / "modules" / "charting" / "test_stacked_column_pipeline.py",
)

LEGACY_PLUGIN_MEKKO_PATH = (
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "charting"
    / "mekko_pipeline.py"
)

LEGACY_PLUGIN_PIPELINE_PATHS = (
    LEGACY_PLUGIN_MEKKO_PATH,
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "charting"
    / "area_pipeline.py",
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "charting"
    / "stacked_column_pipeline.py",
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "charting"
    / "scatter_pipeline.py",
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "charting"
    / "bubble_pipeline.py",
)

PLOTTING_PLUGIN_PATHS = (
    ROOT / "plugins" / "variance-analysis",
    ROOT / "plugins" / "period-comparison",
    ROOT / "plugins" / "mix-contribution-analysis",
    ROOT / "plugins" / "scatter-bubble-analysis",
    ROOT / "plugins" / "distribution-analysis",
    ROOT / "plugins" / "set-overlap-analysis",
    ROOT / "plugins" / "_shared" / "vendor" / "modules",
)

FORBIDDEN_SALES_APP_IMPORTS = (
    "modules.sales",
    "from modules.sales",
    "import modules.sales",
)


def _load_plugin_module(plugin: str, filename: str) -> Any:
    script_dir = ROOT / "plugins" / plugin / "scripts"
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    spec = importlib.util.spec_from_file_location(
        f"prepare_reuse_{plugin.replace('-', '_')}_{filename.replace('.', '_')}",
        script_dir / filename,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_stub_artifact(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".png":
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
            b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT"
            b"\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA"
            b"\xb5\xa2\x8b\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return
    path.write_text("test chart artifact\n", encoding="utf-8")


def _write_mix_reuse_fixture(path: Path) -> None:
    rows = [
        {
            "Scenario": scenario,
            "Orderdate": f"2025-0{month}-28",
            "Productline": productline,
            "Category": category,
            "Region": region,
            "Salesamount": amount,
            "Units": units,
        }
        for scenario, multiplier in (("PY", 0.8), ("AC", 1.0))
        for month in (1, 2)
        for productline, category, region, amount, units in (
            (
                "Bikes",
                "Road",
                "North",
                100.0 * multiplier * month,
                10.0 * multiplier * month,
            ),
            (
                "Bikes",
                "Mountain",
                "South",
                80.0 * multiplier * month,
                8.0 * multiplier * month,
            ),
            (
                "Accessories",
                "Helmets",
                "North",
                40.0 * multiplier * month,
                4.0 * multiplier * month,
            ),
        )
    ]
    pl.DataFrame(rows).write_csv(path)


def _write_scatter_reuse_fixture(path: Path) -> None:
    pl.DataFrame(
        {
            "Date": ["2026-01-01"] * 8,
            "Period": ["AC"] * 8,
            "Brand": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "Retailer": [
                "North",
                "South",
                "East",
                "West",
                "North",
                "South",
                "East",
                "West",
            ],
            "Type": [
                "Permanent",
                "Permanent",
                "Tone",
                "Tone",
                "Other",
                "Other",
                "Male",
                "Male",
            ],
            "Unit Price": [3.5, 3.9, 4.2, 4.8, 5.1, 5.5, 6.0, 6.4],
            "Units": [40, 47, 52, 61, 68, 75, 84, 91],
            "Sales": [140.0, 183.3, 218.4, 292.8, 346.8, 412.5, 504.0, 582.4],
        }
    ).write_csv(path)


def _write_distribution_reuse_fixture(path: Path) -> None:
    rows = []
    for period in ("PY", "AC"):
        for brand in ("A", "B", "C", "D"):
            for channel in ("Retail", "Online"):
                rows.append(
                    {
                        "Period": period,
                        "Brand": brand,
                        "Channel": channel,
                        "Sales": float(len(rows) + 10),
                    }
                )
    pl.DataFrame(rows).write_csv(path)


def _write_period_reuse_fixture(path: Path) -> None:
    rows = [
        {
            "Scenario": scenario,
            "Orderdate": f"{year}-{month:02d}-28",
            "Productline": productline,
            "Region": region,
            "Salesamount": amount,
        }
        for scenario, year, multiplier in (("PY", 2024, 0.85), ("AC", 2025, 1.0))
        for month in (1, 2, 3)
        for productline, region, amount in (
            ("Bikes", "North", 100.0 * multiplier * month),
            ("Accessories", "South", 60.0 * multiplier * month),
        )
    ]
    pl.DataFrame(rows).write_csv(path)


def _write_set_overlap_reuse_fixture(path: Path) -> None:
    pl.DataFrame(
        {
            "Period": ["AC", "AC", "AC", "AC", "AC", "AC"],
            "SKU": ["sku1", "sku1", "sku2", "sku3", "sku3", "sku4"],
            "Retailer": ["A", "B", "A", "B", "C", "C"],
            "Region": ["North", "North", "North", "North", "North", "North"],
        }
    ).write_csv(path)


def _write_variance_reuse_fixture(path: Path) -> None:
    pl.DataFrame(
        {
            "product": ["A", "A", "B", "B"],
            "category": ["Cat", "Cat", "Dog", "Dog"],
            "period": ["2023", "2024", "2023", "2024"],
            "sales": [100.0, 150.0, 200.0, 180.0],
            "units": [10.0, 12.0, 20.0, 18.0],
            "discount": [5.0, 6.0, 10.0, 12.0],
            "cogs": [60.0, 84.0, 120.0, 110.0],
        }
    ).write_csv(path)


def test_deprecated_sales_fastapi_app_source_removed() -> None:
    existing_paths = [
        str(path.relative_to(ROOT))
        for path in DEPRECATED_SALES_APP_PATHS
        if path.exists()
    ]

    assert existing_paths == []


def test_plotting_plugins_do_not_import_deprecated_sales_app() -> None:
    offenders: list[str] = []
    for plugin_path in PLOTTING_PLUGIN_PATHS:
        for path in plugin_path.rglob("*"):
            if path.suffix not in {".cjs", ".json", ".md", ".py"}:
                continue
            text = path.read_text(encoding="utf-8")
            if any(marker in text for marker in FORBIDDEN_SALES_APP_IMPORTS):
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_non_plugin_mekko_pipeline_removed_but_plugin_legacy_copy_remains() -> None:
    existing_paths = [
        str(path.relative_to(ROOT))
        for path in NON_PLUGIN_MEKKO_APP_PATHS
        if path.exists()
    ]

    assert existing_paths == []
    assert LEGACY_PLUGIN_MEKKO_PATH.is_file()


def test_non_plugin_duplicate_chart_pipelines_removed_but_plugin_copies_remain() -> (
    None
):
    existing_paths = [
        str(path.relative_to(ROOT))
        for path in NON_PLUGIN_DUPLICATE_PIPELINE_PATHS
        if path.exists()
    ]

    assert existing_paths == []
    assert all(path.is_file() for path in LEGACY_PLUGIN_PIPELINE_PATHS)


def test_sales_app_no_longer_exposes_removed_duplicate_catalog_actions() -> None:
    removed_paths = (
        ROOT / "src" / "review-react" / "sales.jsx",
        ROOT / "templates" / "review_sales_react.html",
        ROOT / "static" / "js" / "review-sales-react.js",
    )

    assert [
        str(path.relative_to(ROOT)) for path in removed_paths if path.exists()
    ] == []


def test_sales_chart_route_and_legacy_sales_page_removed() -> None:
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")

    assert '"/sales/charts"' not in source
    assert '"/legacy/review/sales"' not in source
    assert "def fetch_sales_charts" not in source
    assert "review_sales_react.html" not in source
    assert "review-sales-react.js" not in source


@pytest.mark.parametrize(
    (
        "plugin",
        "core_filename",
        "runner_name",
        "writer_name",
        "fixture_writer",
        "input_name",
    ),
    [
        (
            "mix-contribution-analysis",
            "mix_core.py",
            "run_mix_contribution",
            "write_legacy_mix_chart",
            _write_mix_reuse_fixture,
            "mix.csv",
        ),
        (
            "scatter-bubble-analysis",
            "scatter_bubble_core.py",
            "run_scatter_bubble",
            "write_legacy_scatter_bubble_chart",
            _write_scatter_reuse_fixture,
            "scatter.csv",
        ),
        (
            "distribution-analysis",
            "distribution_core.py",
            "run_distribution",
            "write_legacy_distribution_chart",
            _write_distribution_reuse_fixture,
            "distribution.csv",
        ),
    ],
)
def test_cache_backed_plotting_runs_prepare_once_and_share_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plugin: str,
    core_filename: str,
    runner_name: str,
    writer_name: str,
    fixture_writer: Any,
    input_name: str,
) -> None:
    core = _load_plugin_module(plugin, core_filename)
    input_path = tmp_path / input_name
    output_dir = tmp_path / plugin
    fixture_writer(input_path)
    read_calls = 0
    prepare_calls = 0
    prepared_canonical_ids: list[int] = []
    writer_canonical_ids: list[int] = []
    writer_cache_ids: list[int] = []
    original_read_table = core.read_table
    original_prepare_canonical_frame = core.prepare_canonical_frame

    def read_table_spy(path: Path) -> pl.DataFrame:
        nonlocal read_calls
        read_calls += 1
        return original_read_table(path)

    def prepare_canonical_frame_spy(frame: pl.DataFrame, recipe: dict[str, Any]) -> Any:
        nonlocal prepare_calls
        prepare_calls += 1
        prepared = original_prepare_canonical_frame(frame, recipe)
        canonical = prepared[0] if isinstance(prepared, tuple) else prepared
        prepared_canonical_ids.append(id(canonical))
        return prepared

    def fake_legacy_writer(
        canonical: pl.DataFrame,
        _recipe: dict[str, Any],
        output_path: Path,
        spec: dict[str, Any],
        **kwargs: Any,
    ) -> SimpleNamespace:
        writer_canonical_ids.append(id(canonical))
        writer_cache_ids.append(id(kwargs["prepared_data_cache"]))
        artifact_name = str(spec.get("artifact_name") or f"{spec['name']}.html")
        artifact_path = output_path / artifact_name
        _write_stub_artifact(artifact_path)
        return SimpleNamespace(
            paths=[str(artifact_path)],
            audit={
                "status": "written",
                "prepared_data_cache": {"enabled": True},
            },
            chart_context=None,
        )

    monkeypatch.setattr(core, "read_table", read_table_spy)
    monkeypatch.setattr(core, "prepare_canonical_frame", prepare_canonical_frame_spy)
    monkeypatch.setattr(core, writer_name, fake_legacy_writer)

    getattr(core, runner_name)(input_path, output_dir, language="en")

    assert read_calls == 1
    assert prepare_calls == 1
    assert len(writer_canonical_ids) >= 2
    assert set(writer_canonical_ids) == {prepared_canonical_ids[0]}
    assert len(set(writer_cache_ids)) == 1


def test_period_comparison_prepares_once_and_reuses_canonical_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = _load_plugin_module("period-comparison", "period_core.py")
    input_path = tmp_path / "period.csv"
    output_dir = tmp_path / "period"
    _write_period_reuse_fixture(input_path)
    read_calls = 0
    prepare_calls = 0
    prepared_canonical_ids: list[int] = []
    writer_canonical_ids: list[int] = []
    original_read_table = core.read_table
    original_prepare_canonical_frame = core.prepare_canonical_frame

    def read_table_spy(path: Path) -> pl.DataFrame:
        nonlocal read_calls
        read_calls += 1
        return original_read_table(path)

    def prepare_canonical_frame_spy(
        frame: pl.DataFrame, recipe: dict[str, Any]
    ) -> tuple[pl.DataFrame, dict[str, Any]]:
        nonlocal prepare_calls
        prepare_calls += 1
        canonical, period_window = original_prepare_canonical_frame(frame, recipe)
        prepared_canonical_ids.append(id(canonical))
        return canonical, period_window

    def fake_chart_writer(
        _chart_frame: pl.DataFrame,
        canonical: pl.DataFrame,
        _recipe: dict[str, Any],
        output_path: Path,
        *,
        render: bool = True,
    ) -> tuple[list[str], dict[str, Any]]:
        writer_canonical_ids.append(id(canonical))
        artifact_path = output_path / f"period_chart_{len(writer_canonical_ids)}.html"
        _write_stub_artifact(artifact_path)
        return [str(artifact_path)], {"status": "written"}

    def fake_small_multiples_writer(
        _small_multiples_frame: pl.DataFrame,
        canonical: pl.DataFrame,
        _recipe: dict[str, Any],
        _selection: dict[str, Any],
        output_path: Path,
        *,
        render: bool = True,
    ) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
        writer_canonical_ids.append(id(canonical))
        artifact_path = output_path / "period_small_multiples.html"
        _write_stub_artifact(artifact_path)
        return [str(artifact_path)], {"status": "written"}, {"status": "written"}

    for writer_name in (
        "write_column_chart",
        "write_line_chart",
        "write_by_period_chart",
        "write_slope_chart",
        "write_dot_chart",
        "write_waterfall_chart",
    ):
        monkeypatch.setattr(core, writer_name, fake_chart_writer)
    monkeypatch.setattr(core, "read_table", read_table_spy)
    monkeypatch.setattr(core, "prepare_canonical_frame", prepare_canonical_frame_spy)
    monkeypatch.setattr(
        core, "write_small_multiples_chart", fake_small_multiples_writer
    )

    core.run_period_comparison(input_path, output_dir, language="en")

    assert read_calls == 1
    assert prepare_calls == 1
    assert len(writer_canonical_ids) >= 2
    assert set(writer_canonical_ids) == {prepared_canonical_ids[0]}


def test_set_overlap_prepares_once_and_reuses_canonical_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = _load_plugin_module("set-overlap-analysis", "set_overlap_core.py")
    input_path = tmp_path / "overlap.csv"
    recipe_path = tmp_path / "recipe.json"
    output_dir = tmp_path / "set_overlap"
    _write_set_overlap_reuse_fixture(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "plugin": "set-overlap-analysis",
                "mappings": {
                    "item_column": "SKU",
                    "set_column": "Retailer",
                    "period_column": "Period",
                    "dimensions": ["Region"],
                },
                "options": {
                    "charts": ["upset", "venn"],
                    "selected_period": "AC",
                    "set_values": ["A", "B", "C"],
                    "max_sets": 3,
                    "min_intersection_size": 1,
                    "highlighted_sets": [],
                    "write_html": False,
                },
            }
        ),
        encoding="utf-8",
    )
    read_calls = 0
    prepare_calls = 0
    prepared_canonical_ids: list[int] = []
    writer_canonical_ids: list[int] = []
    original_read_table = core.read_table
    original_prepare_canonical_frame = core.prepare_canonical_frame

    def read_table_spy(path: Path) -> pl.DataFrame:
        nonlocal read_calls
        read_calls += 1
        return original_read_table(path)

    def prepare_canonical_frame_spy(
        frame: pl.DataFrame, recipe: dict[str, Any]
    ) -> pl.DataFrame:
        nonlocal prepare_calls
        prepare_calls += 1
        canonical = original_prepare_canonical_frame(frame, recipe)
        prepared_canonical_ids.append(id(canonical))
        return canonical

    def fake_overlap_writer(
        canonical: pl.DataFrame,
        _recipe: dict[str, Any],
        output_path: Path,
        _selected_sets: list[str],
        *,
        render: bool = True,
    ) -> tuple[list[str], dict[str, Any]]:
        writer_canonical_ids.append(id(canonical))
        artifact_path = output_path / f"overlap_chart_{len(writer_canonical_ids)}.png"
        _write_stub_artifact(artifact_path)
        return [str(artifact_path)], {"status": "written"}

    monkeypatch.setattr(core, "read_table", read_table_spy)
    monkeypatch.setattr(core, "prepare_canonical_frame", prepare_canonical_frame_spy)
    monkeypatch.setattr(core, "_write_upset_chart", fake_overlap_writer)
    monkeypatch.setattr(core, "_write_venn_chart", fake_overlap_writer)

    core.run_set_overlap(input_path, output_dir, recipe_path, language="en")

    assert read_calls == 1
    assert prepare_calls == 1
    assert len(writer_canonical_ids) == 2
    assert prepared_canonical_ids
    assert len(set(writer_canonical_ids)) == 1
