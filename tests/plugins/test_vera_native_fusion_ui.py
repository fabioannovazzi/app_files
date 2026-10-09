"""Fictional component transport, kept separate from source and native-host checks."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []

CONFIRM = (
    "Ho riesaminato l’anteprima completa e confermo questo passaggio sul caso corrente"
)


def events(body: str) -> dict:
    fixture = ROOT / "tests/plugins/fusion_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/fusion.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};const confirm={json.dumps(CONFIRM)};(async()=>{{{body}}})().catch(error=>{{process.stderr.write(error.stack);process.exitCode=1;}});"
    completed = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_fusion_ui_literal_fields_recover_without_preview_or_confirmation():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-merger');ui.field(confirm).checked=true;
const field=ui.field('Ruolo professionale effettivo');field.value='  Literal fictional role  ';field.dispatch('input');await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({fields:ui.page.fields,confirmed:ui.field(confirm).checked,calls:ui.calls}));
"""
    )
    assert result["fields"]["professional_role"] == "  Literal fictional role  "
    assert result["confirmed"] is False
    assert not any(
        row["name"].endswith(("_preview", "_execute")) for row in result["calls"]
    )


def test_fusion_ui_complete_preview_requires_renewed_confirmation():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-merger');const field=ui.field('Ambito definito della conferma');field.value='Fictional defined scope';field.dispatch('input');await ui.panel.flush();let withoutPreview=false,withoutConsent=false;ui.field(confirm).checked=true;try{await ui.button('Esegui e conserva il passaggio').action();}catch(error){withoutPreview=true;}await ui.button('Controlla passaggio scelto').action();try{await ui.button('Esegui e conserva il passaggio').action();}catch(error){withoutConsent=true;}const whole=ui.text();ui.field(confirm).checked=true;await ui.button('Esegui e conserva il passaggio').action();process.stdout.write(JSON.stringify({withoutPreview,withoutConsent,whole,calls:ui.calls}));
"""
    )
    assert result["withoutPreview"] is True
    assert result["withoutConsent"] is True
    assert "Full fictional approval target" in result["whole"]
    assert "Fictional defined scope" in result["whole"]
    executed = next(row for row in result["calls"] if row["name"].endswith("_execute"))
    assert executed["args"]["preview_ref"] == "fictional-full-preview"
    assert executed["args"]["confirmed"] is True


def test_fusion_ui_changed_fields_invalidate_preview_and_consent():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-merger');await ui.button('Controlla passaggio scelto').action();ui.field(confirm).checked=true;const field=ui.field('Conferma effettivamente espressa dal professionista');field.value='Changed fictional assertion';field.dispatch('input');let denied=false;try{await ui.button('Esegui e conserva il passaggio').action();}catch(error){denied=true;}process.stdout.write(JSON.stringify({denied,checked:ui.field(confirm).checked,text:ui.text(),calls:ui.calls}));
"""
    )
    assert result["denied"] is True
    assert result["checked"] is False
    assert "Full fictional approval target" not in result["text"]
    assert not any(row["name"].endswith("_execute") for row in result["calls"])


def test_fusion_ui_viewer_reads_full_current_and_historical_records():
    result = events(
        """
const ui=fixture(source,{can_write:false,can_approve:false});await ui.panel.open('fictional-merger');process.stdout.write(JSON.stringify({disabled:ui.button('Esegui e conserva il passaggio').disabled,inspectDisabled:ui.button('Controlla passaggio scelto').disabled,text:ui.text(),calls:ui.calls,labels:ui.nodes().filter(x=>x.tagName==='TEXTAREA').map(x=>x.attributes['aria-label'])}));
"""
    )
    assert result["disabled"] is True
    assert result["inspectDisabled"] is True
    assert "Complete fictional current fact" in result["text"]
    assert "Retained fictional prior fact" in result["text"]
    assert [row["name"] for row in result["calls"]] == ["vera_workspace_fusion_setup"]
    assert not any("JSON" in label for label in result["labels"])


def test_fusion_ui_uncertain_operation_disables_new_execution():
    result = events(
        """
const ui=fixture(source,{pending_operations:['uncertain']});await ui.panel.open('fictional-merger');process.stdout.write(JSON.stringify({disabled:ui.button('Esegui e conserva il passaggio').disabled,text:ui.text(),calls:ui.calls}));
"""
    )
    assert result["disabled"] is True
    assert "Non ripetere automaticamente" in result["text"]
    assert "Complete fictional current fact" in result["text"]
    assert not any(row["name"].endswith("_execute") for row in result["calls"])


def test_fusion_ui_stale_fields_require_explicit_private_discard():
    result = events(
        """
const ui=fixture(source,{draft_stale:true});await ui.panel.open('fictional-merger');let denied=false;try{await ui.button('Scarta campi privati').action();}catch(error){denied=true;}ui.field('Scarto soltanto i campi privati precedenti; conservo storia, prove e conferme').checked=true;await ui.button('Scarta campi privati').action();process.stdout.write(JSON.stringify({denied,calls:ui.calls,text:ui.text()}));
"""
    )
    assert result["denied"] is True
    cleared = next(
        row for row in result["calls"] if row["name"].endswith("_draft_clear")
    )
    assert cleared["args"]["expected_draft_revision"] == "initial"
    assert cleared["args"]["confirmed"] is True
    assert "Quali dati arrivano al modello" in result["text"]
