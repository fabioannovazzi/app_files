"""Typed UI checks on an injected fictional transport, not native-host acceptance."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []


def browser(body):
    fixture = ROOT / "tests/plugins/patent_box_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/patent-box.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};(async()=>{{{body}}})().catch(e=>{{process.stderr.write(e.stack);process.exitCode=1;}});"
    completed = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_patent_box_initialization_edits_clear_consent_and_restore_literal_draft():
    result = browser(
        """
const ui=fixture(source);await ui.panel.open('fictional-work');
ui.confirmation().checked=true;
const date=ui.field('Data del caso');date.value='2026-09-23';date.dispatch('input');
const kind=ui.field('Natura effettiva del caso');kind.value='true';kind.dispatch('change');
await ui.panel.flush();await ui.panel.refresh();
process.stdout.write(JSON.stringify({fields:ui.drafts.initialize.fields,consent:ui.confirmation().checked,calls:ui.calls,dirty:ui.dirty}));
"""
    )
    assert result["fields"] == {"as_of": "2026-09-23", "demo": True}
    assert result["consent"] is False
    assert result["dirty"] is False
    assert not any(row["name"].endswith("_execute") for row in result["calls"])


def test_patent_box_ledger_controls_keep_exact_range_without_inferred_mapping():
    result = browser(
        """
const ui=fixture(source);await ui.panel.open('fictional-work','inspect_ledger');
for(const [label,value,event] of [['Documento contabile selezionato','E0001','change'],['Formato dichiarato','CSV','change'],['Riga intestazioni','1','input'],['Prima riga selezionata','2','input'],['Ultima riga selezionata','47','input'],['Separatore CSV',';','change'],['Codifica CSV','cp1252','change']]){const input=ui.field(label);input.value=value;input.dispatch(event);}
await ui.panel.flush();process.stdout.write(JSON.stringify(ui.drafts.inspect_ledger.fields));
"""
    )
    assert result["evidence_id"] == "E0001"
    assert result["options"] == {
        "format": "CSV",
        "sheet": None,
        "header_row": 1,
        "first_row": 2,
        "last_row": 47,
        "delimiter": ";",
        "encoding": "cp1252",
        "pdf_extraction": None,
    }


def test_patent_box_review_requires_full_exact_preview_and_clears_on_version_change():
    result = browser(
        """
const ui=fixture(source);await ui.panel.open('fictional-work','review');
const digest=ui.field('Versione esatta del caso');digest.value=ui.digest;digest.dispatch('change');
ui.confirmation().checked=true;let refused=false;
try{await ui.button('Esegui e conserva questo passaggio').action();}catch(e){refused=true;}
await ui.button('Leggi caso e riesame completi').action();
const enabled=!ui.confirmation().disabled;
ui.confirmation().checked=true;digest.value=ui.second;digest.dispatch('change');
process.stdout.write(JSON.stringify({refused,enabled,checked:ui.confirmation().checked,disabled:ui.confirmation().disabled,calls:ui.calls,text:ui.text()}));
"""
    )
    assert result["refused"] is True
    assert result["enabled"] is True
    assert result["checked"] is False
    assert result["disabled"] is True
    assert "Whole fictional proposal" in result["text"]
    assert not any(row["name"].endswith("_execute") for row in result["calls"])


def test_patent_box_local_review_preserves_declared_name_and_no_authentication_claim():
    result = browser(
        """
const ui=fixture(source);await ui.panel.open('fictional-work','review');
const digest=ui.field('Versione esatta del caso');digest.value=ui.digest;digest.dispatch('change');
await ui.button('Leggi caso e riesame completi').action();
const name=ui.field('Nome dichiarato del revisore');name.value='  FICTIONAL DECLARED  ';name.dispatch('input');
const ref=ui.field('Riferimento effettivo della conferma');ref.value='fictional-reference';ref.dispatch('input');
ui.confirmation().checked=true;await ui.button('Esegui e conserva questo passaggio').action();
process.stdout.write(JSON.stringify({calls:ui.calls,checked:ui.confirmation().checked,text:ui.text()}));
"""
    )
    executed = next(row for row in result["calls"] if row["name"].endswith("_execute"))
    assert executed["args"]["fields"]["reviewer"] == "  FICTIONAL DECLARED  "
    assert executed["args"]["fields"]["synthetic"] is True
    assert result["checked"] is False
    assert "accettazione sintetica" in result["text"]


def test_patent_box_existing_proposal_has_typed_edits_and_locked_normalization():
    result = browser(
        """
const ui=fixture(source);await ui.panel.open('fictional-work','propose');
const select=ui.field('Versione da usare per la modifica');select.value='proposal_'+ui.digest+'.json';select.dispatch('change');
await ui.button('Copia questa versione nei campi').action();
const text=ui.all().find(e=>e.attributes['aria-label']==='Conclusione e limiti · proposal / controls / 0 / conclusion');
const money=ui.all().find(e=>e.attributes['aria-label']==='Importo contabile · proposal / case / costs / 0 / book_amount');
ui.confirmation().checked=true;text.value='Located fictional unresolved gap';text.dispatch('input');await ui.panel.flush();
process.stdout.write(JSON.stringify({fields:ui.drafts.propose.fields,moneyLocked:money.disabled,checked:ui.confirmation().checked}));
"""
    )
    assert (
        result["fields"]["proposal"]["controls"][0]["conclusion"]
        == "Located fictional unresolved gap"
    )
    assert result["fields"]["proposal"]["controls"][0]["status"] == "NOT_TESTED"
    assert "normalization_record" not in result["fields"]["proposal"]
    assert (
        result["fields"]["proposal"]["case"]["costs"][0]["book_amount"] == "100000.00"
    )
    assert result["moneyLocked"] is True
    assert result["checked"] is False


def test_patent_box_stale_draft_requires_separate_discard_without_public_execute():
    result = browser(
        """
const ui=fixture(source,{draft_stale:true,drafts:{review:{fields:{reviewer:'FICTIONAL PREVIOUS'},stamp:'old'}}});await ui.panel.open('fictional-work','review');
let refused=false;try{await ui.button('Scarta la bozza privata').action();}catch(e){refused=true;}
ui.confirmation().checked=true;await ui.button('Scarta la bozza privata').action();
process.stdout.write(JSON.stringify({refused,calls:ui.calls,draft:ui.drafts.review,checked:ui.confirmation().checked}));
"""
    )
    assert result["refused"] is True
    assert result["draft"]["fields"] == {}
    assert result["checked"] is False
    assert not any(row["name"].endswith("_execute") for row in result["calls"])


def test_patent_box_viewer_can_read_without_draft_or_producer_writes():
    result = browser(
        """
const ui=fixture(source,{can_write:false});await ui.panel.open('fictional-work','initialize');await ui.panel.flush();
process.stdout.write(JSON.stringify({disabled:ui.button('Esegui e conserva questo passaggio').disabled,calls:ui.calls,text:ui.text()}));
"""
    )
    assert result["disabled"] is True
    assert "Consultazione soltanto" in result["text"]
    assert [row["name"] for row in result["calls"]] == [
        "vera_workspace_patent_box_setup"
    ]


def test_patent_box_document_link_verifies_exact_bytes_and_does_not_send_chat():
    result = browser(
        """
const ui=fixture(source);await ui.panel.open('fictional-work','calculate');
await ui.button('Prepara PDF da aprire o scaricare').action();
const link=ui.all().find(e=>e.tagName==='A');
process.stdout.write(JSON.stringify({calls:ui.calls,download:link.download,href:link.href}));ui.panel.dispose();
"""
    )
    assert result["download"] == "fascicolo_A_B.pdf"
    assert result["href"].startswith("blob:")
    assert [row["name"] for row in result["calls"]] == [
        "vera_workspace_patent_box_setup",
        "vera_workspace_patent_box_artifact",
    ]
