"""UI events on a declared fictional transport; source acceptance is separate."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []


def events(body: str) -> dict:
    fixture = ROOT / "tests/plugins/communication_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/communication.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};(async()=>{{{body}}})().catch(error=>{{process.stderr.write(error.stack);process.exitCode=1;}});"
    result = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_communication_ui_literal_matrix_restores_without_consent_or_public_write():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-communication');
ui.field('Confermo questo passaggio sulla versione completa corrente. Invio e pubblicazione restano distinti').checked=true;
ui.field('Ho aperto tutti gli elaborati grafici esatti e confermo la checklist del workflow').checked=true;
const reviewer=ui.field('Professionista che ha svolto il riesame');reviewer.value='  Fictional literal reviewer  ';reviewer.dispatch('input');
const decision=ui.field('Decisione · claims');decision.value='returned';decision.dispatch('change');
const note=ui.field('Motivazione · claims');note.value='Fictional missing scope';note.dispatch('input');
await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({fields:ui.page.fields,calls:ui.calls,confirmation:ui.field('Confermo questo passaggio sulla versione completa corrente. Invio e pubblicazione restano distinti').checked,quality:ui.field('Ho aperto tutti gli elaborati grafici esatti e confermo la checklist del workflow').checked}));
"""
    )
    assert result["fields"]["reviewer"] == "  Fictional literal reviewer  "
    assert result["fields"]["decisions"] == {
        "claims": {"decision": "returned", "note": "Fictional missing scope"}
    }
    assert result["confirmation"] is False
    assert result["quality"] is False
    assert {call["name"] for call in result["calls"]} == {
        "vera_workspace_communication_setup",
        "vera_workspace_communication_draft_save",
    }


def test_communication_ui_execution_requires_renewed_explicit_confirmation():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-communication');
const action=ui.field('Passaggio da conservare');action.value='semantic_review';action.dispatch('change');
await ui.panel.flush();let refused=false;try{await ui.button('Esegui e conserva il passaggio').action();}catch(error){refused=true;}
const visible=ui.text();ui.field('Confermo questo passaggio sulla versione completa corrente. Invio e pubblicazione restano distinti').checked=true;
await ui.button('Esegui e conserva il passaggio').action();process.stdout.write(JSON.stringify({refused,visible,calls:ui.calls}));
"""
    )
    assert result["refused"] is True
    assert "Fictional full claim" in result["visible"]
    execute = next(
        call for call in result["calls"] if call["name"].endswith("_execute")
    )
    assert execute["args"]["source_ref"] == "exact-version"
    assert execute["args"]["quality_checklist_confirmed"] is False
    assert execute["args"]["confirmed"] is True


def test_communication_ui_viewer_sees_complete_review_without_write_controls():
    result = events(
        """
const ui=fixture(source,{can_write:false});await ui.panel.open('fictional-communication');process.stdout.write(JSON.stringify({disabled:ui.button('Esegui e conserva il passaggio').disabled,reviewerDisabled:ui.field('Professionista che ha svolto il riesame').disabled,visible:ui.text(),calls:ui.calls}));
"""
    )
    assert result["disabled"] is True
    assert result["reviewerDisabled"] is True
    assert "Scope remains unresolved" in result["visible"]
    assert [call["name"] for call in result["calls"]] == [
        "vera_workspace_communication_setup"
    ]


def test_communication_ui_empty_catalogue_preserves_studio_wide_and_chat_setup_boundary():
    result = events(
        """
const ui=fixture(source);await ui.panel.catalogue();process.stdout.write(JSON.stringify({visible:ui.text(),calls:ui.calls}));
"""
    )
    assert "non appartengono al fascicolo di un cliente" in result["visible"]
    assert "Nessun run di comunicazione collegato" in result["visible"]
    assert [call["name"] for call in result["calls"]] == [
        "vera_workspace_communication_catalogue"
    ]


def test_communication_ui_stale_fields_need_explicit_discard_and_keep_exact_public_run():
    result = events(
        """
const ui=fixture(source,{draft_stale:true});await ui.panel.open('fictional-communication');let refused=false;try{await ui.button('Scarta campi privati').action();}catch(error){refused=true;}
ui.field('Scarto soltanto questi campi incompleti dopo il confronto con la versione corrente').checked=true;await ui.button('Scarta campi privati').action();process.stdout.write(JSON.stringify({refused,calls:ui.calls}));
"""
    )
    assert result["refused"] is True
    clear = next(
        call for call in result["calls"] if call["name"].endswith("_draft_clear")
    )
    assert clear["args"]["work_ref"] == "fictional-communication"
    assert clear["args"]["expected_draft_revision"] == "initial"
    assert not any(call["name"].endswith("_execute") for call in result["calls"])
