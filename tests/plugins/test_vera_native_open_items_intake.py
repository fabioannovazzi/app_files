"""Initial native intake against real fictional source PDFs and public assurance."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from tests.plugins import test_vera_native_workspace as native
from tests.plugins.test_open_item_reconciliation_plugin import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program


@pytest.fixture
def initial_open_items(tmp_path, monkeypatch, request):
    ledger = _load_customer_ledger()
    client = tmp_path / "Fictional open-item customer"
    client.mkdir()
    client_id = "client_" + "b6" * 12
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(client, client_id, "Fictional initial intake")
    source_root = (
        native.ROOT / "plugins/vera/assets/courses/open-item-reconciliation/files/input"
    )
    if getattr(request, "param", False):
        large_source_root = tmp_path / "large-source"
        large_source_root.mkdir()
        for name in ("open-items-it.pdf", "bank-march-it.pdf"):
            raw = (source_root / name).read_bytes()
            if name == "open-items-it.pdf":
                raw += b" " * (4 * 1024 * 1024)
            (large_source_root / name).write_bytes(raw)
        source_root = large_source_root
    receipts = [
        ledger.import_document(
            client, client_id, engagement["engagement_id"], source_root / name, "source"
        )["receipt"]
        for name in ("open-items-it.pdf", "bank-march-it.pdf")
    ]
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "open-item-reconciliation",
        "synthetic",
        input_ids=[row["input_id"] for row in receipts],
    )
    started = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    binding = {
        "work_ref": "initial-open-items",
        "client_root": str(client),
        "client_id": client_id,
        "engagement_id": engagement["engagement_id"],
        "run_id": prepared["run"]["run_id"],
        "workflow_id": "open-item-reconciliation",
    }
    return (
        native.configure(monkeypatch, tmp_path, [binding]),
        Path(started["context"]["output_dir"]),
        binding,
    )


def initial_program(language: str = "it") -> str:
    """The test reviewer explicitly declares the meaning of these named fixtures."""
    fields = {
        "scope_year": "2026",
        "cutoff_date": "2026-03-31",
        "currency": "EUR",
        "jurisdiction": "IT",
        "language": language,
        "document_language": "it",
        "reviewer_ref": "reviewer.synthetic",
        "reviewed_on": date.today().isoformat(),
        "post_cutoff_events_excluded": True,
        "payment_orders_are_bank_evidence": False,
        "factoring_pro_soluto_closes_item": True,
        "compensation_requires_bank": False,
        "counterparty_keywords": ["servizi esempio"],
        "title": "Revisione fittizia da conservare",
        "narrative": "Nota fittizia da conservare.",
    }
    return (
        """
const setup=payload(call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'}));
const intakeScope={work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft.draft_revision};
const fields="""
        + json.dumps(fields)
        + ";"
        + """
fields.sources=Object.fromEntries(setup.items.map(row=>[row.id,{role:row.title==='open-items-it.pdf'?'open_items':'bank_statement',adapter_family:row.title==='open-items-it.pdf'?'open_items_text_v1':'bank_statement_text_v1',perimeter:{entity_ref:'entity.arco',party_ref:'party.servizi_esempio',currency:'EUR',unit:'currency_amount',direction_policy:'supplier',allocation_policy:'one_to_one'},money:{decimal_separator:',',thousands_separator:'.',reported_unit:'EUR',reported_increment:'0.01'},date:{order:'day_first'}}]));
const saved=payload(call('vera_workspace_open_items_intake_draft_save',{...intakeScope,fields}));
const args={...intakeScope,expected_draft_revision:saved.draft_revision,human_reviewed:true,idempotency_key:'fictional-initial-open-items'};
"""
    )


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_initial_open_items_retains_full_package_and_replays_without_approval(
    initial_open_items, language
):
    env, output, binding = initial_open_items
    result = rpc_program(
        env,
        initial_program(language)
        + """
const prepared=payload(call('vera_workspace_open_items_intake_prepare',args));
const retry=payload(call('vera_workspace_open_items_intake_prepare',args));
const reopened=payload(call('vera_workspace_open_items_intake_setup',{work_ref:setup.work_ref}));
const view=payload(call('vera_workspace_view',{work_ref:setup.work_ref}));
const result={prepared,retry,reopened,view};
""",
    )
    assert result["prepared"] == result["retry"]
    assert result["prepared"]["professional_approval"] is False
    assert result["prepared"]["run_completed"] is False
    assert result["reopened"]["status"] == "prepared"
    assert result["view"]["workflow"] == "open-item-reconciliation"
    manifest = json.loads((output / "reconciliation/run_manifest.json").read_bytes())
    assert manifest["report_options"] == {
        "title": "Revisione fittizia da conservare",
        "narrative": "Nota fittizia da conservare.",
        "language": language,
    }
    assert (output / "reconciliation/riconciliazione_audit.xlsx").is_file()
    assert (output / "reconciliation/assurance_final_outputs").is_dir()
    assert native.workspace_module().load_binding(binding)["run"]["status"] == "running"


@pytest.mark.parametrize(
    "change",
    [
        "human_reviewed:false",
        "revision:'0'.repeat(64)",
        "expected_draft_revision:'0'.repeat(64)",
        "review_ticket:'invalid.signature'",
    ],
)
def test_initial_open_items_refuses_stale_or_unconfirmed_request_before_outputs(
    initial_open_items, change
):
    env, output, _ = initial_open_items
    result = rpc_program(
        env,
        initial_program()
        + "const result=call('vera_workspace_open_items_intake_prepare',{...args,"
        + change
        + "});",
    )
    assert result["isError"] is True
    assert list(output.iterdir()) == []


def test_initial_open_items_catalogue_exposes_initial_intake(initial_open_items):
    env, output, _ = initial_open_items

    result = rpc_program(env, "const result=payload(call('vera_workspace_open',{}));")

    assert result["works"][0]["workflow"] == "open-item-reconciliation"
    assert result["works"][0]["setup_available"] is True
    assert list(output.iterdir()) == []


def test_initial_open_items_original_is_exact_private_readable_for_viewer(
    initial_open_items,
):
    env, output, _ = initial_open_items
    env["VERA_WORKSPACE_ROLES"] = "VIEWER"

    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'}));
const result=call('vera_workspace_open_items_intake_source',{work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,input_id:setup.items[0].id});
""",
    )

    source = result["_meta"]["workspace"]
    raw = base64.b64decode(source["content"], validate=True)
    assert source["mime_type"] == "application/pdf"
    assert source["byte_count"] == len(raw)
    assert source["sha256"] == hashlib.sha256(raw).hexdigest()
    assert (
        raw
        == (
            native.ROOT
            / "plugins/vera/assets/courses/open-item-reconciliation/files/input"
            / source["name"]
        ).read_bytes()
    )
    assert source["content"] not in json.dumps(result["content"])
    assert source["content"] not in json.dumps(result["structuredContent"])
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        "input_id:'another-run-source'",
        "revision:'0'.repeat(64)",
        "review_ticket:'invalid.signature'",
    ],
)
def test_initial_open_items_original_refuses_foreign_or_stale_selection(
    initial_open_items, change
):
    env, output, _ = initial_open_items

    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'}));
const result=call('vera_workspace_open_items_intake_source',{work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,input_id:setup.items[0].id,
"""
        + change
        + "});",
    )

    assert result["isError"] is True
    assert set(result["_meta"]["workspace"]) == {"error"}
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("initial_open_items", [True], indirect=True)
def test_initial_open_items_original_oversized_copy_requires_archive_opening(
    initial_open_items,
):
    env, output, _ = initial_open_items

    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'}));
const source=setup.items.find(row=>row.title==='open-items-it.pdf');
const result=call('vera_workspace_open_items_intake_source',{work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,input_id:source.id});
""",
    )

    assert result["isError"] is True
    assert "Studio Archive" in json.dumps(result["content"])
    assert set(result["_meta"]["workspace"]) == {"error"}
    assert list(output.iterdir()) == []


def test_initial_open_items_viewer_cannot_persist_partial_choices(initial_open_items):
    env, output, _ = initial_open_items
    env["VERA_WORKSPACE_ROLES"] = "VIEWER"
    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'}));
const refused=call('vera_workspace_open_items_intake_draft_save',{work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:'',fields:{currency:'CHF'}});
const result={setup,refused};
""",
    )
    assert result["setup"]["can_prepare"] is False
    assert result["refused"]["isError"] is True
    assert list(output.iterdir()) == []


def test_initial_open_items_partial_choices_remain_private_and_unqualified(
    initial_open_items,
):
    env, output, _ = initial_open_items
    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'}));
const saved=call('vera_workspace_open_items_intake_draft_save',{work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:'',fields:{currency:'CHF',narrative:'Unfinished fictional PRIVATE_SENTINEL'}});
const reopened=call('vera_workspace_open_items_intake_setup',{work_ref:setup.work_ref});
const result={saved,reopened};
""",
    )
    assert (
        result["reopened"]["_meta"]["workspace"]["draft"]["fields"]["currency"] == "CHF"
    )
    assert "PRIVATE_SENTINEL" not in json.dumps(result["reopened"]["content"])
    assert "PRIVATE_SENTINEL" not in json.dumps(result["reopened"]["structuredContent"])
    assert list(output.iterdir()) == []


def test_initial_open_items_foreign_actor_refused_before_draft_read(initial_open_items):
    env, output, _ = initial_open_items
    rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'}));
const result=payload(call('vera_workspace_open_items_intake_draft_save',{work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:'',fields:{narrative:'PRIVATE_OWNER_SENTINEL'}}));
""",
    )
    second_actor = {**env, "VERA_WORKSPACE_ACTOR_ID": "another-fictional-reviewer"}

    result = rpc_program(
        second_actor,
        "const result=call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'});",
    )

    assert result["isError"] is True
    assert "PRIVATE_OWNER_SENTINEL" not in json.dumps(result)
    assert list(output.iterdir()) == []


def test_initial_open_items_changed_source_refused_before_output(initial_open_items):
    env, output, binding = initial_open_items
    loaded = native.workspace_module().load_binding(binding)
    source = (
        Path(loaded["run_root"])
        / loaded["input_manifest"]["inputs"][0]["execution_relative_path"]
    )
    source.write_bytes(source.read_bytes() + b"\nchanged source\n")

    result = rpc_program(
        env,
        "const result=call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'});",
    )

    assert result["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        "delete fields.sources[setup.items[0].id]",
        "fields.sources['unregistered-source']=fields.sources[setup.items[0].id]",
        "delete fields.post_cutoff_events_excluded",
        "fields.reviewed_on='2999-01-01'",
        "fields.language='unsupported'",
    ],
)
def test_initial_open_items_incomplete_scope_refused_before_output(
    initial_open_items, change
):
    env, output, _ = initial_open_items
    program = initial_program().split("const saved=")[0]

    result = rpc_program(
        env,
        program
        + change
        + ";const saved=call('vera_workspace_open_items_intake_draft_save',{...intakeScope,fields});"
        + "const result=saved.isError?saved:call('vera_workspace_open_items_intake_prepare',{...intakeScope,expected_draft_revision:saved._meta.workspace.draft_revision,human_reviewed:true,idempotency_key:'incomplete-scope'});",
    )

    assert result["isError"] is True
    assert list(output.iterdir()) == []
