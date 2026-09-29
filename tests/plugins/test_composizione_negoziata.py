from __future__ import annotations

import copy
import csv
import importlib.util
import json
import runpy
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.model_data_helpers import write_no_model_report

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/composizione-negoziata/scripts/cnc_case.py"
for directory in (
    ROOT / "plugins/_shared/vendor/modules",
    ROOT / "plugins/studio-archive/scripts",
):
    sys.path.insert(0, str(directory))
import client_ledger as ledger  # noqa: E402

SPEC = importlib.util.spec_from_file_location("cnc_test", SCRIPT)
assert SPEC and SPEC.loader
cnc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cnc)


def test_declared_dependency_check_runs_without_third_party_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    monkeypatch.setattr(sys, "argv", ["check_dependencies.py"])

    with pytest.raises(SystemExit) as result:
        runpy.run_path(
            str(SCRIPT.parent / "check_dependencies.py"), run_name="__main__"
        )

    assert result.value.code == 0


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    # Repository import isolation can evict modules; keep one ledger and lock map.
    monkeypatch.setitem(sys.modules, "client_ledger", ledger)
    root = tmp_path / "Cliente sintetico"
    root.mkdir()
    client_id = "client_" + "1" * 24
    ledger.create_client_manifest(root, client_id)
    engagement = ledger.create_engagement(root, client_id, "CNC advisor")
    engagement_id = engagement["engagement_id"]
    source = tmp_path / "incassi.txt"
    source.write_text(
        "Incasso 100000 EUR previsto a novembre; conferma del debitore assente."
    )
    receipt = ledger.import_document(root, client_id, engagement_id, source, "source")[
        "receipt"
    ]
    prepared = ledger.prepare_run(
        root,
        client_id,
        engagement_id,
        cnc.WORKFLOW,
        "0.1.0",
        input_ids=[receipt["input_id"]],
    )
    started = ledger.start_run(root, engagement_id, prepared["run"]["run_id"])
    return SimpleNamespace(
        root=root,
        client_id=client_id,
        engagement_id=engagement_id,
        receipt=receipt,
        run=started,
        context=Path(started["context_path"]),
    )


def node(
    identifier: str,
    *,
    kind: str = "assumption",
    dependencies: tuple[str, ...] = (),
    content: str = "Ipotesi da verificare",
) -> dict:
    return {
        "id": identifier,
        "kind": kind,
        "title": identifier,
        "content": content,
        "classification": "assumed",
        "depends_on": list(dependencies),
        "citations": [],
        "responsibility": "advisor",
        "source": None,
    }


def request(*nodes: dict, revision: int = 0, key: str = "intake") -> dict:
    return {
        "expected_revision": revision,
        "idempotency_key": key,
        "role": "advisor",
        "stage": "Valutazione iniziale",
        "change_reason": "Nuove evidenze selezionate",
        "next_action": {
            "task": "Verificare gli incassi",
            "why": "Manca conferma",
            "capability": "treasury-forecast",
            "output": "Forecast da riesaminare",
            "decision": "Confermare le ipotesi",
        },
        "upsert_nodes": list(nodes),
        "reviews": [],
    }


def initial(case: SimpleNamespace) -> dict:
    evidence = node(
        "document",
        kind="document",
        content="Il debitore non ha confermato il pagamento.",
    )
    evidence["classification"] = "documented"
    evidence["citations"] = [
        {"binding_id": case.receipt["input_id"], "locator": "riga 1"}
    ]
    return request(
        evidence,
        node(
            "collection",
            dependencies=("document",),
            content="Incasso ipotizzato a novembre",
        ),
        node("forecast", kind="analysis", dependencies=("collection",)),
        node("funding", kind="analysis", dependencies=("forecast",)),
        node(
            "proposal",
            kind="draft",
            dependencies=("funding",),
            content="Bozza: i pagamenti proposti dipendono dalla verifica degli incassi.",
        ),
        node(
            "missing_aging",
            kind="gap",
            content="Scadenzario mancante; non è sostituito con zero.",
        ),
    )


def close_run(case: SimpleNamespace) -> None:
    output = Path(case.run["output_dir"])
    declarations = [
        {
            "artifact_id": path.stem,
            "path": path.name,
            "purpose": "Synthetic CNC snapshot",
            "audience": "review",
            "media_type": "application/json",
        }
        for path in output.glob("*.json")
    ]
    declarations += write_no_model_report(
        output, cnc.WORKFLOW, case.run["run"]["run_id"]
    )
    ledger.finalize_run(
        case.root, case.engagement_id, case.run["run"]["run_id"], declarations
    )
    ledger.complete_run(case.root, case.engagement_id, case.run["run"]["run_id"])


def test_receipt_delay_invalidates_transitive_outputs_and_prior_review(
    case: SimpleNamespace,
) -> None:
    saved = cnc.apply_request(case.context, initial(case))
    review = request(revision=1, key="review")
    review["reviews"] = [
        {
            "node_id": "proposal",
            "node_version": saved["payload"]["nodes"]["proposal"]["version"],
            "reviewer_ref": "synthetic-professional",
            "confirmation_ref": "synthetic-user-confirmation",
            "decision": "accepted",
            "reason": "Assumption-dependent draft reviewed",
        }
    ]
    cnc.apply_request(case.context, review)

    changed = cnc.apply_request(
        case.context,
        request(
            node(
                "collection",
                dependencies=("document",),
                content="Incasso rinviato a gennaio",
            ),
            revision=2,
            key="delay",
        ),
    )

    assert changed["payload"]["stale_nodes"] == ["forecast", "funding", "proposal"]
    assert (
        saved["payload"]["nodes"]["collection"]["content"]
        == "Incasso ipotizzato a novembre"
    )
    assert "storica: nuova revisione necessaria" in cnc.render_record(changed)
    assert (
        changed["payload"]["reviews"][0]["authority"]
        == "record_only_identity_not_verified"
    )
    assert "missing_aging" not in changed["payload"]["stale_nodes"]


def test_identical_retry_preserves_revision_and_changed_retry_fails(
    case: SimpleNamespace,
) -> None:
    update = initial(case)
    saved = cnc.apply_request(case.context, update)

    repeated = cnc.apply_request(case.context, update)

    assert repeated == saved
    changed = copy.deepcopy(update)
    changed["stage"] = "Different intent"
    with pytest.raises(ledger.LedgerError, match="retry key"):
        cnc.apply_request(case.context, changed)


@pytest.mark.parametrize(
    "change,pattern",
    [
        ({"role": "esperto"}, "Role is fixed"),
        ({"expected_revision": 0}, "Stale workflow revision"),
        ({"production_approved": True}, "exactly"),
    ],
)
def test_invalid_case_updates_do_not_write(
    case: SimpleNamespace, change: dict, pattern: str
) -> None:
    cnc.apply_request(case.context, initial(case))
    update = request(revision=1, key="change")
    update.update(change)

    with pytest.raises((ValueError, ledger.LedgerError), match=pattern):
        cnc.apply_request(case.context, update)

    assert (
        len(ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW))
        == 1
    )


@pytest.mark.parametrize("dependencies", [("absent",), ("cycle",)])
def test_unknown_or_cyclic_dependencies_are_rejected(
    case: SimpleNamespace, dependencies: tuple[str, ...]
) -> None:
    update = request(node("cycle", dependencies=dependencies))

    with pytest.raises(ValueError, match="cycle or unknown"):
        cnc.apply_request(case.context, update)


def test_foreign_input_reference_is_rejected(case: SimpleNamespace) -> None:
    update = initial(case)
    update["upsert_nodes"][0]["citations"][0]["binding_id"] = "input_" + "f" * 24

    with pytest.raises(ValueError, match="bound to this managed run"):
        cnc.apply_request(case.context, update)


def test_changed_input_bytes_reject_resume(case: SimpleNamespace) -> None:
    cnc.apply_request(case.context, initial(case))
    imported = Path(case.receipt["path"])
    imported.write_text("Changed without an archive import")

    with pytest.raises(ledger.LedgerError, match="no longer matches"):
        ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW)


def test_resume_from_fresh_process_and_successor_run_preserves_case(
    case: SimpleNamespace,
) -> None:
    saved = cnc.apply_request(case.context, initial(case))
    close_run(case)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            str(case.context),
            "--resume",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert saved["content_sha256"] in result.stderr
    assert "Scadenzario mancante" in result.stderr
    successor = ledger.prepare_run(
        case.root,
        case.client_id,
        case.engagement_id,
        cnc.WORKFLOW,
        "0.1.0",
        input_ids=[case.receipt["input_id"]],
        new_run=True,
    )
    ledger.start_run(case.root, case.engagement_id, successor["run"]["run_id"])
    next_snapshot = cnc.apply_request(
        Path(successor["context_path"]), request(revision=1, key="reopen")
    )
    assert next_snapshot["previous_sha256"] == saved["content_sha256"]
    assert next_snapshot["payload"]["nodes"] == saved["payload"]["nodes"]


def test_concurrent_different_updates_commit_only_one_revision(
    case: SimpleNamespace,
) -> None:
    def apply(key: str) -> str:
        try:
            cnc.apply_request(case.context, request(node(key), key=key))
            return "saved"
        except (ValueError, ledger.LedgerError) as exc:
            if "Stale workflow revision" not in str(exc):
                raise
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(apply, ("first", "second")))

    assert sorted(outcomes) == ["saved", "stale"]
    assert (
        len(ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW))
        == 1
    )


def test_stale_output_cannot_receive_new_review(case: SimpleNamespace) -> None:
    first = cnc.apply_request(case.context, initial(case))
    cnc.apply_request(
        case.context,
        request(node("collection", content="Gennaio"), revision=1, key="delay"),
    )
    update = request(revision=2, key="review")
    update["reviews"] = [
        {
            "node_id": "proposal",
            "node_version": first["payload"]["nodes"]["proposal"]["version"],
            "reviewer_ref": "professional",
            "confirmation_ref": "user-message",
            "decision": "accepted",
            "reason": "Review",
        }
    ]

    with pytest.raises(ValueError, match="current exact node version"):
        cnc.apply_request(case.context, update)


def test_expert_draft_cannot_be_attributed_to_advisor(case: SimpleNamespace) -> None:
    draft = node("expert_report", kind="draft")
    draft["responsibility"] = "esperto"

    with pytest.raises(ValueError, match="other professional role"):
        cnc.apply_request(case.context, request(draft))


def test_closed_run_cannot_be_modified(case: SimpleNamespace) -> None:
    cnc.apply_request(case.context, initial(case))
    close_run(case)

    with pytest.raises(ValueError, match="running"):
        cnc.apply_request(case.context, request(revision=1, key="late"))


@pytest.mark.parametrize("existing_memo", [False, True])
def test_cli_retry_repairs_missing_memo_without_duplicating_revision(
    case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, existing_memo: bool
) -> None:
    update = initial(case)
    saved = cnc.apply_request(case.context, update)
    output = Path(case.run["output_dir"])
    memo = output / "cnc-revision-000001.md"
    if existing_memo:
        memo.write_text(cnc.render_record(saved), encoding="utf-8")
    request_path = output / "request.json"
    request_path.write_text(json.dumps(update), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--client-engagement",
            str(case.context),
            "--request",
            str(request_path),
        ],
    )

    result = cnc.main()

    assert result == 0
    assert memo.read_text(encoding="utf-8") == cnc.render_record(saved)
    assert (
        len(ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW))
        == 1
    )


def test_cli_retry_refuses_to_replace_conflicting_memo(
    case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    update = initial(case)
    cnc.apply_request(case.context, update)
    output = Path(case.run["output_dir"])
    memo = output / "cnc-revision-000001.md"
    original = "Modifica del professionista da conservare"
    memo.write_text(original, encoding="utf-8")
    request_path = output / "request.json"
    request_path.write_text(json.dumps(update), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--client-engagement",
            str(case.context),
            "--request",
            str(request_path),
        ],
    )

    with pytest.raises(ValueError, match="do not overwrite"):
        cnc.main()

    assert memo.read_text(encoding="utf-8") == original


def test_cli_resume_reads_completed_case_with_source_limits(
    case: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = node(
        "public_source",
        kind="source",
        content="Fonte sintetica; testo normativo completo non verificato",
    )
    source["source"] = {
        "url": "https://example.org/synthetic-source",
        "kind": "synthetic",
        "checked_on": "2026-09-29",
        "applicable_on": "da verificare",
        "inspected_scope": "Solo estratto sintetico",
        "limitations": "Non prova la disciplina vigente",
    }
    cnc.apply_request(case.context, request(source))
    close_run(case)
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT), "--client-engagement", str(case.context), "--resume"]
    )
    caplog.set_level("INFO")

    result = cnc.main()

    assert result == 0
    assert "Solo estratto sintetico" in caplog.text
    assert "Non prova la disciplina vigente" in caplog.text
    assert (
        len(ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW))
        == 1
    )


def test_saved_snapshot_tampering_is_detected_before_resume(
    case: SimpleNamespace,
) -> None:
    cnc.apply_request(case.context, initial(case))
    path = Path(case.run["output_dir"]) / "workflow-revision-000001.json"
    altered = json.loads(path.read_text(encoding="utf-8"))
    altered["payload"]["role"] = "esperto"
    path.write_text(json.dumps(altered), encoding="utf-8")

    with pytest.raises(
        ledger.LedgerError,
        match="digest|seal|integrity",
    ):
        ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW)


def test_regenerated_outputs_bind_new_versions_without_inheriting_reviews(
    case: SimpleNamespace,
) -> None:
    first = cnc.apply_request(case.context, initial(case))
    cnc.apply_request(
        case.context,
        request(
            node("collection", content="Incasso a gennaio"), revision=1, key="delay"
        ),
    )
    update = request(
        node(
            "forecast",
            kind="analysis",
            dependencies=("collection",),
            content="Forecast ricalcolato con incasso a gennaio",
        ),
        node("funding", kind="analysis", dependencies=("forecast",)),
        node(
            "proposal",
            kind="draft",
            dependencies=("funding",),
            content="Nuova proposta da sottoporre al professionista",
        ),
        revision=2,
        key="recalculate",
    )

    regenerated = cnc.apply_request(case.context, update)

    assert regenerated["payload"]["stale_nodes"] == []
    assert (
        regenerated["payload"]["nodes"]["proposal"]["version"]
        != first["payload"]["nodes"]["proposal"]["version"]
    )
    assert regenerated["payload"]["reviews"] == []


def test_expert_case_records_unresolved_independence_without_assuming_acceptance(
    case: SimpleNamespace,
) -> None:
    update = request(
        node(
            "independence",
            kind="question",
            content="Precedente incarico da verificare prima dell'accettazione",
        )
    )
    update["role"] = "esperto"
    update["upsert_nodes"][0]["responsibility"] = "esperto"

    saved = cnc.apply_request(case.context, update)

    assert saved["payload"]["role"] == "esperto"
    assert saved["payload"]["reviews"] == []
    assert saved["payload"]["external_action_authorized"] is False


def test_actual_treasury_cli_output_is_bound_into_cnc_draft(
    case: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    treasury = ROOT / "plugins/treasury-forecast/scripts"
    monkeypatch.syspath_prepend(str(treasury))
    from treasury_inputs import HEADERS
    from treasury_session import current_record

    staging = tmp_path / "treasury"
    staging.mkdir()
    tables = {name: [] for name in HEADERS}
    tables["accounts"] = [{"account_id": "bank", "balance": "50000.00"}]
    tables["planned_flows"] = [
        {
            "flow_id": "receipt",
            "side": "receivable",
            "amount": "100000.00",
            "expected_date": "2026-11-15",
            "description": "Incasso previsto",
            "basis": "Ipotesi sintetica esplicita",
        },
        {
            "flow_id": "payment",
            "side": "payable",
            "amount": "80000.00",
            "expected_date": "2026-11-30",
            "description": "Pagamento previsto",
            "basis": "Impegno sintetico esplicito",
        },
    ]
    manifest = {
        "schema_version": "vera.treasury_manifest.v1",
        "company_id": "synthetic-cnc",
        "company_name": "Società sintetica CNC",
        "currency": "EUR",
        "as_of": "2026-10-31",
        "horizon_end": "2027-01-31",
        "coverage": "Due flussi sintetici; nessuna completezza aziendale dichiarata",
        "tables": {},
        "invoice_files": [],
        "previous": None,
    }
    inputs = []
    for name, headers in HEADERS.items():
        path = staging / f"{name}.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(tables[name])
        receipt = ledger.import_document(
            case.root, case.client_id, case.engagement_id, path, "source"
        )["receipt"]
        inputs.append(receipt["input_id"])
        manifest["tables"][name] = {
            "path": f"imports/{receipt['input_id']}/{Path(receipt['relative_path']).name}"
        }
    manifest_path = staging / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    inputs.append(
        ledger.import_document(
            case.root, case.client_id, case.engagement_id, manifest_path, "source"
        )["receipt"]["input_id"]
    )
    run = ledger.prepare_run(
        case.root,
        case.client_id,
        case.engagement_id,
        "treasury-forecast",
        "0.1.0",
        input_ids=inputs,
    )
    run = ledger.start_run(case.root, case.engagement_id, run["run"]["run_id"])
    bound_manifest = next(
        row["path"]
        for row in run["context"]["input_bindings"]
        if row["path"].endswith("manifest.json")
    )
    execution = subprocess.run(
        [
            sys.executable,
            str(treasury / "run_treasury.py"),
            "prepare",
            "--client-engagement",
            run["context_path"],
            "--manifest",
            bound_manifest,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert execution.returncode == 0, execution.stderr
    output = Path(run["output_dir"])
    _, forecast = current_record(output)
    assert forecast["minimum_daily_cash"] == "50000.00"
    write_no_model_report(output, "treasury-forecast", run["run"]["run_id"])
    declarations = [
        {
            "artifact_id": (
                "forecast" if path.name == "forecast.json" else f"support-{index}"
            ),
            "path": path.relative_to(output).as_posix(),
            "purpose": "Synthetic treasury result",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(
            sorted(path for path in output.rglob("*") if path.is_file())
        )
    ]
    ledger.finalize_run(
        case.root, case.engagement_id, run["run"]["run_id"], declarations
    )
    ledger.complete_run(case.root, case.engagement_id, run["run"]["run_id"])
    cnc_run = ledger.prepare_run(
        case.root,
        case.client_id,
        case.engagement_id,
        cnc.WORKFLOW,
        "0.1.0",
        upstream_artifacts=[
            {
                "run_id": run["run"]["run_id"],
                "artifact_id": "forecast",
                "role": "source",
            }
        ],
    )
    cnc_run = ledger.start_run(case.root, case.engagement_id, cnc_run["run"]["run_id"])
    analysis = node(
        "treasury",
        kind="analysis",
        content="Tesoreria sintetica: cassa minima EUR 50.000; incasso di novembre ipotizzato, non confermato.",
    )
    analysis["classification"] = "calculated"
    analysis["citations"] = [
        {
            "binding_id": cnc_run["context"]["input_bindings"][0]["binding_id"],
            "locator": "minimum_daily_cash; events",
        }
    ]
    update = request(
        analysis,
        node(
            "memo",
            kind="draft",
            dependencies=("treasury",),
            content="Prima di formulare proposte verificare l'incasso di novembre e simulare il rinvio a gennaio.",
        ),
    )
    update_path = Path(cnc_run["output_dir"]) / "request.json"
    update_path.write_text(json.dumps(update))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            cnc_run["context_path"],
            "--request",
            str(update_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    saved = ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW)[
        -1
    ]
    assert (
        saved["payload"]["nodes"]["treasury"]["citations"][0]["upstream_workflow_id"]
        == "treasury-forecast"
    )
    assert (
        "simulare il rinvio a gennaio"
        in (Path(cnc_run["output_dir"]) / "cnc-revision-000001.md").read_text()
    )
