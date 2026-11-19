"""Explicit native settings preserve identity without reading process settings."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


def reporter():
    spec = importlib.util.spec_from_file_location(
        "explicit_incidents", ROOT / "plugins/lucia/scripts/operational_incidents.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_settings_file_cli_retains_identity_and_ignores_environment(tmp_path):
    settings = tmp_path / "settings.json"
    state = tmp_path / "state"
    settings.write_text(
        json.dumps(
            {
                "state_dir": str(state),
                "device_dir": str(tmp_path / "device"),
                "host": "codex",
                "host_session": str(uuid4()),
                "delivery": "local-only",
            }
        )
    )
    command = [
        sys.executable,
        str(ROOT / "plugins/lucia/scripts/operational_incidents.py"),
        "context",
        "--settings",
        str(settings),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=True)
    second = subprocess.run(command, capture_output=True, text=True, check=True)
    assert (
        json.loads(first.stdout)["credentials"]
        == json.loads(second.stdout)["credentials"]
    )
    assert json.loads(first.stdout)["outbox_path"] == str(state / "state.json")


def test_incident_environment_cannot_override_explicit_settings(tmp_path, monkeypatch):
    module = reporter()
    session, task = str(uuid4()), str(uuid4())
    monkeypatch.setenv("MPARANZA_INCIDENT_HOST_SESSION", "not-a-uuid")
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", "not-a-uuid")
    monkeypatch.setenv("MPARANZA_INCIDENT_STATE_DIR", str(tmp_path / "wrong"))
    monkeypatch.setenv("MPARANZA_INCIDENT_HOST", "cowork")
    module.configure_settings(
        {
            "host_session": session,
            "task_id": task,
            "host": "codex",
            "state_dir": str(tmp_path / "chosen"),
            "delivery": "local-only",
        }
    )
    receipt = module.report_failure("test", "execution", "Synthetic failure")
    assert receipt["reporting"] == "queued"
    state = json.loads((tmp_path / "chosen/state.json").read_text())
    assert state["outbox"][0]["delivery_scope"] == task
    assert module._SESSION == session
    assert module.local_context()["client_status"]["host"] == "codex"
    assert not (tmp_path / "wrong").exists()


@pytest.mark.parametrize(
    "settings",
    [
        {"host_session": "invalid"},
        {"task_id": "invalid"},
        {"host": "invalid"},
        {"delivery": "invalid"},
        {"endpoint": "https://example.com"},
    ],
)
def test_invalid_explicit_settings_are_rejected(settings):
    with pytest.raises(ValueError):
        reporter().configure_settings(settings)


def test_settings_preserve_symlink_path_rejection(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic links"):
        reporter().configure_settings({"state_dir": str(alias)})


@pytest.mark.parametrize(
    "name",
    ["operational_incidents.py", "notarized_run_receipt.py", "_python_bootstrap.py"],
)
def test_shared_network_helpers_do_not_read_environment(name):
    source = (ROOT / "plugins/_shared/reporting-runtime" / name).read_text()
    assert "os.environ" not in source
    assert "getenv(" not in source
