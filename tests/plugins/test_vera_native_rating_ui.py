"""Explicit fictional UI transport; not engine or installed-host acceptance."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []

CONFIRM = "Ho controllato il dossier completo e confermo il render sul caso e sul predecessore selezionati"


def events(body: str) -> dict:
    fixture = ROOT / "tests/plugins/rating_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/rating.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};const confirm={json.dumps(CONFIRM)};(async()=>{{{body}}})().catch(error=>{{process.stderr.write(error.stack);process.exitCode=1;}});"
    result = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_rating_ui_recovers_literal_selection_without_confirmation_or_preview():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-rating');ui.field(confirm).checked=true;
const field=ui.field('Caso JSON registrato');field.value='case-one';field.dispatch('change');
const note=ui.field('Nota privata · non entra nel dossier');note.value='  Literal fictional note  ';note.dispatch('input');
await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({fields:ui.page.fields,confirmed:ui.field(confirm).checked,calls:ui.calls}));
"""
    )
    assert result["fields"]["case_input_id"] == "case-one"
    assert result["fields"]["note"] == "  Literal fictional note  "
    assert result["confirmed"] is False
    assert not any(
        row["name"].endswith(("_read", "_execute")) for row in result["calls"]
    )


def test_rating_ui_requires_whole_preview_then_renewed_confirmation():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-rating');const field=ui.field('Caso JSON registrato');field.value='case-one';field.dispatch('change');await ui.panel.flush();
let withoutPreview=false,withoutConsent=false;ui.field(confirm).checked=true;try{await ui.button('Conserva dossier').action();}catch(error){withoutPreview=true;}
await ui.button('Controlla dossier scelto').action();try{await ui.button('Conserva dossier').action();}catch(error){withoutConsent=true;}
const whole=ui.text();ui.field(confirm).checked=true;await ui.button('Conserva dossier').action();process.stdout.write(JSON.stringify({withoutPreview,withoutConsent,whole,calls:ui.calls}));
"""
    )
    assert result["withoutPreview"] is True
    assert result["withoutConsent"] is True
    assert "Whole fictional observation" in result["whole"]
    assert "Not realized" in result["whole"]
    executed = next(row for row in result["calls"] if row["name"].endswith("_execute"))
    assert executed["args"]["preview_ref"] == "fictional-whole-preview"
    assert executed["args"]["confirmed"] is True


def test_rating_ui_changed_fields_clear_preview_and_confirmation():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-rating');await ui.button('Controlla dossier scelto').action();ui.field(confirm).checked=true;const note=ui.field('Nota privata · non entra nel dossier');note.value='changed after preview';note.dispatch('input');let denied=false;try{await ui.button('Conserva dossier').action();}catch(error){denied=true;}process.stdout.write(JSON.stringify({denied,checked:ui.field(confirm).checked,text:ui.text(),calls:ui.calls}));
"""
    )
    assert result["denied"] is True
    assert result["checked"] is False
    assert "Whole fictional observation" not in result["text"]
    assert not any(row["name"].endswith("_execute") for row in result["calls"])


def test_rating_ui_viewer_reads_whole_case_without_mutation():
    result = events(
        """
const ui=fixture(source,{can_write:false,can_render:false});await ui.panel.open('fictional-rating');const field=ui.field('Caso JSON registrato');field.value='case-one';field.dispatch('change');await ui.button('Controlla dossier scelto').action();process.stdout.write(JSON.stringify({disabled:ui.button('Conserva dossier').disabled,calls:ui.calls,text:ui.text()}));
"""
    )
    assert result["disabled"] is True
    assert "Unresolved fictional scope" in result["text"]
    assert [row["name"] for row in result["calls"]] == [
        "vera_workspace_rating_setup",
        "vera_workspace_rating_read",
    ]


def test_rating_ui_uncertain_write_disables_repeat_without_removing_read_path():
    result = events(
        """
const ui=fixture(source,{pending_operations:['uncertain'],can_render:false});await ui.panel.open('fictional-rating');await ui.button('Controlla dossier scelto').action();process.stdout.write(JSON.stringify({disabled:ui.button('Conserva dossier').disabled,text:ui.text(),calls:ui.calls}));
"""
    )
    assert result["disabled"] is True
    assert "non ripetere automaticamente" in result["text"]
    assert "Whole fictional dossier Markdown" in result["text"]
    assert not any(row["name"].endswith("_execute") for row in result["calls"])


def test_rating_ui_stale_fields_require_explicit_private_discard():
    result = events(
        """
const ui=fixture(source,{draft_stale:true});await ui.panel.open('fictional-rating');let denied=false;try{await ui.button('Scarta campi privati').action();}catch(error){denied=true;}ui.field('Scarto soltanto i campi privati precedenti; conservo dossier, fonti e ricevute').checked=true;await ui.button('Scarta campi privati').action();process.stdout.write(JSON.stringify({denied,calls:ui.calls}));
"""
    )
    assert result["denied"] is True
    clear = next(row for row in result["calls"] if row["name"].endswith("_draft_clear"))
    assert clear["args"]["expected_draft_revision"] == "initial"
    assert clear["args"]["confirmed"] is True
