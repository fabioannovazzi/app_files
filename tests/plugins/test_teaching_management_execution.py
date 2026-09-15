"""Replay authored teaching commentary through the complete current pack workflow.

These are local execution checks, not simulated learner or professional approval.
The prose fixture captures host-authored interpretation; no model is called here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.plugins._teaching_release import prepared_kit, record_native_check
from tests.plugins.test_teaching_kit_execution import (
    ROOT,
    _bound_case,
    _complete_teaching_case,
    _read,
    _run,
    _write,
)

__all__: list[str] = []

MODULE = "plugins/management-control-pack/scripts"


def _recipe(inventory, language, phase, entity):
    """Encode only the reviewed accounting meanings in the prepared source note."""
    tables = {t["table_label"]: t["table_id"] for t in inventory["tables"]}
    end = "2026-02-28" if phase == "demo" else "2026-03-31"
    return {
        "schema_version": "vera.management_control_recipe.v1",
        "workflow_id": "management-control-pack",
        "inventory_sha256": inventory["inventory_sha256"],
        "language": language,
        "entity": entity,
        "reporting_period": {"start": "2026-01-01", "end": end, "cutoff": end},
        "currency": "EUR",
        "fiscal_year_start_month": 1,
        "number_format": "dot_decimal",
        "date_format": "%Y-%m-%d",
        "tables": {
            "general_ledger": {
                "table_id": tables["GL"],
                "columns": {
                    "date": "Date",
                    "account_code": "Account",
                    "category": "Category",
                    "amount": "Amount",
                },
            },
            "budget": {
                "table_id": tables["Budget"],
                "columns": {"date": "Date", "category": "Category", "amount": "Amount"},
            },
        },
        "category_roles": {
            "Revenue": "revenue",
            "COGS": "cogs",
            "Operating expenses": "operating_expense",
        },
        "category_multipliers": {},
        "aging_buckets": [30, 60, 90],
        "top_customers": 10,
        "control_totals": {
            "general_ledger": "53000" if phase == "demo" else "85000",
            "budget": "47000" if phase == "demo" else "77000",
        },
        "control_tolerance": "0.01",
        "mapping_review": {
            "status": "reviewed",
            "reviewer": "Authored fictional source meanings; no professional approval",
            "reviewed_at": "2026-09-15T00:00:00+02:00",
        },
        "audience": "public_demo",
    }


def _execute(run, client_root, language, phase, prior=None):
    """Inspect, map, calculate, interpret, finalize and deliver one actual run."""
    prose = _read(ROOT / "tests/fixtures/teaching_reviews/management_control.json")[
        language
    ]
    output = Path(run["output_dir"])
    source = next(
        item["path"]
        for item in run["context"]["input_bindings"]
        if item["path"].endswith(".xlsx")
    )
    _run(f"{MODULE}/check_dependencies.py")
    _run(
        f"{MODULE}/inspect_inputs.py",
        "--input",
        source,
        "--output-dir",
        output / "inspection",
        "--client-engagement",
        run["context_path"],
    )
    inventory = _read(output / "inspection/inspection.json")
    recipe = _recipe(inventory, language, phase, prose["entity"])
    _write(output / "reviewed_recipe.json", recipe)
    pack = output / "pack"
    _run(
        f"{MODULE}/run_pack.py",
        "--input",
        source,
        "--recipe",
        output / "reviewed_recipe.json",
        "--output-dir",
        pack,
        "--client-engagement",
        run["context_path"],
    )
    execution = _read(pack / "execution_receipt.json")
    receipt = _read(pack / "model_context_receipt.json")
    context = _read(pack / "model_context.json")
    assert execution["status"] == context["status"] == "partial"
    assert receipt["validation"]["status"] == "passed"
    assert (
        receipt["model_context"]["sha256"]
        == hashlib.sha256((pack / "model_context.json").read_bytes()).hexdigest()
    )
    assert receipt["model_read_policy"]["full_pack_model_read_required"] is False
    assert {c["status"] for c in context["controls"]} == {"passed"}
    metrics = {m["metric_id"]: m["value"] for m in context["metrics"]}
    assert metrics["budget.total.ebitda_variance"] == (
        "6000" if phase == "demo" else "8000"
    )
    assert metrics["pnl.total.ebitda"] == recipe["control_totals"]["general_ledger"]
    commentary = _read(pack / "commentary_template.json")
    commentary.update(prose[phase])
    commentary["limitations"] = prose["limitations"]
    _write(pack / "management_commentary.json", commentary)
    _run(
        f"{MODULE}/finalize_pack.py",
        "--pack",
        pack / "management_control_pack.json",
        "--commentary",
        pack / "management_commentary.json",
        "--output-dir",
        pack / "final",
        "--client-engagement",
        run["context_path"],
    )
    final_receipt = _read(pack / "final/commentary_receipt.json")
    assert final_receipt["status"] == "draft_pending_professional_review"
    report = (pack / "final/management_control_report.md").read_text(encoding="utf-8")
    first_observation = prose[phase]["observations"][0]["text"]
    comparison_heading = (
        "## Confronto con il budget" if language == "it" else "## Budget comparisons"
    )
    assert report.index(first_observation) < report.index(comparison_heading)
    assert "metric_id |" not in report
    assert "| -0,00 |" not in report and "| -0.00 |" not in report
    assert "| Consuntivo |" in report if language == "it" else "| Actual |" in report
    html = (pack / "final/management_control_dashboard_reviewed.html").read_text(
        encoding="utf-8"
    )
    assert (
        "<h2>Consuntivo e budget</h2>" in html
        if language == "it"
        else "<h2>Actual and budget</h2>" in html
    )
    workbook = load_workbook(pack / "management_control_pack.xlsx", data_only=True)
    summary = workbook["Sintesi" if language == "it" else "Summary"]
    assert summary["C12"].value == int(recipe["control_totals"]["general_ledger"])
    comparisons = workbook[
        "Confronto con il budget" if language == "it" else "Budget comparisons"
    ]
    assert comparisons["D2"].value == 100000
    assert comparisons["E2"].value == 120000
    assert comparisons["G2"].value == 0.2
    assert comparisons["G2"].number_format == "0.00%"
    assert comparisons.freeze_panes == "A2"
    workbook.close()
    targets = [
        (prose["dashboard"], pack / "final/management_control_dashboard_reviewed.html"),
        (prose["report"], pack / "final/management_control_report.md"),
        (prose["workbook"], pack / "management_control_pack.xlsx"),
        (prose["review"], output / "codex_run_review.md"),
        (prose["data_report"], output / "model_data_report.md"),
    ]
    if prior:
        targets.append(
            (prose["prior"], prior / "pack/final/management_control_report.md")
        )
        previous = _read(prior / "pack/model_context.json")
        assert (
            context["sections"]["monthly_pnl"]["rows"][:2]
            == previous["sections"]["monthly_pnl"]["rows"]
        )
    (output / "codex_run_review.md").write_text(
        prose["review_note"] + "\n", encoding="utf-8"
    )
    (output / "artifact_card.md").write_text(
        f"# {prose['card_title']}\n\n{prose[phase]['observations'][0]['text']}\n\n"
        + "\n".join(f"- [{label}]({path})" for label, path in targets)
        + f"\n\n{prose['next']}\n",
        encoding="utf-8",
    )
    ledger = _complete_teaching_case(run, client_root)
    assert all(path.is_file() and path.stat().st_size for _, path in targets)
    return ledger, output


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
@prepared_kit("vera/management-control-pack")
def test_management_kit_delivers_commentary_and_retains_previous_period(
    tmp_path, monkeypatch, record_property, language, phase
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "management-control-pack",
        "management-control-pack",
        "demo",
        language=language,
    )
    ledger, first = _execute(run, tmp_path / "case", language, "demo")
    output = first
    preserved = {p: p.read_bytes() for p in first.rglob("*") if p.is_file()}
    if phase == "practice":
        context = run["context"]
        sources = [
            p for p in (tmp_path / "kit/files/practice").iterdir() if p.is_file()
        ]
        inputs = [
            ledger.import_document(
                tmp_path / "case",
                context["client_id"],
                context["engagement_id"],
                path,
                "source",
            )["receipt"]["input_id"]
            for path in sources
        ]
        prepared = ledger.prepare_run(
            tmp_path / "case",
            context["client_id"],
            context["engagement_id"],
            "management-control-pack",
            context["workflow_version"],
            input_ids=inputs,
            new_run=True,
        )
        revised = ledger.start_run(
            tmp_path / "case", context["engagement_id"], prepared["run"]["run_id"]
        )
        _, output = _execute(revised, tmp_path / "case", language, phase, first)
        assert output != first
    assert all(p.read_bytes() == content for p, content in preserved.items())
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="management-control-pack",
        language=language,
        phase=phase,
    )
    record_property("teaching_output", str(output))
