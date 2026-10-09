"""Declared fictional component events, never native-host or browser validation."""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []
CONFIRM = "Ho controllato questa voce completa e confermo la decisione espressa"


def events(body):
    fixture = ROOT / "tests/plugins/browser_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/browser.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};const confirm={json.dumps(CONFIRM)};(async()=>{{{body}}})().catch(e=>{{process.stderr.write(e.stack);process.exitCode=1;}});"
    result = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_browser_ui_restores_private_fields_without_restoring_confirmation():
    result = events(
        "const ui=fixture(source);await ui.panel.openEntry('fictional-batch','invoice-1');ui.field(confirm).checked=true;const note=ui.field('Nota effettiva del professionista');note.value='  Literal incomplete note  ';note.dispatch('input');await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({fields:ui.page.fields,checked:ui.field(confirm).checked,calls:ui.calls}));"
    )
    assert result["fields"]["note"] == "  Literal incomplete note  "
    assert result["checked"] is False
    assert not any(c["name"].endswith("_review_commit") for c in result["calls"])


def test_browser_ui_explicit_correction_request_keeps_complete_entry_visible():
    result = events(
        "const ui=fixture(source);await ui.panel.openEntry('fictional-batch','invoice-1');const decision=ui.field('Decisione espressa sul controllo'),note=ui.field('Nota effettiva del professionista');decision.value='correction_requested';decision.dispatch('change');note.value='Actual fictional request';note.dispatch('input');let denied=false;try{await ui.button('Registra controllo').action();}catch(e){denied=true;}const text=ui.text();ui.field(confirm).checked=true;await ui.button('Registra controllo').action();process.stdout.write(JSON.stringify({denied,text,calls:ui.calls}));"
    )
    assert result["denied"] is True
    assert "Fictional proposed account" in result["text"]
    assert "Fictional observed posting" in result["text"]
    committed = next(c for c in result["calls"] if c["name"].endswith("_review_commit"))
    assert committed["args"]["fields"]["decision"] == "correction_requested"
    assert committed["args"]["confirmed"] is True


def test_browser_ui_changed_note_clears_current_confirmation():
    result = events(
        "const ui=fixture(source);await ui.panel.openEntry('fictional-batch','invoice-1');ui.field(confirm).checked=true;const note=ui.field('Nota effettiva del professionista');note.value='Changed note';note.dispatch('input');process.stdout.write(JSON.stringify({checked:ui.field(confirm).checked,calls:ui.calls}));"
    )
    assert result["checked"] is False
    assert not any(c["name"].endswith("_review_commit") for c in result["calls"])


def test_browser_ui_viewer_and_uncertain_write_keep_records_readable():
    result = events(
        "const viewer=fixture(source,{can_write:false});await viewer.panel.openEntry('fictional-batch','invoice-1');const disabled=viewer.button('Registra controllo').disabled;const uncertain=fixture(source,{pending_operations:['uncertain']});await uncertain.panel.openEntry('fictional-batch','invoice-1');process.stdout.write(JSON.stringify({disabled,uncertainDisabled:uncertain.button('Registra controllo').disabled,text:uncertain.text(),calls:uncertain.calls}));"
    )
    assert result["disabled"] is True
    assert result["uncertainDisabled"] is True
    assert "scrittura precedente è incerta" in result["text"]
    assert "Fictional complete line" in result["text"]


def test_browser_ui_stale_draft_discard_requires_explicit_confirmation():
    result = events(
        "const ui=fixture(source,{draft_stale:true});await ui.panel.openEntry('fictional-batch','invoice-1');let denied=false;try{await ui.button('Scarta campi privati').action();}catch(e){denied=true;}ui.field('Scarto soltanto i campi privati precedenti; conservo fatture e controlli').checked=true;await ui.button('Scarta campi privati').action();process.stdout.write(JSON.stringify({denied,calls:ui.calls}));"
    )
    assert result["denied"] is True
    cleared = next(c for c in result["calls"] if c["name"].endswith("_draft_clear"))
    assert cleared["args"]["expected_draft_revision"] == "initial"
    assert cleared["args"]["confirmed"] is True


def test_browser_ui_process_progress_refresh_keeps_same_readonly_work():
    result = events(
        "const ui=fixture(source,{kind:'process',data:{process:{description:{process:{name:'Fictional teaching',objective:'Fictional goal'}},available_in_qualified_environment:false},attempts:[{evidence:{result:'unfinished'}}]}});await ui.panel.open('fictional-process');await ui.panel.refresh();process.stdout.write(JSON.stringify({active:ui.panel.active(),text:ui.text(),calls:ui.calls}));"
    )
    assert result["active"] is True
    assert "Collaudo dell’ambiente da completare" in result["text"]
    assert [c["name"] for c in result["calls"]] == ["vera_workspace_browser_setup"] * 2
    assert "Quali dati arrivano al modello" in result["text"]


def test_browser_ui_labels_identify_controls_and_explain_incomplete_save():
    result = events(
        "const ui=fixture(source);await ui.panel.openEntry('fictional-batch','invoice-1');const elements=ui.elements();const select=ui.field('Decisione espressa sul controllo'),note=ui.field('Nota effettiva del professionista');process.stdout.write(JSON.stringify({labels:elements.filter(e=>e.tagName==='LABEL'&&e.attributes.for).map(e=>({text:e.text,for:e.attributes.for})),controls:[select,note].map(e=>({id:e.attributes.id,help:e.attributes['aria-describedby']})),help:elements.find(e=>e.attributes.id===note.attributes['aria-describedby']).text,calls:ui.calls}));"
    )
    assert result["labels"] == [
        {
            "text": "Decisione espressa sul controllo",
            "for": result["controls"][0]["id"],
        },
        {
            "text": "Nota effettiva del professionista",
            "for": result["controls"][1]["id"],
        },
    ]
    assert result["controls"][0]["id"] != result["controls"][1]["id"]
    assert result["controls"][0]["help"] == result["controls"][1]["help"]
    assert "conservare campi incompleti" in result["help"]
    assert "nuova conferma" in result["help"]
    assert not any(c["name"].endswith("_review_commit") for c in result["calls"])


def test_browser_ui_complete_record_distinguishes_empty_and_exact_source_values():
    result = events(
        "const entry={id:'invoice-1',document:'Fictional invoice',status:'completed',posting_reference:'  001/A  ',correction_of:'',question:'',proposed:[{label:'Fictional source label',value:'00019.00',source:'<img src=x onerror=alert(1)>'}],actual:[],evidence:[],reason:null,extra_declared_field:'Retain this unfamiliar value'};const ui=fixture(source,{entry});await ui.panel.openEntry('fictional-batch','invoice-1');process.stdout.write(JSON.stringify({text:ui.text(),tags:ui.elements().map(e=>e.tagName),headings:ui.elements().filter(e=>e.tagName==='DT').map(e=>e.text)}));"
    )
    assert "Riferimento della registrazione" in result["headings"]
    assert "Registrazione rettificata" in result["headings"]
    assert "  001/A  " in result["text"]
    assert "00019.00" in result["text"]
    assert "<img src=x onerror=alert(1)>" in result["text"]
    assert "IMG" not in result["tags"]
    assert "Campo vuoto" in result["text"]
    assert "Non indicato" in result["text"]
    assert "Nessuna voce conservata." in result["text"]
    assert "extra_declared_field" in result["headings"]
    assert "Retain this unfamiliar value" in result["text"]


def test_browser_ui_complete_long_evidence_keeps_last_value_and_source():
    result = events(
        "const evidence=Array.from({length:73},(_,index)=>({label:'Evidence '+index,value:'Value '+index,source:'Source '+index}));const ui=fixture(source,{entry:{id:'invoice-1',document:'Fictional invoice',status:'completed',evidence}});await ui.panel.openEntry('fictional-batch','invoice-1');process.stdout.write(JSON.stringify({text:ui.text(),listItems:ui.elements().filter(e=>e.tagName==='LI').length,calls:ui.calls}));"
    )
    assert result["listItems"] == 73
    assert "Evidence 72" in result["text"]
    assert "Value 72" in result["text"]
    assert "Source 72" in result["text"]
    assert not any(c["name"].endswith("_review_commit") for c in result["calls"])


def test_browser_ui_batch_row_buttons_name_the_exact_document():
    result = events(
        "const entries=[{id:'one',document:'Invoice Alpha',status:'completed',outcome:'Result one'},{id:'two',document:'Invoice Beta',status:'failed',outcome:'Result two'}];const ui=fixture(source,{data:{record:{payload:{entries,reviews:[],title:'Fictional batch',scope:'Fictional scope',expected_items:2},revision:1},history:[]}});await ui.panel.open('fictional-batch');process.stdout.write(JSON.stringify({names:ui.elements().filter(e=>e.tagName==='BUTTON'&&e.text==='Esamina e controlla voce').map(e=>e.attributes['aria-label']),calls:ui.calls}));"
    )
    assert result["names"] == [
        "Esamina e controlla Invoice Alpha",
        "Esamina e controlla Invoice Beta",
    ]
    assert [c["name"] for c in result["calls"]] == ["vera_workspace_browser_setup"]


@pytest.mark.parametrize(
    ("language", "footer", "posting_label", "record_button"),
    [
        (
            "it",
            "Quali dati arrivano al modello",
            "Riferimento della registrazione",
            "Registra controllo",
        ),
        ("en", "What data reaches the model", "Posting reference", "Record review"),
        (
            "fr",
            "Quelles données parviennent au modèle",
            "Référence de l’écriture",
            "Enregistrer le contrôle",
        ),
        (
            "de",
            "Welche Daten gelangen zum Modell",
            "Buchungsreferenz",
            "Prüfung erfassen",
        ),
        (
            "es",
            "Qué datos llegan al modelo",
            "Referencia del asiento",
            "Registrar revisión",
        ),
    ],
)
def test_browser_ui_language_changes_copy_but_preserves_actual_decision(
    language, footer, posting_label, record_button
):
    result = events(
        f"const ui=fixture(source,{{fields:{{decision:'correction_requested',note:'  Nota originale del professionista  '}},entry:{{id:'invoice-1',document:'Original invoice 001/A',status:'completed',posting_reference:'  001/A  ',evidence:[{{label:'Original source label',value:'00019.00',source:'Original source reference'}}]}}}},{{language:{json.dumps(language)}}});await ui.panel.openEntry('fictional-batch','invoice-1');const all=ui.elements(),check=all.find(e=>e.tagName==='INPUT');let denied=false;try{{await ui.button({json.dumps(record_button)}).action();}}catch(e){{denied=true;}}const text=ui.text();check.checked=true;await ui.button({json.dumps(record_button)}).action();process.stdout.write(JSON.stringify({{language:ui.panel.language(),text,denied,fields:ui.page.fields,calls:ui.calls}}));"
    )
    assert result["language"] == language
    assert footer in result["text"]
    assert posting_label in result["text"]
    assert "  001/A  " in result["text"]
    assert "00019.00" in result["text"]
    assert "Original source label" in result["text"]
    assert "Original source reference" in result["text"]
    assert "artifact_only" in result["text"]
    assert result["denied"] is True
    committed = next(c for c in result["calls"] if c["name"].endswith("_review_commit"))
    assert committed["args"]["fields"] == {
        "decision": "correction_requested",
        "note": "  Nota originale del professionista  ",
    }
    assert committed["args"]["confirmed"] is True


def test_browser_ui_switch_language_saves_incomplete_fields_and_reopens_same_entry():
    result = events(
        "const ui=fixture(source);await ui.panel.openEntry('fictional-batch','invoice-1');const note=ui.field('Nota effettiva del professionista');note.value='  Original unfinished note  ';note.dispatch('input');ui.field(confirm).checked=true;await ui.panel.setLanguage('fr');const all=ui.elements();process.stdout.write(JSON.stringify({language:ui.panel.language(),fields:ui.page.fields,confirmed:all.find(e=>e.tagName==='INPUT').checked,text:ui.text(),calls:ui.calls}));"
    )
    assert result["language"] == "fr"
    assert result["fields"] == {"decision": "", "note": "  Original unfinished note  "}
    assert result["confirmed"] is False
    assert "Quelles données parviennent au modèle" in result["text"]
    assert [c["name"] for c in result["calls"]] == [
        "vera_workspace_browser_read",
        "vera_workspace_browser_draft_save",
        "vera_workspace_browser_read",
    ]
    assert result["calls"][-1]["args"] == {
        "work_ref": "fictional-batch",
        "item_id": "invoice-1",
    }


def test_browser_ui_language_save_failure_keeps_original_context_and_unfinished_fields():
    result = events(
        "const ui=fixture(source,{}, {failSave:true});await ui.panel.openEntry('fictional-batch','invoice-1');const note=ui.field('Nota effettiva del professionista');note.value='Unsaved original note';note.dispatch('input');let denied=false;try{await ui.panel.setLanguage('en');}catch(e){denied=true;}process.stdout.write(JSON.stringify({denied,language:ui.panel.language(),note:ui.field('Nota effettiva del professionista').value,calls:ui.calls}));"
    )
    assert result["denied"] is True
    assert result["language"] == "it"
    assert result["note"] == "Unsaved original note"
    assert [c["name"] for c in result["calls"]] == [
        "vera_workspace_browser_read",
        "vera_workspace_browser_draft_save",
    ]


def test_browser_ui_language_selector_and_refresh_preserve_selected_readonly_process():
    result = events(
        "const ui=fixture(source,{kind:'process',data:{process:{description:{process:{name:'Original process name',objective:'Original process objective'}},available_in_qualified_environment:false},attempts:[]}});await ui.panel.open('fictional-process');const select=ui.field('Lingua del pannello');select.value='de';await select.dispatch('change');await ui.panel.refresh();process.stdout.write(JSON.stringify({language:ui.panel.language(),active:ui.panel.active(),text:ui.text(),calls:ui.calls}));"
    )
    assert result["language"] == "de"
    assert result["active"] is True
    assert "Original process name" in result["text"]
    assert "Original process objective" in result["text"]
    assert "Die Qualifizierung der Umgebung ist noch abzuschließen." in result["text"]
    assert [c["args"] for c in result["calls"]] == [
        {"work_ref": "fictional-process"},
        {"work_ref": "fictional-process"},
        {"work_ref": "fictional-process"},
    ]


def test_browser_ui_unsupported_language_preserves_selected_record_without_a_write():
    result = events(
        "const ui=fixture(source);await ui.panel.openEntry('fictional-batch','invoice-1');let denied=false;try{await ui.panel.setLanguage('xx');}catch(e){denied=true;}process.stdout.write(JSON.stringify({denied,language:ui.panel.language(),active:ui.panel.active(),calls:ui.calls}));"
    )
    assert result["denied"] is True
    assert result["language"] == "it"
    assert result["active"] is True
    assert [c["name"] for c in result["calls"]] == ["vera_workspace_browser_read"]
