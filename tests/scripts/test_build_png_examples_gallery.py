from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_png_examples_gallery as gallery


def test_parse_args_defaults_to_curated_gallery_exclusions() -> None:
    args = gallery._parse_args([])

    assert "mix_regular /" not in args.exclude
    assert "mix_regular / area_" not in args.exclude
    assert "mix_regular / line" not in args.exclude
    assert "mix_regular / stacked_column_synthesis" in args.exclude
    assert "mix_current / mix_regular / barmekko" not in args.exclude
    assert "mix_current / mix_regular / marimekko" not in args.exclude
    assert "mix_current / mix_regular / pareto" not in args.exclude
    assert "mix_current / mix_regular / related_metrics_bar" in args.exclude
    assert "mix_current / mix_regular / stacked_column" in args.exclude
    assert "mix_current / mix_regular / stacked_pareto" not in args.exclude
    assert "mix_multitier_bar /" in args.exclude
    assert "mix_multitier_bar_dimension_panels /" in args.exclude
    assert "mix_stacked_column_synthesis /" in args.exclude
    assert "mix_cohort_brand /" in args.exclude
    assert "mix_cohort_product /" in args.exclude
    assert "mix_comparison / related_metrics_bar_small_multiples_1" in args.exclude
    assert "mix_comparison / related_metrics_bar_small_multiples_2" in args.exclude
    assert " / multitier_bar_2" in args.exclude
    assert " / multitier_bar_3" in args.exclude
    assert " / multitier_bar_4" in args.exclude
    assert "variance / root_cause_bridge_alt_" in args.exclude
    assert "variance / root_cause_client_report_" in args.exclude
    assert "variance-analysis / examples /" in args.exclude
    assert "period-comparison / examples /" in args.exclude
    assert gallery.DEFAULT_EXACT_EXCLUDE_LABELS == (
        "period / year_over_year_line_small_multiples",
    )
    assert args.include_default_excluded is False


def test_parse_args_can_include_default_excluded_examples() -> None:
    args = gallery._parse_args(["--include-default-excluded"])

    assert args.include_default_excluded is True


def test_render_html_artifact_prefers_explicit_screenshot_marker(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "chart.html"
    output_path = tmp_path / "chart.png"
    source_path.write_text(
        (
            '<main data-gallery-screenshot><div class="plotly-graph-div"></div>'
            "</main>"
        ),
        encoding="utf-8",
    )
    calls: list[tuple[str, str]] = []

    class FakeLocator:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        @property
        def first(self) -> "FakeLocator":
            return self

        def count(self) -> int:
            return 1

        def screenshot(self, *, path: str, timeout: int) -> None:
            calls.append(("screenshot", self.selector))
            Path(path).write_bytes(b"png")

    class FakePage:
        def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
            calls.append(("goto", url))

        def locator(self, selector: str) -> FakeLocator:
            calls.append(("locator", selector))
            return FakeLocator(selector)

        def close(self) -> None:
            calls.append(("close", ""))

    class FakeBrowser:
        def new_page(
            self,
            *,
            viewport: dict[str, int],
            device_scale_factor: int,
        ) -> FakePage:
            calls.append(("new_page", str(viewport["width"])))
            return FakePage()

    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="set_overlap / upset_small_multiples",
        dimensions=None,
    )

    gallery._render_html_artifact(FakeBrowser(), item, wait_ms=0)  # type: ignore[arg-type]

    assert output_path.read_bytes() == b"png"
    assert ("screenshot", gallery.EXPLICIT_HTML_ARTIFACT_SELECTOR) in calls
    assert ("locator", gallery.PLOTLY_DIV_SELECTOR) not in calls


def test_gallery_label_renames_by_period_to_recency_window(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    period_dir = source_root / "period"
    period_dir.mkdir(parents=True)
    source_path = period_dir / "year_over_year_by_period.html"

    label = gallery._gallery_label(source_root, source_path)

    assert label == "period / year_over_year_by_recency_window"
    assert gallery._source_gallery_label(label) == "period / year_over_year_by_period"


def test_gallery_label_flattens_first_class_mix_regular_examples(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    mix_dir = source_root / "mix_current" / "mix_regular"
    mix_dir.mkdir(parents=True)
    source_path = mix_dir / "marimekko_small_multiples.html"

    label = gallery._gallery_label(source_root, source_path)

    assert label == "mix_current / marimekko_small_multiples"
    assert (
        gallery._source_gallery_label(label)
        == "mix_current / mix_regular / marimekko_small_multiples"
    )


def test_title_context_falls_back_to_context_summary_for_generated_mix_cards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    gallery_dir = source_root / "png-gallery"
    source_dir = source_root / "mix_comparison" / "mix_regular"
    source_dir.mkdir(parents=True)
    gallery_dir.mkdir()
    source_path = source_dir / "line.html"
    source_path.write_text("<html></html>", encoding="utf-8")
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=gallery_dir / "mix_comparison__mix_regular__line.png",
        label="mix_comparison / line",
        dimensions=None,
    )
    monkeypatch.setattr(gallery, "_context_sidecar_path", lambda _item: None)
    monkeypatch.setattr(gallery, "_title_lines_from_html_source", lambda _path: [])
    monkeypatch.setattr(
        gallery,
        "_context_summary",
        lambda _item: gallery.ContextSummary(
            grammar="line_time_series",
            metrics="Sales",
            dimensions="Brand",
            periods="Jan, Feb",
            trace_widths=None,
            capability="mix.timeline",
            source_reference="line",
        ),
    )

    title_context = gallery._title_context(item, gallery_dir)

    assert title_context == {
        "lines": [
            "Mix & Contribution Analysis",
            "line_time_series | Sales | Brand",
            "Jan, Feb",
        ],
        "who": "Mix & Contribution Analysis",
        "what": "line_time_series | Sales | Brand",
        "when": "Jan, Feb",
        "source": "../mix_comparison/mix_regular/line.html",
    }


def test_gallery_label_keeps_mix_bar_and_stacked_bar_separate(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    mix_dir = source_root / "mix_comparison"
    mix_dir.mkdir(parents=True)
    bar_path = mix_dir / "bar.html"
    stacked_bar_path = mix_dir / "stacked_bar.html"

    bar_label = gallery._gallery_label(source_root, bar_path)
    stacked_bar_label = gallery._gallery_label(source_root, stacked_bar_path)

    assert bar_label == "mix_comparison / bar"
    assert stacked_bar_label == "mix_comparison / stacked_bar"
    assert gallery._source_gallery_label(bar_label) == "mix_comparison / bar"
    assert (
        gallery._source_gallery_label(stacked_bar_label)
        == "mix_comparison / stacked_bar"
    )


def test_build_index_links_chart_sidecars(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_cohort"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    source_path = run_dir / "cohort_lost_stacked_column.html"
    output_path = gallery_dir / "mix_cohort__cohort_lost_stacked_column.png"
    source_path.write_text("<html></html>", encoding="utf-8")
    (run_dir / "cohort_lost_stacked_column_chart_context.json").write_text(
        json.dumps(
            {
                "chart_title_lines": [
                    "Mexico hair color",
                    "Sales in mEUR by Barcode_Lost",
                    "2015, 2016, 2017",
                ],
                "legacy_chart": "stacked column",
                "metrics": ["Sales"],
                "dimensions": ["Barcode_Lost"],
                "selected_periods": ["2015", "2016", "2017"],
                "plotly_figures": [
                    {
                        "traces": [
                            {"type": "bar", "width": [0.44999999999999996, 0.45]},
                            {"type": "bar", "width": [0.25]},
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "cohort_lost_stacked_column_chart_data.csv").write_text(
        "dimension,value\n2017,10\n",
        encoding="utf-8",
    )
    (run_dir / "used_recipe.json").write_text("{}", encoding="utf-8")

    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="mix_cohort / cohort_lost_stacked_column",
        dimensions=None,
    )
    html = gallery._build_index(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    assert 'href="../mix_cohort/cohort_lost_stacked_column.html">source</a>' in html
    assert 'href="manifest.json">manifest.json</a>' in html
    assert "<b>grammar</b> stacked column" in html
    assert "<b>metric</b> Sales" in html
    assert "<b>dimension</b> Barcode_Lost" in html
    assert "<b>period</b> 2015, 2016, 2017" in html
    assert "<b>trace width</b> 0.25, 0.45" in html
    assert (
        'href="../mix_cohort/cohort_lost_stacked_column_chart_context.json">'
        "context</a>"
    ) in html
    assert (
        'href="../mix_cohort/cohort_lost_stacked_column_chart_data.csv">data</a>'
        in html
    )
    assert 'href="../mix_cohort/used_recipe.json">recipe</a>' in html


def test_build_index_links_png_chart_sidecars_with_numbered_suffix(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_comparison"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    source_path = run_dir / "related_metrics_bar_small_multiples_1.png"
    output_path = (
        gallery_dir / "mix_comparison__related_metrics_bar_small_multiples_1.png"
    )
    source_path.write_bytes(b"not-used-by-index-test")
    (run_dir / "related_metrics_bar_small_multiples_chart_context.json").write_text(
        json.dumps(
            {
                "legacy_chart": "stacked bar",
                "metrics": ["Sales", "Sales Growth Rate"],
                "dimensions": ["Brand", "Channel"],
                "selected_periods": ["2015-12-20", "2015-11-08"],
                "trace_widths": [0.25],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "related_metrics_bar_small_multiples_chart_data.csv").write_text(
        "dimension,value\nCompany,10\n",
        encoding="utf-8",
    )
    (run_dir / "used_recipe.json").write_text("{}", encoding="utf-8")

    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="mix_comparison / related_metrics_bar_small_multiples_1",
        dimensions=None,
    )
    html = gallery._build_index(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    assert (
        'href="../mix_comparison/related_metrics_bar_small_multiples_1.png">'
        "source</a>"
    ) in html
    assert "<b>grammar</b> stacked bar" in html
    assert "<b>metric</b> Sales, Sales Growth Rate" in html
    assert "<b>dimension</b> Brand, Channel" in html
    assert "<b>period</b> 2015-12-20, 2015-11-08" in html
    assert "<b>trace width</b> 0.25" in html
    assert "related_metrics_bar_small_multiples_chart_context.json" in html
    assert "related_metrics_bar_small_multiples_chart_data.csv" in html
    assert 'href="../mix_comparison/used_recipe.json">recipe</a>' in html


def test_build_index_uses_html_trace_width_fallback(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_stacked_column_synthesis"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    source_path = run_dir / "stacked_column_synthesis.html"
    output_path = (
        gallery_dir / "mix_stacked_column_synthesis__stacked_column_synthesis.png"
    )
    source_path.write_text(
        '{"marker":{"line":{"width":2}},"width":[0.8,0.8,0.8],"type":"bar"}',
        encoding="utf-8",
    )
    (run_dir / "stacked_column_synthesis_chart_context.json").write_text(
        json.dumps(
            {
                "legacy_chart": "stacked column",
                "metrics": ["Sales"],
                "dimensions": ["Company", "Brand"],
                "selected_periods": ["2017"],
                "plotly_figures": [{"traces": [{"type": "bar", "width": []}]}],
            }
        ),
        encoding="utf-8",
    )

    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="mix_stacked_column_synthesis / stacked_column_synthesis",
        dimensions=None,
    )
    html = gallery._build_index(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    assert "<b>trace width</b> 0.8" in html


def test_iter_source_artifacts_prefers_current_html_over_stale_png(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_comparison"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    (run_dir / "stacked_column_synthesis.html").write_text(
        '<script>Plotly.newPlot("chart", [{"type":"bar"}], {});</script>',
        encoding="utf-8",
    )
    (run_dir / "stacked_column_synthesis.png").write_bytes(b"stale")
    (run_dir / "mix_contribution_audit.json").write_text(
        json.dumps(
            {
                "legacy_runtime": {
                    "chart_audits": {
                        "stacked_column_synthesis": {
                            "exports": [
                                {
                                    "artifact": "stacked_column_synthesis.html",
                                    "renderer": "legacy_plotly+html_only",
                                    "export_width": 1400,
                                    "export_height": 900,
                                }
                            ]
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        gallery._audit_dimensions(source_root),
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=False,
    )

    assert [item.source_path.name for item in items] == [
        "stacked_column_synthesis.html"
    ]


def test_iter_source_artifacts_keeps_canonical_stacked_column_without_exact_hide(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_comparison"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    (run_dir / "stacked_column.html").write_text(
        '<script>Plotly.newPlot("chart", [{"type":"bar"}], {});</script>',
        encoding="utf-8",
    )

    items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        dimensions={},
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=False,
        exact_exclude_labels=gallery.DEFAULT_EXACT_EXCLUDE_LABELS,
    )

    assert [item.label for item in items] == ["mix_comparison / stacked_column"]


def test_iter_source_artifacts_excludes_drilldown_suffix_by_default(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "variance"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    (run_dir / "root_cause_bridge.png").write_bytes(b"main")
    (run_dir / "root_cause_client_report_drilldown.png").write_bytes(
        b"report-drilldown"
    )
    (run_dir / "root_cause_bridge_alt_1_drilldown_row_1.png").write_bytes(
        b"row-drilldown"
    )

    default_items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        dimensions={},
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=False,
    )
    drilldown_items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        dimensions={},
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=True,
    )

    assert [item.label for item in default_items] == ["variance / root_cause_bridge"]
    assert {item.label for item in drilldown_items} == {
        "variance / root_cause_bridge",
        "variance / root_cause_bridge_alt_1_drilldown_row_1",
        "variance / root_cause_client_report_drilldown",
    }


def test_iter_source_artifacts_ignores_unreferenced_html_when_run_has_current_outputs(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_current"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    (run_dir / "stacked_bar.png").write_bytes(b"current")
    (run_dir / "stacked_bar_small_multiples.html").write_text(
        "<html></html>",
        encoding="utf-8",
    )
    (run_dir / "final_artifacts.json").write_text(
        json.dumps(
            {
                "outputs": [
                    {
                        "path": "stacked_bar.png",
                        "kind": "png",
                        "status": "written",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        dimensions={},
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=False,
    )

    assert [item.source_path.name for item in items] == ["stacked_bar.png"]


def test_iter_source_artifacts_keeps_source_manifest_table_with_current_outputs(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "period"
    source_pack_dir = run_dir / "source_pack"
    gallery_dir = source_root / "png-gallery"
    source_pack_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)

    (run_dir / "year_over_year_dot.html").write_text(
        '<script>Plotly.newPlot("chart", [{"type":"scatter"}], {});</script>',
        encoding="utf-8",
    )
    (run_dir / "comparison_table.html").write_text(
        "<html><table></table></html>",
        encoding="utf-8",
    )
    (run_dir / "final_artifacts.json").write_text(
        json.dumps(
            {
                "outputs": [
                    {
                        "path": "year_over_year_dot.html",
                        "kind": "html",
                        "status": "written",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (source_pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "producer": {"plugin": "period-comparison"},
                "artifacts": [
                    {
                        "artifact_id": "comparison_table",
                        "kind": "tables",
                        "source_path": "comparison_table.html",
                        "table_spec_name": "comparison_table",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        dimensions={},
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=False,
    )

    assert [item.source_path.name for item in items] == [
        "comparison_table.html",
        "year_over_year_dot.html",
    ]


def test_iter_source_artifacts_prefers_png_when_current_outputs_include_html_pair(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "variance"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    (run_dir / "root_cause_bridge.png").write_bytes(b"current-png")
    (run_dir / "root_cause_bridge.html").write_text(
        "<html></html>",
        encoding="utf-8",
    )
    (run_dir / "final_artifacts.json").write_text(
        json.dumps(
            {
                "outputs": [
                    {
                        "path": "root_cause_bridge.html",
                        "kind": "html",
                        "status": "written",
                    },
                    {
                        "path": "root_cause_bridge.png",
                        "kind": "png",
                        "status": "written",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        dimensions={},
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=False,
    )

    assert [item.source_path.name for item in items] == ["root_cause_bridge.png"]


def test_iter_source_artifacts_prefers_table_html_when_current_outputs_include_png_pair(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "period"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    (run_dir / "comparison_table.png").write_bytes(b"stale-table-png")
    (run_dir / "comparison_table.html").write_text(
        "<html><table></table></html>",
        encoding="utf-8",
    )
    (run_dir / "final_artifacts.json").write_text(
        json.dumps(
            {
                "outputs": [
                    {
                        "path": "comparison_table.html",
                        "kind": "html",
                        "status": "written",
                    },
                    {
                        "path": "comparison_table.png",
                        "kind": "png",
                        "status": "written",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        dimensions={},
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=False,
    )

    assert [item.source_path.name for item in items] == ["comparison_table.html"]


def test_iter_source_artifacts_excludes_matching_labels(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    gallery_dir = source_root / "png-gallery"
    keep_dir = source_root / "mix_cohort"
    skip_dir = source_root / "mix_cohort_brand"
    keep_dir.mkdir(parents=True)
    skip_dir.mkdir()
    gallery_dir.mkdir()

    (keep_dir / "cohort_lost_stacked_column.html").write_text(
        '<script>Plotly.newPlot("chart", [{"type":"bar"}], {});</script>',
        encoding="utf-8",
    )
    (skip_dir / "cohort_lost_stacked_column.html").write_text(
        '<script>Plotly.newPlot("chart", [{"type":"bar"}], {});</script>',
        encoding="utf-8",
    )

    items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        dimensions={},
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=False,
        exclude_filters=["mix_cohort_brand"],
    )

    assert [item.label for item in items] == ["mix_cohort / cohort_lost_stacked_column"]


def test_dedupe_gallery_items_keeps_one_card_per_artifact_id(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    primary_dir = source_root / "mix_multitier_bar"
    duplicate_dir = source_root / "mix_multitier_bar_dimension_panels"
    gallery_dir = source_root / "png-gallery"
    primary_dir.mkdir(parents=True)
    duplicate_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    for run_dir in (primary_dir, duplicate_dir):
        (run_dir / "multitier_bar_dimension_panels.html").write_text(
            '<script>Plotly.newPlot("chart", [{"type":"bar"}], {});</script>',
            encoding="utf-8",
        )
        source_pack_dir = run_dir / "source_pack"
        source_pack_dir.mkdir()
        (source_pack_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "plugin": "mix-contribution-analysis",
                    "artifacts": [
                        {
                            "artifact_id": "multitier_bar_dimension_panels",
                            "kind": "chart",
                            "path": "multitier_bar_dimension_panels.html",
                            "plugin": "mix-contribution-analysis",
                            "chart_type": "multitier_bar_dimension_panels",
                            "metrics": ["Sales"],
                            "active_dimensions": ["Company"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    items = gallery._iter_source_artifacts(
        source_root,
        gallery_dir,
        dimensions={},
        filters=[],
        include_source_pack=False,
        include_review_html=False,
        include_drilldowns=False,
    )

    deduped = gallery._dedupe_gallery_items(items)

    assert [item.label for item in deduped] == [
        "mix_multitier_bar / multitier_bar_dimension_panels"
    ]


def test_dedupe_rendered_gallery_items_removes_identical_png_cards(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    gallery_dir = source_root / "png-gallery"
    comparison_dir = source_root / "mix_comparison"
    regular_dir = source_root / "mix_regular"
    comparison_dir.mkdir(parents=True)
    regular_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    comparison_source = comparison_dir / "area_absolute.html"
    regular_source = regular_dir / "area_absolute.html"
    comparison_output = gallery_dir / "mix_comparison__area_absolute.png"
    regular_output = gallery_dir / "mix_regular__area_absolute.png"
    comparison_source.write_text("<html></html>", encoding="utf-8")
    regular_source.write_text("<html></html>", encoding="utf-8")
    comparison_output.write_bytes(b"same rendered png")
    regular_output.write_bytes(b"same rendered png")

    items = [
        gallery.GalleryItem(
            source_path=comparison_source,
            output_path=comparison_output,
            label="mix_comparison / area_absolute",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=regular_source,
            output_path=regular_output,
            label="mix_regular / area_absolute",
            dimensions=None,
        ),
    ]

    deduped = gallery._dedupe_rendered_gallery_items(items)

    assert [item.label for item in deduped] == ["mix_comparison / area_absolute"]
    assert comparison_output.exists()
    assert not regular_output.exists()


def test_sort_gallery_items_groups_by_source_family_then_plugin_source(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    gallery_dir = source_root / "png-gallery"
    gallery_dir.mkdir(parents=True)
    for run_name in (
        "period",
        "funnel",
        "statement",
        "attributes",
        "mix_current",
        "distribution",
        "scatter",
        "set_overlap",
        "variance",
    ):
        run_dir = source_root / run_name
        run_dir.mkdir(parents=True)
        (run_dir / "chart.html").write_text("<html></html>", encoding="utf-8")

    items = [
        gallery.GalleryItem(
            source_path=source_root / "attributes" / "chart.html",
            output_path=gallery_dir / "attributes__chart.png",
            label="attributes / chart",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=source_root / "period" / "chart.html",
            output_path=gallery_dir / "period__chart.png",
            label="period / chart",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=source_root / "funnel" / "chart.html",
            output_path=gallery_dir / "funnel__chart.png",
            label="funnel / chart",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=source_root / "statement" / "chart.html",
            output_path=gallery_dir / "statement__chart.png",
            label="statement / chart",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=source_root / "set_overlap" / "chart.html",
            output_path=gallery_dir / "set_overlap__chart.png",
            label="set_overlap / chart",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=source_root / "variance" / "chart.html",
            output_path=gallery_dir / "variance__chart.png",
            label="variance / chart",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=source_root / "scatter" / "chart.html",
            output_path=gallery_dir / "scatter__chart.png",
            label="scatter / chart",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=source_root / "mix_current" / "chart.html",
            output_path=gallery_dir / "mix_current__chart.png",
            label="mix_current / chart",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=source_root / "distribution" / "chart.html",
            output_path=gallery_dir / "distribution__chart.png",
            label="distribution / chart",
            dimensions=None,
        ),
    ]

    sorted_items = gallery._sort_gallery_items(items)

    assert [item.label for item in sorted_items] == [
        "variance / chart",
        "period / chart",
        "mix_current / chart",
        "scatter / chart",
        "distribution / chart",
        "set_overlap / chart",
        "funnel / chart",
        "statement / chart",
        "attributes / chart",
    ]


def test_build_index_suppresses_redundant_single_plugin_family_heading(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    source_dir = source_root / "audit-reconciliation"
    gallery_dir = source_root / "png-gallery"
    source_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)
    source_path = source_dir / "index.html"
    output_path = gallery_dir / "audit-reconciliation__index.png"
    source_path.write_text("<html></html>", encoding="utf-8")
    output_path.write_bytes(b"png")
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="audit-reconciliation / index",
        dimensions=None,
    )
    stats = {
        output_path: gallery.ImageStats(
            width=1600,
            height=900,
            byte_count=3,
            non_white_ratio=0.05,
            edge_ink_ratio=0.0,
        )
    }

    html = gallery._build_index([item], stats, gallery_dir)

    assert (
        '<h2 class="source-heading">audit reconciliation <span>1 items</span></h2>'
        in html
    )
    assert '<h2 class="plugin-heading">audit reconciliation' not in html


def test_default_skipped_artifact_excludes_generic_html_snapshot(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "client-intake" / "index.html"
    source_path.parent.mkdir()
    source_path.write_text(
        "<html><main>Plugin documentation</main></html>", encoding="utf-8"
    )

    assert gallery._is_default_skipped_artifact(
        source_path,
        include_source_pack=True,
        include_review_html=False,
        include_drilldowns=True,
    )


def test_default_skipped_artifact_keeps_plotly_chart_html(tmp_path: Path) -> None:
    source_path = tmp_path / "period" / "chart.html"
    source_path.parent.mkdir()
    source_path.write_text(
        '<script>Plotly.newPlot("chart", [{"type":"scatter"}], {});</script>',
        encoding="utf-8",
    )

    assert not gallery._is_default_skipped_artifact(
        source_path,
        include_source_pack=True,
        include_review_html=False,
        include_drilldowns=True,
    )


def test_sort_gallery_items_keeps_mix_chart_families_adjacent(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    gallery_dir = source_root / "png-gallery"
    gallery_dir.mkdir(parents=True)
    labels = [
        "mix_comparison / stacked_column_synthesis",
        "mix_comparison / column_total_with_overlay",
        "mix_comparison / related_metrics_bar",
        "mix_comparison / bar",
        "mix_comparison / stacked_bar",
        "mix_comparison / bar_small_multiples",
        "mix_current / stacked_bar_small_multiples",
        "mix_comparison / multitier_bar_dimension_panels",
        "mix_comparison / column_total",
        "mix_comparison / multitier_bar",
        "mix_comparison / related_metrics_bar_small_multiples",
        "mix_like_for_like / like_for_like_column_total",
        "mix_current / stacked_bar",
        "mix_comparison / multitier_bar_two_dimension",
        "mix_comparison / stacked_column",
        "mix_comparison / stacked_column_small_multiples",
        "mix_current / marimekko_small_multiples",
        "mix_comparison / stacked_bar_small_multiples",
        "mix_comparison / line",
        "mix_comparison / line_small_multiples",
        "mix_comparison / area_absolute",
        "mix_cohort / cohort_lost_stacked_column",
        "mix_comparison / area_share",
        "mix_current / barmekko",
        "mix_current / barmekko_small_multiples",
        "mix_current / marimekko",
        "mix_cohort / cohort_since_stacked_column",
        "mix_like_for_like / like_for_like_stacked_column",
    ]
    items = []
    for label in labels:
        group, stem = label.split(" / ", 1)
        source_dir = source_root / group
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / f"{stem}.html"
        source_path.write_text("<html></html>", encoding="utf-8")
        items.append(
            gallery.GalleryItem(
                source_path=source_path,
                output_path=gallery_dir / f"{group}__{stem}.png",
                label=label,
                dimensions=None,
            )
        )

    sorted_items = gallery._sort_gallery_items(items)

    assert [item.label for item in sorted_items] == [
        "mix_comparison / bar",
        "mix_comparison / stacked_bar",
        "mix_current / stacked_bar",
        "mix_comparison / bar_small_multiples",
        "mix_comparison / stacked_bar_small_multiples",
        "mix_current / stacked_bar_small_multiples",
        "mix_comparison / related_metrics_bar",
        "mix_comparison / related_metrics_bar_small_multiples",
        "mix_comparison / multitier_bar",
        "mix_comparison / multitier_bar_dimension_panels",
        "mix_comparison / multitier_bar_two_dimension",
        "mix_comparison / column_total",
        "mix_comparison / column_total_with_overlay",
        "mix_like_for_like / like_for_like_column_total",
        "mix_comparison / stacked_column",
        "mix_comparison / stacked_column_small_multiples",
        "mix_like_for_like / like_for_like_stacked_column",
        "mix_comparison / stacked_column_synthesis",
        "mix_cohort / cohort_since_stacked_column",
        "mix_cohort / cohort_lost_stacked_column",
        "mix_comparison / line",
        "mix_comparison / line_small_multiples",
        "mix_comparison / area_absolute",
        "mix_comparison / area_share",
        "mix_current / barmekko",
        "mix_current / barmekko_small_multiples",
        "mix_current / marimekko",
        "mix_current / marimekko_small_multiples",
    ]


def test_sort_gallery_items_keeps_period_tables_adjacent(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    period_dir = source_root / "period"
    gallery_dir = source_root / "png-gallery"
    period_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)
    for name in (
        "year_over_year_slope.html",
        "year_over_year_slope_small_multiples.html",
        "year_over_year_waterfall.html",
        "year_over_year_waterfall_small_multiples.html",
        "year_over_year_dot.html",
        "year_over_year_small_multiples.html",
        "year_over_year_by_period.html",
        "year_over_year_by_period_small_multiples.html",
        "year_over_year_line.html",
        "time_series_table.html",
        "comparison_table.html",
    ):
        (period_dir / name).write_text("<html></html>", encoding="utf-8")

    items = [
        gallery.GalleryItem(
            source_path=period_dir / "year_over_year_slope.html",
            output_path=gallery_dir / "period__year_over_year_slope.png",
            label="period / year_over_year_slope",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "year_over_year_slope_small_multiples.html",
            output_path=gallery_dir
            / "period__year_over_year_slope_small_multiples.png",
            label="period / year_over_year_slope_small_multiples",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "year_over_year_waterfall.html",
            output_path=gallery_dir / "period__year_over_year_waterfall.png",
            label="period / year_over_year_waterfall",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "year_over_year_waterfall_small_multiples.html",
            output_path=gallery_dir
            / "period__year_over_year_waterfall_small_multiples.png",
            label="period / year_over_year_waterfall_small_multiples",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "year_over_year_dot.html",
            output_path=gallery_dir / "period__year_over_year_dot.png",
            label="period / year_over_year_dot",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "year_over_year_small_multiples.html",
            output_path=gallery_dir / "period__year_over_year_small_multiples.png",
            label="period / year_over_year_small_multiples",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "year_over_year_line.html",
            output_path=gallery_dir / "period__year_over_year_line.png",
            label="period / year_over_year_line",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "year_over_year_by_period.html",
            output_path=gallery_dir / "period__year_over_year_by_period.png",
            label="period / year_over_year_by_recency_window",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "year_over_year_by_period_small_multiples.html",
            output_path=gallery_dir
            / "period__year_over_year_by_period_small_multiples.png",
            label="period / year_over_year_by_recency_window_small_multiples",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "time_series_table.html",
            output_path=gallery_dir / "period__time_series_table.png",
            label="period / time_series_table",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_dir / "comparison_table.html",
            output_path=gallery_dir / "period__comparison_table.png",
            label="period / comparison_table",
            dimensions=None,
        ),
    ]

    sorted_items = gallery._sort_gallery_items(items)

    assert [item.label for item in sorted_items] == [
        "period / comparison_table",
        "period / time_series_table",
        "period / year_over_year_by_recency_window",
        "period / year_over_year_by_recency_window_small_multiples",
        "period / year_over_year_line",
        "period / year_over_year_small_multiples",
        "period / year_over_year_waterfall",
        "period / year_over_year_waterfall_small_multiples",
        "period / year_over_year_dot",
        "period / year_over_year_slope",
        "period / year_over_year_slope_small_multiples",
    ]


def test_build_index_renders_plugin_source_headings(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    gallery_dir = source_root / "png-gallery"
    attributes_dir = source_root / "attributes"
    mix_dir = source_root / "mix_current"
    period_dir = source_root / "period"
    attributes_dir.mkdir(parents=True)
    mix_dir.mkdir(parents=True)
    period_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    attributes_source = attributes_dir / "attribute_bridge_table.html"
    mix_source = mix_dir / "stacked_bar.html"
    period_source = period_dir / "year_over_year_dot.html"
    attributes_output = gallery_dir / "attributes__attribute_bridge_table.png"
    mix_output = gallery_dir / "mix_current__stacked_bar.png"
    period_output = gallery_dir / "period__year_over_year_dot.png"
    attributes_source.write_text("<html></html>", encoding="utf-8")
    mix_source.write_text("<html></html>", encoding="utf-8")
    period_source.write_text("<html></html>", encoding="utf-8")
    items = [
        gallery.GalleryItem(
            source_path=attributes_source,
            output_path=attributes_output,
            label="attributes / attribute_bridge_table",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=mix_source,
            output_path=mix_output,
            label="mix_current / stacked_bar",
            dimensions=None,
        ),
        gallery.GalleryItem(
            source_path=period_source,
            output_path=period_output,
            label="period / year_over_year_dot",
            dimensions=None,
        ),
    ]
    stats = {
        attributes_output: gallery.ImageStats(
            width=1280,
            height=560,
            byte_count=100,
            non_white_ratio=0.2,
            edge_ink_ratio=0.0,
        ),
        mix_output: gallery.ImageStats(
            width=1400,
            height=900,
            byte_count=100,
            non_white_ratio=0.2,
            edge_ink_ratio=0.0,
        ),
        period_output: gallery.ImageStats(
            width=1400,
            height=900,
            byte_count=100,
            non_white_ratio=0.2,
            edge_ink_ratio=0.0,
        ),
    }

    html = gallery._build_index(gallery._sort_gallery_items(items), stats, gallery_dir)

    assert "Movement and period sources <span>1 items</span>" in html
    assert "Mix and composition sources <span>1 items</span>" in html
    assert "Structured table sources <span>1 items</span>" in html
    assert "function scrollToHashTarget()" in html
    assert "window.addEventListener('hashchange',scheduleHashScroll)" in html
    assert "image.addEventListener('load',scheduleHashScroll,{once:true})" in html
    assert "Mix &amp; Contribution Analysis <span>1 items</span>" in html
    assert "Period Comparison <span>1 items</span>" in html
    assert "Attribute Tables <span>1 items</span>" in html


def test_build_index_flags_sparse_and_edge_heavy_images(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "period"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    source_path = run_dir / "year_over_year_dot.html"
    output_path = gallery_dir / "period__year_over_year_dot.png"
    source_path.write_text("<html></html>", encoding="utf-8")
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="period / year_over_year_dot",
        dimensions=None,
    )

    html = gallery._build_index(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.004,
                edge_ink_ratio=0.03,
                crop_risk_ink_ratio=0.03,
                top_edge_ink_ratio=0.03,
                right_edge_ink_ratio=0.03,
            )
        },
        gallery_dir,
    )

    assert "1 QA-flagged | 1 crop-risk | 1 sparse" in html
    assert ">crop risk</span>" in html
    assert ">sparse</span>" in html


def test_build_index_ignores_axis_edge_ink_without_crop_risk(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "distribution"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    source_path = run_dir / "histogram.html"
    output_path = gallery_dir / "distribution__histogram.png"
    source_path.write_text("<html></html>", encoding="utf-8")
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="distribution / histogram",
        dimensions=None,
    )

    html = gallery._build_index(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.08,
                crop_risk_ink_ratio=0.0,
                bottom_edge_ink_ratio=0.08,
                left_edge_ink_ratio=0.08,
            )
        },
        gallery_dir,
    )

    assert "0 QA-flagged | 0 crop-risk | 0 sparse" in html
    assert ">crop risk</span>" not in html


def test_build_index_accepts_sparse_nonempty_dot_html(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "period"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    source_path = run_dir / "year_over_year_dot.html"
    output_path = gallery_dir / "period__year_over_year_dot.png"
    source_path.write_text(
        '<script>Plotly.newPlot("chart", [{"type":"scatter","x":[1],"y":[2]}], {});</script>',
        encoding="utf-8",
    )
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="period / year_over_year_dot",
        dimensions=None,
    )

    html = gallery._build_index(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.004,
                edge_ink_ratio=0.0,
                crop_risk_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    assert "0 QA-flagged | 0 crop-risk | 0 sparse" in html
    assert ">sparse</span>" not in html


def test_build_index_flags_sparse_empty_dot_html(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "period"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    source_path = run_dir / "year_over_year_dot.html"
    output_path = gallery_dir / "period__year_over_year_dot.png"
    source_path.write_text(
        '<script>Plotly.newPlot("chart", [], {});</script>',
        encoding="utf-8",
    )
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="period / year_over_year_dot",
        dimensions=None,
    )

    html = gallery._build_index(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.004,
                edge_ink_ratio=0.0,
                crop_risk_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    assert "1 QA-flagged | 0 crop-risk | 1 sparse" in html
    assert ">sparse</span>" in html


def test_build_manifest_contains_sidecars_context_stats_and_flags(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_cohort"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    source_path = run_dir / "cohort_lost_stacked_column.html"
    output_path = gallery_dir / "mix_cohort__cohort_lost_stacked_column.png"
    source_path.write_text("<html></html>", encoding="utf-8")
    (run_dir / "cohort_lost_stacked_column_chart_context.json").write_text(
        json.dumps(
            {
                "chart_title_lines": [
                    "Mexico hair color",
                    "Sales in mEUR by Barcode_Lost",
                    "2015, 2016, 2017",
                ],
                "legacy_chart": "stacked column",
                "metrics": ["Sales"],
                "dimensions": ["Barcode_Lost"],
                "selected_periods": ["2015", "2016", "2017"],
                "plotly_figures": [
                    {
                        "traces": [
                            {"type": "bar", "width": [0.44999999999999996, 0.45]},
                            {"type": "bar", "width": [0.25]},
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "cohort_lost_stacked_column_chart_data.csv").write_text(
        "dimension,value\n2017,10\n",
        encoding="utf-8",
    )
    (run_dir / "used_recipe.json").write_text("{}", encoding="utf-8")
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="mix_cohort / cohort_lost_stacked_column",
        dimensions=None,
    )
    stats = {
        output_path: gallery.ImageStats(
            width=1400,
            height=900,
            byte_count=100,
            non_white_ratio=0.004,
            edge_ink_ratio=0.03,
            crop_risk_ink_ratio=0.03,
            top_edge_ink_ratio=0.03,
            right_edge_ink_ratio=0.03,
        )
    }

    manifest = gallery._build_manifest([item], stats, gallery_dir)

    assert manifest["schema_version"] == "1.1"
    assert manifest["item_count"] == 1
    assert manifest["quality_summary"] == "1 QA-flagged | 1 crop-risk | 1 sparse"
    assert manifest["quality_thresholds"] == {
        "high_edge_ink_ratio": gallery.HIGH_EDGE_INK_RATIO,
        "high_crop_risk_ink_ratio": gallery.HIGH_CROP_RISK_INK_RATIO,
        "low_non_white_ratio": gallery.LOW_NON_WHITE_RATIO,
    }
    item_payload = manifest["items"][0]
    assert item_payload["label"] == "mix_cohort / cohort_lost_stacked_column"
    assert item_payload["source"] == "../mix_cohort/cohort_lost_stacked_column.html"
    assert item_payload["output"] == "mix_cohort__cohort_lost_stacked_column.png"
    assert item_payload["artifact_type"] == "html"
    assert item_payload["dimensions"] == {"width": 1400, "height": 900}
    assert item_payload["context_summary"] == {
        "capability": None,
        "grammar": "stacked column",
        "metrics": "Sales",
        "dimensions": "Barcode_Lost",
        "periods": "2015, 2016, 2017",
        "trace_widths": "0.25, 0.45",
        "source_reference": None,
    }
    assert item_payload["title_context"] == {
        "lines": [
            "Mexico hair color",
            "Sales in mEUR by Barcode_Lost",
            "2015, 2016, 2017",
        ],
        "who": "Mexico hair color",
        "what": "Sales in mEUR by Barcode_Lost",
        "when": "2015, 2016, 2017",
        "source": "../mix_cohort/cohort_lost_stacked_column_chart_context.json",
    }
    assert [flag["label"] for flag in item_payload["quality_flags"]] == [
        "crop risk",
        "sparse",
    ]
    assert {sidecar["label"] for sidecar in item_payload["sidecars"]} == {
        "source",
        "context",
        "data",
        "recipe",
    }
    assert item_payload["artifact_contract"] is None
    assert item_payload["artifact_readiness"]["missing_sidecars"] == ["manifest"]
    assert item_payload["artifact_readiness"]["issues"] == [
        "missing_manifest",
        "missing_artifact_contract",
    ]
    assert item_payload["artifact_readiness"]["ready"] is False


def test_build_manifest_extracts_semantic_html_title_context(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "funnel"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()
    source_path = run_dir / "funnel_stage_table.html"
    output_path = gallery_dir / "funnel__funnel_stage_table.png"
    source_path.write_text(
        (
            '<main data-gallery-screenshot><header class="report-title">'
            "<h1>Baby CRM extract</h1>"
            "<p>Lead readiness funnel in records</p>"
            "<p>Sequential gates</p>"
            "</header></main>"
        ),
        encoding="utf-8",
    )
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="funnel / funnel_stage_table",
        dimensions=None,
    )

    manifest = gallery._build_manifest(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1200,
                height=700,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    assert manifest["items"][0]["title_context"] == {
        "lines": [
            "Baby CRM extract",
            "Lead readiness funnel in records",
            "Sequential gates",
        ],
        "who": "Baby CRM extract",
        "what": "Lead readiness funnel in records",
        "when": "Sequential gates",
        "source": "../funnel/funnel_stage_table.html",
    }


def test_build_index_uses_source_pack_metadata_when_local_sidecar_is_missing(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "period"
    gallery_dir = source_root / "png-gallery"
    source_pack_dir = run_dir / "source_pack"
    context_dir = source_pack_dir / "contexts"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()
    context_dir.mkdir(parents=True)

    source_path = run_dir / "year_over_year_dot.html"
    output_path = gallery_dir / "period__year_over_year_dot.png"
    source_path.write_text(
        '{"type":"scatter","x":[1],"y":[2]}',
        encoding="utf-8",
    )
    (context_dir / "period_comparison_context.json").write_text(
        json.dumps({"analysis_type": "period_comparison"}),
        encoding="utf-8",
    )
    (source_pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "artifact_id": "year_over_year_dot",
                        "kind": "charts",
                        "source_path": "year_over_year_dot.html",
                        "source_payload_path": (
                            "contexts/period_comparison_context.json"
                        ),
                        "capability_id": "period_comparison.dot",
                        "plugin": "period-comparison",
                        "chart_family": "period_comparison",
                        "chart_type": "dot",
                        "resolved_parameters": {
                            "metric": "Sales",
                            "dimensions": ["Company"],
                            "baseline_period": "PY",
                            "comparison_period": "AC",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="period / year_over_year_dot",
        dimensions=None,
    )
    html = gallery._build_index(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )
    manifest = gallery._build_manifest(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    assert "<b>capability</b> period_comparison.dot" in html
    assert "<b>grammar</b> period_comparison.dot" in html
    assert "<b>metric</b> Sales" in html
    assert "<b>dimension</b> Company" in html
    assert "<b>period</b> PY, AC" in html
    assert "<b>source</b> year_over_year_dot" in html
    assert (
        'href="../period/source_pack/contexts/period_comparison_context.json">'
        "context</a>"
    ) in html
    assert 'href="../period/source_pack/manifest.json">manifest</a>' in html
    assert manifest["items"][0]["context_summary"] == {
        "capability": "period_comparison.dot",
        "grammar": "period_comparison.dot",
        "metrics": "Sales",
        "dimensions": "Company",
        "periods": "PY, AC",
        "trace_widths": None,
        "source_reference": "year_over_year_dot",
    }


def test_build_manifest_uses_canonical_csv_as_data_sidecar_when_chart_data_missing(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "distribution"
    gallery_dir = source_root / "png-gallery"
    source_pack_dir = run_dir / "source_pack"
    context_dir = source_pack_dir / "contexts"
    context_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)

    source_path = run_dir / "boxplot.html"
    output_path = gallery_dir / "distribution__boxplot.png"
    source_path.write_text("<html></html>", encoding="utf-8")
    (run_dir / "distribution_canonical.csv").write_text(
        "Company,Units\nA,10\n",
        encoding="utf-8",
    )
    (run_dir / "used_recipe.json").write_text("{}", encoding="utf-8")
    (context_dir / "distribution_context.json").write_text(
        json.dumps({"analysis_type": "distribution"}),
        encoding="utf-8",
    )
    (source_pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "producer": {"plugin": "distribution-analysis"},
                "artifacts": [
                    {
                        "artifact_id": "distribution_canonical",
                        "kind": "table",
                        "path": "distribution_canonical.csv",
                    },
                    {
                        "artifact_id": "boxplot",
                        "kind": "chart",
                        "path": "boxplot.html",
                        "source_payload_path": ("contexts/distribution_context.json"),
                        "capability_id": "distribution.boxplot",
                        "resolved_parameters": {"metric": "Units"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="distribution / boxplot",
        dimensions=None,
    )

    manifest = gallery._build_manifest(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1400,
                height=900,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    sidecars = {
        sidecar["label"]: sidecar["href"]
        for sidecar in manifest["items"][0]["sidecars"]
    }
    assert sidecars["data"] == "../distribution/distribution_canonical.csv"
    assert manifest["items"][0]["artifact_contract"]["capability_id"] == (
        "distribution.boxplot"
    )
    assert manifest["items"][0]["artifact_readiness"]["ready"] is True


def test_build_manifest_uses_variance_results_for_standard_waterfall_data_sidecar(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "variance"
    gallery_dir = source_root / "png-gallery"
    source_pack_dir = run_dir / "source_pack"
    context_dir = source_pack_dir / "contexts"
    table_dir = source_pack_dir / "tables"
    context_dir.mkdir(parents=True)
    table_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)

    source_path = run_dir / "waterfall.png"
    output_path = gallery_dir / "variance__waterfall.png"
    source_path.write_bytes(b"png")
    (run_dir / "used_recipe.json").write_text("{}", encoding="utf-8")
    (context_dir / "standard_variance_context.json").write_text(
        json.dumps({"chart_type": "standard_variance_waterfall"}),
        encoding="utf-8",
    )
    (table_dir / "variance_results.csv").write_text(
        "variance_type,variance_amount\nUnits,10\n",
        encoding="utf-8",
    )
    (table_dir / "waterfall_small_multiples_summary.csv").write_text(
        "panel,variance_amount\nA,10\n",
        encoding="utf-8",
    )
    (table_dir / "root_cause_sweep_summary.csv").write_text(
        "alternative,total\n1,10\n",
        encoding="utf-8",
    )
    (source_pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "producer": {"plugin": "variance-analysis"},
                "artifacts": [
                    {
                        "artifact_id": "variance_results",
                        "kind": "tables",
                        "pack_path": "source_pack/tables/variance_results.csv",
                    },
                    {
                        "artifact_id": "waterfall_small_multiples_summary",
                        "kind": "tables",
                        "pack_path": (
                            "source_pack/tables/"
                            "waterfall_small_multiples_summary.csv"
                        ),
                    },
                    {
                        "artifact_id": "root_cause_sweep_summary",
                        "kind": "tables",
                        "pack_path": (
                            "source_pack/tables/root_cause_sweep_summary.csv"
                        ),
                    },
                    {
                        "artifact_id": "waterfall",
                        "kind": "charts",
                        "source_path": "waterfall.png",
                        "source_payload_path": (
                            "contexts/standard_variance_context.json"
                        ),
                        "capability_id": "variance.scenario_bridge",
                        "resolved_parameters": {"metric": "Sales"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="variance / waterfall",
        dimensions=None,
    )

    manifest = gallery._build_manifest(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1000,
                height=388,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    sidecars = {
        sidecar["label"]: sidecar["href"]
        for sidecar in manifest["items"][0]["sidecars"]
    }
    assert sidecars["data"] == "../variance/source_pack/tables/variance_results.csv"
    assert manifest["items"][0]["artifact_readiness"]["ready"] is True


def test_build_manifest_uses_small_multiples_summary_before_variance_fallback(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "variance"
    gallery_dir = source_root / "png-gallery"
    source_pack_dir = run_dir / "source_pack"
    context_dir = source_pack_dir / "contexts"
    table_dir = source_pack_dir / "tables"
    context_dir.mkdir(parents=True)
    table_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)

    source_path = run_dir / "waterfall_small_multiples.png"
    output_path = gallery_dir / "variance__waterfall_small_multiples.png"
    source_path.write_bytes(b"png")
    (run_dir / "used_recipe.json").write_text("{}", encoding="utf-8")
    (context_dir / "waterfall_small_multiples_context.json").write_text(
        json.dumps({"analysis_type": "standard_variance_small_multiples"}),
        encoding="utf-8",
    )
    (table_dir / "waterfall_small_multiples_summary.csv").write_text(
        "panel,variance_amount\nA,10\n",
        encoding="utf-8",
    )
    (table_dir / "variance_results.csv").write_text(
        "variance_type,variance_amount\nUnits,10\n",
        encoding="utf-8",
    )
    (source_pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "producer": {"plugin": "variance-analysis"},
                "artifacts": [
                    {
                        "artifact_id": "waterfall_small_multiples_summary",
                        "kind": "tables",
                        "pack_path": (
                            "source_pack/tables/"
                            "waterfall_small_multiples_summary.csv"
                        ),
                    },
                    {
                        "artifact_id": "variance_results",
                        "kind": "tables",
                        "pack_path": "source_pack/tables/variance_results.csv",
                    },
                    {
                        "artifact_id": "waterfall_small_multiples",
                        "kind": "charts",
                        "source_path": "waterfall_small_multiples.png",
                        "source_payload_path": (
                            "contexts/waterfall_small_multiples_context.json"
                        ),
                        "capability_id": "variance.scenario_bridge",
                        "resolved_parameters": {"metric": "Sales"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="variance / waterfall_small_multiples",
        dimensions=None,
    )

    manifest = gallery._build_manifest(
        [item],
        {
            output_path: gallery.ImageStats(
                width=1510,
                height=1159,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    sidecars = {
        sidecar["label"]: sidecar["href"]
        for sidecar in manifest["items"][0]["sidecars"]
    }
    assert sidecars["data"] == (
        "../variance/source_pack/tables/waterfall_small_multiples_summary.csv"
    )
    assert manifest["items"][0]["artifact_readiness"]["ready"] is True


def test_build_index_uses_source_pack_metadata_for_table_artifact(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "period"
    gallery_dir = source_root / "png-gallery"
    source_pack_dir = run_dir / "source_pack"
    context_dir = source_pack_dir / "contexts"
    context_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)

    source_path = run_dir / "comparison_table.html"
    output_path = gallery_dir / "period__comparison_table.png"
    source_path.write_text(
        "<html><body><table><tr><td>Total</td></tr></table></body></html>",
        encoding="utf-8",
    )
    (context_dir / "comparison_table_context.json").write_text(
        json.dumps(
            {
                "chart": "comparison_table",
                "metric": "Value_LC",
                "metric_label": "Sales",
            }
        ),
        encoding="utf-8",
    )
    (source_pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "producer": {"plugin": "period-comparison"},
                "artifacts": [
                    {
                        "artifact_id": "comparison_table",
                        "kind": "tables",
                        "source_path": "comparison_table.html",
                        "source_payload_path": (
                            "contexts/comparison_table_context.json"
                        ),
                        "table_spec_name": "comparison_table",
                        "table_key": "comparison_table",
                        "plugin": "period-comparison",
                        "table_family": "period_comparison",
                        "table_type": "comparison_table",
                        "resolved_parameters": {
                            "metric": "Sales",
                            "dimensions": ["Company"],
                            "baseline_period": "PY",
                            "comparison_period": "AC",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    item = gallery.GalleryItem(
        source_path=source_path,
        output_path=output_path,
        label="period / comparison_table",
        dimensions=None,
    )
    html = gallery._build_index(
        [item],
        {
            output_path: gallery.ImageStats(
                width=960,
                height=560,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )
    manifest = gallery._build_manifest(
        [item],
        {
            output_path: gallery.ImageStats(
                width=960,
                height=560,
                byte_count=100,
                non_white_ratio=0.2,
                edge_ink_ratio=0.0,
            )
        },
        gallery_dir,
    )

    assert "<b>capability</b>" not in html
    assert "<b>grammar</b> comparison_table" in html
    assert "<b>metric</b> Sales" in html
    assert "<b>metric</b> Value_LC" not in html
    assert "<b>dimension</b> Company" in html
    assert "<b>period</b> PY, AC" in html
    assert "<b>source</b> comparison_table" in html
    assert 'href="../period/source_pack/manifest.json">manifest</a>' in html
    assert manifest["items"][0]["context_summary"] == {
        "capability": None,
        "grammar": "comparison_table",
        "metrics": "Sales",
        "dimensions": "Company",
        "periods": "PY, AC",
        "trace_widths": None,
        "source_reference": "comparison_table",
    }
    assert manifest["items"][0]["artifact_type"] == "table"


def test_context_summary_infers_capability_from_catalog_chart_spec(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_multitier_bar"
    source_pack_dir = run_dir / "source_pack"
    context_dir = source_pack_dir / "contexts"
    gallery_dir = source_root / "png-gallery"
    context_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)

    source_path = run_dir / "multitier_bar.html"
    source_path.write_text("<html></html>", encoding="utf-8")
    (run_dir / "multitier_bar_chart_context.json").write_text(
        json.dumps(
            {
                "analysis_type": "mix_contribution",
                "dimensions": ["Company", "Brand", "Channel"],
            }
        ),
        encoding="utf-8",
    )
    (context_dir / "mix_contribution_context.json").write_text(
        json.dumps({"analysis_type": "mix_contribution"}),
        encoding="utf-8",
    )
    (source_pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "plugin": "mix-contribution-analysis",
                "artifacts": [
                    {
                        "artifact_id": "multitier_bar",
                        "kind": "chart",
                        "path": "multitier_bar.html",
                        "source_payload_path": (
                            "contexts/mix_contribution_context.json"
                        ),
                        "chart_type": "multitier_bar",
                        "plugin": "mix-contribution-analysis",
                        "metrics": ["Sales"],
                        "active_dimensions": ["Company"],
                        "configured_dimensions": [
                            "Company",
                            "Brand",
                            "Channel",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = gallery._context_summary(
        gallery.GalleryItem(
            source_path=source_path,
            output_path=gallery_dir / "mix_multitier_bar__multitier_bar.png",
            label="mix_multitier_bar / multitier_bar",
            dimensions=None,
        )
    )

    assert summary is not None
    assert summary.capability is None
    assert summary.grammar == "multitier_bar"
    assert summary.metrics == "Sales"
    assert summary.dimensions == "Company"


def test_context_summary_omits_mix_configured_dimensions_without_active_dimension(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_multitier_bar"
    source_pack_dir = run_dir / "source_pack"
    context_dir = source_pack_dir / "contexts"
    gallery_dir = source_root / "png-gallery"
    context_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)

    source_path = run_dir / "multitier_bar.html"
    source_path.write_text("<html></html>", encoding="utf-8")
    (run_dir / "multitier_bar_chart_context.json").write_text(
        json.dumps(
            {
                "analysis_type": "mix_contribution",
                "dimensions": ["Company", "Brand", "Channel"],
            }
        ),
        encoding="utf-8",
    )
    (context_dir / "mix_contribution_context.json").write_text(
        json.dumps({"analysis_type": "mix_contribution"}),
        encoding="utf-8",
    )
    (source_pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "plugin": "mix-contribution-analysis",
                "artifacts": [
                    {
                        "artifact_id": "multitier_bar",
                        "kind": "chart",
                        "path": "multitier_bar.html",
                        "source_payload_path": (
                            "contexts/mix_contribution_context.json"
                        ),
                        "chart_type": "multitier_bar",
                        "plugin": "mix-contribution-analysis",
                        "metrics": ["Sales"],
                        "configured_dimensions": [
                            "Company",
                            "Brand",
                            "Channel",
                        ],
                        "available_dimensions": [
                            "Company",
                            "Brand",
                            "Channel",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = gallery._context_summary(
        gallery.GalleryItem(
            source_path=source_path,
            output_path=gallery_dir / "mix_multitier_bar__multitier_bar.png",
            label="mix_multitier_bar / multitier_bar",
            dimensions=None,
        )
    )

    assert summary is not None
    assert summary.capability is None
    assert summary.dimensions is None


def test_context_summary_infers_set_overlap_capability_from_artifact_path(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "set_overlap"
    source_pack_dir = run_dir / "source_pack"
    gallery_dir = source_root / "png-gallery"
    source_pack_dir.mkdir(parents=True)
    gallery_dir.mkdir(parents=True)

    source_path = run_dir / "upset.html"
    source_path.write_text("<html></html>", encoding="utf-8")
    (source_pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "plugin": "set-overlap-analysis",
                "artifacts": [
                    {
                        "artifact_type": "chart",
                        "path": "upset.html",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = gallery._context_summary(
        gallery.GalleryItem(
            source_path=source_path,
            output_path=gallery_dir / "set_overlap__upset.png",
            label="set_overlap / upset",
            dimensions=None,
        )
    )

    assert summary is not None
    assert summary.capability is None
    assert summary.grammar is None


def test_clear_gallery_dir_removes_manifest(tmp_path: Path) -> None:
    gallery_dir = tmp_path / "png-gallery"
    gallery_dir.mkdir()
    (gallery_dir / "index.html").write_text("old", encoding="utf-8")
    (gallery_dir / "manifest.json").write_text("old", encoding="utf-8")
    (gallery_dir / "chart.png").write_bytes(b"old")
    (gallery_dir / "keep.txt").write_text("keep", encoding="utf-8")

    gallery._clear_gallery_dir(gallery_dir)

    assert not (gallery_dir / "index.html").exists()
    assert not (gallery_dir / "manifest.json").exists()
    assert not (gallery_dir / "chart.png").exists()
    assert (gallery_dir / "keep.txt").exists()


def test_build_gallery_keeps_existing_gallery_when_browser_launch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_comparison"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()

    source_path = run_dir / "column_total.html"
    source_path.write_text(
        '<script>Plotly.newPlot("chart", [{"type":"bar"}], {});</script>',
        encoding="utf-8",
    )
    (gallery_dir / "index.html").write_text("old index", encoding="utf-8")
    (gallery_dir / "manifest.json").write_text("old manifest", encoding="utf-8")
    (gallery_dir / "old.png").write_bytes(b"old png")

    class BrowserLauncher:
        def launch(self, **_: object) -> object:
            raise RuntimeError("browser unavailable")

    class PlaywrightContext:
        chromium = BrowserLauncher()

        def __enter__(self) -> "PlaywrightContext":
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(gallery, "sync_playwright", PlaywrightContext)

    args = gallery._parse_args(
        ["--source-root", str(source_root), "--gallery-dir", str(gallery_dir)]
    )

    with pytest.raises(RuntimeError, match="browser unavailable"):
        gallery._build_gallery(args)

    assert (gallery_dir / "index.html").read_text(encoding="utf-8") == "old index"
    assert (gallery_dir / "manifest.json").read_text(encoding="utf-8") == "old manifest"
    assert (gallery_dir / "old.png").read_bytes() == b"old png"
    assert not gallery._staging_gallery_dir(gallery_dir).exists()
