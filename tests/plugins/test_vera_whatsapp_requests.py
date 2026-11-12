"""Portable persistence/dispatch tests with synthetic evidence, not native UI acceptance."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/vera/scripts"
ACCOUNT = "+393331112222"
PHONE = "+41795550101"


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "whatsapp_requests", SCRIPTS / "whatsapp_requests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    store = module.WhatsAppRequests(tmp_path / "private")
    yield store
    store.close()


def setup(service):
    lock = service.call(
        "acquire", {"request_key": "lock", "account": ACCOUNT, "owner": "test-session"}
    )
    binding = service.call(
        "bind",
        {
            "request_key": "bind",
            "token": lock["token"],
            "account": ACCOUNT,
            "phone": PHONE,
            "observed_phone": PHONE,
            "client": "Synthetic client",
            "alias": "Nickname",
            "evidence": "Synthetic profile/contact-info",
            "confirmation": "Synthetic user instruction",
            "platform": "windows",
        },
    )
    request = service.call(
        "capture",
        {
            "request_key": "capture",
            "binding_id": binding["id"],
            "request": {
                "title": "F24 request",
                "owner": "Operator",
                "source": "Synthetic instruction",
                "follow_up_date": "2026-11-12",
                "items": [
                    {"id": "f24", "description": "F24 receipt", "status": "awaiting"}
                ],
            },
        },
    )
    return lock, request


def prepare(service, request, **extra):
    return service.call(
        "prepare",
        {
            "request_key": "prepare",
            "id": request["id"],
            "expected_revision": request["revision"],
            "body": "Synthetic test request",
            "authorization": "Synthetic explicit send instruction",
            **extra,
        },
    )


def claim(service, lock, operation, **extra):
    return service.call(
        "claim",
        {
            "request_key": "claim",
            "id": operation["id"],
            "token": lock["token"],
            "observed_phone": PHONE,
            "observed_account": ACCOUNT,
            **extra,
        },
    )


def test_claim_replay_and_restart_never_redispatch(service):
    lock, request = setup(service)
    operation = prepare(service, request)
    assert claim(service, lock, operation)["execute"] is True
    assert claim(service, lock, operation)["execute"] is False
    reopened = type(service)(service.root)
    try:
        assert (
            claim(reopened, lock, operation, request_key="different-key")["execute"]
            is False
        )
        assert reopened.call("read", {"id": operation["id"]})["status"] == "submitting"
    finally:
        reopened.close()
    with pytest.raises(ValueError, match="outcome"):
        service.call(
            "release",
            {"request_key": "release", "token": lock["token"], "evidence": "Ended"},
        )


def test_concurrent_store_cannot_take_over_ui(service):
    setup(service)
    other = type(service)(service.root)
    try:
        with pytest.raises(ValueError, match="another session"):
            other.call(
                "acquire", {"request_key": "other", "account": PHONE, "owner": "second"}
            )
    finally:
        other.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"observed_phone": "+41795550102"},
        {"observed_account": PHONE},
        {"token": "wrong"},
    ],
)
def test_wrong_recipient_account_or_lock_prevents_dispatch(service, changes):
    lock, request = setup(service)
    operation = prepare(service, request)
    with pytest.raises(ValueError):
        claim(service, lock, operation, **changes)
    assert service.get(operation["id"])["status"] == "prepared"


def test_uncertain_send_requires_matching_evidence_and_blocks_new_content(service):
    lock, request = setup(service)
    operation = prepare(service, request)
    claim(service, lock, operation)
    service.call(
        "resolve",
        {
            "request_key": "uncertain",
            "id": operation["id"],
            "outcome": "uncertain",
            "evidence": {"locator": "Synthetic timeout after click"},
        },
    )
    with pytest.raises(ValueError, match="existing message"):
        prepare(
            service, request, request_key="different-body", body="A different message"
        )
    with pytest.raises(ValueError, match="definitive"):
        service.call(
            "resolve",
            {
                "request_key": "failed",
                "id": operation["id"],
                "outcome": "failed",
                "evidence": {"locator": "No bubble visible"},
            },
        )
    evidence = {
        "locator": "Synthetic outgoing bubble at 10:00",
        "phone": PHONE,
        "body": operation["body"],
        "attachment_names": [],
        "delivery": "sent",
    }
    with pytest.raises(ValueError, match="differs"):
        service.call(
            "resolve",
            {
                "request_key": "wrong",
                "id": operation["id"],
                "outcome": "accepted",
                "evidence": {**evidence, "body": "wrong"},
            },
        )
    result = service.call(
        "resolve",
        {
            "request_key": "verified",
            "id": operation["id"],
            "outcome": "accepted",
            "evidence": evidence,
        },
    )
    assert result["status"] == "accepted" and result["delivery"] == "sent"
    assert prepare(service, request, request_key="new-key")["id"] == operation["id"]
    with pytest.raises(ValueError, match="new specific instruction"):
        prepare(
            service, request, request_key="no-new-authority", repeat_of=operation["id"]
        )
    repeated = prepare(
        service,
        request,
        request_key="deliberate-repeat",
        repeat_of=operation["id"],
        authorization="Synthetic user explicitly requests a second reminder",
    )
    assert repeated["id"] != operation["id"]
    assert service.call(
        "release",
        {"request_key": "release", "token": lock["token"], "evidence": "Session ended"},
    )["released"]
    with pytest.raises(ValueError, match="Acquire"):
        service.call(
            "acquire",
            {"request_key": "lock", "account": ACCOUNT, "owner": "test-session"},
        )


def test_selected_bytes_survive_archive_failure_and_source_change(service, tmp_path):
    lock, request = setup(service)
    source = tmp_path / "synthetic.txt"
    source.write_text("Synthetic document", encoding="utf-8")
    attachment = service.call(
        "stage",
        {
            "request_key": "file",
            "id": request["id"],
            "path": str(source),
            "source": "Synthetic message 12 November 10:00",
            "direction": "outgoing",
        },
    )
    source.write_text("changed original", encoding="utf-8")
    service.call(
        "archive",
        {
            "request_key": "archive-failed",
            "id": attachment["id"],
            "status": "failed",
            "evidence": "Synthetic Archive unavailable",
        },
    )
    context = service.call("context", {"account": ACCOUNT, "day": "2026-11-12"})
    assert context["requests"][0]["follow_up_due"] is True
    assert context["pending_archive"][0]["sha256"] == attachment["sha256"]
    assert Path(attachment["path"]).read_text() == "Synthetic document"
    with pytest.raises(ValueError, match="match"):
        service.call(
            "archive",
            {
                "request_key": "wrong-hash",
                "id": attachment["id"],
                "status": "archived",
                "sha256": "wrong",
                "evidence": "receipt",
            },
        )
    service.call(
        "archive",
        {
            "request_key": "archive-ok",
            "id": attachment["id"],
            "status": "archived",
            "sha256": attachment["sha256"],
            "evidence": "Synthetic receipt",
        },
    )
    operation = prepare(service, request, attachment_ids=[attachment["id"]])
    Path(attachment["path"]).write_text("tampered")
    with pytest.raises(ValueError, match="changed"):
        claim(service, lock, operation)


def test_received_is_not_complete_and_revisions_prevent_lost_updates(service):
    _, request = setup(service)
    item = {
        "id": "f24",
        "description": "F24 receipt",
        "status": "received",
        "evidence": "Synthetic attachment id",
    }
    args = {
        "request_key": "change",
        "id": request["id"],
        "expected_revision": 0,
        "patch": {"items": [item]},
    }
    changed = service.call("change", args)
    assert changed["revision"] == 1 and changed["status"] == "open"
    with pytest.raises(ValueError, match="revision"):
        service.call("change", {**args, "request_key": "stale"})
    with pytest.raises(ValueError, match="Open items"):
        service.call(
            "change",
            {
                **args,
                "request_key": "premature",
                "expected_revision": 1,
                "patch": {"status": "complete"},
            },
        )
    with pytest.raises(ValueError, match="evidence"):
        service.call(
            "change",
            {
                **args,
                "request_key": "missing",
                "expected_revision": 1,
                "patch": {"items": [{**item, "evidence": ""}]},
            },
        )
    completed = service.call(
        "change",
        {
            **args,
            "request_key": "complete",
            "expected_revision": 1,
            "patch": {"items": [{**item, "status": "complete"}], "status": "complete"},
        },
    )
    assert completed["status"] == "complete"
    assert (
        service.call("context", {"account": ACCOUNT, "day": "2026-11-12"})["total"] == 0
    )


def test_changed_retry_and_cancelled_retry(service):
    lock, request = setup(service)
    operation = prepare(service, request)
    with pytest.raises(ValueError, match="changed content"):
        prepare(service, request, body="changed")
    service.call(
        "resolve",
        {
            "request_key": "cancel",
            "id": operation["id"],
            "outcome": "cancelled",
            "evidence": {"locator": "Synthetic user cancels before dispatch"},
        },
    )
    retry = prepare(
        service,
        request,
        request_key="retry",
        retry_of=operation["id"],
        authorization="New synthetic explicit instruction",
    )
    assert retry["id"] != operation["id"]
    assert claim(service, lock, retry)["execute"]


def test_archive_metadata_change_cannot_create_a_duplicate_file_send(service, tmp_path):
    lock, request = setup(service)
    source = tmp_path / "synthetic.txt"
    source.write_text("Synthetic file")
    attachment = service.call(
        "stage",
        {
            "request_key": "stage",
            "id": request["id"],
            "path": str(source),
            "source": "Synthetic source",
            "direction": "outgoing",
        },
    )
    operation = prepare(service, request, attachment_ids=[attachment["id"]])
    claim(service, lock, operation)
    service.call(
        "resolve",
        {
            "request_key": "accept",
            "id": operation["id"],
            "outcome": "accepted",
            "evidence": {
                "phone": PHONE,
                "body": operation["body"],
                "attachment_names": ["synthetic.txt"],
                "locator": "Synthetic UI",
            },
        },
    )
    service.call(
        "archive",
        {
            "request_key": "archive",
            "id": attachment["id"],
            "status": "failed",
            "evidence": "Synthetic archive outage",
        },
    )
    assert (
        prepare(
            service, request, request_key="again", attachment_ids=[attachment["id"]]
        )["id"]
        == operation["id"]
    )


def test_mcp_service_exposes_local_tools_and_persists_across_processes(tmp_path):
    module = ROOT / "plugins/vera/mcp/studio-work.cjs"
    script = "const s=require(process.argv[1]); console.log(JSON.stringify(s.handle(JSON.parse(process.argv[2]))));"
    env = {
        **os.environ,
        "VERA_STUDIO_WORK_DATA": str(tmp_path),
        "VERA_STUDIO_WORK_PYTHON": sys.executable,
    }

    def run(request):
        return json.loads(
            subprocess.check_output(
                ["node", "-e", script, str(module), json.dumps(request)],
                env=env,
                text=True,
            )
        )

    listed = run({"method": "tools/list"})
    assert "vera_whatsapp_claim" in {t["name"] for t in listed["tools"]}
    result = run(
        {
            "method": "tools/call",
            "params": {
                "name": "vera_whatsapp_acquire",
                "arguments": {
                    "request_key": "one",
                    "account": ACCOUNT,
                    "owner": "Test",
                },
            },
        }
    )
    assert result["structuredContent"]["account"] == ACCOUNT
    context = run(
        {
            "method": "tools/call",
            "params": {
                "name": "vera_whatsapp_context",
                "arguments": {"account": ACCOUNT, "day": "2026-11-12"},
            },
        }
    )
    assert context["structuredContent"]["ui_busy"] is True
    invalid = run(
        {
            "method": "tools/call",
            "params": {
                "name": "vera_whatsapp_read",
                "arguments": {"id": "x", "extra": "x"},
            },
        }
    )
    assert invalid["isError"] is True


def test_current_native_adapter_regressions():
    result = subprocess.run(
        ["node", "--test", str(ROOT / "tests/plugins/whatsapp_local.test.mjs")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
