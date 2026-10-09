"""Initial panel events on explicitly fictional transport, not native acceptance."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []
CONFIRM = "Confermo che questo avvio riguarda soltanto una dimostrazione richiesta con dati sintetici; nessun mandato reale"


def events(body):
    fixture = ROOT / "tests/plugins/transformation_ui_fixture.cjs"
    source = ROOT / "plugins/vera/ui/transformation.js"
    code = f"const {{fixture}}=require({json.dumps(str(fixture))});const source={json.dumps(str(source))};const confirm={json.dumps(CONFIRM)};const initial={{fields:{{owner:'',purpose:''}},created:false,data:{{case_id:'FICTIONAL-INIT',state:null}}}};(async()=>{{{body}}})().catch(e=>{{process.stderr.write(e.stack);process.exitCode=1;}});"
    result = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_initial_ui_literal_fields_recover_without_confirmation_or_creation():
    result = events(
        "const ui=fixture(source,initial);await ui.panel.openInitial('fictional-transform');ui.field(confirm).checked=true;const owner=ui.field('Proprietario dichiarato del prototipo');owner.value='  Literal fictional owner  ';owner.dispatch('input');await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({fields:ui.page.fields,confirmed:ui.field(confirm).checked,calls:ui.calls,text:ui.text()}));"
    )
    assert result["fields"] == {"owner": "  Literal fictional owner  ", "purpose": ""}
    assert result["confirmed"] is False
    assert "mandato reale" in result["text"]
    assert not any(c["name"].endswith("_create") for c in result["calls"])
    assert any(
        c["name"] == "vera_workspace_transformation_initial_draft_save"
        for c in result["calls"]
    )


def test_initial_ui_explicit_creation_is_separate_from_private_save_and_review():
    result = events(
        "const ui=fixture(source,initial);await ui.panel.openInitial('fictional-transform');for(const [label,value]of [['Proprietario dichiarato del prototipo','FICTIONAL_OWNER'],['Scopo della dimostrazione sintetica','Only requested synthetic demonstration']]){const field=ui.field(label);field.value=value;field.dispatch('input');}let denied=false;try{await ui.button('Crea il caso sintetico').action();}catch(e){denied=true;}ui.field(confirm).checked=true;await ui.button('Crea il caso sintetico').action();process.stdout.write(JSON.stringify({denied,created:ui.page.created,calls:ui.calls,text:ui.text(),resume:Boolean(ui.button('Riprendi il caso creato'))}));"
    )
    assert result["denied"] is True
    assert result["created"] is True
    assert result["resume"] is True
    created = next(c for c in result["calls"] if c["name"].endswith("_create"))
    assert created["args"]["synthetic_only"] is True
    assert created["args"]["confirmed"] is True
    assert created["args"]["fields"]["owner"] == "FICTIONAL_OWNER"
    assert "Non indicato" in result["text"]
    assert not any(c["name"].endswith("_execute") for c in result["calls"])


def test_initial_ui_changed_purpose_withdraws_confirmation():
    result = events(
        "const ui=fixture(source,initial);await ui.panel.openInitial('fictional-transform');ui.field(confirm).checked=true;const purpose=ui.field('Scopo della dimostrazione sintetica');purpose.value='Changed fictional purpose';purpose.dispatch('input');process.stdout.write(JSON.stringify({confirmed:ui.field(confirm).checked,calls:ui.calls}));"
    )
    assert result["confirmed"] is False
    assert not any(c["name"].endswith("_create") for c in result["calls"])


def test_initial_ui_viewer_and_uncertain_creation_disable_creation():
    result = events(
        "const viewer=fixture(source,{...initial,can_write:false});await viewer.panel.openInitial('fictional-transform');const uncertain=fixture(source,{...initial,pending_operations:['uncertain']});await uncertain.panel.openInitial('fictional-transform');process.stdout.write(JSON.stringify({viewerDisabled:viewer.button('Crea il caso sintetico').disabled,uncertainDisabled:uncertain.button('Crea il caso sintetico').disabled,text:uncertain.text(),calls:uncertain.calls}));"
    )
    assert result["viewerDisabled"] is True
    assert result["uncertainDisabled"] is True
    assert "non ripetere la creazione" in result["text"]
    assert not any(c["name"].endswith("_create") for c in result["calls"])


def test_initial_ui_created_uncertain_case_has_no_ordinary_resume_action():
    result = events(
        "const ui=fixture(source,{...initial,created:true,pending_operations:['uncertain'],data:{case_id:'FICTIONAL-INIT',state:{case:{id:'FICTIONAL-INIT',purpose:'Preserve the actual synthetic case'},decisions:[]}}});await ui.panel.openInitial('fictional-transform');process.stdout.write(JSON.stringify({resume:Boolean(ui.button('Riprendi il caso creato')),text:ui.text(),calls:ui.calls}));"
    )
    assert result["resume"] is False
    assert "Preserve the actual synthetic case" in result["text"]
    assert "non ripetere la creazione" in result["text"]
    assert [c["name"] for c in result["calls"]] == [
        "vera_workspace_transformation_initial_setup"
    ]


def test_initial_ui_catalogue_selects_initial_route_for_new_bound_target():
    result = events(
        "const ui=fixture(source,{...initial,configured:true,works:[{work_ref:'fictional-transform',case_id:'FICTIONAL-INIT',objective:'Synthetic demonstration',case_revision:0,initialization:true}]});await ui.panel.catalogue();await ui.button('Prepara questo prototipo').action();process.stdout.write(JSON.stringify({calls:ui.calls,text:ui.text()}));"
    )
    assert [c["name"] for c in result["calls"]] == [
        "vera_workspace_transformation_catalogue",
        "vera_workspace_transformation_initial_setup",
    ]
    assert "Avvia un caso sintetico" in result["text"]
    assert "Quali dati arrivano al modello" in result["text"]
