"""Actual website producer through source MCP; every case is fictional."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from tests.plugins.test_presenza_digitale_studio import _prepare_run
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program

__all__ = []


def connect(base: Path, run: Path) -> dict:
    config = base / "website-bindings.json"
    config.write_text(
        json.dumps(
            {
                "tenant_id": "fictional-website-tenant",
                "actor_id": "fictional-reviewer",
                "bindings": [
                    {
                        "work_ref": "website-fictional",
                        "workspace": str(run.parent.parent),
                        "workspace_id": "studio-example",
                        "run_id": run.name,
                    }
                ],
            }
        )
    )
    env = {
        **os.environ,
        "VERA_WORKSPACE_TENANT_ID": "fictional-website-tenant",
        "VERA_WORKSPACE_ACTOR_ID": "fictional-reviewer",
        "VERA_WORKSPACE_ROLES": "REVIEWER",
        "VERA_WORKSPACE_PYTHON": sys.executable,
        "VERA_WEBSITE_WORKSPACE_BINDINGS": str(config),
    }
    env.pop("VERA_WORKSPACE_BINDINGS", None)
    return env


@pytest.fixture
def website(tmp_path):
    domain, run = _prepare_run(tmp_path)
    return connect(tmp_path, run), domain, run


PROGRAM = """
const setup=()=>payload(call('vera_workspace_website_setup',{work_ref:'website-fictional'}));
const authority=p=>({work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket});
const fields=(operation='review',scope='identity_and_claims')=>({operation,scope,reviewer:'FICTIONAL_PROFESSIONAL',decision:'accepted',note:'Private fictional note; not real professional acceptance.'});
const save=(p,f)=>payload(call('vera_workspace_website_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f}));
const execute=(p,f,key)=>{const saved=save(p,f),args={...authority(p),expected_draft_revision:saved.draft_revision,fields:f,confirmed:true,idempotency_key:key};return {result:payload(call('vera_workspace_website_execute',args)),args};};
"""


def test_website_private_literal_fields_restore_without_public_changes_or_consent(
    website,
):
    env, _, run = website
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
    result = rpc_program(
        env,
        PROGRAM
        + """
const p=setup(),f=fields();f.reviewer='  literal reviewer  ';f.decision='';const saved=save(p,f),stale=call('vera_workspace_website_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f}),restored=setup();const result={saved,stale,restored};
""",
    )
    assert result["restored"]["fields"]["reviewer"] == "  literal reviewer  "
    assert result["restored"]["confirmation_restored"] is False
    assert (
        result["restored"]["data"]["records"]["brief"]["brief"]["source_use_plan"][0][
            "post_brief_access"
        ]
        == "mapped_brief_only"
    )
    assert result["stale"]["isError"] is True
    assert {p: p.read_bytes() for p in before} == before


def test_website_public_review_exact_retry_keeps_one_actual_event(website):
    env, _, run = website
    result = rpc_program(
        env,
        PROGRAM
        + """
const p=setup(),step=execute(p,fields(),'fictional-review'),retry=payload(call('vera_workspace_website_execute',step.args)),changed=call('vera_workspace_website_execute',{...step.args,fields:{...step.args.fields,reviewer:'different'}}),current=setup();const result={step:step.result,retry,changed,current};
""",
    )
    events = json.loads((run / "reviews/review_log.json").read_bytes())["events"]
    assert len(events) == 1
    assert events[0]["scope"] == "identity_and_claims"
    assert events[0]["reviewer"] == "FICTIONAL_PROFESSIONAL"
    assert events[0]["confirmed_by_user"] is True
    assert "note" not in events[0]
    assert result["retry"]["result"] == result["step"]["result"]
    assert result["retry"]["revision"] == result["step"]["revision"]
    assert result["changed"]["isError"] is True
    assert result["current"]["draft_stale"] is True


def test_website_three_actual_reviews_package_and_validation_complete_local_chain(
    website,
):
    env, domain, run = website
    result = rpc_program(
        env,
        PROGRAM
        + """
for(const scope of setup().data.required_review_scopes)execute(setup(),fields('review',scope),'fictional-'+scope);
const packaged=execute(setup(),fields('package_release'),'fictional-package');
const verified=execute(setup(),fields('validate_run'),'fictional-validate'),current=setup();const result={packaged:packaged.result,verified:verified.result,current};
""",
    )
    assert domain.validate_run(run)["status"] == "release_ready"
    assert (
        len(json.loads((run / "reviews/review_log.json").read_bytes())["events"]) == 3
    )
    assert result["verified"]["result"]["valid"] is True
    assert result["current"]["data"]["packages"]["release"]["kind"] == "release"
    assert result["current"]["sent_or_published"] is False
    assert result["current"]["data"]["records"]["state"]["deliveries"] == []


def test_website_preview_package_and_sites_binding_preserve_separate_publication_gate(
    tmp_path,
):
    _, run = _prepare_run(tmp_path, noindex=True, publication_provider="sites")
    hosting = run / "work/sites-project/.openai/hosting.json"
    hosting.parent.mkdir()
    hosting.write_text('{"project_id":"fictional-sites-project"}')
    env = connect(tmp_path, run)
    result = rpc_program(
        env,
        PROGRAM
        + """
execute(setup(),fields('package_preview'),'fictional-preview');const bound=execute(setup(),fields('sites_preview_binding'),'fictional-binding'),current=setup();const result={bound:bound.result,current};
""",
    )
    assert (
        result["current"]["data"]["validation"]["status"]
        == "preview_sites_binding_ready"
    )
    assert result["current"]["data"]["records"]["state"]["deliveries"] == []
    assert (run / "work/sites-project/.openai/vera-site-package.zip").is_file()
    assert result["bound"]["sent_or_published"] is False


@pytest.mark.parametrize(
    "invalid",
    [{"confirmed": False}, {"reviewer": ""}, {"scope": "invented"}, {"decision": ""}],
)
def test_website_review_refuses_missing_explicit_decision_and_current_scope(
    website, invalid
):
    env, _, run = website
    result = rpc_program(
        env,
        PROGRAM
        + "const invalid="
        + json.dumps(invalid)
        + ";"
        + """
const p=setup(),f=fields();Object.assign(f,Object.fromEntries(Object.entries(invalid).filter(([k])=>k!=='confirmed')));const saved=call('vera_workspace_website_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f});const attempt=saved.isError?saved:call('vera_workspace_website_execute',{...authority(p),expected_draft_revision:payload(saved).draft_revision,fields:f,confirmed:invalid.confirmed===undefined?true:invalid.confirmed,idempotency_key:'fictional-invalid'});const result={attempt};
""",
    )
    assert result["attempt"]["isError"] is True
    assert not (run / "reviews/review_log.json").exists()


def test_website_artifact_returns_declared_screenshot_and_refuses_original_source(
    website,
):
    env, _, run = website
    result = rpc_program(
        env,
        PROGRAM
        + """
const p=setup(),item=p.data.artifacts.find(x=>x.name==='reviews/browser/desktop.png'),artifact=payload(call('vera_workspace_website_artifact',{work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,artifact_ref:item.name})),forbidden=call('vera_workspace_website_artifact',{work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,artifact_ref:'inputs/studio-facts.txt'});const result={artifact,forbidden};
""",
    )
    assert (
        result["artifact"]["sha256"]
        == hashlib.sha256(
            (run / "reviews/browser/desktop.png").read_bytes()
        ).hexdigest()
    )
    assert result["artifact"]["mime_type"] == "image/png"
    assert result["forbidden"]["isError"] is True


def test_website_changed_browser_bytes_invalidate_prior_scope_and_hide_artifacts(
    website,
):
    env, _, run = website
    screenshot = run / "reviews/browser/desktop.png"
    result = rpc_program(
        env,
        PROGRAM
        + "const file="
        + json.dumps(str(screenshot))
        + ";"
        + """
const p=setup();require('node:fs').appendFileSync(file,'altered');const stale=call('vera_workspace_website_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:fields()}),current=setup();const result={stale,current};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["current"]["data"]["validation"]["valid"] is False
    assert result["current"]["data"]["artifacts"] == []


def test_website_viewer_and_wrong_actor_cannot_write_or_adopt_another_binding(website):
    env, _, _ = website
    viewer = {**env, "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        viewer,
        PROGRAM
        + """
const p=setup(),write=call('vera_workspace_website_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:fields()});const result={page:p,write};
""",
    )
    assert result["page"]["can_write"] is False
    assert result["write"]["isError"] is True
    wrong = rpc_program(
        {**env, "VERA_WORKSPACE_ACTOR_ID": "other-actor"},
        "const result=call('vera_workspace_website_catalogue',{});",
    )
    assert wrong["isError"] is True


def test_website_public_failure_retains_uncertain_intent_without_automatic_repeat(
    website,
):
    env, _, run = website
    result = rpc_program(
        env,
        PROGRAM
        + """
const p=setup(),f=fields('package_release'),saved=save(p,f),args={...authority(p),expected_draft_revision:saved.draft_revision,fields:f,confirmed:true,idempotency_key:'fictional-incomplete-package'},first=call('vera_workspace_website_execute',args),retry=call('vera_workspace_website_execute',args),current=setup();const result={first,retry,current};
""",
    )
    assert result["first"]["isError"] is True
    assert result["retry"]["isError"] is True
    assert result["current"]["pending_operations"] == ["fictional-incomplete-package"]
    assert not list((run / "packages").glob("*/package_manifest.json"))


def test_website_all_routes_are_app_only_and_full_records_remain_private(website):
    env, _, _ = website
    result = rpc_program(
        env,
        """
const list=service.handle({method:'tools/list',id:2}).result.tools.filter(x=>x.name.startsWith('vera_workspace_website_')),opened=call('vera_workspace_website_setup',{work_ref:'website-fictional'}),resource=service.handle({method:'resources/read',id:3,params:{uri:'ui://vera/workspace-v1.html'}}).result;const result={list,opened,resource};
""",
    )
    assert len(result["list"]) == 6
    assert all(row["_meta"]["ui"]["visibility"] == ["app"] for row in result["list"])
    assert "site_brief_record" not in json.dumps(result["opened"]["content"])
    assert result["opened"]["_meta"]["workspace"]["data"]["records"]["brief"]
    assert "VeraWebsite" in result["resource"]["contents"][0]["text"]


def test_website_missing_binding_does_not_require_or_enumerate_client_archive(website):
    env, _, _ = website
    env.pop("VERA_WEBSITE_WORKSPACE_BINDINGS")
    result = rpc_program(
        env, "const result=payload(call('vera_workspace_website_catalogue',{}));"
    )
    assert result["configured"] is False
    assert result["works"] == []
    assert result["workspace_scope"] == "studio_wide"


@pytest.mark.parametrize("linked", ["symlink", "hardlink"])
def test_website_linked_public_evidence_is_refused_before_projection(
    website, tmp_path, linked
):
    env, _, run = website
    path = run / "reviews/browser/desktop.png"
    retained = tmp_path / "retained-screenshot.png"
    path.rename(retained)
    if linked == "symlink":
        path.symlink_to(retained)
    else:
        os.link(retained, path)

    result = rpc_program(
        env,
        "const result=call('vera_workspace_website_setup',{work_ref:'website-fictional'});",
    )

    assert result["isError"] is True
    assert "Website" in result["content"][0]["text"]
    assert not (run / "reviews/review_log.json").exists()


def test_website_tampered_completed_receipt_is_refused_before_retry_or_new_review(
    website,
):
    env, _, run = website
    directory = run.parent.parent / ".native-workspace"
    result = rpc_program(
        env,
        PROGRAM
        + "const directory="
        + json.dumps(str(directory))
        + ";"
        + """
const step=execute(setup(),fields(),'fictional-retained-review'),fs=require('node:fs'),path=require('node:path'),privateDir=fs.readdirSync(directory).find(x=>x.startsWith('website-')),file=path.join(directory,privateDir,'operations.json'),operations=JSON.parse(fs.readFileSync(file,'utf8'));operations['fictional-retained-review'].result.saved=false;fs.writeFileSync(file,JSON.stringify(operations));const refused=call('vera_workspace_website_setup',{work_ref:'website-fictional'});const result={refused};
""",
    )
    assert result["refused"]["isError"] is True
    assert "receipt integrity mismatch" in result["refused"]["content"][0]["text"]
    assert (
        len(json.loads((run / "reviews/review_log.json").read_bytes())["events"]) == 1
    )
