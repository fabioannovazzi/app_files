"""Typed authoring events on a declared fictional transport, not installed-host acceptance."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []


def browser(body):
    fixture = ROOT / "tests/plugins/patent_box_authoring_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/patent-box-authoring.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};(async()=>{{{body}}})().catch(e=>{{process.stderr.write(e.stack);process.exitCode=1;}});"
    result = subprocess.run(
        [NODE, "-e", code], text=True, capture_output=True, check=False, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_patent_box_author_ui_literal_question_selection_restores_without_consent():
    result = browser(
        """
const ui=fixture(source);await ui.panel.open('fictional-work');
ui.field('Confermo questa domanda e la selezione esatta per la preparazione specialistica').checked=true;
const question=ui.field('Domanda e fatti da chiarire');question.value='  FICTIONAL unresolved facts  ';question.dispatch('input');
const task=ui.field('Preparazione richiesta');task.value='propose';task.dispatch('change');
const original=ui.field('fictional.txt · 18 byte');original.checked=true;original.dispatch('change');
const record=ui.field('ledger_E0001.json');record.checked=true;record.dispatch('change');
await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({fields:ui.page.fields,consent:ui.field('Confermo questa domanda e la selezione esatta per la preparazione specialistica').checked,calls:ui.calls}));
"""
    )
    assert result["fields"] == {
        "task": "propose",
        "question": "  FICTIONAL unresolved facts  ",
        "input_ids": ["I1"],
        "record_refs": ["ledger_E0001.json"],
    }
    assert result["consent"] is False
    assert {r["name"] for r in result["calls"]} == {
        "vera_workspace_patent_box_author_setup",
        "vera_workspace_patent_box_author_draft_save",
    }


def test_patent_box_author_ui_request_needs_renewed_selection_confirmation():
    result = browser(
        """
const ui=fixture(source,{fields:{task:'propose',question:'Fictional exact question',input_ids:['I1'],record_refs:[]}});await ui.panel.open('fictional-work');
let refused=false;try{await ui.button('Conserva il mandato a Vera').action();}catch(e){refused=true;}
ui.field('Confermo questa domanda e la selezione esatta per la preparazione specialistica').checked=true;await ui.button('Conserva il mandato a Vera').action();
process.stdout.write(JSON.stringify({refused,calls:ui.calls,consent:ui.field('Confermo questa domanda e la selezione esatta per la preparazione specialistica').checked}));
"""
    )
    assert result["refused"] is True
    assert result["consent"] is False
    assert len([r for r in result["calls"] if r["name"].endswith("_request")]) == 1
    assert not any(r["name"].endswith("_execute") for r in result["calls"])


def test_patent_box_author_ui_fallback_instructs_exact_current_mandate_without_model_or_publish_call():
    result = browser(
        """
const ui=fixture(source);ui.page.grants=[{grant_ref:ui.grantRef,task:'propose',question:'Fictional exact question',status:'open'}];await ui.panel.open('fictional-work');
await ui.button('Riesamina questo mandato').action();await ui.button('Prepara nella chat corrente').action();
process.stdout.write(JSON.stringify({prompt:ui.field('Richiesta di preparazione Patent Box da copiare nella chat corrente').value,calls:ui.calls}));
"""
    )
    assert "vera_workspace_patent_box_author_context" in result["prompt"]
    assert "fictional-exact-source" in result["prompt"]
    assert "non convertire regole reali DRAFT in REVIEWED" in result["prompt"]
    assert "NO_MODEL_EXECUTED" not in result["prompt"]
    assert not any(
        r["name"].endswith(("_context", "_stage", "_adopt", "_execute"))
        for r in result["calls"]
    )


def test_patent_box_author_ui_adoption_requires_comparison_and_exact_complete_stage():
    result = browser(
        """
const ui=fixture(source,{read:{stages:[{stage_ref:'proposal-'+'a'.repeat(64)}]}});ui.page.grants=[{grant_ref:ui.grantRef,task:'propose',question:'Fictional exact question',status:'open'}];await ui.panel.open('fictional-work');await ui.button('Riesamina questo mandato').action();await ui.button('Riesamina proposta · '+ui.stageRef).action();
let refused=false;try{await ui.button('Carica nei campi da rivedere').action();}catch(e){refused=true;}
ui.field('Ho confrontato i campi privati attuali e confermo la loro sostituzione con questa proposta esatta').checked=true;
ui.field('Carico questa proposta completa nei campi privati. Esecuzione e decisioni professionali richiedono conferme separate').checked=true;
const text=ui.text();await ui.button('Carica nei campi da rivedere').action();process.stdout.write(JSON.stringify({refused,text,calls:ui.calls}));
"""
    )
    assert result["refused"] is True
    assert "Fictional located gap" in result["text"]
    adopted = next(r for r in result["calls"] if r["name"].endswith("_adopt"))
    assert adopted["args"]["stage_ref"] == adopted["args"]["selected_stage_ref"]
    assert adopted["args"]["expected_producer_draft_revision"] == "exact-producer-draft"
    assert not any(r["name"].endswith("_execute") for r in result["calls"])


def test_patent_box_author_ui_viewer_has_no_question_or_mandate_writes():
    result = browser(
        """
const ui=fixture(source,{can_write:false,can_author:false});await ui.panel.open('fictional-work');await ui.panel.flush();process.stdout.write(JSON.stringify({disabled:ui.button('Conserva il mandato a Vera').disabled,calls:ui.calls,text:ui.text()}));
"""
    )
    assert result["disabled"] is True
    assert "Consultazione soltanto" in result["text"]
    assert [r["name"] for r in result["calls"]] == [
        "vera_workspace_patent_box_author_setup"
    ]
