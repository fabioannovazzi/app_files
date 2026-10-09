"""Actual panel events over a fictional protocol; not installed-host acceptance."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tests.plugins.test_vera_native_studio_work import NODE, PLUGIN, ROOT

__all__ = []


def events(body):
    """Execute maintained panel source with explicit fictional responses."""
    fixture = json.dumps(str(ROOT / "tests/plugins/studio_work_ui_fixture.cjs"))
    source = json.dumps(
        str(
            Path(
                os.environ.get(
                    "VERA_STUDIO_WORK_UI_TEST_SOURCE", str(PLUGIN / "ui/studio-work.js")
                )
            )
        )
    )
    code = f"const {{fixture}}=require({fixture});const source={source};(async()=>{{{body}}})().catch(error=>{{process.stderr.write(error.stack);process.exitCode=1;}});"
    result = subprocess.run(
        [str(NODE), "-e", code], capture_output=True, text=True, timeout=20, check=False
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_studio_panel_partial_fields_reopen_without_confirmation_or_schedule():
    result = events(
        """
const ui=fixture(source);await ui.panel.open({form:'capture'});ui.confirm().checked=true;
ui.field('Appunti').value='  FICTIONAL PRIVATE NOTE  ';ui.field('Appunti').dispatch('input');
ui.field('Priorità dichiarata').value='0';ui.field('Priorità dichiarata').dispatch('input');
await ui.panel.flush();await ui.panel.open({form:'capture'});
process.stdout.write(JSON.stringify({draft:ui.drafts.capture,confirm:ui.confirm().checked,calls:ui.calls,dirty:ui.dirty,text:ui.text()}));
"""
    )
    assert result["draft"]["fields"] == {
        "notes": "  FICTIONAL PRIVATE NOTE  ",
        "priority": 0,
    }
    assert result["confirm"] is False
    assert result["dirty"] is False
    assert not any(call["name"].endswith("_submit") for call in result["calls"])
    assert "Quali dati arrivano al modello" in result["text"]
    assert "Nessuna data viene ricavata" in result["text"]


def test_studio_panel_dependency_choices_include_all_pages_without_id_entry():
    result = events(
        """
const items=Array.from({length:65},(_,index)=>({id:'fixture-'+index,title:'Fictional task '+index,kind:'task',status:'open'}));
const ui=fixture(source,{items});await ui.panel.open({form:'capture'});
const selected=ui.all().find(value=>value.tagName==='INPUT'&&value.type==='checkbox'&&value.parentElement.children.some(child=>child.text==='Fictional task 64 · Aperto'));selected.checked=true;selected.dispatch('change');await ui.panel.flush();
process.stdout.write(JSON.stringify({fields:ui.drafts.capture.fields,calls:ui.calls}));
"""
    )
    assert result["fields"] == {"depends_on": ["fixture-64"]}
    pages = [
        call["args"].get("offset", 0)
        for call in result["calls"]
        if call["args"].get("expected_scope")
    ]
    assert pages == [0, 30, 60]


def test_studio_panel_calendar_receipts_have_real_paging_controls():
    result = events(
        """
const operations=Array.from({length:65},(_,index)=>({id:'operation-'+index,state:'uncertain',action:'create',desired:{title:'Fictional event '+index}}));
const ui=fixture(source,{operations});await ui.panel.open({collection:'operations'});await ui.button('Altre voci →').action();await ui.button('Altre voci →').action();process.stdout.write(JSON.stringify({text:ui.text(),calls:ui.calls}));
"""
    )
    assert "61–65 di 65" in result["text"]
    assert "Fictional event 64" in result["text"]
    assert [call["args"].get("offset", 0) for call in result["calls"]] == [0, 30, 60]


def test_studio_panel_field_change_revokes_confirmation_before_local_submit():
    result = events(
        """
const ui=fixture(source);await ui.panel.open({form:'capture'});let refused=false;try{await ui.button('Registra il salvataggio locale').action();}catch(error){refused=true;}
ui.confirm().checked=true;ui.field('Titolo').value='Fictional task';ui.field('Titolo').dispatch('input');const cleared=!ui.confirm().checked;await ui.panel.flush();ui.confirm().checked=true;await ui.button('Registra il salvataggio locale').action();
process.stdout.write(JSON.stringify({refused,cleared,calls:ui.calls,draft:ui.drafts.capture,confirm:ui.confirm().checked,text:ui.text()}));
"""
    )
    assert result["refused"] is True
    assert result["cleared"] is True
    submits = [call for call in result["calls"] if call["name"].endswith("_submit")]
    assert len(submits) == 1
    assert submits[0]["args"]["human_confirmed"] is True
    assert "fields" not in submits[0]["args"]
    assert result["draft"]["state"] == "completed"
    assert result["confirm"] is False


def test_studio_panel_uncertain_local_save_blocks_second_submit_then_recovers():
    result = events(
        """
const ui=fixture(source,{submit_error:true});await ui.panel.open({form:'capture'});ui.field('Titolo').value='Fictional task';ui.field('Titolo').dispatch('input');await ui.panel.flush();ui.confirm().checked=true;try{await ui.button('Registra il salvataggio locale').action();}catch(error){}
let refused=false;try{await ui.button('Registra il salvataggio locale').action();}catch(error){refused=true;}
await ui.button('Rileggi la ricevuta locale').action();await ui.button('Recupera il salvataggio locale').action();process.stdout.write(JSON.stringify({refused,calls:ui.calls,draft:ui.drafts.capture}));
"""
    )
    assert result["refused"] is True
    assert (
        len([call for call in result["calls"] if call["name"].endswith("_submit")]) == 1
    )
    assert (
        len([call for call in result["calls"] if call["name"].endswith("_recover")])
        == 1
    )
    assert result["draft"]["state"] == "completed"


def test_studio_panel_stale_fields_require_explicit_private_discard():
    result = events(
        """
const ui=fixture(source,{stale:true,fields:{notes:'Older fictional fields'}});await ui.panel.open({form:'capture'});const disabled=ui.field('Appunti').disabled;let refused=false;try{await ui.button('Scarta soltanto la bozza privata').action();}catch(error){refused=true;}ui.discard().checked=true;await ui.button('Scarta soltanto la bozza privata').action();process.stdout.write(JSON.stringify({disabled,refused,fields:ui.drafts.capture.fields,calls:ui.calls,text:ui.text()}));
"""
    )
    assert result["disabled"] is True
    assert result["refused"] is True
    assert result["fields"] == {}
    assert not any(call["name"].endswith("_submit") for call in result["calls"])


def test_studio_panel_meeting_actions_are_literal_partial_fields():
    result = events(
        """
const ui=fixture(source);await ui.panel.open({form:'meeting'});ui.field('Sintesi').value='FICTIONAL SUPPLIED SUMMARY';ui.field('Sintesi').dispatch('input');await ui.button('Aggiungi impegno dalla riunione').action();const title=ui.fields('Titolo').at(-1);title.value='Fictional follow-up';title.dispatch('input');await ui.panel.flush();process.stdout.write(JSON.stringify({fields:ui.drafts.meeting.fields,calls:ui.calls}));
"""
    )
    assert result["fields"] == {
        "meeting": {"summary": "FICTIONAL SUPPLIED SUMMARY"},
        "actions": [{"title": "Fictional follow-up"}],
    }
    assert not any(call["name"].endswith("_submit") for call in result["calls"])


def test_studio_panel_selected_discussion_sends_only_reference_and_revision():
    result = events(
        """
const items=[{id:'fictional-item',title:'PRIVATE FICTIONAL TITLE',source:'PRIVATE FICTIONAL SOURCE',notes:'PRIVATE FICTIONAL NOTE',status:'open'}];const ui=fixture(source,{items});await ui.panel.open();await ui.button('Discuti questa voce con Vera').action();process.stdout.write(JSON.stringify({chat:ui.chat,text:ui.text(),calls:ui.calls}));
"""
    )
    message = result["chat"][0]
    assert "fictional-item" in message
    assert "fictional-scope" in message
    assert "PRIVATE FICTIONAL" not in message
    assert "non autorizza" in message
    assert "PRIVATE FICTIONAL NOTE" in result["text"]


def test_studio_panel_completed_save_displays_current_receipt_without_draft_warning():
    result = events(
        """
const ui=fixture(source);await ui.panel.open({form:'capture'});ui.field('Titolo').value='Fictional task';ui.field('Titolo').dispatch('input');await ui.panel.flush();ui.confirm().checked=true;await ui.button('Registra il salvataggio locale').action();process.stdout.write(JSON.stringify({text:ui.text(),messages:ui.messages}));
"""
    )
    assert "Salvataggio locale conservato" in result["text"]
    assert "Il registro è cambiato" not in result["text"]
    assert (
        result["messages"][-1]["text"]
        == "Salvataggio locale conservato e riletto. Nessuna operazione calendario eseguita."
    )
