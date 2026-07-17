from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi import Request
from fastapi.testclient import TestClient  # type: ignore  # pylint: disable=wrong-import-position

import modules.pdp.api as pdp_api
from modules.auth.dependencies import (
    require_authenticated_user,
    require_authenticated_user_for_site,
)
from modules.auth.session import AuthenticatedUser
from modules.pdp.api import app


def _allow_sales_brief_calls() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    app.dependency_overrides[require_authenticated_user_for_site] = lambda: None
    sales_permission = getattr(pdp_api.SALES_DATASET_PERMISSION, "dependency", None)
    if callable(sales_permission):
        app.dependency_overrides[sales_permission] = lambda: None


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _make_metrics_response(
    *,
    headers: list[str],
    rows: list[tuple[str, dict[str, str], float, float, float, float]],
) -> pdp_api.SalesMetricsResponse:
    sales_rows = [
        pdp_api.SalesMetricRow(
            month=month,
            dimensions=dimensions,
            sales=sales,
            units=units,
            sales_share=sales_share,
            units_share=units_share,
        )
        for month, dimensions, sales, units, sales_share, units_share in rows
    ]
    return pdp_api.SalesMetricsResponse(
        total_sales=sum(row.sales for row in sales_rows),
        total_units=sum(row.units for row in sales_rows),
        dimension_headers=headers,
        rows=sales_rows,
        months=sorted({row.month for row in sales_rows}),
    )


def _make_attribute_metadata() -> pdp_api.AttributeMetadataResponse:
    return pdp_api.AttributeMetadataResponse(
        placeholder_values=["unknown"],
        attributes=[
            pdp_api.AttributeOption(
                id="coverage",
                label="Coverage",
                column="coverage",
                values=["buildable", "light", "sheer", "medium"],
                active=True,
                coverage_pct=0.92,
                non_placeholder_records=92,
                total_records=100,
                distinct_non_placeholder_values=4,
            ),
            pdp_api.AttributeOption(
                id="form",
                label="Format",
                column="form",
                values=["cream", "powder", "liquid", "stick"],
                active=True,
                coverage_pct=0.89,
                non_placeholder_records=89,
                total_records=100,
                distinct_non_placeholder_values=4,
            ),
            pdp_api.AttributeOption(
                id="finish",
                label="Finish",
                column="finish",
                values=["natural", "satin", "dewy", "matte"],
                active=True,
                coverage_pct=0.87,
                non_placeholder_records=87,
                total_records=100,
                distinct_non_placeholder_values=4,
            ),
            pdp_api.AttributeOption(
                id="shade_family",
                label="Shade family",
                column="shade_family",
                values=["pink", "peach"],
                active=True,
                coverage_pct=0.41,
                non_placeholder_records=41,
                total_records=100,
                distinct_non_placeholder_values=2,
            ),
        ],
        price_band_values=["premium", "mid", "value"],
    )


def _make_sales_metrics_by_dimension() -> (
    dict[tuple[tuple[str, ...], int], pdp_api.SalesMetricsResponse]
):
    return {
        ((), 1): _make_metrics_response(
            headers=[],
            rows=[
                ("2024-01-01", {}, 8.0, 1.0, 1.0, 1.0),
                ("2024-02-01", {}, 9.5, 1.0, 1.0, 1.0),
                ("2024-03-01", {}, 11.0, 1.0, 1.0, 1.0),
                ("2024-04-01", {}, 18.5, 1.0, 1.0, 1.0),
                ("2024-05-01", {}, 10.5, 1.0, 1.0, 1.0),
                ("2024-06-01", {}, 12.0, 1.0, 1.0, 1.0),
            ],
        ),
        ((), 12): _make_metrics_response(
            headers=[],
            rows=[
                ("2024-01-01", {}, 100.0, 10.0, 1.0, 1.0),
                ("2024-02-01", {}, 101.0, 10.0, 1.0, 1.0),
                ("2024-03-01", {}, 102.0, 10.0, 1.0, 1.0),
                ("2024-04-01", {}, 103.0, 10.0, 1.0, 1.0),
                ("2024-05-01", {}, 104.0, 10.0, 1.0, 1.0),
                ("2024-06-01", {}, 105.0, 10.0, 1.0, 1.0),
                ("2024-07-01", {}, 106.0, 10.0, 1.0, 1.0),
                ("2024-08-01", {}, 107.0, 10.0, 1.0, 1.0),
                ("2024-09-01", {}, 108.0, 10.0, 1.0, 1.0),
                ("2024-10-01", {}, 109.0, 10.0, 1.0, 1.0),
                ("2024-11-01", {}, 110.0, 10.0, 1.0, 1.0),
                ("2024-12-01", {}, 117.4, 10.0, 1.0, 1.0),
                ("2025-09-01", {}, 209.9, 10.0, 1.0, 1.0),
            ],
        ),
        (("price_band",), 1): _make_metrics_response(
            headers=["Price bands"],
            rows=[
                ("2024-01-01", {"Price bands": "premium"}, 20.0, 2.0, 0.20, 0.20),
                ("2024-01-01", {"Price bands": "mid"}, 35.0, 3.5, 0.35, 0.35),
                ("2024-01-01", {"Price bands": "value"}, 45.0, 4.5, 0.45, 0.45),
                ("2025-01-01", {"Price bands": "premium"}, 28.0, 2.8, 0.28, 0.28),
                ("2025-01-01", {"Price bands": "mid"}, 36.0, 3.6, 0.36, 0.36),
                ("2025-01-01", {"Price bands": "value"}, 36.0, 3.6, 0.36, 0.36),
            ],
        ),
        (("brand",), 1): _make_metrics_response(
            headers=["Brands"],
            rows=[
                ("2024-01-01", {"Brands": "rare beauty"}, 40.0, 4.0, 0.40, 0.40),
                ("2024-01-01", {"Brands": "dibs beauty"}, 22.0, 2.2, 0.22, 0.22),
                ("2024-01-01", {"Brands": "other"}, 38.0, 3.8, 0.38, 0.38),
                ("2025-01-01", {"Brands": "rare beauty"}, 31.0, 3.1, 0.31, 0.31),
                ("2025-01-01", {"Brands": "dibs beauty"}, 29.0, 2.9, 0.29, 0.29),
                ("2025-01-01", {"Brands": "other"}, 40.0, 4.0, 0.40, 0.40),
            ],
        ),
        (("coverage",), 1): _make_metrics_response(
            headers=["Coverage"],
            rows=[
                ("2024-01-01", {"Coverage": "buildable"}, 40.0, 4.0, 0.40, 0.40),
                ("2024-01-01", {"Coverage": "light"}, 20.0, 2.0, 0.20, 0.20),
                ("2024-01-01", {"Coverage": "sheer"}, 10.0, 1.0, 0.10, 0.10),
                ("2024-01-01", {"Coverage": "medium"}, 30.0, 3.0, 0.30, 0.30),
                ("2025-01-01", {"Coverage": "buildable"}, 26.0, 2.6, 0.26, 0.26),
                ("2025-01-01", {"Coverage": "light"}, 31.0, 3.1, 0.31, 0.31),
                ("2025-01-01", {"Coverage": "sheer"}, 15.0, 1.5, 0.15, 0.15),
                ("2025-01-01", {"Coverage": "medium"}, 28.0, 2.8, 0.28, 0.28),
            ],
        ),
        (("form",), 1): _make_metrics_response(
            headers=["Format"],
            rows=[
                ("2024-01-01", {"Format": "cream"}, 40.0, 4.0, 0.40, 0.40),
                ("2024-01-01", {"Format": "powder"}, 38.0, 3.8, 0.38, 0.38),
                ("2024-01-01", {"Format": "liquid"}, 8.0, 0.8, 0.08, 0.08),
                ("2024-01-01", {"Format": "stick"}, 14.0, 1.4, 0.14, 0.14),
                ("2025-01-01", {"Format": "cream"}, 43.0, 4.3, 0.43, 0.43),
                ("2025-01-01", {"Format": "powder"}, 26.0, 2.6, 0.26, 0.26),
                ("2025-01-01", {"Format": "liquid"}, 18.0, 1.8, 0.18, 0.18),
                ("2025-01-01", {"Format": "stick"}, 13.0, 1.3, 0.13, 0.13),
            ],
        ),
        (("finish",), 1): _make_metrics_response(
            headers=["Finish"],
            rows=[
                ("2024-01-01", {"Finish": "natural"}, 45.0, 4.5, 0.45, 0.45),
                ("2024-01-01", {"Finish": "satin"}, 25.0, 2.5, 0.25, 0.25),
                ("2024-01-01", {"Finish": "dewy"}, 15.0, 1.5, 0.15, 0.15),
                ("2024-01-01", {"Finish": "matte"}, 15.0, 1.5, 0.15, 0.15),
                ("2025-01-01", {"Finish": "natural"}, 28.0, 2.8, 0.28, 0.28),
                ("2025-01-01", {"Finish": "satin"}, 31.0, 3.1, 0.31, 0.31),
                ("2025-01-01", {"Finish": "dewy"}, 24.0, 2.4, 0.24, 0.24),
                ("2025-01-01", {"Finish": "matte"}, 17.0, 1.7, 0.17, 0.17),
            ],
        ),
    }


def test_fetch_sales_brief_returns_structured_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_by_dimension = _make_sales_metrics_by_dimension()

    def fake_fetch_sales_metrics(**kwargs: object) -> pdp_api.SalesMetricsResponse:
        dimensions = tuple(str(value) for value in (kwargs["dimensions"] or []))
        window_months = int(kwargs["window_months"])
        return metrics_by_dimension[(dimensions, window_months)]

    monkeypatch.setattr(pdp_api, "fetch_sales_metrics", fake_fetch_sales_metrics)
    monkeypatch.setattr(
        pdp_api,
        "fetch_attribute_metadata",
        lambda **_kwargs: _make_attribute_metadata(),
    )

    _allow_sales_brief_calls()
    client = TestClient(app)
    response = client.get(
        "/review/sales/brief",
        params=[
            ("retailer", "ulta"),
            ("category", "blush"),
            ("dataset", "us_cosmetics"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Market scan: ulta / blush"
    assert payload["scope"] == "single_category"
    assert payload["analysis_scope"]["report_mode"] == "market_report"
    assert payload["analysis_scope"]["dataset"] == "us_cosmetics"
    assert payload["attribute_dimensions"] == ["coverage", "form", "finish"]
    assert len(payload["highlights"]) == 3
    assert all(
        "volatile" not in highlight.lower() for highlight in payload["highlights"]
    )
    assert payload["highlights"][0].startswith("The slice grew materially")
    assert {section["lens"] for section in payload["sections"]} >= {
        "growth_size",
        "price_value_capture",
        "brand_shifts",
        "attribute_mix",
    }
    assert "findings" not in payload
    first_section_finding = payload["sections"][0]["findings"][0]
    assert "volatile" not in first_section_finding["claim"].lower()
    assert first_section_finding["primary_evidence"] is not None
    assert first_section_finding["primary_evidence"]["chart_id"].startswith(
        "us-cosmetics_combo_total_abs_"
    )
    assert first_section_finding["primary_evidence"]["chart_request"] == {
        "retailer": ["ulta"],
        "category": ["blush"],
        "brand": [],
        "filters": [],
        "price_band": [],
        "pareto": [],
        "also_blush": [],
        "also_highlighter": [],
        "also_cheek": [],
        "also_eyeliner": [],
        "dimension": [],
        "chart_type": "stacked_column",
        "metric": "sales",
        "window_months": 1,
        "overlay_metric": "units",
        "dataset": "us_cosmetics",
    }
    assert "score_total" not in first_section_finding
    assert "supporting_evidence" not in first_section_finding
    assert first_section_finding["claim"].startswith("The slice grew materially")
    assert (
        first_section_finding["evidence_bullets"][0]
        == "sales moved from $117.4 to $209.9"
    )
    assert first_section_finding["metrics"][0]["display_value"] == "$117.4"


def test_fetch_sales_brief_rejects_multiple_categories() -> None:
    _allow_sales_brief_calls()
    client = TestClient(app)

    response = client.get(
        "/review/sales/brief",
        params=[
            ("retailer", "ulta"),
            ("category", "blush"),
            ("category", "bronzer"),
        ],
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Sales brief currently supports exactly one category."
    )


def test_fetch_sales_brief_prioritizes_focus_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_by_dimension = _make_sales_metrics_by_dimension()

    def fake_fetch_sales_metrics(**kwargs: object) -> pdp_api.SalesMetricsResponse:
        dimensions = tuple(str(value) for value in (kwargs["dimensions"] or []))
        window_months = int(kwargs["window_months"])
        return metrics_by_dimension[(dimensions, window_months)]

    monkeypatch.setattr(pdp_api, "fetch_sales_metrics", fake_fetch_sales_metrics)
    monkeypatch.setattr(
        pdp_api,
        "fetch_attribute_metadata",
        lambda **_kwargs: _make_attribute_metadata(),
    )

    _allow_sales_brief_calls()
    client = TestClient(app)
    response = client.get(
        "/review/sales/brief",
        params=[
            ("retailer", "ulta"),
            ("category", "blush"),
            ("focus_attribute", "Finish"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["attribute_dimensions"][:3] == ["finish", "coverage", "form"]
