from __future__ import annotations

import sys
import types
import plotly.graph_objects as go
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.auth.dependencies import require_authenticated_user

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


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pdp_api.router)
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None
    return app


def test_review_brief_chart_view_renders_lookup_form() -> None:
    client = TestClient(_build_app())
    resp = client.get("/review/brief/charts/view")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Review brief chart lookup" in resp.text


def test_review_brief_chart_view_returns_gone_after_sales_viewer_removal(
    monkeypatch,
) -> None:
    chart_data = {
        "chart_id": "us-cosmetics_slope_facets_form_blush_abc123",
        "chart_type": "slope_share_facets",
        "category_key": "blush",
        "retailers": ["amazon", "sephora"],
        "dimensions": [{"id": "brand"}, {"id": "form"}],
        "facet": {"id": "retailer"},
    }
    meta = {
        "source": "job",
        "job_scope": {
            "dataset": "us_cosmetics",
            "category": "blush",
            "brands": ["tarte"],
            "pareto": ["A"],
            "price_bands": ["premium"],
            "attribute_filters": ["finish:matte|satin"],
        },
    }

    monkeypatch.setattr(
        pdp_api,
        "_load_review_brief_job_chart",
        lambda _job_id, _chart_id: (chart_data, meta),
    )

    client = TestClient(_build_app())
    resp = client.get(
        "/review/brief/charts/view",
        params={"job": "job123", "chart": chart_data["chart_id"]},
        follow_redirects=False,
    )

    assert resp.status_code == 410
    assert "Sales chart viewer has been removed" in resp.text


def test_review_brief_chart_resolve_returns_sales_state(monkeypatch) -> None:
    chart_data = {
        "chart_id": "us-cosmetics_stacked_column_finish_blush_abc123",
        "chart_type": "stacked_column",
        "category_key": "blush",
        "retailers": ["ulta"],
        "dimensions": [{"id": "brand"}, {"id": "finish"}],
        "month": "2026-01-01",
    }
    meta = {
        "source": "job",
        "job_scope": {"dataset": "us_cosmetics", "brands": ["byoma"]},
    }
    monkeypatch.setattr(
        pdp_api,
        "_load_review_brief_job_chart",
        lambda _job_id, _chart_id: (chart_data, meta),
    )

    client = TestClient(_build_app())
    resp = client.get(
        "/review/brief/charts/resolve",
        params={"job": "job123", "chart": chart_data["chart_id"]},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["chart_id"] == chart_data["chart_id"]
    assert payload["job_id"] == "job123"
    assert payload["dataset"] == "us_cosmetics"
    assert payload["retailers"] == ["ulta"]
    assert payload["categories"] == ["blush"]
    assert payload["brands"] == ["byoma"]
    assert payload["dimensions"] == ["brand", "finish"]
    assert payload["period_mode"] == "single_month"
    assert payload["month"] == ""


def test_review_brief_chart_png_returns_image(monkeypatch) -> None:
    chart_data = {
        "chart_id": "us-cosmetics_slope_finish_blush_abc123",
        "chart_type": "slope_share",
        "rows": [
            {
                "brand": "A",
                "attribute": "Matte",
                "start_share_pct": 10.0,
                "end_share_pct": 15.0,
            }
        ],
    }
    monkeypatch.setattr(
        pdp_api,
        "_load_review_brief_job_chart",
        lambda _job_id, _chart_id: (chart_data, {"source": "job"}),
    )
    monkeypatch.setattr(
        pdp_api,
        "_review_brief_chart_figures",
        lambda _chart: [("Facet A", go.Figure())],
    )
    monkeypatch.setattr(pdp_api.pio, "to_image", lambda _fig, **_kwargs: b"png-bytes")

    client = TestClient(_build_app())
    resp = client.get(
        "/review/brief/charts/png",
        params={"job": "job123", "chart": chart_data["chart_id"], "facet": "facet a"},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == b"png-bytes"


def test_review_brief_chart_png_handles_renderer_failure(monkeypatch) -> None:
    chart_data = {
        "chart_id": "us-cosmetics_slope_finish_blush_def456",
        "chart_type": "slope_share",
        "rows": [
            {
                "brand": "A",
                "attribute": "Matte",
                "start_share_pct": 10.0,
                "end_share_pct": 15.0,
            }
        ],
    }
    monkeypatch.setattr(
        pdp_api,
        "_load_review_brief_job_chart",
        lambda _job_id, _chart_id: (chart_data, {"source": "job"}),
    )
    monkeypatch.setattr(
        pdp_api,
        "_review_brief_chart_figures",
        lambda _chart: [(None, go.Figure())],
    )

    def _raise_to_image(_fig, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(pdp_api.pio, "to_image", _raise_to_image)

    client = TestClient(_build_app())
    resp = client.get(
        "/review/brief/charts/png",
        params={"job": "job123", "chart": chart_data["chart_id"]},
    )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "PNG rendering is unavailable."
