"""Keep committed Archive work and independent reporting recovery distinguishable."""

from __future__ import annotations

import errno
import json
import re
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
)

__all__: list[str] = []


def _start(core, case):
    prepared = core.prepare_studio_client_workflow(
        case.engagement_id,
        "journal-bank-reconciliation",
        input_ids=[case.imported["input_id"]],
        new_run=True,
        state_dir=case.state_dir,
    )
    core.start_studio_client_workflow(
        case.client_id,
        case.engagement_id,
        prepared["run"]["run_id"],
        state_dir=case.state_dir,
    )
    return core.ledger.load_run(
        case.client_root, case.engagement_id, prepared["run"]["run_id"]
    )


def _ready(core, case, loaded):
    output = Path(loaded["output_dir"])
    (output / "result.txt").write_bytes(b"Preserved professional result\n")
    core.finalize_studio_client_workflow(
        case.client_id,
        case.engagement_id,
        loaded["run"]["run_id"],
        [
            {
                "artifact_id": "result",
                "path": "result.txt",
                "purpose": "Result",
                "audience": "review",
                "media_type": "text/plain",
            }
        ],
        state_dir=case.state_dir,
    )


def _terminate(core, case, loaded, outcome):
    operation = {
        "failed": core.fail_studio_client_workflow,
        "cancelled": core.cancel_studio_client_workflow,
        "completed": core.complete_studio_client_workflow,
    }[outcome]
    kwargs = {"state_dir": case.state_dir}
    if outcome == "failed":
        kwargs["reason"] = "Synthetic interrupted work"
    return operation(
        case.client_id, case.engagement_id, loaded["run"]["run_id"], **kwargs
    )


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "completed"])
def test_delivery_instruction_reads_the_actual_terminal_response(
    archive_core, client_case, outcome
):
    loaded = _start(archive_core, client_case)
    _ready(archive_core, client_case, loaded)
    instruction = (
        Path(__file__).resolve().parents[2]
        / "plugins/vera/skills/vera/references/selective-reporting.md"
    ).read_text(encoding="utf-8")
    field = re.search(r"include the returned\s+`([\w.]+)`", instruction)
    assert field is not None

    result = _terminate(archive_core, client_case, loaded, outcome)

    namespace, field_name = field[1].split(".")
    delivered = result[namespace][field_name]
    saved = (Path(loaded["output_dir"]) / "model_data_report.md").read_text(
        encoding="utf-8"
    )
    assert delivered == saved
    assert loaded["run"]["run_id"] in delivered


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "completed"])
def test_local_report_failure_returns_committed_status_and_remains_recoverable(
    archive_core, client_case, monkeypatch, outcome
):
    import archive_reporting
    from archive_report_store import Registry

    loaded = _start(archive_core, client_case)
    _ready(archive_core, client_case, loaded)
    report = Path(loaded["output_dir"]) / "model_data_report.json"
    retained = report.read_bytes()

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic report write failure")

    monkeypatch.setattr(archive_reporting, "snapshot_run", unavailable)

    result = _terminate(archive_core, client_case, loaded, outcome)

    assert result["status"] == outcome
    assert result["reporting"]["status"] == "unavailable"
    assert result["reporting"]["run_status_saved"] is True
    assert result["reporting"]["retry_pending"] is True
    assert report.read_bytes() == retained
    assert Registry().terminal_runs() == [Path(loaded["run_root"])]
    assert (
        json.loads((Path(loaded["run_root"]) / "run.json").read_text())["status"]
        == outcome
    )


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "completed"])
@pytest.mark.parametrize("failure_stage", ["snapshot_run", "reseal"])
def test_repeating_terminal_call_recovers_report_without_repeating_work(
    archive_core, client_case, monkeypatch, outcome, failure_stage
):
    import archive_report_seal
    import archive_reporting
    from archive_report_store import Registry

    loaded = _start(archive_core, client_case)
    _ready(archive_core, client_case, loaded)
    output = Path(loaded["output_dir"])
    professional = (output / "result.txt").read_bytes()
    source = Path(client_case.imported["imported_path"])
    source_bytes = source.read_bytes()
    module = (
        archive_reporting if failure_stage == "snapshot_run" else archive_report_seal
    )

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic interrupted reporting write")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(module, failure_stage, unavailable)
        _terminate(archive_core, client_case, loaded, outcome)
    history = json.loads((Path(loaded["run_root"]) / "run.json").read_text())[
        "status_history"
    ]

    result = _terminate(archive_core, client_case, loaded, outcome)

    assert result["status"] == outcome
    assert result["reporting"]["status"] == "available"
    report = json.loads((output / "model_data_report.json").read_text())
    assert report["outcome"] == outcome
    assert report["collection_closed"] is True
    assert report["report_revision"] == 1
    assert (output / "result.txt").read_bytes() == professional
    assert source.read_bytes() == source_bytes
    assert (
        json.loads((Path(loaded["run_root"]) / "run.json").read_text())[
            "status_history"
        ]
        == history
    )
    assert Registry().terminal_runs() == []
    archive_core.ledger.validate_run_artifacts(
        client_case.client_root, client_case.engagement_id, loaded["run"]["run_id"]
    )


def test_interrupted_markdown_write_recovers_same_report_without_recalculation(
    archive_core, client_case, monkeypatch
):
    import archive_report_store

    loaded = _start(archive_core, client_case)
    _ready(archive_core, client_case, loaded)
    output = Path(loaded["output_dir"])
    old_markdown = (output / "model_data_report.md").read_bytes()
    professional = (output / "result.txt").read_bytes()
    original = archive_report_store.atomic_bytes

    def unavailable(path, content):
        if path.name == "model_data_report.md":
            raise OSError("Synthetic failure after report JSON was saved")
        return original(path, content)

    with monkeypatch.context() as interrupted:
        interrupted.setattr(archive_report_store, "atomic_bytes", unavailable)
        pending = _terminate(archive_core, client_case, loaded, "completed")
    frozen_json = (output / "model_data_report.json").read_bytes()
    assert pending["status"] == "completed"
    assert pending["reporting"]["status"] == "unavailable"
    assert json.loads(frozen_json)["outcome"] == "completed"
    assert (output / "model_data_report.md").read_bytes() == old_markdown

    result = _terminate(archive_core, client_case, loaded, "completed")

    assert result["reporting"]["status"] == "available"
    assert (output / "model_data_report.json").read_bytes() == frozen_json
    assert (output / "result.txt").read_bytes() == professional
    assert result["reporting"]["display_markdown"] == (
        output / "model_data_report.md"
    ).read_text(encoding="utf-8")
    archive_core.ledger.validate_run_artifacts(
        client_case.client_root, client_case.engagement_id, loaded["run"]["run_id"]
    )


def test_failed_terminal_recovery_does_not_skip_healthy_sibling_or_receipts(
    archive_core, client_case, monkeypatch
):
    import archive_report_receipt
    import archive_reporting
    from archive_report_store import Registry

    broken = _start(archive_core, client_case)
    healthy = _start(archive_core, client_case)

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic interrupted reporting write")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(archive_reporting, "snapshot_run", unavailable)
        _terminate(archive_core, client_case, broken, "failed")
        _terminate(archive_core, client_case, healthy, "failed")
    original = archive_reporting.snapshot_run

    def broken_only(loaded):
        if loaded["run"]["run_id"] == broken["run"]["run_id"]:
            raise OSError("Synthetic retained broken report")
        return original(loaded)

    monkeypatch.setattr(archive_reporting, "snapshot_run", broken_only)
    retries = []
    monkeypatch.setattr(
        archive_report_receipt,
        "retry_pending",
        lambda *args, **kwargs: retries.append(True),
    )

    archive_core.ledger.retry_reporting(client_case.client_root)

    assert Registry().terminal_runs() == [Path(broken["run_root"])]
    assert (
        json.loads(
            (Path(healthy["output_dir"]) / "model_data_report.json").read_text()
        )["outcome"]
        == "failed"
    )
    assert retries == [True]


def test_failed_recovery_batch_yields_to_later_pending_runs(
    archive_core, client_case, monkeypatch
):
    import archive_reporting
    from archive_report_store import Registry

    runs = [_start(archive_core, client_case) for _ in range(4)]

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic reporting failure")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(archive_reporting, "snapshot_run", unavailable)
        for loaded in runs:
            _terminate(archive_core, client_case, loaded, "failed")
    # Fix the batch order explicitly; prior ordinary operations can rotate it.
    registry = Registry()
    with registry.transaction() as connection:
        connection.execute("DELETE FROM recovery_attempts")
    first_batch = registry.terminal_runs()
    last_root = Path(runs[-1]["run_root"])
    original = archive_reporting.snapshot_run

    def first_batch_broken(loaded):
        if Path(loaded["run_root"]) in first_batch:
            raise OSError("Synthetic retained failure")
        return original(loaded)

    monkeypatch.setattr(archive_reporting, "snapshot_run", first_batch_broken)
    archive_core.ledger.retry_reporting(client_case.client_root)

    archive_core.ledger.retry_reporting(client_case.client_root)

    assert last_root not in registry.terminal_runs()
    assert (
        json.loads((last_root / "outputs/model_data_report.json").read_text())[
            "outcome"
        ]
        == "failed"
    )


def test_changed_professional_output_still_prevents_completion(
    archive_core, client_case
):
    loaded = _start(archive_core, client_case)
    _ready(archive_core, client_case, loaded)
    (Path(loaded["output_dir"]) / "result.txt").write_bytes(b"Changed after sealing")

    with pytest.raises(archive_core.ArchiveError):
        _terminate(archive_core, client_case, loaded, "completed")

    assert (
        json.loads((Path(loaded["run_root"]) / "run.json").read_text())["status"]
        == "ready_for_review"
    )


def test_unreadable_transition_metadata_does_not_hide_other_pending_runs(
    tmp_path, monkeypatch
):
    from archive_report_store import Registry

    registry = Registry(tmp_path / "queue")
    broken = tmp_path / "broken"
    healthy = tmp_path / "healthy"
    broken.mkdir()
    healthy.mkdir()
    (broken / "run.json").write_text('{"status":"failed"}')
    (healthy / "run.json").write_text('{"status":"failed"}')
    registry.register("broken", broken)
    registry.register("healthy", healthy)
    original = Path.lstat

    def unavailable(path, *args, **kwargs):
        if path == broken / "run.json":
            raise PermissionError(errno.EACCES, "Synthetic unavailable metadata")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", unavailable)

    pending = registry.terminal_runs()

    assert pending == [healthy]


def test_other_clients_do_not_consume_selected_clients_recovery_batch(tmp_path):
    from archive_report_store import Registry

    registry = Registry(tmp_path / "queue")
    foreign = tmp_path / "Other client/Vera/engagements/eng_a/runs"
    selected = tmp_path / "Selected client"
    for number in range(3):
        root = foreign / f"run_{number}"
        root.mkdir(parents=True)
        (root / "run.json").write_text('{"status":"failed"}')
        registry.register(f"foreign-{number}", root)
    root = selected / "Vera/engagements/eng_b/runs/run_selected"
    root.mkdir(parents=True)
    (root / "run.json").write_text('{"status":"failed"}')
    registry.register("selected", root)

    pending = registry.terminal_runs(client_root=selected)

    assert pending == [root]


@pytest.mark.parametrize("outcome", ["failed", "cancelled"])
@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_terminal_failure_retains_report_when_execution_input_is_unavailable(
    archive_core, client_case, outcome, damage
):
    loaded = _start(archive_core, client_case)
    selected = Path(loaded["context"]["input_bindings"][0]["path"])
    original = Path(client_case.imported["imported_path"]).read_bytes()
    if damage == "missing":
        selected.unlink()
    else:
        selected.write_bytes(b"Changed execution copy\n")

    result = _terminate(archive_core, client_case, loaded, outcome)

    assert result["status"] == outcome
    assert result["reporting"]["status"] == "available"
    report = json.loads(
        (Path(loaded["output_dir"]) / "model_data_report.json").read_text()
    )
    assert report["outcome"] == outcome
    assert report["collection_closed"] is True
    assert report["run_id"] == loaded["run"]["run_id"]
    assert Path(client_case.imported["imported_path"]).read_bytes() == original
    recovered = archive_core.ledger.load_run(
        client_case.client_root, client_case.engagement_id, loaded["run"]["run_id"]
    )
    assert recovered["run"]["status"] == outcome
    assert selected.read_bytes() == original


def test_selected_read_does_not_recover_an_unrelated_pending_report(
    archive_core, client_case, monkeypatch
):
    import archive_reporting

    unrelated = _start(archive_core, client_case)
    selected = _start(archive_core, client_case)

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic interrupted report")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(archive_reporting, "snapshot_run", unavailable)
        _terminate(archive_core, client_case, unrelated, "failed")
    attempts = []
    original = archive_reporting.finish_run

    def observed(loaded):
        attempts.append(loaded["run"]["run_id"])
        return original(loaded)

    monkeypatch.setattr(archive_reporting, "finish_run", observed)

    result = archive_core.read_studio_run_artifact(
        client_case.client_id,
        client_case.engagement_id,
        selected["run"]["run_id"],
        selected["context"]["input_bindings"][0]["path"],
        state_dir=client_case.state_dir,
    )

    assert result["data"]
    assert attempts == []


def test_selected_read_does_not_retry_a_siblings_pending_server_receipt(
    archive_core, client_case, monkeypatch
):
    import archive_report_receipt

    sibling = _start(archive_core, client_case)
    selected = _start(archive_core, client_case)
    attempts = []

    def pending(path):
        attempts.append(path)
        return {"status": "pending", "reason": "Synthetic offline server"}

    monkeypatch.setattr(archive_report_receipt, "stamp_report", pending)
    _terminate(archive_core, client_case, sibling, "failed")
    attempts.clear()

    result = archive_core.read_studio_run_artifact(
        client_case.client_id,
        client_case.engagement_id,
        selected["run"]["run_id"],
        selected["context"]["input_bindings"][0]["path"],
        state_dir=client_case.state_dir,
    )

    assert result["data"]
    assert attempts == []


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_sealed_result_can_complete_without_reopening_input_admission(
    archive_core, client_case, damage
):
    loaded = _start(archive_core, client_case)
    _ready(archive_core, client_case, loaded)
    source = Path(loaded["context"]["input_bindings"][0]["path"])
    reference = json.loads(
        (Path(loaded["run_root"]) / "work-recovery.json").read_text()
    )
    import shutil

    shutil.rmtree(reference["store"])
    if damage == "missing":
        source.unlink()
    else:
        source.write_bytes(b"Altered input")

    result = _terminate(archive_core, client_case, loaded, "completed")

    assert result["status"] == "completed"

    assert (
        json.loads((Path(loaded["run_root"]) / "run.json").read_text())["status"]
        == "completed"
    )


def test_terminal_report_retry_survives_later_missing_input(
    archive_core, client_case, monkeypatch
):
    import archive_reporting

    loaded = _start(archive_core, client_case)

    def unavailable(*args, **kwargs):
        raise OSError("Interrupted report write")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(archive_reporting, "snapshot_run", unavailable)
        _terminate(archive_core, client_case, loaded, "failed")
    Path(loaded["context"]["input_bindings"][0]["path"]).unlink()

    archive_core.ledger.retry_reporting(
        client_case.client_root,
        engagement_id=client_case.engagement_id,
        run_id=loaded["run"]["run_id"],
    )

    report = json.loads(
        (Path(loaded["output_dir"]) / "model_data_report.json").read_text()
    )
    assert report["outcome"] == "failed"
    assert report["collection_closed"] is True


def test_recovery_selector_does_not_follow_run_id_into_another_engagement(
    archive_core, client_case, monkeypatch
):
    import archive_reporting

    loaded = _start(archive_core, client_case)

    def unavailable(*args, **kwargs):
        raise OSError("Interrupted report write")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(archive_reporting, "snapshot_run", unavailable)
        _terminate(archive_core, client_case, loaded, "failed")
    before = (Path(loaded["output_dir"]) / "model_data_report.json").read_bytes()
    other = archive_core.create_studio_client_engagement(
        client_case.client_id, "Independent engagement", state_dir=client_case.state_dir
    )["engagement"]["engagement_id"]

    archive_core.ledger.retry_reporting(
        client_case.client_root, engagement_id=other, run_id=loaded["run"]["run_id"]
    )

    assert (
        Path(loaded["output_dir"]) / "model_data_report.json"
    ).read_bytes() == before
