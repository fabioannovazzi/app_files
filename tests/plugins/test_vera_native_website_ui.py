"""UI recovery events on fictional transport, not installed native-host acceptance."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []

CONFIRM = "Confermo questo passaggio sul sito e sui record correnti. Preparare un pacchetto o un collegamento non pubblica il sito"


def events(body: str) -> dict:
    fixture = ROOT / "tests/plugins/website_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/website.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};const confirm={json.dumps(CONFIRM)};(async()=>{{{body}}})().catch(error=>{{process.stderr.write(error.stack);process.exitCode=1;}});"
    completed = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_website_ui_literal_scope_recovers_without_confirmation_or_public_review():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-website');ui.field(confirm).checked=true;
const reviewer=ui.field('Professionista che ha svolto il riesame');reviewer.value='  Fictional literal reviewer  ';reviewer.dispatch('input');
const scope=ui.field('Ambito della decisione');scope.value='responsive_preview';scope.dispatch('change');const decision=ui.field('Decisione professionale');decision.value='returned';decision.dispatch('change');
await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({fields:ui.page.fields,calls:ui.calls,confirmation:ui.field(confirm).checked,visible:ui.text()}));
"""
    )
    assert result["fields"]["reviewer"] == "  Fictional literal reviewer  "
    assert result["fields"]["scope"] == "responsive_preview"
    assert result["fields"]["decision"] == "returned"
    assert result["confirmation"] is False
    assert "mapped_brief_only" in result["visible"]
    assert {row["name"] for row in result["calls"]} == {
        "vera_workspace_website_setup",
        "vera_workspace_website_draft_save",
    }


def test_website_ui_execution_needs_renewed_confirmation_and_retains_exact_scope():
    result = events(
        """
const ui=fixture(source);await ui.panel.open('fictional-website');const action=ui.field('Passaggio da conservare');action.value='review';action.dispatch('change');await ui.panel.flush();let refused=false;try{await ui.button('Esegui e conserva il passaggio').action();}catch(error){refused=true;}ui.field(confirm).checked=true;await ui.button('Esegui e conserva il passaggio').action();process.stdout.write(JSON.stringify({refused,calls:ui.calls,visible:ui.text()}));
"""
    )
    assert result["refused"] is True
    executed = next(row for row in result["calls"] if row["name"].endswith("_execute"))
    assert executed["args"]["revision"] == "exact-version"
    assert executed["args"]["source_ref"] == "exact-version"
    assert executed["args"]["confirmed"] is True
    assert "Whole fictional site fact" in result["visible"]


def test_website_ui_viewer_sees_whole_records_without_write_controls():
    result = events(
        """
const ui=fixture(source,{can_write:false});await ui.panel.open('fictional-website');process.stdout.write(JSON.stringify({disabled:ui.button('Esegui e conserva il passaggio').disabled,reviewerDisabled:ui.field('Professionista che ha svolto il riesame').disabled,visible:ui.text(),calls:ui.calls}));
"""
    )
    assert result["disabled"] is True
    assert result["reviewerDisabled"] is True
    assert "Scope remains unresolved" in result["visible"]
    assert [row["name"] for row in result["calls"]] == ["vera_workspace_website_setup"]


def test_website_ui_pending_write_disables_repeat_and_preserves_visible_records():
    result = events(
        """
const ui=fixture(source,{pending_operations:['uncertain-fictional-write']});await ui.panel.open('fictional-website');process.stdout.write(JSON.stringify({disabled:ui.button('Esegui e conserva il passaggio').disabled,visible:ui.text(),calls:ui.calls}));
"""
    )
    assert result["disabled"] is True
    assert "recupero nel workflow specialistico" in result["visible"]
    assert "Whole fictional site fact" in result["visible"]
    assert [row["name"] for row in result["calls"]] == ["vera_workspace_website_setup"]


def test_website_ui_stale_private_fields_need_explicit_discard_without_public_execution():
    result = events(
        """
const ui=fixture(source,{draft_stale:true});await ui.panel.open('fictional-website');let refused=false;try{await ui.button('Scarta campi privati').action();}catch(error){refused=true;}ui.field('Scarto soltanto questi campi privati dopo il confronto con il sito corrente').checked=true;await ui.button('Scarta campi privati').action();process.stdout.write(JSON.stringify({refused,calls:ui.calls}));
"""
    )
    assert result["refused"] is True
    clear = next(row for row in result["calls"] if row["name"].endswith("_draft_clear"))
    assert clear["args"]["expected_draft_revision"] == "initial"
    assert clear["args"]["confirmed"] is True
    assert not any(row["name"].endswith("_execute") for row in result["calls"])


def test_website_ui_missing_binding_preserves_specialist_chat_setup():
    result = events(
        """
const ui=fixture(source);await ui.panel.catalogue();process.stdout.write(JSON.stringify({visible:ui.text(),calls:ui.calls}));
"""
    )
    assert "Nessun sito collegato" in result["visible"]
    assert "presenza-digitale-studio nella chat" in result["visible"]
    assert [row["name"] for row in result["calls"]] == [
        "vera_workspace_website_catalogue"
    ]
