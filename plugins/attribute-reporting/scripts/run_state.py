#!/usr/bin/env python3
"""Maintain a hash-bound, resumable Attribute Reporting run ledger.

Stage order and artifact hashes are deterministic because resumability and
write idempotency are mechanically verifiable contracts.  This module never
performs semantic mapping, narrative authoring, or review judgment.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "RunStateError",
    "STAGES",
    "initialize_run",
    "inspect_run",
    "record_stage",
    "main",
]

LOGGER = logging.getLogger(__name__)
RUN_INTAKE_SCHEMA = "attribute_reporting.clara_run_intake.v1"
RUN_STATE_SCHEMA = "attribute_reporting.run_state.v1"
STAGE_RECEIPT_SCHEMA = "attribute_reporting.stage_receipt.v1"
TERMINAL_SUCCESS = {"complete", "skipped"}
ALLOWED_STAGE_STATUSES = {
    "pending",
    "running",
    "complete",
    "skipped",
    "partial",
    "blocked",
    "failed",
    "invalidated",
}
STAGES: tuple[dict[str, str], ...] = (
    {"id": "intake", "owner": "deterministic"},
    {"id": "server_snapshot", "owner": "deterministic"},
    {"id": "image_hydration", "owner": "deterministic"},
    {"id": "mapping_tasks", "owner": "deterministic"},
    {"id": "mapping_decisions", "owner": "codex_agent"},
    {"id": "mapping_review", "owner": "independent_codex_agent"},
    {"id": "mapping_apply", "owner": "deterministic_server_write"},
    {"id": "rebuilt_package", "owner": "deterministic"},
    {"id": "report_prepare", "owner": "deterministic"},
    {"id": "report_authoring", "owner": "codex_agent"},
    {"id": "report_render", "owner": "deterministic"},
    {"id": "semantic_review", "owner": "independent_codex_agent"},
    {"id": "browser_qa", "owner": "deterministic"},
    {"id": "correctness", "owner": "deterministic"},
)
STAGE_INDEX = {item["id"]: index for index, item in enumerate(STAGES)}


class RunStateError(ValueError):
    """Raised when a run ledger or stage receipt is unsafe or inconsistent."""


def _stage_is_proceedable(stage_id: str, status: str) -> bool:
    return status in TERMINAL_SUCCESS or (
        stage_id == "image_hydration" and status == "partial"
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


@contextmanager
def _locked_run(run: Path) -> Iterator[None]:
    """Serialize ledger reads and writes across parallel local Codex agents."""

    lock_path = run / ".run_state.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RunStateError(f"Required run file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RunStateError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RunStateError(f"Expected a JSON object in {path}")
    return payload


def _assert_private_run_dir(run_dir: Path, *, must_exist: bool = False) -> Path:
    run = run_dir.expanduser().resolve()
    for parent in (run, *run.parents):
        if (parent / ".git").exists():
            raise RunStateError(
                "Attribute Reporting run outputs cannot be inside a Git workspace"
            )
    if must_exist and not run.is_dir():
        raise RunStateError(f"Run directory does not exist: {run}")
    return run


def _safe_artifact_path(run: Path, value: str) -> tuple[Path, str]:
    raw = Path(value)
    candidate = (
        raw.expanduser().resolve() if raw.is_absolute() else (run / raw).resolve()
    )
    if not candidate.is_relative_to(run):
        raise RunStateError(f"Stage artifact escapes the run directory: {value}")
    return candidate, candidate.relative_to(run).as_posix()


def _artifact_records(run: Path, artifacts: Sequence[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in artifacts:
        path, relative = _safe_artifact_path(run, value)
        if relative in seen:
            continue
        seen.add(relative)
        if not path.is_file():
            raise RunStateError(f"Stage artifact does not exist: {path}")
        records.append(
            {
                "path": relative,
                "sha256": _sha256_file(path),
                "byte_count": path.stat().st_size,
            }
        )
    return records


def _initial_state(run_id: str) -> dict[str, Any]:
    return {
        "schema_version": RUN_STATE_SCHEMA,
        "run_id": run_id,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "status": "running",
        "next_stage": "intake",
        "stages": [
            {
                "stage_id": item["id"],
                "owner": item["owner"],
                "status": "pending",
                "receipt": f"stage_receipts/{index + 1:02d}-{item['id']}.json",
                "receipt_sha256": "",
            }
            for index, item in enumerate(STAGES)
        ],
    }


def initialize_run(
    run_dir: Path,
    *,
    retailer: str,
    category: str,
    author_agent_id: str,
    server_origin: str,
    data_mode: str = "current_snapshot",
) -> dict[str, Any]:
    """Create one private run folder and its first completed receipt."""

    run = _assert_private_run_dir(run_dir)
    retailer_key = retailer.strip()
    category_key = category.strip()
    author_id = author_agent_id.strip()
    origin = server_origin.strip().rstrip("/")
    if not retailer_key or not category_key or not author_id or not origin:
        raise RunStateError(
            "retailer, category, author_agent_id, and server_origin are required"
        )
    if data_mode not in {"current_snapshot", "fresh_local_scrape"}:
        raise RunStateError("Unsupported data_mode")
    run.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(run, 0o700)
    with _locked_run(run):
        existing_entries = [
            path for path in run.iterdir() if path.name != ".run_state.lock"
        ]
        if existing_entries:
            existing = run / "run_intake.json"
            if not existing.is_file():
                raise RunStateError(
                    "Refusing to initialize a non-empty directory without a run intake"
                )
            intake = _load_json(existing)
            if (
                intake.get("schema_version") == RUN_INTAKE_SCHEMA
                and intake.get("scope")
                == {"retailer": retailer_key, "category_key": category_key}
                and intake.get("author_agent_id") == author_id
                and intake.get("data_mode") == data_mode
                and intake.get("server_origin") == origin
            ):
                return _inspect_run_unlocked(run)
            raise RunStateError(
                "Existing run intake does not match the requested scope"
            )

        run_id = uuid.uuid4().hex
        intake = {
            "schema_version": RUN_INTAKE_SCHEMA,
            "run_id": run_id,
            "created_at": _utc_now(),
            "plugin": "clara",
            "workflow": "attribute_reporting",
            "scope": {"retailer": retailer_key, "category_key": category_key},
            "author_agent_id": author_id,
            "data_mode": data_mode,
            "server_origin": origin,
            "output_dir": str(run),
            "assumptions": [
                "New means the retailer-defined new or newest cohort in the source data.",
                "The canonical taxonomy is centrally governed per category.",
            ],
            "data_posture": {
                "structured_data_persistence": "authenticated_server_database",
                "taxonomy_authority": "central_per_category",
                "model_execution": "local_codex_agents",
                "model_provider_api_key_required": False,
                "product_image_storage": "local_machine_only",
                "product_images_uploaded_to_server": False,
                "report_storage": "private_local_only",
                "report_uploaded_to_server": False,
            },
        }
        state = _initial_state(run_id)
        _write_json_atomic(run / "run_intake.json", intake)
        _write_json_atomic(run / "run_state.json", state)
        return _record_stage_unlocked(
            run,
            "intake",
            status="complete",
            artifacts=["run_intake.json"],
            detail={"data_mode": data_mode},
        )


def _validated_receipt(
    run: Path,
    stage: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    receipt_path, _relative = _safe_artifact_path(run, str(stage["receipt"]))
    if not receipt_path.is_file():
        return None, "receipt_missing"
    try:
        receipt = _load_json(receipt_path)
    except RunStateError:
        return None, "receipt_invalid"
    if (
        receipt.get("schema_version") != STAGE_RECEIPT_SCHEMA
        or receipt.get("run_id") is None
        or receipt.get("stage_id") != stage.get("stage_id")
        or receipt.get("status") not in ALLOWED_STAGE_STATUSES
    ):
        return None, "receipt_contract_invalid"
    expected_receipt_sha = str(stage.get("receipt_sha256") or "")
    if expected_receipt_sha and _canonical_sha256(receipt) != expected_receipt_sha:
        return None, "receipt_hash_changed"
    for artifact in receipt.get("artifacts") or []:
        if not isinstance(artifact, dict):
            return None, "artifact_contract_invalid"
        try:
            artifact_path, _ = _safe_artifact_path(run, str(artifact.get("path") or ""))
        except RunStateError:
            return None, "artifact_path_invalid"
        if not artifact_path.is_file():
            return None, "artifact_missing"
        if _sha256_file(artifact_path) != str(artifact.get("sha256") or ""):
            return None, "artifact_hash_changed"
    return receipt, ""


def _inspect_run_unlocked(run: Path) -> dict[str, Any]:
    """Inspect a run while the caller holds its ledger lock."""

    intake = _load_json(run / "run_intake.json")
    state = _load_json(run / "run_state.json")
    if intake.get("schema_version") != RUN_INTAKE_SCHEMA:
        raise RunStateError("Unsupported run intake schema")
    if state.get("schema_version") != RUN_STATE_SCHEMA:
        raise RunStateError("Unsupported run state schema")
    if state.get("run_id") != intake.get("run_id"):
        raise RunStateError("Run intake and state use different run ids")

    raw_stages = state.get("stages")
    if not isinstance(raw_stages, list) or len(raw_stages) != len(STAGES):
        raise RunStateError("Run state has an invalid stage list")

    observed_stages: list[dict[str, Any]] = []
    prior_ready = True
    next_stage = ""
    overall_status = "running"
    for expected, raw_stage in zip(STAGES, raw_stages, strict=True):
        if (
            not isinstance(raw_stage, dict)
            or raw_stage.get("stage_id") != expected["id"]
        ):
            raise RunStateError("Run state stages differ from the workflow contract")
        stage = dict(raw_stage)
        receipt, drift = _validated_receipt(run, stage)
        recorded_status = str(stage.get("status") or "pending")
        effective_status = recorded_status
        if recorded_status in TERMINAL_SUCCESS and receipt is None:
            effective_status = "invalidated"
        if not prior_ready and recorded_status != "pending":
            effective_status = "invalidated"
            drift = drift or "upstream_not_complete"
        if prior_ready and not _stage_is_proceedable(expected["id"], effective_status):
            prior_ready = False
            if not next_stage:
                next_stage = expected["id"]
        stage["effective_status"] = effective_status
        stage["drift_reason"] = drift
        observed_stages.append(stage)
        if effective_status in {"blocked", "failed", "partial"}:
            overall_status = effective_status
    if prior_ready:
        overall_status = (
            "complete_with_caveats"
            if any(
                item["stage_id"] == "image_hydration"
                and item["effective_status"] == "partial"
                for item in observed_stages
            )
            else "complete"
        )
    return {
        "schema_version": RUN_STATE_SCHEMA,
        "run_id": state["run_id"],
        "run_dir": str(run),
        "status": overall_status,
        "next_stage": next_stage,
        "stages": observed_stages,
    }


def inspect_run(run_dir: Path) -> dict[str, Any]:
    """Read receipts, detect drift, and return the first resumable stage."""

    run = _assert_private_run_dir(run_dir, must_exist=True)
    with _locked_run(run):
        return _inspect_run_unlocked(run)


def _record_stage_unlocked(
    run_dir: Path,
    stage_id: str,
    *,
    status: str,
    artifacts: Sequence[str] = (),
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a stage receipt while the caller holds the run ledger lock."""

    run = _assert_private_run_dir(run_dir, must_exist=True)
    if stage_id not in STAGE_INDEX:
        raise RunStateError(f"Unknown stage: {stage_id}")
    if status not in ALLOWED_STAGE_STATUSES - {"pending", "invalidated"}:
        raise RunStateError(f"Unsupported recorded stage status: {status}")
    state = _load_json(run / "run_state.json")
    intake = _load_json(run / "run_intake.json")
    if state.get("run_id") != intake.get("run_id"):
        raise RunStateError("Run intake and state use different run ids")
    stage_position = STAGE_INDEX[stage_id]
    stages = state.get("stages")
    if not isinstance(stages, list) or len(stages) != len(STAGES):
        raise RunStateError("Run state has an invalid stage list")
    if status in TERMINAL_SUCCESS:
        for upstream in stages[:stage_position]:
            if not _stage_is_proceedable(
                str(upstream.get("stage_id") or ""),
                str(upstream.get("status") or "pending"),
            ):
                raise RunStateError(
                    f"Cannot complete {stage_id} before {upstream.get('stage_id')}"
                )

    artifact_records = _artifact_records(run, artifacts)
    stage_entry = stages[stage_position]
    receipt_path, receipt_relative = _safe_artifact_path(
        run, str(stage_entry["receipt"])
    )
    previous_receipt = _load_json(receipt_path) if receipt_path.is_file() else None
    receipt = {
        "schema_version": STAGE_RECEIPT_SCHEMA,
        "run_id": state["run_id"],
        "stage_id": stage_id,
        "owner": STAGES[stage_position]["owner"],
        "recorded_at": _utc_now(),
        "status": status,
        "artifacts": artifact_records,
        "detail": dict(detail or {}),
        "supersedes_receipt_sha256": (
            _canonical_sha256(previous_receipt) if previous_receipt else ""
        ),
    }
    receipt_sha = _canonical_sha256(receipt)
    changed = previous_receipt is None or any(
        previous_receipt.get(key) != receipt.get(key)
        for key in ("status", "artifacts", "detail")
    )
    _write_json_atomic(receipt_path, receipt)
    stage_entry.update(
        {
            "status": status,
            "receipt": receipt_relative,
            "receipt_sha256": receipt_sha,
        }
    )
    if changed:
        for downstream in stages[stage_position + 1 :]:
            if downstream.get("status") != "pending":
                downstream["status"] = "invalidated"
    state["updated_at"] = _utc_now()
    state["stages"] = stages
    state["next_stage"] = next(
        (
            str(item["stage_id"])
            for item in stages
            if not _stage_is_proceedable(
                str(item.get("stage_id") or ""),
                str(item.get("status") or "pending"),
            )
        ),
        "",
    )
    state["status"] = (
        (
            "complete_with_caveats"
            if any(
                item.get("stage_id") == "image_hydration"
                and item.get("status") == "partial"
                for item in stages
            )
            else "complete"
        )
        if not state["next_stage"]
        else "running"
    )
    _write_json_atomic(run / "run_state.json", state)
    return _inspect_run_unlocked(run)


def record_stage(
    run_dir: Path,
    stage_id: str,
    *,
    status: str,
    artifacts: Sequence[str] = (),
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Atomically write a stage receipt and serialize parallel agent updates."""

    run = _assert_private_run_dir(run_dir, must_exist=True)
    with _locked_run(run):
        return _record_stage_unlocked(
            run,
            stage_id,
            status=status,
            artifacts=artifacts,
            detail=detail,
        )


def main(argv: Iterable[str] | None = None) -> int:
    """Initialize, inspect, or update a resumable run ledger."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    initialize = subparsers.add_parser("init")
    initialize.add_argument("run_dir", type=Path)
    initialize.add_argument("--retailer", required=True)
    initialize.add_argument("--category", required=True)
    initialize.add_argument("--author-agent-id", required=True)
    initialize.add_argument("--server-origin", required=True)
    initialize.add_argument(
        "--data-mode",
        choices=("current_snapshot", "fresh_local_scrape"),
        default="current_snapshot",
    )
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("run_dir", type=Path)
    record = subparsers.add_parser("record")
    record.add_argument("run_dir", type=Path)
    record.add_argument("stage", choices=tuple(STAGE_INDEX))
    record.add_argument(
        "--status",
        choices=tuple(sorted(ALLOWED_STAGE_STATUSES - {"pending", "invalidated"})),
        required=True,
    )
    record.add_argument("--artifact", action="append", default=[])
    record.add_argument("--detail-json", default="{}")
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "init":
            result = initialize_run(
                args.run_dir,
                retailer=args.retailer,
                category=args.category,
                author_agent_id=args.author_agent_id,
                server_origin=args.server_origin,
                data_mode=args.data_mode,
            )
        elif args.command == "status":
            result = inspect_run(args.run_dir)
        else:
            raw_detail = json.loads(args.detail_json)
            if not isinstance(raw_detail, dict):
                raise RunStateError("--detail-json must contain an object")
            result = record_stage(
                args.run_dir,
                args.stage,
                status=args.status,
                artifacts=args.artifact,
                detail=raw_detail,
            )
    except (RunStateError, json.JSONDecodeError) as exc:
        LOGGER.error("Run-state operation failed: %s", exc)
        return 1
    LOGGER.info(
        "Run %s; next stage: %s", result["status"], result["next_stage"] or "none"
    )
    return 0 if result["status"] not in {"failed", "blocked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
