"""Shared presentation regressions: exact figures, source closure and draft status."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.plugins.test_business_planning_shared import (
    FIXTURE,
    REPORT_MODULE,
    PlanningError,
    bind_plugin_imports,
    build_plan,
    case_data,
    compile_html,
    export_pdf,
    write_package,
)


def presentation_case():
    case = case_data()
    case["presentation"] = {
        "language": "it",
        "tables": [
            {
                "id": "annual",
                "title": "Scenario sintetico",
                "section": "economics",
                "headers": ["Voce", "EUR"],
                "rows": [
                    [
                        {"text": "Ricavi"},
                        {
                            "calculation_ids": [
                                f"base/2027-{m}/revenue" for m in ("01", "02", "03")
                            ],
                            "operation": "sum",
                            "value": "3000",
                        },
                    ]
                ],
                "caption_id": "profit-risk",
            }
        ],
        "actions": [
            {
                "action_id": "actions",
                "owner": "Fondatori",
                "when": "Prima degli ordini",
                "criterion_id": "change",
            }
        ],
        "source_notes": [
            {
                "source_id": case["sources"][0]["id"],
                "claim": "Confronto ricavi",
                "locator": "Tabella A, righe 1-3",
                "url": "https://example.org/evidence",
            }
        ],
    }
    return case


def test_native_tables_sources_and_legend_render_without_wrapper():
    case = presentation_case()
    rendered = compile_html(build_plan(case, source_root=FIXTURE), source_root=FIXTURE)
    assert '<html lang="it">' in rendered
    assert ">3.000<" in rendered
    assert "Tabella A, righe 1-3" in rendered
    assert case["sources"][0]["version"] in rendered
    assert 'class="source-url">https://example.org/evidence' in rendered
    assert 'svg class="legend-key"' in rendered
    assert 'stroke-dasharray="8 4"' in rendered
    assert "Fondatori" in rendered and "Prova / criterio di decisione" in rendered
    assert rendered.count('id="narrative-actions"') == 1
    assert "base/2027-01/revenue … base/2027-03/revenue (3)" in rendered


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["tables"][0]["rows"][0][1].update(value="2999"),
        lambda p: p["tables"][0]["rows"][0][1].update(calculation_ids=["missing"]),
        lambda p: p["tables"][0]["rows"][0][1].update(
            calculation_ids=["base/2027-01/revenue"] * 2
        ),
        lambda p: p["tables"][0]["rows"][0][1].update(style="percent"),
        lambda p: p["source_notes"][0].update(url="javascript:alert(1)"),
        lambda p: p["source_notes"][0].update(source_id="unknown"),
        lambda p: p["actions"][0].update(criterion_id="missing"),
        lambda p: p.update(actions="invalid"),
        lambda p: p.update(language="invalid"),
    ],
)
def test_invalid_presentation_is_rejected_before_output(mutation):
    case = presentation_case()
    mutation(case["presentation"])
    with pytest.raises(PlanningError):
        build_plan(case, source_root=FIXTURE)


def test_table_tampering_rejected_by_canonical_replay():
    plan = build_plan(presentation_case(), source_root=FIXTURE)
    plan["case"]["presentation"]["tables"][0]["rows"][0][1]["value"] = "3001"
    with pytest.raises(PlanningError):
        compile_html(plan, source_root=FIXTURE)


def test_draft_pdf_preserves_partial_status_and_hashes_actual_output(
    tmp_path, monkeypatch
):
    case = presentation_case()
    case["review"] = {"status": "pending"}
    plan = build_plan(case, source_root=FIXTURE)

    def render(plan, *, source_root, output, draft=False):
        assert draft and plan["status"] == "partial"
        output.write_bytes(b"%PDF-fixture")

    monkeypatch.setattr(REPORT_MODULE, "export_pdf", render)
    write_package(plan, source_root=FIXTURE, output=tmp_path, draft_pdf=True)
    receipt = json.loads((tmp_path / "execution_receipt.json").read_text())
    assert receipt["status"] == "partial" and receipt["pdf_mode"] == "draft"
    assert {
        "path": "business_plan_draft.pdf",
        "sha256": hashlib.sha256(b"%PDF-fixture").hexdigest(),
    } in receipt["outputs"]


def test_partial_final_export_still_refused(tmp_path):
    case = presentation_case()
    case["review"] = {"status": "pending"}
    with pytest.raises(PlanningError):
        export_pdf(
            build_plan(case, source_root=FIXTURE),
            source_root=FIXTURE,
            output=tmp_path / "invalid.pdf",
        )
    assert not (tmp_path / "invalid.pdf").exists()


def test_failed_draft_removes_partial_pdf_and_records_failure(tmp_path, monkeypatch):
    plan = build_plan(presentation_case(), source_root=FIXTURE)

    def fail(plan, *, source_root, output, draft=False):
        output.write_bytes(b"partial")
        raise PlanningError("renderer interrupted")

    monkeypatch.setattr(REPORT_MODULE, "export_pdf", fail)
    with pytest.raises(PlanningError, match="renderer interrupted"):
        write_package(plan, source_root=FIXTURE, output=tmp_path, draft_pdf=True)
    receipt = json.loads((tmp_path / "execution_receipt.json").read_text())
    assert receipt["status"] == "partial"
    assert receipt["pdf_error"] == "renderer interrupted"
    assert not (tmp_path / "business_plan_draft.pdf").exists()
    assert (tmp_path / "business_plan_review.html").exists()
