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
    with pytest.raises(ValueError, match="Totale Dare"):
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
        "expected_draft_revision": "",
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
        assert not list(output.rglob("posting-draft-*.json"))
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
            panel.get_by_role("heading", name="Unresolved", exact=True)
        ).to_be_visible()
        assert posting.load(output)[1]["decisions"] == {}
        panel.get_by_role("button", name="Fictional payment").click()
        expect(note).to_have_value("Fictional unsaved note")
        expect(
            panel.get_by_text("Bozza conservata · decisione non salvata", exact=True)
        ).to_be_visible()
        panel.get_by_role("button", name="Scarta modifiche", exact=True).click()
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
            panel.locator("#detail").get_by_text(
                "Decisione salvata · Da rivedere", exact=False
            )
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
            panel.locator("#detail").get_by_text(
                "Decisione salvata · Accettato", exact=False
            )
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
        expect(
            panel.get_by_text("Bozza conservata · decisione non salvata", exact=True)
        ).to_be_visible()
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
    with pytest.raises(ValueError, match="Partita, anno"):
        posting.save_decision(review, "B001", data, actor="fictional")


def browser_work(review, factory, monkeypatch, tmp_path, *, batch=None, chart=None):
    """Bind only synthetic sources to the real review host."""
    import os

    from tests.plugins.test_vera_native_workspace import configure

    batch = batch or posting.load(review)[0]["batch"]
    work = factory(
        "journal-bank-reconciliation", input_files={"batch.json": json.dumps(batch)}
    )
    output = work["output_dir"]
    posting.prepare(
        output, batch, run_id=work["run_id"], source_sha256="a" * 64, chart=chart
    )
    binding = {
        "work_ref": "posting-fictional-expanded",
        "client_root": str(work["client_root"]),
        "client_id": work["client_id"],
        "engagement_id": work["engagement_id"],
        "run_id": work["run_id"],
        "workflow_id": "journal-bank-reconciliation",
    }
    return (
        output,
        binding,
        {**os.environ, **configure(monkeypatch, tmp_path, [binding])},
    )


def test_browser_accounting_totals_italian_amounts_errors_undo_and_next(
    review, vera_workflow_workspace, monkeypatch, tmp_path
):
    from playwright.sync_api import expect

    from tests.plugins.test_vera_review_browser import review_host

    batch = posting.load(review)[0]["batch"]
    batch["items"][0]["bank"]["amount"] = "-1030.46"
    batch["items"][0]["proposed_lines"][0]["amount"] = "1030.46"
    output, binding, env = browser_work(
        review, vera_workflow_workspace, monkeypatch, tmp_path, batch=batch
    )
    with review_host(env) as (page, mount, errors):
        panel = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        detail = panel.locator("#detail")
        amount = detail.get_by_role("textbox", name="Importo EUR", exact=True)
        expect(amount).to_have_value("1.030,46")
        expect(detail.locator(".posting-bank")).to_contain_text("1.030,46")
        expect(detail.locator(".posting-totals")).to_contain_text(
            "Totale Dare1.030,46Totale Avere1.030,46Differenza0,00"
        )
        amount.fill("1.030,45")
        expect(detail.locator(".posting-totals")).to_contain_text("−0,01")
        detail.get_by_role("button", name="Salva e successivo", exact=True).click()
        expect(amount).to_be_focused()
        assert posting.load(output)[1]["decisions"] == {}
        amount.fill("1,030.46")
        expect(amount).to_have_attribute("aria-invalid", "true")
        expect(
            detail.get_by_text(
                "Usa 1.030,46 oppure 1030,46; sono ammessi al massimo due decimali.",
                exact=True,
            )
        ).to_be_visible()
        amount.fill("1.030")
        expect(amount).to_have_attribute("aria-invalid", "true")
        expect(
            detail.get_by_text(
                "Importo ambiguo: indica anche i centesimi, per esempio 1.030,00.",
                exact=True,
            )
        ).to_be_visible()
        amount.fill("1.030,46")
        detail.get_by_role("textbox", name="Partita", exact=True).fill("350")
        detail.get_by_role("button", name="Salva e successivo", exact=True).click()
        expect(detail.get_by_role("textbox", name="Anno", exact=True)).to_be_focused()
        detail.get_by_role("textbox", name="Anno", exact=True).fill("2026")
        detail.get_by_role("textbox", name="Sezionale", exact=True).fill("00")
        detail.get_by_role("button", name="Rimuovi contropartita 1", exact=True).click()
        expect(
            detail.get_by_role("button", name="Annulla rimozione", exact=True)
        ).to_be_focused()
        detail.get_by_role("button", name="Salva e successivo", exact=True).click()
        expect(
            detail.get_by_role("button", name="Aggiungi contropartita", exact=True)
        ).to_be_focused()
        detail.get_by_role("button", name="Annulla rimozione", exact=True).click()
        expect(detail.get_by_role("textbox", name="Conto", exact=True)).to_be_focused()
        expect(amount).to_have_value("1.030,46")
        expect(detail.get_by_role("textbox", name="Partita", exact=True)).to_have_value(
            "350"
        )
        # Keyboard can reach and change the native radio group.
        pending = detail.get_by_role("radio", name="Da rivedere", exact=True)
        pending.focus()
        pending.press("ArrowRight")
        expect(
            detail.get_by_role("radio", name="Accetta le righe corrette", exact=True)
        ).to_be_checked()
        page.set_viewport_size({"width": 1280, "height": 1100})
        page.screenshot(path=str(tmp_path / "posting-wide.png"), full_page=True)
        page.set_viewport_size({"width": 540, "height": 1000})
        assert detail.evaluate("el=>el.scrollWidth<=el.clientWidth+1")
        page.screenshot(path=str(tmp_path / "posting-narrow.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 900})
        amount.fill("999.999.999,99")
        expect(detail.locator(".posting-totals")).to_contain_text("999.999.999,99")
        assert detail.evaluate("el=>el.scrollWidth<=el.clientWidth+1")
        amount.fill("1.030,46")
        detail.get_by_role("button", name="Salva e successivo", exact=True).click()
        expect(
            detail.get_by_role("heading", name="Unresolved", exact=True)
        ).to_be_visible()
        saved = posting.load(output)[1]
        assert list(saved["decisions"]) == ["B001"]
        assert saved["decisions"]["B001"]["lines"][0]["amount"] == "1030.46"
        assert saved["decisions"]["B001"]["lines"][0]["partita"] == "350"
        assert not errors


def test_whole_review_search_decision_filters_and_next_cross_pages(review):
    batch = posting.load(review)[0]["batch"]
    template = batch["items"][0]
    batch["items"] = [
        {**template, "id": f"B{i:03}", "title": f"Movement {i}"} for i in range(65)
    ]
    target = review / "whole-review"
    target.mkdir()
    posting.prepare(target, batch, run_id="fictional", source_sha256="b" * 64)
    posting.save_decision(target, "B064", decision(status="pending"), actor="fictional")
    before = posting.revision(target)
    result = posting.projection(
        target, {"search_text": "Movement 64", "decision_filter": "pending"}
    )
    assert result["total"] == 1 and result["items"][0]["id"] == "B064"
    assert posting.projection(target, {"decision_filter": "unsaved"})["total"] == 64
    result = posting.projection(target, {"item_id": "B029"})
    assert result["data"]["next_id"] == "B030" and result["data"]["next_offset"] == 30
    assert posting.revision(target) == before


def test_verified_chart_membership_and_tamper_detection(review):
    batch = posting.load(review)[0]["batch"]
    target = review / "chart-review"
    target.mkdir()
    chart = {
        "client_id": "fictional",
        "source_binding_id": "fictional-chart",
        "source_sha256": "c" * 64,
        "accounts": [{"code": "4000001", "name": "Fornitori sintetici"}],
    }
    posting.prepare(
        target, batch, run_id="fictional", source_sha256="a" * 64, chart=chart
    )
    assert posting.projection(target, {})["data"]["chart_of_accounts"] == chart
    with pytest.raises(ValueError, match="piano dei conti"):
        posting.save_decision(
            target, "B001", decision(account="4000002"), actor="fictional"
        )
    posting.save_decision(
        target, "B001", decision(account="4000001"), actor="fictional"
    )
    case = posting.read(target / posting.CASE)
    case["chart_of_accounts"]["accounts"][0]["name"] = "Changed"
    posting.write(target / posting.CASE, case)
    with pytest.raises(ValueError, match="è cambiato"):
        posting.load(target)


def test_movement_drafts_are_isolated_compare_and_set_and_preserve_legacy(
    review, vera_workflow_workspace, monkeypatch, tmp_path
):
    import sys

    sys.path.insert(0, str(ROOT / "plugins/vera/scripts"))
    import native_workspace as workspace

    output, binding, _ = browser_work(
        review, vera_workflow_workspace, monkeypatch, tmp_path
    )
    before = (output / posting.STATE).read_bytes()
    legacy = {
        "work_ref": binding["work_ref"],
        "revision": posting.revision(output),
        "item_id": "B001",
        "source_ref": None,
        "fields": {
            "posting_id": "B001",
            "status": "pending",
            "lines": [],
            "note": "Legacy retained",
        },
    }
    old_path = workspace.draft_path(output, "fictional-reviewer")
    workspace.atomic_json(old_path, legacy)
    read = lambda item: workspace.dispatch(
        "vera_workspace_draft_read", {"work_ref": binding["work_ref"], "item_id": item}
    )
    first = read("B001")
    assert first["draft"] == legacy
    assert read("B002")["draft"] is None

    def store(item, checkpoint, note):
        view = workspace.dispatch(
            "vera_workspace_view", {"work_ref": binding["work_ref"], "item_id": item}
        )
        return workspace.dispatch(
            "vera_workspace_draft_save",
            {
                "work_ref": binding["work_ref"],
                "item_id": item,
                "revision": view["revision"],
                "expected_draft_revision": checkpoint,
                "fields": {
                    "posting_id": item,
                    "status": "accepted",
                    "lines": [],
                    "note": note,
                },
            },
        )

    latest = store("B001", first["draft_revision"], "Newer draft")
    with pytest.raises(ValueError, match="altra finestra"):
        store("B001", first["draft_revision"], "Stale tab")
    store("B002", "", "Other movement")
    assert read("B001")["draft"]["fields"]["note"] == "Newer draft"
    assert read("B002")["draft"]["fields"]["note"] == "Other movement"
    assert read("B001")["draft_revision"] == latest["draft_revision"]
    assert workspace.read_json(old_path) == legacy
    assert (output / posting.STATE).read_bytes() == before


def test_browser_verified_chart_search_and_whole_review_search(
    review, vera_workflow_workspace, monkeypatch, tmp_path
):
    from playwright.sync_api import expect

    from tests.plugins.test_vera_review_browser import review_host

    batch = posting.load(review)[0]["batch"]
    template = batch["items"][0]
    batch["items"] = [
        {**template, "id": f"B{i:03}", "title": f"Movement {i}"} for i in range(35)
    ]
    chart = {
        "client_id": "fictional",
        "source_binding_id": "fictional-chart",
        "source_sha256": "c" * 64,
        "accounts": [
            {"code": "4000001", "name": "Fornitori sintetici"},
            {"code": "4000002", "name": "Costi sintetici"},
        ],
    }
    output, binding, env = browser_work(
        review, vera_workflow_workspace, monkeypatch, tmp_path, batch=batch, chart=chart
    )
    before = (output / posting.STATE).read_bytes()
    with review_host(env) as (page, mount, errors):
        page.set_viewport_size({"width": 1280, "height": 1100})
        panel = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        search = panel.get_by_role(
            "searchbox", name="Cerca in tutti i movimenti", exact=True
        )
        search.fill("Movement 34")
        search.press("Enter")
        detail = panel.locator("#detail")
        expect(
            detail.get_by_role("heading", name="Movement 34", exact=True)
        ).to_be_visible()
        expect(detail.get_by_text("Fornitori sintetici", exact=True)).to_be_visible()
        detail.get_by_role(
            "searchbox", name="Cerca codice o denominazione contropartita 1", exact=True
        ).fill("Costi")
        detail.get_by_role(
            "combobox", name="Scegli conto contropartita 1", exact=True
        ).click()
        detail.get_by_role(
            "option", name="4000002 · Costi sintetici", exact=True
        ).click()
        expect(detail.get_by_role("textbox", name="Conto", exact=True)).to_have_value(
            "4000002"
        )
        expect(detail.get_by_text("Costi sintetici", exact=True)).to_be_visible()
        assert (output / posting.STATE).read_bytes() == before
        assert not errors


@pytest.mark.parametrize("foreign_client", [False, True])
def test_registered_chart_cli_requires_same_client_and_retains_source_receipt(
    review, vera_workflow_workspace, monkeypatch, foreign_client
):
    import hashlib
    import sys

    batch = posting.load(review)[0]["batch"]
    chart = {
        "client_id": (
            "other-client" if foreign_client else "client_111111111111111111111111"
        ),
        "accounts": [{"code": "4000001", "name": "Fornitori sintetici"}],
    }
    work = vera_workflow_workspace(
        "journal-bank-reconciliation",
        input_files={"batch.json": json.dumps(batch), "chart.json": json.dumps(chart)},
    )
    bindings = {
        Path(row["path"]).name: row for row in work["context"]["input_bindings"]
    }
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "posting-review",
            "--client-engagement",
            str(work["context_path"]),
            "--batch-input-id",
            bindings["batch.json"]["binding_id"],
            "--chart-input-id",
            bindings["chart.json"]["binding_id"],
        ],
    )
    if foreign_client:
        with pytest.raises(ValueError, match="altro cliente"):
            posting.main()
        assert not (work["output_dir"] / posting.CASE).exists()
    else:
        posting.main()
        case, _ = posting.load(work["output_dir"])
        assert case["chart_of_accounts"]["client_id"] == work["client_id"]
        assert (
            case["chart_of_accounts"]["source_binding_id"]
            == bindings["chart.json"]["binding_id"]
        )
        assert (
            case["chart_of_accounts"]["source_sha256"]
            == hashlib.sha256(
                Path(bindings["chart.json"]["path"]).read_bytes()
            ).hexdigest()
        )


def test_browser_failed_draft_read_keeps_visible_movement_and_write_scope(
    review, vera_workflow_workspace, monkeypatch, tmp_path
):
    """A failed navigation read must not retarget the still-visible editor."""
    from playwright.sync_api import expect

    from tests.plugins.test_vera_review_browser import review_host

    output, binding, env = browser_work(
        review, vera_workflow_workspace, monkeypatch, tmp_path
    )
    with review_host(env) as (page, mount, errors):
        page.set_viewport_size({"width": 1280, "height": 1000})
        panel = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        detail = panel.locator("#detail")
        expect(
            detail.get_by_role("heading", name="Fictional payment", exact=True)
        ).to_be_visible()
        detail.get_by_role("textbox", name="Nota o documento mancante").fill(
            "Retained before failed navigation"
        )
        page.evaluate(
            """()=>{const original=window.mcpCall;window.mcpCall=async(params)=>{
          if(params.name==='vera_workspace_draft_read'&&params.arguments.item_id==='B002')return {isError:true,content:[{type:'text',text:'Lettura bozza temporaneamente non disponibile'}]};
          return original(params);
        }}"""
        )
        panel.get_by_role("button", name="Unresolved").click()
        expect(
            panel.get_by_text(
                "Lettura bozza temporaneamente non disponibile", exact=True
            )
        ).to_be_visible()
        expect(
            detail.get_by_role("heading", name="Fictional payment", exact=True)
        ).to_be_visible()
        expect(
            detail.get_by_role("textbox", name="Nota o documento mancante")
        ).to_have_value("Retained before failed navigation")
        detail.get_by_role("radio", name="Da rivedere", exact=True).check()
        detail.get_by_role(
            "button", name="Salva decisione e correzioni", exact=True
        ).click()
        expect(
            detail.get_by_text("Decisione salvata · Da rivedere", exact=False)
        ).to_be_visible()
        saved = posting.load(output)[1]["decisions"]
        assert (
            list(saved) == ["B001"]
            and saved["B001"]["note"] == "Retained before failed navigation"
        )
        assert not errors
