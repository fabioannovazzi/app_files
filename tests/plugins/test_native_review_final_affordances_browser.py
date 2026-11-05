"""Exercise read-only affordances and owned document labels with real MCP data."""

from __future__ import annotations

import os

from playwright.sync_api import expect

from tests.plugins.test_vera_native_inps import inps_run  # noqa: F401
from tests.plugins.test_vera_native_variance import variance_run  # noqa: F401
from tests.plugins.test_vera_review_browser import review_host

__all__: list[str] = []


def test_variance_viewer_cannot_offer_save_or_calculation(variance_run, monkeypatch):
    _, output, binding, _ = variance_run
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    before = {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    with review_host(dict(os.environ)) as (_, mount, errors):
        app = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        expect(
            app.get_by_role("button", name="Conserva scelte in bozza", exact=True)
        ).to_be_disabled()
        expect(
            app.get_by_role(
                "button", name="Calcola e conserva tutti i risultati", exact=True
            )
        ).to_be_disabled()
        assert not errors
    assert before == {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }


def test_inps_owned_document_labels_preserve_authored_fact(inps_run):
    _, binding, output = inps_run
    before = {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    with review_host(dict(os.environ)) as (_, mount, errors):
        app = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        expect(
            app.get_by_role("heading", name="Memo per lo studio", exact=True)
        ).to_be_visible()
        expect(
            app.get_by_role("heading", name="Controlli del fascicolo", exact=True)
        ).to_be_visible()
        for label in ("Artifact studio_memo.md", "Package validation audit"):
            expect(app.get_by_role("heading", name=label, exact=True)).to_have_count(0)
        app.get_by_role(
            "button", name="Consulta evidenza e riscontro", exact=True
        ).first.click()
        expect(
            app.get_by_role("heading", name="Decorrenza del rapporto", exact=True)
        ).to_be_visible()
        assert not errors
    assert before == {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
