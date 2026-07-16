from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
import time
import types
import zipfile
from pathlib import Path

import plotly.graph_objects as go
import pytest

pytest.importorskip("fastapi")

from fastapi import Request
from fastapi.testclient import (
    TestClient,  # type: ignore  # pylint: disable=wrong-import-position
)

from modules.auth.dependencies import require_authenticated_user
from modules.slides import api as slides_api
from src.review_brief.pptx_template import REVIEW_BRIEF_PPTX_SPEC_FILENAME
from src.slides.storage import DeckStorage

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

app = pdp_api.app


def _install_fake_review_brief_llm(monkeypatch) -> None:
    import src.review_brief.generator as brief_generator

    naming = brief_generator.get_naming_params()
    interpretation_step = naming["reviewBriefChartInterpretationQuery"]
    narrative_step = naming["reviewBriefNarrativeQuery"]

    def fake_run_step_json(_llm_wrapper, step, _system_prompt, prompts, **_kwargs):
        prompt_items = [prompts] if isinstance(prompts, str) else list(prompts)
        if step == narrative_step:
            chart_ids: list[str] = []
            try:
                first_prompt = prompt_items[0] if prompt_items else "{}"
                data = json.loads(first_prompt)
                charts = data.get("charts") if isinstance(data, dict) else None
                if isinstance(charts, list):
                    for item in charts[:2]:
                        chart = item.get("chart") if isinstance(item, dict) else None
                        chart_id = (
                            str(chart.get("chart_id") or "")
                            if isinstance(chart, dict)
                            else ""
                        )
                        if chart_id:
                            chart_ids.append(chart_id)
            except (TypeError, ValueError):
                chart_ids = []
            return [
                {
                    "executive_narrative": "Test narrative.",
                    "key_takeaways": ["Takeaway 1", "Takeaway 2"],
                    "suggested_flow": [
                        {
                            "title": "Slide 1",
                            "chart_ids": chart_ids,
                        }
                    ],
                }
            ]
        assert step == interpretation_step
        outputs = []
        for prompt in prompt_items:
            chart_id = ""
            try:
                data = json.loads(prompt)
                chart = data.get("chart") if isinstance(data, dict) else None
                if isinstance(chart, dict):
                    chart_id = str(chart.get("chart_id") or "")
            except (TypeError, ValueError):
                chart_id = ""
            outputs.append(
                {
                    "chart_id": chart_id,
                    "headline": "Test headline",
                    "bullets": ["Test bullet 1", "Test bullet 2"],
                    "relevance": 80,
                }
            )
        return outputs

    monkeypatch.setattr(brief_generator, "run_step_json", fake_run_step_json)


def _fake_build_review_brief_pdf(
    markdown: str, *, charts_json_path: str, output_pdf_path: Path
) -> Path:
    del markdown, charts_json_path
    output_pdf_path.write_bytes(b"%PDF-1.7\nbrief\n")
    return output_pdf_path


def test_review_brief_job_creation_is_disabled() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None
    client = TestClient(app)
    response = client.post(
        "/review/brief/jobs",
        json={
            "retailers": ["ulta", "sephora"],
            "category": "bronzer",
            "prompt_style": "uniform",
        },
    )
    assert response.status_code == 410
    assert (
        "disabled pending redesign" in str(response.json().get("detail") or "").lower()
    )
    app.dependency_overrides.clear()


def test_review_brief_sync_generation_is_disabled() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None

    client = TestClient(app)
    response = client.post(
        "/review/brief/generate",
        json={
            "retailers": ["ulta", "sephora"],
            "category": "bronzer",
            "prompt_style": "uniform",
        },
    )

    assert response.status_code == 410
    assert (
        "disabled pending redesign" in str(response.json().get("detail") or "").lower()
    )
    app.dependency_overrides.clear()


def test_review_brief_legacy_chart_view_route_has_been_removed() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None

    client = TestClient(app)
    response = client.get(
        "/review/sales/brief/charts/view",
        params={"job": "job123", "chart": "chart456"},
        follow_redirects=False,
    )
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_download_review_brief_job_pptx_redirects_when_not_authenticated() -> None:
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    assert callable(brief_permission)

    def fake_redirect(request: Request):
        del request
        raise pdp_api.HTTPException(
            status_code=307,
            detail="Authentication required.",
            headers={"Location": "/"},
        )

    app.dependency_overrides[brief_permission] = fake_redirect

    client = TestClient(app)
    response = client.get(
        "/review/brief/jobs/job123/pptx",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers.get("location") == "/"
    app.dependency_overrides.clear()


def test_review_brief_job_enqueue_returns_gone_without_starting_worker(
    monkeypatch,
) -> None:
    started = {"called": False}

    def fake_start_worker(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        del args, kwargs
        started["called"] = True

    monkeypatch.setattr(
        pdp_api._REVIEW_BRIEF_JOB_STORE, "start_worker", fake_start_worker
    )
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None

    client = TestClient(app)
    response = client.post(
        "/review/brief/jobs",
        json={
            "retailers": ["ulta"],
            "category": "blush",
            "prompt_style": "uniform",
        },
        headers={"origin": "https://mparanza.com"},
    )
    assert response.status_code == 410
    assert started["called"] is False
    app.dependency_overrides.clear()


def test_build_review_brief_job_deck_is_disabled() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None

    client = TestClient(app)
    response = client.post("/review/brief/jobs/jobDeck/deck")

    assert response.status_code == 410
    assert (
        "disabled pending redesign" in str(response.json().get("detail") or "").lower()
    )
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("payload", "expected_detail"),
    [
        (
            {"retailers": ["ulta"], "category": "blush"},
            "disabled pending redesign",
        ),
        (
            {"retailers": ["ulta"], "category": "blush", "prompt_style": "unknown"},
            "disabled pending redesign",
        ),
    ],
)
def test_review_brief_job_rejects_invalid_prompt_style(
    payload: dict[str, object], expected_detail: str
) -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None

    client = TestClient(app)
    response = client.post("/review/brief/jobs", json=payload)
    assert response.status_code == 410
    assert expected_detail in str(response.json().get("detail") or "")
    app.dependency_overrides.clear()


def test_review_brief_store_marks_orphan_running_job_failed(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "review_brief_jobs.json"
    store = pdp_api.ReviewBriefJobStore(db_path=db_path)
    job_id = store.create_job(
        {"retailers": ["ulta"], "category": "blush"}, start_worker=False
    )

    with store._connect() as conn:
        conn.execute(
            """
            UPDATE review_brief_jobs
            SET status = ?, runner_pid = ?, updated_at = ?
            WHERE job_id = ?
            """,
            ("running", 424242, time.time(), job_id),
        )

    monkeypatch.setattr(
        pdp_api.ReviewBriefJobStore,
        "_is_pid_alive",
        staticmethod(lambda _pid: False),
    )

    job = store.get_job(job_id)
    assert job is not None
    assert job["status"] == "failed"
    assert "interrupted" in str(job.get("error") or "").lower()


def test_inline_review_brief_chart_previews_embeds_data_uri(
    tmp_path: Path, monkeypatch
) -> None:
    charts_payload = {
        "charts": [
            {
                "chart_id": "chart_demo_123",
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
        ]
    }
    json_path = tmp_path / "brief.json"
    json_path.write_text(json.dumps(charts_payload), encoding="utf-8")
    markdown = (
        "![Chart preview: demo]"
        "(https://mparanza.com/review/brief/charts/png?chart=chart_demo_123)\n"
    )

    monkeypatch.setattr(
        pdp_api,
        "_review_brief_chart_figures",
        lambda _chart: [(None, go.Figure())],
    )
    monkeypatch.setattr(pdp_api.pio, "to_image", lambda _fig, **_kwargs: b"png-bytes")

    rendered = pdp_api._inline_review_brief_chart_previews(
        markdown,
        charts_json_path=str(json_path),
    )

    assert "data:image/png;base64," in rendered
    assert "review/brief/charts/png?chart=chart_demo_123" not in rendered


def test_inline_review_brief_chart_previews_preserves_url_on_render_failure(
    tmp_path: Path, monkeypatch
) -> None:
    charts_payload = {
        "charts": [
            {
                "chart_id": "chart_demo_456",
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
        ]
    }
    json_path = tmp_path / "brief.json"
    json_path.write_text(json.dumps(charts_payload), encoding="utf-8")
    markdown = (
        "![Chart preview: demo]"
        "(https://mparanza.com/review/brief/charts/png?chart=chart_demo_456)\n"
    )

    monkeypatch.setattr(
        pdp_api,
        "_review_brief_chart_figures",
        lambda _chart: [(None, go.Figure())],
    )

    def _raise_to_image(_fig, **_kwargs):  # type: ignore[no-untyped-def]
        raise ValueError("renderer unavailable")

    monkeypatch.setattr(pdp_api.pio, "to_image", _raise_to_image)

    rendered = pdp_api._inline_review_brief_chart_previews(
        markdown,
        charts_json_path=str(json_path),
    )

    assert rendered == markdown


def test_render_review_brief_chart_png_bytes_uses_external_python_fallback(
    monkeypatch,
) -> None:
    chart_data = {
        "chart_id": "chart_demo_fallback_001",
        "chart_type": "slope_share",
        "rows": [
            {
                "brand": "A",
                "attribute": "matte",
                "start_share_pct": 10.0,
                "end_share_pct": 11.0,
            }
        ],
    }
    monkeypatch.setattr(
        pdp_api,
        "_review_brief_chart_figures",
        lambda _chart: [(None, go.Figure())],
    )
    to_image_paths: list[str] = []

    def _raise_to_image(_fig, **_kwargs):  # type: ignore[no-untyped-def]
        to_image_paths.append(str(os.environ.get("PATH") or ""))
        raise RuntimeError("kaleido unavailable")

    monkeypatch.setattr(pdp_api.pio, "to_image", _raise_to_image)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(
        pdp_api,
        "_render_plotly_png_with_external_python",
        lambda _fig, *, width, height, scale: b"png-bytes-fallback",
    )

    rendered = pdp_api._render_review_brief_chart_png_bytes(chart_data)
    assert rendered == b"png-bytes-fallback"
    assert to_image_paths
    assert "/usr/bin" in to_image_paths[0].split(os.pathsep)
    assert "/bin" in to_image_paths[0].split(os.pathsep)


def test_render_review_brief_chart_png_bytes_does_not_apply_corner_stamp(
    monkeypatch,
) -> None:
    chart_data = {
        "chart_id": "chart_demo_plain_001",
        "chart_type": "stacked",
        "rows": [
            {"month": "2024-01-01", "segment": "matte", "share_pct": 60.0},
            {"month": "2024-01-01", "segment": "dewy", "share_pct": 40.0},
        ],
    }
    monkeypatch.setattr(
        pdp_api,
        "_review_brief_chart_figures",
        lambda _chart: [(None, go.Figure())],
    )
    captured: dict[str, object] = {}

    def _fake_to_image(fig, **_kwargs):  # type: ignore[no-untyped-def]
        captured["kwargs"] = dict(_kwargs)
        captured["annotations"] = list(fig.layout.annotations or [])
        captured["images"] = list(fig.layout.images or [])
        return b"\x89PNG\r\n\x1a\nplain"

    monkeypatch.setattr(pdp_api.pio, "to_image", _fake_to_image)

    rendered = pdp_api._render_review_brief_chart_png_bytes(chart_data)

    assert rendered == b"\x89PNG\r\n\x1a\nplain"
    annotations = captured.get("annotations")
    assert isinstance(annotations, list)
    assert annotations == []
    images = captured.get("images")
    assert isinstance(images, list)
    assert images == []
    kwargs = captured.get("kwargs")
    assert isinstance(kwargs, dict)
    width, height, scale = pdp_api._review_brief_png_export_options()
    assert kwargs.get("width") == width
    assert kwargs.get("height") == height
    assert kwargs.get("scale") == scale


def test_render_review_brief_chart_png_uses_high_resolution_export_options(
    monkeypatch,
) -> None:
    chart_data = {
        "chart_id": "chart_demo_png_route_001",
        "chart_type": "stacked",
        "rows": [
            {"month": "2024-01-01", "segment": "matte", "share_pct": 60.0},
            {"month": "2024-01-01", "segment": "dewy", "share_pct": 40.0},
        ],
    }
    monkeypatch.setattr(
        pdp_api,
        "_find_review_brief_chart_in_reports",
        lambda _chart_id: (chart_data, {"source": "test"}),
    )
    monkeypatch.setattr(
        pdp_api,
        "_review_brief_chart_figures",
        lambda _chart: [(None, go.Figure())],
    )
    monkeypatch.setattr(pdp_api, "_ensure_review_brief_kaleido_path", lambda: "")
    captured: dict[str, object] = {}

    def _fake_to_image(_fig, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return b"\x89PNG\r\n\x1a\nroute"

    monkeypatch.setattr(pdp_api.pio, "to_image", _fake_to_image)

    response = pdp_api.render_review_brief_chart_png(
        chart="chart_demo_png_route_001",
        job=None,
        facet=None,
    )

    assert response.body == b"\x89PNG\r\n\x1a\nroute"
    width, height, scale = pdp_api._review_brief_png_export_options()
    assert captured.get("width") == width
    assert captured.get("height") == height
    assert captured.get("scale") == scale


def test_render_plotly_png_with_external_python_prefers_current_interpreter(
    monkeypatch,
) -> None:
    calls: list[str] = []
    run_env_paths: list[str] = []
    monkeypatch.setattr(pdp_api, "_REVIEW_BRIEF_PNG_RENDER_FAILED_PYTHONS", set())

    class _Proc:
        returncode = 0
        stdout = b"\x89PNG\r\n\x1a\nfake"
        stderr = b""

    def _fake_run(cmd, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(str(cmd[0]))
        env = _kwargs.get("env")
        run_env_paths.append(str((env or {}).get("PATH") or ""))
        return _Proc()

    monkeypatch.setattr(pdp_api.subprocess, "run", _fake_run)
    monkeypatch.setenv("PATH", "")

    rendered = pdp_api._render_plotly_png_with_external_python(
        go.Figure(),
        width=100,
        height=60,
        scale=1,
    )

    assert rendered == b"\x89PNG\r\n\x1a\nfake"
    assert calls == [sys.executable]
    assert run_env_paths
    path_parts = run_env_paths[0].split(os.pathsep)
    assert "/usr/bin" in path_parts
    assert "/bin" in path_parts


def test_review_brief_chart_figures_stacked_share_renderer_removed() -> None:
    figures = pdp_api._review_brief_chart_figures(
        {
            "chart_type": "stacked",
            "title": "finish share over time",
            "rows": [
                {"month": "2022-01-01", "segment": "cream", "share_pct": 52.9},
                {"month": "2022-01-01", "segment": "liquid", "share_pct": 9.0},
                {"month": "2022-01-01", "segment": "pressed powder", "share_pct": 25.9},
                {"month": "2022-01-01", "segment": "other", "share_pct": 12.2},
                {"month": "2025-09-01", "segment": "cream", "share_pct": 43.6},
                {"month": "2025-09-01", "segment": "liquid", "share_pct": 20.0},
                {"month": "2025-09-01", "segment": "pressed powder", "share_pct": 31.0},
                {"month": "2025-09-01", "segment": "other", "share_pct": 5.4},
            ],
        }
    )

    assert figures == []


def test_review_brief_chart_figures_stacked_share_facets_renderer_removed() -> None:
    figures = pdp_api._review_brief_chart_figures(
        {
            "chart_type": "stacked_share_facets",
            "title": "coverage share over time (faceted by Source)",
            "rows": [
                {
                    "facet": "ulta",
                    "month": "2022-01-01",
                    "segment": "buildable",
                    "share_pct": 40.0,
                },
                {
                    "facet": "ulta",
                    "month": "2022-01-01",
                    "segment": "medium",
                    "share_pct": 60.0,
                },
                {
                    "facet": "ulta",
                    "month": "2025-09-01",
                    "segment": "buildable",
                    "share_pct": 55.0,
                },
                {
                    "facet": "ulta",
                    "month": "2025-09-01",
                    "segment": "medium",
                    "share_pct": 45.0,
                },
                {
                    "facet": "sephora",
                    "month": "2022-01-01",
                    "segment": "buildable",
                    "share_pct": 25.0,
                },
                {
                    "facet": "sephora",
                    "month": "2022-01-01",
                    "segment": "medium",
                    "share_pct": 75.0,
                },
                {
                    "facet": "sephora",
                    "month": "2025-09-01",
                    "segment": "buildable",
                    "share_pct": 64.0,
                },
                {
                    "facet": "sephora",
                    "month": "2025-09-01",
                    "segment": "medium",
                    "share_pct": 36.0,
                },
            ],
        }
    )

    assert figures == []


def test_review_brief_chart_figures_ignores_removed_stacked_renderer() -> None:
    figures = pdp_api._review_brief_chart_figures(
        {
            "chart_type": "stacked",
            "title": "finish share over time",
            "prompt_style": "editorial",
            "rows": [
                {"month": "2022-01-01", "segment": "cream", "share_pct": 52.9},
                {"month": "2025-09-01", "segment": "cream", "share_pct": 43.6},
            ],
        }
    )

    assert figures == []


def test_review_brief_chart_figures_stacked_column_renderer_removed() -> None:
    figures = pdp_api._review_brief_chart_figures(
        {
            "chart_type": "stacked_column_absolute",
            "title": "Price band monthly stacked values",
            "rows": [
                {"month": "2022-01-01", "segment": "mid", "sales": 9.7},
                {"month": "2022-01-01", "segment": "value", "sales": 4.0},
                {"month": "2022-01-01", "segment": "premium", "sales": 2.7},
                {"month": "2025-09-01", "segment": "mid", "sales": 32.5},
                {"month": "2025-09-01", "segment": "value", "sales": 8.0},
                {"month": "2025-09-01", "segment": "premium", "sales": 6.9},
            ],
        }
    )

    assert figures == []


def test_review_brief_chart_window_months_non_rolling_defaults_to_one() -> None:
    assert (
        pdp_api._review_brief_chart_window_months(
            {},
            chart_type="combo_total_abs",
        )
        == 1
    )
    assert (
        pdp_api._review_brief_chart_window_months(
            {"window": {"mode": "monthly", "months": 12}},
            chart_type="stacked_abs",
        )
        == 1
    )
    assert (
        pdp_api._review_brief_chart_window_months(
            {"window": {"mode": "rolling", "months": 6}},
            chart_type="stacked",
        )
        == 6
    )


def test_review_brief_chart_figures_combo_renderer_removed(
    monkeypatch,
) -> None:
    del monkeypatch
    rows = [
        {"month": "2024-01-01", "sales": 16.4, "units": 1.0},
        {"month": "2024-02-01", "sales": 16.4, "units": 0.9},
        {"month": "2024-03-01", "sales": 20.1, "units": 1.0},
    ]
    figures = pdp_api._review_brief_chart_figures(
        {
            "chart_id": "chart_combo_demo",
            "chart_type": "combo_total_abs",
            "category_key": "blush",
            "retailers": ["sephora", "ulta"],
            "rows": rows,
            "payload": {
                "rows": rows,
                "bar_metric": "sales",
                "line_metric": "units",
            },
            "start_month": "2024-01-01",
            "end_month": "2024-03-01",
        }
    )

    assert figures == []


def test_review_brief_chart_figures_stacked_share_canonical_renderer_removed(
    monkeypatch,
) -> None:
    del monkeypatch
    rows = [
        {"month": "2024-01-01", "segment": "cream", "share_pct": 60.0},
        {"month": "2024-01-01", "segment": "powder", "share_pct": 40.0},
        {"month": "2025-01-01", "segment": "cream", "share_pct": 55.0},
        {"month": "2025-01-01", "segment": "powder", "share_pct": 45.0},
    ]
    figures = pdp_api._review_brief_chart_figures(
        {
            "chart_id": "us-cosmetics_stacked_coverage_blush_demo",
            "chart_type": "stacked",
            "category_key": "blush",
            "retailers": ["ulta", "sephora"],
            "dimensions": [{"id": "coverage", "label": "coverage"}],
            "rows": rows,
            "payload": {
                "rows": rows,
                "segment_label": "coverage",
            },
            "start_month": "2024-01-01",
            "end_month": "2025-01-01",
        }
    )

    assert figures == []


def test_review_brief_chart_figures_slope_uses_inline_labels(monkeypatch) -> None:
    del monkeypatch
    figures = pdp_api._review_brief_chart_figures(
        {
            "chart_type": "slope_share",
            "title": "Brand × form (start → end)",
            "rows": [
                {
                    "brand": None,
                    "attribute": None,
                    "brand_right": "too faced",
                    "finish_right": "satin",
                    "start_share_pct": 0.0,
                    "end_share_pct": 8.4,
                },
                {
                    "brand": "rare beauty",
                    "attribute": "natural",
                    "start_share_pct": 30.6,
                    "end_share_pct": 6.9,
                },
            ],
        }
    )

    assert len(figures) == 1
    figure = figures[0][1]
    names = [str(getattr(trace, "name", "")) for trace in list(figure.data)]
    assert "too faced · satin" in names
    assert "rare beauty · natural" in names
    assert "Series" not in " ".join(names)
    assert figure.layout.showlegend is False
    annotations = list(figure.layout.annotations or [])
    assert annotations
    assert any(
        "too faced" in str(getattr(ann, "text", "")).lower() for ann in annotations
    )


def test_review_brief_chart_figures_slope_share_facets_combines_small_multiples() -> (
    None
):
    figures = pdp_api._review_brief_chart_figures(
        {
            "chart_type": "slope_share_facets",
            "title": "Brand x form (faceted by Source)",
            "rows": [
                {
                    "facet": "sephora",
                    "brand": "rare beauty",
                    "attribute": "liquid",
                    "start_share_pct": 49.3,
                    "end_share_pct": 8.6,
                },
                {
                    "facet": "sephora",
                    "brand": "rhode",
                    "attribute": "cream",
                    "start_share_pct": 1.2,
                    "end_share_pct": 37.2,
                },
                {
                    "facet": "ulta",
                    "brand": "rare beauty",
                    "attribute": "liquid",
                    "start_share_pct": 10.5,
                    "end_share_pct": 4.3,
                },
                {
                    "facet": "ulta",
                    "brand": "rhode",
                    "attribute": "cream",
                    "start_share_pct": 0.5,
                    "end_share_pct": 8.5,
                },
            ],
        }
    )

    assert len(figures) == 3
    assert figures[0][0] is None
    combined = figures[0][1]
    assert len(list(combined.data)) >= 4
    subplot_titles = {
        str(getattr(annotation, "text", "")).strip().lower()
        for annotation in list(combined.layout.annotations or [])
    }
    assert "sephora" in subplot_titles
    assert "ulta" in subplot_titles
    assert {str(item[0]) for item in figures[1:]} == {"sephora", "ulta"}


def test_build_review_brief_pdf_embeds_chart_from_comment_marker(
    tmp_path: Path, monkeypatch
) -> None:
    chart_id = "chart_demo_999"
    charts_payload = {
        "charts": [
            {
                "chart_id": chart_id,
                "chart_type": "slope_share",
                "rows": [{"segment": "A", "share_pct": 10.0}],
            }
        ]
    }
    charts_json_path = tmp_path / "brief.json"
    charts_json_path.write_text(json.dumps(charts_payload), encoding="utf-8")
    markdown = "\n".join(
        [
            "# NotebookLM Brief — Demo",
            "",
            "### Demo section",
            f"**Instance ID**: `{chart_id}`",
            f"<!-- chart_id: {chart_id} -->",
            "",
        ]
    )
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2pM5sAAAAASUVORK5CYII="
    )
    calls: list[tuple[str, str | None]] = []

    def _fake_png_bytes(chart_data, *, facet=None):  # type: ignore[no-untyped-def]
        calls.append((str(chart_data.get("chart_id") or ""), facet))
        return png_bytes

    monkeypatch.setattr(
        pdp_api, "_render_review_brief_chart_png_bytes", _fake_png_bytes
    )

    output_pdf_path = tmp_path / "brief.pdf"
    built_path = pdp_api._build_review_brief_pdf(
        markdown,
        charts_json_path=str(charts_json_path),
        output_pdf_path=output_pdf_path,
    )

    assert built_path == output_pdf_path
    assert output_pdf_path.exists()
    assert output_pdf_path.stat().st_size > 0
    assert calls == [(chart_id, None)]


def test_build_review_brief_pdf_embeds_chart_from_instance_id_line(
    tmp_path: Path, monkeypatch
) -> None:
    chart_id = "chart_demo_instance_001"
    charts_payload = {
        "charts": [
            {
                "chart_id": chart_id,
                "chart_type": "slope_share",
                "rows": [{"segment": "A", "share_pct": 10.0}],
            }
        ]
    }
    charts_json_path = tmp_path / "brief.json"
    charts_json_path.write_text(json.dumps(charts_payload), encoding="utf-8")
    markdown = "\n".join(
        [
            "# NotebookLM Brief - Demo",
            "",
            f"**Instance ID**: `{chart_id}`",
            "",
        ]
    )
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2pM5sAAAAASUVORK5CYII="
    )
    calls: list[tuple[str, str | None]] = []

    def _fake_png_bytes(chart_data, *, facet=None):  # type: ignore[no-untyped-def]
        calls.append((str(chart_data.get("chart_id") or ""), facet))
        return png_bytes

    monkeypatch.setattr(
        pdp_api, "_render_review_brief_chart_png_bytes", _fake_png_bytes
    )

    output_pdf_path = tmp_path / "brief.pdf"
    built_path = pdp_api._build_review_brief_pdf(
        markdown,
        charts_json_path=str(charts_json_path),
        output_pdf_path=output_pdf_path,
    )

    assert built_path == output_pdf_path
    assert output_pdf_path.exists()
    assert output_pdf_path.stat().st_size > 0
    assert calls == [(chart_id, None)]


def test_build_review_brief_pdf_raises_when_chart_preview_missing(
    tmp_path: Path, monkeypatch
) -> None:
    chart_id = "chart_demo_missing_png"
    charts_payload = {
        "charts": [
            {
                "chart_id": chart_id,
                "chart_type": "slope_share",
                "rows": [{"segment": "A", "share_pct": 10.0}],
            }
        ]
    }
    charts_json_path = tmp_path / "brief.json"
    charts_json_path.write_text(json.dumps(charts_payload), encoding="utf-8")
    markdown = "\n".join(
        [
            "# NotebookLM Brief - Demo",
            "",
            f"<!-- chart_id: {chart_id} -->",
            "",
            "Body text",
        ]
    )

    monkeypatch.setattr(
        pdp_api,
        "_render_review_brief_chart_png_bytes",
        lambda _chart, *, facet=None: None,
    )

    output_pdf_path = tmp_path / "brief.pdf"
    with pytest.raises(RuntimeError, match="Missing rendered chart previews"):
        pdp_api._build_review_brief_pdf(
            markdown,
            charts_json_path=str(charts_json_path),
            output_pdf_path=output_pdf_path,
        )


def test_build_review_brief_pdf_raises_when_chart_markers_missing(
    tmp_path: Path,
) -> None:
    charts_payload = {
        "charts": [
            {
                "chart_id": "chart_demo_000",
                "chart_type": "slope_share",
                "rows": [{"segment": "A", "share_pct": 10.0}],
            }
        ]
    }
    charts_json_path = tmp_path / "brief.json"
    charts_json_path.write_text(json.dumps(charts_payload), encoding="utf-8")
    markdown = "# NotebookLM Brief - Demo\n\nBody without chart markers\n"

    with pytest.raises(RuntimeError, match="No chart markers found"):
        pdp_api._build_review_brief_pdf(
            markdown,
            charts_json_path=str(charts_json_path),
            output_pdf_path=tmp_path / "brief.pdf",
        )


def test_build_review_brief_chart_png_bundle_writes_chart_map_and_pngs(
    tmp_path: Path, monkeypatch
) -> None:
    chart_a = "chart_demo_a"
    chart_b = "chart_demo_b"
    charts_payload = {
        "charts": [
            {"chart_id": chart_a, "chart_type": "stacked", "rows": []},
            {"chart_id": chart_b, "chart_type": "stacked", "rows": []},
        ]
    }
    charts_json_path = tmp_path / "brief.json"
    charts_json_path.write_text(json.dumps(charts_payload), encoding="utf-8")
    markdown = "\n".join(
        [
            "# NotebookLM Brief — Demo",
            f"<!-- chart_id: {chart_b} -->",
            f"<!-- chart_id: {chart_a} -->",
            "",
        ]
    )
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2pM5sAAAAASUVORK5CYII="
    )
    calls: list[tuple[str, str | None]] = []

    def _fake_review_figures(
        chart_data: dict[str, object],
    ) -> list[tuple[str | None, go.Figure]]:
        chart_id = str(chart_data.get("chart_id") or "").strip()
        fig = go.Figure()
        fig.update_layout(
            title={
                "text": (
                    f"<span>{chart_id} line 1</span><br>"
                    f"<span>{chart_id} line 2</span><br>"
                    f"<span>{chart_id} line 3</span>"
                )
            }
        )
        return [(None, fig)]

    def _fake_render_png_bytes(
        chart_data: dict[str, object], *, facet: str | None = None
    ) -> bytes:
        calls.append((str(chart_data.get("chart_id") or ""), facet))
        return png_bytes

    monkeypatch.setattr(pdp_api, "_review_brief_chart_figures", _fake_review_figures)
    monkeypatch.setattr(
        pdp_api, "_render_review_brief_chart_png_bytes", _fake_render_png_bytes
    )

    output_zip_path = tmp_path / "brief-charts.zip"
    built_zip = pdp_api._build_review_brief_chart_png_bundle(
        markdown,
        charts_json_path=str(charts_json_path),
        output_zip_path=output_zip_path,
    )

    assert built_zip == output_zip_path
    assert output_zip_path.exists()
    with zipfile.ZipFile(output_zip_path, "r") as archive:
        names = archive.namelist()
        png_names = [name for name in names if name.endswith(".png")]
        assert len(png_names) == 2
        assert set(png_names) == {f"{chart_a}.png", f"{chart_b}.png"}
        assert "chart-map.md" in names
        assert "chart-serials.json" in names
        chart_map = archive.read("chart-map.md").decode("utf-8")
        assert "- Chart count: 2" in chart_map
        assert f"| {chart_b} | - | {chart_b}.png |" in chart_map
        assert f"| {chart_a} | - | {chart_a}.png |" in chart_map
        chart_serials = json.loads(archive.read("chart-serials.json").decode("utf-8"))
        assert chart_serials["chart_count"] == 2
        items_by_filename = {
            str(item.get("filename") or ""): item
            for item in chart_serials.get("items", [])
        }
        assert items_by_filename[f"{chart_b}.png"]["chart_id"] == chart_b
        assert items_by_filename[f"{chart_b}.png"]["facet"] is None
        assert (
            items_by_filename[f"{chart_b}.png"]["title_line_1"] == f"{chart_b} line 1"
        )
        assert (
            items_by_filename[f"{chart_b}.png"]["title_line_2"] == f"{chart_b} line 2"
        )
        assert (
            items_by_filename[f"{chart_b}.png"]["title_line_3"] == f"{chart_b} line 3"
        )
        assert items_by_filename[f"{chart_a}.png"]["chart_id"] == chart_a
        assert items_by_filename[f"{chart_a}.png"]["facet"] is None
        assert (
            items_by_filename[f"{chart_a}.png"]["title_line_1"] == f"{chart_a} line 1"
        )
        assert (
            items_by_filename[f"{chart_a}.png"]["title_line_2"] == f"{chart_a} line 2"
        )
        assert (
            items_by_filename[f"{chart_a}.png"]["title_line_3"] == f"{chart_a} line 3"
        )
    assert calls == [(chart_b, None), (chart_a, None)]


def test_build_review_brief_chart_png_bundle_uses_facet_suffix_from_markdown_links(
    tmp_path: Path, monkeypatch
) -> None:
    chart_id = "chart_demo_faceted"
    charts_payload = {
        "charts": [
            {"chart_id": chart_id, "chart_type": "stacked_share_facets", "rows": []},
        ]
    }
    charts_json_path = tmp_path / "brief.json"
    charts_json_path.write_text(json.dumps(charts_payload), encoding="utf-8")
    markdown = "\n".join(
        [
            "# NotebookLM Brief — Demo",
            (
                "![Chart preview: ulta]"
                "(https://mparanza.com/review/brief/charts/png"
                f"?chart={chart_id}&facet=ulta)"
            ),
            (
                "![Chart preview: sephora]"
                "(https://mparanza.com/review/brief/charts/png"
                f"?chart={chart_id}&facet=sephora)"
            ),
            "",
        ]
    )
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2pM5sAAAAASUVORK5CYII="
    )
    calls: list[tuple[str, str | None]] = []

    def _fake_review_figures(
        chart_data: dict[str, object],
    ) -> list[tuple[str | None, go.Figure]]:
        del chart_data
        fig_ulta = go.Figure()
        fig_ulta.update_layout(
            title={
                "text": (
                    "<span>ulta line 1</span><br>"
                    "<span>ulta line 2</span><br>"
                    "<span>ulta line 3</span>"
                )
            }
        )
        fig_sephora = go.Figure()
        fig_sephora.update_layout(
            title={
                "text": (
                    "<span>sephora line 1</span><br>"
                    "<span>sephora line 2</span><br>"
                    "<span>sephora line 3</span>"
                )
            }
        )
        return [("ulta", fig_ulta), ("sephora", fig_sephora)]

    def _fake_render_png_bytes(
        chart_data: dict[str, object], *, facet: str | None = None
    ) -> bytes:
        calls.append((str(chart_data.get("chart_id") or ""), facet))
        return png_bytes

    monkeypatch.setattr(pdp_api, "_review_brief_chart_figures", _fake_review_figures)
    monkeypatch.setattr(
        pdp_api, "_render_review_brief_chart_png_bytes", _fake_render_png_bytes
    )

    output_zip_path = tmp_path / "brief-charts.zip"
    built_zip = pdp_api._build_review_brief_chart_png_bundle(
        markdown,
        charts_json_path=str(charts_json_path),
        output_zip_path=output_zip_path,
    )

    assert built_zip == output_zip_path
    with zipfile.ZipFile(output_zip_path, "r") as archive:
        names = archive.namelist()
        png_names = [name for name in names if name.endswith(".png")]
        assert set(png_names) == {
            f"{chart_id}__facet-sephora.png",
            f"{chart_id}__facet-ulta.png",
        }
        chart_map = archive.read("chart-map.md").decode("utf-8")
        assert f"| {chart_id} | ulta | " f"{chart_id}__facet-ulta.png |" in chart_map
        assert (
            f"| {chart_id} | sephora | " f"{chart_id}__facet-sephora.png |" in chart_map
        )
        chart_serials = json.loads(archive.read("chart-serials.json").decode("utf-8"))
        items_by_filename = {
            str(item.get("filename") or ""): item
            for item in chart_serials.get("items", [])
        }
        assert items_by_filename[f"{chart_id}__facet-ulta.png"]["chart_id"] == chart_id
        assert items_by_filename[f"{chart_id}__facet-ulta.png"]["facet"] == "ulta"
        assert (
            items_by_filename[f"{chart_id}__facet-ulta.png"]["title_line_1"]
            == "ulta line 1"
        )
        assert (
            items_by_filename[f"{chart_id}__facet-sephora.png"]["chart_id"] == chart_id
        )
        assert items_by_filename[f"{chart_id}__facet-sephora.png"]["facet"] == "sephora"
        assert (
            items_by_filename[f"{chart_id}__facet-sephora.png"]["title_line_1"]
            == "sephora line 1"
        )

    assert calls == [(chart_id, "ulta"), (chart_id, "sephora")]


def test_build_review_brief_chart_png_bundle_keeps_chart_id_name_without_facet_marker(
    tmp_path: Path, monkeypatch
) -> None:
    chart_id = "chart_demo_faceted_default"
    charts_payload = {
        "charts": [
            {"chart_id": chart_id, "chart_type": "stacked_share_facets", "rows": []},
        ]
    }
    charts_json_path = tmp_path / "brief.json"
    charts_json_path.write_text(json.dumps(charts_payload), encoding="utf-8")
    markdown = f"# NotebookLM Brief — Demo\n\n<!-- chart_id: {chart_id} -->\n"
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2pM5sAAAAASUVORK5CYII="
    )
    calls: list[tuple[str, str | None]] = []

    def _fake_review_figures(
        chart_data: dict[str, object],
    ) -> list[tuple[str | None, go.Figure]]:
        del chart_data
        fig_ulta = go.Figure()
        fig_ulta.update_layout(
            title={
                "text": (
                    "<span>ulta default line 1</span><br>"
                    "<span>ulta default line 2</span><br>"
                    "<span>ulta default line 3</span>"
                )
            }
        )
        fig_sephora = go.Figure()
        fig_sephora.update_layout(
            title={
                "text": (
                    "<span>sephora default line 1</span><br>"
                    "<span>sephora default line 2</span><br>"
                    "<span>sephora default line 3</span>"
                )
            }
        )
        return [("ulta", fig_ulta), ("sephora", fig_sephora)]

    def _fake_render_png_bytes(
        chart_data: dict[str, object], *, facet: str | None = None
    ) -> bytes:
        calls.append((str(chart_data.get("chart_id") or ""), facet))
        return png_bytes

    monkeypatch.setattr(pdp_api, "_review_brief_chart_figures", _fake_review_figures)
    monkeypatch.setattr(
        pdp_api, "_render_review_brief_chart_png_bytes", _fake_render_png_bytes
    )

    output_zip_path = tmp_path / "brief-charts.zip"
    pdp_api._build_review_brief_chart_png_bundle(
        markdown,
        charts_json_path=str(charts_json_path),
        output_zip_path=output_zip_path,
    )

    with zipfile.ZipFile(output_zip_path, "r") as archive:
        names = archive.namelist()
        png_names = [name for name in names if name.endswith(".png")]
        assert sorted(png_names) == sorted([f"{chart_id}.png"])
        chart_map = archive.read("chart-map.md").decode("utf-8")
        assert f"| {chart_id} | - | {chart_id}.png |" in chart_map
        chart_serials = json.loads(archive.read("chart-serials.json").decode("utf-8"))
        items_by_filename = {
            str(item.get("filename") or ""): item
            for item in chart_serials.get("items", [])
        }
        assert items_by_filename[f"{chart_id}.png"]["chart_id"] == chart_id
        assert items_by_filename[f"{chart_id}.png"]["facet"] is None
        assert (
            items_by_filename[f"{chart_id}.png"]["title_line_1"]
            == "ulta default line 1"
        )
        assert (
            items_by_filename[f"{chart_id}.png"]["title_line_2"]
            == "ulta default line 2"
        )
        assert (
            items_by_filename[f"{chart_id}.png"]["title_line_3"]
            == "ulta default line 3"
        )

    assert calls == [(chart_id, None)]


def test_fetch_review_brief_job_status_is_disabled() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None

    client = TestClient(app)
    response = client.get("/review/brief/jobs/job-inline-001")
    assert response.status_code == 410
    assert (
        "disabled pending redesign" in str(response.json().get("detail") or "").lower()
    )
    app.dependency_overrides.clear()


def test_download_review_brief_job_output_is_disabled() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None

    client = TestClient(app)
    response = client.get("/review/brief/jobs/job-download-001/download")
    assert response.status_code == 410
    assert (
        "disabled pending redesign" in str(response.json().get("detail") or "").lower()
    )
    app.dependency_overrides.clear()


def test_download_review_brief_job_charts_zip_is_disabled() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None

    client = TestClient(app)
    response = client.get("/review/brief/jobs/job-download-zip-001/charts.zip")
    assert response.status_code == 410
    assert (
        "disabled pending redesign" in str(response.json().get("detail") or "").lower()
    )
    app.dependency_overrides.clear()


def test_download_review_brief_job_package_is_disabled() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: None
    brief_permission = getattr(pdp_api.REVIEW_BRIEF_PERMISSION, "dependency", None)
    if callable(brief_permission):
        app.dependency_overrides[brief_permission] = lambda: None

    client = TestClient(app)
    response = client.get("/review/brief/jobs/job-package-001/package.zip")
    assert response.status_code == 410
    assert (
        "disabled pending redesign" in str(response.json().get("detail") or "").lower()
    )
    app.dependency_overrides.clear()


def test_sales_charts_route_has_been_removed() -> None:
    client = TestClient(app)
    response = client.get(
        "/review/sales/charts",
        params=[("retailer", "ulta"), ("category", "blush")],
    )

    assert response.status_code == 404


def test_create_app_unhandled_exception_returns_error_id() -> None:
    test_app = pdp_api.create_app()

    @test_app.get("/__boom")
    def _boom() -> dict[str, str]:
        raise RuntimeError("boom")

    client = TestClient(test_app, raise_server_exceptions=False)
    response = client.get("/__boom?x=1")

    assert response.status_code == 500
    payload = response.json()
    assert "Internal server error" in str(payload.get("detail") or "")
    assert str(payload.get("error_id") or "").strip()
