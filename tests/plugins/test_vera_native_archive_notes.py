"""Literal fictional interview sources, private recovery and actual owned imports."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.plugins.test_adeguati_assetti import intelligent_case, review_for
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_aml_authoring import REQUEST, STAGE
from tests.plugins.test_vera_native_archive_imports import import_workspace
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import registry_workspace
from tests.plugins.test_vera_native_assetti_authoring import assetti_program

__all__ = []

NOTE = "\nFictional owner-managed service company.\nI report a monthly policy and two quarterly reports.\nNo independent documents or operating samples supplied.\nDéclaration non vérifiée · € · 🧾\n"


def program(client: str, engagement: str, body: str, text: str = NOTE) -> str:
    """Use current signed owned-engagement tools, preserving literal text."""
    return f"""
const selected={{client_id:{json.dumps(client)},engagement_id:{json.dumps(engagement)}}};
const setup=payload(call('vera_workspace_archive_import_note_read',selected));
const authority=current=>({{...selected,scope_revision:current.scope_revision,archive_ticket:current.archive_ticket,confirmed:true}});
const fields={{name:'colloquio-fittizio.json',reported_by:'Fictional company speaker, attribution unverified',text:{json.dumps(text)}}};
const draftArgs={{...authority(setup),expected_draft_revision:setup.draft.draft_revision,fields}};
{body}
"""


STORE = (
    "const stored=payload(call('vera_workspace_archive_import_note_store',draftArgs));"
)
BEGIN = """
const beginArgs={...authority(stored),expected_draft_revision:stored.draft.draft_revision,idempotency_key:'fictional-literal-note'};
const begun=payload(call('vera_workspace_archive_import_note_begin',beginArgs));
"""
TRANSFER = """
const bytes=Buffer.from(begun.source_text,'utf8');
const transport=payload(call('vera_workspace_archive_import_setup',selected));
for(let offset=0;offset<bytes.length;offset+=transport.chunk_bytes){
 payload(call('vera_workspace_archive_import_chunk',{...authority(transport),upload_ref:begun.upload_ref,offset,data:bytes.subarray(offset,offset+transport.chunk_bytes).toString('base64')}));
}
const finishArgs={...authority(transport),upload_ref:begun.upload_ref};
const finished=payload(call('vera_workspace_archive_import_finish',finishArgs));
"""


@pytest.mark.parametrize("text", [NOTE, NOTE * 1200], ids=["short", "multi_chunk"])
def test_complete_literal_note_conserves_attribution_and_original_without_run_or_model(
    import_workspace, text
):
    env, folder, client, engagement = import_workspace
    ledger = _load_customer_ledger()
    before = ledger.list_inputs(folder, engagement)
    runs = ledger.list_runs(folder, engagement)
    result = rpc_program(
        env,
        program(
            client,
            engagement,
            STORE
            + BEGIN
            + "const beginRetry=payload(call('vera_workspace_archive_import_note_begin',beginArgs));"
            + TRANSFER
            + """
const retry=payload(call('vera_workspace_archive_import_finish',finishArgs));
const read=payload(call('vera_workspace_archive_import_note_read',{...selected,upload_ref:begun.upload_ref}));
const model=call('vera_workspace_archive_import_note_read',selected);
const result={setup,stored,begun,beginRetry,finished,retry,read,modelContent:model.content,modelData:model.structuredContent};
""",
            text,
        ),
    )
    receipt = ledger.load_input_receipt(
        folder, engagement, result["finished"]["input_id"]
    )
    source = Path(receipt["path"]).read_text()
    value = json.loads(source)
    assert value["text"] == text
    assert value["reported_by"] == "Fictional company speaker, attribution unverified"
    assert value["kind"] == "user_statement"
    assert value["capture"]["owner"] == [
        "fictional-reviewer",
        "fictional-studio",
        client,
        engagement,
    ]
    assert value["capture"]["identity_authenticated"] is False
    assert value["capture"]["captured_at"].endswith("+00:00")
    assert "not independent evidence" in value["limitations"]
    assert source == result["begun"]["source_text"] == result["read"]["source_text"]
    assert result["begun"]["upload_ref"] == result["beginRetry"]["upload_ref"]
    assert result["begun"]["source_text"] == result["beginRetry"]["source_text"]
    assert result["begun"]["file"] == result["beginRetry"]["file"]
    assert result["finished"] == result["retry"]
    assert result["read"]["upload"]["origin"] == "user_statement"
    assert result["read"]["upload"]["status"] == "imported"
    assert len(ledger.list_inputs(folder, engagement)) == len(before) + 1
    assert ledger.list_runs(folder, engagement) == runs
    assert receipt["role"] == "source"
    assert NOTE not in json.dumps(result["modelContent"])
    assert "text" not in result["modelData"]
    assert result["finished"]["workflow_executed"] is False


def test_private_note_draft_reopens_exact_text_with_no_official_source(
    import_workspace,
):
    env, folder, client, engagement = import_workspace
    ledger = _load_customer_ledger()
    before = ledger.list_inputs(folder, engagement)
    result = rpc_program(
        env, program(client, engagement, STORE + "const result=stored;")
    )
    reopened = rpc_program(env, program(client, engagement, "const result=setup;"))
    assert reopened["draft"] == result["draft"]
    assert reopened["draft"]["fields"]["text"] == NOTE
    assert reopened["retained"] == []
    assert "confirmed" not in reopened["draft"]
    assert ledger.list_inputs(folder, engagement) == before


@pytest.mark.parametrize(
    "change", ["viewer", "ticket", "scope", "cas", "path", "type", "too_large"]
)
def test_invalid_literal_draft_authority_or_shape_cannot_create_source(
    import_workspace, change
):
    env, folder, client, engagement = import_workspace
    if change == "viewer":
        env = {**env, "VERA_WORKSPACE_ROLES": "VIEWER"}
    edits = {
        "viewer": "",
        "ticket": "draftArgs.archive_ticket='forged';",
        "scope": "draftArgs.scope_revision='changed';",
        "cas": "draftArgs.expected_draft_revision='0'.repeat(64);",
        "path": "draftArgs.fields.name='../outside.json';",
        "type": "draftArgs.fields.text={invented:true};",
        "too_large": "draftArgs.fields.text='🧾'.repeat(70000);",
    }
    result = rpc_program(
        env,
        program(
            client,
            engagement,
            edits[change]
            + "const result=call('vera_workspace_archive_import_note_store',draftArgs);",
        ),
    )
    assert result["isError"] is True
    assert not list(
        (folder / "Vera").glob(
            "engagements/*/.native-imports/*/upload-*/original-note.json"
        )
    )


@pytest.mark.parametrize(
    "change", ["empty", "unconfirmed", "stale_cas", "same_draft_new_key"]
)
def test_literal_source_capture_requires_exact_complete_confirmed_draft(
    import_workspace, change
):
    env, folder, client, engagement = import_workspace
    before = _load_customer_ledger().list_inputs(folder, engagement)
    prefix = "fields.text='';" if change == "empty" else ""
    edit = {
        "empty": "",
        "unconfirmed": "args.confirmed=false;",
        "stale_cas": "args.expected_draft_revision='0'.repeat(64);",
        "same_draft_new_key": BEGIN,
    }[change]
    body = (
        prefix
        + STORE
        + edit
        + "const args={...authority(stored),expected_draft_revision:stored.draft.draft_revision,idempotency_key:'another-note'};"
        + (edit if change in {"unconfirmed", "stale_cas"} else "")
        + "const result=call('vera_workspace_archive_import_note_begin',args);"
    )
    # Only the duplicate probe captures an original; none imports an official source.
    if change in {"unconfirmed", "stale_cas"}:
        body = (
            prefix
            + STORE
            + "const args={...authority(stored),expected_draft_revision:stored.draft.draft_revision,idempotency_key:'another-note'};"
            + edit
            + "const result=call('vera_workspace_archive_import_note_begin',args);"
        )
    result = rpc_program(env, program(client, engagement, body))
    assert result["isError"] is True
    assert _load_customer_ledger().list_inputs(folder, engagement) == before


def test_draft_clear_keeps_original_and_recovery_uses_its_exact_bytes(import_workspace):
    env, folder, client, engagement = import_workspace
    before = _load_customer_ledger().list_inputs(folder, engagement)
    initial = rpc_program(
        env, program(client, engagement, STORE + BEGIN + "const result=begun;")
    )
    cleared = rpc_program(
        env,
        program(
            client,
            engagement,
            "const clear=payload(call('vera_workspace_archive_import_note_clear',{...authority(setup),expected_draft_revision:setup.draft.draft_revision}));const read=payload(call('vera_workspace_archive_import_note_read',{...selected,upload_ref:"
            + json.dumps(initial["upload_ref"])
            + "}));const result={clear,read};",
        ),
    )
    assert cleared["clear"]["draft"]["draft_revision"] == ""
    assert cleared["read"]["source_text"] == initial["source_text"]
    assert json.loads(cleared["read"]["source_text"])["text"] == NOTE
    assert _load_customer_ledger().list_inputs(folder, engagement) == before


def test_foreign_actor_does_not_read_another_literal_draft_or_captured_original(
    import_workspace,
):
    env, _, client, engagement = import_workspace
    initial = rpc_program(
        env, program(client, engagement, STORE + BEGIN + "const result=begun;")
    )
    foreign = {**env, "VERA_WORKSPACE_ACTOR_ID": "different-fictional-reviewer"}
    result = rpc_program(
        foreign,
        program(
            client,
            engagement,
            "const denied=call('vera_workspace_archive_import_note_read',{...selected,upload_ref:"
            + json.dumps(initial["upload_ref"])
            + "});const result={setup,denied};",
        ),
    )
    assert result["setup"]["draft"]["draft_revision"] == ""
    assert result["setup"]["retained"] == []
    assert result["denied"]["isError"] is True


def test_altered_captured_original_refuses_import_and_new_run_preparation(
    import_workspace,
):
    env, folder, client, engagement = import_workspace
    before = _load_customer_ledger().list_inputs(folder, engagement)
    initial = rpc_program(
        env, program(client, engagement, STORE + BEGIN + "const result={setup,begun};")
    )
    original = next(
        (folder / "Vera").glob(
            "engagements/*/.native-imports/*/upload-*/original-note.json"
        )
    )
    original.write_text('{"text":"tampered"}')
    result = rpc_program(
        env,
        "const result=call('vera_workspace_archive_import_note_read',"
        + json.dumps({"client_id": client, "engagement_id": engagement})
        + ");",
    )
    assert result["isError"] is True
    args = {
        "client_id": client,
        "engagement_id": engagement,
        "scope_revision": initial["setup"]["scope_revision"],
        "archive_ticket": initial["setup"]["archive_ticket"],
        "confirmed": True,
        "workflow_id": "adeguati-assetti",
        "input_ids": [before[0]["input_id"]],
        "upstream_artifacts": [],
        "label": "Refused changed original",
        "purpose": "Must not adopt tampered capture.",
        "idempotency_key": "tampered-note",
    }
    refused = rpc_program(
        env,
        "const result=call('vera_workspace_archive_prepare'," + json.dumps(args) + ");",
    )
    assert refused["isError"] is True
    assert _load_customer_ledger().list_inputs(folder, engagement) == before


def test_note_source_prepares_native_assetti_and_conserves_reported_evidence_only(
    import_workspace, tmp_path
):
    env, folder, client, engagement = import_workspace
    result = rpc_program(
        env,
        program(
            client,
            engagement,
            STORE
            + BEGIN
            + TRANSFER
            + """
const inputs=payload(call('vera_workspace_archive_inputs',selected));
const prepared=payload(call('vera_workspace_archive_prepare',{...authority(inputs),workflow_id:'adeguati-assetti',input_ids:[finished.input_id],upstream_artifacts:[],label:'Fictional first interview',purpose:'Assess reported practice and evidence gaps.',idempotency_key:'fictional-first-assetti'}));
const listed=payload(call('vera_workspace_open',selected));
const work=listed.works.find(w=>w.run_id===prepared.run_id);
const started=payload(call('vera_workspace_archive_start',{...authority(work),run_id:work.run_id}));
const result={finished,prepared,started,work};
""",
        ),
    )
    ledger = _load_customer_ledger()
    loaded = ledger.load_run(folder, engagement, result["prepared"]["run_id"])
    source = (
        Path(loaded["run_root"])
        / loaded["input_manifest"]["inputs"][0]["execution_relative_path"]
    )
    review = review_for(source, Path(loaded["run_root"]) / "inputs")
    review["intelligent_review"] = copy.deepcopy(
        intelligent_case(tmp_path)["intelligent_review"]
    )
    review["as_of"] = "2026-10-07"
    review["observations"][0].update(
        description="The fictional speaker reports monthly policy and quarterly reports; no operating samples supplied.",
        evidence_state="reported",
    )
    review["intelligent_review"]["processes"][0][
        "operation"
    ] = "Quarterly reports are reported; actual delivery and use unverified."
    review["intelligent_review"]["chronology"][0][
        "event"
    ] = "Original statement captured; capture time is not prior information availability."
    review["limitations"] = (
        "Only a declared user statement; no independent operating evidence or authenticated attribution."
    )
    proposal = rpc_program(
        env,
        assetti_program(
            result["work"]["work_ref"],
            review,
            REQUEST
            + STAGE
            + "const published=payload(call('vera_workspace_assetti_author_publish',publishArgs));const result={context,read,published};",
        ),
    )
    assert json.loads(source.read_text())["text"] == NOTE
    assert (
        proposal["context"]["sources"][0]["sha256"]
        == loaded["input_manifest"]["inputs"][0]["sha256"]
    )
    assert (
        proposal["read"]["record"]["review"]["observations"][0]["evidence_state"]
        == "reported"
    )
    assert (
        proposal["read"]["record"]["review"]["intelligent_review"]
        == review["intelligent_review"]
    )
    assert proposal["published"]["status"] == "draft_for_review"
    assert "professional_decision" not in proposal["read"]["record"]["review"]
    assert (
        ledger.load_run(folder, engagement, loaded["run"]["run_id"])["run"]["status"]
        == "running"
    )


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_extracted_literal_notes_use_actual_public_import_without_native_host_claim(
    import_workspace, tmp_path, surface
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, folder, client, engagement = import_workspace
    builder = load_builder(
        "build_codex_plugin_zip" if surface == "codex" else "build_claude_plugin_zip"
    )
    if surface == "codex":
        vera = next(item for item in builder.load_bundles() if item.name == "vera")
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        _, packages = builder.load_configuration()
        vera = next(item for item in packages if item.plugin == "vera")
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
        program(
            client, engagement, STORE + BEGIN + TRANSFER + "const result=finished;"
        ),
        server=target / "mcp/workspace.cjs",
    )
    receipt = _load_customer_ledger().load_input_receipt(
        folder, engagement, result["input_id"]
    )
    assert json.loads(Path(receipt["path"]).read_text())["text"] == NOTE
    assert receipt["role"] == "source"
    assert result["workflow_executed"] is False
    assert (target / "scripts/native_archive_imports.py").read_bytes() == (
        Path("plugins/vera/scripts/native_archive_imports.py").read_bytes()
    )


def test_literal_draft_concurrent_cas_does_not_replace_other_panel_fields(
    import_workspace,
):
    env, _, client, engagement = import_workspace
    result = rpc_program(
        env,
        program(
            client,
            engagement,
            STORE
            + "const stale=call('vera_workspace_archive_import_note_store',{...draftArgs,fields:{...fields,text:'Different panel'}});const current=payload(call('vera_workspace_archive_import_note_read',selected));const result={stored,stale,current};",
        ),
    )
    assert result["stale"]["isError"] is True
    assert result["current"]["draft"] == result["stored"]["draft"]
    assert result["current"]["draft"]["fields"]["text"] == NOTE


@pytest.mark.parametrize("link", ["hardlink", "dangling_draft", "owner_directory"])
def test_literal_draft_linked_file_or_owner_directory_refuses_scope_escape(
    import_workspace, tmp_path, link
):
    env, folder, client, engagement = import_workspace
    rpc_program(env, program(client, engagement, STORE + "const result=stored;"))
    draft = next(
        (folder / "Vera").glob("engagements/*/.native-imports/*/note-draft.json")
    )
    if link == "hardlink":
        (tmp_path / "linked-note.json").hardlink_to(draft)
    elif link == "dangling_draft":
        draft.unlink()
        draft.symlink_to(tmp_path / "missing-note.json")
    else:
        owner = draft.parent
        draft.unlink()
        owner.rmdir()
        owner.symlink_to(tmp_path, target_is_directory=True)
    result = rpc_program(
        env,
        'const result=call("vera_workspace_archive_import_note_read",'
        + json.dumps({"client_id": client, "engagement_id": engagement})
        + ");",
    )
    assert result["isError"] is True


def test_captured_note_can_finish_after_private_draft_discard(import_workspace):
    env, folder, client, engagement = import_workspace
    result = rpc_program(
        env,
        program(
            client,
            engagement,
            STORE
            + BEGIN
            + "const original=begun;payload(call('vera_workspace_archive_import_note_clear',{...authority(stored),expected_draft_revision:stored.draft.draft_revision}));"
            + TRANSFER
            + "const read=payload(call('vera_workspace_archive_import_note_read',{...selected,upload_ref:original.upload_ref}));const result={original,finished,read};",
        ),
    )
    assert result["read"]["draft"]["draft_revision"] == ""
    assert result["read"]["source_text"] == result["original"]["source_text"]
    receipt = _load_customer_ledger().load_input_receipt(
        folder, engagement, result["finished"]["input_id"]
    )
    assert json.loads(Path(receipt["path"]).read_text())["text"] == NOTE
