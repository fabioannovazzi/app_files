"""Actual owned Archive byte import, integrity and recovery using fictional files."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import registry_workspace

__all__ = []


@pytest.fixture
def import_workspace(registry_workspace):
    env, studio, _, _, client, engagement = registry_workspace
    env.update(
        VERA_WORKSPACE_ACTOR_ID="fictional-reviewer",
        VERA_WORKSPACE_TENANT_ID="fictional-studio",
        VERA_WORKSPACE_ROLES="REVIEWER",
    )
    return env, studio / "Cliente Beta", client, engagement


def program(
    client: str,
    engagement: str,
    data: bytes,
    body: str,
    name: str = "évidence fictive.bin",
) -> str:
    selected = {"client_id": client, "engagement_id": engagement}
    chosen = {
        "name": name,
        "byte_count": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "role": "source",
    }
    return f"""
const selected={json.dumps(selected)},file={json.dumps(chosen)},bytes=Buffer.from({json.dumps(base64.b64encode(data).decode())},'base64');
const setup=payload(call('vera_workspace_archive_import_setup',selected));
const authority=()=>({{...selected,scope_revision:setup.scope_revision,archive_ticket:setup.archive_ticket,confirmed:true}});
const beginArgs={{...authority(),file,idempotency_key:'fictional-'+require('node:crypto').createHash('sha256').update(file.name).digest('hex')}};
{body}
"""


BEGIN = "const begun=payload(call('vera_workspace_archive_import_begin',beginArgs));"
CHUNKS = """
for(let offset=0;offset<bytes.length;offset+=setup.chunk_bytes){
 const args={...authority(),upload_ref:begun.upload_ref,offset,data:bytes.subarray(offset,offset+setup.chunk_bytes).toString('base64')};
 const received=payload(call('vera_workspace_archive_import_chunk',args));
 const retry=payload(call('vera_workspace_archive_import_chunk',args));
 if(JSON.stringify(received)!==JSON.stringify(retry))throw new Error('Chunk retry differed');
}
"""
FINISH = """
const finishArgs={...authority(),upload_ref:begun.upload_ref};
const finished=payload(call('vera_workspace_archive_import_finish',finishArgs));
const retry=payload(call('vera_workspace_archive_import_finish',finishArgs));
"""


@pytest.mark.parametrize(
    "data",
    [b"Fictional document with no real personal information.", bytes(range(256)) * 513],
)
def test_selected_complete_bytes_register_exact_public_receipt_and_stable_retries(
    import_workspace, data
):
    env, folder, client, engagement = import_workspace
    ledger = _load_customer_ledger()
    before = ledger.list_inputs(folder, engagement)
    runs_before = ledger.list_runs(folder, engagement)
    result = rpc_program(
        env,
        program(
            client,
            engagement,
            data,
            BEGIN
            + "const beginRetry=payload(call('vera_workspace_archive_import_begin',beginArgs));"
            + CHUNKS
            + FINISH
            + "const after=payload(call('vera_workspace_archive_import_setup',selected));const inputs=payload(call('vera_workspace_archive_inputs',selected));const result={begun,beginRetry,finished,retry,after,inputs,modelContent:call('vera_workspace_archive_import_setup',selected).content};",
        ),
    )
    receipt = ledger.load_input_receipt(
        folder, engagement, result["finished"]["input_id"]
    )
    assert Path(receipt["path"]).read_bytes() == data
    assert receipt["sha256"] == hashlib.sha256(data).hexdigest()
    assert receipt["role"] == "source"
    assert receipt["stored_name"] == "évidence fictive.bin"
    assert result["begun"]["upload_ref"] == result["beginRetry"]["upload_ref"]
    assert result["finished"] == result["retry"]
    assert len(ledger.list_inputs(folder, engagement)) == len(before) + 1
    assert ledger.list_runs(folder, engagement) == runs_before
    assert result["after"]["rows"][0]["status"] == "imported"
    assert base64.b64encode(data).decode() not in json.dumps(result["modelContent"])
    assert result["finished"]["workflow_executed"] is False


def test_partial_bytes_reopen_without_importing_or_changing_run_sources(
    import_workspace,
):
    env, folder, client, engagement = import_workspace
    data = b"Fictional source " * 8192
    ledger = _load_customer_ledger()
    before = ledger.list_inputs(folder, engagement)
    result = rpc_program(
        env,
        program(
            client,
            engagement,
            data,
            BEGIN
            + """
const received=payload(call('vera_workspace_archive_import_chunk',{...authority(),upload_ref:begun.upload_ref,offset:0,data:bytes.subarray(0,setup.chunk_bytes).toString('base64')}));
const denied=call('vera_workspace_archive_import_finish',{...authority(),upload_ref:begun.upload_ref});
const result={begun,received,denied};
""",
        ),
    )
    reopened = rpc_program(
        env, program(client, engagement, data, "const result=setup;")
    )
    assert reopened["rows"][0]["received"] == 65536
    assert reopened["rows"][0]["upload_ref"] == result["begun"]["upload_ref"]
    assert reopened["rows"][0]["status"] == "receiving"
    assert result["denied"]["isError"] is True
    assert ledger.list_inputs(folder, engagement) == before


@pytest.mark.parametrize(
    "change",
    ["path", "zero", "too_large", "role", "digest", "unconfirmed", "ticket", "viewer"],
)
def test_invalid_file_choice_or_authority_cannot_allocate_import(
    import_workspace, change
):
    env, folder, client, engagement = import_workspace
    ledger = _load_customer_ledger()
    before = ledger.list_inputs(folder, engagement)
    mutations = {
        "path": "beginArgs.file.name='../escape.bin';",
        "zero": "beginArgs.file.byte_count=0;",
        "too_large": "beginArgs.file.byte_count=67108865;",
        "role": "beginArgs.file.role='automatically-inferred';",
        "digest": "beginArgs.file.sha256='bad';",
        "unconfirmed": "beginArgs.confirmed=false;",
        "ticket": "beginArgs.archive_ticket='forged';",
        "viewer": "",
    }
    if change == "viewer":
        env = {**env, "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        env,
        program(
            client,
            engagement,
            b"Fictional bytes",
            mutations[change]
            + "const result=call('vera_workspace_archive_import_begin',beginArgs);",
        ),
    )
    assert result["isError"] is True
    assert ledger.list_inputs(folder, engagement) == before
    assert not list(
        (folder / ledger.LEDGER_DIRECTORY).glob(
            "engagements/*/.native-imports/*/upload-*"
        )
    )


def test_other_reviewer_cannot_resume_or_see_retained_upload(import_workspace):
    env, folder, client, engagement = import_workspace
    data = b"Fictional evidence"
    initial = rpc_program(
        env, program(client, engagement, data, BEGIN + "const result=begun;")
    )
    foreign = {**env, "VERA_WORKSPACE_ACTOR_ID": "another-fictional-reviewer"}
    result = rpc_program(
        foreign,
        program(
            client,
            engagement,
            data,
            f"const denied=call('vera_workspace_archive_import_finish',{{...authority(),upload_ref:{json.dumps(initial['upload_ref'])}}});const result={{setup,denied}};",
        ),
    )
    assert result["setup"]["rows"] == []
    assert result["denied"]["isError"] is True


@pytest.mark.parametrize(
    "change", ["different_chunk", "out_of_order", "full_hash", "different_begin"]
)
def test_changed_or_out_of_order_bytes_never_register_source(import_workspace, change):
    env, folder, client, engagement = import_workspace
    data = b"Fictional bytes"
    ledger = _load_customer_ledger()
    before = ledger.list_inputs(folder, engagement)
    bodies = {
        "different_chunk": BEGIN
        + CHUNKS
        + "const result=call('vera_workspace_archive_import_chunk',{...authority(),upload_ref:begun.upload_ref,offset:0,data:Buffer.from('Different bytes').toString('base64')});",
        "out_of_order": BEGIN
        + "const result=call('vera_workspace_archive_import_chunk',{...authority(),upload_ref:begun.upload_ref,offset:1,data:bytes.subarray(1).toString('base64')});",
        "full_hash": "beginArgs.file.sha256='0'.repeat(64);"
        + BEGIN
        + CHUNKS
        + "const result=call('vera_workspace_archive_import_finish',{...authority(),upload_ref:begun.upload_ref});",
        "different_begin": BEGIN
        + "const result=call('vera_workspace_archive_import_begin',{...beginArgs,file:{...file,name:'different.bin'}});",
    }
    result = rpc_program(env, program(client, engagement, data, bodies[change]))
    assert result["isError"] is True
    assert ledger.list_inputs(folder, engagement) == before


@pytest.mark.parametrize("phase", ["chunk", "chunk_pre_state", "import"])
def test_explicit_same_byte_recovery_completes_receipted_intent_without_duplicate(
    import_workspace, phase
):
    env, folder, client, engagement = import_workspace
    data = b"Fictional recovery bytes"
    ledger = _load_customer_ledger()
    body = (
        BEGIN + CHUNKS + (FINISH if phase == "import" else "") + "const result={begun};"
    )
    result = rpc_program(env, program(client, engagement, data, body))
    base = next((folder / ledger.LEDGER_DIRECTORY).rglob(result["begun"]["upload_ref"]))
    path = base / (
        "import.json" if phase == "import" else "chunk-request-00000000.json"
    )
    intent = json.loads(path.read_text())
    intent.pop("result")
    path.write_text(json.dumps(intent))
    if phase == "chunk_pre_state":
        (base / "state.json").write_text(json.dumps({"chunks": []}))
    before = ledger.list_inputs(folder, engagement)
    mutation = (
        "const repairArgs={...authority(),upload_ref:"
        + json.dumps(result["begun"]["upload_ref"])
        + (
            "};const action='vera_workspace_archive_import_finish';"
            if phase == "import"
            else ",offset:0,data:bytes.toString('base64')};const action='vera_workspace_archive_import_chunk';"
        )
    )
    repaired = rpc_program(
        env,
        program(
            client,
            engagement,
            data,
            mutation
            + "const denied=call(action,repairArgs);const repaired=payload(call(action,{...repairArgs,recover:true}));const result={denied,repaired};",
        ),
    )
    assert repaired["denied"]["isError"] is True
    if phase == "import":
        assert ledger.list_inputs(folder, engagement) == before
        assert repaired["repaired"]["status"] == "already_imported"
    else:
        assert ledger.list_inputs(folder, engagement) == before
        assert repaired["repaired"]["received"] == len(data)


def test_same_bytes_with_new_filename_use_public_alias_deduplication(import_workspace):
    env, folder, client, engagement = import_workspace
    data = b"Fictional duplicate source"
    ledger = _load_customer_ledger()
    first = rpc_program(
        env,
        program(
            client,
            engagement,
            data,
            BEGIN + CHUNKS + FINISH + "const result=finished;",
            name="first.bin",
        ),
    )
    second = rpc_program(
        env,
        program(
            client,
            engagement,
            data,
            BEGIN + CHUNKS + FINISH + "const result=finished;",
            name="second.bin",
        ),
    )
    receipt = ledger.load_input_receipt(folder, engagement, first["input_id"])
    assert second["input_id"] == first["input_id"]
    assert second["status"] == "already_imported"
    assert receipt["imported_names"] == ["first.bin", "second.bin"]


def test_imported_source_is_explicitly_selected_in_a_fresh_native_run(import_workspace):
    env, folder, client, engagement = import_workspace
    data = b"Fictional registered source for an explicit AML question."
    result = rpc_program(
        env,
        program(
            client,
            engagement,
            data,
            BEGIN
            + CHUNKS
            + FINISH
            + """
const inputs=payload(call('vera_workspace_archive_inputs',selected));
const prepared=payload(call('vera_workspace_archive_prepare',{...scope(inputs),workflow_id:'aml-review',input_ids:[finished.input_id],upstream_artifacts:[],label:'Fictional selected import',purpose:'Review only the chosen registered source',idempotency_key:'import-then-prepare'}));
const listing=payload(call('vera_workspace_open',selected));
const row=listing.works.find(row=>row.run_id===prepared.run_id);
const started=payload(call('vera_workspace_archive_start',scope(row)));
const author=payload(call('vera_workspace_aml_author_setup',{work_ref:prepared.work_ref}));
const result={finished,prepared,started,author};
""",
        ),
    )
    loaded = _load_customer_ledger().load_run(
        folder, engagement, result["prepared"]["run_id"]
    )
    assert loaded["run"]["status"] == "running"
    assert len(loaded["input_manifest"]["inputs"]) == 1
    assert (
        loaded["input_manifest"]["inputs"][0]["binding_id"]
        == result["finished"]["input_id"]
    )
    assert (
        Path(loaded["run_root"])
        / loaded["input_manifest"]["inputs"][0]["execution_relative_path"]
    ).read_bytes() == data
    assert result["author"]["draft"]["fields"]["input_ids"] == []
    assert list(Path(loaded["output_dir"]).iterdir()) == []


def test_interrupted_import_blocks_new_preparation_until_explicit_recovery(
    import_workspace,
):
    env, folder, client, engagement = import_workspace
    data = b"Fictional pending import"
    ledger = _load_customer_ledger()
    result = rpc_program(
        env,
        program(
            client, engagement, data, BEGIN + CHUNKS + FINISH + "const result=begun;"
        ),
    )
    base = next((folder / ledger.LEDGER_DIRECTORY).rglob(result["upload_ref"]))
    receipt = json.loads((base / "import.json").read_text())
    receipt.pop("result")
    (base / "import.json").write_text(json.dumps(receipt))
    blocked = rpc_program(
        env,
        program(
            client,
            engagement,
            data,
            """
const inputs=payload(call('vera_workspace_archive_inputs',selected));
const denied=call('vera_workspace_archive_import_begin',{...beginArgs,idempotency_key:'new-import-while-uncertain'});
const prepare=call('vera_workspace_archive_prepare',{...scope(inputs),workflow_id:'aml-review',input_ids:[inputs.rows[0].input_id],upstream_artifacts:[],label:'Fictional refusal',purpose:'Do not use uncertain imports',idempotency_key:'refused-prepare'});
const result={inputs,denied,prepare};
""",
        ),
    )
    assert blocked["inputs"]["can_prepare"] is False
    assert blocked["inputs"]["import_recovery_required"] is True
    assert blocked["denied"]["isError"] is True
    assert blocked["prepare"]["isError"] is True
