"""Real owned SARI initialization; no native host or model acceptance claims."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_registro_imprese_sari_plugin import (
    _load_archive_core,
    _running_sari_workspace,
)
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import configure

__all__ = []


@pytest.fixture
def sari_run(tmp_path, monkeypatch):
    workspace = _running_sari_workspace(tmp_path)
    context = workspace["context"]
    binding = {
        "work_ref": "fictional-registry-intake",
        "client_root": str(workspace["client_root"]),
        "client_id": context["client_id"],
        "engagement_id": context["engagement_id"],
        "run_id": context["run_id"],
        "workflow_id": "registro-imprese-sari",
    }
    configure(monkeypatch, tmp_path, [binding])
    return workspace, binding, Path(context["output_dir"])


def initial_program(fixture, language="it", jurisdiction="IT"):
    return f"""
const work={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const initialCall=call('vera_workspace_sari_setup',work),initial=payload(initialCall);
const authority=page=>({{...work,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision}});
const fields={{reference_date:'2026-10-08',client_reference:'PRIVATE-UNSENT-REFERENCE',language:{json.dumps(language)},jurisdiction:{json.dumps(jurisdiction)}}};
const saved=payload(call('vera_workspace_sari_draft_save',{{...authority(initial),fields}}));
const prepare={{...authority(initial),expected_draft_revision:saved.draft_revision,fields,confirmed:true,idempotency_key:'fictional-registry-initialize'}};
"""


def initialized_program(fixture):
    return (
        initial_program(fixture)
        + """
const receipt=payload(call('vera_workspace_sari_prepare',prepare));
const page=payload(call('vera_workspace_sari_setup',work));
const exact={...work,revision:page.revision,source_ref:page.source_ref,item_id:page.rows[0].document_id};
"""
    )


def test_sari_private_parameters_recover_without_case_mutation_or_model_disclosure(
    sari_run,
):
    result = rpc_program(
        os.environ.copy(),
        initial_program(sari_run)
        + """
const reopenedCall=call('vera_workspace_sari_setup',work);
const result={initial,initialCall,saved,reopenedCall,reopened:payload(reopenedCall),catalogue:payload(call('vera_workspace_open',{}))};
""",
    )

    assert result["initial"]["can_prepare"] is True
    assert (
        result["reopened"]["fields"]["client_reference"] == "PRIVATE-UNSENT-REFERENCE"
    )
    assert result["reopened"]["draft_revision"] != result["initial"]["draft_revision"]
    assert "confirmed" not in result["reopened"]["fields"]
    assert "fields" not in result["reopenedCall"]["structuredContent"]
    assert "PRIVATE-UNSENT" not in json.dumps(result["reopenedCall"]["content"])
    assert result["catalogue"]["works"][0]["setup_available"] is True
    assert list(sari_run[2].iterdir()) == []


@pytest.mark.parametrize(
    ("language", "jurisdiction"),
    [("it", "IT"), ("en", "IT"), ("fr", "CH-GE"), ("de", "CH-GE"), ("es", "IT")],
)
def test_sari_initialization_reuses_public_producers_without_legal_decisions_and_retries_once(
    sari_run, language, jurisdiction
):
    result = rpc_program(
        os.environ.copy(),
        initial_program(sari_run, language, jurisdiction)
        + """
const first=payload(call('vera_workspace_sari_prepare',prepare));
const retry=payload(call('vera_workspace_sari_prepare',prepare));
const page=payload(call('vera_workspace_sari_setup',work));
const result={first,retry,page};
""",
    )
    intake = json.loads((sari_run[2] / "case_intake_draft.json").read_bytes())
    plan = json.loads((sari_run[2] / "practice_plan_draft.json").read_bytes())
    execution = json.loads((sari_run[2] / "run_intake.json").read_bytes())
    inventory = json.loads((sari_run[2] / "local_evidence_inventory.json").read_bytes())

    assert result["first"] == result["retry"]
    assert result["page"]["can_prepare"] is False
    assert result["page"]["draft_stale"] is True
    assert intake["run_id"] == sari_run[1]["run_id"]
    assert intake["jurisdiction"] == jurisdiction
    assert plan["jurisdiction"] == jurisdiction
    assert execution["language"] == language
    assert intake["competent_chamber"]["confirmation_status"] == "unknown"
    assert intake["activity"]["classification_status"] == "unknown"
    assert plan["professional_review"]["status"] == "pending"
    assert plan["position_matrix"] == []
    assert result["first"]["ready_to_file"] is False
    assert result["first"]["semantic_decisions_performed"] is False
    assert inventory["ocr"]["enabled"] is False
    assert inventory["ocr"]["model_download_allowed"] is False
    assert inventory["ocr"]["case_content_network_transfer"] is False
    assert result["page"]["total"] == inventory["document_count"]
    assert (sari_run[2] / "official_sources.json").exists() is False
    assert (sari_run[2] / "final_artifacts.json").exists() is False
    assert (
        len(
            [
                row
                for row in execution["execution_trace"]
                if row["step_id"] == "initialize_case"
            ]
        )
        == 1
    )


def test_sari_complete_extraction_private_until_exact_explicit_context(sari_run):
    result = rpc_program(
        os.environ.copy(),
        initialized_program(sari_run)
        + """
const readCall=call('vera_workspace_sari_read',exact),context=call('vera_workspace_sari_context',exact);
const outputs=payload(call('vera_workspace_sari_outputs',{...work,revision:page.revision}));
const result={receipt,page,readCall,read:payload(readCall),context,outputs};
""",
    )
    inventory = json.loads((sari_run[2] / "local_evidence_inventory.json").read_bytes())
    document = inventory["documents"][0]
    original = (sari_run[2] / document["text_path"]).read_bytes()

    assert result["read"]["content"].encode() == original
    assert (
        result["read"]["evidence"]["text_sha256"]
        == hashlib.sha256(original).hexdigest()
    )
    assert "content" not in result["readCall"]["structuredContent"]
    assert result["context"]["structuredContent"] == {
        key: value for key, value in result["read"].items() if key != "review_ticket"
    }
    assert "review_ticket" not in result["context"]["structuredContent"]
    assert "_meta" not in result["context"]
    assert "PRIVATE-UNSENT" not in json.dumps(result["context"])
    assert str(sari_run[2]) not in json.dumps(result["context"])
    assert (
        result["context"]["structuredContent"]["actual_model_reads_verified"] is False
    )
    assert len(result["outputs"]["files"]) == 4


@pytest.mark.parametrize(
    "change",
    [
        "confirmed:false",
        "revision:'f'.repeat(64)",
        "expected_draft_revision:'f'.repeat(64)",
        "review_ticket:'forged.signature'",
        "work_ref:'other-owned-run'",
        "fields:{...fields,reference_date:'2026-02-30'}",
        "fields:{...fields,client_reference:'../other-client'}",
        "fields:{...fields,jurisdiction:'CH'}",
        "fields:{...fields,language:'xx'}",
        "source_path:'/private/other-client.txt'",
        "fields:{...fields,professional_review:'reviewed'}",
    ],
)
def test_sari_invalid_initial_authority_or_parameters_preserve_empty_public_run(
    sari_run, change
):
    result = rpc_program(
        os.environ.copy(),
        initial_program(sari_run)
        + f"const result=call('vera_workspace_sari_prepare',{{...prepare,{change}}});",
    )

    assert result["isError"] is True
    assert list(sari_run[2].iterdir()) == []
    assert (
        sari_run[2].parent / ".native-workspace/sari-intake-operations.json"
    ).exists() is False


def test_sari_viewer_reads_but_cannot_save_or_initialize(sari_run):
    result = rpc_program(
        {**os.environ, "VERA_WORKSPACE_ROLES": "VIEWER"},
        f"""
const work={{work_ref:{json.dumps(sari_run[1]['work_ref'])}}},page=payload(call('vera_workspace_sari_setup',work));
const saved=call('vera_workspace_sari_draft_save',{{...work,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision,fields:page.fields}});
const result={{page,saved}};
""",
    )

    assert result["page"]["can_write"] is False
    assert result["saved"]["isError"] is True
    assert list(sari_run[2].iterdir()) == []


@pytest.mark.parametrize(
    "change",
    ["item_id:'DOC-FOREIGN'", "source_ref:'f'.repeat(64)", "revision:'f'.repeat(64)"],
)
def test_sari_context_refuses_foreign_or_stale_selection(sari_run, change):
    result = rpc_program(
        os.environ.copy(),
        initialized_program(sari_run)
        + f"const result=call('vera_workspace_sari_context',{{...exact,{change}}});",
    )

    assert result["isError"] is True
    assert "content" not in result.get("structuredContent", {})


def test_sari_changed_extraction_refuses_context_without_regeneration(sari_run):
    result = rpc_program(
        os.environ.copy(),
        initialized_program(sari_run)
        + f"""
const fs=require('node:fs'),path=require('node:path'),directory={json.dumps(str(sari_run[2]))};
const inventory=JSON.parse(fs.readFileSync(path.join(directory,'local_evidence_inventory.json'),'utf8'));
const file=path.join(directory,inventory.documents[0].text_path);
fs.appendFileSync(file,'CHANGED EXTRACTION');
const result=call('vera_workspace_sari_context',exact);
""",
    )

    assert result["isError"] is True
    inventory = json.loads((sari_run[2] / "local_evidence_inventory.json").read_bytes())
    assert (
        (sari_run[2] / inventory["documents"][0]["text_path"])
        .read_text()
        .endswith("CHANGED EXTRACTION")
    )


def test_sari_stale_private_generation_cannot_overwrite_and_clear_preserves_outputs(
    sari_run,
):
    result = rpc_program(
        os.environ.copy(),
        initial_program(sari_run)
        + """
const stale=call('vera_workspace_sari_draft_save',{...authority(initial),fields:{...fields,client_reference:'LOST-UPDATE'}});
const cleared=payload(call('vera_workspace_sari_draft_clear',{...authority(initial),expected_draft_revision:saved.draft_revision,confirmed:true}));
const result={stale,cleared,reopened:payload(call('vera_workspace_sari_setup',work))};
""",
    )

    assert result["stale"]["isError"] is True
    assert result["reopened"]["fields"]["client_reference"] == ""
    assert result["cleared"]["draft_revision"] == result["reopened"]["draft_revision"]
    assert list(sari_run[2].iterdir()) == []


def test_sari_existing_output_is_preserved_and_initialization_refuses(sari_run):
    original = b"Existing ordinary specialist artifact, not an empty run."
    (sari_run[2] / "existing.txt").write_bytes(original)
    result = rpc_program(
        os.environ.copy(),
        initial_program(sari_run)
        + "const result={initial,refused:call('vera_workspace_sari_prepare',prepare)};",
    )

    assert result["initial"]["setup_status"] == "ordinary_continuation_required"
    assert result["initial"]["can_prepare"] is False
    assert result["refused"]["isError"] is True
    assert (sari_run[2] / "existing.txt").read_bytes() == original
    assert (sari_run[2] / "run_intake.json").exists() is False


def test_sari_changed_original_refuses_resume_and_native_open(sari_run):
    source = next(Path(sari_run[0]["context"]["input_dir"]).rglob("*.txt"))
    source.write_bytes(source.read_bytes() + b" changed registered source")
    result = rpc_program(
        os.environ.copy(),
        f"""
const work={{work_ref:{json.dumps(sari_run[1]['work_ref'])}}};
const result={{setup:call('vera_workspace_sari_setup',work),resume:call('vera_workspace_resume_context',work)}};
""",
    )

    assert result["setup"]["isError"] is True
    assert result["resume"]["isError"] is True
    assert list(sari_run[2].iterdir()) == []


def test_sari_resume_validates_exact_ids_without_reading_documents_or_mutating_case(
    sari_run,
):
    result = rpc_program(
        os.environ.copy(),
        initialized_program(sari_run)
        + "const result=payload(call('vera_workspace_resume_context',work));",
    )

    assert result == {
        key: sari_run[1][key]
        for key in ("work_ref", "client_id", "engagement_id", "run_id", "workflow_id")
    }
    assert (sari_run[2] / "final_artifacts.json").exists() is False


def test_sari_uncertain_intake_blocks_repeat_and_archive_closure(sari_run, monkeypatch):
    from types import SimpleNamespace

    from tests.plugins.test_vera_native_workspace import workspace_module

    module = workspace_module()
    import native_sari_intake as intake

    api = SimpleNamespace(**vars(module))
    binding = sari_run[1]
    setup = module.dispatch(
        "vera_workspace_sari_setup", {"work_ref": binding["work_ref"]}
    )
    proposed = {
        "reference_date": "2026-10-08",
        "client_reference": "FICTIONAL-CASE",
        "language": "it",
        "jurisdiction": "IT",
    }
    saved = module.dispatch(
        "vera_workspace_sari_draft_save",
        {
            "work_ref": binding["work_ref"],
            "revision": setup["revision"],
            "expected_draft_revision": setup["draft_revision"],
            "fields": proposed,
        },
    )
    original_engine = intake.engine

    def interrupted(root, request):
        if request["operation"] == "prepare":
            raise TimeoutError("Fictional uncertain public preparation")
        return original_engine(root, request)

    monkeypatch.setattr(intake, "engine", interrupted)
    arguments = {
        "work_ref": binding["work_ref"],
        "revision": setup["revision"],
        "expected_draft_revision": saved["draft_revision"],
        "fields": proposed,
        "confirmed": True,
        "idempotency_key": "fictional-interruption",
    }

    with pytest.raises(TimeoutError, match="uncertain public preparation"):
        module.dispatch("vera_workspace_sari_prepare", arguments)

    audit = intake.audit_run(sari_run[2], api)
    assert audit["recovery_required"] is True
    with pytest.raises(PermissionError, match="requires recovery"):
        module.dispatch("vera_workspace_sari_prepare", arguments)
    # Closure is a registry action, unavailable in the operator-bound pilot.
    # Reuse the real archive configured by this fixture rather than inventing one.
    monkeypatch.delenv("VERA_WORKSPACE_BINDINGS")
    monkeypatch.setenv(
        "VERA_STUDIO_ARCHIVE_STATE_DIR",
        str(Path(binding["client_root"]).parents[1] / "private-state"),
    )
    # The fixture retains the public core's OS lease under a unique test import.
    # Reuse that same instance rather than competing for its lease in this process.
    monkeypatch.setitem(sys.modules, "archive_core", _load_archive_core())
    with pytest.raises(ValueError, match="ordinary recovery before output closure"):
        module.dispatch(
            "vera_workspace_archive_closure",
            {key: binding[key] for key in ("client_id", "engagement_id", "run_id")},
        )
    assert list(sari_run[2].iterdir()) == []


def test_sari_sealed_completed_inventory_stays_readonly_and_exact(
    sari_run, monkeypatch
):
    rpc_program(
        os.environ.copy(), initialized_program(sari_run) + "const result=receipt;"
    )
    output, binding = sari_run[2], sari_run[1]
    write_no_model_report(output, "registro-imprese-sari", binding["run_id"])
    declarations = [
        {
            "artifact_id": f"fictional_registry_{index}",
            "path": path.relative_to(output).as_posix(),
            "purpose": "Preserve the complete fictional registry initialization",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(
            sorted(p for p in output.rglob("*") if p.is_file())
        )
    ]
    ledger = _load_customer_ledger()
    ledger.finalize_run(
        Path(binding["client_root"]),
        binding["engagement_id"],
        binding["run_id"],
        declarations,
    )
    ledger.complete_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    before = {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*")
        if p.is_file()
    }
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    result = rpc_program(
        os.environ.copy(),
        f"""
const work={{work_ref:{json.dumps(binding['work_ref'])}}},page=payload(call('vera_workspace_sari_setup',work));
const exact={{...work,revision:page.revision,source_ref:page.source_ref,item_id:page.rows[0].document_id}};
const result={{page,selected:payload(call('vera_workspace_sari_read',exact)),outputs:payload(call('vera_workspace_sari_outputs',{{...work,revision:page.revision}})),denied:call('vera_workspace_sari_draft_save',{{...work,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision,fields:page.fields}})}};
""",
    )

    assert result["page"]["run_status"] == "completed"
    assert result["page"]["can_write"] is False
    inventory = json.loads(before["local_evidence_inventory.json"])
    assert (
        result["selected"]["content"].encode()
        == before[inventory["documents"][0]["text_path"]]
    )
    assert result["denied"]["isError"] is True
    assert {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*")
        if p.is_file()
    } == before


def test_sari_oversized_complete_context_is_refused_without_truncation(
    vera_workflow_workspace, tmp_path, monkeypatch
):
    workspace = vera_workflow_workspace(
        "registro-imprese-sari",
        input_files={"large.txt": "Fictional source evidence.\n" * 4000},
    )
    context = json.loads(Path(workspace["context_path"]).read_bytes())
    binding = {
        "work_ref": "fictional-oversized-registry",
        "client_root": str(workspace["client_root"]),
        **{key: context[key] for key in ("client_id", "engagement_id", "run_id")},
        "workflow_id": "registro-imprese-sari",
    }
    configure(monkeypatch, tmp_path, [binding])
    fixture = (workspace, binding, Path(workspace["output_dir"]))
    result = rpc_program(
        os.environ.copy(),
        initialized_program(fixture)
        + "const result={privateRead:payload(call('vera_workspace_sari_read',exact)),modelContext:call('vera_workspace_sari_context',exact)};",
    )

    assert len(result["privateRead"]["content"].encode()) > 64_000
    assert result["privateRead"]["content"].endswith("Fictional source evidence.\n")
    assert result["modelContext"]["isError"] is True
    assert "structuredContent" not in result["modelContext"]
    assert (
        "Complete SARI content exceeds native limit"
        in result["modelContext"]["content"][0]["text"]
    )
