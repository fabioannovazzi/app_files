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


def queued_connector_report(tmp_path, monkeypatch):
    module, store, _ = client(tmp_path, monkeypatch)

    def offline(*_args):
        raise urllib.error.URLError("Tunnel connection failed: 403 Forbidden")

    monkeypatch.setattr(module, "_post", offline)
    queued = module.report_failure(
        "journal-sampling", "dependency-setup", "synthetic setup failure"
    )
    own = Credentials.model_validate(module.local_context()["credentials"])
    store.register(own)
    receipt = store.report(own, Report.model_validate(queued["report"]))
    return module, store, own, queued, receipt


def test_connector_delivery_ack_clears_exact_outbox_without_network_or_identity_change(
    tmp_path, monkeypatch
):
    module, _, own, queued, receipt = queued_connector_report(tmp_path, monkeypatch)
    private_log = module.diagnostic_directory() / "unreviewed.stderr"
    private_log.write_text("unreviewed private value")
    pointer = module.retain_diagnostic(private_log, queued)
    monkeypatch.setattr(
        module, "_post", lambda *_args: pytest.fail("Ack must not use direct HTTP")
    )

    first = module.acknowledge_delivery(receipt)
    second = module.acknowledge_delivery(receipt)

    assert first == second
    assert first["queued"] == 0
    assert module.local_context()["credentials"] == own.model_dump(mode="json")
    assert (
        module._read()["receipts"][0]["report"]["report_id"]
        == queued["report"]["report_id"]
    )
    assert pointer.exists()
    assert private_log.read_text() == "unreviewed private value"


@pytest.mark.parametrize(
    "invalid", ["foreign_owner", "wrong_report", "unrecorded", "supplement"]
)
def test_invalid_delivery_receipt_preserves_local_queue(tmp_path, monkeypatch, invalid):
    module, _, _, _, receipt = queued_connector_report(tmp_path, monkeypatch)
    replacements = {
        "foreign_owner": {"installation_id": str(uuid4())},
        "wrong_report": {"report_id": str(uuid4())},
        "unrecorded": {"recorded": False},
        "supplement": {"evidence_for_report_id": receipt["report_id"]},
    }
    before = (tmp_path / "private/state.json").read_text()

    with pytest.raises(ValueError):
        module.acknowledge_delivery({**receipt, **replacements[invalid]})

    assert (tmp_path / "private/state.json").read_text() == before


def test_blocked_direct_poll_returns_independent_route_and_preserves_queue(
    tmp_path, monkeypatch
):
    module, _, own, _, _ = queued_connector_report(tmp_path, monkeypatch)
    before = module._read()["outbox"]

    result = module.check_incidents()

    assert result["transport"] == "unavailable"
    assert result["independent_connector"] == "vera_incident_status"
    assert result["error_type"] == "URLError"
    assert "403 Forbidden" in result["message"]
    assert module._read()["outbox"] == before
    assert module.local_context()["credentials"] == own.model_dump(mode="json")


def test_remote_status_runs_fixed_retry_once_offline_and_retains_private_error_for_review(
    tmp_path, monkeypatch
):
    from modules.operational_incidents.contracts import Remedy

    module, store, own, queued, receipt = queued_connector_report(tmp_path, monkeypatch)
    module.acknowledge_delivery(receipt)
    store.remedy(
        receipt["incident_id"],
        Remedy(
            target_report_id=receipt["report_id"],
            kind="automatic",
            action="retry-dependency-setup",
            summary="Retry fixed setup",
            evidence="Interrupted synthetic setup",
            expected_outcome="Ready to resume",
        ),
    )
    row = store.status(own)["incidents"][0]
    remote = {
        "binding": "saved-connector",
        "installation_id": str(uuid4()),
        "incidents": [{**row, "installation_id": str(own.installation_id)}],
    }
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        kwargs["stderr"].write(
            "PRIVATE_RECOVERY_VALUE\nRuntimeError: complete synthetic setup cause\n"
        )
        return subprocess.CompletedProcess(arguments, 1, "", "")

    monkeypatch.setattr(module.subprocess, "run", run)

    result = module.check_incidents(remote_status=remote)
    repeated = module.check_incidents(remote_status=remote)

    assert len(calls) == 1
    assert calls[0][-2:] == ["--module", "journal-sampling"]
    assert result["queued"] == repeated["queued"] == 1
    state = module._read()
    assert state["outbox"][0]["payload"]["outcome"]["execution_succeeded"] is False
    assert "PRIVATE_RECOVERY_VALUE" not in json.dumps(state["outbox"])
    pointer = Path(result["pending_diagnostics"][0])
    metadata = json.loads(pointer.read_text())
    assert metadata["report"]["report_id"] == queued["report"]["report_id"]
    assert "complete synthetic setup cause" in Path(metadata["stderr_path"]).read_text()
    actual_outcome = state["outbox"][0]["payload"]["outcome"]
    outcome_receipt = store.outcome(own, Outcome.model_validate(actual_outcome))
    acknowledged = module.acknowledge_delivery(outcome_receipt)
    assert acknowledged["operation"] == "outcome"
    assert acknowledged["queued"] == 0
    assert pointer.exists()


def test_parent_runtime_exception_retains_its_complete_chain(
    tmp_path, monkeypatch, caplog
):
    import sys
    from types import SimpleNamespace

    module, store, _ = client(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "operational_incidents", module)
    spec = importlib.util.spec_from_file_location(
        "parent_capture_launcher",
        ROOT / "plugins/vera/scripts/managed_python_runtime.py",
    )
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    (tmp_path / "helper.py").write_text("# synthetic helper")
    monkeypatch.setattr(launcher, "prepare_execution_root", lambda *_args: tmp_path)
    monkeypatch.setattr(
        launcher._IMPLEMENTATION,
        "select_runtime",
        lambda *_args: SimpleNamespace(requirement_root=tmp_path),
    )

    def failed_parent(*_args, **_kwargs):
        try:
            raise OSError("synthetic underlying parent cause")
        except OSError as error:
            raise RuntimeError(
                "synthetic parent failure PRIVATE_PARENT_VALUE"
            ) from error

    monkeypatch.setattr(launcher._IMPLEMENTATION, "main", failed_parent)

    result = launcher.main(["--module", "bandi-agevolazioni", "run", "helper.py"])

    assert result == 1
    pointer = Path(module.local_context()["pending_diagnostics"][0])
    metadata = json.loads(pointer.read_text())
    raw = Path(metadata["stderr_path"]).read_text()
    assert "synthetic underlying parent cause" in raw
    assert "synthetic parent failure PRIVATE_PARENT_VALUE" in raw
    assert "PRIVATE_PARENT_VALUE" not in json.dumps(store.queue())
    assert "VERA_TECHNICAL_EVIDENCE" in caplog.text


def test_integrity_failure_routes_to_remote_connector_without_unverified_report_helper(
    tmp_path, monkeypatch, caplog
):
    import sys
    from types import SimpleNamespace

    module, _, _ = client(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "operational_incidents", module)
    monkeypatch.setattr(
        module,
        "report_failure",
        lambda *_args, **_kwargs: pytest.fail(
            "Unverified incident code must not execute"
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "integrity_capture_launcher",
        ROOT / "plugins/vera/scripts/managed_python_runtime.py",
    )
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    (tmp_path / "helper.py").write_text("# synthetic helper")
    monkeypatch.setattr(
        launcher._IMPLEMENTATION,
        "select_runtime",
        lambda *_args: SimpleNamespace(requirement_root=tmp_path),
    )

    def invalid(*_args):
        raise ValueError("Installation content mismatch: synthetic.py")

    monkeypatch.setattr(launcher, "prepare_execution_root", invalid)

    result = launcher.main(["--module", "bandi-agevolazioni", "run", "helper.py"])

    assert result == 1
    assert "VERA_REMOTE_INCIDENT_REQUIRED" in caplog.text
    assert "stage=installation-preparation" in caplog.text
    assert "Installation content mismatch: synthetic.py" in caplog.text


def test_remote_status_for_another_installation_cannot_run_local_retry(
    tmp_path, monkeypatch
):
    module, _, _, _, _ = queued_connector_report(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Foreign action must not execute"),
    )
    remote = {
        "binding": "saved-connector",
        "installation_id": str(uuid4()),
        "incidents": [{"installation_id": str(uuid4())}],
    }

    result = module.check_incidents(remote_status=remote)

    assert result["pending"] == []
    assert result["queued"] == 1


def test_out_of_order_receipt_ack_still_uses_exact_latest_report(tmp_path, monkeypatch):
    from modules.operational_incidents.contracts import Remedy

    module, store, own, _, first = queued_connector_report(tmp_path, monkeypatch)
    second_queued = module.report_failure(
        "journal-sampling",
        "dependency-setup",
        "synthetic setup failure",
        measurements={"attempt": 2},
    )
    second = store.report(own, Report.model_validate(second_queued["report"]))
    module.acknowledge_delivery(second)
    module.acknowledge_delivery(first)
    store.remedy(
        second["incident_id"],
        Remedy(
            target_report_id=second["report_id"],
            kind="automatic",
            action="retry-dependency-setup",
            summary="Validate setup",
            evidence="Current setup boundary",
            expected_outcome="Ready to resume",
        ),
    )
    remote = {
        "binding": "saved-connector",
        "installation_id": str(uuid4()),
        "incidents": [
            {
                **store.status(own)["incidents"][0],
                "installation_id": str(own.installation_id),
            }
        ],
    }
    monkeypatch.setattr(
        module,
        "_post",
        lambda *_args: pytest.fail("Cached-status retry must not use HTTP"),
    )
    calls = []

    def run(arguments, **_kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", run)

    result = module.check_incidents(remote_status=remote)

    assert first["incident_id"] == second["incident_id"]
    assert len(calls) == 1
    assert result["notifications"][-1]["recovery"] == "ready-to-resume"
    pending = json.loads((tmp_path / "private/state.json").read_text())["outbox"]
    assert pending[0]["payload"]["outcome"]["report_id"] == second["report_id"]
    assert pending[0]["payload"]["outcome"]["status"] == "action-required"


def test_cli_ack_delivery_uses_actual_receipt_file_without_network(
    tmp_path, monkeypatch, capsys
):
    module, _, _, _, receipt = queued_connector_report(tmp_path, monkeypatch)
    path = tmp_path / "actual-receipt.json"
    path.write_text(json.dumps(receipt))
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["operational_incidents.py", "ack-delivery", "--input", str(path)],
    )

    module.main()

    assert json.loads(capsys.readouterr().out)["queued"] == 0
    assert module.local_context()["queued"] == 0


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


def test_setup_helper_success_requires_original_case_verification(
    tmp_path, monkeypatch
):
    module, store, _ = client(tmp_path, monkeypatch)
    module.report_failure(
        "journal-sampling", "dependency-setup", "helper exit", exit_code=1
    )
    module.record_success("journal-sampling", "run_sample.py")
    assert store.queue()[0]["outcomes"][0]["status"] == "action-required"
    assert store.queue()[0]["outcomes"][0]["execution_succeeded"] is False


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
            target_report_id=result["report"]["report_id"],
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
                "target_report_id": result["report"]["report_id"],
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
    assert store.queue()[0]["outcomes"][0]["status"] == "action-required"
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
    assert saved["outcomes"][-1]["execution_succeeded"] is False
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
