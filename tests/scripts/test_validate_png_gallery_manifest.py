from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts import validate_png_gallery_manifest as validator


def _write_manifest(path: Path, items: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"items": items}), encoding="utf-8")


def test_validate_png_gallery_manifest_png_only_returns_no_violations(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "distribution / price_distribution_box",
                "source": "../distribution/price_distribution_box.png",
                "output": "distribution__price_distribution_box.png",
                "artifact_type": "png",
            }
        ],
    )

    violations = validator.validate_png_gallery_manifest(manifest_path)

    assert violations == []


def test_validate_png_gallery_manifest_reports_html_gallery_cards(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "mix_current / current_sales_bridge",
                "source": "../mix_current/current_sales_bridge.html",
                "output": "mix_current__current_sales_bridge.png",
                "artifact_type": "html",
            }
        ],
    )

    violations = validator.validate_png_gallery_manifest(manifest_path)

    assert violations == [
        validator.HtmlGalleryItem(
            label="mix_current / current_sales_bridge",
            source="../mix_current/current_sales_bridge.html",
            output="mix_current__current_sales_bridge.png",
            artifact_type="html",
        )
    ]


def test_validate_png_gallery_manifest_allows_html_when_requested(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "period / weekly_trend",
                "source": "../period/weekly_trend.html",
                "output": "period__weekly_trend.png",
                "artifact_type": "html",
            }
        ],
    )

    violations = validator.validate_png_gallery_manifest(
        manifest_path,
        allow_html=True,
    )

    assert violations == []


def test_main_returns_failure_for_html_gallery_card(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "scatter / quadrant_bubble",
                "source": "../scatter/quadrant_bubble.html",
                "output": "scatter__quadrant_bubble.png",
                "artifact_type": "html",
            }
        ],
    )

    exit_code = validator.main(["--manifest", str(manifest_path)])

    assert exit_code == 1


def test_main_returns_success_when_html_is_explicitly_allowed(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "set_overlap / upset",
                "source": "../set_overlap/upset.html",
                "output": "set_overlap__upset.png",
                "artifact_type": "html",
            }
        ],
    )

    exit_code = validator.main(
        ["--manifest", str(manifest_path), "--allow-html"],
    )

    assert exit_code == 0


def test_main_returns_error_for_malformed_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"cards": []}), encoding="utf-8")

    exit_code = validator.main(["--manifest", str(manifest_path)])

    assert exit_code == 2


def test_find_artifact_readiness_violations_accepts_complete_card(
    tmp_path: Path,
) -> None:
    gallery_dir = tmp_path / "png-gallery"
    source_dir = tmp_path / "distribution"
    gallery_dir.mkdir()
    source_dir.mkdir()
    for filename in (
        "boxplot.html",
        "boxplot_context.json",
        "boxplot_data.csv",
        "manifest.json",
        "used_recipe.json",
    ):
        (source_dir / filename).write_text("ok", encoding="utf-8")
    manifest_path = gallery_dir / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "distribution / boxplot",
                "source": "../distribution/boxplot.html",
                "output": "distribution__boxplot.png",
                "artifact_type": "html",
                "sidecars": [
                    {"label": "source", "href": "../distribution/boxplot.html"},
                    {"label": "context", "href": "../distribution/boxplot_context.json"},
                    {"label": "data", "href": "../distribution/boxplot_data.csv"},
                    {"label": "manifest", "href": "../distribution/manifest.json"},
                    {"label": "recipe", "href": "../distribution/used_recipe.json"},
                ],
                "artifact_contract": {
                    "capability_id": "distribution.boxplot",
                    "when_to_use": "Show distribution spread.",
                    "required_parameters": ["source_file", "metric"],
                    "outputs": [{"artifact_type": "chart", "formats": ["png"]}],
                },
                "artifact_readiness": {"ready": True, "issues": []},
            }
        ],
    )

    violations = validator.find_artifact_readiness_violations(manifest_path)

    assert violations == []


def test_find_artifact_readiness_violations_accepts_png_card(
    tmp_path: Path,
) -> None:
    gallery_dir = tmp_path / "png-gallery"
    source_dir = tmp_path / "variance"
    gallery_dir.mkdir()
    source_dir.mkdir()
    for filename in (
        "waterfall.png",
        "waterfall_context.json",
        "waterfall_chart_data.json",
        "manifest.json",
        "used_recipe.json",
    ):
        (source_dir / filename).write_text("ok", encoding="utf-8")
    manifest_path = gallery_dir / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "variance / waterfall",
                "source": "../variance/waterfall.png",
                "output": "variance__waterfall.png",
                "artifact_type": "png",
                "sidecars": [
                    {"label": "source", "href": "../variance/waterfall.png"},
                    {"label": "context", "href": "../variance/waterfall_context.json"},
                    {
                        "label": "data",
                        "href": "../variance/waterfall_chart_data.json",
                    },
                    {"label": "manifest", "href": "../variance/manifest.json"},
                    {"label": "recipe", "href": "../variance/used_recipe.json"},
                ],
                "artifact_contract": {
                    "capability_id": "variance.scenario_bridge",
                    "when_to_use": "Show standard variance movement.",
                    "required_parameters": ["source_file", "metric"],
                    "outputs": [{"artifact_type": "chart", "formats": ["png"]}],
                },
                "artifact_readiness": {"ready": True, "issues": []},
            }
        ],
    )

    violations = validator.find_artifact_readiness_violations(manifest_path)

    assert violations == []


def test_find_artifact_readiness_violations_reports_missing_and_broken_links(
    tmp_path: Path,
) -> None:
    gallery_dir = tmp_path / "png-gallery"
    gallery_dir.mkdir()
    manifest_path = gallery_dir / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "mix / column_total",
                "source": "../mix/column_total.png",
                "output": "mix__column_total.png",
                "artifact_type": "png",
                "sidecars": [
                    {"label": "source", "href": "../mix/column_total.png"},
                    {"label": "context", "href": "../mix/column_total_context.json"},
                ],
            }
        ],
    )

    violations = validator.find_artifact_readiness_violations(manifest_path)

    codes = {violation.code for violation in violations}
    assert "broken_source" in codes
    assert "broken_context" in codes
    assert "missing_data" in codes
    assert "missing_manifest" in codes
    assert "missing_recipe" in codes
    assert "missing_artifact_contract" in codes


def test_main_requires_artifact_ready_when_requested(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "variance / waterfall",
                "source": "../variance/waterfall.png",
                "output": "variance__waterfall.png",
                "artifact_type": "png",
                "sidecars": [],
            }
        ],
    )

    exit_code = validator.main(
        ["--manifest", str(manifest_path), "--require-artifact-ready"],
    )

    assert exit_code == 1


def test_find_title_contract_violations_accepts_context_title_lines(
    tmp_path: Path,
) -> None:
    gallery_dir = tmp_path / "png-gallery"
    source_dir = tmp_path / "statement"
    gallery_dir.mkdir()
    source_dir.mkdir()
    (source_dir / "pnl_statement_table.html").write_text(
        "<main data-gallery-screenshot></main>",
        encoding="utf-8",
    )
    (source_dir / "pnl_statement_table_chart_context.json").write_text(
        json.dumps(
            {
                "chart_title_lines": [
                    "SoftCons International Inc.",
                    "Profit and loss statement in mUSD",
                    "2012..2015 PL and AC (FC)",
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest_path = gallery_dir / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "statement / pnl_statement_table",
                "source": "../statement/pnl_statement_table.html",
                "output": "statement__pnl_statement_table.png",
                "artifact_type": "table",
                "sidecars": [
                    {
                        "label": "context",
                        "href": "../statement/pnl_statement_table_chart_context.json",
                    }
                ],
            }
        ],
    )

    violations = validator.find_title_contract_violations(manifest_path)

    assert violations == []


def test_find_title_contract_violations_accepts_plotly_html_title(
    tmp_path: Path,
) -> None:
    gallery_dir = tmp_path / "png-gallery"
    source_dir = tmp_path / "period"
    gallery_dir.mkdir()
    source_dir.mkdir()
    (source_dir / "year_over_year_small_multiples.html").write_text(
        (
            '<script>Plotly.newPlot("chart", [], {"title": {"text": '
            '"Mexico hair color<br>Sales in m by Type<br>AC vs PY, through 2017-08-27"}});'
            "</script>"
        ),
        encoding="utf-8",
    )
    manifest_path = gallery_dir / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "period / year_over_year_small_multiples",
                "source": "../period/year_over_year_small_multiples.html",
                "output": "period__year_over_year_small_multiples.png",
                "artifact_type": "html",
            }
        ],
    )

    violations = validator.find_title_contract_violations(manifest_path)

    assert violations == []


def test_find_title_contract_violations_reports_missing_title_contract(
    tmp_path: Path,
) -> None:
    gallery_dir = tmp_path / "png-gallery"
    source_dir = tmp_path / "scatter"
    gallery_dir.mkdir()
    source_dir.mkdir()
    (source_dir / "scatter.html").write_text(
        '<script>Plotly.newPlot("chart", [], {"title": {"text": "Sales"}});</script>',
        encoding="utf-8",
    )
    manifest_path = gallery_dir / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "scatter / scatter",
                "source": "../scatter/scatter.html",
                "output": "scatter__scatter.png",
                "artifact_type": "html",
            }
        ],
    )

    violations = validator.find_title_contract_violations(manifest_path)

    assert violations == [
        validator.GalleryReadinessViolation(
            "scatter / scatter",
            "missing_title_contract",
            "found 0 title row(s)",
        )
    ]


def test_find_title_contract_violations_ignores_empty_title_contract_fields(
    tmp_path: Path,
) -> None:
    gallery_dir = tmp_path / "png-gallery"
    source_dir = tmp_path / "mix"
    gallery_dir.mkdir()
    source_dir.mkdir()
    (source_dir / "stacked_bar.html").write_text("<main></main>", encoding="utf-8")
    (source_dir / "stacked_bar_chart_context.json").write_text(
        json.dumps({"who": None, "what": None, "when": None}),
        encoding="utf-8",
    )
    manifest_path = gallery_dir / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "mix_current / stacked_bar",
                "source": "../mix/stacked_bar.html",
                "output": "mix_current__stacked_bar.png",
                "artifact_type": "html",
                "sidecars": [
                    {
                        "label": "context",
                        "href": "../mix/stacked_bar_chart_context.json",
                    }
                ],
            }
        ],
    )

    violations = validator.find_title_contract_violations(manifest_path)

    assert violations == [
        validator.GalleryReadinessViolation(
            "mix_current / stacked_bar",
            "missing_title_contract",
            "found 0 title row(s)",
        )
    ]


def test_main_requires_title_contract_when_requested(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "label": "variance / waterfall",
                "source": "../variance/waterfall.png",
                "output": "variance__waterfall.png",
                "artifact_type": "png",
            }
        ],
    )

    exit_code = validator.main(
        ["--manifest", str(manifest_path), "--require-title-contract"],
    )

    assert exit_code == 1
