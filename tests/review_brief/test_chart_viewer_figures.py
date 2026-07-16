from __future__ import annotations

import sys
import types

if "parsers.extractors" not in sys.modules:
    parsers_pkg = types.ModuleType("parsers")
    extractors_mod = types.ModuleType("parsers.extractors")
    extractors_mod.normalise_name = lambda value: str(value)
    extractors_mod.extract_beneficiary = lambda _text: ""
    extractors_mod.extract_references = lambda _text: []
    parsers_pkg.extractors = extractors_mod
    sys.modules["parsers"] = parsers_pkg
    sys.modules["parsers.extractors"] = extractors_mod

from modules.pdp import api as pdp_api


def test_review_brief_chart_figures_stacked_share_renderer_removed() -> None:
    chart = {
        "chart_type": "stacked_share",
        "title": "Demo stacked",
        "rows": [
            {"month": "2024-01-01", "segment": "A", "share_pct": 60.0},
            {"month": "2024-01-01", "segment": "B", "share_pct": 40.0},
            {"month": "2024-02-01", "segment": "A", "share_pct": 55.0},
            {"month": "2024-02-01", "segment": "B", "share_pct": 45.0},
        ],
    }

    figures = pdp_api._review_brief_chart_figures(chart)
    assert figures == []


def test_review_brief_chart_figures_stacked_share_title_renderer_removed() -> None:
    chart = {
        "chart_id": "us-cosmetics_stacked_form_blush_deadbeef1234",
        "dataset": "us_cosmetics",
        "chart_type": "stacked_share",
        "category_label": "blush",
        "retailers": ["ulta"],
        "dimensions": [{"id": "form", "label": "form"}],
        "rows": [
            {"month": "2022-01-01", "segment": "cream", "share_pct": 52.9},
            {"month": "2022-01-01", "segment": "liquid", "share_pct": 9.0},
            {"month": "2025-09-01", "segment": "cream", "share_pct": 43.6},
            {"month": "2025-09-01", "segment": "liquid", "share_pct": 20.0},
        ],
    }

    figures = pdp_api._review_brief_chart_figures(chart)
    assert figures == []


def test_review_brief_chart_figures_stacked_share_highlight_renderer_removed() -> None:
    chart = {
        "chart_type": "stacked_share",
        "chart_palette": "bain",
        "title": "Highlighted stacked",
        "payload": {"highlighted_dimension": ["matte"]},
        "rows": [
            {"month": "2024-01-01", "segment": "matte", "share_pct": 40.0},
            {"month": "2024-01-01", "segment": "dewy", "share_pct": 60.0},
            {"month": "2024-02-01", "segment": "matte", "share_pct": 43.0},
            {"month": "2024-02-01", "segment": "dewy", "share_pct": 57.0},
        ],
    }

    figures = pdp_api._review_brief_chart_figures(chart)
    assert figures == []


def test_review_brief_chart_figures_stacked_share_annual_renderer_removed() -> None:
    chart = {
        "chart_type": "stacked_share",
        "title": "Annual stacked",
        "rows": [
            {"year": "2023", "segment": "A", "share_pct": 62.0},
            {"year": "2023", "segment": "B", "share_pct": 38.0},
            {"year": "2024", "segment": "A", "share_pct": 59.0},
            {"year": "2024", "segment": "B", "share_pct": 41.0},
        ],
    }

    figures = pdp_api._review_brief_chart_figures(chart)
    assert figures == []


def test_review_brief_chart_figures_stacked_column_absolute_renderer_removed() -> None:
    chart = {
        "chart_type": "stacked_column_absolute",
        "title": "Absolute stacked",
        "payload": {"metric": "sales"},
        "rows": [
            {"month": "2024-01-01", "segment": "A", "sales": 10.0},
            {"month": "2024-01-01", "segment": "B", "sales": 6.0},
            {"month": "2024-02-01", "segment": "A", "sales": 11.0},
            {"month": "2024-02-01", "segment": "B", "sales": 5.0},
        ],
    }

    figures = pdp_api._review_brief_chart_figures(chart)
    assert figures == []


def test_review_brief_chart_figures_combo_total_absolute_renderer_removed() -> None:
    chart = {
        "chart_type": "combo_total_absolute",
        "title": "Absolute combo",
        "payload": {"bar_metric": "sales", "line_metric": "units"},
        "rows": [
            {"month": "2024-01-01", "sales": 20.0, "units": 2.0, "price": 10.0},
            {"month": "2024-02-01", "sales": 22.0, "units": 2.2, "price": 10.0},
        ],
    }

    figures = pdp_api._review_brief_chart_figures(chart)
    assert figures == []


def test_review_brief_chart_figures_slope_applies_bain_highlight_to_attribute() -> None:
    chart = {
        "chart_type": "slope_share",
        "chart_palette": "bain",
        "title": "Highlighted slope",
        "payload": {"highlighted_dimension": ["matte"]},
        "rows": [
            {
                "brand": "brand_a",
                "attribute": "matte",
                "start_share_pct": 10.0,
                "end_share_pct": 20.0,
            },
            {
                "brand": "brand_b",
                "attribute": "dewy",
                "start_share_pct": 30.0,
                "end_share_pct": 35.0,
            },
        ],
    }

    figures = pdp_api._review_brief_chart_figures(chart)
    assert figures
    _facet, fig = figures[0]

    matte_traces = [t for t in fig.data if "matte" in str(t.name).lower()]
    assert matte_traces
    assert all(str(trace.line.color).lower() == "#cb2026" for trace in matte_traces)

    dewy_traces = [t for t in fig.data if "dewy" in str(t.name).lower()]
    assert dewy_traces
    assert all(str(trace.line.color).lower() != "#cb2026" for trace in dewy_traces)
