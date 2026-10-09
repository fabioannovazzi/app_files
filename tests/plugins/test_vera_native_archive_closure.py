"""Exact physical Archive closure on fictional runs, not installed-host acceptance."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import (
    MAINTAINED_WORKFLOWS,
    rpc_program,
)
from tests.plugins.test_vera_native_archive_navigation import (  # noqa: F401
    registry_workspace,
)
from tests.plugins.test_vera_native_workspace import ROOT, workspace_module

__all__ = []


@pytest.fixture
def closure_workspace(registry_workspace, request):
    env, root, _, _, client, engagement = registry_workspace
    ledger = _load_customer_ledger()
    folder = root / "Cliente Beta"
    run = ledger.list_runs(folder, engagement)[0]["run"]
    loaded = ledger.load_run(folder, engagement, run["run_id"])
    output = Path(loaded["output_dir"])
    count = getattr(request, "param", 1)
    for number in range(count):
        (output / f"working-{number:03}.txt").write_text(
            "Fictional local working file.\n"
        )
    write_no_model_report(output, run["workflow_id"], run["run_id"])
    selected = dict(client_id=client, engagement_id=engagement, run_id=run["run_id"])
    return env, folder, output, selected


def setup(selected: dict) -> str:
    """Use exact app identities and explicit fixture purposes, never filename inference."""
    return f"""const selected={json.dumps(selected)};
const read=offset=>payload(call('vera_workspace_archive_closure',{{...selected,offset:offset||0}}));
const authority=view=>({{...scope(view),expected_draft_revision:view.draft_revision}});
const declarations=view=>Object.fromEntries(view.rows.map(row=>[row.id,{{artifact_id:row.id.replace(':','.'),purpose:'Inspect this fictional local output.',audience:'review',media_type:'application/octet-stream'}}]));
const first=read();
"""


def declare_all() -> str:
    return """
let view=first;
for(let offset=0;offset<first.total;offset+=30){
 view=read(offset);
 payload(call('vera_workspace_archive_declare',{...authority(view),declarations:declarations(view)}));
}
view=read();
const seal={...authority(view),human_reviewed:true,idempotency_key:'fictional-seal'};
"""


def test_closure_seal_and_explicit_completion_keep_all_outputs_and_retry(
    closure_workspace,
):
    env, folder, output, selected = closure_workspace
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    body = (
        setup(selected)
        + declare_all()
        + """
const finalized=payload(call('vera_workspace_archive_finalize',seal));
const ready=read();
const complete={...authority(ready),human_reviewed:true,idempotency_key:'fictional-complete'};
const completed=payload(call('vera_workspace_archive_complete',complete));
const result={first,finalized,ready,completed,retrySeal:payload(call('vera_workspace_archive_finalize',seal)),retryComplete:payload(call('vera_workspace_archive_complete',complete)),closed:read(),summary:call('vera_workspace_archive_closure',selected).content};
"""
    )

    result = rpc_program(env, body)

    ledger = _load_customer_ledger()
    manifest = ledger.validate_run_artifacts(
        folder, selected["engagement_id"], selected["run_id"]
    )
    assert result["first"]["report"]["valid"] is True
    assert (
        result["finalized"]["status"] == result["ready"]["status"] == "ready_for_review"
    )
    assert result["ready"]["can_complete"] is True
    assert result["closed"]["status"] == "completed"
    assert result["completed"]["professional_approval"] is False
    assert result["completed"]["sent_or_published"] is False
    assert result["retrySeal"] == result["finalized"]
    assert result["retryComplete"] == result["completed"]
    assert {row["path"] for row in manifest["artifacts"]} == set(before)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert result["closed"]["draft_revision"] == ""
    assert str(output) not in json.dumps(result["summary"])
    assert "Fictional local working file" not in json.dumps(result["summary"])


@pytest.mark.parametrize("closure_workspace", [61], indirect=True)
def test_closure_paged_declarations_merge_every_physical_file(closure_workspace):
    env, folder, _, selected = closure_workspace
    body = (
        setup(selected)
        + """
payload(call('vera_workspace_archive_declare',{...authority(first),declarations:declarations(first)}));
const incomplete=read();
const refused=call('vera_workspace_archive_finalize',{...authority(incomplete),human_reviewed:true,idempotency_key:'incomplete-seal'});
"""
        + declare_all()
        + """
const result={first,refused,last:read(60),finalized:payload(call('vera_workspace_archive_finalize',seal)),after:read()};
"""
    )

    result = rpc_program(env, body)

    assert result["first"]["total"] == 63
    assert len(result["first"]["rows"]) == 30
    assert result["refused"]["isError"] is True
    assert result["last"]["total"] == 63
    assert len(result["last"]["rows"]) == 3
    assert result["last"]["has_more"] is False
    manifest = _load_customer_ledger().validate_run_artifacts(
        folder, selected["engagement_id"], selected["run_id"]
    )
    assert len(manifest["artifacts"]) == 63
    assert result["after"]["status"] == "ready_for_review"


@pytest.mark.parametrize(
    "change",
    [
        "archive_ticket:'forged.signature'",
        "scope_revision:'f'.repeat(64)",
        "client_id:'client_111111111111111111111111'",
        "confirmed:false",
        "expected_draft_revision:'e'.repeat(64)",
        "declarations:{'file:foreign':{purpose:'Wrong owner'}}",
        "declarations:{[first.rows[0].id]:{path:'/another-client/output'}}",
    ],
)
def test_closure_invalid_scope_or_private_fields_do_not_write(
    closure_workspace, change
):
    env, _, output, selected = closure_workspace
    body = (
        setup(selected)
        + f"""
const refused=call('vera_workspace_archive_declare',{{...authority(first),declarations:declarations(first),{change}}});
const result={{refused,after:read()}};
"""
    )

    result = rpc_program(env, body)

    assert result["refused"]["isError"] is True
    assert result["after"]["draft_revision"] == ""
    assert not (output.parent / "artifact_manifest.json").exists()
    assert result["after"]["status"] == "running"


@pytest.mark.parametrize("damage", ["missing", "wrong-run", "markdown", "schema"])
def test_closure_real_disclosure_required_before_sealing(closure_workspace, damage):
    env, _, output, selected = closure_workspace
    path = output / "model_data_report.json"
    if damage == "missing":
        path.unlink()
    elif damage == "markdown":
        (output / "model_data_report.md").write_text("Unverified report text")
    elif damage == "wrong-run":
        write_no_model_report(
            output, "composizione-negoziata", "run_111111111111111111111111"
        )
    else:
        value = json.loads(path.read_text())
        value["phases"][0]["outcome"] = "invented_no_transmission"
        path.write_text(json.dumps(value))
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    body = (
        setup(selected)
        + declare_all()
        + """
const refused=call('vera_workspace_archive_finalize',seal);
const result={first,refused,after:read()};
"""
    )

    result = rpc_program(env, body)

    assert result["first"]["report"]["valid"] is False
    assert result["refused"]["isError"] is True
    assert result["after"]["status"] == "running"
    assert result["after"]["draft_revision"]
    assert result["after"]["interrupted"] is False
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert not (output.parent / "artifact_manifest.json").exists()


def test_closure_hash_consistent_invalid_report_schema_is_refused(closure_workspace):
    env, _, output, selected = closure_workspace
    path = output / "model_data_report.json"
    value = json.loads(path.read_text())
    value["phases"][0]["outcome"] = "invented_no_transmission"
    normalized = {
        k: v
        for k, v in value.items()
        if k not in {"report_id", "evidence", "limitations"}
    }

    def sha(payload):
        return hashlib.sha256(
            (
                json.dumps(
                    payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                + "\n"
            ).encode()
        ).hexdigest()

    value["evidence"]["input_sha256"] = sha(normalized)
    value["evidence"]["receipt_sha256"] = sha(
        {
            "input_sha256": value["evidence"]["input_sha256"],
            "files": value["evidence"]["files"],
        }
    )
    value["report_id"] = "model_data_" + value["evidence"]["receipt_sha256"][:24]
    path.write_text(json.dumps(value))
    body = (
        setup(selected)
        + """
const result=first;
"""
    )

    result = rpc_program(env, body)

    assert result["report"]["valid"] is False
    assert "outcome is unsupported" in result["report"]["reason"]


@pytest.mark.parametrize(
    "outcome,valid,status",
    [
        ("not_measurable", True, "ready_for_review"),
        ("changed-evidence", False, "running"),
    ],
)
def test_closure_preserves_actual_report_uncertainty_and_evidence_receipts(
    closure_workspace, outcome, valid, status
):
    from tests.plugins.test_vera_model_data_report import _load_module

    env, _, output, selected = closure_workspace
    value = json.loads((output / "model_data_report.json").read_text())
    request = {
        k: v
        for k, v in value.items()
        if k not in {"report_id", "evidence", "limitations"}
    }
    phase = request["phases"][0]
    if outcome == "not_measurable":
        phase.update(
            outcome="not_measurable",
            evidence_basis="not_measurable",
            reason="Fictional host telemetry is unavailable; transmission is unknown.",
        )
    else:
        phase["evidence_files"] = ["working-000.txt"]
    report, markdown = _load_module().build_model_data_report(
        request, evidence_root=output
    )
    (output / "model_data_report.json").write_text(json.dumps(report))
    (output / "model_data_report.md").write_text(markdown)
    if outcome == "changed-evidence":
        (output / "working-000.txt").write_text(
            "Changed after report evidence was sealed."
        )
    body = (
        setup(selected)
        + declare_all()
        + """
const result={first,finalized:call('vera_workspace_archive_finalize',seal),after:read()};
"""
    )

    result = rpc_program(env, body)

    assert result["first"]["report"]["valid"] is valid
    assert result["after"]["status"] == status
    assert result["after"]["interrupted"] is False
    assert (
        json.loads((output / "model_data_report.json").read_text())["phases"][0][
            "outcome"
        ]
        == phase["outcome"]
    )


def test_closure_changed_population_requires_explicit_discard(closure_workspace):
    env, _, output, selected = closure_workspace
    body = (
        setup(selected)
        + declare_all()
        + f"""
require('node:fs').writeFileSync({json.dumps(str(output / 'late.txt'))},'Fictional late producer file.');
const refused=call('vera_workspace_archive_finalize',seal),stale=read();
const adopt=call('vera_workspace_archive_declare',{{...authority(stale),declarations:declarations(stale)}});
const discarded=payload(call('vera_workspace_archive_discard',authority(stale)));
const result={{refused,stale,adopt,discarded,after:read()}};
"""
    )

    result = rpc_program(env, body)

    assert result["refused"]["isError"] is True
    assert result["stale"]["draft_stale"] is True
    assert result["adopt"]["isError"] is True
    assert result["discarded"]["discarded"] is True
    assert result["after"]["draft_revision"] == ""
    assert result["after"]["status"] == "running"
    assert (output / "late.txt").read_text() == "Fictional late producer file."


def test_closure_viewer_can_inspect_but_cannot_declare_or_complete(closure_workspace):
    env, _, _, selected = closure_workspace
    body = (
        setup(selected)
        + """
const result={first,refused:call('vera_workspace_archive_declare',{...authority(first),declarations:declarations(first)})};
"""
    )

    result = rpc_program({**env, "VERA_WORKSPACE_ROLES": "VIEWER"}, body)

    assert result["first"]["can_declare"] is False
    assert result["first"]["can_complete"] is False
    assert result["refused"]["isError"] is True


def test_closure_hardlinked_domain_output_retains_maintained_ledger_contract(
    closure_workspace,
):
    env, _, output, selected = closure_workspace
    os.link(output / "working-000.txt", output / "second-reference.txt")
    body = (
        setup(selected)
        + declare_all()
        + """
const result=payload(call('vera_workspace_archive_finalize',seal));
"""
    )

    result = rpc_program(env, body)

    assert result["status"] == "ready_for_review"
    assert (output / "working-000.txt").stat().st_nlink == 2


@pytest.mark.parametrize(
    "invalid", ["missing-purpose", "unknown-audience", "duplicate-id"]
)
def test_closure_incomplete_semantic_declarations_remain_private(
    closure_workspace, invalid
):
    env, _, output, selected = closure_workspace
    edits = {
        "missing-purpose": "fields[first.rows[0].id].purpose='';",
        "unknown-audience": "fields[first.rows[0].id].audience='automatic-delivery';",
        "duplicate-id": "for(const row of first.rows)fields[row.id].artifact_id='same-reference';",
    }
    body = (
        setup(selected)
        + f"""
const fields=declarations(first);{edits[invalid]}
payload(call('vera_workspace_archive_declare',{{...authority(first),declarations:fields}}));
const view=read();
const refused=call('vera_workspace_archive_finalize',{{...authority(view),human_reviewed:true,idempotency_key:'invalid-declarations'}});
const result={{refused,after:read()}};
"""
    )

    result = rpc_program(env, body)

    assert result["refused"]["isError"] is True
    assert result["after"]["draft_revision"]
    assert result["after"]["interrupted"] is False
    assert result["after"]["status"] == "running"
    assert not (output.parent / "artifact_manifest.json").exists()


def test_closure_concurrent_draft_patch_cannot_overwrite_or_discard(closure_workspace):
    env, _, _, selected = closure_workspace
    body = (
        setup(selected)
        + """
const stale=authority(first);
payload(call('vera_workspace_archive_declare',{...stale,declarations:declarations(first)}));
const overwrite=call('vera_workspace_archive_declare',{...stale,declarations:{[first.rows[0].id]:{purpose:'Concurrent replacement'}}});
const discard=call('vera_workspace_archive_discard',stale);
const result={overwrite,discard,after:read()};
"""
    )

    result = rpc_program(env, body)

    assert result["overwrite"]["isError"] is True
    assert result["discard"]["isError"] is True
    assert (
        result["after"]["rows"][0]["declaration"]["purpose"]
        == "Inspect this fictional local output."
    )


@pytest.mark.parametrize("workflow", MAINTAINED_WORKFLOWS)
def test_closure_each_maintained_workflow_seals_only_archival_status(
    registry_workspace, workflow
):
    env, root, _, _, client, engagement = registry_workspace
    ledger = _load_customer_ledger()
    folder = root / "Cliente Beta"
    existing = ledger.list_runs(folder, engagement)[0]["run"]
    loaded = ledger.load_run(folder, engagement, existing["run_id"])
    prepared = ledger.prepare_run(
        folder,
        client,
        engagement,
        workflow,
        "fictional-closure",
        input_ids=[loaded["input_manifest"]["inputs"][0]["binding_id"]],
    )
    started = ledger.start_run(folder, engagement, prepared["run"]["run_id"])
    output = Path(started["output_dir"])
    write_no_model_report(output, workflow, prepared["run"]["run_id"])
    selected = dict(
        client_id=client, engagement_id=engagement, run_id=prepared["run"]["run_id"]
    )
    body = (
        setup(selected)
        + declare_all()
        + """
const sealed=payload(call('vera_workspace_archive_finalize',seal));
const ready=read();
const result=payload(call('vera_workspace_archive_complete',{...authority(ready),human_reviewed:true,idempotency_key:'gate-complete'}));
"""
    )

    result = rpc_program(env, body)

    assert result["status"] == "completed"
    assert result["professional_approval"] is False
    assert result["sent_or_published"] is False
    assert (
        len(
            ledger.validate_run_artifacts(folder, engagement, selected["run_id"])[
                "artifacts"
            ]
        )
        == 2
    )


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_closure_fresh_extracted_package_preserves_customer_ledger(
    closure_workspace, tmp_path, surface
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, folder, output, selected = closure_workspace
    ledger = _load_customer_ledger()
    original = ledger.load_run(folder, selected["engagement_id"], selected["run_id"])
    prepared = ledger.prepare_run(
        folder,
        selected["client_id"],
        selected["engagement_id"],
        "composizione-negoziata",
        "fictional-package-" + surface,
        input_ids=[original["input_manifest"]["inputs"][0]["binding_id"]],
    )
    started = ledger.start_run(
        folder, selected["engagement_id"], prepared["run"]["run_id"]
    )
    selected = {**selected, "run_id": prepared["run"]["run_id"]}
    output = Path(started["output_dir"])
    (output / "working-000.txt").write_text("Fictional local working file.\n")
    if surface == "codex":
        builder = load_builder("build_codex_plugin_zip")
        vera = next(p for p in builder.load_bundles() if p.name == "vera")
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        builder = load_builder("build_claude_plugin_zip")
        _, packages = builder.load_configuration()
        vera = next(p for p in packages if p.plugin == "vera")
        entries = builder.claude_package_entries(vera)
        prefix = ""
    target = tmp_path / "extracted"
    for name, content in entries.items():
        if name.startswith(prefix):
            destination = target / name[len(prefix) :]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    write_no_model_report(
        output,
        "composizione-negoziata",
        selected["run_id"],
        runtime_profile="anthropic-cowork" if surface == "cowork" else "openai-codex",
        report_script=target
        / "modules/studio-archive/scripts/build_model_data_report.py",
    )
    body = (
        setup(selected)
        + declare_all()
        + """
const sealed=payload(call('vera_workspace_archive_finalize',seal));
const ready=read();
const completed=payload(call('vera_workspace_archive_complete',{...authority(ready),human_reviewed:true,idempotency_key:'packaged-complete'}));
const result={sealed,completed,closed:read()};
"""
    )

    result = rpc_program(env, body, server=target / "mcp/workspace.cjs")

    assert result["closed"]["status"] == "completed"
    assert result["closed"]["report"]["valid"] is True
    manifest = _load_customer_ledger().validate_run_artifacts(
        folder, selected["engagement_id"], selected["run_id"]
    )
    assert len(manifest["artifacts"]) == 3
    assert (output / "working-000.txt").read_text() == "Fictional local working file.\n"


@pytest.mark.parametrize("failure", ["interruption", "concurrent-change"])
def test_closure_uncertain_public_write_never_adopts_or_completes(
    closure_workspace, monkeypatch, failure
):
    env, _, output, selected = closure_workspace
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    for key, value in {
        **env,
        "VERA_WORKSPACE_ACTOR_ID": "fixture-reviewer",
        "VERA_WORKSPACE_TENANT_ID": "fixture-studio",
        "VERA_WORKSPACE_ROLES": "REVIEWER",
    }.items():
        monkeypatch.setenv(key, value)
    from native_archive_navigation import archive_module

    service = workspace_module()
    first = service.dispatch("vera_workspace_archive_closure", selected)
    authority = {
        **selected,
        "scope_revision": first["scope_revision"],
        "expected_draft_revision": "",
        "confirmed": True,
    }
    fields = {
        row["id"]: {
            "artifact_id": row["id"].replace(":", "."),
            "purpose": "Fictional local output.",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for row in first["rows"]
    }
    saved = service.dispatch(
        "vera_workspace_archive_declare", {**authority, "declarations": fields}
    )
    core = archive_module(ROOT / "plugins/studio-archive")
    original = core.finalize_studio_client_workflow

    def fail(*args):
        if failure == "interruption":
            raise TimeoutError("Fictional interrupted maintained API")
        (output / "working-000.txt").write_text(
            "Concurrent producer changed these bytes."
        )
        return original(*args)

    monkeypatch.setattr(core, "finalize_studio_client_workflow", fail)
    request = {
        **authority,
        "expected_draft_revision": saved["draft_revision"],
        "human_reviewed": True,
        "idempotency_key": "uncertain-seal",
    }

    with pytest.raises((TimeoutError, ValueError), match="interrupted|reviewed bytes"):
        service.dispatch("vera_workspace_archive_finalize", request)

    reopened = service.dispatch("vera_workspace_archive_closure", selected)
    assert reopened["interrupted"] is True
    assert reopened["can_declare"] is False
    assert reopened["can_complete"] is False
    assert reopened["draft_revision"] == saved["draft_revision"]
    assert reopened["status"] == (
        "running" if failure == "interruption" else "ready_for_review"
    )
    with pytest.raises(ValueError, match="Interrupted archive closure"):
        service.dispatch("vera_workspace_archive_finalize", request)
