"""Full synthetic CNC journeys; financial execution is real, judgments are fixtures."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_composizione_negoziata import (
    SCRIPT,
    case,
    cnc,
    initial,
    ledger,
    node,
    request,
)
from tests.plugins.test_teaching_cnc_execution import _forecast, _next_run
from tests.plugins.test_teaching_kit_execution import _complete_teaching_case


def save(run, update, role):
    update["role"] = role
    for value in update["upsert_nodes"]:
        value["responsibility"] = role
    path = Path(run["output_dir"]) / f"request-{update['idempotency_key']}.json"
    path.write_text(json.dumps(update, ensure_ascii=False), encoding="utf-8")
    execution = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            run["context_path"],
            "--request",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert execution.returncode == 0, execution.stderr
    return json.loads(
        (
            Path(run["output_dir"])
            / f"workflow-revision-{update['expected_revision'] + 1:06d}.json"
        ).read_text()
    )


def financial_node(run, cash):
    result = node(
        "forecast",
        kind="analysis",
        dependencies=("collection",),
        content=f"Cassa minima calcolata EUR {cash}; il credito resta da verificare.",
    )
    result["classification"] = "calculated"
    binding = next(
        item
        for item in run["context"]["input_bindings"]
        if item.get("upstream_workflow_id") == "treasury-forecast"
    )
    result["citations"] = [
        {"binding_id": binding["binding_id"], "locator": "minimum_daily_cash"}
    ]
    return result


@pytest.mark.parametrize("role", ["advisor", "esperto"])
def test_both_roles_execute_forecast_revise_and_deliver_negative_outcome(
    case, monkeypatch, tmp_path, role
):
    update = initial(case)
    update["upsert_nodes"] = [
        value
        for value in update["upsert_nodes"]
        if value["id"] in {"document", "collection", "missing_aging"}
    ]
    update["upsert_nodes"][-1]["classification"] = "missing"
    save(case.run, update, role)
    _complete_teaching_case(case.run, case.root)
    treasury, baseline = _forecast(case.root, case.run["context"], "demo", monkeypatch)
    assert baseline["minimum_daily_cash"] == "50000.00"
    inputs = [case.receipt["input_id"]]
    run = _next_run(case.root, case.run, inputs, treasury)
    proposal = node(
        "proposal",
        kind="draft",
        dependencies=("forecast",),
        content=(
            "Advisor: proposta condizionata alla conferma dell'incasso."
            if role == "advisor"
            else "Esperto: quesiti neutrali alle parti sulla prova e tempistica dell'incasso; nessuna strategia di parte."
        ),
    )
    first = save(
        run,
        request(financial_node(run, "50000.00"), proposal, revision=1, key="baseline"),
        role,
    )
    _complete_teaching_case(run, case.root)
    event_path = tmp_path / "new-evidence.txt"
    event_path.write_text(
        "Caso fittizio: il debitore comunica il rinvio dell'incasso al 15 gennaio 2027. Il creditore rifiuta la proposta e non risultano altri accordi. Nessuna ricevuta di deposito è fornita.",
        encoding="utf-8",
    )
    receipt = ledger.import_document(
        case.root, case.client_id, case.engagement_id, event_path, "source"
    )["receipt"]
    inputs.append(receipt["input_id"])
    run = _next_run(case.root, run, inputs)
    event = node("new_evidence", kind="document", content=event_path.read_text())
    event["classification"] = "documented"
    event["citations"] = [
        {"binding_id": receipt["input_id"], "locator": "Intero documento sintetico"}
    ]
    changed = save(
        run,
        request(
            event,
            node(
                "collection",
                dependencies=("document", "new_evidence"),
                content="Incasso rinviato al 15 gennaio 2027; recuperabilità ancora da verificare",
            ),
            revision=2,
            key="new-evidence",
        ),
        role,
    )
    assert changed["payload"]["stale_nodes"] == ["forecast", "proposal"]
    _complete_teaching_case(run, case.root)
    treasury, revised = _forecast(case.root, run["context"], "practice", monkeypatch)
    assert revised["minimum_daily_cash"] == "-30000.00"
    run = _next_run(case.root, run, inputs, treasury)
    outcome = node(
        "negotiation_outcome",
        kind="fact",
        dependencies=("new_evidence",),
        content="Il creditore ha rifiutato la proposta; non risultano accordi dalle evidenze selezionate.",
    )
    outcome["classification"] = "documented"
    proposal = node(
        "proposal",
        kind="draft",
        dependencies=("forecast", "negotiation_outcome"),
        content="La precedente proposta deve essere riconsiderata: fabbisogno minimo EUR 30000; nessuna copertura impegnata documentata. Valutare alternative senza modificare le ipotesi per ottenere un esito positivo.",
    )
    report = node(
        "final_report",
        kind="draft",
        dependencies=("forecast", "negotiation_outcome", "proposal", "missing_aging"),
        content=(
            "Relazione all'impresa e handoff dell'advisor."
            if role == "advisor"
            else "Relazione finale in bozza dell'esperto indipendente: verifiche, interlocuzioni ed esito negativo; nessuna assunzione del ruolo di advisor."
        )
        + "\nLa tesoreria è stata eseguita in due run: il minimo passa da EUR 50000 a EUR -30000 dopo il rinvio. Il creditore rifiuta e non risultano accordi. Mancano aging, riscontro della recuperabilità e ricevute degli adempimenti. Le prospettive devono essere rivalutate dal professionista, con ricerca aggiornata sulle alternative. Firma, deposito e chiusura giuridica non attestati.",
    )
    closing = request(
        financial_node(run, "-30000.00"),
        outcome,
        proposal,
        report,
        revision=3,
        key="handoff",
    )
    closing["stage"] = "Esito negativo: relazione e attività residue da rivedere"
    closing["next_action"] = {
        "task": "Rivedere la relazione e verificare alternative e adempimenti",
        "why": "Mancano accordo, copertura e ricevute",
        "capability": "quesito-legale-fiscale",
        "output": "Handoff con fonti attuali e questioni aperte",
        "decision": "Il professionista decide esito e seguito pertinenti al proprio ruolo",
    }
    closing["closure"] = {
        "outcome": "no_agreement",
        "report_id": "final_report",
        "basis_ids": ["forecast", "negotiation_outcome"],
        "receipt_ids": [],
        "residual_tasks": [
            {
                "node_id": "missing_aging",
                "owner": "Professionista sintetico",
                "due_basis": "Da concordare; nessun termine giuridico presunto",
            }
        ],
    }
    final = save(run, closing, role)
    _complete_teaching_case(run, case.root)
    resume = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            run["context_path"],
            "--resume",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resume.returncode == 0, resume.stderr
    assert "Esito proposto: no_agreement" in resume.stderr
    assert "-30000.00" in resume.stderr
    assert final["payload"]["role"] == role
    assert final["payload"]["stale_nodes"] == []
    assert cnc.closure_status(final["payload"]) == "draft_handoff"
    assert final["payload"]["reviews"] == []
    assert first["payload"]["nodes"]["forecast"]["content"].startswith(
        "Cassa minima calcolata EUR 50000.00"
    )
    assert (
        ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW)[0][
            "payload"
        ]["nodes"]["collection"]["content"]
        == "Incasso ipotizzato a novembre"
    )
    assert (
        final["payload"]["nodes"]["forecast"]["citations"][0]["upstream_workflow_id"]
        == "treasury-forecast"
    )
