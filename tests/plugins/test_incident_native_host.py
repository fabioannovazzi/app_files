"""Exercise the native stdio bridge, persistent host proof and guest ownership."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest

from modules.operational_incidents.api import TOOLS, _dispatch
from modules.operational_incidents.contracts import Credentials, ReporterStatus
from modules.operational_incidents.store import IncidentStore
from tests.modules.operational_incidents.test_incidents import report

ROOT = Path(__file__).resolve().parents[2]


def installed(tmp_path: Path, endpoint: str | None = None) -> Path:
    root = tmp_path / "installed"
    (root / "scripts").mkdir(parents=True)
    for name in (
        "incident_host_mcp.cjs",
        "operational_incidents.py",
        "technical_runner.py",
    ):
        shutil.copyfile(ROOT / "plugins/vera/scripts" / name, root / "scripts" / name)
    if endpoint is not None:
        # Only this owned fixture changes transport. Production has no URL override.
        script = root / "scripts/operational_incidents.py"
        original = script.read_text()
        assignment = 'SERVER = "https://mparanza.com/api/operational-incidents"'
        assert original.count(assignment) == 1
        script.write_text(original.replace(assignment, f'SERVER = "{endpoint}"'))
    (root / ".codex-plugin").mkdir()
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"name": "vera", "version": "0.1.391"})
    )
    files = {
        item.relative_to(root).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in root.rglob("*")
        if item.is_file()
    }
    (root / "execution-files.json").write_text(
        json.dumps({"schema_version": 1, "files": files})
    )
    return root


def call(
    root: Path, device: Path, name: str, arguments: dict, *, cwd: Path | None = None
) -> dict:
    environment = {
        **os.environ,
        "MPARANZA_INCIDENT_DEVICE_DIR": str(device),
        "MPARANZA_INCIDENT_STATE_DIR": str(device.parent / "unused-task-state"),
        "MPARANZA_INCIDENT_HOST": "codex",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }
    result = subprocess.run(
        ["node", str(root / "scripts/incident_host_mcp.cjs")],
        input=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
        env=environment,
        cwd=cwd or root,
    )
    return json.loads(result.stdout)["result"]


def test_native_stdio_processes_keep_public_host_code_without_exposing_key(tmp_path):
    root = installed(tmp_path)
    device = tmp_path / "native-host"
    poison = tmp_path / "poison"
    poison.mkdir()
    marker = poison / "executed"
    (poison / "platform.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('untrusted import')"
    )

    first = call(root, device, "vera_incident_host_context", {}, cwd=poison)
    second = call(root, device, "vera_incident_host_context", {})

    assert (
        first["structuredContent"]["device_id"]
        == second["structuredContent"]["device_id"]
    )
    assert first["structuredContent"]["binding"] == "native-host"
    assert (
        first["structuredContent"]["broker_status"]["session_id"]
        != second["structuredContent"]["broker_status"]["session_id"]
    )
    saved = json.loads((device / "identity.json").read_text())
    assert saved["device_key"] not in json.dumps(first)
    assert not marker.exists()
    assert not (device.parent / "unused-task-state/state.json").exists()
    if os.name == "posix":
        assert (device / "identity.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("damage", ["helper", "index"])
def test_native_stdio_refuses_damaged_reporter_before_creating_host_key(
    tmp_path, damage
):
    root = installed(tmp_path)
    if damage == "helper":
        with (root / "scripts/operational_incidents.py").open("a") as handle:
            handle.write("\nraise RuntimeError('PRIVATE_SENTINEL')\n")
    else:
        (root / "execution-files.json").write_text("{}")
    device = tmp_path / "native-host"

    result = call(root, device, "vera_incident_host_context", {})

    assert result["isError"] is True
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    assert not device.exists()


def test_native_stdio_binds_fresh_guest_reporters_without_overstating_guest_version(
    tmp_path,
):
    store = IncidentStore(tmp_path / "service.sqlite3")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            value = _dispatch(store, self.path.rsplit("/", 1)[-1], payload)
            encoded = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root = installed(tmp_path, f"http://127.0.0.1:{server.server_port}")
        guests = [
            Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
            for _ in range(2)
        ]
        results = []
        for guest in guests:
            store.register(guest)
            store.report(guest, report())
            store.observe_reporter(
                guest,
                ReporterStatus(
                    session_id=uuid4(),
                    protocol=1,
                    product_version="0.1.381",
                    host="codex",
                    platform="linux",
                ),
            )
            results.append(
                call(
                    root,
                    tmp_path / "native-host",
                    "vera_incident_host_link",
                    {"credentials": guest.model_dump(mode="json")},
                )
            )

        one, two = [value["structuredContent"] for value in results]
        assert one["device_id"] == two["device_id"]
        assert one["app_installation_id"] == two["app_installation_id"]
        assert store.registry()["reporting_instances"] == 2
        assert store.registry()["linked_host_devices"] == 1
        app = store.app_installation(one["app_installation_id"])
        assert len(app["native_broker_sessions"]) == 2
        assert app["native_broker_sessions"][0]["product_version"] == "0.1.391"
        assert (
            store.installation(str(guests[0].installation_id))["reporter_sessions"][0][
                "product_version"
            ]
            == "0.1.381"
        )
        saved = json.loads((tmp_path / "native-host/identity.json").read_text())
        assert set(saved) == {"device_id", "device_key"}
        assert saved["device_key"] not in json.dumps(results)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_identity_read_failure_returns_source_facts_without_key(tmp_path):
    root = installed(tmp_path)
    device = tmp_path / "native-host"
    device.mkdir()
    secret = "PRIVATE_HOST_KEY_" + uuid4().hex
    (device / "identity.json").write_text(
        json.dumps({"device_id": "invalid", "device_key": secret})
    )

    result = call(root, device, "vera_incident_host_context", {})

    facts = result["structuredContent"]["technical_facts"]
    assert result["isError"] is True
    assert facts["capture_state"] == "pending"
    assert facts["events"][0]["error_type"] == "ValueError"
    assert "complete_stderr" not in json.dumps(result)
    assert secret not in json.dumps(result)


@pytest.mark.parametrize(
    "variant",
    [
        "deployed-contract",
        "legacy-contract",
        "missing-progress",
        "duplicate",
        "wrong-name",
        "invalid-schema",
        "invalid-list",
        "invalid-name",
    ],
)
def test_release_checker_requires_the_actual_remote_incident_tool_contract(variant):
    tools = json.loads(json.dumps(TOOLS))
    if variant == "legacy-contract":
        tools = [tool for tool in tools if tool["name"].startswith("vera_incident_")]
    elif variant == "missing-progress":
        tools.pop()
    elif variant == "duplicate":
        tools[-1] = tools[0]
    elif variant == "wrong-name":
        tools[-1]["name"] = "unrelated_tool"
    elif variant == "invalid-schema":
        tools[-1]["inputSchema"] = {"type": "array"}
    elif variant == "invalid-list":
        tools = None
    elif variant == "invalid-name":
        tools[-1]["name"] = 42
    checker = ROOT / "scripts/check_packaged_mcp.cjs"
    program = "const {validIncidentTools}=require(process.argv[1]); process.stdout.write(JSON.stringify(validIncidentTools(JSON.parse(process.argv[2]))));"

    result = subprocess.run(
        ["node", "-e", program, str(checker), json.dumps(tools)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) is (
        variant in {"deployed-contract", "legacy-contract"}
    )
