"""Exercise discovery and lazy execution across actual process boundaries."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from scripts.build_vera_mcp_catalog import add_vera_mcp_catalog

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


def _seal(root: Path) -> None:
    files = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file() and file.name != "execution-files.json"
    }
    (root / "execution-files.json").write_text(
        json.dumps({"schema_version": 1, "files": files})
    )


@pytest.fixture
def installation(tmp_path: Path) -> Path:
    root = tmp_path / "plugin"
    (root / "scripts").mkdir(parents=True)
    (root / ".codex-plugin").mkdir()
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"name": "vera", "version": "0.1.999"})
    )
    for name in (
        "on_demand_mcp.cjs",
        "mcp_service_client.cjs",
        "verify_mcp_package.cjs",
    ):
        shutil.copyfile(ROOT / "plugins/vera/scripts" / name, root / "scripts" / name)
    shutil.copyfile(
        ROOT / "tests/plugins/fixtures/on_demand_service.cjs", root / "service.cjs"
    )
    configs = {
        name: {
            "command": "node",
            "args": ["./service.cjs", name],
            "env": {
                "START_LOG": str(tmp_path / "starts"),
                "WRITE_LOG": str(tmp_path / "writes"),
            },
        }
        for name in ("alpha", "beta")
    }
    (root / "mcp-services.json").write_text(json.dumps({"mcpServers": configs}))
    entries = {
        file.relative_to(root).as_posix(): file.read_bytes()
        for file in root.rglob("*")
        if file.is_file()
    }
    add_vera_mcp_catalog(entries)
    (root / "mcp-catalog.json").write_bytes(entries["mcp-catalog.json"])
    (tmp_path / "starts").unlink()
    _seal(root)
    return root


class Session:
    def __init__(self, root: Path):
        self.process = subprocess.Popen(
            ["node", str(root / "scripts/on_demand_mcp.cjs")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.messages: queue.Queue = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.next_id = 0
        self.call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        self.send({"method": "notifications/initialized"})

    def _read(self):
        for line in self.process.stdout:
            self.messages.put(json.loads(line))

    def send(self, message):
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        self.process.stdin.flush()

    def receive(self, timeout=10):
        return self.messages.get(timeout=timeout)

    def call(self, method, params=None, timeout=10):
        self.next_id += 1
        self.send({"id": self.next_id, "method": method, "params": params or {}})
        return self.receive(timeout=timeout)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            raise
        assert self.process.returncode == 0, self.process.stderr.read()


@pytest.fixture
def session(installation):
    active = Session(installation)
    yield active
    active.close()


def test_catalogue_exposes_individual_tools_and_panels_without_starting_workers(
    session, installation
):
    tools = session.call("tools/list")["result"]["tools"]
    resources = session.call("resources/list")["result"]["resources"]
    prompts = session.call("prompts/list")["result"]["prompts"]

    assert [tool["name"] for tool in tools] == ["use_alpha", "use_beta"]
    assert tools[0]["_meta"]["ui"]["resourceUri"] == "ui://alpha"
    assert len(resources) == len(prompts) == 2
    assert not (installation.parent / "starts").exists()


def test_first_use_starts_only_owner_and_later_calls_retain_review_state(
    session, installation
):
    first = session.call(
        "tools/call",
        {"name": "use_alpha", "arguments": {"action": "save", "value": "review-token"}},
    )
    second = session.call("tools/call", {"name": "use_alpha", "arguments": {}})

    assert second["result"]["structuredContent"] == first["result"]["structuredContent"]
    assert second["result"]["structuredContent"]["value"] == "review-token"
    assert (installation.parent / "starts").read_text().count("alpha:") == 1
    assert "beta:" not in (installation.parent / "starts").read_text()


def test_simultaneous_first_calls_share_one_worker(session, installation):
    session.send({"id": "one", "method": "tools/call", "params": {"name": "use_beta"}})
    session.send({"id": "two", "method": "tools/call", "params": {"name": "use_beta"}})
    first, second = session.receive(), session.receive()

    assert {first["id"], second["id"]} == {"one", "two"}
    assert (
        first["result"]["structuredContent"]["pid"]
        == second["result"]["structuredContent"]["pid"]
    )
    assert len((installation.parent / "starts").read_text().splitlines()) == 1


@pytest.mark.parametrize(
    "method,params,key",
    [
        ("resources/read", {"uri": "ui://beta"}, "contents"),
        ("prompts/get", {"name": "prompt_beta"}, "messages"),
    ],
)
def test_panel_and_prompt_access_start_only_their_owner(
    session, installation, method, params, key
):
    response = session.call(method, params)

    assert response["result"][key]
    assert (installation.parent / "starts").read_text().startswith("beta:")


def test_unknown_tool_does_not_start_a_service(session, installation):
    reply = session.call("tools/call", {"name": "not_a_tool"})

    assert reply["error"]["code"] == -32602
    assert not (installation.parent / "starts").exists()


def test_worker_crash_does_not_replay_write_and_other_services_remain_usable(
    session, installation
):
    failed = session.call(
        "tools/call", {"name": "use_alpha", "arguments": {"action": "crash"}}
    )
    retry = session.call(
        "tools/call", {"name": "use_alpha", "arguments": {"action": "crash"}}
    )
    other = session.call("tools/call", {"name": "use_beta"})

    assert "error" in failed and "error" in retry
    assert "inspect any existing result" in failed["error"]["message"]
    assert (installation.parent / "writes").read_text() == "saved\n"
    assert other["result"]["structuredContent"]["name"] == "beta"


def test_original_worker_errors_are_forwarded(session):
    response = session.call(
        "tools/call", {"name": "use_alpha", "arguments": {"action": "error"}}
    )

    assert response["error"] == {"code": -32602, "message": "original worker error"}


@pytest.mark.parametrize("payload", ["null", "not-json"])
def test_malformed_worker_reply_does_not_crash_other_services(session, payload):
    failed = session.call(
        "tools/call",
        {"name": "use_alpha", "arguments": {"action": "malformed", "payload": payload}},
    )
    other = session.call("tools/call", {"name": "use_beta"})

    assert failed["error"]["code"] == -32000
    assert other["result"]["structuredContent"]["name"] == "beta"


def test_progress_notifications_preserve_the_host_token(session):
    session.send(
        {
            "id": "progress",
            "method": "tools/call",
            "params": {
                "name": "use_alpha",
                "_meta": {"progressToken": "host-progress"},
            },
        }
    )
    notification = session.receive()
    response = session.receive()

    assert notification["method"] == "notifications/progress"
    assert notification["params"]["progressToken"] == "host-progress"
    assert response["id"] == "progress"


def test_worker_requests_round_trip_without_id_collisions(session):
    session.send(
        {
            "id": "caller",
            "method": "tools/call",
            "params": {"name": "use_alpha", "arguments": {"action": "host-request"}},
        }
    )
    request = session.receive()
    session.send({"id": request["id"], "result": {"roots": []}})
    response = session.receive()

    assert request["method"] == "roots/list"
    assert request["id"] != 1
    assert response["id"] == "caller"
    assert response["result"]["structuredContent"] == {"roots": []}


def test_active_cancellation_uses_the_worker_request_id(session):
    session.call("tools/call", {"name": "use_alpha"})
    session.send(
        {
            "id": "wait",
            "method": "tools/call",
            "params": {"name": "use_alpha", "arguments": {"action": "wait"}},
        }
    )
    session.send({"method": "notifications/cancelled", "params": {"requestId": "wait"}})
    response = session.receive()

    assert response["id"] == "wait"
    assert response["error"]["code"] == -32800


def test_host_eof_closes_started_service_processes(installation):
    active = Session(installation)
    response = active.call("tools/call", {"name": "use_alpha"})
    pid = response["result"]["structuredContent"]["pid"]

    active.close()

    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_chat_sessions_do_not_share_worker_state(session, installation):
    session.call(
        "tools/call",
        {"name": "use_alpha", "arguments": {"action": "save", "value": "private"}},
    )
    other = Session(installation)
    try:
        response = other.call("tools/call", {"name": "use_alpha"})
        assert response["result"]["structuredContent"]["value"] is None
    finally:
        other.close()


def test_cancellation_during_startup_does_not_execute_tool(session, installation):
    session.send(
        {
            "id": "cancel",
            "method": "tools/call",
            "params": {"name": "use_alpha", "arguments": {"action": "crash"}},
        }
    )
    session.send(
        {"method": "notifications/cancelled", "params": {"requestId": "cancel"}}
    )
    response = session.receive()

    assert response["error"]["code"] == -32800
    assert not (installation.parent / "writes").exists()


def test_catalogue_tampering_is_rejected_before_discovery(installation):
    (installation / "mcp-catalog.json").write_text("{}")
    result = subprocess.run(
        ["node", str(installation / "scripts/on_demand_mcp.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "Installation content mismatch: mcp-catalog.json" in result.stderr
    assert not (installation.parent / "starts").exists()


def test_catalogue_build_rejects_a_missing_service_instead_of_advertising_it(
    installation,
):
    entries = {
        file.relative_to(installation).as_posix(): file.read_bytes()
        for file in installation.rglob("*")
        if file.is_file() and file.name != "service.cjs"
    }

    with pytest.raises(ValueError, match="Vera catalogue generation failed"):
        add_vera_mcp_catalog(entries)


def test_cold_service_initialization_can_exceed_ten_seconds(installation):
    config_path = installation / "mcp-services.json"
    config = json.loads(config_path.read_text())
    config["mcpServers"]["alpha"]["env"]["INITIALIZE_DELAY_MS"] = "11000"
    config_path.write_text(json.dumps(config))
    _seal(installation)
    active = Session(installation)
    try:
        response = active.call("tools/call", {"name": "use_alpha"}, timeout=20)
    finally:
        active.close()

    assert response["result"]["structuredContent"]["name"] == "alpha"
    assert (installation.parent / "starts").read_text().count("alpha:") == 1
