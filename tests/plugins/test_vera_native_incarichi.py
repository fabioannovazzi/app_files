"""Installed-protocol assignment operations against a disposable owned archive."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_navigation import (  # noqa: F401
    native_call,
    registry_workspace,
)
from tests.plugins.test_vera_native_workspace import workspace_module


@pytest.mark.parametrize(
    ("workflow", "variable", "identity"),
    [
        (
            "fusione-guidata",
            "VERA_FUSIONE_WORKSPACE_BINDINGS",
            {"case_dir": "case", "operation_id": "op_" + "a" * 32},
        ),
        (
            "trasformazione",
            "VERA_TRANSFORMATION_WORKSPACE_BINDINGS",
            {"case_dir": "case", "case_id": "synthetic-case"},
        ),
        (
            "comunicazione-professionale",
            "VERA_COMMUNICATION_WORKSPACE_BINDINGS",
            {
                "workspace": "case",
                "workspace_id": "communication-one",
                "run_id": "run-one",
            },
        ),
        (
            "presenza-digitale-studio",
            "VERA_WEBSITE_WORKSPACE_BINDINGS",
            {
                "workspace": "case",
                "workspace_id": "website-one",
                "run_id": "20261114T120000Z-aaaaaaaaaa",
            },
        ),
        (
            "contenzioso-tributario",
            "VERA_PRACTICE_WORKSPACE_BINDINGS",
            {"kind": "tax", "run_dir": "case"},
        ),
        (
            "studio-document-format",
            "VERA_PRACTICE_WORKSPACE_BINDINGS",
            {"kind": "format", "workspace": "case", "review_id": "review-one"},
        ),
        (
            "browser-automation",
            "VERA_BROWSER_WORKSPACE_BINDINGS",
            {
                "kind": "batch",
                "directory": "case",
                "batch_id": "batch-one",
                "client_root": "client",
                "client_id": "client_" + "a" * 24,
                "engagement_id": "eng_" + "a" * 24,
            },
        ),
    ],
)
def test_independent_case_identity_preserves_updates_and_rechecks_operator(
    tmp_path, monkeypatch, workflow, variable, identity
):
    """Verify saved binding identity, not specialist engine execution."""
    service = workspace_module()
    monkeypatch.setenv("VERA_WORKSPACE_TENANT_ID", "test-studio")
    monkeypatch.setenv("VERA_WORKSPACE_ACTOR_ID", "test-reviewer")
    path = tmp_path / "bindings.json"
    row = {"work_ref": "selected-work", **identity}
    config = {
        "tenant_id": "test-studio",
        "actor_id": "test-reviewer",
        "bindings": [row],
    }
    path.write_text(json.dumps(config))
    monkeypatch.setenv(variable, str(path))
    first = service.independent_work(workflow, "selected-work")
    row["proposals"] = [
        {"proposal_ref": "new-proposal", "path": "/private/new-proposal.json"}
    ]
    path.write_text(json.dumps(config))
    assert service.independent_work(workflow, "selected-work") == first
    changed_key = next(
        key for key in ("case_dir", "workspace", "directory", "run_dir") if key in row
    )
    row[changed_key] = "different-case"
    path.write_text(json.dumps(config))
    assert (
        service.independent_work(workflow, "selected-work")["binding_identity"]
        != first["binding_identity"]
    )
    assert (
        "proposals" not in first
        and "case_dir" not in first
        and "workspace" not in first
    )
    monkeypatch.setenv("VERA_WORKSPACE_ACTOR_ID", "different-reviewer")
    with pytest.raises(PermissionError):
        service.independent_work(workflow, "selected-work")


def test_native_document_only_assignment_can_open_and_continue(
    registry_workspace, tmp_path
):
    env, root, _, _, client_id, _ = registry_workspace
    ledger = _load_customer_ledger()
    folder = root / "Cliente Beta"
    assignment = ledger.create_engagement(folder, client_id, "Opinion without a run")
    selected = {"client_id": client_id, "engagement_id": assignment["engagement_id"]}
    path = tmp_path / "Parere.md"
    path.write_text("Synthetic opinion: più informazioni.", encoding="utf-8")
    receipt = ledger.import_document(
        folder, client_id, assignment["engagement_id"], path, "support"
    )["receipt"]
    read = native_call(env, "vera_incarico_read", selected)
    reference = {"input_id": receipt["input_id"]}
    assert read["documents"][0]["reference"] == reference
    opened = native_call(
        env, "vera_incarico_document", {**selected, "reference": reference}
    )
    assert opened["preview"] == "Synthetic opinion: più informazioni."
    fields = {
        "purpose": "Prepare the requested opinion",
        "workflow_id": "quesito-legale-fiscale",
        "continuation": "Saved opinion; awaiting additional documents",
        "conversations": [],
        "results": [
            {
                "reference": reference,
                "label": "Saved opinion",
                "sha256": receipt["sha256"],
            }
        ],
    }
    saved = native_call(
        env,
        "vera_incarico_update",
        {**selected, "expected_revision": "", "fields": fields},
    )
    assert saved["saved"] is True
    resumed = native_call(env, "vera_incarico_context", selected)
    assert resumed["purpose"] == fields["purpose"]
    assert resumed["results"][0]["available"] is True
    assert resumed["runs"] == []
    catalogue = native_call(env, "vera_workspace_open", selected)
    assert catalogue["incarico"]["documents"][0]["name"] == "Parere.md"
    assert catalogue["works"] == []


@pytest.mark.parametrize("workflow", ["business-planning", "trasformazione"])
def test_native_begin_publish_and_open_grouped_current_revision(
    registry_workspace, tmp_path, workflow
):
    env, root, _, _, cid, _ = registry_workspace
    ledger = _load_customer_ledger()
    eid = ledger.create_engagement(root / "Cliente Beta", cid, "New plan")[
        "engagement_id"
    ]
    scope = {"client_id": cid, "engagement_id": eid}
    begin = native_call(
        env,
        "vera_incarico_begin",
        {**scope, "workflow_id": workflow, "purpose": "Prepare a plan"},
    )
    assert Path(begin["working_directory"]).is_dir()
    files = []
    source_folder = Path(begin["working_directory"])
    while len(str(source_folder)) < 205:
        source_folder /= "documenti del lavoro conservato"
    source_folder.mkdir(parents=True, exist_ok=True)
    for ext in ("md", "pdf"):
        path = source_folder / f"Plan.{ext}"
        assert len(str(path)) > 200
        path.write_bytes(b"Synthetic grouped format test")
        files.append(
            {
                "format": ext,
                "source_path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    request = {
        **scope,
        "entry_key": "plan",
        "label": "Business plan",
        "files": files,
        "expected_revision": 0,
        "idempotency_key": "test-save",
        "primary_format": "pdf",
    }
    published = native_call(env, "vera_incarico_publish_result", request)
    assert "no associated chat" in published["chat_association_warning"]
    assert published["current_revision"] == 1
    assert native_call(env, "vera_incarico_publish_result", request)["reused"] is True
    view = native_call(env, "vera_incarico_read", scope)
    assert view["deliverables"][0]["versions"][0]["primary_format"] == "pdf"
    assert view["documents"] == []
    assert len(view["deliverables"]) == 1
    assert len(view["deliverables"][0]["versions"][0]["formats"]) == 2
    document = native_call(
        env,
        "vera_incarico_document",
        {**scope, "reference": {"entry_key": "plan", "revision": 1, "format": "md"}},
    )
    assert document["preview"] == "Synthetic grouped format test"
    html = next(
        (root / "Cliente Beta/Vera/Pratiche").glob("*New*/Indice.html")
    ).read_text()
    assert html.index("<h2>Conversazioni</h2>") < html.index("<h2>Documenti</h2>")
    assert "Risultati salvati" not in html and "Documenti acquisiti" not in html
    assert (
        "Business plan" in html
        and "Revisione 1" in html
        and "Plan.pdf" in html
        and "Plan.md" in html
    )


def test_native_publication_reuses_legacy_output_without_rewriting_its_receipt(
    registry_workspace, tmp_path
):
    env, root, _, _, cid, _ = registry_workspace
    ledger = _load_customer_ledger()
    folder = root / "Cliente Beta"
    eid = ledger.create_engagement(folder, cid, "Saved output recovery")[
        "engagement_id"
    ]
    scope = {"client_id": cid, "engagement_id": eid}
    native_call(
        env,
        "vera_incarico_begin",
        {
            **scope,
            "workflow_id": "business-planning",
            "purpose": "Recover the saved plan",
        },
    )
    source = tmp_path / "Business plan.md"
    source.write_text("Synthetic saved plan")
    imported = ledger.import_document(folder, cid, eid, source, "support")["receipt"]
    before = {
        str(p): p.read_bytes()
        for p in (folder / "vera/engagements" / eid).rglob("*")
        if p.is_file()
    }
    request = {
        **scope,
        "entry_key": "plan",
        "label": "Business plan 2027–2029",
        "primary_format": "md",
        "files": [
            {
                "format": "md",
                "source_path": imported["path"],
                "sha256": imported["sha256"],
                "legacy_input_id": imported["input_id"],
            }
        ],
        "expected_revision": 0,
        "idempotency_key": "recover-existing-plan",
    }
    assert (
        native_call(env, "vera_incarico_publish_result", request)["current_revision"]
        == 1
    )
    assert native_call(env, "vera_incarico_publish_result", request)["reused"] is True
    view = native_call(env, "vera_incarico_read", scope)
    assert len(view["deliverables"]) == 1 and view["documents"] == []
    assert all(Path(path).read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize("explicit_parent", [False, True])
def test_begin_captures_origin_before_work_preserving_other_chats(
    registry_workspace, explicit_parent
):
    env, root, _, _, client_id, _ = registry_workspace
    ledger = _load_customer_ledger()
    eid = ledger.create_engagement(root / "Cliente Beta", client_id, "Origin test")[
        "engagement_id"
    ]
    scope = {"client_id": client_id, "engagement_id": eid}
    parent = {
        "host": "codex",
        "thread_id": "11111111-1111-4111-8111-111111111111",
        "title": "Parent user chat",
        "url": "",
    }
    worker = "22222222-2222-4222-8222-222222222222"
    selected_env = {
        **env,
        "CODEX_THREAD_ID": worker if explicit_parent else parent["thread_id"],
    }
    args = {**scope, "workflow_id": "quesito-legale-fiscale", "purpose": "Test origin"}
    if explicit_parent:
        args["originating_conversation"] = parent
    first = native_call(selected_env, "vera_incarico_begin", args)
    assert first["conversation_linked"] is True
    assert first["conversation_link_status"] == "linked"
    assert first["conversation_link_action"] is None
    assert [item["thread_id"] for item in first["conversations"]] == [
        parent["thread_id"]
    ]
    assert (
        native_call(selected_env, "vera_incarico_begin", args)["revision"]
        == first["revision"]
    )
    other = {
        **parent,
        "thread_id": "33333333-3333-4333-8333-333333333333",
        "title": "Later user chat",
    }
    later = native_call(
        selected_env, "vera_incarico_begin", {**args, "originating_conversation": other}
    )
    retry = native_call(selected_env, "vera_incarico_begin", args)
    assert retry["revision"] == later["revision"]
    assert [item["thread_id"] for item in retry["conversations"]] == [
        parent["thread_id"],
        other["thread_id"],
    ]
    page = native_call(selected_env, "vera_workspace_open", scope)
    assert (
        page["incarico"]["conversations"][0]["url"]
        == "codex://threads/" + parent["thread_id"]
    )
    assert page["works"] == []


def test_begin_does_not_turn_archive_session_into_chat_identity(registry_workspace):
    env, root, _, _, client_id, _ = registry_workspace
    ledger = _load_customer_ledger()
    eid = ledger.create_engagement(
        root / "Cliente Beta", client_id, "No host identity"
    )["engagement_id"]
    result = native_call(
        env,
        "vera_incarico_begin",
        {
            "client_id": client_id,
            "engagement_id": eid,
            "workflow_id": "business-planning",
            "purpose": "No chat ID available",
        },
    )
    assert result["conversations"] == []
    assert result["conversation_linked"] is False
    assert result["conversation_link_status"] == "origin_unknown"
    assert "repeat begin" in result["conversation_link_action"]


def test_begin_without_origin_does_not_claim_an_older_chat_is_current(
    registry_workspace,
):
    env, root, _, _, client_id, _ = registry_workspace
    ledger = _load_customer_ledger()
    eid = ledger.create_engagement(root / "Cliente Beta", client_id, "Resume chat")[
        "engagement_id"
    ]
    args = {
        "client_id": client_id,
        "engagement_id": eid,
        "workflow_id": "business-planning",
        "purpose": "Resume",
    }
    origin = {
        "host": "codex",
        "thread_id": "11111111-1111-4111-8111-111111111111",
        "title": "Original chat",
        "url": "",
    }
    first = native_call(
        env, "vera_incarico_begin", {**args, "originating_conversation": origin}
    )
    unknown = native_call(env, "vera_incarico_begin", args)
    assert unknown["conversation_linked"] is False
    assert unknown["conversation_link_status"] == "origin_unknown"
    assert unknown["revision"] == first["revision"]
    assert unknown["conversations"] == first["conversations"]
    current = {**origin, "thread_id": "22222222-2222-4222-8222-222222222222"}
    repaired = native_call(
        env, "vera_incarico_begin", {**args, "originating_conversation": current}
    )
    assert repaired["conversation_link_status"] == "linked"
    assert repaired["conversations"] == [origin, current]
    assert (
        native_call(
            env, "vera_incarico_begin", {**args, "originating_conversation": current}
        )["revision"]
        == repaired["revision"]
    )
