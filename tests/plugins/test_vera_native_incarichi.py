"""Installed-protocol assignment operations against a disposable owned archive."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_navigation import (  # noqa: F401
    native_call,
    registry_workspace,
)


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
    for ext in ("md", "pdf"):
        path = Path(begin["working_directory"]) / f"Plan.{ext}"
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
    }
    published = native_call(env, "vera_incarico_publish_result", request)
    assert published["current_revision"] == 1
    assert native_call(env, "vera_incarico_publish_result", request)["reused"] is True
    view = native_call(env, "vera_incarico_read", scope)
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
    assert (
        "Business plan" in html
        and "Revisione 1" in html
        and "PDF" in html
        and "MD" in html
    )
