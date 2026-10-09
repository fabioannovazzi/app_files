"""Unfinished app-only bank drafts never qualify or mutate official workpapers."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_bank_preparation import (  # noqa: F401
    INITIAL,
    initial_bank,
)

SOURCE_DRAFT = """
const initial=payload(call('vera_workspace_bank_setup',{work_ref:'initial-bank'}));
const fields={phase:'sources',choices:Object.fromEntries(initial.items.map(row=>[row.id,row.title.startsWith('bank')?'bank':'journal'])),language:'fr',document_language:'auto'};
const args={work_ref:initial.work_ref,revision:initial.revision,review_ticket:initial.review_ticket,expected_draft_revision:'',fields};
"""


def test_bank_source_draft_survives_new_process_without_official_artifacts(
    initial_bank,
):
    env, output, _ = initial_bank
    saved = rpc_program(
        env,
        SOURCE_DRAFT
        + "const result=payload(call('vera_workspace_bank_draft_save',args));",
    )

    reopened = rpc_program(
        env,
        "const result=payload(call('vera_workspace_bank_draft_read',{work_ref:'initial-bank'}));",
    )

    assert saved["draft_saved"] is True
    assert reopened["stale"] is False
    assert reopened["draft"]["fields"]["language"] == "fr"
    assert reopened["draft"]["fields"]["choices"]
    assert reopened["draft"]["draft_revision"] == saved["draft_revision"]
    assert list(output.iterdir()) == []
    path = next((output.parent / ".native-workspace").glob("bank-draft-*.json"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("operation", ["save", "clear"])
def test_bank_draft_stale_checkpoint_cannot_replace_another_panel(
    initial_bank, operation
):
    env, _, _ = initial_bank

    result = rpc_program(
        env,
        SOURCE_DRAFT
        + f"""
const first=payload(call('vera_workspace_bank_draft_save',args));
const {{fields:unused,...clearArgs}}=args;
const changed=call('vera_workspace_bank_draft_{operation}',{json.dumps(operation)}==='clear'?clearArgs:args);
const retained=payload(call('vera_workspace_bank_draft_read',{{work_ref:'initial-bank'}}));
const result={{first,changed,retained}};
""",
    )

    assert result["changed"]["isError"] is True
    assert "draft changed in another panel" in result["changed"]["content"][0]["text"]
    assert (
        result["retained"]["draft"]["draft_revision"]
        == result["first"]["draft_revision"]
    )


@pytest.mark.parametrize(
    "change",
    [
        "fields.choices={'foreign':'bank'}",
        "fields.choices[initial.items[0].id]=[]",
        "fields.language='invalid'",
        "fields.language=[]",
        "fields.professional_approval=true",
        "fields.choices=initial.items.map(row=>row.id)",
        "fields.choices=Object.fromEntries(initial.items.map(row=>[row.id,'sample']))",
        "fields.extra_path='/another-client.csv'",
        "args.review_ticket='forged.signature'",
        "args.revision='f'.repeat(64)",
        "args.expected_draft_revision='not-a-checkpoint'",
    ],
)
def test_bank_draft_invalid_scope_or_fields_write_nothing(initial_bank, change):
    env, output, _ = initial_bank

    result = rpc_program(
        env,
        SOURCE_DRAFT
        + change
        + "; const result=call('vera_workspace_bank_draft_save',args);",
    )

    assert result["isError"] is True
    assert list(output.iterdir()) == []
    assert list((output.parent / ".native-workspace").glob("bank-draft-*.json")) == []


def test_bank_review_draft_preserves_invalid_raw_field_and_never_qualifies(
    initial_bank,
):
    env, output, _ = initial_bank

    result = rpc_program(
        env,
        INITIAL
        + """
const source=page.items[0];
const fields={phase:'review',policy:{default_currency:'CHF',default_entity_ref:'fictional-company'},files:{[source.id]:{mapping:{},options:{header_rows:'['}}},selected_item_id:source.id};
const saved=payload(call('vera_workspace_bank_draft_save',{work_ref:page.work_ref,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:'',fields}));
const draft=payload(call('vera_workspace_bank_draft_read',{work_ref:'initial-bank'}));
const current=payload(call('vera_workspace_bank_setup',{work_ref:'initial-bank'}));
const result={saved,draft,current};
""",
    )

    fields = result["draft"]["draft"]["fields"]
    assert fields["files"][fields["selected_item_id"]]["options"]["header_rows"] == "["
    assert (
        result["draft"]["file_bindings"][fields["selected_item_id"]]["side"] == "bank"
    )
    assert result["current"]["status"] == "inspected"
    assert result["current"]["can_execute"] is False
    assert result["current"]["proposal"]["policy"]["default_currency"] is None
    assert not (output / "reconciliation").exists()


@pytest.mark.parametrize(
    "change",
    [
        "fields.policy.allow_evidence_reuse=true",
        "fields.files={'foreign':{mapping:{},options:{}}}",
        "fields.files[source.id].mapping.foreign='Date'",
        "fields.files[source.id].options.foreign='value'",
        "fields.selected_item_id='foreign'",
        "fields.selected_item_id=[]",
        "fields.policy.default_currency={confirmed:true}",
        "fields.policy.default_currency='x'.repeat(4001)",
        "fields.human_reviewed=true",
    ],
)
def test_bank_review_draft_refuses_undeclared_fields(initial_bank, change):
    env, _, _ = initial_bank

    result = rpc_program(
        env,
        INITIAL
        + """
const source=page.items[0];
const fields={phase:'review',policy:{},files:{[source.id]:{mapping:{},options:{}}},selected_item_id:source.id};
"""
        + change
        + "; const result=call('vera_workspace_bank_draft_save',{work_ref:page.work_ref,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:'',fields});",
    )

    assert result["isError"] is True


def test_bank_source_draft_becomes_stale_after_inspection_and_exact_clear_preserves_outputs(
    initial_bank,
):
    env, output, _ = initial_bank
    result = rpc_program(
        env,
        SOURCE_DRAFT
        + """
const saved=payload(call('vera_workspace_bank_draft_save',args));
const inspection=payload(call('vera_workspace_bank_inspect',{work_ref:initial.work_ref,revision:initial.revision,review_ticket:initial.review_ticket,human_reviewed:true,bank_input_ids:initial.items.filter(row=>row.title.startsWith('bank')).map(row=>row.id),journal_input_ids:initial.items.filter(row=>row.title.startsWith('journal')).map(row=>row.id),language:'it',document_language:'auto',idempotency_key:'draft-inspect'}));
const stale=payload(call('vera_workspace_bank_draft_read',{work_ref:'initial-bank'}));
const current=payload(call('vera_workspace_bank_setup',{work_ref:'initial-bank'}));
const cleared=payload(call('vera_workspace_bank_draft_clear',{work_ref:current.work_ref,revision:current.revision,review_ticket:current.review_ticket,expected_draft_revision:saved.draft_revision}));
const after=payload(call('vera_workspace_bank_draft_read',{work_ref:'initial-bank'}));
const result={stale,cleared,after};
""",
    )

    assert result["stale"]["stale"] is True
    assert result["cleared"]["draft_cleared"] is True
    assert result["after"]["draft"] is None
    assert (output / "bank-preparation").is_dir()


def test_bank_viewer_cannot_save_draft(initial_bank):
    env, output, _ = initial_bank
    env["VERA_WORKSPACE_ROLES"] = "VIEWER"

    result = rpc_program(
        env, SOURCE_DRAFT + "const result=call('vera_workspace_bank_draft_save',args);"
    )

    assert result["isError"] is True
    assert list(output.iterdir()) == []


def test_bank_draft_tampered_bytes_are_refused(initial_bank):
    env, output, _ = initial_bank
    rpc_program(
        env,
        SOURCE_DRAFT
        + "const result=payload(call('vera_workspace_bank_draft_save',args));",
    )
    path = next((output.parent / ".native-workspace").glob("bank-draft-*.json"))
    document = json.loads(path.read_bytes())
    document["fields"]["language"] = "de"
    path.write_text(json.dumps(document))

    result = rpc_program(
        env,
        "const result=call('vera_workspace_bank_draft_read',{work_ref:'initial-bank'});",
    )

    assert result["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("namespace", ["actor", "tenant"])
def test_bank_draft_is_not_read_under_another_authorized_namespace(
    initial_bank, namespace
):
    env, output, _ = initial_bank
    rpc_program(
        env,
        SOURCE_DRAFT
        + "const result=payload(call('vera_workspace_bank_draft_save',args));",
    )
    path = next((output.parent / ".native-workspace").glob("bank-draft-*.json"))
    original = path.read_bytes()
    config = json.loads(Path(env["VERA_WORKSPACE_BINDINGS"]).read_bytes())
    config[namespace + "_id"] = "other-authorized-" + namespace
    other_config = Path(env["VERA_WORKSPACE_BINDINGS"]).with_name("other-bindings.json")
    other_config.write_text(json.dumps(config))
    env["VERA_WORKSPACE_BINDINGS"] = str(other_config)
    env["VERA_WORKSPACE_" + namespace.upper() + "_ID"] = config[namespace + "_id"]

    result = rpc_program(
        env,
        "const result=payload(call('vera_workspace_bank_draft_read',{work_ref:'initial-bank'}));",
    )

    assert result["draft"] is None
    assert path.read_bytes() == original


@pytest.mark.parametrize("link", ["symbolic", "hard"])
def test_bank_draft_linked_existing_file_is_refused(initial_bank, link):
    env, output, _ = initial_bank
    rpc_program(
        env,
        SOURCE_DRAFT
        + "const result=payload(call('vera_workspace_bank_draft_save',args));",
    )
    path = next((output.parent / ".native-workspace").glob("bank-draft-*.json"))
    linked = path.with_suffix(".retained")
    if link == "symbolic":
        path.rename(linked)
        path.symlink_to(linked)
    else:
        os.link(path, linked)

    result = rpc_program(
        env,
        "const result=call('vera_workspace_bank_draft_read',{work_ref:'initial-bank'});",
    )

    assert result["isError"] is True
    assert "regular single-link" in result["content"][0]["text"]
    assert list(output.iterdir()) == []
