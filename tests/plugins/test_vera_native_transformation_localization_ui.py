"""Localized fictional UI events; never model or installed-host acceptance."""

from __future__ import annotations

import json

import pytest

from tests.plugins.test_vera_native_transformation_author_ui import FIXTURE
from tests.plugins.test_vera_native_transformation_initial_ui import (
    events as initial_events,
)
from tests.plugins.test_vera_native_transformation_ui import events

__all__ = []

LANGUAGES = [
    ("it", "Preparazione e riesame", "Quali dati arrivano al modello"),
    ("en", "Preparation and review", "What data reaches the model"),
    ("fr", "Préparation et révision", "Quelles données parviennent au modèle"),
    ("de", "Vorbereitung und Prüfung", "Welche Daten das Modell erhält"),
    ("es", "Preparación y revisión", "Qué datos llegan al modelo"),
]


@pytest.mark.parametrize("language,heading,footer", LANGUAGES)
def test_localized_case_retains_literal_records_all_alternatives_and_wire_fields(
    language, heading, footer
):
    result = events(
        """
const ui=fixture(source);ui.page.data.state.records.finding.F1={statement:'Domanda autorizzata',amount:'00019.00',rationale:null,confidence:'',alternatives:Array.from({length:73},(_,i)=>'FICTIONAL-'+i),unknown_source_key:'<literal source text>'};
await ui.panel.open('fictional-transform');
const op=ui.field('Passaggio sintetico');op.value='put';op.dispatch('change');
const raw=ui.field('Proposta JSON completa · nessuna decisione implicita');raw.value=' { "statement": "Nome" } ';raw.dispatch('input');
ui.field(confirm).checked=true;
"""
        + f"await ui.panel.setLanguage({json.dumps(language)});"
        + """
const all=root=>[root,...root.children.flatMap(all)],nodes=all(ui.tree());
process.stdout.write(JSON.stringify({language:ui.panel.language(),lang:ui.tree().attributes.lang,fields:ui.page.fields,checked:nodes.filter(n=>n.tagName==='INPUT'&&n.checked).length,text:ui.text(),items:nodes.filter(n=>n.tagName==='LI').length,footer:ui.tree().children.at(-2).text,calls:ui.calls}));
"""
    )
    assert result["language"] == result["lang"] == language
    assert heading in result["text"]
    assert result["footer"] == footer
    assert result["fields"]["operation"] == "put"
    assert result["fields"]["record_json"] == ' { "statement": "Nome" } '
    assert result["checked"] == 0
    assert result["items"] == 79
    assert "Domanda autorizzata" in result["text"]
    assert "00019.00" in result["text"]
    assert "FICTIONAL-72" in result["text"]
    assert "unknown_source_key" in result["text"]
    assert "<literal source text>" in result["text"]
    assert not any(c["name"].endswith("_execute") for c in result["calls"])


@pytest.mark.parametrize("language,heading,footer", LANGUAGES)
def test_language_switch_preserves_initial_owner_without_creation_or_consent(
    language, heading, footer
):
    result = initial_events(
        "const ui=fixture(source,initial);await ui.panel.openInitial('fictional-transform');const owner=ui.field('Proprietario dichiarato del prototipo');owner.value='  Nome  ';owner.dispatch('input');ui.field(confirm).checked=true;"
        + f"await ui.panel.setLanguage({json.dumps(language)});"
        + "const nodes=root=>[root,...root.children.flatMap(nodes)];process.stdout.write(JSON.stringify({fields:ui.page.fields,language:ui.panel.language(),checked:nodes(ui.tree()).filter(n=>n.checked).length,footer:ui.tree().children.at(-2).text,calls:ui.calls}));"
    )
    assert result["fields"] == {"owner": "  Nome  ", "purpose": ""}
    assert result["language"] == language
    assert result["checked"] == 0
    assert result["footer"] == footer
    assert not any(c["name"].endswith("_create") for c in result["calls"])


@pytest.mark.parametrize("language,heading,footer", LANGUAGES)
def test_language_switch_preserves_question_and_source_refs_without_model_grant(
    language, heading, footer
):
    result = events(
        FIXTURE
        + """
const ui=authorFixture();ui.page.data.sources=[{source_ref:'fictional-selected',name:'Nome',sha256:'a'.repeat(64)}];
await ui.panel.openAuthor('fictional-transform');const question=ui.field('Domanda sulla dimostrazione sintetica');question.value='  Domanda autorizzata  ';question.dispatch('input');
const operation=ui.field('Proposta richiesta alla chat');operation.value='import_evidence';operation.dispatch('change');const selected=ui.field('Nome · fictional-selected');selected.checked=true;selected.dispatch('change');ui.field(consent).checked=true;
"""
        + f"await ui.panel.setLanguage({json.dumps(language)});"
        + """
const nodes=root=>[root,...root.children.flatMap(nodes)];const inputs=nodes(ui.tree()).filter(n=>n.tagName==='INPUT');
process.stdout.write(JSON.stringify({fields:ui.page.fields,selected:ui.field('Nome · fictional-selected').checked,confirmed:inputs.filter(n=>n.checked).length,footer:ui.tree().children.at(-2).text,calls:ui.calls,text:ui.text()}));
"""
    )
    assert result["fields"] == {
        "question": "  Domanda autorizzata  ",
        "operation": "import_evidence",
        "source_refs": ["fictional-selected"],
    }
    assert result["selected"] is True
    assert result["confirmed"] == 1  # Selected source only, never model authorization.
    assert result["footer"] == footer
    assert "Nome" in result["text"]
    assert "a" * 64 in result["text"]
    assert not any(c["name"].endswith("_request") for c in result["calls"])


@pytest.mark.parametrize("language,heading,footer", LANGUAGES)
def test_localized_prepared_request_retains_protocol_and_does_not_resend(
    language, heading, footer
):
    result = events(
        FIXTURE
        + f"const ui=authorFixture({{language:{json.dumps(language)},question:'Nome',selected_sources:[],status:'open',grant_ref:'fictional-grant',pending_operations:false,request_prepared:true,can_prepare_request:false}});"
        + """
await ui.panel.openMandate('fictional-transform','fictional-grant');
const nodes=root=>[root,...root.children.flatMap(nodes)];const request=nodes(ui.tree()).find(n=>n.tagName==='TEXTAREA'&&n.readOnly);
process.stdout.write(JSON.stringify({prompt:request.value,footer:ui.tree().children.at(-2).text,calls:ui.calls,text:ui.text(),buttons:nodes(ui.tree()).filter(n=>n.tagName==='BUTTON').map(n=>({text:n.text,disabled:n.disabled}))}));
"""
    )
    assert result["footer"] == footer
    assert '"work_ref":"fictional-transform"' in result["prompt"]
    assert '"grant_ref":"fictional-grant"' in result["prompt"]
    assert "vera_workspace_transformation_author_context" in result["prompt"]
    assert "vera_workspace_transformation_author_stage" in result["prompt"]
    assert "expected_stage_revision" in result["prompt"]
    assert "idempotency_key" in result["prompt"]
    assert "submit/review/export" in result["prompt"]
    assert "Nome" in result["text"]
    assert [c["name"] for c in result["calls"]] == [
        "vera_workspace_transformation_author_read"
    ]


@pytest.mark.parametrize("language,heading,footer", LANGUAGES)
def test_localized_viewer_controls_stay_disabled(language, heading, footer):
    result = events(
        f"const ui=fixture(source,{{language:{json.dumps(language)},can_write:false}});await ui.panel.open('fictional-transform');const nodes=root=>[root,...root.children.flatMap(nodes)];process.stdout.write(JSON.stringify({{controls:nodes(ui.tree()).filter(n=>n.tagName==='TEXTAREA').map(n=>n.disabled),footer:ui.tree().children.at(-2).text,text:ui.text(),calls:ui.calls}}));"
    )
    assert all(result["controls"])
    assert result["footer"] == footer
    assert heading in result["text"]
    assert [c["name"] for c in result["calls"]] == [
        "vera_workspace_transformation_setup"
    ]


def test_unknown_language_is_refused_without_changing_view_or_saving_fields():
    result = events(
        "const ui=fixture(source,{language:'unknown'});await ui.panel.open('fictional-transform');let error='';try{await ui.panel.setLanguage('unknown');}catch(e){error=e.message;}process.stdout.write(JSON.stringify({error,language:ui.panel.language(),text:ui.text(),calls:ui.calls}));"
    )
    assert result["error"] == "Lingua del pannello non supportata."
    assert result["language"] == "it"
    assert "Preparazione e riesame" in result["text"]
    assert [c["name"] for c in result["calls"]] == [
        "vera_workspace_transformation_setup"
    ]
