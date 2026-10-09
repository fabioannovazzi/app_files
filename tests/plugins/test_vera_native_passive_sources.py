"""Native grouping of fictional already reviewed originals; no professional acceptance."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import (
    archive_cli,
    process_environment,
)
from tests.plugins.test_vera_native_passive_audit import audit_workspace  # noqa: F401
from tests.plugins.test_vera_native_workspace import configure, workspace_module

__all__ = []


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_native_source_group_fresh_package_replays_unchanged_reviewed_reader(
    source_group, tmp_path, surface
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    work, _, env, fields, _ = source_group
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
    target = tmp_path / "fresh-source-group-package"
    for name, content in entries.items():
        if name.startswith(prefix):
            path = target / name[len(prefix) :]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    result = rpc_program(
        env,
        setup(fields)
        + "const result=payload(call('vera_workspace_source_group_prepare',args));",
        server=target / "mcp/workspace.cjs",
    )

    group = work["output_dir"] / ("reviewed-invoices-" + result["group_ref"])
    assert result["status"] == "prepared"
    assert result["groups"][0]["invoice_count"] == 1
    assert result["professional_approval"] is False
    assert (target / "scripts/native_passive_sources_bridge.py").is_file()
    assert (group / "population.json").read_bytes() == work["input_by_name"][
        "reviewed.json"
    ].read_bytes()


@pytest.mark.parametrize("source_group", ["utf8_boundary"], indirect=True)
def test_selected_source_utf8_byte_cap_retains_complete_text_prefix(source_group):
    _, _, env, fields, ids = source_group

    result = rpc_program(
        env,
        setup(fields)
        + "const result=call('vera_workspace_source_group_explain',{work_ref:first.work_ref,revision:first.revision,source_ref:fields.canonical_id,item_id:"
        + json.dumps(ids["invoice.txt"])
        + "}).structuredContent;",
    )

    assert result["untrusted_evidence"]["excerpt"] == "a" * 19_999
    assert result["untrusted_evidence"]["byte_count"] > 20_000


@pytest.mark.parametrize("roles", ["VIEWER", ""])
def test_source_group_viewer_cannot_write_or_confirm_group(source_group, roles):
    work, _, env, fields, _ = source_group
    env = {**env, "VERA_WORKSPACE_ROLES": roles}

    result = rpc_program(
        env,
        setup(fields)
        + "const result={page:first,write:call('vera_workspace_source_group_prepare',args)};",
    )

    assert result["page"]["can_write"] is False
    assert result["write"]["isError"] is True
    assert not list(work["output_dir"].iterdir())


def test_source_group_private_draft_is_not_recovered_by_another_actor_or_tenant(
    source_group, tmp_path
):
    _, binding, env, fields, _ = source_group
    first = rpc_program(
        env,
        setup(fields)
        + "const result=payload(call('vera_workspace_source_group_draft_save',{...authority(first),fields}));",
    )
    other = tmp_path / "other-owner-bindings.json"
    other.write_text(
        json.dumps(
            {
                "actor_id": "another-fictional-reviewer",
                "tenant_id": "another-fictional-studio",
                "bindings": [binding],
            }
        )
    )
    peer_env = {
        **env,
        "VERA_WORKSPACE_BINDINGS": str(other),
        "VERA_WORKSPACE_ACTOR_ID": "another-fictional-reviewer",
        "VERA_WORKSPACE_TENANT_ID": "another-fictional-studio",
    }

    second = rpc_program(peer_env, setup(fields) + "const result=first;")

    assert first["draft"]["fields"] == fields
    assert second["draft"]["fields"] == {}
    assert second["draft"]["exists"] is False


@pytest.fixture
def source_group(
    audit_workspace, vera_workflow_workspace, tmp_path, monkeypatch, request
):
    """Import separate originals and a declared fictional content-bound extraction."""
    folder = tmp_path / "fictional-extract"
    folder.mkdir()
    canonical = audit_workspace.fixture._reviewed_geneva_invoice(folder)
    value = json.loads(canonical.read_text())
    value["invoices"][0]["source_path"] = "originals/invoice.txt"
    variant = getattr(request, "param", "ordinary")
    if variant == "utf8_boundary":
        (folder / "invoice.txt").write_text("a" * 19_999 + "è" + " trailing text")
        value["invoices"][0]["source_sha256"] = hashlib.sha256(
            (folder / "invoice.txt").read_bytes()
        ).hexdigest()
    content = {k: v for k, v in value.items() if k != "professional_review"}
    value["professional_review"]["content_sha256"] = hashlib.sha256(
        json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if variant == "unreviewed":
        value.pop("professional_review")
    elif variant == "tampered_review":
        value["professional_review"]["content_sha256"] = "0" * 64
    work = vera_workflow_workspace(
        "client-file-preparation",
        input_files={
            "reviewed.json": json.dumps(value),
            "invoice.txt": (folder / "invoice.txt").read_text(),
            "foreign.txt": "Another fictional document",
        },
    )
    ids = {
        Path(r["path"]).name: r["binding_id"] for r in work["context"]["input_bindings"]
    }
    binding = {
        "work_ref": "fictional-source-group",
        "client_root": str(work["client_root"]),
        **{k: work[k] for k in ("client_id", "engagement_id", "run_id")},
        "workflow_id": "client-file-preparation",
    }
    env = configure(monkeypatch, tmp_path, [binding])
    fields = {
        "canonical_id": ids["reviewed.json"],
        "originals": {"originals/invoice.txt": ids["invoice.txt"]},
        "operator_ref": "Fictional test grouping operator",
        "decision_basis": "Explicit fictional original mapping; preserve the fictional extraction review.",
    }
    return work, binding, env, fields, ids


def setup(fields: dict) -> str:
    return (
        "const fields="
        + json.dumps(fields)
        + ";\n"
        + """
const first=payload(call('vera_workspace_source_group_setup',{work_ref:'fictional-source-group',canonical_id:fields.canonical_id}));
const authority=p=>({work_ref:p.work_ref,revision:p.revision,review_ticket:p.review_ticket,source_ref:p.data.selection.source_ref,expected_draft_revision:p.draft.draft_revision});
const args={...authority(first),fields,human_reviewed:true,idempotency_key:'fictional-original-group'};
"""
    )


def test_native_source_group_preserves_registered_bytes_review_and_exact_retry(
    source_group,
):
    work, _, env, fields, _ = source_group
    before = {p.name: p.read_bytes() for p in work["input_paths"]}
    context_before = work["context_path"].read_bytes()

    result = rpc_program(
        env,
        setup(fields)
        + """
const saved=payload(call('vera_workspace_source_group_draft_save',{...authority(first),fields}));
const prepared=payload(call('vera_workspace_source_group_prepare',{...args,expected_draft_revision:saved.draft.draft_revision}));
const retry=payload(call('vera_workspace_source_group_prepare',{...args,expected_draft_revision:saved.draft.draft_revision}));
const reopened=payload(call('vera_workspace_source_group_setup',{work_ref:first.work_ref,canonical_id:fields.canonical_id}));
const raw=call('vera_workspace_source_group_outputs',{work_ref:first.work_ref,revision:reopened.revision,source_ref:fields.canonical_id,group_ref:prepared.group_ref});
const result={first,prepared,retry,reopened,raw,files:payload(raw)};
""",
    )

    group = work["output_dir"] / (
        "reviewed-invoices-" + result["prepared"]["group_ref"]
    )
    assert result["prepared"]["status"] == "prepared"
    assert result["retry"]["status"] == "already_prepared"
    assert result["retry"]["group_ref"] == result["prepared"]["group_ref"]
    assert (group / "population.json").read_bytes() == before["reviewed.json"]
    assert (group / "originals/invoice.txt").read_bytes() == before["invoice.txt"]
    assert len(list(work["output_dir"].iterdir())) == 1
    assert (
        len(
            list(
                (work["output_dir"].parent / ".native-workspace").glob(
                    "source-group-request-*.json"
                )
            )
        )
        == 1
    )
    assert result["reopened"]["groups"][0]["invoice_count"] == 1
    assert result["files"]["professional_approval"] is False
    assert {p["name"] for p in result["files"]["outputs"]} == {
        "population.json",
        "originals/invoice.txt",
        "grouping-review.json",
    }
    assert str(group) not in json.dumps(result["raw"]["content"])
    assert not list(
        (work["output_dir"].parent / ".native-workspace").glob(
            "source-group-preflight-*"
        )
    )
    assert work["context_path"].read_bytes() == context_before


def test_native_source_group_draft_cas_recovery_and_confirmation_are_separate(
    source_group,
):
    work, _, env, fields, _ = source_group

    result = rpc_program(
        env,
        setup(fields)
        + """
const saved=payload(call('vera_workspace_source_group_draft_save',{...authority(first),fields}));
const stale=call('vera_workspace_source_group_draft_save',{...authority(first),fields:{...fields,operator_ref:'Lost update'}});
const recovered=payload(call('vera_workspace_source_group_setup',{work_ref:first.work_ref,canonical_id:fields.canonical_id}));
const missing=call('vera_workspace_source_group_prepare',{...authority(recovered),fields,human_reviewed:false,idempotency_key:'missing-confirmation'});
const result={saved,stale,recovered,missing};
""",
    )

    assert result["stale"]["isError"] is True
    assert result["recovered"]["draft"]["fields"] == fields
    assert "human_reviewed" not in result["recovered"]["draft"]["fields"]
    assert result["missing"]["isError"] is True
    assert not list(work["output_dir"].iterdir())


@pytest.mark.parametrize(
    "fault", ["missing_original", "wrong_original", "foreign_id", "forged_ticket"]
)
def test_native_source_group_rejects_incomplete_foreign_or_changed_authority(
    source_group, fault
):
    work, _, env, fields, ids = source_group
    changes = {
        "missing_original": {"fields": {**fields, "originals": {}}},
        "wrong_original": {
            "fields": {
                **fields,
                "originals": {"originals/invoice.txt": ids["foreign.txt"]},
            }
        },
        "foreign_id": {
            "fields": {**fields, "originals": {"originals/invoice.txt": "foreign"}}
        },
        "forged_ticket": {"review_ticket": "forged.ticket"},
    }

    result = rpc_program(
        env,
        setup(fields)
        + "const changes="
        + json.dumps(changes[fault])
        + ";const result=call('vera_workspace_source_group_prepare',{...args,...changes});",
    )

    assert result["isError"] is True
    assert not list(work["output_dir"].iterdir())
    assert not list(
        (work["output_dir"].parent / ".native-workspace").glob(
            "source-group-request-*.json"
        )
    )


@pytest.mark.parametrize(
    "source_group", ["unreviewed", "tampered_review"], indirect=True
)
def test_native_source_group_invalid_review_never_becomes_an_official_group(
    source_group,
):
    work, _, env, fields, _ = source_group

    result = rpc_program(
        env,
        setup(fields)
        + "const result=call('vera_workspace_source_group_prepare',args);",
    )

    assert result["isError"] is True
    assert "decision bound to its exact content" in result["content"][0]["text"]
    assert not list(work["output_dir"].iterdir())
    assert not list(
        (work["output_dir"].parent / ".native-workspace").glob(
            "source-group-request-*.json"
        )
    )
    assert not list(
        (work["output_dir"].parent / ".native-workspace").glob(
            "source-group-preflight-*"
        )
    )


def test_native_source_group_selected_explanation_excludes_other_documents_and_paths(
    source_group,
):
    work, _, env, fields, ids = source_group

    result = rpc_program(
        env,
        setup(fields)
        + "const result=call('vera_workspace_source_group_explain',{work_ref:first.work_ref,revision:first.revision,source_ref:fields.canonical_id,item_id:"
        + json.dumps(ids["invoice.txt"])
        + "}).structuredContent;",
    )

    assert result["untrusted_evidence"]["id"] == ids["invoice.txt"]
    assert result["untrusted_evidence"]["excerpt"].startswith("Synthetic invoice")
    assert "professional_review" not in result["untrusted_evidence"]
    assert str(work["client_root"]) not in json.dumps(result)
    assert "Another fictional document" not in json.dumps(result)


def test_native_source_group_copy_budget_counts_canonical_json_before_intent(
    source_group, monkeypatch
):
    work, _, _, fields, _ = source_group
    module = workspace_module()
    page = module.dispatch(
        "vera_workspace_source_group_setup",
        {"work_ref": "fictional-source-group", "canonical_id": fields["canonical_id"]},
    )
    import native_passive_sources

    original = next(p for p in work["input_paths"] if p.name == "invoice.txt")
    monkeypatch.setattr(
        native_passive_sources, "MAX_COPY_BYTES", original.stat().st_size
    )
    args = {
        "work_ref": page["work_ref"],
        "revision": page["revision"],
        "source_ref": fields["canonical_id"],
        "expected_draft_revision": "",
        "fields": fields,
        "human_reviewed": True,
        "idempotency_key": "fictional-copy-budget",
    }

    with pytest.raises(ValueError, match="copy limit"):
        module.dispatch("vera_workspace_source_group_prepare", args)

    assert not list(work["output_dir"].iterdir())
    assert not list(
        (work["output_dir"].parent / ".native-workspace").glob(
            "source-group-request-*.json"
        )
    )


def test_native_source_group_guard_fault_retains_intent_and_refuses_duplicate_copy(
    source_group, monkeypatch
):
    work, _, _, fields, _ = source_group
    module = workspace_module()
    selected = {
        "work_ref": "fictional-source-group",
        "canonical_id": fields["canonical_id"],
    }
    page = module.dispatch("vera_workspace_source_group_setup", selected)
    guard = module.write_lock

    @contextmanager
    def failing_guard(output):
        with guard(output):
            yield
            raise OSError("Fictional guard release failure")

    monkeypatch.setattr(module, "write_lock", failing_guard)
    args = {
        "work_ref": page["work_ref"],
        "revision": page["revision"],
        "source_ref": fields["canonical_id"],
        "expected_draft_revision": "",
        "fields": fields,
        "human_reviewed": True,
        "idempotency_key": "fictional-guard-fault",
    }

    with pytest.raises(OSError, match="guard release"):
        module.dispatch("vera_workspace_source_group_prepare", args)

    monkeypatch.setattr(module, "write_lock", guard)
    before = {
        p.relative_to(work["output_dir"]).as_posix(): p.read_bytes()
        for p in work["output_dir"].rglob("*")
        if p.is_file()
    }
    state = module.dispatch("vera_workspace_source_group_setup", selected)
    assert state["interrupted"] is True
    assert state["can_write"] is False
    with pytest.raises(ValueError, match="specialist inspection"):
        module.dispatch("vera_workspace_source_group_prepare", args)
    assert {
        p.relative_to(work["output_dir"]).as_posix(): p.read_bytes()
        for p in work["output_dir"].rglob("*")
        if p.is_file()
    } == before


def test_native_owned_group_closure_upstream_selection_and_audit_intake_preserve_review(
    source_group, audit_workspace, tmp_path
):
    work, _, _, fields, _ = source_group
    studio = tmp_path / "Owned Studio"
    studio.mkdir()
    folder = studio / "Fictional Client"
    shutil.move(str(work["client_root"]), folder)
    env = process_environment()
    env.update(
        VERA_WORKSPACE_PYTHON=sys.executable,
        VERA_STUDIO_ARCHIVE_SESSION_ID="fictional-native-group-handoff",
        VERA_STUDIO_ARCHIVE_STATE_DIR=str(tmp_path / "owned-private-state"),
    )
    archive_cli(env, "configure", "--archive-root", str(studio))
    selected = {"client_id": work["client_id"], "engagement_id": work["engagement_id"]}
    body = (
        "const selected="
        + json.dumps(selected)
        + ";const fields="
        + json.dumps(fields)
        + ";const runId="
        + json.dumps(work["run_id"])
        + ";\n"
        + """
const catalogue=payload(call('vera_workspace_open',selected));
const row=catalogue.works.find(r=>r.run_id===runId);
const first=payload(call('vera_workspace_source_group_setup',{work_ref:row.work_ref,canonical_id:fields.canonical_id}));
const prepared=payload(call('vera_workspace_source_group_prepare',{work_ref:row.work_ref,revision:first.revision,source_ref:fields.canonical_id,review_ticket:first.review_ticket,expected_draft_revision:'',fields,human_reviewed:true,idempotency_key:'owned-fictional-group'}));
const result={row,prepared};
"""
    )
    grouped = rpc_program(env, body)
    ledger = _load_customer_ledger()
    loaded = ledger.load_run(folder, work["engagement_id"], work["run_id"])
    output = Path(loaded["output_dir"])
    canonical_before = loaded["context"]["input_bindings"]
    write_no_model_report(output, "client-file-preparation", work["run_id"])
    scope_selected = {**selected, "run_id": work["run_id"]}

    sealed = rpc_program(
        env,
        "const selected="
        + json.dumps(scope_selected)
        + ";\n"
        + """
const first=payload(call('vera_workspace_archive_closure',selected));
const declarations=Object.fromEntries(first.rows.map(r=>[r.id,{artifact_id:r.id.replace(':','.'),purpose:'Fictional exact source-group handoff test',audience:'internal',media_type:'application/octet-stream'}]));
const saved=payload(call('vera_workspace_archive_declare',{...scope(first),expected_draft_revision:first.draft_revision,declarations}));
const fresh=payload(call('vera_workspace_archive_closure',selected));
const sealed=payload(call('vera_workspace_archive_finalize',{...scope(fresh),expected_draft_revision:fresh.draft_revision,human_reviewed:true,idempotency_key:'fictional-source-group-seal'}));
const result=sealed;
""",
    )
    rows = audit_workspace.fixture._ledger_rows(
        supplier_vat="CHE123456789",
        gross="108.10",
        taxable="100.00",
        vat="8.10",
        payable="-108.10",
    )
    for row in rows:
        row["currency"] = "CHF"
    source_ledger = audit_workspace.fixture._write_ledger(
        tmp_path / "geneva-ledger.csv", rows
    )
    mapping = audit_workspace.fixture._write_mapping(tmp_path / "geneva-mapping.json")
    imported = [
        ledger.import_document(
            folder, work["client_id"], work["engagement_id"], path, "source"
        )["receipt"]["input_id"]
        for path in (source_ledger, mapping)
    ]

    handoff = rpc_program(
        env,
        "const selected="
        + json.dumps(selected)
        + ";const imported="
        + json.dumps(imported)
        + ";\n"
        + """
const inputs=payload(call('vera_workspace_archive_inputs',selected));
const original=inputs.upstream_rows.find(r=>r.path.endsWith('/originals/invoice.txt'));
const canonical=inputs.upstream_rows.find(r=>r.path.endsWith('/population.json'));
const args={...scope(inputs),workflow_id:'passive-invoice-audit',input_ids:imported,upstream_artifacts:[{run_id:canonical.run_id,artifact_id:canonical.artifact_id,role:'reviewed_invoices'},{run_id:original.run_id,artifact_id:original.artifact_id,role:'original_document'}],label:'Fictional CH-GE audit intake',purpose:'Verify exact native source-group reuse without a semantic worker',idempotency_key:'fictional-native-ch-ge-audit'};
const prepared=payload(call('vera_workspace_archive_prepare',args));
const retry=payload(call('vera_workspace_archive_prepare',args));
const fresh=payload(call('vera_workspace_open',selected));
const row=fresh.works.find(r=>r.run_id===prepared.run_id);
payload(call('vera_workspace_archive_start',scope(row)));
const setup=payload(call('vera_workspace_passive_setup',{work_ref:row.work_ref}));
const result={prepared,retry,setup,canonical,original};
""",
    )

    audit_run = ledger.load_run(
        folder, work["engagement_id"], handoff["prepared"]["run_id"]
    )
    identities = {
        Path(r["path"]).name: r["binding_id"]
        for r in audit_run["context"]["input_bindings"]
    }
    intake_fields = {
        "choices": {
            identities["population.json"]: "invoices",
            identities["geneva-ledger.csv"]: "ledger",
            identities["geneva-mapping.json"]: "ledger_mapping",
        },
        "controls": {
            k: str(v) if v is not None else ""
            for k, v in audit_workspace.recipe["controls"].items()
        },
        "operator_ref": "Fictional native intake reviewer",
        "decision_basis": "Fictional source group and CHF mapping; no accounting approval.",
    }
    qualified = rpc_program(
        env,
        "const workRef="
        + json.dumps(handoff["prepared"]["work_ref"])
        + ";const fields="
        + json.dumps(intake_fields)
        + ";\n"
        + """
const fresh=payload(call('vera_workspace_passive_setup',{work_ref:workRef}));
const qualified=payload(call('vera_workspace_passive_qualify',{work_ref:workRef,revision:fresh.revision,review_ticket:fresh.review_ticket,expected_draft_revision:fresh.draft.draft_revision,fields,human_reviewed:true}));
const result=qualified;
""",
    )

    assert grouped["row"]["source_groups_available"] is True
    assert sealed["status"] == "ready_for_review"
    assert handoff["prepared"]["run_id"] == handoff["retry"]["run_id"]
    assert qualified["qualified"]["population"] == 1
    assert qualified["qualified"]["match_counts"]["matched"] == 1
    assert audit_run["run"]["status"] == "running"
    assert not (Path(audit_run["output_dir"]) / "audit.sqlite3").exists()
    assert len(audit_run["context"]["input_bindings"]) == 4
    canonical = next(
        r
        for r in audit_run["context"]["input_bindings"]
        if Path(r["path"]).name == "population.json"
    )
    original = next(
        r
        for r in audit_run["context"]["input_bindings"]
        if Path(r["path"]).name == "invoice.txt"
    )
    assert (
        Path(original["path"])
        == Path(canonical["path"]).parent / "originals/invoice.txt"
    )
    assert (
        json.loads(Path(canonical["path"]).read_bytes())["professional_review"][
            "reviewer_ref"
        ]
        == "synthetic-professional"
    )
    assert (
        ledger.load_run(folder, work["engagement_id"], work["run_id"])["context"][
            "input_bindings"
        ]
        == canonical_before
    )
