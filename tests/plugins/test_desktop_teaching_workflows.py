"""Run the real product workflows against the packaged fictional starters."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tests.plugins.test_desktop_teaching import (
    ROOT,
    WORKFLOWS,
    cases,
    change,
    prepare,
    store,
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_product_workflow_from_the_bound_tutorial_case(store, monkeypatch):
    prepare(store)
    wf = WORKFLOWS[store.product][0]
    change(store, "start", workflow_id=wf)
    lesson = store.status()["lessons"][0]
    source = (
        store.plugin_root
        / "assets/onboarding"
        / ("actual-budget.xlsx" if store.product == "clara" else "matter-brief.md")
    )
    case = cases.prepare_case(
        store,
        thread_id="worker",
        workflow=wf,
        token=lesson["worker_token"],
        phase="demo",
        sources=[source],
    )
    if store.product == "clara":
        monkeypatch.syspath_prepend(
            str(ROOT / "plugins/management-control-pack/scripts")
        )
        module = _load(
            "tutorial_budget",
            store.plugin_root / "modules/reporting-engine/scripts/budget_report.py",
        )
        bound = Path(case["inputs"][0]["path"])
        output = Path(case["output_dir"])
        inspection_dir = output / "inspection"
        assert (
            module.main(
                ["inspect", "--input", str(bound), "--output-dir", str(inspection_dir)]
            )
            == 0
        )
        inspection = json.loads(
            (inspection_dir / "inspection.json").read_text(encoding="utf-8")
        )
        ids = {t["table_label"]: t["table_id"] for t in inspection["tables"]}
        # The fixture explicitly supplies monthly EUR revenue and negative COGS.
        # Review binds those meanings and the visible source totals, not keywords.
        recipe = {
            "schema_version": "vera.management_control_recipe.v1",
            "workflow_id": "management-control-pack",
            "inventory_sha256": inspection["inventory_sha256"],
            "entity": "Arco — synthetic teaching case",
            "reporting_period": {
                "start": "2026-01-01",
                "end": "2026-02-28",
                "cutoff": "2026-02-28",
            },
            "currency": "EUR",
            "fiscal_year_start_month": 1,
            "number_format": "dot_decimal",
            "date_format": "%Y-%m-%d",
            "tables": {
                "general_ledger": {
                    "table_id": ids["GL"],
                    "columns": {
                        "date": "Date",
                        "account_code": "Account",
                        "category": "Category",
                        "amount": "Amount",
                    },
                },
                "budget": {
                    "table_id": ids["Budget"],
                    "columns": {
                        "date": "Date",
                        "category": "Category",
                        "amount": "Amount",
                    },
                },
            },
            "category_roles": {"Revenue": "revenue", "COGS": "cogs"},
            "category_multipliers": {},
            "aging_buckets": [30, 60, 90],
            "top_customers": 10,
            "control_totals": {"general_ledger": "90000", "budget": "81000"},
            "control_tolerance": "0.01",
            "mapping_review": {
                "status": "reviewed",
                "reviewer": "Synthetic fixture review",
                "reviewed_at": "2026-09-13T10:00:00+02:00",
            },
            "audience": "public_demo",
        }
        path = output / "reviewed_recipe.json"
        path.write_text(json.dumps(recipe), encoding="utf-8")
        report = output / "report"
        assert (
            module.main(
                [
                    "run",
                    "--input",
                    str(bound),
                    "--recipe",
                    str(path),
                    "--output-dir",
                    str(report),
                ]
            )
            == 0
        )
        pack = json.loads(
            (report / "management_control_pack.json").read_text(encoding="utf-8")
        )
        assert pack["metrics"]["budget.total.ebitda_variance"]["value"] == "9000"
        assert (report / "model_context.json").is_file()
        artifacts = [
            report / "management_control_pack.json",
            report / "model_context.json",
        ]
    else:
        monkeypatch.syspath_prepend(str(ROOT / "plugins/apertura-pratica/scripts"))
        core = _load(
            "tutorial_matter",
            ROOT / "plugins/apertura-pratica/scripts/apertura_pratica_core.py",
        )
        output = Path(case["output_dir"])
        core.initialize_workspace(
            output,
            opening_mode="new_client_new_matter",
            client_reference="synthetic-beta",
            matter_reference="synthetic-supply",
            language="it",
        )
        # Managed initialization imports the actual ledger-bound selected input.
        intake_path = output / "matter_intake.json"
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
        intake["client"]["display_name"] = "Beta Laboratorio Srl (fittizio)"
        intake["matter"].update(
            title="Consegna incompleta — esempio",
            objective="Preparare il dossier da rivedere",
            requested_work="Assistenza richiesta nella controversia di fornitura",
            summary="Il cliente menziona contratto e corrispondenza non ancora forniti.",
        )
        intake_path.write_text(json.dumps(intake, ensure_ascii=False), encoding="utf-8")
        core.prepare_review(output)
        validation = core.validate_run(output)
        assert validation["status"] != "ready_to_open"
        memo = output / "matter_opening_memo.md"
        assert "Beta Laboratorio" in memo.read_text(encoding="utf-8")
        assert (output / "review_payload.json").is_file()
        artifacts = [memo, output / "validation_report.json"]
    change(
        store,
        "demo",
        workflow_id=wf,
        artifacts=[str(p) for p in artifacts],
        prompt="Show the actual workflow",
        review="Actual source-bound output checked; professional review and user practice remain pending",
    )
    assert store.status()["lessons"][0]["status"] == "active"
