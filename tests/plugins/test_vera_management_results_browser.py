"""Read saved reporting and costing results without exposing receipt internals."""

from __future__ import annotations

import hashlib
import json
import os

import pytest
from playwright.sync_api import expect

from tests.plugins.test_vera_native_management_execution import (  # noqa: F401
    calculate,
    management_run,
)
from tests.plugins.test_vera_review_browser import review_host

__all__: list[str] = []


@pytest.mark.parametrize(
    "management_run,expected_value",
    [("reporting", "1.000"), ("costing", "21.000,00")],
    indirect=["management_run"],
)
@pytest.mark.parametrize("width", [400, 1080])
def test_saved_management_shows_values_coverage_and_controls_without_mutating_files(
    management_run, monkeypatch, width, expected_value
):
    _, output, binding, choices, _ = management_run
    result, _ = calculate(management_run)
    folder = output / result["source_ref"]
    original = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()
    }
    context = json.loads((folder / "model_context.json").read_text())
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    with review_host(dict(os.environ)) as (page, mount, errors):
        page.set_viewport_size({"width": width, "height": 900})
        app = mount("vera_workspace_open", {})
        app.get_by_role("button", name="Apri lavoro →", exact=True).click()
        expect(
            app.get_by_role("heading", name="Calcolo conservato", exact=True)
        ).to_be_visible()
        expect(
            app.get_by_role("heading", name="Risultati calcolati", exact=True)
        ).to_be_visible()
        expect(
            app.get_by_role("heading", name="Copertura dei dati", exact=True)
        ).to_be_visible()
        expect(
            app.get_by_role("heading", name="Controlli sui totali", exact=True)
        ).to_be_visible()
        expect(
            app.get_by_role(
                "button", name="Calcola e conserva tutti i file", exact=True
            )
        ).to_have_count(0)
        assert app.locator("main").evaluate(
            "node => node.scrollWidth <= node.clientWidth + 1"
        )
        visible = app.locator("main").inner_text()
        for technical in (
            binding["run_id"],
            result["source_ref"],
            "ordinary_exit_code",
            "context_receipt_verified",
            "model_context.json",
            "metric_id",
            "Net cash movement",
            "Top customer revenue share",
            "Top five customer revenue share",
            "Service gross margin",
            "receivables",
            "payables",
            "sales_lines",
        ):
            assert technical not in visible
        expect(
            app.get_by_role("cell", name=expected_value, exact=True).first
        ).to_be_visible()
        assert "direct_costing_evoluto" not in visible
        assert "reviewed_source_revenue" not in visible
        metric_count = len(context["metrics"])
        # Every bounded metric is presented, including zero and negative values.
        tables = app.locator(".prepared-table table")
        assert tables.locator("tbody tr").count() == metric_count + len(
            context["coverage"]
        ) + len(context["controls"])
        app.get_by_role("button", name="Fatti calcolati", exact=True).first.click()
        expect(
            app.get_by_role("heading", name="Prospetto conservato").first
        ).to_be_visible()
        assert "| ---" not in app.locator("main").inner_text()
        assert not errors
        if os.environ.get("VERA_REVIEW_SCREENSHOTS"):
            from pathlib import Path

            page.screenshot(
                path=Path(os.environ["VERA_REVIEW_SCREENSHOTS"])
                / f"management-{choices['mode']}-{width}.png"
            )
    assert original == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()
    }
