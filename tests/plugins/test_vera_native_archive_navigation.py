"""Real registry/run source mechanisms; no installed native-host acceptance."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests._plugin_cli import workflow_cli
from tests.plugins.test_bilancio_native_workspace import demo_environment
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_workspace import (
    NODE,
    ROOT,
    SERVER,
    treasury_binding,
)

ARCHIVE = ROOT / "plugins/studio-archive/scripts/studio_archive.py"


def process_environment() -> dict[str, str]:
    """Keep runtime/OS paths without unrelated account credentials in fixtures."""
    return {
        key: os.environ[key]
        for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR")
        if key in os.environ
    }


def archive_cli(env: dict[str, str], *arguments: str) -> dict:
    completed = subprocess.run(
        [*workflow_cli(ARCHIVE), *arguments],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    return json.loads(completed.stdout)


def native_call(env: dict[str, str], tool: str, arguments: dict) -> dict:
    completed = subprocess.run(
        [NODE, str(SERVER)],
        input=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
        )
        + "\n",
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)["result"]
    if result.get("isError"):
        raise ValueError(result["content"][0]["text"])
    return result["_meta"]["workspace"]


@pytest.fixture
def registry_workspace(tmp_path):
    root = tmp_path / "Studio"
    root.mkdir()
    binding, output = treasury_binding(root)
    ledger = _load_customer_ledger()
    other = root / "Cliente Beta"
    other.mkdir()
    other_id = "client_222222222222222222222222"
    ledger.create_client_manifest(other, other_id)
    engagement = ledger.create_engagement(other, other_id, "Mandato Beta")
    source = tmp_path / "received.txt"
    source.write_text("Fictional source for a separate client.")
    receipt = ledger.import_document(
        other, other_id, engagement["engagement_id"], source, "source"
    )["receipt"]
    prepared = ledger.prepare_run(
        other,
        other_id,
        engagement["engagement_id"],
        "composizione-negoziata",
        "0.1.0",
        input_ids=[receipt["input_id"]],
    )
    ledger.start_run(other, engagement["engagement_id"], prepared["run"]["run_id"])
    env = process_environment()
    env.update(
        VERA_WORKSPACE_PYTHON=sys.executable,
        VERA_STUDIO_ARCHIVE_SESSION_ID="fictional-native-archive",
        VERA_STUDIO_ARCHIVE_STATE_DIR=str(tmp_path / "private-state"),
    )
    archive_cli(env, "configure", "--archive-root", str(root))
    return env, root, binding, output, other_id, engagement["engagement_id"]


def selected_run(env: dict[str, str], binding: dict) -> dict:
    return native_call(
        env,
        "vera_workspace_open",
        {"client_id": binding["client_id"], "engagement_id": binding["engagement_id"]},
    )["works"][0]


def test_native_unconfigured_registry_offers_setup_without_json(tmp_path):
    env = process_environment()
    env.update(
        VERA_WORKSPACE_PYTHON=sys.executable,
        VERA_STUDIO_ARCHIVE_SESSION_ID="fictional-unconfigured",
        VERA_STUDIO_ARCHIVE_STATE_DIR=str(tmp_path / "state"),
    )

    result = native_call(env, "vera_workspace_open", {})

    assert result["configured"] is False
    assert result["setup_required"] is True
    assert result["clients"] == []
    assert result["works"] == []
    assert not (tmp_path / "state/config.json").exists()


def test_native_registry_reads_clients_engagements_runs_without_private_contacts(
    registry_workspace,
):
    env, root, binding, _, other_id, _ = registry_workspace

    clients = native_call(env, "vera_workspace_open", {})
    engagements = native_call(
        env, "vera_workspace_open", {"client_id": binding["client_id"]}
    )
    run = selected_run(env, binding)

    assert {row["client_id"] for row in clients["clients"] if row["client_id"]} == {
        binding["client_id"],
        other_id,
    }
    assert engagements["engagements"][0]["engagement_id"] == binding["engagement_id"]
    assert run["run_id"] == binding["run_id"]
    assert run["review_available"] is True
    assert run["inputs_valid"] is True
    assert str(root) not in json.dumps([clients, engagements, run])
    assert "email_addresses" not in json.dumps(clients)


def test_native_registry_reopens_treasury_from_authoritative_run(registry_workspace):
    env, _, binding, _, _, _ = registry_workspace
    run = selected_run(env, binding)

    result = native_call(env, "vera_workspace_view", {"work_ref": run["work_ref"]})

    assert result["kind"] == "treasury"
    assert result["client_id"] == binding["client_id"]
    assert result["engagement_id"] == binding["engagement_id"]
    assert result["data"]["opening_cash"] == "40000.00"


def test_native_registry_cross_client_engagement_refuses(registry_workspace):
    env, _, binding, output, other_id, other_engagement = registry_workspace
    before = (output / "treasury_session.json").read_bytes()

    with pytest.raises(ValueError, match="does not belong"):
        native_call(
            env,
            "vera_workspace_open",
            {"client_id": binding["client_id"], "engagement_id": other_engagement},
        )
    swapped = "studio-" + "_".join(
        value.split("_", 1)[1]
        for value in (other_id, binding["engagement_id"], binding["run_id"])
    )
    with pytest.raises(ValueError):
        native_call(env, "vera_workspace_view", {"work_ref": swapped})

    assert (output / "treasury_session.json").read_bytes() == before


def test_native_registry_other_session_cannot_adopt_private_state(registry_workspace):
    env, _, _, _, _, _ = registry_workspace

    with pytest.raises(ValueError, match="configuration changed during this run"):
        native_call(
            {**env, "VERA_STUDIO_ARCHIVE_SESSION_ID": "different-fictional-session"},
            "vera_workspace_open",
            {},
        )


def test_native_registry_changed_source_blocks_reopen_and_chat_handoff(
    registry_workspace,
):
    env, _, binding, output, _, _ = registry_workspace
    run = selected_run(env, binding)
    inputs = output.parent / "inputs"
    source = next(inputs.rglob("*.csv"))
    source.write_bytes(source.read_bytes() + b"changed")

    listed = selected_run(env, binding)

    assert listed["inputs_valid"] is False
    assert listed["review_available"] is False
    with pytest.raises(ValueError):
        native_call(env, "vera_workspace_view", {"work_ref": run["work_ref"]})
    with pytest.raises(ValueError):
        native_call(env, "vera_workspace_resume_context", {"work_ref": run["work_ref"]})


def test_native_registry_unimplemented_workflow_keeps_verified_specialist_handoff(
    registry_workspace,
):
    env, _, _, _, other_id, other_engagement = registry_workspace
    run = native_call(
        env,
        "vera_workspace_open",
        {"client_id": other_id, "engagement_id": other_engagement},
    )["works"][0]

    result = native_call(
        env, "vera_workspace_resume_context", {"work_ref": run["work_ref"]}
    )

    assert run["review_available"] is False
    assert result == {
        "work_ref": run["work_ref"],
        "client_id": other_id,
        "engagement_id": other_engagement,
        "run_id": run["run_id"],
        "workflow_id": "composizione-negoziata",
    }


@pytest.mark.parametrize(
    "tool", ["vera_workspace_archive_setup", "vera_workspace_archive_refresh"]
)
def test_native_archive_configuration_refuses_model_path_argument_before_write(
    registry_workspace, tool
):
    env, _, _, _, _, _ = registry_workspace
    config = Path(env["VERA_STUDIO_ARCHIVE_STATE_DIR"]) / "config.json"
    before = config.read_bytes()

    with pytest.raises(ValueError, match="Unexpected field"):
        native_call(
            env, tool, {"confirmed": True, "archive_root": "/untrusted/browser/path"}
        )

    assert config.read_bytes() == before


def test_native_archive_setup_cancellation_preserves_absent_configuration(
    tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "native_navigation", ROOT / "plugins/vera/scripts/native_archive_navigation.py"
    )
    navigation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(navigation)
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_SESSION_ID", "fictional-cancelled-picker")
    core = navigation.archive_module(ROOT / "plugins/studio-archive")
    monkeypatch.setattr(core, "_select_archive_root_with_native_picker", lambda: None)

    result = navigation.archive_action(ROOT / "plugins/studio-archive", "setup")

    assert result["setup_status"] == "cancelled"
    assert not (tmp_path / "state/config.json").exists()


def test_native_archive_refresh_retains_source_and_customer_ledger_bytes(
    registry_workspace,
):
    env, root, binding, _, _, _ = registry_workspace
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }

    result = native_call(env, "vera_workspace_archive_refresh", {"confirmed": True})

    assert result["status"] == "refreshed"
    assert result["recovery_status"] == "recovered"
    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert {name: after[name] for name in before} == before
    navigation_files = sorted(Path(name) for name in after.keys() - before.keys())
    assert [path.name for path in navigation_files] == [
        ".readable-archive.lock",
        "APRI ARCHIVIO.html",
        "Indice.html",
        "Indice.html",
        ".readable-archive.lock",
        "APRI ARCHIVIO.html",
        "Indice.html",
        "Indice.html",
    ]
    assert {path.parts[0] for path in navigation_files} == {
        "Cliente Beta",
        "Studio client",
    }
    assert {path.parts[1] for path in navigation_files} == {"Vera"}
    assert selected_run(env, binding)["run_id"] == binding["run_id"]


def test_native_registry_pages_real_engagements_without_other_client_rows(
    registry_workspace,
):
    env, _, binding, _, _, other_engagement = registry_workspace
    ledger = _load_customer_ledger()
    new_engagement_count = 30
    for index in range(new_engagement_count):
        ledger.create_engagement(
            Path(binding["client_root"]),
            binding["client_id"],
            f"Fictional engagement {index}",
        )

    first = native_call(env, "vera_workspace_open", {"client_id": binding["client_id"]})
    second = native_call(
        env, "vera_workspace_open", {"client_id": binding["client_id"], "offset": 30}
    )

    assert first["total"] == new_engagement_count + 1
    assert len(first["engagements"]) == 30
    assert first["has_more"] is True
    assert len(second["engagements"]) == 1
    assert second["has_more"] is False
    first_ids = {row["engagement_id"] for row in first["engagements"]}
    second_ids = {row["engagement_id"] for row in second["engagements"]}
    assert first_ids.isdisjoint(second_ids)
    assert other_engagement not in first_ids | second_ids


def treasury_review_exchange(env: dict[str, str], reference: str) -> dict:
    """Exercise public JSON-RPC handlers with one live signing-key lifetime."""
    code = """
const workspace = require(process.argv[1]);
let id = 0;
const call = (name, args) => workspace.handle({jsonrpc: '2.0', id: ++id,
  method: 'tools/call', params: {name, arguments: args}}).result;
const ref = process.argv[2];
const first = call('vera_workspace_view', {work_ref: ref})._meta.workspace;
const item = first.items[0];
const selected = call('vera_workspace_view', {work_ref: ref, item_id: item.event_id})._meta.workspace;
const saved = call('vera_workspace_save', {work_ref: ref, item_id: item.event_id,
  revision: selected.revision, review_ticket: selected.review_ticket,
  human_reviewed: true, idempotency_key: 'fictional-owned-archive-review',
  decisions: {[item.event_id]: {expected_date: '2026-10-01', basis: 'Fictional human-reviewed timing'}}});
const reopened = call('vera_workspace_view', {work_ref: ref})._meta.workspace;
process.stdout.write(JSON.stringify({saved, first_revision: first.revision, reopened, event_id: item.event_id}));
"""
    completed = subprocess.run(
        [NODE, "-e", code, str(SERVER), reference],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_native_owned_archive_saves_and_reopens_authoritative_treasury_decision(
    registry_workspace,
):
    env, _, binding, output, _, _ = registry_workspace
    run = selected_run(env, binding)

    result = treasury_review_exchange(env, run["work_ref"])

    assert not result["saved"].get("isError"), result["saved"]
    assert result["saved"]["_meta"]["workspace"]["saved"] is True
    assert result["reopened"]["revision"] != result["first_revision"]
    from tests.plugins.test_treasury_delivery import current_record

    record = current_record(output)[1]
    assert record["decisions"][result["event_id"]]["expected_date"] == "2026-10-01"


@pytest.mark.parametrize("role", ["VIEWER", ""])
def test_native_owned_archive_viewer_override_refuses_domain_write(
    registry_workspace, role
):
    env, _, binding, output, _, _ = registry_workspace
    run = selected_run(env, binding)
    before = {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }

    result = treasury_review_exchange(
        {**env, "VERA_WORKSPACE_ROLES": role}, run["work_ref"]
    )

    assert result["saved"]["isError"] is True
    assert "Reviewer authority" in result["saved"]["content"][0]["text"]
    assert {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    } == before


def test_native_archive_picker_uses_existing_access_check_without_returning_root(
    tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "native_navigation_success",
        ROOT / "plugins/vera/scripts/native_archive_navigation.py",
    )
    navigation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(navigation)
    root = tmp_path / "Studio"
    root.mkdir()
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(tmp_path / "private-state"))
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_SESSION_ID", "fictional-selected-picker")
    core = navigation.archive_module(ROOT / "plugins/studio-archive")
    monkeypatch.setattr(core, "_select_archive_root_with_native_picker", lambda: root)

    result = navigation.archive_action(ROOT / "plugins/studio-archive", "setup")

    assert result["configured"] is True
    assert result["setup_status"] == "configured"
    assert result["access_diagnostic"]["ok"] is True
    assert result["access_diagnostic"]["root_listing"] == "readable"
    assert str(root) not in json.dumps(result)
    assert (tmp_path / "private-state/config.json").exists()
    assert list(root.iterdir()) == []


def test_native_registry_renamed_client_recovers_run_and_exposes_treasury_gap(
    registry_workspace,
):
    env, root, binding, output, _, _ = registry_workspace
    original_ref = selected_run(env, binding)["work_ref"]
    relative_output = output.relative_to(Path(binding["client_root"]))
    before = (output / "treasury_session.json").read_bytes()
    destination = root / "Fascicolo rinominato"
    Path(binding["client_root"]).rename(destination)

    native_call(env, "vera_workspace_archive_refresh", {"confirmed": True})
    run = selected_run(env, binding)

    assert run["work_ref"] == original_ref
    assert run["client_label"] == destination.name
    assert run["inputs_valid"] is True
    assert run["review_available"] is False
    assert run["review_status"] == "specialist_recovery_required"
    with pytest.raises(ValueError, match="prepared source is missing"):
        native_call(env, "vera_workspace_view", {"work_ref": original_ref})
    assert (
        native_call(env, "vera_workspace_resume_context", {"work_ref": original_ref})[
            "run_id"
        ]
        == binding["run_id"]
    )
    assert (
        destination / relative_output / "treasury_session.json"
    ).read_bytes() == before


@pytest.mark.parametrize(
    "tool", ["vera_workspace_archive_setup", "vera_workspace_archive_refresh"]
)
def test_native_archive_configuration_requires_explicit_choice(
    registry_workspace, tool
):
    env, _, _, _, _, _ = registry_workspace
    config = Path(env["VERA_STUDIO_ARCHIVE_STATE_DIR"]) / "config.json"
    before = config.read_bytes()

    with pytest.raises(ValueError, match="Invalid confirmed"):
        native_call(env, tool, {"confirmed": False})

    assert config.read_bytes() == before


@pytest.fixture
def registry_bilancio(tmp_path):
    environment = demo_environment(tmp_path)
    env = process_environment()
    env.update(environment)
    env.update(
        VERA_WORKSPACE_PYTHON=sys.executable,
        VERA_WORKSPACE_ACTOR_ID=environment["VERA_XBRL_ACTOR_ID"],
        VERA_WORKSPACE_TENANT_ID=environment["VERA_XBRL_TENANT_ID"],
        VERA_STUDIO_ARCHIVE_SESSION_ID="fictional-canonical-archive",
        VERA_STUDIO_ARCHIVE_STATE_DIR=str(tmp_path / "private-state"),
    )
    archive_cli(env, "configure", "--archive-root", str(tmp_path / "demo"))
    binding = json.loads(Path(env["VERA_XBRL_WORKSPACE_BINDINGS"]).read_bytes())[
        "bindings"
    ][0]
    return env, binding


def test_native_owned_archive_opens_canonical_bilancio_without_generic_allowlist(
    registry_bilancio,
):
    env, binding = registry_bilancio
    run = selected_run(env, binding)

    result = native_call(env, "vera_workspace_view", {"work_ref": run["work_ref"]})

    assert "VERA_WORKSPACE_BINDINGS" not in env
    assert run["review_available"] is True
    assert run["workflow"] == "bilancio-xbrl-it"
    assert result["kind"] == "bilancio"
    assert result["data"]["case_id"] == binding["case_id"]
    assert result["client_id"] == binding["client_id"]
    assert str(Path(binding["client_root"])) not in json.dumps(result["data"])


@pytest.mark.parametrize(
    "field", ["client_root", "client_id", "engagement_id", "run_id"]
)
def test_native_owned_archive_refuses_bilancio_binding_to_different_run_identity(
    registry_bilancio,
    field,
):
    env, binding = registry_bilancio
    path = Path(env["VERA_XBRL_WORKSPACE_BINDINGS"])
    payload = json.loads(path.read_bytes())
    payload["bindings"][0][field] = "different-fictional-identity"
    path.write_text(json.dumps(payload))
    run = selected_run(env, binding)

    with pytest.raises(ValueError, match="exact authorized case connection"):
        native_call(env, "vera_workspace_view", {"work_ref": run["work_ref"]})

    assert run["review_available"] is False
    assert run["review_status"] == "canonical_connection_required"


@pytest.mark.parametrize("field", ["tenant_id", "actor_id"])
def test_native_owned_archive_refuses_foreign_canonical_bilancio_actor(
    registry_bilancio,
    field,
):
    env, binding = registry_bilancio
    env["VERA_WORKSPACE_" + field.upper()] = "another-fictional-owner"
    run = selected_run(env, binding)

    with pytest.raises(ValueError, match="another actor"):
        native_call(env, "vera_workspace_view", {"work_ref": run["work_ref"]})

    assert run["review_available"] is False


@pytest.mark.parametrize("change", ["missing", "duplicate", "unavailable_case"])
def test_native_owned_archive_keeps_bilancio_unavailable_without_exact_case_access(
    registry_bilancio,
    change,
):
    env, binding = registry_bilancio
    path = Path(env["VERA_XBRL_WORKSPACE_BINDINGS"])
    payload = json.loads(path.read_bytes())
    if change == "missing":
        env.pop("VERA_XBRL_WORKSPACE_BINDINGS")
    elif change == "duplicate":
        payload["bindings"].append(dict(payload["bindings"][0]))
        path.write_text(json.dumps(payload))
    else:
        payload["bindings"][0]["case_id"] = "nonexistent_fictional_case"
        path.write_text(json.dumps(payload))
    run = selected_run(env, binding)

    with pytest.raises(ValueError):
        native_call(env, "vera_workspace_view", {"work_ref": run["work_ref"]})

    assert run["review_available"] is False
    assert (
        native_call(
            env, "vera_workspace_resume_context", {"work_ref": run["work_ref"]}
        )["run_id"]
        == binding["run_id"]
    )


@pytest.mark.parametrize("canonical_role", ["REVIEWER", "READ_ONLY_AUDITOR"])
def test_native_owned_archive_bilancio_save_retains_canonical_reviewer_authority(
    registry_bilancio,
    canonical_role,
):
    env, binding = registry_bilancio
    env["VERA_XBRL_ROLES"] = canonical_role
    reference = selected_run(env, binding)["work_ref"]
    case_path = (
        Path(env["VERA_XBRL_STORAGE_ROOT"]) / "demo_studio/aurora_2025/case.json"
    )
    before = case_path.read_bytes()
    code = """
const workspace = require(process.argv[1]);
let id = 0;
const call = (name, arguments) => workspace.handle({jsonrpc: '2.0', id: ++id,
  method: 'tools/call', params: {name, arguments}}).result;
const work_ref = process.argv[2];
const first = call('vera_workspace_view', {work_ref})._meta.workspace;
const item = first.items.find(row => row.rule_id === 'INPUT.PRIOR_XBRL_RECOMMENDED');
const selected = call('vera_workspace_view', {work_ref, item_id: item.issue_id})._meta.workspace;
const saved = call('vera_workspace_save', {work_ref, item_id: item.issue_id,
  revision: selected.revision, review_ticket: selected.review_ticket,
  human_reviewed: true, idempotency_key: 'fictional-owned-bilancio-review',
  action: 'ACKNOWLEDGED', reason: 'Esaminato rilievo sul precedente XBRL nel caso fittizio.'});
const reopened = call('vera_workspace_view', {work_ref})._meta.workspace;
process.stdout.write(JSON.stringify({saved, reopened}));
"""

    completed = subprocess.run(
        [NODE, "-e", code, str(SERVER), reference],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    if canonical_role == "READ_ONLY_AUDITOR":
        assert result["saved"]["isError"] is True
        assert case_path.read_bytes() == before
    else:
        assert not result["saved"].get("isError"), result["saved"]
        case = json.loads(case_path.read_bytes())
        assert len(result["reopened"]["data"]["review"]["review_decisions"]) == 1
        assert case["audit_events"][-1]["actor"] == "demo_reviewer"
        assert result["reopened"]["data"]["validation_current"] is False


def test_native_owned_archive_changed_bilancio_source_blocks_authorized_case_view(
    registry_bilancio,
):
    env, binding = registry_bilancio
    run = selected_run(env, binding)
    ledger = _load_customer_ledger()
    loaded = ledger.load_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    source = next((Path(loaded["output_dir"]).parent / "inputs").rglob("*.csv"))
    source.write_bytes(source.read_bytes() + b"changed source")

    with pytest.raises(ValueError):
        native_call(env, "vera_workspace_view", {"work_ref": run["work_ref"]})

    assert selected_run(env, binding)["inputs_valid"] is False
