"""Fictional owner-local panel acceptance; no live calendar or host claims."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

__all__ = []
ROOT = Path(__file__).resolve().parents[2]
PLUGIN = Path(
    os.environ.get("VERA_STUDIO_WORK_TEST_PLUGIN_ROOT", str(ROOT / "plugins/vera"))
)
NODE = Path(
    shutil.which("node")
    or "/Users/fabio/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
)


@pytest.fixture
def native(monkeypatch, tmp_path):
    """Load the adapter with test-only import isolation and private owner data."""
    for name in ("studio_work", "native_studio_work"):
        spec = importlib.util.spec_from_file_location(
            name, PLUGIN / "scripts" / (name + ".py")
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
    value = module.NativeStudioWork(tmp_path / "owner")
    yield value
    value.close()


def sourced(title="Fictional task"):
    """Return explicit source-based local fields."""
    return {
        "title": title,
        "kind": "task",
        "source": "Fictional typed user request",
        "status": "open",
    }


def identity(page):
    return {
        "form": page["form"],
        "scope_revision": page["scope_revision"],
        "expected_draft_revision": page["draft"]["revision"],
    }


def saved_draft(native, form="capture", fields=None):
    page = native.page({"form": form})
    return native.dispatch(
        "draft_save",
        {**identity(page), "fields": sourced() if fields is None else fields},
    )


def test_panel_partial_literal_draft_survives_new_session_without_business_write(
    native,
):
    fields = {"notes": "  FICTIONAL PRIVATE NOTE  ", "priority": 0}
    page = saved_draft(native, fields=fields)
    reopened = type(native)(native.service.path.parent)
    try:
        result = reopened.page({"form": "capture"})
    finally:
        reopened.close()
    assert result["draft"]["fields"] == fields
    assert result["draft"]["revision"] == page["draft"]["revision"]
    assert result["counts"] == {
        "items": 0,
        "meetings": 0,
        "operations": 0,
        "history": 0,
    }
    assert "human_confirmed" not in result["draft"]
    assert result["day"] is None


def test_panel_submit_requires_renewed_confirmation(native):
    page = saved_draft(native)
    with pytest.raises(ValueError, match="Renew confirmation"):
        native.dispatch("submit", identity(page))
    assert native.page({})["counts"]["items"] == 0


def test_panel_capture_uses_public_ledger_and_recovery_never_duplicates(native):
    page = saved_draft(native)
    result = native.dispatch("submit", {**identity(page), "human_confirmed": True})
    recovered = native.dispatch("recover", identity(result))
    item = result["draft"]["result"]["item"]
    assert recovered["draft"]["result"]["item"] == item
    assert native.service.record(item["id"]) == item
    assert result["counts"]["items"] == 1
    assert result["counts"]["operations"] == 0
    assert result["draft"]["state"] == "completed"


def test_panel_lost_response_after_public_save_recovers_same_receipt(
    native, monkeypatch
):
    page = saved_draft(native)
    dispatch = native.service.dispatch

    def lost_response(action, args):
        dispatch(action, args)
        raise OSError("Fictional interrupted response")

    monkeypatch.setattr(native.service, "dispatch", lost_response)
    with pytest.raises(OSError, match="interrupted"):
        native.dispatch("submit", {**identity(page), "human_confirmed": True})
    pending = native.page({"form": "capture"})
    monkeypatch.setattr(native.service, "dispatch", dispatch)
    recovered = native.dispatch("recover", identity(pending))
    assert pending["draft"]["state"] == "pending"
    assert recovered["draft"]["state"] == "completed"
    assert recovered["counts"]["items"] == 1
    assert recovered["counts"]["history"] == 1


def test_panel_changed_draft_revision_refuses_overwrite(native):
    page = native.page({"form": "capture"})
    saved_draft(native, fields={"notes": "First fictional panel"})
    with pytest.raises(ValueError, match="Draft changed"):
        native.dispatch(
            "draft_save", {**identity(page), "fields": {"notes": "Second panel"}}
        )
    assert (
        native.page({"form": "capture"})["draft"]["fields"]["notes"]
        == "First fictional panel"
    )


def test_panel_business_revision_change_requires_comparison_then_private_discard(
    native,
):
    page = saved_draft(native)
    item = native.service.dispatch(
        "capture", {"request_key": "other-chat", "item": sourced("Other chat")}
    )["item"]
    with pytest.raises(ValueError, match="Register changed"):
        native.dispatch("submit", {**identity(page), "human_confirmed": True})
    current = native.page({"form": "capture"})
    cleared = native.dispatch("draft_clear", identity(current))
    assert current["draft"]["stale"] is True
    assert cleared["draft"]["fields"] == {}
    assert native.service.record(item["id"])["title"] == "Other chat"


def test_panel_exact_record_change_retains_authoritative_source(native):
    item = native.service.dispatch(
        "capture", {"request_key": "initial", "item": sourced()}
    )["item"]
    page = saved_draft(
        native,
        "record:" + item["id"],
        {"status": "delegated", "owner": "Fictional partner"},
    )
    result = native.dispatch("submit", {**identity(page), "human_confirmed": True})
    current = native.service.record(item["id"])
    assert current["revision"] == 2
    assert current["source"] == item["source"]
    assert current["status"] == "delegated"
    assert result["counts"]["items"] == 1


def test_panel_calendar_linked_change_preserves_public_engine_restriction(native):
    item = native.service.dispatch(
        "capture", {"request_key": "initial", "item": sourced()}
    )["item"]
    body = native.db.execute(
        "SELECT body FROM records WHERE id=?", (item["id"],)
    ).fetchone()[0]
    value = json.loads(body)
    value["calendar"] = {"calendar_id": "fixture-calendar", "event_id": "fixture-event"}
    native.db.execute(
        "UPDATE records SET body=? WHERE id=?", (json.dumps(value), item["id"])
    )
    page = saved_draft(
        native, "record:" + item["id"], {"title": "Fictional moved appointment"}
    )
    with pytest.raises(ValueError, match="Calendar-linked changes"):
        native.dispatch("submit", {**identity(page), "human_confirmed": True})
    assert native.service.record(item["id"])["title"] == item["title"]
    assert native.page({"form": page["form"]})["draft"]["state"] == "draft"


def test_panel_meeting_and_actions_use_existing_atomic_public_save(native):
    fields = {
        "meeting": {
            "title": "Fictional review",
            "date": "2026-10-09",
            "source": "Supplied fictional notes",
            "summary": "No inferred decisions",
        },
        "actions": [sourced("First follow-up"), sourced("Second follow-up")],
    }
    page = saved_draft(native, "meeting", fields)
    result = native.dispatch("submit", {**identity(page), "human_confirmed": True})
    assert result["counts"]["meetings"] == 1
    assert result["counts"]["items"] == 2
    assert len(result["draft"]["result"]["meeting"]["action_ids"]) == 2
    assert result["counts"]["operations"] == 0


def test_panel_invalid_meeting_action_rolls_back_all_authoritative_rows(native):
    fields = {
        "meeting": {
            "title": "Fictional review",
            "date": "2026-10-09",
            "source": "Supplied notes",
        },
        "actions": [sourced(), {"title": "Missing source", "kind": "task"}],
    }
    page = saved_draft(native, "meeting", fields)
    with pytest.raises(ValueError, match="source"):
        native.dispatch("submit", {**identity(page), "human_confirmed": True})
    assert native.page({})["counts"] == {
        "items": 0,
        "meetings": 0,
        "operations": 0,
        "history": 0,
    }


@pytest.mark.parametrize("collection", ["items", "operations", "meetings", "history"])
def test_panel_pages_all_collections_beyond_ordinary_context_caps(native, collection):
    for index in range(65):
        if collection == "items":
            native.service.dispatch(
                "capture",
                {"request_key": "fixture-" + str(index), "item": sourced(str(index))},
            )
        elif collection == "meetings":
            native.service.dispatch(
                "meeting",
                {
                    "request_key": "fixture-" + str(index),
                    "meeting": {
                        "title": str(index),
                        "date": "2026-10-09",
                        "source": "Fictional notes",
                    },
                },
            )
        elif collection == "operations":
            native.db.execute(
                "INSERT INTO operations VALUES(?,?,?,?)",
                (
                    str(index),
                    "fictional-record",
                    "uncertain",
                    json.dumps({"action": "create", "evidence": "FICTIONAL"}),
                ),
            )
        else:
            native.service.audit("fixture", {"index": index})
    first = native.page({"collection": collection})
    second = native.page(
        {
            "collection": collection,
            "offset": first["next_offset"],
            "expected_scope": first["scope_revision"],
        }
    )
    third = native.page(
        {
            "collection": collection,
            "offset": second["next_offset"],
            "expected_scope": first["scope_revision"],
        }
    )
    assert [len(first["items"]), len(second["items"]), len(third["items"])] == [
        30,
        30,
        5,
    ]
    assert third["next_offset"] is None
    assert third["total"] == 65


def test_panel_selected_context_returns_exact_record_without_other_notes(native):
    selected = native.service.dispatch(
        "capture", {"request_key": "first", "item": sourced("Selected")}
    )["item"]
    native.service.dispatch(
        "capture",
        {
            "request_key": "second",
            "item": {**sourced("Other"), "notes": "OTHER PRIVATE NOTE"},
        },
    )
    page = native.page({})
    result = native.dispatch(
        "context",
        {
            "scope_revision": page["scope_revision"],
            "collection": "items",
            "item_id": selected["id"],
        },
    )
    assert result["selection"] == selected
    assert "OTHER PRIVATE NOTE" not in json.dumps(result)
    assert result["external_write_authorized"] is False


def test_panel_other_owner_and_pending_calendar_dispatch_are_rejected(native, tmp_path):
    page = saved_draft(native)
    other = type(native)(tmp_path / "other-owner")
    try:
        with pytest.raises(ValueError, match="Register changed"):
            other.dispatch("draft_save", {**identity(page), "fields": sourced()})
        with pytest.raises(ValueError, match="Unknown native"):
            native.dispatch("claim", {"operation_id": "fictional"})
    finally:
        other.close()


def node_run(tmp_path, code):
    """Use actual bundled Node and actual Python stdio in a fictional owner root."""
    env = {
        **os.environ,
        "VERA_STUDIO_WORK_DATA": str(tmp_path / "mcp-owner"),
        "VERA_STUDIO_WORK_PYTHON": sys.executable,
    }
    result = subprocess.run(
        [str(NODE), "-e", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_panel_mcp_private_payload_and_ordinary_tools_remain_distinct(tmp_path):
    source = json.dumps(str(PLUGIN / "mcp/studio-work.cjs"))
    result = node_run(
        tmp_path,
        f"const s=require({source});s.call('vera_studio_work_capture',{{request_key:'fixture',item:{{title:'PRIVATE FICTIONAL TITLE',kind:'task',source:'PRIVATE FICTIONAL SOURCE'}}}});const r=s.handle({{method:'tools/call',params:{{name:'vera_studio_work_panel_open',arguments:{{}}}}}});const ordinary=s.handle({{method:'tools/call',params:{{name:'vera_studio_work_context',arguments:{{day:'2026-10-09'}}}}}});process.stdout.write(JSON.stringify({{r,ordinary,tools:s.TOOLS}}));",
    )
    assert "PRIVATE FICTIONAL TITLE" not in json.dumps(result["r"]["structuredContent"])
    assert "PRIVATE FICTIONAL SOURCE" not in json.dumps(result["r"]["content"])
    assert (
        result["r"]["_meta"]["studioWork"]["items"][0]["title"]
        == "PRIVATE FICTIONAL TITLE"
    )
    assert (
        result["ordinary"]["structuredContent"]["items"][0]["title"]
        == "PRIVATE FICTIONAL TITLE"
    )
    submit = next(
        row for row in result["tools"] if row["name"] == "vera_studio_work_panel_submit"
    )
    assert submit["_meta"]["ui"]["visibility"] == ["app"]


def test_panel_mcp_strict_ticket_and_resource_use_real_sources(tmp_path):
    source = json.dumps(str(PLUGIN / "mcp/studio-work.cjs"))
    result = node_run(
        tmp_path,
        f"const s=require({source});const p=s.call('vera_studio_work_panel_page',{{form:'capture'}})._meta.studioWork;const args={{form:'capture',scope_revision:p.scope_revision,expected_draft_revision:0,review_ticket:p.review_ticket+'00',fields:{{notes:'FICTIONAL'}}}};const refused=s.handle({{method:'tools/call',params:{{name:'vera_studio_work_panel_draft_save',arguments:args}}}});const good=s.call('vera_studio_work_panel_draft_save',{{...args,review_ticket:p.review_ticket}});const resource=s.handle({{method:'resources/read',params:{{uri:'ui://vera/studio-work-v1.html'}}}});process.stdout.write(JSON.stringify({{refused,good,html:resource.contents[0].text,mime:resource.contents[0].mimeType}}));",
    )
    assert result["refused"]["isError"] is True
    assert result["good"]["_meta"]["studioWork"]["draft"]["fields"] == {
        "notes": "FICTIONAL"
    }
    assert "Quali dati arrivano al modello" in result["html"]
    assert "globalThis.VeraStudioWork" in result["html"]
    assert "/*__JS__*/" not in result["html"]
    assert result["mime"] == "text/html;profile=mcp-app"
