"""Component event regressions on fictional transport, not installed-host acceptance."""

from __future__ import annotations

import json
import subprocess

from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []


def events(body: str) -> dict:
    code = f"const {{fixture}}=require({json.dumps(str(ROOT / 'tests/plugins/practice_ui_fixture.cjs'))});const source={json.dumps(str(ROOT / 'plugins/vera/ui/practice-reviews.js'))};(async()=>{{{body}}})().catch(e=>{{process.stderr.write(e.stack);process.exitCode=1;}});"
    result = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, timeout=20, check=False
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_event_edit_clears_save_confirmation():
    result = events(
        "const ui=fixture(source);await ui.panel.catalogue();await ui.button('Apri revisione').action();ui.checks()[0].checked=true;const field=ui.field('Termine indicato');field.value='2025-01-15';field.dispatch('input');let refused=false;try{await ui.button('Conserva la revisione nel registro').action();}catch(e){refused=true;}process.stdout.write(JSON.stringify({checked:ui.checks()[0].checked,refused,calls:ui.calls}));"
    )
    assert result["checked"] is False
    assert result["refused"] is True
    assert all(not c["name"].endswith("_save") for c in result["calls"])


def test_added_event_requires_new_confirmation_and_saved_discussion():
    result = events(
        "const ui=fixture(source);await ui.panel.catalogue();await ui.button('Apri revisione').action();ui.checks()[0].checked=true;await ui.button('Aggiungi evento o termine').action();let refused=false;try{await ui.button('Discuti questo evento con Vera').action();}catch(e){refused=true;}process.stdout.write(JSON.stringify({checked:ui.checks()[0].checked,refused,calls:ui.calls,messages:ui.messages}));"
    )
    assert result["checked"] is False
    assert result["refused"] is True
    assert result["messages"] == []


def test_saved_calendar_reopens_saved_revision_after_explicit_save():
    result = events(
        "const ui=fixture(source);await ui.panel.catalogue();await ui.button('Apri revisione').action();const field=ui.field('Evento');field.value='Reviewed fictional event';field.dispatch('input');ui.checks()[0].checked=true;await ui.button('Conserva la revisione nel registro').action();await ui.panel.refresh();process.stdout.write(JSON.stringify({value:ui.field('Evento').value,checked:ui.checks()[0].checked,calls:ui.calls}));"
    )
    assert result["value"] == "Reviewed fictional event"
    assert result["checked"] is False
    saved = next(c for c in result["calls"] if c["name"].endswith("_tax_save"))
    assert saved["args"]["revision"] == "revision-one"
    assert saved["args"]["human_reviewed"] is True


def test_format_edit_disables_adoption_until_previews_are_prepared():
    result = events(
        "const ui=fixture(source,'format');await ui.panel.catalogue();await ui.button('Apri revisione').action();ui.checks().forEach(e=>e.checked=true);const field=ui.field('Dimensione testo · punti');field.value='12';field.dispatch('input');const disabled=ui.button('Adotta il formato esaminato').disabled;ui.checks()[0].checked=true;await ui.button('Genera due nuovi esempi').action();process.stdout.write(JSON.stringify({disabled,enabled:!ui.button('Adotta il formato esaminato').disabled,checked:ui.checks().map(e=>e.checked),calls:ui.calls}));"
    )
    assert result["disabled"] is True
    assert result["enabled"] is True
    assert result["checked"] == [False, False]
    assert all(not c["name"].endswith("_approve") for c in result["calls"])


def test_viewer_can_read_without_offering_writes():
    result = events(
        "const tax=fixture(source,'tax',{can_write:false});await tax.panel.catalogue();await tax.button('Apri revisione').action();const format=fixture(source,'format',{can_write:false});await format.panel.catalogue();await format.button('Apri revisione').action();process.stdout.write(JSON.stringify({disabled:[tax.button('Conserva la revisione nel registro').disabled,format.button('Genera due nuovi esempi').disabled,format.button('Adotta il formato esaminato').disabled]}));"
    )
    assert result["disabled"] == [True, True, True]


def test_no_host_message_returns_copyable_exact_selection_request():
    result = events(
        "const ui=fixture(source,'format');await ui.panel.catalogue();await ui.button('Apri revisione').action();await ui.button('Apri questo esempio nella chat').action();process.stdout.write(JSON.stringify({prompt:ui.elements().find(e=>e.tagName==='TEXTAREA'&&e.readOnly).value,calls:ui.calls,messages:ui.messages}));"
    )
    assert "preview-short.docx" in result["prompt"]
    assert "revision-one" in result["prompt"]
    assert result["messages"] == []
    assert len(result["calls"]) == 2


def test_calendar_source_change_populates_sections_and_resets_confirmation():
    result = events(
        "const ui=fixture(source,'tax',{sources:[{id:'D001',units:[{anchor:'line:1',text:'Fictional source passage.'}]}]});await ui.panel.catalogue();await ui.button('Apri revisione').action();ui.checks()[0].checked=true;const sourceField=ui.field('Fonte');sourceField.value='D001';sourceField.dispatch('change');const units=ui.field('Pagina o sezione');const choices=units.children.map(e=>e.value);units.value='line:1';units.dispatch('change');process.stdout.write(JSON.stringify({choices,checked:ui.checks()[0].checked,preview:ui.elements().filter(e=>e.tagName==='PRE').map(e=>e.textContent)}));"
    )
    assert result["choices"] == ["", "line:1"]
    assert result["checked"] is False
    assert "Fictional source passage." in result["preview"]


def test_calendar_select_changes_save_literal_citation_and_status():
    result = events(
        "const ui=fixture(source,'tax',{sources:[{id:'D001',units:[{anchor:'line:1',text:'Fictional source passage.'}]}]});await ui.panel.catalogue();await ui.button('Apri revisione').action();const select=(label,value)=>{const e=ui.field(label);e.value=value;e.dispatch('change');};select('Fonte','D001');select('Pagina o sezione','line:1');const quote=ui.field('Citazione letterale da conservare');quote.value='Fictional source passage.';quote.dispatch('input');await ui.button('Aggiungi il riscontro scelto').action();ui.checks()[0].checked=true;select('Stato del termine','conditional');const cleared=!ui.checks()[0].checked;ui.checks()[0].checked=true;await ui.button('Conserva la revisione nel registro').action();await ui.panel.refresh();process.stdout.write(JSON.stringify({cleared,status:ui.field('Stato del termine').value,calendar:ui.page.data.matter.calendar}));"
    )
    assert result["cleared"] is True
    assert result["status"] == "conditional"
    assert result["calendar"][0]["citations"] == [
        {"source_id": "D001", "anchor": "line:1", "quote": "Fictional source passage."}
    ]
