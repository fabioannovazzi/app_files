"""Actual public-store practice regressions; no installed-host acceptance implied."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

from tests.plugins import test_lucia_legal_documents as documents
from tests.plugins import test_studio_document_format as formats
from tests.plugins.test_vera_native_workspace import workspace_module

ROOT = Path(__file__).resolve().parents[2]


def configure(monkeypatch, tmp_path, rows):
    path = tmp_path / "practice-bindings.json"
    path.write_text(
        json.dumps(
            {
                "tenant_id": "fictional-studio",
                "actor_id": "fictional-reviewer",
                "bindings": rows,
            }
        )
    )
    monkeypatch.setenv("VERA_PRACTICE_WORKSPACE_BINDINGS", str(path))
    monkeypatch.setenv("VERA_WORKSPACE_TENANT_ID", "fictional-studio")
    monkeypatch.setenv("VERA_WORKSPACE_ACTOR_ID", "fictional-reviewer")
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "REVIEWER")
    return workspace_module()


@pytest.fixture
def tax_case(tmp_path, monkeypatch):
    run, _ = documents.text_pack(tmp_path)
    monkeypatch.syspath_prepend(str(ROOT / "plugins/lucia/scripts"))
    matter = importlib.import_module("legal_matter")
    matter.initialize(
        run, "contenzioso-tributario", "Fictional tax matter; no legal opinion"
    )
    pack = matter.read_pack(run)
    unit = pack["sources"][0]["units"][0]
    proposal = json.loads((run / "matter.json").read_text())
    proposal["calendar"] = [
        {
            "id": "notice",
            "event": "Fictional notice",
            "event_date": "2025-06-01",
            "due_date": "2025-06-15",
            "status": "conditional",
            "basis": "Fictional reviewer-supplied example; no statutory calculation",
            "reviewer_ref": "",
            "citations": [
                {
                    "source_id": pack["sources"][0]["id"],
                    "anchor": unit["anchor"],
                    "quote": unit["text"],
                }
            ],
        }
    ]
    draft = tmp_path / "initial-calendar.json"
    draft.write_text(json.dumps(proposal))
    matter.save(run, draft, 0)
    service = configure(
        monkeypatch,
        tmp_path,
        [{"work_ref": "tax-one", "kind": "tax", "run_dir": str(run)}],
    )
    return service, run, matter


@pytest.fixture
def format_case(tmp_path, monkeypatch):
    workspace, _ = formats._studio(tmp_path)
    service = configure(
        monkeypatch,
        tmp_path,
        [
            {
                "work_ref": "format-one",
                "kind": "format",
                "workspace": str(workspace),
                "review_id": "format-review-001",
            }
        ],
    )
    return service, workspace


def test_tax_calendar_save_preserves_history_and_exact_retry(tax_case):
    service, run, matter = tax_case
    before = (run / "matter.json").read_bytes()
    view = service.dispatch("vera_workspace_practice_read", {"work_ref": "tax-one"})
    proposal = copy.deepcopy(view["data"]["matter"])
    proposal["calendar"][0].update(
        status="reviewed",
        reviewer_ref="fictional-professional",
        basis="Original reference checked in this fictional exercise",
    )
    args = {
        "work_ref": "tax-one",
        "revision": view["revision"],
        "human_reviewed": True,
        "idempotency_key": "tax-review-one",
        "review": proposal,
    }

    saved = service.dispatch("vera_workspace_practice_tax_save", args)
    repeated = service.dispatch("vera_workspace_practice_tax_save", args)

    assert repeated == saved
    assert saved["data"]["matter"]["calendar"][0]["status"] == "reviewed"
    assert (run / "matter-history/revision-0001.json").read_bytes() == before
    assert (
        "Cronologia" in (run / "matter.html").read_text()
        or "Chronology" in (run / "matter.html").read_text()
    )
    assert matter.status(run)["work_products_recorded"] is False


@pytest.mark.parametrize(
    "fault", ["stale", "unconfirmed", "viewer", "bad_quote", "bad_date"]
)
def test_tax_calendar_refuses_invalid_or_unqualified_save(tax_case, monkeypatch, fault):
    service, run, _ = tax_case
    before = (run / "matter.json").read_bytes()
    view = service.dispatch("vera_workspace_practice_read", {"work_ref": "tax-one"})
    proposal = copy.deepcopy(view["data"]["matter"])
    args = {
        "work_ref": "tax-one",
        "revision": view["revision"],
        "human_reviewed": True,
        "idempotency_key": "refused-tax",
        "review": proposal,
    }
    if fault == "stale":
        args["revision"] = "0" * 64
    elif fault == "unconfirmed":
        args["human_reviewed"] = False
    elif fault == "viewer":
        monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    elif fault == "bad_quote":
        proposal["calendar"][0]["citations"][0]["quote"] = "Not present in the source"
    else:
        proposal["calendar"][0]["due_date"] = "2025-02-30"

    with pytest.raises((ValueError, PermissionError)):
        service.dispatch("vera_workspace_practice_tax_save", args)

    assert (run / "matter.json").read_bytes() == before


def test_tax_context_is_exact_namespaced_selected_event(tax_case):
    service, _, _ = tax_case
    view = service.dispatch("vera_workspace_practice_read", {"work_ref": "tax-one"})

    context = service.dispatch(
        "vera_workspace_practice_context",
        {
            "work_ref": "tax-one",
            "revision": view["revision"],
            "item_id": "calendar:notice",
        },
    )

    assert context["untrusted_evidence"]["item"]["id"] == "notice"
    assert len(context["untrusted_evidence"]["source_units"]) == 1
    assert "matter" not in context["untrusted_evidence"]


def test_format_prepare_leaves_adopted_profile_unchanged_until_explicit_adoption(
    format_case,
):
    service, workspace = format_case
    original = (workspace / "studio_profile.json").read_bytes()
    view = service.dispatch("vera_workspace_practice_read", {"work_ref": "format-one"})
    prepare = {
        "work_ref": "format-one",
        "revision": view["revision"],
        "human_reviewed": True,
        "idempotency_key": "format-prepare-one",
        "settings": {"body_font_size_pt": 11},
    }

    new = service.dispatch("vera_workspace_practice_format_prepare", prepare)
    repeated = service.dispatch("vera_workspace_practice_format_prepare", prepare)

    assert new == repeated
    assert (
        new["data"]["proposal"]["profile"]["document"]["docx"]["body_font_size_pt"]
        == 11
    )
    assert (workspace / "studio_profile.json").read_bytes() == original
    adopted = service.dispatch(
        "vera_workspace_practice_format_approve",
        {
            "work_ref": "format-one",
            "revision": new["revision"],
            "human_reviewed": True,
            "idempotency_key": "format-adopt-one",
            "reviewer": "fictional-professional",
        },
    )
    assert (
        adopted["data"]["current_profile"]["approved_from"]["contribution_digest"]
        == new["data"]["proposal"]["review_digest"]
    )
    assert (workspace / "studio_profile.json").read_bytes() != original


def test_format_read_refuses_tampered_preview(format_case):
    service, workspace = format_case
    preview = workspace / "runs/format-review-001/preview-short.docx"
    preview.write_bytes(preview.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="preview bytes changed"):
        service.dispatch("vera_workspace_practice_read", {"work_ref": "format-one"})


def test_practice_binding_refuses_another_actor(tax_case, monkeypatch):
    service, _, _ = tax_case
    monkeypatch.setenv("VERA_WORKSPACE_ACTOR_ID", "another-actor")

    with pytest.raises(PermissionError, match="another actor"):
        service.dispatch("vera_workspace_practice_read", {"work_ref": "tax-one"})


@pytest.mark.parametrize(
    "action,payload",
    [
        ("tax_save", {"review": {}}),
        ("format_prepare", {"settings": {"body_font_size_pt": 12}}),
        ("format_approve", {"reviewer": "fictional-reviewer"}),
    ],
)
def test_practice_mcp_forgery_is_refused_before_public_write(tax_case, action, payload):
    import os
    import subprocess

    from tests.plugins.test_vera_native_workspace import NODE, SERVER

    _, run, _ = tax_case
    before = (run / "matter.json").read_bytes()
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "vera_workspace_practice_" + action,
            "arguments": {
                "work_ref": "tax-one",
                "revision": "forged",
                "review_ticket": "forged.invalid",
                "human_reviewed": True,
                "idempotency_key": "forged",
                **payload,
            },
        },
    }
    result = subprocess.run(
        [NODE, str(SERVER)],
        input=json.dumps(request) + "\n",
        env={**os.environ, "VERA_WORKSPACE_PYTHON": os.sys.executable},
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    response = json.loads(result.stdout)["result"]
    assert response["isError"] is True
    assert "Invalid review ticket" in result.stdout
    assert (run / "matter.json").read_bytes() == before
