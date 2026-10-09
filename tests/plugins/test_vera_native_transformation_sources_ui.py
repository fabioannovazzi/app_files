"""Fictional source-editor events and semantic DOM, not native-host acceptance."""

from __future__ import annotations

import json

import pytest

from tests.plugins.test_vera_native_transformation_ui import events

__all__ = []

PREPARE = """
const ui=fixture(source);
ui.page.data.sources=[{source_ref:'fictional-a',name:'Synthetic A.txt',sha256:'a'.repeat(64)},{source_ref:'fictional-b',name:'Synthetic B.txt',sha256:'b'.repeat(64)}];
await ui.panel.open('fictional-transform');
const op=ui.field('Passaggio sintetico');op.value='import_evidence';op.dispatch('change');
"""


def test_source_editor_exact_literal_partial_fields_recover_without_consent():
    result = events(
        PREPARE
        + """
const id=ui.field('Identificativo dell’evidenza');id.value='  FICTIONAL_E1  ';id.dispatch('input');
const pick=ui.field('Fonte sintetica collegata');pick.value='fictional-b';pick.dispatch('change');
const origin=ui.field('Origine dichiarata della fonte');origin.value='  Declared synthetic origin  ';origin.dispatch('input');
await ui.panel.flush();await ui.panel.refresh();
process.stdout.write(JSON.stringify({fields:ui.page.fields,record:JSON.parse(ui.page.fields.record_json),pick:ui.field('Fonte sintetica collegata').value,confirmed:ui.field(confirm).checked,calls:ui.calls}));
"""
    )
    assert result["record"] == {
        "id": "  FICTIONAL_E1  ",
        "source_ref": "fictional-b",
        "origin": "  Declared synthetic origin  ",
        "locator": "",
    }
    assert result["pick"] == "fictional-b"
    assert result["confirmed"] is False
    assert result["fields"]["actor"] == ""
    assert not any(call["name"].endswith("_execute") for call in result["calls"])


def test_source_editor_requires_user_selection_and_shows_complete_file_hashes():
    result = events(
        PREPARE
        + """
const pick=ui.field('Fonte sintetica collegata');
process.stdout.write(JSON.stringify({value:pick.value,choices:pick.children.map(option=>option.value),raw:ui.page.fields.record_json,text:ui.text()}));
"""
    )
    assert result["value"] == ""
    assert result["choices"] == ["", "fictional-a", "fictional-b"]
    assert result["raw"] == ""
    assert "a" * 64 in result["text"]
    assert "b" * 64 in result["text"]


def test_source_editor_change_withdraws_confirmation_and_exact_execution_fields():
    result = events(
        PREPARE
        + """
ui.field(confirm).checked=true;const pick=ui.field('Fonte sintetica collegata');pick.value='fictional-a';pick.dispatch('change');await ui.panel.flush();
let refused=false;try{await ui.button('Esegui e conserva il passaggio sintetico').action();}catch(error){refused=true;}
process.stdout.write(JSON.stringify({refused,confirmed:ui.field(confirm).checked,calls:ui.calls}));
"""
    )
    assert result["refused"] is True
    assert result["confirmed"] is False
    assert not any(call["name"].endswith("_execute") for call in result["calls"])


@pytest.mark.parametrize(
    "literal",
    [
        ' { "id": ',
        '{"id":"keep","source_ref":"fictional-a","origin":"keep","locator":"keep","extra":"preserve"}',
        '{"id":null,"source_ref":"fictional-a","origin":"keep","locator":"keep"}',
        "[]",
    ],
)
def test_source_editor_preserves_unfinished_or_different_complete_proposal(literal):
    result = events(
        PREPARE
        + f"const raw=ui.field('Proposta JSON completa · nessuna decisione implicita');raw.value={json.dumps(literal)};raw.dispatch('input');await ui.panel.flush();process.stdout.write(JSON.stringify({{literal:ui.page.fields.record_json,pick:Boolean(ui.field('Fonte sintetica collegata')),text:ui.text()}}));"
    )
    assert result["literal"] == literal
    assert result["pick"] is False
    assert "nessun" in result["text"]


def test_source_editor_retains_unknown_reference_without_selecting_another_file():
    result = events(
        """
const ui=fixture(source);ui.page.fields.operation='import_evidence';ui.page.fields.record_json=JSON.stringify({id:'E1',source_ref:'old-reference',origin:'Literal origin',locator:'p. 2'});await ui.panel.open('fictional-transform');const pick=ui.field('Fonte sintetica collegata');process.stdout.write(JSON.stringify({value:pick.value,raw:ui.page.fields.record_json,text:ui.text(),calls:ui.calls}));
"""
    )
    assert result["value"] == "old-reference"
    assert "Riferimento non più collegato" in result["text"]
    assert json.loads(result["raw"])["source_ref"] == "old-reference"
    assert len(result["calls"]) == 1


@pytest.mark.parametrize(
    "restrictions", [{"can_write": False}, {"pending_operations": ["uncertain"]}]
)
def test_source_editor_viewer_and_uncertain_write_disable_bound_source_fields(
    restrictions,
):
    result = events(
        f"const ui=fixture(source,{json.dumps(restrictions)});ui.page.fields.operation='import_evidence';await ui.panel.open('fictional-transform');process.stdout.write(JSON.stringify({{disabled:ui.field('Fonte sintetica collegata').disabled,idDisabled:ui.field('Identificativo dell’evidenza').disabled,calls:ui.calls}}));"
    )
    assert result["disabled"] is True
    assert result["idDisabled"] is True
    assert len(result["calls"]) == 1


def test_semantic_records_preserve_all_array_items_and_distinguish_empty_values():
    result = events(
        """
const ui=fixture(source);ui.page.data.state.records.finding.F1={statement:'<synthetic-markup>',rationale:null,alternatives:Array.from({length:73},(_,i)=>'alternative-'+i),confidence:'',amount:'00019.00',flag:false,nested:{}};await ui.panel.open('fictional-transform');const nodes=root=>[root,...root.children.flatMap(nodes)],all=nodes(ui.tree());process.stdout.write(JSON.stringify({items:all.filter(n=>n.tagName==='LI').length,terms:all.filter(n=>n.tagName==='DT').map(n=>n.text),text:ui.text()}));
"""
    )
    assert (
        result["items"] == 79
    )  # 73 alternatives, five contract fields and one blocker.
    assert "Rilievo proposto" in result["terms"]
    assert "Motivazione" in result["terms"]
    assert "alternative-72" in result["text"]
    assert "<synthetic-markup>" in result["text"]
    assert "Non indicato" in result["text"]
    assert "Testo vuoto" in result["text"]
    assert "Falso · false" in result["text"]
    assert "Nessun campo conservato" in result["text"]
    assert "Elenco vuoto" in result["text"]
    assert "00019.00" in result["text"]
