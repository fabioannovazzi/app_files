"""Execute native specialist recipes, then consume their real sealed artifacts in CNC."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.plugins.test_composizione_negoziata import ROOT, cnc, ledger, node, request
from tests.plugins.test_teaching_kit_execution import _complete_teaching_case

QUALIFIERS = [
    "tests/plugins/test_teaching_kit_execution.py::test_financial_analysis_kit_runs_current_net_debt_pack[demo-38000-it]",
    "tests/plugins/test_teaching_kit_execution.py::test_centrale_rischi_kit_runs_actual_inspection_analysis_and_delivery[demo]",
    "tests/plugins/test_teaching_kit_execution.py::test_bank_reconciliation_kit_runs_current_comparison[it-demo-2]",
    "tests/plugins/test_teaching_kit_execution.py::test_open_item_kit_runs_current_pdf_ingestion_and_workpapers[it-demo-2]",
    "tests/plugins/test_business_planning_shared.py::test_vera_registered_entrypoint_binds_every_source_receipt",
]
RESULTS = {
    "financial-analysis": "prepared/fdd_result.json",
    "centrale-rischi-review": "analysis/centrale_rischi_analysis.json",
    "journal-bank-reconciliation": "reconciliation/reconciliation_audit.json",
    "open-item-reconciliation": "assurance_final_outputs/reconciliation_results.json",
    "business-planning": "plan/business_plan.json",
}


def bind_native_results(root: Path) -> dict[str, dict]:
    """Keep each fictional case separate; import no result from another engagement."""
    from vera_assurance import load_client_engagement_context_file

    evidence = {}
    paths = sorted(root.rglob("context.json"))
    for context_path in paths:
        portable = json.loads(context_path.read_text())
        workflow = portable.get("workflow_id")
        if workflow not in RESULTS:
            continue
        context = load_client_engagement_context_file(
            context_path,
            expected_workflow_id=workflow,
            allowed_statuses=("running", "ready_for_review", "completed"),
        )
        client_root = Path(context["studio_client_folder"]["client_root"])
        run_record = json.loads((context_path.parent / "run.json").read_text())
        if run_record["status"] == "running":
            _complete_teaching_case(
                {"context": context, "output_dir": context["output_dir"]}, client_root
            )
        manifest = json.loads(
            (context_path.parent / "artifact_manifest.json").read_text()
        )
        result = next(
            item for item in manifest["artifacts"] if item["path"] == RESULTS[workflow]
        )
        prepared = ledger.prepare_run(
            client_root,
            context["client_id"],
            context["engagement_id"],
            cnc.WORKFLOW,
            "completion-test",
            input_ids=[],
            upstream_artifacts=[
                {
                    "run_id": context["run_id"],
                    "artifact_id": result["artifact_id"],
                    "role": "source",
                }
            ],
            new_run=True,
        )
        run = ledger.start_run(
            client_root, context["engagement_id"], prepared["run"]["run_id"]
        )
        binding = run["context"]["input_bindings"][0]
        item = node(
            "specialist_result",
            kind="analysis",
            content=f"Actual synthetic {workflow} result captured. Its specialist limits and open issues remain applicable; capture does not imply professional acceptance.",
        )
        item["classification"] = "calculated"
        item["citations"] = [
            {"binding_id": binding["binding_id"], "locator": RESULTS[workflow]}
        ]
        saved = cnc.apply_request(Path(run["context_path"]), request(item))
        output = Path(run["output_dir"])
        (output / "cnc-handoff.md").write_text(
            cnc.render_record(saved), encoding="utf-8"
        )
        _complete_teaching_case(run, client_root)
        citation = saved["payload"]["nodes"]["specialist_result"]["citations"][0]
        evidence[workflow] = {
            "source_sha256": result["sha256"],
            "bound_sha256": citation["sha256"],
            "workflow": citation["upstream_workflow_id"],
            "snapshot": saved["content_sha256"],
            "context": run["context_path"],
        }
    (root / "cnc-handoffs.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )
    return evidence


def test_five_native_specialist_results_are_sealed_and_bound_to_cnc(
    tmp_path, monkeypatch
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    monkeypatch.setitem(sys.modules, "client_ledger", ledger)
    cases = tmp_path / "specialist-cases"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            *QUALIFIERS,
            f"--basetemp={cases}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    evidence = bind_native_results(cases)
    assert set(evidence) == set(RESULTS)
    assert {key: row["workflow"] for key, row in evidence.items()} == {
        key: key for key in RESULTS
    }
    assert {key: row["source_sha256"] for key, row in evidence.items()} == {
        key: row["bound_sha256"] for key, row in evidence.items()
    }
