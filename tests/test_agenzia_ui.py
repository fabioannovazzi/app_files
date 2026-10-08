"""Native projection and launch recovery through the same ordinary worker API."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins/browser-automation/scripts"


@pytest.fixture
def services(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return SimpleNamespace(
        ui=importlib.import_module("agenzia_ui"),
        cli=importlib.import_module("agenzia_acquire"),
        contracts=importlib.import_module("ade_acquisition.contracts"),
        storage=importlib.import_module("ade_acquisition.storage"),
        engine=importlib.import_module("ade_acquisition.engine"),
    )


@pytest.fixture
def workspace(tmp_path, services):
    plan = {
        "schema_version": "vera-agenzia-plan/v1",
        "clients": [
            {
                "name": "Ditta esempio",
                "tax_code": "01234567890",
                "vat_number": "01234567890",
            }
        ],
        "date_from": "2026-01-01",
        "date_to": "2026-01-31",
        "operations": ["ricevute"],
    }
    source = tmp_path / "plan.json"
    services.storage.atomic_json(source, plan)
    return {"plan_path": str(source), "output_directory": str(tmp_path / "output")}


def test_native_save_uses_exact_revision_and_retains_only_selected_clients(
    services, workspace
):
    opened = services.ui.dispatch({**workspace, "action": "open"})
    modified = {**opened["plan"], "date_to": "2026-02-28"}
    saved = services.ui.dispatch(
        {
            **workspace,
            "action": "save",
            "args": {"revision": opened["revision"], "plan": modified},
        }
    )
    assert saved["plan"]["date_to"] == "2026-02-28"
    with pytest.raises(services.contracts.AcquisitionError, match="draft-changed"):
        services.ui.dispatch(
            {
                **workspace,
                "action": "save",
                "args": {"revision": opened["revision"], "plan": modified},
            }
        )


def test_native_save_cannot_replace_a_client_identity(services, workspace):
    opened = services.ui.dispatch({**workspace, "action": "open"})
    opened["plan"]["clients"][0]["vat_number"] = "09876543210"
    with pytest.raises(
        services.contracts.AcquisitionError, match="outside-selected-source"
    ):
        services.ui.dispatch(
            {
                **workspace,
                "action": "save",
                "args": {"revision": opened["revision"], "plan": opened["plan"]},
            }
        )


def test_native_binding_expires_if_source_plan_changes(services, workspace):
    opened = services.ui.dispatch({**workspace, "action": "open"})
    updated = {**opened["plan"], "date_to": "2026-02-28"}
    services.storage.atomic_json(Path(workspace["plan_path"]), updated)
    with pytest.raises(
        services.contracts.AcquisitionError, match="source-plan-changed"
    ):
        services.ui.dispatch(
            {
                **workspace,
                "source_revision": opened["source_revision"],
                "action": "open",
            }
        )


def test_lost_start_response_returns_reserved_run_without_launching_again(
    services, workspace, monkeypatch
):
    launched = []

    def spawn(command, **kwargs):
        launched.append(command)
        return SimpleNamespace(pid=54321)

    monkeypatch.setattr(services.cli.subprocess, "Popen", spawn)
    store = services.storage.Store(Path(workspace["output_directory"]))
    plan = services.contracts.Plan.parse(
        services.storage.read_json(Path(workspace["plan_path"]))
    )
    first = services.cli._start(store, plan, "retry-token")
    again = services.cli._start(store, plan, "retry-token")
    assert again["run_id"] == first["run_id"]
    assert len(launched) == 1
    assert (
        services.storage.read_json(Path(first["run_directory"]) / "plan.json")
        == plan.payload()
    )


def test_startup_without_live_worker_expires_and_allows_explicit_resume(
    services, workspace, monkeypatch
):
    monkeypatch.setattr(
        services.cli.subprocess, "Popen", lambda *a, **k: SimpleNamespace(pid=54321)
    )
    opened = services.ui.dispatch({**workspace, "action": "open"})
    first = services.ui.dispatch(
        {
            **workspace,
            "action": "start",
            "args": {"revision": opened["revision"], "request_id": "first"},
        }
    )
    run = Path(first["run_directory"])
    old = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    services.storage.atomic_json(
        run / "status.json", {"state": "starting", "updated_at": old}
    )
    assert services.cli._summary(run)["state"] == "interrupted"
    resumed = services.ui.dispatch(
        {
            **workspace,
            "action": "resume",
            "args": {"run_id": run.name, "request_id": "resume"},
        }
    )
    assert resumed["run_id"] != run.name
    assert len(resumed["recent_runs"]) == 2
    repeat = services.ui.dispatch(
        {
            **workspace,
            "action": "resume",
            "args": {"run_id": run.name, "request_id": "resume"},
        }
    )
    assert repeat["run_id"] == resumed["run_id"]
    assert len(repeat["recent_runs"]) == 2


def test_different_launch_cannot_race_a_pending_start(services, workspace, monkeypatch):
    monkeypatch.setattr(
        services.cli.subprocess, "Popen", lambda *a, **k: SimpleNamespace(pid=54321)
    )
    store = services.storage.Store(Path(workspace["output_directory"]))
    plan = services.contracts.Plan.parse(
        services.storage.read_json(Path(workspace["plan_path"]))
    )
    services.cli._start(store, plan, "first")
    with pytest.raises(
        services.contracts.AcquisitionError, match="acquisition-already-running"
    ):
        services.cli._start(store, plan, "second")


def test_launch_failure_is_durable_and_retry_does_not_repeat_side_effect(
    services, workspace, monkeypatch
):
    def broken(*args, **kwargs):
        raise OSError("private machine path")

    monkeypatch.setattr(services.cli.subprocess, "Popen", broken)
    store = services.storage.Store(Path(workspace["output_directory"]))
    plan = services.contracts.Plan.parse(
        services.storage.read_json(Path(workspace["plan_path"]))
    )
    with pytest.raises(
        services.contracts.AcquisitionError, match="worker-launch-failed"
    ):
        services.cli._start(store, plan, "first")
    retry = services.cli._start(store, plan, "first")
    assert retry["state"] == "failed"
    assert retry["error"] == "worker-launch-failed"


def test_native_status_ignores_only_uncommitted_final_event(services, workspace):
    store = services.storage.Store(Path(workspace["output_directory"]))
    plan = services.contracts.Plan.parse(
        services.storage.read_json(Path(workspace["plan_path"]))
    )
    run = store.new_run(plan.payload())
    services.storage.atomic_json(
        run / "status.json",
        {"state": "partial", "updated_at": services.engine.timestamp()},
    )
    (run / "events.jsonl").write_text(
        json.dumps({"kind": "invoice", "status": "failed", "error": "missing-original"})
        + '\n{"kind":',
        encoding="utf-8",
    )
    result = services.ui.dispatch(
        {**workspace, "action": "status", "args": {"run_id": run.name}}
    )
    assert result["invoice_total"] == 1
    assert result["invoice_results"][0]["status"] == "failed"
    with pytest.raises(
        services.contracts.AcquisitionError, match="event-log-incomplete"
    ):
        services.engine.load_events(run)


def test_native_status_rejects_corrupt_committed_events(services, workspace):
    store = services.storage.Store(Path(workspace["output_directory"]))
    run = store.new_run(services.storage.read_json(Path(workspace["plan_path"])))
    (run / "events.jsonl").write_text("invalid\n", encoding="utf-8")
    with pytest.raises(
        services.contracts.AcquisitionError, match="event-log-incomplete"
    ):
        services.engine.load_events(run, allow_pending=True)


def test_native_download_cannot_escape_run_directory(services, workspace):
    store = services.storage.Store(Path(workspace["output_directory"]))
    run = store.new_run(services.storage.read_json(Path(workspace["plan_path"])))
    with pytest.raises(
        services.contracts.AcquisitionError, match="output-not-available"
    ):
        services.ui.dispatch(
            {
                **workspace,
                "action": "download",
                "args": {"run_id": run.name, "name": "../../plan.json"},
            }
        )


def test_worker_runs_actual_engine_and_writes_reports_without_model_calls(
    services, workspace, monkeypatch
):
    from contextlib import contextmanager

    demo = importlib.import_module("agenzia_demo")
    fixture = services.storage.read_json(
        SCRIPTS.parents[2] / "scripts/course_materials/inputs/agenzia/practice.json"
    )
    store = services.storage.Store(Path(workspace["output_directory"]))
    run = store.new_run(fixture["plan"])
    services.storage.atomic_json(run / "auth-ready.json", {"ready": True})

    @contextmanager
    def browser():
        yield object()

    monkeypatch.setattr(services.cli, "open_browser", browser)
    monkeypatch.setattr(
        services.cli, "Portal", lambda page: demo._TeachingPortal(fixture)
    )
    result = services.cli._worker(store, run)
    assert result["state"] == "complete"
    assert result["downloaded"] == 2
    assert (run / "riepilogo.xlsx").is_file()
    assert (run / "model_data_report.md").is_file()


def test_worker_cancel_during_login_keeps_terminal_status(
    services, workspace, monkeypatch
):
    from contextlib import contextmanager

    store = services.storage.Store(Path(workspace["output_directory"]))
    run = store.new_run(services.storage.read_json(Path(workspace["plan_path"])))
    services.storage.atomic_json(run / "cancel.json", {"cancel": True})

    @contextmanager
    def browser():
        yield object()

    monkeypatch.setattr(services.cli, "open_browser", browser)
    result = services.cli._worker(store, run)
    assert result["state"] == "cancelled"
    assert result["error"] == "cancelled"


def test_cli_prepares_plan_without_exposing_client_rows(services, tmp_path, capsys):
    source = tmp_path / "clients.csv"
    source.write_text(
        "nominativo cliente;codice fiscale;partita iva\nCliente riservato;01234567890;01234567890\n"
    )
    output = tmp_path / "plan.json"
    result = services.cli.main(
        [
            "plan",
            "--clients",
            str(source),
            "--date-from",
            "2026-01-01",
            "--date-to",
            "2026-01-31",
            "--operations",
            "ricevute",
            "--output",
            str(output),
        ]
    )
    visible = capsys.readouterr().out
    assert result == 0
    assert json.loads(visible)["clients"] == 1
    assert "Cliente riservato" not in visible
    assert (
        services.storage.read_json(output)["clients"][0]["vat_number"] == "01234567890"
    )


@pytest.mark.parametrize("action", ["status", "continue", "cancel"])
def test_cli_control_uses_selected_saved_run(services, workspace, capsys, action):
    store = services.storage.Store(Path(workspace["output_directory"]))
    run = store.new_run(services.storage.read_json(Path(workspace["plan_path"])))
    services.storage.atomic_json(
        run / "status.json",
        {"state": "waiting_for_login", "updated_at": services.engine.timestamp()},
    )
    result = services.cli.main(
        [action, "--output", str(store.root), "--run-id", run.name]
    )
    assert result == 0
    response = json.loads(capsys.readouterr().out)
    expected = {
        "status": "interrupted",
        "continue": "continue-requested",
        "cancel": "cancel-requested",
    }
    assert response["state"] == expected[action]


def test_cli_rejects_unknown_run_without_paths_or_traceback(
    services, workspace, capsys
):
    result = services.cli.main(
        [
            "status",
            "--output",
            workspace["output_directory"],
            "--run-id",
            "../elsewhere",
        ]
    )
    assert result == 1
    assert json.loads(capsys.readouterr().out) == {
        "state": "failed",
        "error": "run-id-invalid",
    }


def test_worker_does_not_report_completion_before_outputs_are_ready(
    services, workspace, monkeypatch
):
    from contextlib import contextmanager

    demo = importlib.import_module("agenzia_demo")
    fixture = services.storage.read_json(
        SCRIPTS.parents[2] / "scripts/course_materials/inputs/agenzia/practice.json"
    )
    store = services.storage.Store(Path(workspace["output_directory"]))
    run = store.new_run(fixture["plan"])
    services.storage.atomic_json(run / "auth-ready.json", {"ready": True})

    @contextmanager
    def browser():
        yield object()

    write_reports = services.cli.write_reports
    observed = []

    def delayed_outputs(folder, plan, state):
        observed.append(services.cli._summary(folder)["state"])
        return write_reports(folder, plan, state)

    monkeypatch.setattr(services.cli, "open_browser", browser)
    monkeypatch.setattr(
        services.cli, "Portal", lambda page: demo._TeachingPortal(fixture)
    )
    monkeypatch.setattr(services.cli, "write_reports", delayed_outputs)
    result = services.cli._worker(store, run)
    assert observed == ["finalizing"]
    assert result["state"] == "complete"
    assert result["reports_ready"] is True


def test_interrupted_output_generation_is_not_completed_work(services, workspace):
    store = services.storage.Store(Path(workspace["output_directory"]))
    run = store.new_run(services.storage.read_json(Path(workspace["plan_path"])))
    services.storage.atomic_json(
        run / "status.json",
        {
            "state": "complete",
            "reports_ready": False,
            "updated_at": services.engine.timestamp(),
        },
    )
    assert services.cli._summary(run)["state"] == "interrupted"
    with pytest.raises(services.contracts.AcquisitionError, match="report-not-ready"):
        services.ui.dispatch(
            {
                **workspace,
                "action": "download",
                "args": {"run_id": run.name, "name": "riepilogo.xlsx"},
            }
        )
