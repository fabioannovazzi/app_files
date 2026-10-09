from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "plugins/bilancio-xbrl-it/mcp/server.cjs"
NODE = shutil.which("node") or str(
    Path.home()
    / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
)


def pilot_builder():
    spec = importlib.util.spec_from_file_location(
        "workspace_pilot", ROOT / "scripts/build_vera_workspace_pilot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def demo_environment(tmp_path: Path) -> dict[str, str]:
    return pilot_builder().seed_demo(tmp_path / "demo")


def test_rebuild_reuses_fictional_case_without_recreating_it(tmp_path):
    builder = pilot_builder()
    original = tmp_path / "original"
    builder.build_pilot(original)
    environment = json.loads((original / "environment.json").read_bytes())
    case_path = (
        Path(environment["VERA_XBRL_STORAGE_ROOT"])
        / "demo_studio/aurora_2025/case.json"
    )
    original_bytes = case_path.read_bytes()
    refreshed = tmp_path / "refreshed"

    builder.build_pilot(refreshed, version="0.0.2", reuse_demo=original)

    assert json.loads((refreshed / "environment.json").read_bytes()) == environment
    assert case_path.read_bytes() == original_bytes
    assert not (refreshed / "fictional-archive").exists()


def test_rebuild_rejects_non_demo_identity_before_creating_output(tmp_path):
    builder = pilot_builder()
    original = tmp_path / "original"
    original.mkdir()
    (original / "environment.json").write_text(
        json.dumps({"VERA_XBRL_TENANT_ID": "real_studio"})
    )
    refreshed = tmp_path / "refreshed"

    with pytest.raises(ValueError, match="fictional archive"):
        builder.build_pilot(refreshed, reuse_demo=original)

    assert not refreshed.exists()


class McpClient:
    def __init__(self, environment):
        self.process = subprocess.Popen(
            [NODE, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, **environment},
        )
        self.request_id = 0

    def request(self, method, params):
        self.request_id += 1
        self.process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": self.request_id,
                    "method": method,
                    "params": params,
                }
            )
            + "\n"
        )
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())["result"]

    def call(self, name, **arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)


@pytest.fixture
def connected(tmp_path):
    environment = demo_environment(tmp_path)
    client = McpClient(environment)
    yield client, environment
    client.close()


def selected_finding(client, case_id="aurora_2025"):
    page = client.call("xbrl_workspace_view", case_id=case_id)["_meta"]["workspace"]
    issue = next(
        item
        for item in page["review"]["issues"]["items"]
        if item["rule_id"] == "INPUT.PRIOR_XBRL_RECOMMENDED"
    )
    return client.call(
        "xbrl_workspace_view",
        case_id=case_id,
        revision_id=page["revision_id"],
        issue_id=issue["issue_id"],
    )["_meta"]["workspace"]


def review_args(selected):
    return {
        "case_id": selected["case_id"],
        "revision_id": selected["revision_id"],
        "issue_id": selected["selection"]["issue"]["issue_id"],
        "action": "ACKNOWLEDGED",
        "reason": "Ho esaminato il rilievo: manca il precedente XBRL in questo caso fittizio.",
        "human_reviewed": True,
        "idempotency_key": "review_demo_1",
        "review_ticket": selected["review_ticket"],
    }


def test_review_loop_persists_once_and_reopens_authoritative_revision(connected):
    client, environment = connected
    selected = selected_finding(client)
    args = review_args(selected)

    saved = client.call("xbrl_workspace_review_issue", **args)
    replay = client.call("xbrl_workspace_review_issue", **args)
    fresh = client.call("xbrl_workspace_view", case_id="aurora_2025")["_meta"][
        "workspace"
    ]

    assert not saved.get("isError")
    assert args["reason"] not in json.dumps(saved["structuredContent"])
    assert replay == saved
    assert fresh["revision_id"] != selected["revision_id"]
    assert len(fresh["review"]["review_decisions"]) == 1
    assert fresh["review"]["review_decisions"][0]["reviewed_by"] == "demo_reviewer"
    stored = json.loads(
        (
            Path(environment["VERA_XBRL_STORAGE_ROOT"])
            / "demo_studio/aurora_2025/case.json"
        ).read_bytes()
    )
    assert stored["audit_events"][-1]["originating_interface"] == "mcp-app-workspace"


def test_explanation_contains_only_selected_finding_and_selected_cell(connected):
    client, _ = connected
    selected = selected_finding(client)

    result = client.call(
        "xbrl_workspace_explain",
        case_id="aurora_2025",
        revision_id=selected["revision_id"],
        issue_id=selected["selection"]["issue"]["issue_id"],
        source_ref="src_0000001",
    )

    context = result["structuredContent"]["context"]
    assert len(context["packet"]["reviewed_context"]["issues"]) == 1
    assert context["untrusted_evidence"]["anchors"][0]["raw_value"] == "1000"
    assert len(context["untrusted_evidence"]["anchors"]) == 1
    assert "Officina Aurora" not in json.dumps(context)
    assert "Debiti" not in json.dumps(context)
    assert "review_ticket" not in json.dumps(result)


@pytest.mark.parametrize("source_ref", [None, "src_0000007"])
def test_chat_request_contains_only_readable_request_and_exact_references(
    connected, source_ref
):
    client, _ = connected
    selected = selected_finding(client)
    if source_ref:
        selected = client.call(
            "xbrl_workspace_view",
            case_id=selected["case_id"],
            revision_id=selected["revision_id"],
            issue_id=selected["selection"]["issue"]["issue_id"],
            source_ref=source_ref,
        )["_meta"]["workspace"]
    module = ROOT / "plugins/bilancio-xbrl-it/ui/explanation-message.js"
    title = "Manca il bilancio XBRL dell'esercizio precedente"

    output = subprocess.run(
        [
            NODE,
            "-e",
            "const {buildExplanationMessage}=require(process.argv[1]);"
            "const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));"
            "process.stdout.write(JSON.stringify(buildExplanationMessage("
            "input.snapshot,input.title)));",
            str(module),
        ],
        input=json.dumps({"snapshot": selected, "title": title}),
        text=True,
        capture_output=True,
        check=True,
    )
    message = json.loads(output.stdout)

    assert message["_meta"]["openai/message"]["target"] == "new"
    assert len(message["content"]) == 1
    prompt = message["content"][0]["text"]
    assert prompt.startswith(f"Spiega il rilievo «{title}» del bilancio al 2025-12-31.")
    assert "Fascicolo: aurora_2025 · rilievo: iss_0001 · revisione: rev_4." in prompt
    source_sentence = {
        None: "Nessuna cella sorgente aggiunta alla selezione.",
        "src_0000007": "Fonte scelta: src_0000007.",
    }[source_ref]
    assert source_sentence in prompt
    assert "Prima di rispondere, recupera con Vera questo rilievo" in prompt
    assert "chiedimi di riaprire il rilievo" in prompt
    assert prompt.endswith("Non salvare decisioni.")
    assert len(prompt) < 700
    assert "{" not in prompt
    assert "90,00" not in prompt
    assert selected["selection"]["context_sha256"] not in output.stdout
    assert "schema_version" not in output.stdout
    assert "review_ticket" not in output.stdout
    assert "Officina Aurora" not in output.stdout


@pytest.mark.parametrize(
    "change",
    [
        {"case_id": "another_client"},
        {"revision_id": "rev_999"},
        {"issue_id": "unknown"},
        {"review_ticket": "forged"},
        {"human_reviewed": False},
    ],
)
def test_review_rejects_forged_or_cross_scope_submission(connected, change):
    client, _ = connected
    args = {**review_args(selected_finding(client)), **change}

    result = client.call("xbrl_workspace_review_issue", **args)

    assert result["isError"] is True
    current = client.call("xbrl_workspace_view", case_id="aurora_2025")["_meta"][
        "workspace"
    ]
    assert current["review"]["review_decisions"] == []


def test_changed_case_rejects_stale_explanation(connected):
    client, _ = connected
    selected = selected_finding(client)
    client.call("xbrl_workspace_review_issue", **review_args(selected))

    result = client.call(
        "xbrl_workspace_explain",
        case_id="aurora_2025",
        revision_id=selected["revision_id"],
        issue_id=selected["selection"]["issue"]["issue_id"],
    )

    assert result["isError"] is True
    assert "Stale revision" in result["content"][0]["text"]


def test_ui_catalogue_data_and_write_tools_are_not_model_visible(connected):
    client, _ = connected
    tools = client.request("tools/list", {})["tools"]

    result = client.call("xbrl_workspace_open")

    assert "Officina Aurora" in json.dumps(result["_meta"])
    assert "Officina Aurora" not in json.dumps(result["structuredContent"])
    writer = next(
        tool for tool in tools if tool["name"] == "xbrl_workspace_review_issue"
    )
    assert writer["_meta"]["ui"]["visibility"] == ["app"]
    assert writer["annotations"]["readOnlyHint"] is False


def test_resource_registers_native_entrypoints_and_offline_assets(connected):
    client, _ = connected
    tools = client.request("tools/list", {})["tools"]
    entry = next(tool for tool in tools if tool["name"] == "xbrl_workspace_open")

    result = client.request(
        "resources/read", {"uri": entry["_meta"]["ui"]["resourceUri"]}
    )

    assert entry["_meta"]["openai/ui"]["entrypoints"] == [
        {"type": "global"},
        {"type": "thread"},
    ]
    resource = result["contents"][0]
    assert resource["mimeType"] == "text/html;profile=mcp-app"
    assert resource["_meta"]["openai/ui"]["preferredDisplayMode"] == "fullscreen"
    assert "__FONT__" not in resource["text"]
    assert "ui/initialize" in resource["text"]
    assert "fetch(" not in resource["text"]


def test_normal_installation_does_not_advertise_the_private_ui(tmp_path):
    environment = demo_environment(tmp_path)
    client = McpClient(
        {**environment, "VERA_XBRL_UI_ONLY": "0", "VERA_XBRL_NATIVE_UI": "0"}
    )
    try:
        result = client.request("tools/list", {})

        assert "xbrl_workspace_open" not in {tool["name"] for tool in result["tools"]}
        assert client.request("resources/list", {})["resources"] == []
    finally:
        client.close()


def test_workspace_refuses_other_actor_configuration(connected):
    _, environment = connected
    client = McpClient({**environment, "VERA_XBRL_ACTOR_ID": "other_actor"})
    try:
        result = client.call("xbrl_workspace_open")
        assert result["isError"] is True
        assert "authenticated actor" in result["content"][0]["text"]
    finally:
        client.close()


def test_stale_decision_does_not_create_a_second_review(connected):
    client, _ = connected
    args = review_args(selected_finding(client))
    client.call("xbrl_workspace_review_issue", **args)

    result = client.call(
        "xbrl_workspace_review_issue",
        **{**args, "idempotency_key": "different_request"},
    )

    assert result["isError"] is True
    assert "Stale revision" in result["content"][0]["text"]


def test_read_only_actor_cannot_save_a_review(tmp_path):
    environment = demo_environment(tmp_path)
    client = McpClient({**environment, "VERA_XBRL_ROLES": "READ_ONLY_AUDITOR"})
    try:
        selected = selected_finding(client)

        result = client.call("xbrl_workspace_review_issue", **review_args(selected))

        assert result["isError"] is True
        assert "OVERRIDE is not granted" in result["content"][0]["text"]
    finally:
        client.close()


def test_missing_configuration_returns_a_renderable_setup_failure(tmp_path):
    client = McpClient(
        {
            "VERA_XBRL_STORAGE_ROOT": "",
            "VERA_XBRL_TENANT_ID": "",
            "VERA_XBRL_ACTOR_ID": "",
            "VERA_XBRL_ROLES": "",
            "VERA_XBRL_PYTHON": sys.executable,
            "VERA_XBRL_UI_ONLY": "1",
        }
    )
    try:
        result = client.call("xbrl_workspace_open")

        assert result["isError"] is True
        assert "environment is incomplete" in result["_meta"]["workspace"]["error"]
    finally:
        client.close()


def test_unknown_source_cannot_be_attached_to_an_explanation(connected):
    client, _ = connected
    selected = selected_finding(client)

    result = client.call(
        "xbrl_workspace_explain",
        case_id="aurora_2025",
        revision_id=selected["revision_id"],
        issue_id=selected["selection"]["issue"]["issue_id"],
        source_ref="another_client_source",
    )

    assert result["isError"] is True
    assert "Unknown source reference" in result["content"][0]["text"]


@pytest.fixture
def two_clients(tmp_path):
    builder = pilot_builder()
    environment = builder.seed_demo(tmp_path / "aurora")
    second = builder.seed_demo(
        tmp_path / "boreale",
        scenario="boreale",
        storage_root=Path(environment["VERA_XBRL_STORAGE_ROOT"]),
    )
    bindings_path = Path(environment["VERA_XBRL_WORKSPACE_BINDINGS"])
    bindings = json.loads(bindings_path.read_bytes())
    bindings["bindings"].extend(
        json.loads(Path(second["VERA_XBRL_WORKSPACE_BINDINGS"]).read_bytes())[
            "bindings"
        ]
    )
    bindings_path.write_text(json.dumps(bindings))
    client = McpClient(environment)
    yield client, environment
    client.close()


def test_explanation_switches_between_authorized_clients_without_prior_context(
    two_clients,
):
    client, _ = two_clients
    selected_finding(client)
    second = selected_finding(client, "boreale_2025")

    result = client.call(
        "xbrl_workspace_explain",
        case_id="boreale_2025",
        revision_id=second["revision_id"],
        issue_id=second["selection"]["issue"]["issue_id"],
        source_ref="src_0000002",
    )

    context = result["structuredContent"]["context"]
    assert context["case_id"] == "boreale_2025"
    assert context["untrusted_evidence"]["anchors"][0]["raw_value"] == "Banca Boreale"
    assert "aurora_2025" not in json.dumps(context)
    assert "Cassa" not in json.dumps(context)


def test_review_ticket_cannot_be_reused_for_another_authorized_client(two_clients):
    client, _ = two_clients
    first = selected_finding(client)
    second = selected_finding(client, "boreale_2025")
    args = {**review_args(second), "review_ticket": first["review_ticket"]}

    result = client.call("xbrl_workspace_review_issue", **args)

    assert result["isError"] is True
    assert "mismatched review ticket" in result["content"][0]["text"]
    assert selected_finding(client, "boreale_2025")["review"]["review_decisions"] == []


def test_new_connection_reopens_saved_decision_without_another_clients_context(
    two_clients,
):
    client, environment = two_clients
    first = selected_finding(client)
    client.call("xbrl_workspace_review_issue", **review_args(first))
    selected_finding(client, "boreale_2025")
    reopened = McpClient(environment)
    try:
        result = selected_finding(reopened)

        assert (
            result["review"]["review_decisions"][0]["reason"]
            == review_args(first)["reason"]
        )
        assert "boreale_2025" not in json.dumps(result)
        assert "Banca Boreale" not in json.dumps(result)
    finally:
        reopened.close()


def test_local_protocol_host_serves_current_ui_resource(tmp_path):
    builder = pilot_builder()
    directory = tmp_path / "pilot"
    builder.build_pilot(directory)
    process = subprocess.Popen(
        [NODE, str(ROOT / "scripts/serve_vera_workspace_pilot.cjs"), str(directory)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        url = process.stdout.readline().strip()
        with urlopen(url + "/ui", timeout=10) as response:
            html = response.read().decode("utf-8")
        assert "Fascicoli di bilancio" in html
        assert "Discuti in una nuova chat" in html
        assert "/*__JS__*/" not in html
    finally:
        process.terminate()
        process.communicate(timeout=10)
