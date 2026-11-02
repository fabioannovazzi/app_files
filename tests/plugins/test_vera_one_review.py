"""One user-facing review editor per registered workflow, including on reopen."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.plugins import test_journal_bank_reconciliation_plugin as bank
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import archived_review_binding, configure

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
VERA = ROOT / "plugins/vera"


def test_every_registered_vera_workflow_has_one_declared_editor_or_none() -> None:
    routes = json.loads((VERA / "ui/review-routes.json").read_bytes())
    components = json.loads((VERA / "components.json").read_bytes())["plugins"]

    assert set(routes) == set(components)
    assert set(routes.values()) == {None, "items", "task"}
    assert routes["deep-research-validator"] is None
    assert routes["journal-bank-reconciliation"] == "items"
    assert routes["open-item-reconciliation"] == "items"


def test_bank_review_saves_and_reopens_from_both_entry_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, _, review, _, _ = bank._prepare_sealed_mcp_review_run(
        tmp_path, portable=True
    )
    binding, _ = archived_review_binding(output, "journal-bank-reconciliation")
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    item = next(row for row in review["items"] if row["item_type"] == "unmatched_bank")
    body = """
const ref = REF;
const launch = call('vera_open_review', {work_ref:ref});
const chat = payload(launch);
const directory = payload(call('vera_workspace_open', {}));
const archive = payload(call('vera_workspace_review_route', {work_ref:directory.works[0].work_ref}));
const archivedIds = payload(call('vera_open_review', IDS));
const prior = payload(call('vera_workspace_view', {work_ref:ref,item_id:ITEM}));
const decision = {work_ref:ref, revision:prior.revision, review_ticket:prior.review_ticket,
  human_reviewed:true, item_id:ITEM, idempotency_key:'review-one', decisions:[{item_id:ITEM,action:'mark_unclear',reviewer_note:'Need fee support'}]};
const saved = payload(call('vera_workspace_save', decision));
const reopened = payload(call('vera_workspace_view', {work_ref:archive.work_ref,resume_review:true}));
const stale = call('vera_workspace_save', {...decision,idempotency_key:'old-window'});
const repeated = payload(call('vera_workspace_save', decision));
const result = {chat,archive,archivedIds,visible:launch.structuredContent,notes:reopened.data.ui_decisions.decisions,selection:reopened.selection.id,
  stale:stale.isError, repeated:repeated.revision===saved.revision};
"""
    result = rpc_program(
        env,
        body.replace(
            "IDS",
            json.dumps(
                {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
            ),
        )
        .replace("REF", json.dumps(binding["work_ref"]))
        .replace("ITEM", json.dumps(item["id"])),
    )
    assert result["chat"] == result["archive"] == result["archivedIds"]
    assert result["chat"]["view"] == "items"
    assert result["visible"] == {"status": "ready", "work_ref": binding["work_ref"]}
    assert result["selection"] == item["id"]
    assert result["notes"][0]["item_id"] == item["id"]
    assert result["notes"][0]["reviewer_note"] == "Need fee support"
    assert result["stale"] and result["repeated"]


def test_product_catalogue_cannot_register_a_second_component_editor() -> None:
    program = """
const {projectVeraReview} = require('./scripts/build_product_mcp_catalog.cjs');
const routes = require('./plugins/vera/ui/review-routes.json');
const assert = require('node:assert/strict');
const added = {name:"secondService",resources:[{uri:"ui://different/review"}],tools:[],initialize:{}};
assert.throws(() => projectVeraReview(added,{},routes), /Unassigned/);
const template = {...added,resources:[],resourceTemplates:[{uriTemplate:"ui://different/{run}"}]};
assert.throws(() => projectVeraReview(template,{},routes), /Unassigned/);
for (const component of Object.keys(routes)) {
  const uri='ui://unexpected/extra-review.html';
  const service={resources:[{uri}],tools:[{name:'render_extra_review',_meta:{ui:{resourceUri:uri}}}],initialize:{}};
  projectVeraReview(service,{args:['run_component_mcp.cjs',component]},routes);
  if(service.resources.length || service.tools.length) throw Error(component);
}
"""
    subprocess.run(["node", "-e", program], cwd=ROOT, check=True)


def test_vera_open_item_result_delivers_files_without_generating_a_browser_editor(
    tmp_path, monkeypatch
):
    from tests.plugins.test_open_item_reconciliation_plugin import load_review_session

    monkeypatch.setenv("VERA_COMPONENT_HOST", "1")
    module = load_review_session()
    intake = module.write_run_intake(tmp_path, assumptions={})
    session = module.write_review_session_artifacts(
        tmp_path, run_id=intake.run_id, run_intake_path=intake.path, result={}
    )

    manifest = json.loads(session.final_artifacts_path.read_bytes())
    assert session.review_html_path is None
    assert not (tmp_path / "review_ui.html").exists()
    assert manifest["review_handoff"]["primary"] == "vera_open_review"
    assert manifest["review_handoff"]["required_before_final_delivery"] is False
    card = session.artifact_card_path.read_text()
    assert ".json" not in card and "localhost" not in card
    assert session.ui_decisions_path.is_file() and session.review_payload_path.is_file()
