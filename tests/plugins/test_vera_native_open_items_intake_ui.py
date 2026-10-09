"""Fictional native panel events; actual host acceptance remains separate."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []

CONFIRM = "Ho riesaminato tutti i documenti, le convenzioni e i criteri. Prepara gli elaborati da rivedere"
DISCARD = "Scarta soltanto le mie scelte incomplete dopo il confronto con i documenti correnti"


def events(body: str) -> dict:
    """Execute real panel source against an explicit fictional transport."""
    fixture = ROOT / "tests/plugins/open_items_intake_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/open-items-intake.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};const confirm={json.dumps(CONFIRM)};const discard={json.dumps(DISCARD)};(async()=>{{{body}}})().catch(error=>{{process.stderr.write(error.stack);process.exitCode=1;}});"
    result = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_open_items_panel_preserves_partial_literal_fields_without_defaults_or_consent():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-intake');ui.field(confirm).checked=true;
const currency=ui.field('Valuta del confronto');currency.value='CHF';currency.dispatch('input');
const note=ui.field('Nota da conservare negli elaborati');note.value='  FICTIONAL PRIVATE NOTE  ';note.dispatch('input');
await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({draft:ui.draft,consent:ui.field(confirm).checked,calls:ui.calls,dirty:ui.dirty,text:ui.text()}));
"""
    )
    assert result["draft"]["fields"] == {
        "currency": "CHF",
        "narrative": "  FICTIONAL PRIVATE NOTE  ",
    }
    assert result["consent"] is False
    assert result["dirty"] is False
    assert not any(call["name"].endswith("_prepare") for call in result["calls"])
    assert "Quali dati arrivano al modello" in result["text"]


def test_open_items_panel_all_source_pages_are_available_without_assigning_roles():
    result = events(
        """
const items=Array.from({length:35},(_,index)=>({id:'SOURCE-'+index,title:'original-'+index+'.pdf',kind:'.pdf'}));
const ui=fixture(source,{items});await ui.panel.open('fictional-intake');await ui.button('Altri documenti →').action();
process.stdout.write(JSON.stringify({text:ui.text(),fields:ui.draft.fields,calls:ui.calls}));
"""
    )
    assert "original-34.pdf" in result["text"]
    assert result["fields"] == {}
    assert [call["args"].get("offset", 0) for call in result["calls"]] == [0, 30]


def test_open_items_panel_source_decisions_remain_separate_and_literal():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-intake');
for(const [label,value] of [['Ruolo del documento · fictional-source-0.pdf','open_items'],['Ruolo del documento · fictional-source-1.pdf','bank_statement'],['Separatore delle migliaia · fictional-source-0.pdf','none'],['Ordine delle date · fictional-source-0.pdf','month_first'],['Trattare una disposizione di pagamento come evidenza bancaria','false']]){const input=ui.field(label);input.value=value;input.dispatch('change');}
await ui.panel.flush();process.stdout.write(JSON.stringify(ui.draft.fields));
"""
    )
    assert result == {
        "sources": {
            "SOURCE-0": {
                "role": "open_items",
                "money": {"thousands_separator": ""},
                "date": {"order": "month_first"},
            },
            "SOURCE-1": {"role": "bank_statement"},
        },
        "payment_orders_are_bank_evidence": False,
    }


def test_open_items_panel_requires_renewed_confirmation_then_hands_back_to_review():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-intake');let refused=false;
try{await ui.button('Prepara gli elaborati delle partite').action();}catch(error){refused=true;}
ui.field(confirm).checked=true;await ui.button('Prepara gli elaborati delle partite').action();await ui.button('Apri la revisione delle partite').action();
process.stdout.write(JSON.stringify({refused,calls:ui.calls,opened:ui.opened,consent:ui.field(confirm).checked,disabled:ui.button('Prepara gli elaborati delle partite').disabled,text:ui.text()}));
"""
    )
    assert result["refused"] is True
    prepared = [call for call in result["calls"] if call["name"].endswith("_prepare")]
    assert len(prepared) == 1
    assert prepared[0]["args"]["human_reviewed"] is True
    assert prepared[0]["args"]["expected_draft_revision"] == "initial-draft"
    assert result["opened"] == ["fictional-intake"]
    assert result["consent"] is False
    assert result["disabled"] is True
    assert "Restano rilievi" in result["text"]


def test_open_items_panel_uncertain_request_prevents_repeated_execution():
    result = events(
        """
const ui=fixture(source,{prepare_error:true});await ui.panel.open('fictional-intake');ui.field(confirm).checked=true;
try{await ui.button('Prepara gli elaborati delle partite').action();}catch(error){}
let refused=false;try{await ui.button('Prepara gli elaborati delle partite').action();}catch(error){refused=true;}
await ui.panel.refresh();process.stdout.write(JSON.stringify({refused,calls:ui.calls,disabled:ui.button('Prepara gli elaborati delle partite').disabled,text:ui.text()}));
"""
    )
    assert result["refused"] is True
    assert (
        len([call for call in result["calls"] if call["name"].endswith("_prepare")])
        == 1
    )
    assert result["disabled"] is True
    assert "non ripete il calcolo" in result["text"]


def test_open_items_panel_stale_private_choices_require_explicit_discard():
    result = events(
        """
const ui=fixture(source,{stale:true,fields:{currency:'CHF'}});await ui.panel.open('fictional-intake');let refused=false;
try{await ui.button('Scarta le scelte incomplete').action();}catch(error){refused=true;}
ui.field(discard).checked=true;await ui.button('Scarta le scelte incomplete').action();
process.stdout.write(JSON.stringify({refused,calls:ui.calls,fields:ui.draft.fields,consent:ui.field(confirm).checked}));
"""
    )
    assert result["refused"] is True
    assert result["fields"] == {}
    assert result["consent"] is False
    cleared = next(call for call in result["calls"] if call["name"].endswith("_clear"))
    assert cleared["args"]["expected_draft_revision"] == "initial-draft"


def test_open_items_panel_viewer_keeps_source_reading_without_write_controls():
    result = events(
        """
const ui=fixture(source,{can_prepare:false,can_discard:false});await ui.panel.open('fictional-intake');await ui.button('Consulta questo originale').action();
process.stdout.write(JSON.stringify({writeDisabled:ui.button('Prepara gli elaborati delle partite').disabled,discardDisabled:ui.button('Scarta le scelte incomplete').disabled,fieldDisabled:ui.field('Valuta del confronto').disabled,calls:ui.calls,urls:ui.urls.length,text:ui.text()}));
"""
    )
    assert result["writeDisabled"] is True
    assert result["discardDisabled"] is True
    assert result["fieldDisabled"] is True
    assert result["urls"] == 1
    assert [call["name"] for call in result["calls"]] == [
        "vera_workspace_open_items_intake_setup",
        "vera_workspace_open_items_intake_source",
    ]


def test_open_items_panel_wrong_source_hash_never_creates_download():
    result = events(
        """
const ui=fixture(source,{tampered_source:true});await ui.panel.open('fictional-intake');let refused=false;
try{await ui.button('Consulta questo originale').action();}catch(error){refused=true;}
process.stdout.write(JSON.stringify({refused,urls:ui.urls.length,calls:ui.calls}));
"""
    )
    assert result["refused"] is True
    assert result["urls"] == 0


def test_open_items_panel_failed_draft_can_be_explicitly_discarded_without_save_loop():
    result = events(
        """
const ui=fixture(source,{save_error:true});await ui.panel.open('fictional-intake');const currency=ui.field('Valuta del confronto');currency.value='CHF';currency.dispatch('input');
try{await ui.panel.flush();}catch(error){}
ui.field(discard).checked=true;await ui.button('Scarta le scelte incomplete').action();
process.stdout.write(JSON.stringify({fields:ui.draft.fields,calls:ui.calls,dirty:ui.dirty}));
"""
    )
    assert result["fields"] == {}
    assert result["dirty"] is False
    assert (
        len([call for call in result["calls"] if call["name"].endswith("_save")]) == 1
    )
