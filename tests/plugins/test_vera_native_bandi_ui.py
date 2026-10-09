"""Standalone maintained UI behaviour with an explicit injected fictional host."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []


def browser(body):
    fixture = ROOT / "tests/plugins/bandi_contributions_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/bandi-contributions.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};(async()=>{{{body}}})().catch(e=>{{process.stderr.write(e.stack);process.exitCode=1;}});"
    completed = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_task_edit_preserves_literal_fields_and_clears_both_consents():
    result = browser(
        """
const ui=fixture(source);await ui.panel.open('fictional-work');
const checks=ui.all().filter(e=>e.type==='checkbox');checks.forEach(e=>e.checked=true);
const input=ui.field('Riferimento dichiarato della sessione separata');input.value='FICTIONAL-NEW-SESSION';input.dispatch('input');
await ui.panel.flush();await ui.panel.refresh();
process.stdout.write(JSON.stringify({fields:ui.page.fields,consents:ui.all().filter(e=>e.type==='checkbox').map(e=>e.checked),calls:ui.calls,dirty:ui.dirty}));
"""
    )
    assert result["fields"]["model_session_ref"] == "FICTIONAL-NEW-SESSION"
    assert result["consents"] == [False, False]
    assert result["dirty"] is False
    assert [row["name"] for row in result["calls"]].count(
        "vera_workspace_bandi_author_request"
    ) == 0


def test_authorization_refuses_missing_attestation_and_copy_does_not_send_chat_message():
    result = browser(
        """
const ui=fixture(source,{fields:{task:'WORKFLOW_GUIDANCE',subject_ids:['SRC-001'],raw_source_ids:[],model_session_ref:'FICTIONAL-SESSION-001'}});await ui.panel.open('fictional-work');
let refused=false;try{await ui.button('Autorizza questo contributo').action();}catch(e){refused=true;}
ui.all().filter(e=>e.type==='checkbox').forEach(e=>e.checked=true);
await ui.button('Autorizza questo contributo').action();await ui.button('Richiesta per sessione separata').action();
const prompt=ui.field('Richiesta Bandi da copiare in una sessione separata').value;
process.stdout.write(JSON.stringify({refused,prompt,calls:ui.calls,restored:ui.all().filter(e=>e.type==='checkbox').map(e=>e.checked)}));
"""
    )
    assert result["refused"] is True
    assert "sessione separata" in result["prompt"]
    assert "vera_workspace_bandi_author_context" in result["prompt"]
    assert "ui/message" not in [row["name"] for row in result["calls"]]
    assert result["restored"] == [False, False, False]


def test_proposal_registration_requires_complete_preview_and_renewed_confirmation():
    result = browser(
        """
const grant={grant_ref:'mandate-'+ 'a'.repeat(64),task:'WORKFLOW_GUIDANCE',status:'open',stages:[{stage_ref:'proposal-'+ 'b'.repeat(64)}]};
const ui=fixture(source,{grants:[grant]});await ui.panel.open('fictional-work');await ui.button('Riesamina proposta conservata').action();
const button=ui.button('Registra questo suggerimento');const disabled=button.disabled;
let refused=false;try{await button.action();}catch(e){refused=true;}
const confirm=ui.all().find(e=>e.attributes['aria-label']?.startsWith('Ho riesaminato'));confirm.checked=true;confirm.dispatch('change');
const enabled=!button.disabled;await button.action();
process.stdout.write(JSON.stringify({disabled,refused,enabled,calls:ui.calls,status:ui.page.grants[0].status}));
"""
    )
    assert result["disabled"] is True
    assert result["refused"] is True
    assert result["enabled"] is True
    assert result["status"] == "recorded"
    assert "vera_workspace_bandi_author_decide" not in [
        row["name"] for row in result["calls"]
    ]


def test_disposition_fields_persist_incomplete_and_never_restore_decision_consent():
    result = browser(
        """
const grant={grant_ref:'mandate-'+ 'a'.repeat(64),task:'WORKFLOW_GUIDANCE',status:'recorded',stages:[],intelligence_run_id:'INTEL-000001'};
const ui=fixture(source,{grants:[grant],public_suggestions:[{intelligence_run_id:'INTEL-000001',status:'MODEL_SUGGESTED'}]});await ui.panel.open('fictional-work');await ui.button('Riesamina e disponi sul suggerimento').action();
ui.all().filter(e=>e.type==='checkbox').forEach(e=>e.checked=true);
const input=ui.field('Note e limiti della disposizione');input.value='Incomplete reviewer note';input.dispatch('input');
await ui.panel.flush();await ui.panel.refresh();
let refused=false;try{await ui.button('Registra disposizione').action();}catch(e){refused=true;}
process.stdout.write(JSON.stringify({fields:ui.draft.fields,consents:ui.all().filter(e=>e.type==='checkbox').map(e=>e.checked),refused,calls:ui.calls}));
"""
    )
    assert result["fields"] == {
        "decision": "",
        "reviewer_id": "",
        "reviewer_role": "",
        "notes": "Incomplete reviewer note",
    }
    assert result["consents"] == [False, False]
    assert result["refused"] is True
    assert "vera_workspace_bandi_author_decide" not in [
        row["name"] for row in result["calls"]
    ]


def test_viewer_task_fields_and_mutation_controls_are_disabled():
    result = browser(
        """
const ui=fixture(source,{can_write:false});await ui.panel.open('fictional-work');
process.stdout.write(JSON.stringify({disabled:ui.button('Autorizza questo contributo').disabled,inputs:ui.all().filter(e=>['INPUT','TEXTAREA','SELECT'].includes(e.tagName)).map(e=>e.disabled),calls:ui.calls}));
"""
    )
    assert result["disabled"] is True
    assert all(result["inputs"])
    assert [row["name"] for row in result["calls"]] == [
        "vera_workspace_bandi_author_setup"
    ]
