"""Execute the fictional CNC lessons; do not attest learner or professional approval."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins._teaching_release import prepared_kit, record_native_check
from tests.plugins.test_composizione_negoziata import (
    ROOT,
    SCRIPT,
    cnc,
    ledger,
    node,
    request,
)
from tests.plugins.test_teaching_kit_execution import (
    _bound_case,
    _complete_teaching_case,
    _run,
)

__all__ = ["test_cnc_kit_executes_forecast_and_preserves_case_versions"]

WORDS = {
    "it": (
        "Scadenzario e conferma del debitore mancanti.",
        "Cassa minima EUR {cash}; verificare gli incassi prima di formulare proposte.",
    ),
    "en": (
        "Aging and debtor confirmation are missing.",
        "Minimum cash EUR {cash}; verify receipts before making proposals.",
    ),
    "fr": (
        "Balance âgée et confirmation du débiteur absentes.",
        "Trésorerie minimale EUR {cash}; vérifier les encaissements avant toute proposition.",
    ),
    "de": (
        "Altersstruktur und Schuldnerbestätigung fehlen.",
        "Mindestliquidität EUR {cash}; Zahlungseingänge vor Vorschlägen prüfen.",
    ),
    "es": (
        "Faltan antigüedad de saldos y confirmación del deudor.",
        "Caja mínima EUR {cash}; verificar cobros antes de formular propuestas.",
    ),
}


def _save(root: Path, run: dict, update: dict) -> dict:
    """Use the native CLI to persist a test-authored, explicitly synthetic judgment."""
    path = Path(run["output_dir"]) / f"request-{update['idempotency_key']}.json"
    path.write_text(json.dumps(update, ensure_ascii=False), encoding="utf-8")
    _run(SCRIPT, "--client-engagement", run["context_path"], "--request", path)
    return ledger.load_workflow_history(
        root, run["context"]["engagement_id"], cnc.WORKFLOW
    )[-1]


def _next_run(
    root: Path, prior: dict, inputs: list[str], treasury: dict | None = None
) -> dict:
    """Start another CNC run with real input and optional upstream artifact bindings."""
    context = prior["context"]
    kwargs = {}
    if treasury is not None:
        kwargs["upstream_artifacts"] = [
            {
                "run_id": treasury["run"]["run_id"],
                "artifact_id": "forecast",
                "role": "source",
            }
        ]
    prepared = ledger.prepare_run(
        root,
        context["client_id"],
        context["engagement_id"],
        cnc.WORKFLOW,
        context["workflow_version"],
        input_ids=inputs,
        new_run=True,
        **kwargs,
    )
    return ledger.start_run(root, context["engagement_id"], prepared["run"]["run_id"])


def _forecast(
    root: Path, context: dict, phase: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict, dict]:
    """Execute treasury using the explicitly reviewed fictional lesson facts."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/treasury-forecast/scripts"))
    from treasury_inputs import HEADERS
    from treasury_session import current_record

    staging = root / f"treasury-{phase}"
    staging.mkdir()
    receipt_date = "2026-11-15" if phase == "demo" else "2027-01-15"
    tables = {name: [] for name in HEADERS}
    tables["accounts"] = [{"account_id": "bank", "balance": "50000.00"}]
    tables["planned_flows"] = [
        {
            "flow_id": "receipt",
            "side": "receivable",
            "amount": "100000.00",
            "expected_date": receipt_date,
            "description": "Synthetic receipt",
            "basis": "Unconfirmed date from fictional CNC lesson",
        },
        {
            "flow_id": "payment",
            "side": "payable",
            "amount": "80000.00",
            "expected_date": "2026-11-30",
            "description": "Synthetic payment",
            "basis": "Fictional CNC lesson obligation",
        },
    ]
    manifest = {
        "schema_version": "vera.treasury_manifest.v1",
        "company_id": "synthetic-cnc",
        "company_name": "Synthetic CNC lesson",
        "currency": "EUR",
        "as_of": "2026-10-31",
        "horizon_end": "2027-01-31",
        "coverage": "Only the two fictional flows; aging, collectability and business completeness unverified",
        "tables": {},
        "invoice_files": [],
        "previous": None,
    }
    inputs = []
    for name, headers in HEADERS.items():
        path = staging / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(tables[name])
        receipt = ledger.import_document(
            root, context["client_id"], context["engagement_id"], path, "source"
        )["receipt"]
        inputs.append(receipt["input_id"])
        manifest["tables"][name] = {
            "path": f"imports/{receipt['input_id']}/{Path(receipt['relative_path']).name}"
        }
    path = staging / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    inputs.append(
        ledger.import_document(
            root, context["client_id"], context["engagement_id"], path, "source"
        )["receipt"]["input_id"]
    )
    prepared = ledger.prepare_run(
        root,
        context["client_id"],
        context["engagement_id"],
        "treasury-forecast",
        context["workflow_version"],
        input_ids=inputs,
        new_run=True,
    )
    run = ledger.start_run(root, context["engagement_id"], prepared["run"]["run_id"])
    bound_manifest = next(
        row["path"]
        for row in run["context"]["input_bindings"]
        if row["path"].endswith("manifest.json")
    )
    _run(
        "plugins/treasury-forecast/scripts/run_treasury.py",
        "prepare",
        "--client-engagement",
        run["context_path"],
        "--manifest",
        bound_manifest,
    )
    _, result = current_record(Path(run["output_dir"]))
    relative = Path("versions") / result["record_sha256"] / "forecast.json"
    run["forecast_path"] = str(Path(run["output_dir"]) / relative)
    _complete_teaching_case(run, root, artifact_ids={relative.as_posix(): "forecast"})
    return run, result


def _draft(
    root: Path, run: dict, cash: str, language: str, revision: int, phase: str
) -> dict:
    """Bind the actual forecast; prose is a reviewed synthetic fixture, not model output."""
    binding = next(
        row
        for row in run["context"]["input_bindings"]
        if row.get("upstream_workflow_id") == "treasury-forecast"
    )
    analysis = node(
        "forecast",
        kind="analysis",
        dependencies=("collection",),
        content=WORDS[language][1].format(cash=cash),
    )
    analysis["classification"] = "calculated"
    analysis["citations"] = [
        {"binding_id": binding["binding_id"], "locator": "minimum_daily_cash; events"}
    ]
    funding = node(
        "funding",
        kind="analysis",
        dependencies=("forecast",),
        content=WORDS[language][1].format(cash=cash),
    )
    memo = node(
        "memo",
        kind="draft",
        dependencies=("funding",),
        content=WORDS[language][1].format(cash=cash),
    )
    return _save(
        root,
        run,
        request(analysis, funding, memo, revision=revision, key=f"draft-{phase}"),
    )


@prepared_kit("vera/composizione-negoziata")
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_cnc_kit_executes_forecast_and_preserves_case_versions(
    tmp_path, monkeypatch, record_property, language, phase
):
    monkeypatch.setitem(sys.modules, "client_ledger", ledger)
    run = _bound_case(
        tmp_path, monkeypatch, cnc.WORKFLOW, cnc.WORKFLOW, "demo", language=language
    )
    root = tmp_path / "case"
    source = run["context"]["input_bindings"][0]
    input_ids = [source["binding_id"]]
    document = node(
        "document",
        kind="document",
        content=Path(source["path"]).read_text(encoding="utf-8"),
    )
    document["classification"] = "documented"
    document["citations"] = [
        {"binding_id": source["binding_id"], "locator": "Complete fictional case input"}
    ]
    gap = node("missing_aging", kind="gap", content=WORDS[language][0])
    gap["classification"] = "missing"
    _save(
        root,
        run,
        request(
            document,
            node(
                "collection",
                dependencies=("document",),
                content="2026-11-15; unconfirmed fictional receipt",
            ),
            gap,
        ),
    )
    _complete_teaching_case(run, root)
    treasury, forecast = _forecast(root, run["context"], "demo", monkeypatch)
    assert forecast["minimum_daily_cash"] == "50000.00"
    baseline_forecast = Path(treasury["forecast_path"])
    baseline_bytes = baseline_forecast.read_bytes()
    run = _next_run(root, run, input_ids, treasury)
    baseline = _draft(root, run, forecast["minimum_daily_cash"], language, 1, "demo")
    baseline_memo = Path(run["output_dir"]) / "cnc-revision-000002.md"
    assert baseline["payload"]["stale_nodes"] == []
    assert baseline["payload"]["reviews"] == []
    assert (
        baseline["payload"]["nodes"]["forecast"]["citations"][0]["upstream_workflow_id"]
        == "treasury-forecast"
    )
    _complete_teaching_case(run, root)
    final = baseline
    final_memo = baseline_memo
    if phase == "practice":
        updates = list((tmp_path / "kit" / "files" / "practice").glob("*.md"))
        assert len(updates) == 1
        receipt = ledger.import_document(
            root,
            run["context"]["client_id"],
            run["context"]["engagement_id"],
            updates[0],
            "source",
        )["receipt"]
        input_ids.append(receipt["input_id"])
        run = _next_run(root, run, input_ids)
        update = node(
            "update", kind="document", content=updates[0].read_text(encoding="utf-8")
        )
        update["classification"] = "documented"
        update["citations"] = [
            {
                "binding_id": receipt["input_id"],
                "locator": "Complete fictional receipt update",
            }
        ]
        changed = _save(
            root,
            run,
            request(
                update,
                node(
                    "collection",
                    dependencies=("document", "update"),
                    content="2027-01-15; revised fictional receipt",
                ),
                revision=2,
                key="receipt-delay",
            ),
        )
        assert changed["payload"]["stale_nodes"] == ["forecast", "funding", "memo"]
        _complete_teaching_case(run, root)
        treasury, forecast = _forecast(root, run["context"], "practice", monkeypatch)
        assert forecast["minimum_daily_cash"] == "-30000.00"
        run = _next_run(root, run, input_ids, treasury)
        final = _draft(
            root, run, forecast["minimum_daily_cash"], language, 3, "practice"
        )
        final_memo = Path(run["output_dir"]) / "cnc-revision-000004.md"
        _complete_teaching_case(run, root)
        assert baseline_forecast.read_bytes() == baseline_bytes
        assert (
            final["payload"]["nodes"]["memo"]["version"]
            != baseline["payload"]["nodes"]["memo"]["version"]
        )
    resumed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            run["context_path"],
            "--resume",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    assert final["content_sha256"] in resumed.stderr
    assert final["payload"]["role"] == "advisor"
    assert final["payload"]["stale_nodes"] == []
    assert final["payload"]["reviews"] == []
    assert final["payload"]["nodes"]["missing_aging"]["classification"] == "missing"
    assert final["payload"]["external_action_authorized"] is False
    assert WORDS[language][1].format(
        cash=forecast["minimum_daily_cash"]
    ) in final_memo.read_text(encoding="utf-8")
    artifacts = [
        final_memo,
        Path(treasury["forecast_path"]),
        Path(run["output_dir"]) / f"workflow-revision-{final['revision']:06d}.json",
    ]
    (tmp_path / "lesson-evidence.json").write_text(
        json.dumps(
            {
                "language": language,
                "phase": phase,
                "artifacts": [
                    {
                        "name": path.name,
                        "path": str(path),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for path in artifacts
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow=cnc.WORKFLOW,
        language=language,
        phase=phase,
    )
