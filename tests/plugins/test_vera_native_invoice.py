"""Fictional invoice proposals through maintained Archive and signed native MCP."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT, configure, workspace_module


@pytest.fixture
def invoice_workspace(tmp_path, monkeypatch, request, vera_workflow_workspace):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/invoice-xml/scripts"))
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    spec = importlib.util.spec_from_file_location(
        "fictional_invoice_fixture",
        ROOT / "plugins/invoice-xml/tests/test_invoice_xml.py",
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    variant = getattr(request, "param", "TD01")
    proposal, staging = fixture._proposal(
        tmp_path, variant if variant.startswith("TD") else "TD01"
    )
    work = vera_workflow_workspace(
        "invoice-xml",
        input_files={
            "synthetic-invoice.txt": (staging / "synthetic-invoice.txt").read_text()
        },
    )
    source = work["context"]["input_bindings"][0]
    proposal["sources"][0]["path"] = (
        Path(source["path"]).relative_to(work["input_dir"]).as_posix()
    )
    proposal["sources"][0]["sha256"] = source["sha256"]
    if variant == "partial":
        proposal["invoice"]["FatturaElettronicaBody"][0]["DatiGenerali"][
            "DatiGeneraliDocumento"
        ]["Numero"] = None
        fixture._refresh_evidence(proposal)
    elif variant == "body-object":
        proposal["invoice"]["FatturaElettronicaBody"] = proposal["invoice"][
            "FatturaElettronicaBody"
        ][0]
        fixture._refresh_evidence(proposal)
    elif variant == "many":
        body = proposal["invoice"]["FatturaElettronicaBody"][0]
        line = body["DatiBeniServizi"]["DettaglioLinee"][0]
        body["DatiBeniServizi"]["DettaglioLinee"] = [
            dict(line, NumeroLinea=str(i + 1)) for i in range(61)
        ]
        body["DatiBeniServizi"]["DatiRiepilogo"][0].update(
            ImponibileImporto="6100.00", Imposta="1342.00"
        )
        body["DatiGenerali"]["DatiGeneraliDocumento"][
            "ImportoTotaleDocumento"
        ] = "7442.00"
        fixture._refresh_evidence(proposal)
    output = work["output_dir"]
    (output / "proposal.json").write_text(json.dumps(proposal))
    binding = {
        "work_ref": "fictional-invoice",
        "client_root": str(work["client_root"]),
        "client_id": work["client_id"],
        "engagement_id": work["engagement_id"],
        "run_id": work["run_id"],
        "workflow_id": "invoice-xml",
    }
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    return env, output, binding, workspace_module(), work, proposal


PREPARE = """
const setup=payload(call('vera_workspace_invoice_setup',{work_ref:'fictional-invoice'}));
const prepareArgs={work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,candidate_ref:setup.candidate.id,human_reviewed:true,idempotency_key:'fictional-prepare'};
const prepared=payload(call('vera_workspace_invoice_prepare',prepareArgs));
const chosen=payload(call('vera_workspace_invoice_setup',{work_ref:setup.work_ref,source_ref:prepared.source_ref}));
const authority=(value,stamp='')=>({work_ref:value.work_ref,revision:value.revision,source_ref:value.data.selection.source_ref,review_ticket:value.review_ticket,expected_draft_revision:stamp});
const review={reviewer:'Fictional professional',reviewed_at:'2026-10-07T10:00:00+02:00',approval_basis:'Fictional actual approval reference; no tax certification.'};
"""


@pytest.mark.parametrize(
    "invoice_workspace",
    ["TD01", "TD04", "TD17", "TD18", "TD19", "body-object"],
    indirect=True,
)
def test_native_invoice_export_uses_exact_public_bytes_and_preserves_run(
    invoice_workspace,
):
    env, output, binding, module, _, proposal = invoice_workspace
    result = rpc_program(
        env,
        PREPARE
        + """
const drafted=payload(call('vera_workspace_invoice_draft_save',{...authority(chosen),fields:review}));
const args={...authority(chosen,drafted.draft_revision),review,human_reviewed:true,idempotency_key:'fictional-export'};
const exported=payload(call('vera_workspace_invoice_export',args));
const retry=payload(call('vera_workspace_invoice_export',args));
const after=payload(call('vera_workspace_view',{work_ref:chosen.work_ref,source_ref:prepared.source_ref}));
const files=payload(call('vera_workspace_outputs',{work_ref:chosen.work_ref,revision:after.revision,source_ref:prepared.source_ref}));
const result={prepared,exported,retry,after,files};
""",
    )
    revision = output / ("draft-" + result["prepared"]["source_ref"])
    assert json.loads((revision / "proposal.json").read_text()) == proposal
    assert result["retry"] == result["exported"]
    assert result["exported"]["signed"] is False
    assert result["exported"]["sent_or_published"] is False
    assert result["after"]["data"]["review"]["approval_basis"].startswith(
        "Fictional actual"
    )
    assert len(result["files"]["outputs"]) == 7
    assert all(
        Path(item["path"]).is_relative_to(revision)
        for item in result["files"]["outputs"]
    )
    assert not list((output.parent / ".native-workspace").glob("invoice-draft-*.json"))
    assert module.load_binding(binding)["run"]["status"] == "running"


@pytest.mark.parametrize("invoice_workspace", ["partial"], indirect=True)
def test_native_invoice_partial_preparation_remains_inspectable_and_export_blocked(
    invoice_workspace,
):
    env, output, _, _, _, _ = invoice_workspace
    result = rpc_program(
        env,
        PREPARE
        + """
const refused=call('vera_workspace_invoice_export',{...authority(chosen),review,human_reviewed:true,idempotency_key:'blocked-export'});
const first=payload(call('vera_workspace_view',{work_ref:chosen.work_ref,source_ref:prepared.source_ref}));
const result={chosen,refused,first};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["first"]["data"]["validation"]["issues"]
    assert not list(output.rglob("*.xml"))
    assert (
        len(list((output.parent / ".native-workspace").glob("invoice-request-*.json")))
        == 1
    )


def test_native_invoice_ticket_forgery_foreign_item_and_draft_cas_refuse(
    invoice_workspace,
):
    env, output, _, _, _, _ = invoice_workspace
    result = rpc_program(
        env,
        PREPARE
        + """
const drafted=payload(call('vera_workspace_invoice_draft_save',{...authority(chosen),fields:{reviewer:review.reviewer}}));
const cas=call('vera_workspace_invoice_draft_save',{...authority(chosen),fields:review});
const forged=call('vera_workspace_invoice_export',{...authority(chosen,drafted.draft_revision),review_ticket:chosen.review_ticket.slice(0,-1)+'x',review,human_reviewed:true,idempotency_key:'forged'});
const other=call('vera_workspace_view',{work_ref:chosen.work_ref,source_ref:prepared.source_ref,item_id:'invoice:foreign'});
const result={cas,forged,other};
""",
    )
    assert result["cas"]["isError"] is True
    assert result["forged"]["isError"] is True
    assert result["other"]["isError"] is True
    assert not list(output.rglob("*.xml"))


@pytest.mark.parametrize("invoice_workspace", ["many"], indirect=True)
def test_native_invoice_pagination_and_selected_context_keep_exact_sources(
    invoice_workspace,
):
    env, _, _, _, _, proposal = invoice_workspace
    result = rpc_program(
        env,
        PREPARE
        + """
const view=payload(call('vera_workspace_view',{work_ref:chosen.work_ref,source_ref:prepared.source_ref,offset:360}));
const item=view.items.find(r=>r.group==='fields');
const args={work_ref:chosen.work_ref,revision:view.revision,source_ref:prepared.source_ref,item_id:item.id};
const selection=payload(call('vera_workspace_view',args));
const explanation=call('vera_workspace_explain',args).structuredContent;
const result={view,selection,explanation};
""",
    )
    assert result["view"]["total"] > 400
    assert len(result["view"]["items"]) == 30
    selected = result["selection"]["selection"]
    assert selected["evidence"][0]["path"] == proposal["sources"][0]["path"]
    assert result["explanation"]["untrusted_evidence"] == selected


def test_native_invoice_export_rejects_missing_confirmation_before_intent(
    invoice_workspace,
):
    env, output, _, _, _, _ = invoice_workspace
    result = rpc_program(
        env,
        PREPARE
        + """
const result=call('vera_workspace_invoice_export',{...authority(chosen),review,human_reviewed:false,idempotency_key:'no-confirmation'});
""",
    )
    assert result["isError"] is True
    assert not list(output.rglob("*.xml"))
    assert (
        len(list((output.parent / ".native-workspace").glob("invoice-request-*.json")))
        == 1
    )


@pytest.mark.parametrize(
    "artifact",
    ["validation.json", "preview.html", "review_request.json", "proposal.json"],
)
def test_native_invoice_read_rejects_altered_public_artifact(
    invoice_workspace, artifact
):
    env, output, _, _, _, _ = invoice_workspace
    result = rpc_program(
        env,
        PREPARE
        + f"""
const fs=require('node:fs'),path=require('node:path');
const file=path.join({json.dumps(str(output))},'draft-'+prepared.source_ref,{json.dumps(artifact)});
fs.appendFileSync(file,'TAMPER');
const result=call('vera_workspace_view',{{work_ref:chosen.work_ref,source_ref:prepared.source_ref}});
""",
    )
    assert result["isError"] is True
    assert not list(output.rglob("*.xml"))


@pytest.mark.parametrize("change", ["value", "markup", "missing", "duplicate"])
def test_native_invoice_preview_order_allowance_preserves_all_public_content(
    invoice_workspace, change
):
    env, output, _, _, _, _ = invoice_workspace
    replacement = {
        "value": "text.replace('122.00','123.00')",
        "markup": "text.replace('<title>', '<script>alert(1)</script><title>')",
        "missing": "text.replace(/<tr><th scope='row'>.*?<\\/tr>/s,'')",
        "duplicate": "text.replace(/(<tr><th scope='row'>.*?<\\/tr>)/s,'$1$1')",
    }[change]
    result = rpc_program(
        env,
        PREPARE
        + f"""
const fs=require('node:fs'),path=require('node:path');
const file=path.join({json.dumps(str(output))},'draft-'+prepared.source_ref,'preview.html');
const text=fs.readFileSync(file,'utf8');fs.writeFileSync(file,{replacement});
const result=call('vera_workspace_view',{{work_ref:chosen.work_ref,source_ref:prepared.source_ref}});
""",
    )
    assert result["isError"] is True


def test_native_invoice_stale_population_draft_and_foreign_source_ref_refuse(
    invoice_workspace,
):
    env, output, _, _, _, _ = invoice_workspace
    result = rpc_program(
        env,
        PREPARE
        + f"""
const fs=require('node:fs');
const drafted=payload(call('vera_workspace_invoice_draft_save',{{...authority(chosen),fields:review}}));
fs.writeFileSync({json.dumps(str(output / 'other-artifact.txt'))},'New authoritative output');
const stale=call('vera_workspace_invoice_export',{{...authority(chosen,drafted.draft_revision),review,human_reviewed:true,idempotency_key:'stale'}});
const reopened=payload(call('vera_workspace_invoice_setup',{{work_ref:chosen.work_ref,source_ref:prepared.source_ref}}));
const refused=call('vera_workspace_invoice_draft_save',{{...authority(reopened,drafted.draft_revision),fields:review}});
const foreign=call('vera_workspace_view',{{work_ref:chosen.work_ref,source_ref:'f'.repeat(64)}});
const cleared=payload(call('vera_workspace_invoice_draft_clear',authority(reopened,drafted.draft_revision)));
const result={{stale,reopened,refused,foreign,cleared}};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["reopened"]["draft"]["stale"] is True
    assert result["reopened"]["draft"]["fields"] == {}
    assert result["refused"]["isError"] is True
    assert result["foreign"]["isError"] is True
    assert result["cleared"]["discarded"] is True
    assert not list(output.rglob("*.xml"))


@pytest.mark.parametrize(
    "review",
    [
        {"reviewed_at": "2026-10-07T10:00:00"},
        {"approval_basis": ""},
        {"unexpected": "invalid"},
    ],
)
def test_native_invoice_invalid_attribution_is_rejected_before_intent(
    invoice_workspace, review
):
    env, output, _, _, _, _ = invoice_workspace
    result = rpc_program(
        env,
        PREPARE
        + f"""
const result=call('vera_workspace_invoice_export',{{...authority(chosen),review:{{...review,...{json.dumps(review)}}},human_reviewed:true,idempotency_key:'invalid-review'}});
""",
    )
    assert result["isError"] is True
    assert not list(output.rglob("*.xml"))
    assert (
        len(list((output.parent / ".native-workspace").glob("invoice-request-*.json")))
        == 1
    )


def test_native_invoice_read_only_actor_cannot_prepare(invoice_workspace):
    env, output, _, _, _, _ = invoice_workspace
    env["VERA_WORKSPACE_ROLES"] = "READER"
    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_invoice_setup',{work_ref:'fictional-invoice'}));
const refused=call('vera_workspace_invoice_prepare',{work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,candidate_ref:setup.candidate.id,human_reviewed:true,idempotency_key:'reader'});
const result={setup,refused};
""",
    )
    assert result["setup"]["can_prepare"] is False
    assert result["refused"]["isError"] is True
    assert not list(output.glob("draft-*"))


@pytest.mark.parametrize("tamper", ["input", "linked", "unregistered"])
def test_native_invoice_only_exact_registered_sources_are_accepted(
    invoice_workspace, tamper
):
    env, output, _, _, work, proposal = invoice_workspace
    if tamper == "input":
        Path(work["context"]["input_bindings"][0]["path"]).write_text("Changed source")
    elif tamper == "linked":
        candidate = output / "proposal.json"
        other = output.parent / "linked-proposal.json"
        candidate.rename(other)
        candidate.symlink_to(other)
    else:
        proposal["sources"][0]["path"] = "unregistered-source.txt"
        (work["input_dir"] / "unregistered-source.txt").write_text("Unknown source")
        (output / "proposal.json").write_text(json.dumps(proposal))
    result = rpc_program(
        env,
        "const result=call('vera_workspace_invoice_setup',{work_ref:'fictional-invoice'});",
    )
    assert result["isError"] is True
    assert not list(output.glob("draft-*"))


@pytest.mark.parametrize("operation", ["prepare", "export"])
def test_native_invoice_concurrent_output_retains_uncertain_intent(
    invoice_workspace, monkeypatch, operation
):
    import native_invoice

    _, output, binding, service, _, _ = invoice_workspace
    setup = service.dispatch(
        "vera_workspace_invoice_setup", {"work_ref": binding["work_ref"]}
    )
    prepare = {
        "work_ref": binding["work_ref"],
        "revision": setup["revision"],
        "candidate_ref": setup["candidate"]["id"],
        "human_reviewed": True,
        "idempotency_key": "direct-prepare",
    }
    request = prepare
    if operation == "export":
        prepared = service.dispatch("vera_workspace_invoice_prepare", prepare)
        setup = service.dispatch(
            "vera_workspace_invoice_setup",
            {"work_ref": binding["work_ref"], "source_ref": prepared["source_ref"]},
        )
        request = {
            "work_ref": binding["work_ref"],
            "revision": setup["revision"],
            "source_ref": prepared["source_ref"],
            "expected_draft_revision": "",
            "review": {
                "reviewer": "fictional",
                "reviewed_at": "2026-10-07T10:00:00+02:00",
                "approval_basis": "Fictional actual approval",
            },
            "human_reviewed": True,
            "idempotency_key": "direct-export",
        }
    original = native_invoice.engine

    def concurrent(root, body):
        result = original(root, body)
        if body["operation"] == operation:
            (output / "concurrent-change.txt").write_text(
                "Different simultaneous producer output"
            )
        return result

    monkeypatch.setattr(native_invoice, "engine", concurrent)
    with pytest.raises(ValueError, match="artifacts differ"):
        service.dispatch("vera_workspace_invoice_" + operation, request)
    reopened = service.dispatch(
        "vera_workspace_invoice_setup", {"work_ref": binding["work_ref"]}
    )
    assert reopened["interrupted"] is True
    assert reopened["can_prepare"] is False
    with pytest.raises(ValueError, match="Interrupted"):
        service.dispatch("vera_workspace_invoice_" + operation, request)
    assert len(list(output.glob("draft-*"))) == 1
    assert service.load_binding(binding)["run"]["status"] == "running"


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_native_invoice_fresh_extracted_package_prepares_and_exports(
    invoice_workspace, tmp_path, surface
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, output, binding, module, _, _ = invoice_workspace
    builder = load_builder(
        "build_codex_plugin_zip" if surface == "codex" else "build_claude_plugin_zip"
    )
    if surface == "codex":
        vera = next(p for p in builder.load_bundles() if p.name == "vera")
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        _, packages = builder.load_configuration()
        vera = next(p for p in packages if p.plugin == "vera")
        entries = builder.claude_package_entries(vera)
        prefix = ""
    target = tmp_path / "extracted"
    for name, content in entries.items():
        if name.startswith(prefix):
            path = target / name[len(prefix) :]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    result = rpc_program(
        env,
        PREPARE
        + """
const exported=payload(call('vera_workspace_invoice_export',{...authority(chosen),review,human_reviewed:true,idempotency_key:'packaged-export'}));
const after=payload(call('vera_workspace_view',{work_ref:chosen.work_ref,source_ref:prepared.source_ref}));
const result={exported,after};
""",
        server=target / "mcp/workspace.cjs",
    )
    assert result["exported"]["status"] == "exported_for_operator"
    assert result["after"]["data"]["export"]["schema_valid"] is True
    assert len(list(output.rglob("*.xml"))) == 1
    assert module.load_binding(binding)["run"]["status"] == "running"
