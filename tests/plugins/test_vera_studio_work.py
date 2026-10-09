"""Persistent process acceptance with fictional connector receipts, not live Google."""

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
PLUGIN = ROOT / "plugins/vera"


def load_service():
    """Load the source without altering production imports."""
    spec = importlib.util.spec_from_file_location(
        "studio_work", PLUGIN / "scripts/studio_work.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_ledger_storage_is_permanent_even_in_codex_sandbox(
    monkeypatch, tmp_path
):
    module = load_service()
    monkeypatch.delenv("VERA_STUDIO_WORK_DATA", raising=False)
    monkeypatch.delenv("PLUGIN_DATA", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.setenv("CODEX_SANDBOX", "1")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    path = module.storage_root()
    assert path.name == "studio-work"
    assert "mparanza-managed-python" not in str(path)
    if sys.platform == "win32":
        assert path == tmp_path / "LocalAppData/Mparanza/Vera/studio-work"
    else:
        assert path == Path.home() / ".local/share/mparanza/vera/studio-work"


@pytest.fixture
def service(tmp_path):
    value = load_service().StudioWork(tmp_path / "private")
    value.dispatch(
        "configure",
        {
            "request_key": "setup",
            "expected_revision": 0,
            "preferences": {
                "timezone": "Europe/Rome",
                "calendar_id": "fictional-calendar",
            },
        },
    )
    yield value
    value.close()


def capture(service, key="capture", **changes):
    """Create one fictional sourced commitment."""
    return service.dispatch(
        "capture",
        {
            "request_key": key,
            "item": {
                "title": "Paola",
                "kind": "appointment",
                "source": "Fictional spoken user request",
                **changes,
            },
        },
    )["item"]


def event(**changes):
    """Return exact fictional timed event fields."""
    return {
        "title": "Paola",
        "start_time": "2026-10-09T10:00:00+02:00",
        "end_time": "2026-10-09T11:00:00+02:00",
        "timezone_str": "Europe/Rome",
        **changes,
    }


def prepare(service, item, action="create", key="prepare", **changes):
    """Prepare, without executing, an authorized fictional operation."""
    return service.dispatch(
        "prepare",
        {
            "request_key": key,
            "item_id": item["id"],
            "expected_revision": item["revision"],
            "action": action,
            "event": {} if action == "delete" else event(**changes),
            "authorization": "Fictional user: schedule Paola Friday at 10",
        },
    )["operation"]


def claim(service, operation, key="claim"):
    return service.dispatch(
        "claim", {"request_key": key, "operation_id": operation["id"]}
    )


def resolve(service, operation, key="resolve", **changes):
    """Supply a fictional read-back, explicitly not independent verification."""
    evidence = {
        "tool": "fictional_google_calendar_read_event",
        "reference": "fixture-response-1",
        "calendar_id": operation["calendar_id"],
        "event_id": operation.get("event_id") or "event-1",
        "event": operation["desired"],
        **changes,
    }
    return service.dispatch(
        "resolve",
        {
            "request_key": key,
            "operation_id": operation["id"],
            "outcome": "verified",
            "evidence": evidence,
        },
    )


def linked_item(service):
    item = capture(service)
    operation = prepare(service, item)
    claim(service, operation)
    return resolve(service, operation)["item"]


def test_capture_reopens_in_new_session_with_same_identity_and_source(service):
    item = capture(service, due_date="2026-10-06", follow_up_date="2026-10-07")
    reopened = load_service().StudioWork(service.path.parent)
    try:
        context = reopened.dispatch("context", {"day": "2026-10-07"})
        assert context["items"][0]["id"] == item["id"]
        assert context["items"][0]["overdue"] is True
        assert context["items"][0]["follow_up_due"] is True
        assert context["scheduler_installed"] is False
    finally:
        reopened.close()


def test_report_workspace_is_durable_and_retry_safe(service):
    args = {"request_key": "report", "label": "Daily planning"}
    first = service.dispatch("report_workspace", args)
    repeated = service.dispatch("report_workspace", args)
    assert first == repeated
    assert Path(first["output_dir"]).is_dir()
    assert Path(first["output_dir"]).parent == service.path.parent / "reports"
    assert first["report_created"] is False


def test_same_capture_request_replays_without_duplicate(service):
    first = capture(service)
    repeated = capture(service)
    assert first == repeated
    assert service.dispatch("context", {"day": "2026-10-07"})["total"] == 1


def test_changed_retry_content_is_rejected(service):
    capture(service)
    with pytest.raises(ValueError, match="different content"):
        capture(service, title="Different Paola")


def test_stale_revision_does_not_overwrite_another_session(service):
    item = capture(service)
    service.dispatch(
        "change",
        {
            "request_key": "change1",
            "item_id": item["id"],
            "expected_revision": 1,
            "patch": {"status": "waiting"},
        },
    )
    with pytest.raises(ValueError, match="changed"):
        service.dispatch(
            "change",
            {
                "request_key": "change2",
                "item_id": item["id"],
                "expected_revision": 1,
                "patch": {"status": "done"},
            },
        )
    assert service.record(item["id"])["status"] == "waiting"


def test_dispatch_receipt_cannot_authorize_duplicate_external_write(service):
    operation = prepare(service, capture(service))
    first = claim(service, operation)
    replay = claim(service, operation)
    another = claim(service, operation, "claim-again")
    assert first["execute"] is True
    assert (
        "Vera operation: " + operation["id"]
        in first["connector_arguments"]["description"]
    )
    assert replay["execute"] is False
    assert another["execute"] is False


def test_uncertain_create_blocks_local_edits_and_second_operation(service):
    item = capture(service)
    operation = prepare(service, item)
    claim(service, operation)
    service.dispatch(
        "resolve",
        {
            "request_key": "uncertain",
            "operation_id": operation["id"],
            "outcome": "uncertain",
            "evidence": {"tool": "fixture", "reference": "timeout"},
        },
    )
    with pytest.raises(ValueError, match="Resolve"):
        prepare(service, item, key="new-write")
    assert claim(service, operation, "again")["execute"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"calendar_id": "wrong"},
        {"event": event()},
        {"event": event(start_time="2026-10-09T12:00:00+02:00")},
    ],
)
def test_wrong_read_back_cannot_mark_write_verified(service, changes):
    operation = prepare(service, capture(service))
    claim(service, operation)
    with pytest.raises(ValueError):
        resolve(service, operation, **changes)
    assert service.operation(operation["id"])["state"] == "in_flight"


def test_create_update_delete_round_trip_retains_identity_and_history(service):
    item = linked_item(service)
    update = prepare(
        service,
        item,
        "update",
        "reschedule",
        start_time="2026-10-09T12:00:00+02:00",
        end_time="2026-10-09T13:00:00+02:00",
    )
    claim(service, update, "dispatch-update")
    updated = resolve(service, update, "verify-update")["item"]
    assert updated["calendar"] == item["calendar"]
    assert updated["start_time"] == "2026-10-09T12:00:00+02:00"
    deletion = prepare(service, updated, "delete", "delete")
    claim(service, deletion, "dispatch-delete")
    cancelled = resolve(service, deletion, "verify-delete", absent=True)["item"]
    assert cancelled["status"] == "cancelled"
    assert "calendar" not in cancelled
    assert service.db.execute("SELECT COUNT(*) FROM history").fetchone()[0] >= 10


def test_completion_preserves_historical_event(service):
    item = linked_item(service)
    result = service.dispatch(
        "change",
        {
            "request_key": "complete",
            "item_id": item["id"],
            "expected_revision": item["revision"],
            "patch": {"status": "done"},
        },
    )
    assert result["item"]["status"] == "done"
    assert result["item"]["calendar"] == item["calendar"]


def test_abandon_only_undispatched_proposal(service):
    operation = prepare(service, capture(service))
    result = service.dispatch(
        "abandon",
        {
            "request_key": "abandon",
            "operation_id": operation["id"],
            "authorization": "User cancels proposal",
        },
    )
    assert result["operation"]["state"] == "abandoned"
    assert claim(service, operation)["execute"] is False


def test_definitive_failure_permits_a_new_operation(service):
    item = capture(service)
    operation = prepare(service, item)
    claim(service, operation)
    result = service.dispatch(
        "resolve",
        {
            "request_key": "failure",
            "operation_id": operation["id"],
            "outcome": "failed",
            "evidence": {
                "tool": "fixture",
                "reference": "explicit-rejection-before-write",
                "definitive_no_write": True,
            },
        },
    )
    assert result["operation"]["state"] == "failed"
    assert prepare(service, item, key="new-proposal")["state"] == "prepared"


def test_reminders_and_all_day_exclusive_end_are_verified(service):
    item = capture(service, kind="deadline", due_date="2026-10-09")
    operation = service.dispatch(
        "prepare",
        {
            "request_key": "deadline",
            "item_id": item["id"],
            "expected_revision": 1,
            "action": "create",
            "authorization": "User requests a deadline reminder",
            "event": {
                "title": "Deadline",
                "start_date": "2026-10-09",
                "end_date": "2026-10-10",
                "reminders": {
                    "use_default": False,
                    "overrides": [{"method": "popup", "minutes": 10080}],
                },
            },
        },
    )["operation"]
    claim(service, operation)
    result = resolve(service, operation)
    assert result["item"]["due_date"] == "2026-10-09"
    assert result["operation"]["state"] == "verified"


def test_meeting_and_actions_roll_back_together_on_invalid_action(service):
    with pytest.raises(ValueError):
        service.dispatch(
            "meeting",
            {
                "request_key": "meeting",
                "meeting": {
                    "title": "Meeting",
                    "date": "2026-10-07",
                    "source": "Fictional notes",
                },
                "actions": [
                    {"title": "Call", "kind": "task", "source": "Notes"},
                    {"title": "Bad", "kind": "invented", "source": "Notes"},
                ],
            },
        )
    assert service.dispatch("context", {"day": "2026-10-07"})["total"] == 0
    assert service.db.execute("SELECT COUNT(*) FROM meetings").fetchone()[0] == 0


def test_meeting_follow_ups_are_persistent_and_retry_safe(service):
    args = {
        "request_key": "meeting",
        "meeting": {
            "title": "Client meeting",
            "date": "2026-10-07",
            "source": "Fictional transcript",
            "decisions": ["Request missing documents"],
        },
        "actions": [
            {
                "title": "Request documents",
                "kind": "follow_up",
                "source": "Fictional transcript",
                "owner": "Monica",
                "follow_up_date": "2026-10-08",
            }
        ],
    }
    saved = service.dispatch("meeting", args)
    repeated = service.dispatch("meeting", args)
    assert saved == repeated
    assert saved["meeting"]["action_ids"] == [saved["items"][0]["id"]]


def test_dependency_cycle_is_rejected(service):
    first = capture(service, "first", kind="task")
    second = capture(service, "second", kind="task", depends_on=[first["id"]])
    with pytest.raises(ValueError, match="cycle"):
        service.dispatch(
            "change",
            {
                "request_key": "cycle",
                "item_id": first["id"],
                "expected_revision": 1,
                "patch": {"depends_on": [second["id"]]},
            },
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"start_time": "2026-10-09T10:00:00"},
        {"attendees": ["person@example.invalid"]},
        {"recurrence": ["RRULE:FREQ=DAILY"]},
    ],
)
def test_unsafe_or_unsupported_event_payload_is_rejected(service, changes):
    item = capture(service)
    with pytest.raises((ValueError, KeyError)):
        prepare(service, item, **changes)


def test_mcp_stdio_capture_and_read_uses_owner_local_state(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the MCP stdio integration")
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "vera_studio_work_capture",
                "arguments": {
                    "request_key": "spoken",
                    "item": {
                        "title": "Call Paola",
                        "kind": "task",
                        "source": "Fictional host voice transcript",
                    },
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "vera_studio_work_context",
                "arguments": {"day": "2026-10-07"},
            },
        },
    ]
    result = subprocess.run(
        [node, str(PLUGIN / "mcp/studio-work.cjs")],
        input="\n".join(json.dumps(x) for x in requests) + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={
            **os.environ,
            "VERA_STUDIO_WORK_PYTHON": sys.executable,
            "PLUGIN_DATA": str(tmp_path),
        },
        timeout=30,
    )
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[1]["result"]["structuredContent"]["item"]["title"] == "Call Paola"
    assert responses[2]["result"]["structuredContent"]["total"] == 1
    assert (tmp_path / "studio-work/studio-work.sqlite3").is_file()
