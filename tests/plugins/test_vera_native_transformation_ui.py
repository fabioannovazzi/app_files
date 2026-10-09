"""Fictional UI transport events, not installed native-host acceptance."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []

CONFIRM = "Confermo questo passaggio sul caso sintetico corrente; nessun mandato reale o azione esterna"


def events(body: str) -> dict:
    fixture = ROOT / "tests/plugins/transformation_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/transformation.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};const confirm={json.dumps(CONFIRM)};(async()=>{{{body}}})().catch(error=>{{process.stderr.write(error.stack);process.exitCode=1;}});"
    completed = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_transformation_ui_literal_json_recovers_without_restored_confirmation():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-transform');ui.field(confirm).checked=true;
const actor=ui.field('Operatore o revisore del passaggio');actor.value='  FICTIONAL literal actor  ';actor.dispatch('input');
const proposal=ui.field('Proposta JSON completa · nessuna decisione implicita');proposal.value=' { "id": "unfinished" } ';proposal.dispatch('input');
await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({fields:ui.page.fields,calls:ui.calls,confirmation:ui.field(confirm).checked,visible:ui.text()}));
"""
    )
    assert result["fields"]["actor"] == "  FICTIONAL literal actor  "
    assert result["fields"]["record_json"] == ' { "id": "unfinished" } '
    assert result["confirmation"] is False
    assert "Missing valuation" in result["visible"]
    assert {r["name"] for r in result["calls"]} == {
        "vera_workspace_transformation_setup",
        "vera_workspace_transformation_draft_save",
    }


def test_transformation_ui_execute_requires_renewed_confirmation_of_exact_fields():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-transform');const op=ui.field('Passaggio sintetico');op.value='submit';op.dispatch('change');const branch=ui.field('Identificativo del ramo');branch.value='B1';branch.dispatch('input');await ui.panel.flush();let refused=false;try{await ui.button('Esegui e conserva il passaggio sintetico').action();}catch(error){refused=true;}ui.field(confirm).checked=true;await ui.button('Esegui e conserva il passaggio sintetico').action();process.stdout.write(JSON.stringify({refused,calls:ui.calls,visible:ui.text()}));
"""
    )
    assert result["refused"] is True
    executed = next(r for r in result["calls"] if r["name"].endswith("_execute"))
    assert executed["args"]["fields"]["branch_id"] == "B1"
    assert executed["args"]["fields"]["decision"] == ""
    assert executed["args"]["confirmed"] is True
    assert "Whole fictional finding" in result["visible"]


def test_transformation_ui_viewer_sees_full_records_without_write_controls():
    result = events(
        "const ui=fixture(source,{can_write:false});await ui.panel.open('fictional-transform');process.stdout.write(JSON.stringify({disabled:ui.button('Esegui e conserva il passaggio sintetico').disabled,fieldDisabled:ui.field('Operatore o revisore del passaggio').disabled,visible:ui.text(),calls:ui.calls}));"
    )
    assert result["disabled"] is True
    assert result["fieldDisabled"] is True
    assert "Only synthetic interpretation" in result["visible"]
    assert [r["name"] for r in result["calls"]] == [
        "vera_workspace_transformation_setup"
    ]


def test_transformation_ui_uncertain_write_disables_repeat():
    result = events(
        "const ui=fixture(source,{pending_operations:['uncertain']});await ui.panel.open('fictional-transform');process.stdout.write(JSON.stringify({disabled:ui.button('Esegui e conserva il passaggio sintetico').disabled,visible:ui.text()}));"
    )
    assert result["disabled"] is True
    assert "recupero nel workflow specialistico" in result["visible"]
    assert "Whole fictional finding" in result["visible"]


def test_transformation_ui_stale_fields_discard_only_on_explicit_choice():
    result = events(
        "const ui=fixture(source,{draft_stale:true});await ui.panel.open('fictional-transform');let refused=false;try{await ui.button('Scarta campi privati').action();}catch(error){refused=true;}ui.field('Scarto soltanto questi campi privati dopo il confronto con il caso corrente').checked=true;await ui.button('Scarta campi privati').action();process.stdout.write(JSON.stringify({refused,calls:ui.calls}));"
    )
    assert result["refused"] is True
    clear = next(r for r in result["calls"] if r["name"].endswith("_draft_clear"))
    assert clear["args"]["confirmed"] is True
    assert not any(r["name"].endswith("_execute") for r in result["calls"])


def test_transformation_ui_missing_binding_uses_synthetic_specialist_setup():
    result = events(
        "const ui=fixture(source);await ui.panel.catalogue();process.stdout.write(JSON.stringify({visible:ui.text(),calls:ui.calls}));"
    )
    assert "Nessun prototipo collegato" in result["visible"]
    assert "Nessun fascicolo cliente" in result["visible"]
    assert "Quali dati arrivano al modello" in result["visible"]
    assert [r["name"] for r in result["calls"]] == [
        "vera_workspace_transformation_catalogue"
    ]
