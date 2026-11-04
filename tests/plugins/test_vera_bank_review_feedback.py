"""Accounting review persists cases and reports actual application effects."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.plugins import test_journal_bank_reconciliation_plugin as bank

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
# Three maintained operations share one subprocess budget on CI runners.
REVIEW_BATCH_TIMEOUT_SECONDS = 30


@pytest.mark.parametrize("damage", [None, "code", "index", "missing"])
def test_updated_reviewer_uses_retained_code_only_for_verified_baseline(
    tmp_path: Path, damage: str | None
) -> None:
    """A new reviewer can apply without recalculating or rewriting old receipts."""
    output, intake, review, _, artifacts = bank._prepare_sealed_mcp_review_run(tmp_path)
    original = bank._tree_snapshot(output)
    copied, shared = bank._copy_journal_bank_implementation(tmp_path / "original")
    stage = tmp_path / "retained-stage"
    component = stage / "modules/journal-bank-reconciliation"
    shutil.copytree(copied, component)
    shutil.copytree(shared, component / "vendor/modules/vera_assurance")
    shutil.copytree(
        shared.parent / "vera_journal_pdf",
        component / "vendor/modules/vera_journal_pdf",
    )
    index = json.dumps(
        {
            "schema_version": 1,
            "files": {
                path.relative_to(stage)
                .as_posix(): hashlib.sha256(path.read_bytes())
                .hexdigest()
                for path in stage.rglob("*")
                if path.is_file()
            },
        }
    ).encode()
    digest = hashlib.sha256(index).hexdigest()
    (stage / "execution-files.json").write_bytes(index)
    runtime = tmp_path / "runtime"
    (runtime / "code").mkdir(parents=True)
    retained = runtime / "code" / digest
    stage.rename(retained)
    run_root = bank._customer_context_path(output).parent
    (run_root / "execution-runtime.json").write_text(
        json.dumps({"schema_version": 1, "package_sha256": digest})
    )
    active, _ = bank._copy_journal_bank_implementation(tmp_path / "updated")
    # Change current owned bytes between runs, never the historical receipt.
    server = active / "mcp/server.cjs"
    server.write_text(server.read_text() + "\n// Updated review presentation.\n")
    if damage == "code":
        (retained / "modules/journal-bank-reconciliation/mcp/server.cjs").write_text(
            "changed"
        )
    elif damage == "index":
        (retained / "execution-files.json").write_text("changed")
    elif damage == "missing":
        shutil.rmtree(retained)
    retained_before = bank._tree_snapshot(retained) if retained.exists() else {}
    decisions = [{"item_id": row["id"], "action": "accept"} for row in review["items"]]

    result = bank._call_mcp_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "apply_journal_bank_decisions",
                    "arguments": {
                        "run_intake": intake,
                        "review_payload": review,
                        "final_artifacts": artifacts,
                        "decisions": decisions,
                    },
                },
            }
        ],
        server_path=server,
        env={
            **os.environ,
            "PYTHON": sys.executable,
            "MPARANZA_RUNTIME_ROOT": str(runtime),
        },
    )[0]["result"]

    if damage:
        assert result["isError"] is True
        assert bank._tree_snapshot(output) == original
    else:
        assert result["isError"] is False, result
        applied = json.loads((output / "applied_decisions.json").read_text())
        assert applied["decision_count"] == applied["item_count"] == 3
        assert (output / "assurance_envelope.json").read_bytes() == original[
            "assurance_envelope.json"
        ][0]
        assert (output / "reconciliation_matches.csv").read_bytes() == original[
            "reconciliation_matches.csv"
        ][0]
        assert (output / "unmatched_bank.csv").read_bytes() == original[
            "unmatched_bank.csv"
        ][0]
        assert (output / "journal_bank_reconciliation.xlsx").read_bytes() == original[
            "journal_bank_reconciliation.xlsx"
        ][0]
    assert (
        bank._tree_snapshot(retained) if retained.exists() else {}
    ) == retained_before


@pytest.mark.parametrize("legacy", [False, True])
def test_accounting_population_excludes_files_and_preserves_open_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy: bool
) -> None:
    """Save/apply the same cases; never invent acceptance of technical files."""
    core = bank.load_core()
    writer = core.write_review_session_artifacts

    def old_writer(*args: Any, **kwargs: Any) -> Any:
        result = writer(*args, **kwargs)
        payload = json.loads(result.review_payload_path.read_text())
        payload["items"].extend(payload.pop("artifact_items"))
        payload["item_count"] = len(payload["items"])
        result.review_payload_path.write_text(json.dumps(payload))
        return dataclasses.replace(result, review_item_count=payload["item_count"])

    if legacy:
        monkeypatch.setattr(core, "write_review_session_artifacts", old_writer)
    monkeypatch.setattr(bank, "load_core", lambda: core)
    output, intake, review, _, artifacts = bank._prepare_sealed_mcp_review_run(tmp_path)
    original_payload = (output / "review_payload.json").read_bytes()
    original_unmatched = (output / "unmatched_bank.csv").read_bytes()
    original_matches = (output / "reconciliation_matches.csv").read_bytes()
    original_workbook = (output / "journal_bank_reconciliation.xlsx").read_bytes()
    cases = [
        row
        for row in review["items"]
        if row["item_type"] in {"matched_pair", "unmatched_bank", "unmatched_journal"}
    ]
    assert len(cases) == 3
    assert review["item_count"] > 3 if legacy else review["item_count"] == 3
    decisions = [
        (
            {
                "item_id": row["id"],
                "action": "request_more_documents",
                "requested_documents": ["Missing bank fee support"],
            }
            if row["item_type"] == "unmatched_bank"
            else {"item_id": row["id"], "action": "accept"}
        )
        for row in cases
    ]
    args = {
        "review_payload": review,
        "run_intake": intake,
        "final_artifacts": artifacts,
        "decisions": decisions,
    }

    responses = bank._call_mcp_server(
        [
            {
                "jsonrpc": "2.0",
                "id": index,
                "method": "tools/call",
                "params": {"name": name, "arguments": args},
            }
            for index, name in enumerate(
                [
                    "render_journal_bank_review",
                    "save_journal_bank_decisions",
                    "apply_journal_bank_decisions",
                ]
            )
        ],
        env={**os.environ, "PYTHON": sys.executable},
        timeout_seconds=REVIEW_BATCH_TIMEOUT_SECONDS,
    )

    rendered = responses[0]["result"]["_meta"]["private_review_payload"]
    assert rendered["review_payload"]["item_count"] == 3
    assert rendered["review_payload"]["artifact_items"]
    assert rendered["final_artifacts"]["outputs"] == artifacts["outputs"]
    assert responses[1]["result"]["isError"] is False
    assert responses[2]["result"]["isError"] is False, responses[2]
    saved = json.loads((output / "ui_decisions.json").read_text())
    applied = json.loads((output / "applied_decisions.json").read_text())
    assert saved["decision_count"] == saved["item_count"] == 3
    assert saved["status"] == "reviewed"
    assert applied["decision_count"] == applied["item_count"] == 3
    assert applied["blocker_count"] == 1
    assert applied["application_status"] == "blocked"
    assert applied["target_update_count"] == applied["native_regeneration_count"] == 0
    assert (output / "review_payload.json").read_bytes() == original_payload
    assert (output / "unmatched_bank.csv").read_bytes() == original_unmatched
    assert (output / "reconciliation_matches.csv").read_bytes() == original_matches
    assert (
        output / "journal_bank_reconciliation.xlsx"
    ).read_bytes() == original_workbook
    assert (
        json.loads((output / "assurance_gates.json").read_text())["report_ready"]
        is False
    )


def render_review(
    *,
    action: str | None = None,
    fail_save: bool = False,
    applied: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Exercise the shipped JS through real buttons and a synthetic host."""
    item = {
        "id": "fee",
        "item_type": "unmatched_bank",
        "title": "Commissione €5",
        "status": "needs_review",
        "allowed_actions": ["accept", "request_more_documents"],
        "data": {
            "description": "Commissione",
            "bank_amount": -5,
            "currency": "EUR",
            "journal_amount": None,
            "amount_delta": 5,
        },
    }
    fixture = {
        "action": action,
        "fail_save": fail_save,
        "catalogue": {
            "works": [
                {
                    "work_ref": "retained-work",
                    "label": "Test 1",
                    "workflow": "journal-bank-reconciliation",
                }
            ]
        },
        "review": {
            "kind": "workbench",
            "workflow": "journal-bank-reconciliation",
            "work_ref": "retained-work",
            "label": "Test 1",
            "run_status": "running",
            "revision": "saved-revision",
            "review_ticket": "ticket",
            "items": [item],
            "total": 1,
            "offset": 0,
            "data": {
                "adapter": {
                    "detailGroups": [
                        {"title": "Journal Entry", "fields": ["journal_amount"]},
                        {"title": "Bank Statement", "fields": ["bank_amount"]},
                        {"title": "Match Result", "fields": ["amount_delta"]},
                    ]
                },
                "ui_decisions": {
                    "decisions": [
                        {
                            "item_id": "fee",
                            "action": "request_more_documents",
                            "status": "needs_evidence",
                            "reviewer_note": "Agent review",
                            "requested_documents": ["Supporto commissione"],
                        }
                    ]
                },
                "applied_decisions": applied,
            },
        },
    }
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(
        [
            node,
            str(ROOT / "tests/plugins/archive_run_list_ui.cjs"),
            str(ROOT / "plugins/vera/ui/workspace.js"),
            "review",
        ],
        input=json.dumps(fixture),
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    return json.loads(result.stdout)


def test_saved_decision_reopens_with_italian_groups_and_requested_documents() -> None:
    result = render_review(action="Salva decisione")

    assert "Decisione salvata · Richiedi documenti" in result["text"]
    assert "Scrittura contabile" not in result["text"]
    assert "Nessuna scrittura corrispondente nel giornale fornito." in result["text"]
    assert "Movimento bancario" in result["text"]
    assert "Esito del confronto" in result["text"]
    assert "Journal Entry" not in result["text"]
    assert result["selectedTitle"] == "Commissione · -5,00 EUR"
    assert {"label": "Documenti richiesti", "value": "Supporto commissione"} in result[
        "fields"
    ]
    saved = next(
        call for call in result["calls"] if call["name"] == "vera_workspace_save"
    )
    assert saved["arguments"]["decisions"][0]["requested_documents"] == [
        "Supporto commissione"
    ]
    assert result["status"] == "Decisione salvata. Stato riletto dal lavoro."


@pytest.mark.parametrize(
    ("applied", "expected"),
    [
        (
            {
                "decision_count": 3,
                "item_count": 3,
                "blocker_count": 1,
                "target_update_count": 0,
                "native_regeneration_count": 0,
            },
            "File aggiornati: 0. File rigenerati: 0.",
        ),
        (
            {
                "decision_count": 3,
                "item_count": 3,
                "blocker_count": 1,
                "target_update_count": 1,
                "native_regenerated_paths": ["workbook.xlsx"],
            },
            "File aggiornati: 1. File rigenerati: 1.",
        ),
        (None, "L’esito dell’applicazione non è disponibile"),
    ],
)
def test_apply_reports_persisted_effects_without_assuming_regeneration(
    applied: dict[str, Any] | None, expected: str
) -> None:
    result = render_review(action="Applica revisione", applied=applied)

    assert expected in result["status"]
    assert result["selectedTitle"] == "Commissione · -5,00 EUR"


def test_failed_save_does_not_report_success_or_reload_selection() -> None:
    result = render_review(action="Salva decisione", fail_save=True)

    assert result["status"] == "Draft write failed"
    assert result["selectedTitle"] == "Commissione · -5,00 EUR"
    assert result["calls"][-1]["name"] == "vera_workspace_save"


@pytest.mark.parametrize(
    "message",
    [
        "PermissionError: Run is not authorised in this workspace",
        "The saved connection is unavailable",
    ],
)
def test_failed_saved_card_can_return_to_authorized_directory(message: str) -> None:
    node = shutil.which("node")
    assert node is not None
    fixture = {
        "error": message,
        "catalogue": {
            "works": [
                {
                    "work_ref": "authorized-work",
                    "label": "Authorized synthetic work",
                    "workflow": "journal-bank-reconciliation",
                }
            ]
        },
    }
    completed = subprocess.run(
        [
            node,
            str(ROOT / "tests/plugins/archive_run_list_ui.cjs"),
            str(ROOT / "plugins/vera/ui/workspace.js"),
            "recovery",
        ],
        input=json.dumps(fixture),
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    result = json.loads(completed.stdout)
    assert result["before"]["buttons"] == ["Torna ai lavori autorizzati"]
    assert result["calls"] == [{"name": "vera_workspace_open", "arguments": {}}]
    assert "Authorized synthetic work" in result["text"]
    assert result["status"] == "Scegli un lavoro collegato a Studio Archive."
    if "PermissionError" in message:
        assert "PermissionError" not in result["before"]["status"]
        assert "connessione corrente" in result["before"]["status"]
