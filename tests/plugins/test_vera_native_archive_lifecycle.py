"""Real maintained ledger lifecycle through the shared app-only native service."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_navigation import (  # noqa: F401
    registry_workspace,
)
from tests.plugins.test_vera_native_workspace import NODE, ROOT, SERVER


def rpc_program(env: dict[str, str], body: str, *, server: Path = SERVER) -> dict:
    """Retain one MCP process so exact signed scopes survive sequential calls."""
    program = f"""const service = require({json.dumps(str(server))});
const call = (name, args) => service.handle({{jsonrpc:'2.0', id:1, method:'tools/call', params:{{name, arguments:args}}}}).result;
const payload = result => {{ if (result.isError) throw new Error(result.content[0].text); return result._meta.workspace; }};
const scope = state => ({{client_id:state.client_id, ...(state.engagement_id ? {{engagement_id:state.engagement_id}} : {{}}), ...(state.run_id ? {{run_id:state.run_id}} : {{}}), scope_revision:state.scope_revision, archive_ticket:state.archive_ticket, confirmed:true}});
{body}
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        [NODE, "-e", program],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        # Instrumentation measures many fresh Python children in one RPC case.
        # Keep the ordinary test deadline and all production deadlines unchanged.
        timeout=300 if "COVERAGE_PROCESS_CONFIG" in env else 90,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def selected_scope(client_id: str, engagement_id: str | None = None) -> str:
    return json.dumps(
        {
            "client_id": client_id,
            **({"engagement_id": engagement_id} if engagement_id else {}),
        }
    )


def preparation_setup(client_id: str, engagement_id: str) -> str:
    """Build an exact imported-source request from the actual private app payload."""
    return f"""
const selected = {selected_scope(client_id, engagement_id)};
const inputs = payload(call('vera_workspace_archive_inputs', selected));
const args = {{...scope(inputs), workflow_id:'journal-bank-reconciliation', input_ids:[inputs.rows[0].input_id], label:'Lavoro di prova', purpose:'Verifica delle fonti sintetiche', idempotency_key:'fictional-native-prepare'}};
"""


def test_native_create_engagement_identical_retry_keeps_one_durable_engagement(
    registry_workspace,
):
    env, _, binding, _, _, _ = registry_workspace
    ledger = _load_customer_ledger()
    folder = Path(binding["client_root"])
    before = ledger.list_engagements(folder, binding["client_id"])
    body = f"""
const page = payload(call('vera_workspace_open', {selected_scope(binding['client_id'])}));
const args = {{...scope(page), label:'Incarico sintetico dal pannello', idempotency_key:'fictional-native-create'}};
const first = payload(call('vera_workspace_archive_create_engagement', args));
const retry = payload(call('vera_workspace_archive_create_engagement', args));
const changed = call('vera_workspace_archive_create_engagement', {{...args, label:'Un altro incarico'}});
const result = {{first, retry, changed}};
"""

    result = rpc_program(env, body)

    stored = ledger.list_engagements(folder, binding["client_id"])
    assert len(stored) == len(before) + 1
    assert result["first"]["status"] == "created"
    assert result["retry"]["status"] == "already_created"
    assert result["retry"]["engagement_id"] == result["first"]["engagement_id"]
    assert result["changed"]["isError"] is True
    assert "different engagement request" in result["changed"]["content"][0]["text"]
    assert str(folder) not in json.dumps(result)


def test_native_prepare_exact_sources_retry_and_start_preserve_public_ledger_contract(
    registry_workspace,
):
    env, root, _, _, client_id, engagement_id = registry_workspace
    body = (
        preparation_setup(client_id, engagement_id)
        + """
const first = payload(call('vera_workspace_archive_prepare', args));
const retry = payload(call('vera_workspace_archive_prepare', args));
const page = payload(call('vera_workspace_open', selected));
const row = page.works.find(item => item.run_id === first.run_id);
const started = payload(call('vera_workspace_archive_start', scope(row)));
const after = payload(call('vera_workspace_open', selected));
const result = {first, retry, row, started, after, publicSummary:call('vera_workspace_archive_inputs', selected).content};
"""
    )

    result = rpc_program(env, body)

    ledger = _load_customer_ledger()
    loaded = ledger.load_run(
        root / "Cliente Beta", engagement_id, result["first"]["run_id"]
    )
    assert result["first"]["status"] == "prepared"
    assert result["retry"]["status"] == "already_prepared"
    assert result["first"]["run_id"] == result["retry"]["run_id"]
    assert result["row"]["can_start"] is True
    assert result["row"]["review_available"] is False
    assert result["started"]["status"] == "running"
    assert result["started"]["workflow_executed"] is False
    assert loaded["run"]["status"] == "running"
    assert len(loaded["input_manifest"]["inputs"]) == 1
    assert list(Path(loaded["output_dir"]).iterdir()) == []
    assert "received.txt" not in json.dumps(result["publicSummary"])
    assert str(root) not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    [
        "archive_ticket:'forged.signature'",
        "scope_revision:'f'.repeat(64)",
        "client_id:'client_111111111111111111111111'",
        "engagement_id:'eng_111111111111111111111111'",
        "confirmed:false",
        "source_path:'/private/another-client.csv'",
        "workflow_id:'apertura-pratica'",
        "input_ids:[]",
        "input_ids:['/private/another-client.csv']",
        "input_ids:[inputs.rows[0].input_id, inputs.rows[0].input_id]",
        "input_ids:['input_111111111111111111111111']",
    ],
)
def test_native_preparation_invalid_authority_or_input_refuses_without_run_creation(
    registry_workspace,
    change,
):
    env, root, _, _, client_id, engagement_id = registry_workspace
    ledger = _load_customer_ledger()
    folder = root / "Cliente Beta"
    before = ledger.list_runs(folder, engagement_id)
    body = (
        preparation_setup(client_id, engagement_id)
        + f"""
const result = call('vera_workspace_archive_prepare', {{...args, {change}}});
"""
    )

    result = rpc_program(env, body)

    assert result["isError"] is True
    assert ledger.list_runs(folder, engagement_id) == before


@pytest.mark.parametrize("role", ["VIEWER", ""])
def test_native_viewer_reads_exact_input_labels_but_cannot_prepare_or_create(
    registry_workspace,
    role,
):
    env, root, _, _, client_id, engagement_id = registry_workspace
    body = (
        preparation_setup(client_id, engagement_id)
        + f"""
const directory = payload(call('vera_workspace_open', {selected_scope(client_id)}));
const prepare = call('vera_workspace_archive_prepare', args);
const create = call('vera_workspace_archive_create_engagement', {{...scope(directory), label:'Vietato', idempotency_key:'fictional-viewer'}});
const result = {{inputs, directory, prepare, create}};
"""
    )

    result = rpc_program({**env, "VERA_WORKSPACE_ROLES": role}, body)

    assert result["inputs"]["can_prepare"] is False
    assert result["directory"]["can_create_engagement"] is False
    assert result["prepare"]["isError"] is True
    assert result["create"]["isError"] is True
    assert not (root / "Cliente Beta/Vera/.native-workspace").exists()


def test_native_preparation_cross_client_engagement_refuses_before_receipt_read(
    registry_workspace,
):
    env, _, binding, _, _, other_engagement = registry_workspace
    body = f"""
const result = call('vera_workspace_archive_inputs', {selected_scope(binding['client_id'], other_engagement)});
"""

    result = rpc_program(env, body)

    assert result["isError"] is True
    assert "received.txt" not in json.dumps(result)


def test_native_start_old_run_ticket_refuses_second_lifecycle_transition(
    registry_workspace,
):
    env, _, _, _, client_id, engagement_id = registry_workspace
    body = (
        preparation_setup(client_id, engagement_id)
        + """
const prepared = payload(call('vera_workspace_archive_prepare', args));
const row = payload(call('vera_workspace_open', selected)).works.find(item => item.run_id === prepared.run_id);
const first = payload(call('vera_workspace_archive_start', scope(row)));
const retry = call('vera_workspace_archive_start', scope(row));
const result = {first, retry};
"""
    )

    result = rpc_program(env, body)

    assert result["first"]["status"] == "running"
    assert result["retry"]["isError"] is True
    assert "Run state changed" in result["retry"]["content"][0]["text"]


def test_native_inputs_paginate_exact_receipts_and_workflow_inventory(
    registry_workspace,
):
    env, root, _, _, client_id, engagement_id = registry_workspace
    ledger = _load_customer_ledger()
    folder = root / "Cliente Beta"
    imported_count = 31
    for index in range(imported_count):
        source = root.parent / f"synthetic-{index:02}.txt"
        source.write_text(f"Separate synthetic document {index}.")
        ledger.import_document(folder, client_id, engagement_id, source, "support")
    expected = ledger.list_inputs(folder, engagement_id)
    body = f"""
const selected = {selected_scope(client_id, engagement_id)};
const first = payload(call('vera_workspace_archive_inputs', selected));
const next = payload(call('vera_workspace_archive_inputs', {{...selected, offset:30}}));
const result = {{first, next}};
"""

    result = rpc_program(env, body)

    assert len(result["first"]["rows"]) == 30
    assert len(result["next"]["rows"]) == 2
    assert result["first"]["has_more"] is True
    assert result["next"]["has_more"] is False
    assert result["first"]["scope_revision"] == result["next"]["scope_revision"]
    assert [
        row["input_id"] for row in result["first"]["rows"] + result["next"]["rows"]
    ] == [row["input_id"] for row in expected]
    maintained = navigation_module().archive_module(ROOT / "plugins/studio-archive")
    assert result["first"]["workflow_choices"] == list(
        maintained.VERA_CLIENT_WORKFLOW_IDS
    )
    assert "apertura-pratica" not in result["first"]["workflow_choices"]
    assert "trasformazione" not in result["first"]["workflow_choices"]
    assert "sha256" not in json.dumps(result)


def navigation_module():
    spec = importlib.util.spec_from_file_location(
        "tested_native_archive_lifecycle",
        ROOT / "plugins/vera/scripts/native_archive_navigation.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def direct_environment(env: dict[str, str], monkeypatch):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("VERA_WORKSPACE_BINDINGS", raising=False)
    monkeypatch.setenv("VERA_WORKSPACE_ACTOR_ID", "fictional-local-actor")
    monkeypatch.setenv("VERA_WORKSPACE_TENANT_ID", "fictional-local-tenant")
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "REVIEWER")


def test_native_create_interrupted_outcome_retains_intent_and_refuses_duplicate(
    registry_workspace,
    monkeypatch,
):
    env, _, binding, _, _, _ = registry_workspace
    direct_environment(env, monkeypatch)
    navigation = navigation_module()
    module_root = ROOT / "plugins/studio-archive"
    core = navigation.archive_module(module_root)
    directory = navigation.catalogue(module_root, {"client_id": binding["client_id"]})
    args = {
        "client_id": binding["client_id"],
        "scope_revision": directory["scope_revision"],
        "label": "Incarico interrotto sintetico",
        "idempotency_key": "fictional-interrupted-create",
        "confirmed": True,
    }
    folder = Path(binding["client_root"])
    before = len(core.ledger.list_engagements(folder, binding["client_id"]))
    create = core.create_studio_client_engagement

    def interrupted(*arguments, **keywords):
        create(*arguments, **keywords)
        raise OSError("Simulated process failure after the maintained creation")

    monkeypatch.setattr(core, "create_studio_client_engagement", interrupted)

    with pytest.raises(OSError, match="Simulated process failure"):
        navigation.lifecycle_action(
            module_root, "vera_workspace_archive_create_engagement", args
        )
    with pytest.raises(ValueError, match="outcome is uncertain"):
        navigation.lifecycle_action(
            module_root, "vera_workspace_archive_create_engagement", args
        )

    assert len(core.ledger.list_engagements(folder, binding["client_id"])) == before + 1
    receipt = next((folder / "Vera/.native-workspace").glob("engagement-*.json"))
    assert "engagement" not in json.loads(receipt.read_bytes())
    assert receipt.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("change", ["new_input", "closed_engagement", "changed_source"])
def test_native_preparation_changed_displayed_scope_refuses_without_new_run(
    registry_workspace,
    monkeypatch,
    change,
):
    env, root, _, _, client_id, engagement_id = registry_workspace
    direct_environment(env, monkeypatch)
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    navigation = navigation_module()
    module_root = ROOT / "plugins/studio-archive"
    core = navigation.archive_module(module_root)
    folder = root / "Cliente Beta"
    displayed = navigation.lifecycle_action(
        module_root,
        "vera_workspace_archive_inputs",
        {"client_id": client_id, "engagement_id": engagement_id},
    )
    args = {
        "client_id": client_id,
        "engagement_id": engagement_id,
        "scope_revision": displayed["scope_revision"],
        "workflow_id": "journal-bank-reconciliation",
        "input_ids": [displayed["rows"][0]["input_id"]],
        "label": "Lavoro sintetico",
        "purpose": "Prova di rifiuto",
        "idempotency_key": "fictional-changed-scope",
        "confirmed": True,
    }
    before = core.ledger.list_runs(folder, engagement_id, verify_inputs=False)
    if change == "new_input":
        source = root.parent / "new-received.txt"
        source.write_text("New synthetic receipt after display")
        core.ledger.import_document(folder, client_id, engagement_id, source, "support")
    elif change == "closed_engagement":
        for loaded in before:
            core.ledger.cancel_run(folder, engagement_id, loaded["run"]["run_id"])
        core.ledger.close_engagement(folder, engagement_id)
    else:
        receipt = core.ledger.list_inputs(folder, engagement_id)[0]
        source = (
            folder
            / "Vera/engagements"
            / engagement_id
            / "inputs"
            / receipt["input_id"]
            / receipt["stored_name"]
        )
        source.write_bytes(source.read_bytes() + b"changed")

    with pytest.raises((ValueError, core.ledger.LedgerError)):
        navigation.lifecycle_action(module_root, "vera_workspace_archive_prepare", args)

    assert len(
        core.ledger.list_runs(folder, engagement_id, verify_inputs=False)
    ) == len(before)


def test_native_new_lifecycle_tools_are_app_only_and_writes_require_signed_scope():
    program = f"const service=require({json.dumps(str(SERVER))}); process.stdout.write(JSON.stringify(service.TOOLS.filter(tool=>tool.name.startsWith('vera_workspace_archive_'))));"

    completed = subprocess.run(
        [NODE, "-e", program], capture_output=True, text=True, check=True
    )

    tools = {tool["name"]: tool for tool in json.loads(completed.stdout)}
    assert tools["vera_workspace_archive_inputs"]["_meta"]["ui"]["visibility"] == [
        "app"
    ]
    assert tools["vera_workspace_archive_create_engagement"]["inputSchema"][
        "required"
    ] == [
        "client_id",
        "scope_revision",
        "archive_ticket",
        "confirmed",
        "label",
        "idempotency_key",
    ]
    assert (
        tools["vera_workspace_archive_prepare"]["annotations"]["readOnlyHint"] is False
    )
    assert tools["vera_workspace_archive_start"]["_meta"]["ui"]["visibility"] == ["app"]


MAINTAINED_WORKFLOWS = (
    navigation_module()
    .archive_module(ROOT / "plugins/studio-archive")
    .VERA_CLIENT_WORKFLOW_IDS
)


@pytest.mark.parametrize("workflow", MAINTAINED_WORKFLOWS)
def test_native_prepare_each_maintained_gate_choice_only_creates_exact_durable_run(
    registry_workspace,
    workflow,
):
    env, root, _, _, client_id, engagement_id = registry_workspace
    body = (
        preparation_setup(client_id, engagement_id)
        + f"""
const result = payload(call('vera_workspace_archive_prepare', {{...args, workflow_id:{json.dumps(workflow)}}}));
"""
    )

    result = rpc_program(env, body)

    ledger = _load_customer_ledger()
    loaded = ledger.load_run(root / "Cliente Beta", engagement_id, result["run_id"])
    item = loaded["input_manifest"]["inputs"][0]
    assert result["workflow_executed"] is False
    assert loaded["run"]["status"] == "prepared"
    assert loaded["run"]["workflow_id"] == workflow
    assert loaded["run"]["workflow_version"] != "unversioned"
    assert (
        Path(loaded["run_root"]) / item["execution_relative_path"]
    ).read_bytes() == (
        root / "Cliente Beta" / item["source_relative_path"]
    ).read_bytes()
    assert list(Path(loaded["output_dir"]).iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        "confirmed:false",
        "archive_ticket:'forged.signature'",
        "scope_revision:'f'.repeat(64)",
        "run_id:'run_111111111111111111111111'",
        "client_id:'client_111111111111111111111111'",
        "source_path:'/private/forbidden.csv'",
    ],
)
def test_native_start_invalid_signed_run_refuses_lifecycle_write(
    registry_workspace,
    change,
):
    env, root, _, _, client_id, engagement_id = registry_workspace
    body = (
        preparation_setup(client_id, engagement_id)
        + f"""
const prepared = payload(call('vera_workspace_archive_prepare', args));
const row = payload(call('vera_workspace_open', selected)).works.find(item => item.run_id === prepared.run_id);
const refused = call('vera_workspace_archive_start', {{...scope(row), {change}}});
const result = {{prepared, refused}};
"""
    )

    result = rpc_program(env, body)

    ledger = _load_customer_ledger()
    loaded = ledger.load_run(
        root / "Cliente Beta", engagement_id, result["prepared"]["run_id"]
    )
    assert result["refused"]["isError"] is True
    assert loaded["run"]["status"] == "prepared"
    assert len(loaded["run"]["status_history"]) == 1


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_fresh_extracted_package_lifecycle_uses_maintained_durable_customer_ledger(
    registry_workspace,
    tmp_path,
    surface,
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, root, _, _, client_id, _ = registry_workspace
    if surface == "codex":
        builder = load_builder("build_codex_plugin_zip")
        vera = next(
            package for package in builder.load_bundles() if package.name == "vera"
        )
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        builder = load_builder("build_claude_plugin_zip")
        _, packages = builder.load_configuration()
        vera = next(package for package in packages if package.plugin == "vera")
        entries = builder.claude_package_entries(vera)
        prefix = ""
    target = tmp_path / "extracted"
    for name, content in entries.items():
        if name.startswith(prefix):
            destination = target / name[len(prefix) :]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    body = f"""
const directory = payload(call('vera_workspace_open', {selected_scope(client_id)}));
const created = payload(call('vera_workspace_archive_create_engagement', {{...scope(directory), label:'Incarico fittizio dal pacchetto', idempotency_key:'fictional-package-create'}}));
const result = {{created}};
"""

    created = rpc_program(env, body, server=target / "mcp/workspace.cjs")["created"]
    # Use the maintained immutable import engine for the package's new engagement.
    ledger = _load_customer_ledger()
    folder = root / "Cliente Beta"
    source = tmp_path / "fictional-package-input.txt"
    source.write_text(
        "Fictional imported evidence; this test does not execute a specialist engine."
    )
    imported = ledger.import_document(
        folder, client_id, created["engagement_id"], source, "source"
    )
    body = (
        preparation_setup(client_id, created["engagement_id"])
        + """
const prepared = payload(call('vera_workspace_archive_prepare', args));
const row = payload(call('vera_workspace_open', selected)).works[0];
const started = payload(call('vera_workspace_archive_start', scope(row)));
const result = {prepared, started};
"""
    )

    result = rpc_program(env, body, server=target / "mcp/workspace.cjs")

    loaded = ledger.load_run(
        folder, created["engagement_id"], result["prepared"]["run_id"]
    )
    assert loaded["run"]["status"] == "running"
    assert loaded["run"]["workflow_version"] != "unversioned"
    assert (
        loaded["input_manifest"]["inputs"][0]["binding_id"]
        == imported["receipt"]["input_id"]
    )
    assert result["started"]["workflow_executed"] is False
    assert list(Path(loaded["output_dir"]).iterdir()) == []
    assert (target / "scripts/native_archive_navigation.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_archive_navigation.py"
    ).read_bytes()
