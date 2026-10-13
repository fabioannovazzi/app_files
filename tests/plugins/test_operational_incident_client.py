"""Automatic delivery, retry persistence and scoped recovery behavior."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import urllib.error
from pathlib import Path
from uuid import uuid4

import pytest

from modules.operational_incidents.contracts import Credentials, Outcome, Report
from modules.operational_incidents.store import IncidentStore

ROOT = Path(__file__).resolve().parents[2]


def client(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "isolated_incident_client",
        ROOT / "plugins/vera/scripts/operational_incidents.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "installation"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"name": "vera", "version": "0.1.361"})
    )
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setenv("MPARANZA_INCIDENT_STATE_DIR", str(tmp_path / "private"))
    store = IncidentStore(tmp_path / "server.sqlite3")

    def post(operation, payload):
        credentials = Credentials.model_validate(payload["credentials"])
        if operation == "register":
            return store.register(credentials)
        if operation == "report":
            return store.report(credentials, Report.model_validate(payload["report"]))
        if operation == "status":
            return store.status(credentials)
        return store.outcome(credentials, Outcome.model_validate(payload["outcome"]))

    monkeypatch.setattr(module, "_post", post)
    return module, store, post


def test_failure_delivers_automatically_and_persists_receipt(tmp_path, monkeypatch):
    module, store, _ = client(tmp_path, monkeypatch)
    result = module.report_failure(
        "journal-sampling",
        "dependency-setup",
        "runtime setup failed: permission denied",
    )
    saved = json.loads((tmp_path / "private/state.json").read_text())
    assert result["reporting"] == "delivered"
    assert saved["outbox"] == []
    assert saved["receipts"][0]["incident_id"] == store.queue()[0]["incident_id"]


def test_offline_delivery_keeps_exact_report_for_retry(tmp_path, monkeypatch):
    module, store, post = client(tmp_path, monkeypatch)

    def unavailable(*_args):
        raise urllib.error.URLError("service unavailable")

    monkeypatch.setattr(module, "_post", unavailable)
    first = module.report_failure(
        "journal-sampling", "dependency-setup", "setup unavailable"
    )
    pending = json.loads((tmp_path / "private/state.json").read_text())["outbox"][0][
        "payload"
    ]["report"]
    assert first["reporting"] == "queued"
    monkeypatch.setattr(module, "_post", post)
    module.check_incidents(recover=False)
    assert store.queue()[0]["reports"][0]["report_id"] == pending["report_id"]
    assert json.loads((tmp_path / "private/state.json").read_text())["outbox"] == []


def test_identical_offline_failures_do_not_duplicate_pending_report(
    tmp_path, monkeypatch
):
    module, _, _ = client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "_post",
        lambda *_args: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    module.report_failure("journal-sampling", "dependency-setup", "same error")
    module.report_failure("journal-sampling", "dependency-setup", "same error")
    assert len(json.loads((tmp_path / "private/state.json").read_text())["outbox"]) == 1


def test_startup_retains_capability_without_network_or_shell(tmp_path, monkeypatch):
    module, _, _ = client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "_post",
        lambda *_args: pytest.fail("Startup context must not need network"),
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Startup must not need shell"),
    )
    first = module.startup_context()
    second = module.startup_context()
    assert first == second
    assert "vera_incident_register/status" in first


def test_unavailable_local_state_routes_to_independent_connector(tmp_path, monkeypatch):
    module, _, _ = client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module, "_read", lambda: (_ for _ in ()).throw(PermissionError("private state"))
    )
    result = module.report_failure(
        "journal-sampling", "dependency-setup", "setup failed"
    )
    assert result["independent_connector"] == "vera_incident_report"
    assert "vera_incident_register" in module.startup_context()


def test_actual_matching_setup_execution_closes_incident(tmp_path, monkeypatch):
    module, store, _ = client(tmp_path, monkeypatch)
    module.report_failure(
        "journal-sampling", "dependency-setup", "helper exit", exit_code=1
    )
    module.record_success("journal-sampling", "run_sample.py")
    assert store.queue() == []


def test_unrelated_helper_success_does_not_close_failed_operation(
    tmp_path, monkeypatch
):
    module, store, _ = client(tmp_path, monkeypatch)
    module.report_failure(
        "journal-sampling", "helper:run_sample.py", "helper exit", exit_code=1
    )
    module.record_success("journal-sampling", "inspect_journal.py")
    assert store.queue()[0]["status"] == "open"


def test_success_without_prior_incident_has_no_network_cost(tmp_path, monkeypatch):
    module, _, _ = client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module, "_post", lambda *_args: pytest.fail("No incident needs a status call")
    )
    module.record_success("journal-sampling", "run_sample.py")


def test_builtin_repair_runs_once_and_setup_success_does_not_close_incident(
    tmp_path, monkeypatch
):
    from modules.operational_incidents.contracts import Remedy

    module, store, _ = client(tmp_path, monkeypatch)
    result = module.report_failure(
        "journal-sampling", "dependency-setup", "setup failed"
    )
    store.remedy(
        result["incident_id"],
        Remedy(
            kind="automatic",
            action="retry-dependency-setup",
            summary="Repeat verified setup",
            evidence="Interrupted package setup identified",
            expected_outcome="Actual helper executes",
        ),
    )
    calls = []

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", run)
    module.check_incidents()
    module.check_incidents()
    assert len(calls) == 1
    assert calls[0][1].get("shell") is None
    assert calls[0][0][-2:] == ["--module", "journal-sampling"]
    assert store.queue()[0]["deliveries"][0]["status"] == "action-required"


def test_client_rejects_unsupported_remote_action_without_running_it(
    tmp_path, monkeypatch
):
    module, _, post = client(tmp_path, monkeypatch)
    result = module.report_failure(
        "journal-sampling", "dependency-setup", "setup failed"
    )

    def poisoned(operation, payload):
        response = post(operation, payload)
        if operation == "status":
            response["incidents"][0]["remedy"] = {
                "kind": "automatic",
                "action": "download-and-execute",
            }
        return response

    monkeypatch.setattr(module, "_post", poisoned)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail(
            "Remote arbitrary commands are prohibited"
        ),
    )
    with pytest.raises(ValueError, match="Unsupported"):
        module.check_incidents()
    assert result["reporting"] == "delivered"


def test_failure_removes_path_and_credentials_from_wire(tmp_path, monkeypatch):
    module, store, _ = client(tmp_path, monkeypatch)
    module.report_failure(
        "journal-sampling",
        "dependency-setup",
        "Cannot execute /home/private-user/private-project/tool token=private-secret",
    )
    encoded = json.dumps(store.queue()[0]["reports"])
    assert "private-user" not in encoded
    assert "private-project" not in encoded
    assert "private-secret" not in encoded


def test_symlink_state_does_not_follow_target(tmp_path, monkeypatch):
    module, _, _ = client(tmp_path, monkeypatch)
    private = tmp_path / "private"
    private.mkdir()
    target = tmp_path / "outside.json"
    target.write_text("do not read or overwrite")
    try:
        (private / "state.json").symlink_to(target)
    except OSError:
        pytest.skip("This host does not permit a local symlink fixture")
    result = module.report_failure("journal-sampling", "dependency-setup", "failed")
    assert result["reporting"] == "local-state-unavailable"
    assert target.read_text() == "do not read or overwrite"


def test_long_technical_message_is_delivered_completely(tmp_path, monkeypatch):
    module, store, _ = client(tmp_path, monkeypatch)
    message = "technical detail " * 12000
    result = module.report_failure("journal-sampling", "dependency-setup", message)
    received = "".join(
        item["message"]
        for row in store.queue()
        for report in row["reports"]
        for item in report["diagnostics"]
    )
    assert result["reporting"] == "delivered"
    assert received == message


def test_concurrent_offline_failures_preserve_both_reports(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    module, _, _ = client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "_post",
        lambda *_args: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda message: module.report_failure(
                    "journal-sampling", "dependency-setup", message
                ),
                ["first technical error", "second technical error"],
            )
        )
    assert all(result["reporting"] == "queued" for result in results)
    saved = json.loads((tmp_path / "private/state.json").read_text())
    assert {
        item["payload"]["report"]["diagnostics"][0]["message"]
        for item in saved["outbox"]
    } == {"first technical error", "second technical error"}


def test_adoption_never_replaces_existing_incident_history(tmp_path, monkeypatch):
    module, store, _ = client(tmp_path, monkeypatch)
    module.report_failure("journal-sampling", "dependency-setup", "original error")
    original = json.loads((tmp_path / "private/state.json").read_text())
    with pytest.raises(ValueError, match="existing incident identity"):
        module._adopt(
            {
                "credentials": {
                    "installation_id": str(uuid4()),
                    "installation_key": uuid4().hex,
                }
            }
        )
    assert json.loads((tmp_path / "private/state.json").read_text()) == original


def test_unregistered_remote_capability_is_not_adopted(tmp_path, monkeypatch):
    from modules.operational_incidents.store import IncidentNotFound

    module, _, _ = client(tmp_path, monkeypatch)
    with pytest.raises(IncidentNotFound):
        module._adopt(
            {
                "credentials": {
                    "installation_id": str(uuid4()),
                    "installation_key": uuid4().hex,
                }
            }
        )
    assert not (tmp_path / "private/state.json").exists()


def test_obsolete_outcome_is_retained_without_blocking_later_reports(
    tmp_path, monkeypatch
):
    module, store, post = client(tmp_path, monkeypatch)
    module.report_failure("journal-sampling", "dependency-setup", "original failure")
    state = module._read()
    state["outbox"].append(
        {
            "operation": "outcome",
            "payload": {
                "outcome": {
                    "outcome_id": str(uuid4()),
                    "incident_id": state["receipts"][0]["incident_id"],
                    "remedy_revision": 1,
                    "status": "recovered",
                    "execution_succeeded": True,
                }
            },
        }
    )
    module._write(state)

    def transport(operation, payload):
        if operation == "outcome":
            raise urllib.error.HTTPError(
                "https://mparanza.com/api/operational-incidents/outcome",
                409,
                "revision changed",
                {},
                None,
            )
        return post(operation, payload)

    monkeypatch.setattr(module, "_post", transport)
    result = module.report_failure(
        "journal-sampling", "dependency-setup", "new technical failure"
    )
    saved = module._read()
    assert result["reporting"] == "delivered"
    assert saved["outbox"] == []
    assert len(saved["rejected_outcomes"]) == 1
    assert len(store.queue()) == 2


def test_same_helper_success_does_not_prove_recovery_of_original_case(
    tmp_path, monkeypatch
):
    module, store, _ = client(tmp_path, monkeypatch)
    module.report_failure(
        "journal-sampling",
        "helper:run_sample.py",
        "Original task helper failed",
        exit_code=1,
    )
    module.record_success("journal-sampling", "run_sample.py")
    assert store.queue()[0]["status"] == "open"


def test_success_during_service_outage_is_durable_and_delivered_on_return(
    tmp_path, monkeypatch
):
    module, store, post = client(tmp_path, monkeypatch)
    module.report_failure(
        "journal-sampling", "dependency-setup", "Synthetic setup failure"
    )
    monkeypatch.setattr(
        module,
        "_post",
        lambda *_args: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(urllib.error.URLError):
        module.record_success("journal-sampling", "run_sample.py")
    assert module._read()["outbox"][0]["operation"] == "observed-success"
    monkeypatch.setattr(module, "_post", post)
    module.check_incidents(recover=False)
    assert store.queue() == []
    assert module._read()["outbox"] == []


def test_offline_failure_success_same_failure_sequence_remains_unresolved(
    tmp_path, monkeypatch
):
    module, store, post = client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "_post",
        lambda *_args: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    module.report_failure(
        "journal-sampling", "dependency-setup", "same synthetic error"
    )
    with pytest.raises(urllib.error.URLError):
        module.record_success("journal-sampling", "run_sample.py")
    module.report_failure(
        "journal-sampling", "dependency-setup", "same synthetic error"
    )
    assert [item["operation"] for item in module._read()["outbox"]] == [
        "report",
        "observed-success",
        "report",
    ]
    monkeypatch.setattr(module, "_post", post)
    module.check_incidents(recover=False)
    row = store.queue()[0]
    assert row["status"] == "open"
    assert len(row["reports"]) == 2


def test_delayed_success_records_evidence_without_closing_newer_remote_failure(
    tmp_path, monkeypatch
):
    module, store, post = client(tmp_path, monkeypatch)
    module.report_failure(
        "journal-sampling", "dependency-setup", "Synthetic setup failure"
    )
    monkeypatch.setattr(
        module,
        "_post",
        lambda *_args: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(urllib.error.URLError):
        module.record_success("journal-sampling", "run_sample.py")
    row = store.queue()[0]["reports"][0]
    credentials = Credentials.model_validate(module._read()["credentials"])
    store.report(credentials, Report.model_validate({**row, "report_id": str(uuid4())}))
    monkeypatch.setattr(module, "_post", post)
    module.check_incidents(recover=False)
    saved = store.queue()[0]
    assert saved["status"] == "open"
    assert saved["outcomes"][-1]["execution_succeeded"] is True
    assert saved["outcomes"][-1]["status"] == "action-required"


def test_cli_context_returns_saved_identity_when_network_is_blocked(
    tmp_path, monkeypatch, capsys
):
    module, _, _ = client(tmp_path, monkeypatch)
    module.startup_context()
    expected = module._read()["credentials"]
    monkeypatch.setattr(
        module,
        "_post",
        lambda *_args: pytest.fail("Local context must not contact the service"),
    )
    monkeypatch.setattr(module.sys, "argv", ["operational_incidents.py", "context"])

    module.main()

    result = json.loads(capsys.readouterr().out)
    assert result["credentials"] == expected
    assert result["queued"] == 0


@pytest.mark.parametrize("extra_stderr_bytes", [0, 100000])
def test_real_failed_helper_retains_error_chain_without_uploading_raw_stderr(
    tmp_path, monkeypatch, capfd, caplog, extra_stderr_bytes
):
    import sys
    from types import SimpleNamespace

    module, store, _ = client(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "operational_incidents", module)
    spec = importlib.util.spec_from_file_location(
        "diagnostic_capture_launcher",
        ROOT / "plugins/vera/scripts/managed_python_runtime.py",
    )
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    helper = tmp_path / "helper.py"
    helper.write_text(
        "import sys\nsys.stdout.write('PROFESSIONAL_STDOUT_SENTINEL\\n')\nsys.stderr.write('PRIVATE_CASE_VALUE_SENTINEL\\n')\n"
        + f"sys.stderr.write('X' * {extra_stderr_bytes})\n"
        + "try:\n    raise OSError('synthetic underlying cause')\nexcept OSError as cause:\n    raise RuntimeError('synthetic transport failed') from cause\n"
    )
    monkeypatch.setattr(launcher, "prepare_execution_root", lambda *args: tmp_path)
    monkeypatch.setattr(
        launcher._IMPLEMENTATION,
        "select_runtime",
        lambda *args: SimpleNamespace(requirement_root=tmp_path),
    )
    monkeypatch.setattr(
        launcher._IMPLEMENTATION,
        "ensure_runtime",
        lambda *args, **kwargs: (True, tmp_path, "ready"),
    )
    monkeypatch.setattr(
        launcher._IMPLEMENTATION, "runtime_python", lambda *args: Path(sys.executable)
    )
    monkeypatch.setattr(
        launcher._IMPLEMENTATION, "runtime_environment", lambda *args: None
    )

    result = launcher.main(["--module", "bandi-agevolazioni", "run", "helper.py"])

    assert result == 1
    path = Path(module.local_context()["pending_diagnostics"][0])
    saved = json.loads(path.read_text())
    raw = Path(saved["stderr_path"]).read_text()
    assert "RuntimeError: synthetic transport failed" in raw
    assert "OSError: synthetic underlying cause" in raw
    assert "direct cause" in raw
    assert raw.count("X") == extra_stderr_bytes
    assert saved["report"]["measurements"]["diagnostic_review_pending"] is True
    assert (
        saved["report"]["measurements"]["stderr_bytes"]
        == Path(saved["stderr_path"]).stat().st_size
    )
    assert "PRIVATE_CASE_VALUE_SENTINEL" in raw
    assert "PROFESSIONAL_STDOUT_SENTINEL" not in raw
    transmitted = json.dumps(store.queue())
    assert "PRIVATE_CASE_VALUE_SENTINEL" not in transmitted
    assert "synthetic transport failed" not in transmitted
    assert (
        saved["report"]["report_id"]
        == store.status(
            Credentials.model_validate(module.local_context()["credentials"])
        )["incidents"][0]["latest_report_id"]
    )
    captured = capfd.readouterr()
    assert "PROFESSIONAL_STDOUT_SENTINEL" in captured.out
    assert "synthetic transport failed" in captured.err
    assert "VERA_TECHNICAL_EVIDENCE" in caplog.text


def test_diagnostic_ack_requires_matching_recorded_supplement(tmp_path, monkeypatch):
    module, store, _ = client(tmp_path, monkeypatch)
    receipt = module.report_failure(
        "bandi-agevolazioni",
        "helper:opportunity_radar.py",
        "helper failed",
        exit_code=1,
    )
    error_path = module.diagnostic_directory() / "test.stderr"
    error_path.write_text("synthetic failure plus unrelated private content")
    pointer = module.retain_diagnostic(error_path, receipt)
    reviewed = Report.model_validate(
        {
            **receipt["report"],
            "report_id": str(uuid4()),
            "evidence_for_report_id": receipt["report"]["report_id"],
            "diagnostics": [
                {
                    "component": "vera-runtime",
                    "error_type": "RuntimeError",
                    "message": "synthetic failure",
                    "stage": "helper:opportunity_radar.py",
                    "evidence_source": "technical-log",
                    "exit_code": 1,
                }
            ],
        }
    )
    ack = store.report(
        Credentials.model_validate(module.local_context()["credentials"]), reviewed
    )

    module.acknowledge_diagnostic(ack, pointer)

    assert not pointer.exists()
    assert not error_path.exists()
    assert module.local_context()["pending_diagnostics"] == []
    assert (
        store.show(ack["incident_id"])["evidence"][0]["diagnostics"][0]["message"]
        == "synthetic failure"
    )


@pytest.mark.parametrize(
    "receipt",
    [{"recorded": False, "evidence_for_report_id": "unknown"}, {"recorded": True}],
)
def test_unrecorded_or_unbound_receipt_cannot_delete_local_diagnostics(
    tmp_path, monkeypatch, receipt
):
    module, _, _ = client(tmp_path, monkeypatch)
    path = module.diagnostic_directory() / "retained.stderr"
    path.write_text("unreviewed technical evidence")

    with pytest.raises(ValueError):
        module.acknowledge_diagnostic(receipt, path.with_suffix(".json"))

    assert path.read_text() == "unreviewed technical evidence"


def test_acknowledging_one_capture_preserves_other_logs_for_the_same_report(
    tmp_path, monkeypatch
):
    module, _, _ = client(tmp_path, monkeypatch)
    receipt = module.report_failure(
        "bandi-agevolazioni", "helper:opportunity_radar.py", "failed"
    )
    first = module.diagnostic_directory() / "first.stderr"
    second = module.diagnostic_directory() / "second.stderr"
    first.write_text("first complete error")
    second.write_text("another pending error")
    first_pointer = module.retain_diagnostic(first, receipt)
    second_pointer = module.retain_diagnostic(second, receipt)
    ack = {"recorded": True, "evidence_for_report_id": receipt["report"]["report_id"]}

    module.acknowledge_diagnostic(ack, first_pointer)

    assert not first.exists()
    assert second.read_text() == "another pending error"
    assert second_pointer.exists()
