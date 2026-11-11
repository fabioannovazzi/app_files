"""Posting review regressions: edits must drive the TXT; proposals are not approval."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "posting_review_tested", ROOT / "plugins/vera/scripts/native_posting_review.py"
)
posting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(posting)


@pytest.fixture
def review(tmp_path):
    batch = {
        "company": "78",
        "bank_account": "2405001",
        "notice": "Fictional test, no professional approval",
        "items": [
            {
                "id": "B001",
                "title": "Fictional payment",
                "bank": {
                    "amount": "-100.00",
                    "date": "2026-09-01",
                    "description": "Fictional supplier",
                },
                "proposed_lines": [
                    {
                        "account": "4000001",
                        "side": "D",
                        "amount": "100.00",
                        "partita": "",
                        "year": "",
                        "section": "",
                    }
                ],
                "reason": "Unreviewed proposal",
                "evidence": "fictional source",
            },
            {
                "id": "B002",
                "title": "Unresolved",
                "bank": {
                    "amount": "10.00",
                    "date": "2026-09-02",
                    "description": "Fictional receipt",
                },
                "proposed_lines": [],
                "reason": "Unknown account",
                "evidence": "fictional source",
            },
        ],
    }
    posting.prepare(tmp_path, batch, run_id="fictional", source_sha256="a" * 64)
    return tmp_path


def decision(account="4000002", amount="100.00", **extra):
    return {
        "status": "accepted",
        "lines": [
            {
                "account": account,
                "side": "D",
                "amount": amount,
                "partita": "",
                "year": "",
                "section": "",
            }
        ],
        "note": "Actual test operator correction",
        **extra,
    }


def test_proposals_never_export_without_decisions(review):
    with pytest.raises(ValueError, match="No accepted"):
        posting.export_reviewed(review)
    assert posting.projection(review, {})["data"]["counts"] == {
        "pending": 2,
        "accepted": 0,
        "rejected": 0,
    }


def test_txt_consumes_corrected_account_and_lists_pending(review):
    posting.save_decision(review, "B001", decision(), actor="fictional-reviewer")
    result = posting.export_reviewed(review)
    raw = (review / result["file"]).read_bytes()
    assert raw[1036:1043] == b"4000002"
    assert raw[6963:6964] == b"N"
    assert len(raw) == 7001
    assert result["records"] == 1 and result["excluded"] == [
        {"id": "B002", "status": "pending"}
    ]
    assert (
        posting.load(review)[0]["batch"]["items"][0]["proposed_lines"][0]["account"]
        == "4000001"
    )


def test_changed_decision_invalidates_current_export_preserving_history(review):
    posting.save_decision(review, "B001", decision(), actor="fictional-reviewer")
    previous = posting.export_reviewed(review)
    posting.save_decision(
        review,
        "B001",
        {"status": "rejected", "lines": [], "note": "Rejected"},
        actor="fictional-reviewer",
    )
    assert "last_export" not in posting.load(review)[1]
    assert len(posting.load(review)[1]["history"]) == 2
    assert (review / previous["file"]).exists()
    with pytest.raises(ValueError, match="No accepted"):
        posting.export_reviewed(review)


def test_unbalanced_acceptance_is_refused_but_draft_can_be_saved(review):
    with pytest.raises(ValueError, match="balance"):
        posting.save_decision(
            review, "B001", decision(amount="99.00"), actor="fictional-reviewer"
        )
    draft = decision(amount="99.00")
    draft["status"] = "pending"
    posting.save_decision(review, "B001", draft, actor="fictional-reviewer")
    assert posting.load(review)[1]["decisions"]["B001"]["status"] == "pending"


def test_valid_partita_needs_no_extra_acknowledgement(review):
    data = decision()
    data["lines"][0].update(partita="350", year="2026", section="00")
    posting.save_decision(review, "B001", data, actor="fictional-reviewer")
    result = posting.export_reviewed(review)
    raw = (review / result["file"]).read_bytes()
    assert raw[1074:1080] == b"000350" and raw[1080:1084] == b"2026"
    assert raw[6963:6964] == b" "


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "0.001", 1.1, True])
def test_non_cent_and_non_exact_values_are_rejected(amount):
    with pytest.raises(ValueError):
        posting.cents(amount)


def test_native_snapshot_uses_posting_adapter_and_detects_stale_state(
    review, monkeypatch
):
    import sys

    sys.path.insert(0, str(ROOT / "plugins/vera/scripts"))
    import native_workspace as workspace

    monkeypatch.setattr(
        workspace, "module_root", lambda component: ROOT / "plugins/vera"
    )
    monkeypatch.setattr(
        workspace, "binding_component", lambda binding: binding["workflow_id"]
    )
    binding = {
        "workflow_id": "journal-bank-reconciliation",
        "work_ref": "fictional",
        "client_id": "test",
        "client_root": str(review),
        "engagement_id": "test",
    }
    loaded = {
        "output_dir": str(review),
        "run": {
            "run_id": "fictional",
            "status": "running",
            "label": "Fictional posting review",
        },
    }
    state = workspace.snapshot(binding, loaded, {})
    assert state["kind"] == "postings" and state["total"] == 2
    posting.save_decision(review, "B001", decision(), actor="fictional-reviewer")
    with pytest.raises(ValueError, match="Stale"):
        workspace.snapshot(binding, loaded, {"revision": state["revision"]})


def test_foreign_batch_decisions_are_rejected(review):
    state = posting.read(review / posting.STATE)
    state["batch_sha256"] = "b" * 64
    posting.write(review / posting.STATE, state)
    with pytest.raises(ValueError, match="another proposal"):
        posting.projection(review, {})


def test_filters_cover_population_before_pagination_without_changing_records(review):
    case, state = posting.load(review)
    original = case["batch"]["items"][0]
    original["proposal_status"] = "Proposta oneri banca"
    case["batch"]["items"] = [
        {**original, "id": f"F{index:03d}"} for index in range(35)
    ] + [case["batch"]["items"][1]]
    case["batch_sha256"] = posting.fingerprint(case["batch"])
    state["batch_sha256"] = case["batch_sha256"]
    posting.write(review / posting.CASE, case)
    posting.write(review / posting.STATE, state)
    before = posting.revision(review)
    first = posting.projection(review, {"view": "POSTING_BANK_FEES"})
    second = posting.projection(review, {"view": "POSTING_BANK_FEES", "offset": 30})
    unresolved = posting.projection(review, {"view": "POSTING_NO_PROPOSAL"})
    assert first["total"] == 35 and len(first["items"]) == 30
    assert second["total"] == 35 and len(second["items"]) == 5
    assert unresolved["total"] == 1
    assert unresolved["selection"]["id"] == "B002"
    assert first["data"]["population_total"] == 36
    assert first["data"]["saved_count"] == 0
    assert posting.revision(review) == before


def test_saved_pending_is_distinct_from_never_saved(review):
    posting.save_decision(
        review, "B001", {**decision(), "status": "pending"}, actor="fictional-reviewer"
    )
    result = posting.projection(review, {})
    assert result["data"]["saved_count"] == 1
    assert result["items"][0]["decision"]["status"] == "pending"
    assert result["items"][1]["decision"] is None
    assert result["data"]["counts"]["pending"] == 2


def test_owned_native_save_reopen_and_export_uses_saved_correction(
    review, vera_workflow_workspace, monkeypatch
):
    import sys

    batch = posting.load(review)[0]["batch"]
    work = vera_workflow_workspace(
        "journal-bank-reconciliation", input_files={"batch.json": json.dumps(batch)}
    )
    sys.path.insert(0, str(ROOT / "plugins/vera/scripts"))
    import native_workspace as workspace

    output = work["output_dir"]
    posting.prepare(output, batch, run_id=work["run_id"], source_sha256="a" * 64)
    binding = {
        "work_ref": "posting-fictional",
        "client_root": str(work["client_root"]),
        "client_id": work["client_id"],
        "engagement_id": work["engagement_id"],
        "run_id": work["run_id"],
        "workflow_id": "journal-bank-reconciliation",
    }
    monkeypatch.setattr(
        workspace,
        "configuration",
        lambda: {
            "mode": "operator-bindings",
            "tenant_id": "fictional-studio",
            "actor_id": "fictional-reviewer",
            "bindings": [binding],
        },
    )
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "REVIEWER")
    view = workspace.dispatch(
        "vera_workspace_view", {"work_ref": "posting-fictional", "item_id": "B001"}
    )
    args = {
        "work_ref": "posting-fictional",
        "revision": view["revision"],
        "item_id": "B001",
        "human_reviewed": True,
        "idempotency_key": "fictional-save-1",
        "review": decision(),
    }
    saved = workspace.dispatch("vera_workspace_save", args)
    assert saved["saved"]
    reopened = workspace.dispatch(
        "vera_workspace_view", {"work_ref": "posting-fictional", "item_id": "B001"}
    )
    assert reopened["selection"]["decision"]["lines"][0]["account"] == "4000002"
    exported = workspace.dispatch(
        "vera_workspace_apply",
        {
            **args,
            "revision": reopened["revision"],
            "idempotency_key": "fictional-export-1",
            "review": {"operation": "export"},
        },
    )
    assert exported["records"] == 1
    files = workspace.outputs(binding, workspace.load_binding(binding))
    assert (
        len(files) == 2 and Path(files[0]["path"]).read_bytes()[1036:1043] == b"4000002"
    )


def test_browser_discard_saved_status_filters_and_txt(
    review, vera_workflow_workspace, monkeypatch, tmp_path
):
    """Exercise real UI/MCP writers on fictional data, never the client batch."""
    import os

    from playwright.sync_api import expect

    from tests.plugins.test_vera_native_workspace import configure
    from tests.plugins.test_vera_review_browser import review_host

    batch = posting.load(review)[0]["batch"]
    batch["items"][0]["proposal_status"] = "Proposta oneri banca"
    work = vera_workflow_workspace(
        "journal-bank-reconciliation", input_files={"batch.json": json.dumps(batch)}
    )
    output = work["output_dir"]
    posting.prepare(output, batch, run_id=work["run_id"], source_sha256="a" * 64)
    original = (output / posting.CASE).read_bytes()
    binding = {
        "work_ref": "posting-fictional-browser",
        "client_root": str(work["client_root"]),
        "client_id": work["client_id"],
        "engagement_id": work["engagement_id"],
        "run_id": work["run_id"],
        "workflow_id": "journal-bank-reconciliation",
    }
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    with review_host(env) as (page, mount, errors):
        page.set_viewport_size({"width": 1280, "height": 1000})
        panel = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        expect(panel.get_by_role("checkbox")).to_have_count(0)
        export = panel.get_by_role("button", name="Genera TXT dalle decisioni salvate")
        expect(export).to_be_disabled()
        choices = panel.get_by_role("group", name="Decisione", exact=True)
        expect(choices.get_by_role("radio")).to_have_count(3)
        expect(
            choices.get_by_role("radio", name="Accetta le righe corrette", exact=True)
        ).to_be_checked()
        expect(
            panel.get_by_role("combobox", name="Decisione", exact=True)
        ).to_have_count(0)
        # Rendering the default must not create a draft or a saved decision.
        page.wait_for_timeout(700)
        assert posting.load(output)[1]["decisions"] == {}
        expect(
            panel.get_by_role("button", name="Scarta modifiche", exact=True)
        ).to_be_hidden()
        expect(export).to_be_disabled()
        note = panel.get_by_role("textbox", name="Nota o documento mancante")
        note.fill("Fictional unsaved note")
        discard = panel.get_by_role("button", name="Scarta modifiche", exact=True)
        expect(discard).to_be_visible()
        panel.get_by_role("button", name="Unresolved").click()
        expect(
            panel.get_by_role("heading", name="Fictional payment", exact=True)
        ).to_be_visible()
        discard.click()
        expect(discard).to_be_hidden()
        expect(note).to_have_value("")
        panel.get_by_role("button", name="Unresolved").click()
        expect(
            panel.get_by_role("heading", name="Unresolved", exact=True)
        ).to_be_visible()
        # No save required to leave an unresolved, unchanged entry.
        panel.get_by_role("combobox", name="Tipo di proposta").click()
        panel.get_by_role("option", name="Nessun abbinamento proposto (1)").click()
        expect(panel.get_by_role("button", name="Fictional payment")).to_have_count(0)
        choices.get_by_role("radio", name="Da rivedere", exact=True).check()
        panel.get_by_role("button", name="Salva decisione e correzioni").click()
        expect(
            choices.get_by_role("radio", name="Da rivedere", exact=True)
        ).to_be_checked()
        expect(
            panel.get_by_text("1 decisioni salvate · 1 mai salvati", exact=True)
        ).to_be_visible()
        expect(
            panel.get_by_text("Decisione salvata · Da rivedere", exact=False)
        ).to_be_visible()
        panel.get_by_role("combobox", name="Tipo di proposta").click()
        panel.get_by_role("option", name="Oneri bancari (1)").click()
        expect(
            panel.get_by_role("heading", name="Fictional payment", exact=True)
        ).to_be_visible()
        panel.get_by_role("textbox", name="Conto", exact=True).fill("4000002")
        expect(
            choices.get_by_role("radio", name="Accetta le righe corrette", exact=True)
        ).to_be_checked()
        panel.get_by_role("button", name="Salva decisione e correzioni").click()
        expect(
            panel.get_by_text("Decisione salvata · Accettato", exact=False)
        ).to_be_visible()
        expect(export).to_be_enabled()
        export.click()
        expect(
            panel.get_by_text(
                "Ultimo TXT: 1 movimenti. Importazione TeamSystem non collaudata.",
                exact=True,
            )
        ).to_be_visible()
        if os.environ.get("TS_REVIEW_SCREENSHOT"):
            page.screenshot(path=os.environ["TS_REVIEW_SCREENSHOT"], full_page=True)
        panel.get_by_role("button", name="File del lavoro", exact=True).click()
        expect(
            panel.get_by_role(
                "textbox", name="Percorso del file TRAF2000_REVISIONE_"
            ).first
        ).to_be_visible()
        assert not errors
    case, saved = posting.load(output)
    receipt = saved["last_export"]
    raw = (output / receipt["file"]).read_bytes()
    assert len(raw) == 7001 and raw[1036:1043] == b"4000002"
    assert receipt["records"] == 1
    assert receipt["excluded"] == [{"id": "B002", "status": "pending"}]
    assert saved["decisions"]["B002"]["lines"] == []
    assert (output / posting.CASE).read_bytes() == original


@pytest.mark.parametrize("saved_status", ["pending", "accepted", "rejected"])
def test_browser_preserves_saved_choice_and_recovers_draft(
    review, vera_workflow_workspace, monkeypatch, tmp_path, saved_status
):
    """The new default must never overwrite a saved choice or recovered draft."""
    import os

    from playwright.sync_api import expect

    from tests.plugins.test_vera_native_workspace import configure
    from tests.plugins.test_vera_review_browser import review_host

    batch = posting.load(review)[0]["batch"]
    work = vera_workflow_workspace(
        "journal-bank-reconciliation", input_files={"batch.json": json.dumps(batch)}
    )
    output = work["output_dir"]
    posting.prepare(output, batch, run_id=work["run_id"], source_sha256="a" * 64)
    posting.save_decision(
        output, "B001", decision(status=saved_status), actor="fictional"
    )
    saved_before = (output / posting.STATE).read_bytes()
    binding = {
        "work_ref": "posting-fictional-draft",
        "client_root": str(work["client_root"]),
        "client_id": work["client_id"],
        "engagement_id": work["engagement_id"],
        "run_id": work["run_id"],
        "workflow_id": "journal-bank-reconciliation",
    }
    labels = {
        "pending": "Da rivedere",
        "accepted": "Accetta le righe corrette",
        "rejected": "Escludi dal TXT",
    }
    draft_status = "rejected" if saved_status != "rejected" else "pending"
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    with review_host(env) as (page, mount, errors):
        panel = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        expect(
            panel.get_by_role("radio", name=labels[saved_status], exact=True)
        ).to_be_checked()
        panel.get_by_role("radio", name=labels[draft_status], exact=True).check()
        panel.get_by_role("textbox", name="Nota o documento mancante").fill(
            "Fictional draft retained"
        )
        page.wait_for_timeout(1200)
        panel = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        panel.get_by_role("button", name="Recupera bozza", exact=True).click()
        expect(
            panel.get_by_role("radio", name=labels[draft_status], exact=True)
        ).to_be_checked()
        expect(
            panel.get_by_role("textbox", name="Nota o documento mancante")
        ).to_have_value("Fictional draft retained")
        assert (output / posting.STATE).read_bytes() == saved_before
        assert not errors


@pytest.mark.parametrize(
    "values",
    [
        {"partita": "350"},
        {"year": "2026"},
        {"section": "00"},
        {"partita": "abc", "year": "2026", "section": "00"},
        {"partita": "350", "year": "26", "section": "00"},
        {"partita": "350", "year": "2026", "section": "000"},
    ],
)
def test_partita_fields_still_require_complete_valid_values(review, values):
    data = decision()
    data["lines"][0].update(values)
    data["partita_confirmed"] = True
    with pytest.raises(ValueError, match="valid partita"):
        posting.save_decision(review, "B001", data, actor="fictional")
