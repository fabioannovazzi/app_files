"""Actual unchanged Rating engine and registered Archive/MCP integration.

All facts are fictional and prequalified; no model, legal or host acceptance.
"""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import pytest

from tests.plugins._native_review_tickets import assert_same_retained_response
from tests.plugins.test_rating_legalita_case import CASE, prepared_case
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import configure, workspace_module

__all__ = []


@pytest.fixture
def rating_run(tmp_path, monkeypatch, request):
    """Register originals and authored case before public preparation/start."""
    variant = getattr(request, "param", "ready")
    ledger = _load_customer_ledger()
    client = tmp_path / "Fictional Rating client"
    client.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(client, client_id, "Fictional Rating case")
    case = prepared_case(tmp_path)
    case["client"].update(
        archive_client_id=client_id, engagement_id=engagement["engagement_id"]
    )
    imported = ledger.import_document(
        client,
        client_id,
        engagement["engagement_id"],
        tmp_path / "evidence.txt",
        "source",
    )["receipt"]
    ids = [imported["input_id"]]
    case["evidence"][0]["uri"] = f"imports/{imported['input_id']}/evidence.txt"
    if variant == "partial":
        case["snapshots"][-1]["instances"][0].update(
            status="claimed", outcome="unknown", decision=None
        )
    if variant == "failed":
        case["snapshots"][-1]["instances"][0].update(
            status="failed", outcome="not_satisfied"
        )
    if variant == "foreign":
        case["evidence"][0]["uri"] = "unregistered/evidence.txt"
    if variant == "client":
        case["client"]["archive_client_id"] = "client_222222222222222222222222"
    if variant == "prerequisite":
        case["synthetic"] = False
        case["evidence"][0]["kind"] = "document"
    if variant == "quote":
        case["snapshots"][-1]["instances"][0]["evidence_links"][0][
            "excerpt"
        ] = "FICTIONAL ABSENT QUOTATION"
    if variant == "many":
        case["limitations"] = [f"Fictional complete limitation {i}" for i in range(91)]
    source = tmp_path / "fictional-rating-case.json"
    source.write_text(json.dumps(case))
    ids.append(
        ledger.import_document(
            client, client_id, engagement["engagement_id"], source, "source"
        )["receipt"]["input_id"]
    )
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "rating-legalita",
        "development",
        input_ids=ids,
    )
    started = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    binding = {
        "work_ref": "fictional-rating",
        "client_root": str(client),
        **{
            k: started["context"][k]
            for k in ("client_id", "engagement_id", "run_id", "workflow_id")
        },
    }
    return (
        configure(monkeypatch, tmp_path, [binding]),
        Path(started["output_dir"]),
        binding,
    )


SELECT = """
const setup=payload(call('vera_workspace_rating_setup',{work_ref:'fictional-rating'}));
const ratingScope={work_ref:setup.work_ref,revision:setup.revision,source_ref:setup.source_ref};
const fields={case_input_id:setup.items[0].id,previous_input_id:'',note:'FICTIONAL private unfinished note'};
const saved=payload(call('vera_workspace_rating_draft_save',{...ratingScope,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields}));
const preview=payload(call('vera_workspace_rating_read',{...ratingScope,fields}));
const args={...ratingScope,review_ticket:setup.review_ticket,expected_draft_revision:saved.draft_revision,fields,preview_ref:preview.preview_ref,confirmed:true,idempotency_key:'fictional-render'};
"""

RENDER = (
    SELECT + "const rendered=payload(call('vera_workspace_rating_execute',args));\n"
)


@pytest.mark.parametrize(
    "rating_run,status",
    [
        ("ready", "ready_for_review"),
        ("partial", "incomplete"),
        ("failed", "not_eligible"),
    ],
    indirect=["rating_run"],
)
def test_rating_unchanged_engine_retains_public_status_and_exact_artifacts(
    rating_run, status
):
    env, output, _ = rating_run
    result = rpc_program(
        env,
        RENDER
        + """
const retry=payload(call('vera_workspace_rating_execute',args));
const reopened=payload(call('vera_workspace_rating_setup',{work_ref:setup.work_ref}));
const read=payload(call('vera_workspace_rating_read',{work_ref:reopened.work_ref,revision:reopened.revision,source_ref:reopened.source_ref,fields}));
const artifact=payload(call('vera_workspace_rating_artifact',{work_ref:reopened.work_ref,revision:reopened.revision,source_ref:reopened.source_ref,artifact_ref:rendered.record_sha256+'/dossier.md'}));
const result={rendered,retry,reopened,read,artifact};
""",
    )
    assert result["rendered"]["status"] == status
    assert_same_retained_response(result["rendered"], result["retry"])
    assert result["rendered"]["run_completed"] is False
    assert result["rendered"]["submission_authorized"] is False
    assert result["rendered"]["professional_approval_added"] is False
    assert result["reopened"]["can_render"] is False
    assert result["reopened"]["draft_stale"] is True
    record = json.loads(
        (output / result["rendered"]["record_sha256"] / "dossier.json").read_bytes()
    )
    assert record == result["read"]["record"]
    assert record["assessment"]["official_rating"] is None
    assert "FICTIONAL private unfinished note" not in result["read"]["report"]
    assert base64.b64decode(
        result["artifact"]["base64"]
    ).decode() == CASE.render_dossier(record)


@pytest.mark.parametrize(
    "rating_run", ["foreign", "client", "prerequisite", "quote"], indirect=True
)
def test_rating_invalid_evidence_identity_prerequisites_or_quotes_never_project_or_render(
    rating_run,
):
    env, output, _ = rating_run
    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_rating_setup',{work_ref:'fictional-rating'}));
const fields={case_input_id:setup.items[0].id,previous_input_id:'',note:''};
const result=call('vera_workspace_rating_read',{work_ref:setup.work_ref,revision:setup.revision,source_ref:setup.source_ref,fields});
""",
    )
    assert result["isError"] is True
    assert set(result["_meta"]["workspace"]) == {"error"}
    assert not list(output.iterdir())


def test_rating_private_draft_recovers_literal_fields_without_consent(rating_run):
    env, output, _ = rating_run
    result = rpc_program(
        env,
        SELECT
        + """
const result=payload(call('vera_workspace_rating_setup',{work_ref:setup.work_ref}));
""",
    )
    assert result["fields"]["note"] == "FICTIONAL private unfinished note"
    assert result["draft_stale"] is False
    assert "confirmed" not in result["fields"]
    assert result["artifacts"] == []
    assert list((output.parent / ".native-workspace").glob("rating-draft-*.json"))


def test_rating_draft_conflict_preserves_original_fields(rating_run):
    env, _, _ = rating_run
    result = rpc_program(
        env,
        SELECT
        + """
const stale=call('vera_workspace_rating_draft_save',{...ratingScope,review_ticket:setup.review_ticket,expected_draft_revision:'',fields:{...fields,note:'new conflicting note'}});
const reopened=payload(call('vera_workspace_rating_setup',{work_ref:setup.work_ref}));
const result={stale,reopened};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["reopened"]["fields"]["note"] == "FICTIONAL private unfinished note"


@pytest.mark.parametrize("changed", ["preview", "consent", "fields", "ticket"])
def test_rating_render_requires_exact_whole_preview_saved_fields_consent_and_signature(
    rating_run, changed
):
    env, output, _ = rating_run
    replacements = {
        "preview": "preview_ref:'0'.repeat(64)",
        "consent": "confirmed:false",
        "fields": "fields:{...fields,note:'different'}",
        "ticket": "review_ticket:'forged.signature'",
    }
    result = rpc_program(
        env,
        SELECT
        + f"const result=call('vera_workspace_rating_execute',{{...args,{replacements[changed]}}});",
    )
    assert result["isError"] is True
    assert not list(output.iterdir())


def test_rating_viewer_can_read_whole_registered_case_but_cannot_write(rating_run):
    env, output, _ = rating_run
    env = {**env, "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_rating_setup',{work_ref:'fictional-rating'}));
const fields={case_input_id:setup.items[0].id,previous_input_id:'',note:''};
const ratingScope={work_ref:setup.work_ref,revision:setup.revision,source_ref:setup.source_ref};
const read=payload(call('vera_workspace_rating_read',{...ratingScope,fields}));
const denied=call('vera_workspace_rating_draft_save',{...ratingScope,review_ticket:setup.review_ticket,expected_draft_revision:'',fields});
const result={setup,read,denied};
""",
    )
    assert result["setup"]["can_write"] is False
    assert result["read"]["record"]["case"]["subjects"][0]["subject_id"] == "PERSON-1"
    assert result["denied"]["isError"] is True
    assert not list(output.iterdir())


@pytest.mark.parametrize("rating_run", ["many"], indirect=True)
def test_rating_whole_preview_keeps_all_limitations_and_instances(rating_run):
    env, _, _ = rating_run
    result = rpc_program(env, SELECT + "const result=preview;")
    assert len(result["record"]["case"]["limitations"]) == 91
    assert len(result["record"]["case"]["snapshots"][-1]["instances"]) == 41
    assert "Fictional complete limitation 90" in result["report"]


def test_rating_uncertain_intent_stops_render_and_keeps_evidence(rating_run):
    env, output, binding = rating_run
    module = workspace_module()
    private = module.ui_state_directory(output)
    value = {
        "request_sha256": "1" * 64,
        "owner_scope": [
            env["VERA_WORKSPACE_ACTOR_ID"],
            env["VERA_WORKSPACE_TENANT_ID"],
            *[
                binding[k]
                for k in ("client_id", "engagement_id", "run_id", "workflow_id")
            ],
        ],
    }
    module.atomic_json(
        private / "rating-request-uncertain.json",
        {**value, "content_sha256": module.digest(value)},
    )
    result = rpc_program(
        env, SELECT + "const result=call('vera_workspace_rating_execute',args);"
    )
    assert result["isError"] is True
    assert (private / "rating-request-uncertain.json").is_file()
    assert not list(output.iterdir())


def test_rating_generic_review_mutation_is_refused(rating_run):
    _, output, _ = rating_run
    module = workspace_module()
    with pytest.raises(ValueError, match="immutable proposals"):
        module.dispatch("vera_workspace_draft_save", {"work_ref": "fictional-rating"})
    assert not list(output.iterdir())


@pytest.fixture
def recovered_rating_run(rating_run):
    """Explicit existing-file fixture; does not qualify the broken first-save path."""
    env, output, binding = rating_run
    module = workspace_module()
    setup = module.dispatch(
        "vera_workspace_rating_setup", {"work_ref": binding["work_ref"]}
    )
    owner = [
        env["VERA_WORKSPACE_ACTOR_ID"],
        env["VERA_WORKSPACE_TENANT_ID"],
        *[binding[k] for k in ("client_id", "engagement_id", "run_id", "workflow_id")],
    ]
    module.atomic_json(
        module.ui_state_directory(output)
        / ("rating-draft-" + module.digest(owner) + ".json"),
        {
            "owner_scope": owner,
            "revision": setup["revision"],
            "fields": {"case_input_id": "", "previous_input_id": "", "note": ""},
        },
    )
    return rating_run


@pytest.mark.parametrize(
    "rating_run,status",
    [
        ("ready", "ready_for_review"),
        ("partial", "incomplete"),
        ("failed", "not_eligible"),
    ],
    indirect=["rating_run"],
)
def test_rating_existing_draft_actual_public_render_replay_and_exact_download(
    recovered_rating_run, status
):
    env, output, _ = recovered_rating_run
    result = rpc_program(
        env,
        RENDER
        + """
const retry=payload(call('vera_workspace_rating_execute',args));
const reopened=payload(call('vera_workspace_rating_setup',{work_ref:setup.work_ref}));
const read=payload(call('vera_workspace_rating_read',{work_ref:reopened.work_ref,revision:reopened.revision,source_ref:reopened.source_ref,fields}));
const downloaded=payload(call('vera_workspace_rating_artifact',{work_ref:reopened.work_ref,revision:reopened.revision,source_ref:reopened.source_ref,artifact_ref:rendered.record_sha256+'/dossier.md'}));
const result={rendered,retry,reopened,read,downloaded};
""",
    )
    assert result["rendered"]["status"] == status
    assert_same_retained_response(result["rendered"], result["retry"])
    assert result["rendered"]["professional_approval_added"] is False
    assert result["rendered"]["run_completed"] is False
    assert result["read"]["record"]["assessment"]["official_rating"] is None
    assert result["read"]["record"]["assessment"]["submission_authorized"] is False
    assert result["reopened"]["draft_stale"] is True
    report = (output / result["rendered"]["record_sha256"] / "dossier.md").read_bytes()
    assert base64.b64decode(result["downloaded"]["base64"]) == report
    assert "FICTIONAL private unfinished note" not in report.decode()


@pytest.mark.parametrize("changed", ["preview", "consent", "fields", "ticket"])
def test_rating_existing_draft_exact_preview_confirmation_fields_and_signature_are_required(
    recovered_rating_run, changed
):
    env, output, _ = recovered_rating_run
    replacements = {
        "preview": "preview_ref:'0'.repeat(64)",
        "consent": "confirmed:false",
        "fields": "fields:{...fields,note:'different'}",
        "ticket": "review_ticket:'forged.signature'",
    }
    result = rpc_program(
        env,
        SELECT
        + f"const result=call('vera_workspace_rating_execute',{{...args,{replacements[changed]}}});",
    )
    assert result["isError"] is True
    assert not list(output.iterdir())


def test_rating_existing_draft_unsafe_artifact_path_is_refused(recovered_rating_run):
    env, _, _ = recovered_rating_run
    result = rpc_program(
        env,
        RENDER
        + """
const reopened=payload(call('vera_workspace_rating_setup',{work_ref:setup.work_ref}));
const result=call('vera_workspace_rating_artifact',{work_ref:reopened.work_ref,revision:reopened.revision,source_ref:reopened.source_ref,artifact_ref:'../../private.txt'});
""",
    )
    assert result["isError"] is True
    assert "exact verified Rating artifact" in result["content"][0]["text"]


def test_rating_existing_draft_completed_receipt_tamper_is_refused(
    recovered_rating_run,
):
    env, output, _ = recovered_rating_run
    rpc_program(env, RENDER + "const result=rendered;")
    receipt_path = next(
        (output.parent / ".native-workspace").glob("rating-request-*.json")
    )
    receipt = json.loads(receipt_path.read_bytes())
    receipt["result"]["status"] = "forged_official_rating"
    receipt_path.write_text(json.dumps(receipt))
    result = rpc_program(
        env,
        "const result=call('vera_workspace_rating_setup',{work_ref:'fictional-rating'});",
    )
    assert result["isError"] is True
    assert "receipt hash changed" in result["content"][0]["text"]


def test_rating_existing_draft_altered_idempotency_key_cannot_render_again(
    recovered_rating_run,
):
    env, output, _ = recovered_rating_run
    result = rpc_program(
        env,
        RENDER
        + "const result=call('vera_workspace_rating_execute',{...args,fields:{...fields,note:'altered'}});",
    )
    assert result["isError"] is True
    assert "different fields" in result["content"][0]["text"]
    assert len(list(output.glob("*/dossier.json"))) == 1
