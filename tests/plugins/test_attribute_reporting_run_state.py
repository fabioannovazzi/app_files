from __future__ import annotations

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "plugins" / "attribute-reporting" / "scripts" / "run_state.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "attribute_reporting_run_state_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_state = _load_module()


def _initialize(tmp_path: Path) -> Path:
    run_dir = tmp_path / "attribute-run"
    result = run_state.initialize_run(
        run_dir,
        retailer="example-retailer",
        category="cashmere",
        author_agent_id="author-agent",
        server_origin="https://mparanza.com/",
    )
    assert result["next_stage"] == "server_snapshot"
    return run_dir


def _write_artifact(run_dir: Path, relative: str, payload: object) -> None:
    path = run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_initialize_run_writes_private_posture_and_completed_intake_receipt(
    tmp_path: Path,
) -> None:
    run_dir = _initialize(tmp_path)

    intake = json.loads((run_dir / "run_intake.json").read_text(encoding="utf-8"))
    observed = run_state.inspect_run(run_dir)

    assert intake["scope"] == {
        "retailer": "example-retailer",
        "category_key": "cashmere",
    }
    assert intake["server_origin"] == "https://mparanza.com"
    assert intake["data_posture"]["model_provider_api_key_required"] is False
    assert intake["data_posture"]["product_images_uploaded_to_server"] is False
    assert intake["data_posture"]["report_uploaded_to_server"] is False
    assert observed["stages"][0]["effective_status"] == "complete"
    assert observed["next_stage"] == "server_snapshot"


def test_initialize_run_is_idempotent_for_same_scope(tmp_path: Path) -> None:
    run_dir = _initialize(tmp_path)
    first = json.loads((run_dir / "run_intake.json").read_text(encoding="utf-8"))

    result = run_state.initialize_run(
        run_dir,
        retailer="example-retailer",
        category="cashmere",
        author_agent_id="author-agent",
        server_origin="https://mparanza.com",
    )

    second = json.loads((run_dir / "run_intake.json").read_text(encoding="utf-8"))
    assert second == first
    assert result["run_id"] == first["run_id"]


def test_initialize_run_rejects_different_server_origin_on_resume(
    tmp_path: Path,
) -> None:
    run_dir = _initialize(tmp_path)

    with pytest.raises(run_state.RunStateError, match="does not match"):
        run_state.initialize_run(
            run_dir,
            retailer="example-retailer",
            category="cashmere",
            author_agent_id="author-agent",
            server_origin="https://other.example",
        )


def test_record_stage_requires_upstream_completion(tmp_path: Path) -> None:
    run_dir = _initialize(tmp_path)
    _write_artifact(run_dir, "package/local_image_manifest.json", {"status": "ok"})

    with pytest.raises(run_state.RunStateError, match="before server_snapshot"):
        run_state.record_stage(
            run_dir,
            "image_hydration",
            status="complete",
            artifacts=["package/local_image_manifest.json"],
        )


def test_inspect_run_invalidates_stage_and_downstream_when_artifact_changes(
    tmp_path: Path,
) -> None:
    run_dir = _initialize(tmp_path)
    _write_artifact(run_dir, "server/package_receipt.json", {"hash": "one"})
    run_state.record_stage(
        run_dir,
        "server_snapshot",
        status="complete",
        artifacts=["server/package_receipt.json"],
    )
    _write_artifact(run_dir, "package/local_image_manifest.json", {"status": "ok"})
    run_state.record_stage(
        run_dir,
        "image_hydration",
        status="complete",
        artifacts=["package/local_image_manifest.json"],
    )

    _write_artifact(run_dir, "server/package_receipt.json", {"hash": "changed"})
    observed = run_state.inspect_run(run_dir)

    server_stage = observed["stages"][1]
    image_stage = observed["stages"][2]
    assert server_stage["effective_status"] == "invalidated"
    assert server_stage["drift_reason"] == "artifact_hash_changed"
    assert image_stage["effective_status"] == "invalidated"
    assert image_stage["drift_reason"] == "upstream_not_complete"
    assert observed["next_stage"] == "server_snapshot"


def test_recording_changed_stage_explicitly_invalidates_completed_downstream(
    tmp_path: Path,
) -> None:
    run_dir = _initialize(tmp_path)
    _write_artifact(run_dir, "server/package_receipt.json", {"hash": "one"})
    run_state.record_stage(
        run_dir,
        "server_snapshot",
        status="complete",
        artifacts=["server/package_receipt.json"],
    )
    _write_artifact(run_dir, "package/local_image_manifest.json", {"status": "ok"})
    run_state.record_stage(
        run_dir,
        "image_hydration",
        status="complete",
        artifacts=["package/local_image_manifest.json"],
    )
    _write_artifact(run_dir, "server/package_receipt.json", {"hash": "two"})

    observed = run_state.record_stage(
        run_dir,
        "server_snapshot",
        status="complete",
        artifacts=["server/package_receipt.json"],
    )

    assert observed["stages"][1]["effective_status"] == "complete"
    assert observed["stages"][2]["effective_status"] == "invalidated"
    assert observed["next_stage"] == "image_hydration"


def test_partial_image_hydration_can_continue_with_visible_caveat(
    tmp_path: Path,
) -> None:
    run_dir = _initialize(tmp_path)
    _write_artifact(run_dir, "server/package_receipt.json", {"hash": "one"})
    run_state.record_stage(
        run_dir,
        "server_snapshot",
        status="complete",
        artifacts=["server/package_receipt.json"],
    )
    _write_artifact(
        run_dir,
        "package/local_image_manifest.json",
        {"summary": {"status": "partial"}},
    )

    after_images = run_state.record_stage(
        run_dir,
        "image_hydration",
        status="partial",
        artifacts=["package/local_image_manifest.json"],
    )
    _write_artifact(run_dir, "mapping/mapping_tasks.json", {"tasks": []})
    after_tasks = run_state.record_stage(
        run_dir,
        "mapping_tasks",
        status="complete",
        artifacts=["mapping/mapping_tasks.json"],
    )

    assert after_images["next_stage"] == "mapping_tasks"
    assert after_images["status"] == "partial"
    assert after_tasks["stages"][2]["effective_status"] == "partial"
    assert after_tasks["next_stage"] == "mapping_decisions"


def test_parallel_stage_updates_leave_one_internally_consistent_receipt(
    tmp_path: Path,
) -> None:
    run_dir = _initialize(tmp_path)
    _write_artifact(run_dir, "server/package_receipt.json", {"hash": "one"})

    def update(index: int) -> dict[str, object]:
        return run_state.record_stage(
            run_dir,
            "server_snapshot",
            status="complete",
            artifacts=["server/package_receipt.json"],
            detail={"parallel_update": index},
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(update, range(8)))

    observed = run_state.inspect_run(run_dir)
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (run_dir / state["stages"][1]["receipt"]).read_text(encoding="utf-8")
    )
    assert len(results) == 8
    assert observed["stages"][1]["effective_status"] == "complete"
    assert observed["stages"][1]["drift_reason"] == ""
    assert receipt["detail"]["parallel_update"] in range(8)


def test_inspect_run_rejects_truncated_stage_contract(tmp_path: Path) -> None:
    run_dir = _initialize(tmp_path)
    state_path = run_dir / "run_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["stages"].pop()
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(run_state.RunStateError, match="invalid stage list"):
        run_state.inspect_run(run_dir)


def test_initialize_run_rejects_git_workspace_output() -> None:
    with pytest.raises(
        run_state.RunStateError, match="cannot be inside a Git workspace"
    ):
        run_state.initialize_run(
            ROOT / "out" / "unsafe-run",
            retailer="example-retailer",
            category="cashmere",
            author_agent_id="author-agent",
            server_origin="https://mparanza.com",
        )
