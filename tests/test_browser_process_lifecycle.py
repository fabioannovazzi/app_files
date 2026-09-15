"""Connected user journey tests. All browser data and CR responses are synthetic."""

from __future__ import annotations

import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/browser-automation/scripts"
VERA = ROOT / "plugins/vera"
FIXTURE = ROOT / "tests/fixtures/browser_automation_runtime/capability.json"
NODE_FIXTURE = ROOT / "tests/fixtures/browser_process_tab.mjs"


@pytest.fixture
def lifecycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "cr-state"))
    return importlib.import_module("process_lifecycle")


def host(mode: str = "simulated", **overrides: Any) -> dict[str, Any]:
    return {
        "execution_mode": mode,
        "browser_control": True,
        "persistent_node": True,
        "local_files": True,
        "locale": "en",
        **overrides,
    }


def description() -> dict[str, Any]:
    capability = json.loads(FIXTURE.read_text())
    return {
        "site": capability["site"]["name"],
        "process": capability["process"],
        "start_state": "Synthetic search page ready",
        "end_condition": "Two synthetic rows with exact fields, or verified empty result",
    }


def release(cr_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "plugin_version": "test-build",
        "status": "built",
        "evidence": "Synthetic test source; no publication or deployment",
        "cr_ids": cr_ids or [],
    }


def checkpoint() -> dict[str, Any]:
    process = description()
    return {
        "schema_version": "browser-teaching-checkpoint/v1",
        "objective": process["process"]["objective"],
        "start_state": process["start_state"],
        "end_condition": process["end_condition"],
        "resume_instruction": "Verify the demonstrated result and inspect the unresolved empty branch",
        "status": "paused",
        "steps": [],
    }


def development() -> dict[str, Any]:
    return {
        "title": "Complete the synthetic search process",
        "process": "Synthetic record search",
        "objective": description()["process"]["objective"],
        "source_version": "test-build",
        "findings": [
            {
                "summary": "Synthetic fixture operator reports the demonstrated row count",
                "basis": "operator_report",
                "step_ids": [],
            }
        ],
        "requested_work": ["Repair result acquisition and replay the exact process"],
        "acceptance_checks": [
            "Two rows match the synthetic fixture; the empty branch is explicitly checked"
        ],
        "gaps": ["No live customer run"],
        "known_limits": ["Synthetic fixture only"],
    }


def problem() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "title": "Synthetic failed result acquisition",
        "expected": "Two synthetic records",
        "observed": "The fixture operator reports that result acquisition stopped",
        "reproduction": [],
        "diagnostics": {
            "occurred_at": None,
            "runtime": None,
            "operation": "Synthetic record search",
            "evidence": [
                "Operator report: result acquisition stopped; no original browser receipt was available"
            ],
            "missing_reasons": {
                "occurred_at": "Original occurrence time was not recorded",
                "runtime": "The original conversation host cannot be verified",
                "reproduction": "Only an attributed partial report is available",
            },
        },
    }


def run_fixture(
    attempt: dict[str, Any], current_host: dict[str, Any], **options: Any
) -> dict[str, Any]:
    config = Path(attempt["attempt_directory"]) / "fixture-config.json"
    config.write_text(
        json.dumps(
            {
                "attemptDirectory": attempt["attempt_directory"],
                "currentHost": current_host,
                **options,
            }
        )
    )
    completed = subprocess.run(
        ["node", str(NODE_FIXTURE), str(config)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


class Response:
    def __init__(self, payload: Any):
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, amount=-1):
        return self.body[:amount] if amount >= 0 else self.body


class Service:
    """Mock service returns a non-guessed CR number and keeps server idempotency."""

    def __init__(self):
        self.requests = []
        self.fail_once = False

    def __call__(self, request, **_kwargs):
        body = json.loads(request.data)
        self.requests.append(body)
        if self.fail_once:
            self.fail_once = False
            import urllib.error

            raise urllib.error.URLError(
                "synthetic timeout after durable server acceptance"
            )
        return Response(
            {
                "change_request_id": "CR-847",
                "status_token": "synthetic-token-kept-local",
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        )


def registered(lifecycle, tmp_path):
    store = lifecycle.ProcessStore(tmp_path / "process-data")
    process = store.create(description())["process_id"]
    store.add_version(process, FIXTURE, release())
    return store, process


def test_teaching_partial_failure_feedback_release_and_retest_survive_new_context(
    lifecycle, tmp_path
):
    store, process = registered(lifecycle, tmp_path)
    teaching = store.begin(process, "teaching", host())
    store.teach(teaching["attempt_id"], checkpoint(), 0)
    saved = checkpoint()
    saved["steps"] = [
        {
            "id": "search",
            "intent": "Search the selected population",
            "action": "Enter the query and submit",
            "decision_reason": "The operator selects the professional scope",
            "outcome": "Operator reports two displayed rows",
            "postcondition": "Two records can be checked",
            "status": "understood",
            "evidence_basis": "operator_report",
            "uncertainties": [],
            "capture": None,
        }
    ]
    store.teach(teaching["attempt_id"], saved, 1)
    restarted = lifecycle.ProcessStore(store.root)
    assert restarted.catalog()[0]["process_id"] == process
    assert (
        restarted.inspect(teaching["attempt_id"])["teaching"]["steps"][0][
            "decision_reason"
        ]
        == saved["steps"][0]["decision_reason"]
    )

    failed = restarted.begin(process, "test", host())
    run = run_fixture(failed, host(), fail=True)
    assert run["result"] == "failed"
    evidence = restarted.inspect(failed["attempt_id"])["evidence"]
    assert evidence["receipt_sha256"]
    assert evidence["elapsed_ms"] >= 0
    assert evidence["measurements"]["input_tokens"]["value"] is None
    assert evidence["measurements"]["input_tokens"]["missing_reason"]
    prepared = restarted.prepare_feedback(
        failed["attempt_id"], development(), problem=problem()
    )
    service = Service()
    service.fail_once = True
    options = dict(
        approval_id="synthetic exact-content transmission consent",
        expected_sha256=prepared["review_sha256"],
        transmission_authorized=True,
        client_options={"opener": service, "base_url": "http://localhost:8080"},
    )
    with pytest.raises(RuntimeError, match="Could not reach"):
        restarted.submit_feedback(prepared["feedback_id"], VERA, **options)
    receipt = lifecycle.ProcessStore(store.root).submit_feedback(
        prepared["feedback_id"], VERA, **options
    )
    assert receipt["change_request_id"] == "CR-847"
    assert receipt["zip_uploaded"] is False
    assert service.requests[0]["submission_id"] == service.requests[1]["submission_id"]
    assert service.requests[1]["request"]["diagnostics"]["occurred_at"] is None
    assert process in service.requests[1]["request"]["diagnostics"]["correlation_ids"]
    wire = json.dumps(service.requests)
    assert "private-session-url" not in wire
    assert "synthetic-token-kept-local" not in json.dumps(receipt)
    assert str(store.root) not in wire
    assert "Browser execution" in wire
    assert "CR-847" in Path(failed["report_path"]).read_text()
    assert (
        restarted.submit_feedback(prepared["feedback_id"], VERA, **options) == receipt
    )
    assert len(service.requests) == 2

    with ZipFile(receipt["archive_path"]) as archive:
        assert "cr-request.json" in archive.namelist()
        assert "run/outputs.json" not in archive.namelist()
    developer = lifecycle.ProcessStore(tmp_path / "developer-data")
    imported = developer.import_feedback(Path(receipt["archive_path"]))
    assert imported["process_id"] == process

    capability = json.loads(FIXTURE.read_text())
    capability["version"] = "0.1.1"
    revised = tmp_path / "revised.json"
    revised.write_text(json.dumps(capability))
    restarted.add_version(process, revised, release(["CR-847"]))
    retry = lifecycle.ProcessStore(store.root).begin(process, "test", host())
    completed = run_fixture(retry, host())
    assert completed["result"] == "passed"
    assert completed["summary"]["outputs"][0]["record_count"] == 2
    assert restarted.inspect(retry["attempt_id"])["plan"]["implementation"]["release"][
        "cr_ids"
    ] == ["CR-847"]
    assert "test simulati" in Path(completed["report_path"]).read_text()


def test_two_simulated_runs_and_correct_reviews_cannot_qualify_real_use(
    lifecycle, tmp_path
):
    store, process = registered(lifecycle, tmp_path)
    attempts = [
        store.begin(process, "test", host()),
        store.begin(process, "test", host()),
    ]
    for attempt in attempts:
        run_fixture(attempt, host())
        store.review_result(
            attempt["attempt_id"],
            {
                "correct": True,
                "reviewer": "model",
                "evidence": "Exact two fixture records match expected values",
            },
        )
    with pytest.raises(ValueError, match="not live"):
        store.qualify(process, [a["attempt_id"] for a in attempts], 30_000)
    use = lifecycle.ProcessStore(store.root).begin(
        process, "use", host("live_connected_chrome")
    )
    assert use["blocked_reason"] == "qualification_required"


@pytest.mark.parametrize(
    "case,expected",
    [
        ("no_tools", "host_capabilities_unavailable"),
        ("changed_host", "host_changed_since_preparation"),
        ("missing_inputs", "executor_failed"),
    ],
)
def test_pre_receipt_failures_always_have_persistent_useful_reports(
    lifecycle, tmp_path, case, expected
):
    store, process = registered(lifecycle, tmp_path)
    current_host = host(browser_control=case != "no_tools")
    attempt = store.begin(process, "test", current_host)
    runtime_host = host(locale="it") if case == "changed_host" else current_host
    result = run_fixture(
        attempt,
        runtime_host,
        inputs={} if case == "missing_inputs" else {"query": "x", "max-results": 2},
    )
    assert result["missing_reason"] == expected
    assert store.inspect(attempt["attempt_id"])["evidence"]["receipt_sha256"] is None
    assert expected in Path(result["report_path"]).read_text()


def test_pending_attempt_is_discoverable_without_old_chat_or_path(lifecycle, tmp_path):
    monkey_root = tmp_path / "stable"
    store = lifecycle.ProcessStore(monkey_root)
    process = store.create(description())["process_id"]
    attempt = store.begin(process, "teaching", host(browser_control=False))
    catalog = lifecycle.ProcessStore(monkey_root).catalog()
    assert catalog[0]["attempts"][0]["attempt_id"] == attempt["attempt_id"]
    assert catalog[0]["attempts"][0]["result"] == "unfinished"
    assert Path(attempt["report_path"]).is_file()


def test_process_boundary_version_identity_and_receipt_integrity_fail_closed(
    lifecycle, tmp_path
):
    store, process = registered(lifecycle, tmp_path)
    with pytest.raises(ValueError, match="exact site"):
        store.create({"site": "Agenzia"})
    changed = json.loads(FIXTURE.read_text())
    changed["version"] = "0.1.1"
    changed["process"]["objective"] = "Another professional process"
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="different professional process"):
        store.add_version(process, path, release())
    teaching = store.begin(process, "teaching", host())
    wrong = checkpoint()
    wrong["objective"] = "Post invoices instead of searching"
    with pytest.raises(ValueError, match="different process"):
        store.teach(teaching["attempt_id"], wrong, 0)
    attempt = store.begin(process, "test", host())
    run_fixture(attempt, host())
    outputs = Path(attempt["attempt_directory"]) / "run/outputs.json"
    outputs.write_text("{}")
    assert store.inspect(attempt["attempt_id"])["evidence"]["result"] == "unverified"
    prepared = store.prepare_feedback(
        attempt["attempt_id"], development(), problem=problem()
    )
    assert (
        "saved_evidence_invalid_or_unavailable"
        in (Path(prepared["directory"]) / "cr-request.json").read_text()
    )


def test_transmission_requires_exact_review_and_retains_unsent_request(
    lifecycle, tmp_path
):
    store, process = registered(lifecycle, tmp_path)
    attempt = store.begin(process, "teaching", host())
    prepared = store.prepare_feedback(attempt["attempt_id"], development())
    with pytest.raises(ValueError, match="authorization"):
        store.submit_feedback(
            prepared["feedback_id"],
            VERA,
            approval_id="not consent",
            expected_sha256=prepared["review_sha256"],
            transmission_authorized=False,
        )
    assert Path(prepared["review_path"]).is_file()
    assert store.resume(process)["cr_ids"] == []


def test_default_store_is_stable_and_private(lifecycle, monkeypatch, tmp_path):
    monkeypatch.setenv("MPARANZA_BROWSER_DATA", str(tmp_path / "configured"))
    first = lifecycle.ProcessStore()
    process = first.create(description())
    assert lifecycle.ProcessStore().create(description()) == process
    if os.name != "nt":
        assert first.database.stat().st_mode & 0o777 == 0o600
        assert first.root.stat().st_mode & 0o777 == 0o700


def reviewed_live_schema_pair(store, process):
    """Create synthetic live-schema contract doubles; never actual live evidence.

    The separate simulation test proves that production admission rejects the
    simulated enum. These doubles exercise the positive branch of that contract.
    They stay only in pytest's temporary directory and must never be distributed.
    """
    current_host = host("live_connected_chrome")
    attempts = [
        store.begin(process, "test", current_host),
        store.begin(process, "test", current_host),
    ]
    for attempt in attempts:
        run_fixture(attempt, current_host)
        store.review_result(
            attempt["attempt_id"],
            {
                "correct": True,
                "reviewer": "model",
                "evidence": "SYNTHETIC TEST DOUBLE: exact two fixture records match the expected values",
            },
        )
    return attempts


def test_qualification_fresh_context_ordinary_use_and_regression_loop_contract(
    lifecycle, tmp_path
):
    store, process = registered(lifecycle, tmp_path)
    attempts = reviewed_live_schema_pair(store, process)
    qualification = store.qualify(process, [a["attempt_id"] for a in attempts], 30_000)
    assert (
        json.loads(Path(qualification["capability_path"]).read_text())["status"]
        == "validated_local"
    )
    # A new process has neither the old conversation nor Python module state.
    cli = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "process_lifecycle.py"),
            "--root",
            str(store.root),
            "catalog",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    recovered = json.loads(cli.stderr)
    assert recovered[0]["available_in_qualified_environment"] is True
    assert recovered[0]["inputs"][0]["purpose"] == "Synthetic search expression."
    fresh = lifecycle.ProcessStore(store.root)
    use = fresh.begin(process, "use", host("live_connected_chrome"))
    assert use["blocked_reason"] is None
    executed = run_fixture(use, host("live_connected_chrome"))
    assert executed["result"] == "passed"
    fresh.review_result(
        use["attempt_id"],
        {
            "correct": True,
            "reviewer": "model",
            "evidence": "SYNTHETIC TEST DOUBLE: exact records checked",
        },
    )
    regression = fresh.begin(process, "use", host("live_connected_chrome"))
    assert (
        run_fixture(regression, host("live_connected_chrome"), fail=True)["result"]
        == "failed"
    )
    feedback = fresh.prepare_feedback(
        regression["attempt_id"], development(), problem=problem()
    )
    service = Service()
    receipt = fresh.submit_feedback(
        feedback["feedback_id"],
        VERA,
        approval_id="synthetic reviewed regression submission",
        expected_sha256=feedback["review_sha256"],
        transmission_authorized=True,
        client_options={"opener": service},
    )
    assert receipt["process_id"] == process
    assert receipt["change_request_id"] == "CR-847"
    blocked = lifecycle.ProcessStore(store.root).begin(
        process, "use", host("live_connected_chrome")
    )
    assert blocked["blocked_reason"] == "qualification_required"
    assert "CR-847" in Path(regression["report_path"]).read_text()


@pytest.mark.parametrize(
    "case", ["missing_review", "incorrect", "slow", "different_host", "duplicate"]
)
def test_qualification_rejects_incomplete_evidence_and_unaccepted_performance(
    lifecycle, tmp_path, case
):
    store, process = registered(lifecycle, tmp_path)
    attempts = reviewed_live_schema_pair(store, process)
    selected = [a["attempt_id"] for a in attempts]
    bound = 30_000
    if case == "incorrect":
        store.review_result(
            selected[0],
            {
                "correct": False,
                "reviewer": "operator",
                "evidence": "One synthetic field is incorrect",
            },
        )
    elif case == "slow":
        bound = 0.000001
    elif case == "different_host":
        third = store.begin(process, "test", host("live_connected_chrome", locale="it"))
        run_fixture(third, host("live_connected_chrome", locale="it"))
        selected[1] = third["attempt_id"]
    elif case == "duplicate":
        selected[1] = selected[0]
    else:
        third = store.begin(process, "test", host("live_connected_chrome"))
        run_fixture(third, host("live_connected_chrome"))
        selected[1] = third["attempt_id"]
    with pytest.raises(ValueError):
        store.qualify(process, selected, bound)


def test_new_contract_and_changed_result_review_suspend_qualification(
    lifecycle, tmp_path
):
    store, process = registered(lifecycle, tmp_path)
    attempts = reviewed_live_schema_pair(store, process)
    store.qualify(process, [a["attempt_id"] for a in attempts], 30_000)
    store.review_result(
        attempts[0]["attempt_id"],
        {
            "correct": False,
            "reviewer": "operator",
            "evidence": "The expected result was interpreted incorrectly",
        },
    )
    assert store.catalog()[0]["available_in_qualified_environment"] is False
    revised = json.loads(FIXTURE.read_text())
    revised["version"] = "0.1.1"
    path = tmp_path / "revision.json"
    path.write_text(json.dumps(revised))
    store.add_version(process, path, release())
    assert (
        store.begin(process, "use", host("live_connected_chrome"))["blocked_reason"]
        == "qualification_required"
    )


def test_runtime_refuses_reexecuting_same_attempt(lifecycle, tmp_path):
    store, process = registered(lifecycle, tmp_path)
    attempt = store.begin(process, "test", host())
    run_fixture(attempt, host())
    with pytest.raises(subprocess.CalledProcessError):
        run_fixture(attempt, host())
    assert store.inspect(attempt["attempt_id"])["evidence"]["result"] == "passed"


def test_retry_after_installed_version_changes_uses_original_submission(
    lifecycle, tmp_path
):
    store, process = registered(lifecycle, tmp_path)
    attempt = store.begin(process, "teaching", host())
    prepared = store.prepare_feedback(
        attempt["attempt_id"], development(), problem=problem()
    )
    plugin = tmp_path / "vera"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / "scripts").mkdir()
    manifest = plugin / ".codex-plugin/plugin.json"
    manifest.write_text(json.dumps({"name": "vera", "version": "0.1.0"}))
    (plugin / "scripts/change_requests.py").write_bytes(
        (VERA / "scripts/change_requests.py").read_bytes()
    )
    service = Service()
    service.fail_once = True
    options = dict(
        approval_id="synthetic unchanged reviewed contents",
        expected_sha256=prepared["review_sha256"],
        transmission_authorized=True,
        client_options={"opener": service},
    )
    with pytest.raises(RuntimeError):
        store.submit_feedback(prepared["feedback_id"], plugin, **options)
    manifest.write_text(json.dumps({"name": "vera", "version": "0.1.1"}))
    receipt = lifecycle.ProcessStore(store.root).submit_feedback(
        prepared["feedback_id"], plugin, **options
    )
    assert receipt["change_request_id"] == "CR-847"
    assert service.requests[0] == service.requests[1]


def test_installed_release_recovery_keeps_identity_without_importing_qualification(
    lifecycle, tmp_path
):
    source, process = registered(lifecycle, tmp_path)
    source.begin(process, "teaching", host())
    module = tmp_path / "installed-module"
    folder = module / "capabilities/synthetic-record-search"
    folder.mkdir(parents=True)
    (folder / "capability.json").write_bytes(FIXTURE.read_bytes())
    source.export_binding(process, folder / "process.json")
    receiver = lifecycle.ProcessStore(tmp_path / "receiver")

    imported = receiver.sync_installed(module)

    assert imported[0]["process_id"] == process
    assert receiver.catalog()[0]["qualification"] is None
    assert receiver.catalog()[0]["installed_lineage"][0]["source_attempt_ids"]
    assert receiver.sync_installed(module) == imported
    source.record_release(
        process,
        "0.1.0",
        {
            **release(),
            "status": "published",
            "evidence": "SYNTHETIC publication fixture; no actual Marketplace operation",
        },
    )
    (folder / "process.json").unlink()
    source.export_binding(process, folder / "process.json")
    receiver.sync_installed(module)
    assert (
        receiver.catalog()[0]["release_history"][-1]["release"]["status"] == "published"
    )
    assert receiver.catalog()[0]["available_in_qualified_environment"] is False


def test_real_status_response_links_fix_version_and_does_not_qualify(
    lifecycle, tmp_path
):
    store, process = registered(lifecycle, tmp_path)
    attempt = store.begin(process, "teaching", host())
    prepared = store.prepare_feedback(attempt["attempt_id"], development())
    store.submit_feedback(
        prepared["feedback_id"],
        VERA,
        approval_id="synthetic reviewed consent",
        expected_sha256=prepared["review_sha256"],
        transmission_authorized=True,
        client_options={"opener": Service()},
    )
    sent = []

    def status_service(request, **_kwargs):
        sent.append(json.loads(request.data))
        return Response(
            {
                "requests": [
                    {
                        "change_request_id": "CR-847",
                        "found": True,
                        "status": "fixed",
                        "disposition": "fixed",
                        "revision": 2,
                        "needs_info_question": None,
                        "fixed": True,
                        "fixed_version": "0.1.300",
                        "install_url": None,
                    }
                ]
            }
        )

    status = store.refresh_status(process, VERA, opener=status_service)

    assert sent[0]["requests"][0]["change_request_id"] == "CR-847"
    assert status[0]["fixed_version"] == "0.1.300"
    assert "status_token" not in json.dumps(status)
    recovered = lifecycle.ProcessStore(store.root).resume(process)
    assert recovered["cr_status"][0]["fixed"] is True
    assert recovered["qualification"] is None


def test_cli_materializes_teaching_reports_handoff_and_installed_catalog(
    lifecycle, tmp_path, monkeypatch, caplog
):
    """Exercise the commands that the user-facing instructions actually prescribe."""
    caplog.set_level("INFO")
    data = tmp_path / "cli-data"
    input_path = tmp_path / "cli-input.json"

    def cli(command, payload=None, *arguments):
        args = ["--root", str(data), command, *arguments]
        if payload is not None:
            input_path.write_text(json.dumps(payload))
            args += ["--input", str(input_path)]
        assert lifecycle.main(args) == 0
        return json.loads(caplog.records[-1].message)

    created = cli("create", description())
    process = created["process_id"]
    registered_version = cli(
        "version", release(), "--process", process, "--capability", str(FIXTURE)
    )
    assert registered_version["version"] == "0.1.0"
    attempt = cli("begin", host(), "--process", process, "--kind", "teaching")
    cli("teach", checkpoint(), "--attempt", attempt["attempt_id"])
    assert (
        cli("inspect", None, "--attempt", attempt["attempt_id"])["teaching"]["revision"]
        == 1
    )
    assert Path(cli("report", None, "--attempt", attempt["attempt_id"])).is_file()
    cli(
        "review",
        {"correct": False, "reviewer": "model", "evidence": "No executable result yet"},
        "--attempt",
        attempt["attempt_id"],
    )
    assert cli("resume", None, "--process", process)["process_id"] == process
    feedback = cli(
        "prepare-feedback",
        {"request": development()},
        "--attempt",
        attempt["attempt_id"],
    )
    client = lifecycle._cr_client(VERA)
    actual_submit = client.submit_suggestion
    monkeypatch.setattr(
        client,
        "submit_suggestion",
        lambda *args, **kwargs: actual_submit(*args, opener=Service(), **kwargs),
    )
    monkeypatch.setattr(lifecycle, "_cr_client", lambda _root: client)
    submission = cli(
        "submit-feedback",
        {
            "feedback_id": feedback["feedback_id"],
            "review_sha256": feedback["review_sha256"],
            "approval_id": "synthetic CLI content consent",
            "transmission_authorized": True,
        },
        "--vera-root",
        str(VERA),
    )
    assert (
        cli("import-feedback", None, "--input", submission["archive_path"])[
            "process_id"
        ]
        == process
    )
    cli(
        "record-release",
        {"version": "0.1.0", "release": release(["CR-847"])},
        "--process",
        process,
    )
    module = tmp_path / "cli-module"
    folder = module / "capabilities/synthetic-record-search"
    folder.mkdir(parents=True)
    (folder / "capability.json").write_bytes(FIXTURE.read_bytes())
    assert Path(
        cli(
            "export-binding",
            None,
            "--process",
            process,
            "--output",
            str(folder / "process.json"),
        )
    ).is_file()
    assert (
        cli("sync-installed", None, "--module-root", str(module))[0]["process_id"]
        == process
    )
    assert cli("catalog")[0]["cr_ids"] == ["CR-847"]
    assert lifecycle.main(["--root", str(data), "resume", "--process", "missing"]) == 1


@pytest.mark.parametrize("mode", ["unknown", "no_files", "no_implementation"])
def test_unavailable_host_or_implementation_preserves_attempt_and_feedback(
    lifecycle, tmp_path, mode
):
    store = lifecycle.ProcessStore(tmp_path / "new-process")
    process = store.create(description())["process_id"]
    if mode != "no_implementation":
        store.add_version(process, FIXTURE, release())
    current_host = host("unverified", local_files=mode != "no_files")
    attempt = store.begin(process, "use", current_host)
    assert attempt["blocked_reason"] in {
        "qualification_required",
        "host_capabilities_unavailable",
        "implementation_unavailable",
    }
    assert Path(attempt["report_path"]).is_file()
    assert store.prepare_feedback(attempt["attempt_id"], development())["sent"] is False


def test_user_visible_routes_and_reports_never_require_technical_user_inputs():
    lifecycle_reference = (
        SCRIPTS.parent / "references/process-lifecycle.md"
    ).read_text()
    ordinary_reference = (SCRIPTS.parent / "references/ordinary-use.md").read_text()
    skill = (SCRIPTS.parent / "skills/browser-automation/SKILL.md").read_text()
    wrapper = (VERA / "skills/browser-automation/SKILL.md").read_text()
    assert "references/ordinary-use.md" in skill
    assert "references/process-lifecycle.md" in wrapper
    assert "accountant never writes automation rules" in lifecycle_reference
    assert "current model" in ordinary_reference
    assert "never ask the operator to resume an old chat" in ordinary_reference
    assert "zip_uploaded: false" in lifecycle_reference
    assert "missing_reasons" in lifecycle_reference
    assert "Load exactly one explicitly named" not in skill


def test_available_host_measurements_remain_in_the_readable_report(lifecycle, tmp_path):
    store, process = registered(lifecycle, tmp_path)
    attempt = store.begin(process, "test", host())
    run_fixture(
        attempt,
        host(),
        hostMeasurements={
            "input_tokens": {
                "value": 23,
                "source": "synthetic host usage fixture scoped to this attempt",
                "missing_reason": None,
            }
        },
    )

    report = store.report(attempt["attempt_id"]).read_text()

    assert "input_tokens: 23" in report
    assert "synthetic host usage fixture scoped to this attempt" in report
    assert "host_does_not_expose_measurement" in report
    assert (
        f"[Output locali]({Path(attempt['attempt_directory']) / 'run' / 'outputs.json'})"
        in report
    )
    assert "[Ricevuta locale]" in report


def test_tutorial_feedback_cannot_leave_its_local_directory(lifecycle, tmp_path):
    store, process = registered(lifecycle, tmp_path)
    attempt = store.begin(process, "teaching", host())
    prepared = store.prepare_feedback(attempt["attempt_id"], development())
    (store.root.parent / ".vera-onboarding-local-only").touch()

    with pytest.raises(ValueError, match="tutorial feedback must remain local"):
        store.submit_feedback(
            prepared["feedback_id"],
            VERA,
            approval_id="Synthetic authorization cannot release tutorial data",
            expected_sha256=prepared["review_sha256"],
            transmission_authorized=True,
        )

    assert store.resume(process)["cr_ids"] == []
