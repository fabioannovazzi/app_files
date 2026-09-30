"""Coordinate host-scheduled research with durable private jobs and no case mutation.

The host model performs public discovery and semantic review. This module owns
cadence, exact job/scan binding, preserved baselines and private notice records.
It never starts a scheduler, sends a message or chooses legal relevance.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .contracts import ContractError, canonical_hash, read_json, validate
from .monitor import impact_queue
from .source_acquisition import compare_scans, open_scan, read_final_scan

__all__ = ["configure", "record_schedule", "begin", "finish", "fail", "status"]
MAX_BYTES = 16 * 1024 * 1024


def _time(at: datetime) -> datetime:
    if at.tzinfo is None:
        raise ContractError("Monitor time needs a timezone")
    return at.astimezone(timezone.utc)


def _read(path: Path) -> dict[str, Any]:
    if (
        path.is_symlink()
        or path.parent.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_BYTES
    ):
        raise ContractError("Monitor records must be bounded regular files")
    value = read_json(path)
    if not isinstance(value, dict):
        raise ContractError("Monitor record must be an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    raw = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode()
    if len(raw) > MAX_BYTES or path.is_symlink() or path.parent.is_symlink():
        raise ContractError("Invalid monitor output path or size")
    if path.exists():
        if path.read_bytes() != raw:
            raise ContractError("Monitor version already exists with different bytes")
        return
    with path.open("xb") as stream:
        stream.write(raw)
    path.chmod(0o600)


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    return {**value, "record_sha256": canonical_hash(value)}


def _record(path: Path) -> dict[str, Any]:
    value = _read(path)
    if (
        canonical_hash({k: v for k, v in value.items() if k != "record_sha256"})
        != value["record_sha256"]
    ):
        raise ContractError("Monitor record changed")
    return value


@contextmanager
def _locked(root: Path) -> Iterator[dict[str, Any]]:
    config = _record(root / "config.json")
    public_root = Path(config["public_root"])
    if not _separate(root, public_root) or (
        config["private_case_index"]
        and not _separate(Path(config["private_case_index"]), public_root)
    ):
        raise ContractError(
            "Private monitor storage now overlaps public source storage"
        )
    lock = root / ".monitor.lock"
    try:
        descriptor = lock.open("xb")
    except FileExistsError as error:
        raise ContractError(
            "Monitor is busy; a crashed owner's lock requires explicit recovery"
        ) from error
    try:
        with descriptor:
            descriptor.write(b"Exclusive monitor operation\n")
        yield config
    finally:
        lock.unlink()


def _separate(left: Path, right: Path) -> bool:
    return not (
        left.resolve().is_relative_to(right.resolve())
        or right.resolve().is_relative_to(left.resolve())
    )


def _scope(plan: dict[str, Any]) -> dict[str, Any]:
    validate(plan, "source-plan.schema.json")
    return {
        row["scope_id"]: {
            k: v for k, v in row.items() if k not in ("window_start", "window_end")
        }
        for row in plan["scopes"]
    }


def configure(
    root: Path,
    *,
    public_root: Path,
    owner: str,
    plan: dict[str, Any],
    private_case_index: Path | None = None,
    interval_hours: int = 168,
) -> dict[str, Any]:
    """Create a disabled service; the selected host owns actual schedule activation."""
    if (
        not owner.strip()
        or type(interval_hours) is not int
        or not 1 <= interval_hours <= 8760
    ):
        raise ContractError("Monitor needs an owner and a bounded interval")
    if (
        not root.is_absolute()
        or not public_root.is_absolute()
        or not _separate(root, public_root)
    ):
        raise ContractError(
            "Private service and public scan directories must be separate absolute paths"
        )
    if private_case_index is not None:
        if not private_case_index.is_absolute() or not _separate(
            private_case_index, public_root
        ):
            raise ContractError(
                "Private case index must stay outside public source storage"
            )
        validate(_read(private_case_index), "case-index.schema.json")
    scope = _scope(plan)
    if len(scope) != len(plan["scopes"]):
        raise ContractError("Monitor scope identifiers must be unique")
    config = _seal(
        {
            "schema_version": "1.0",
            "service_id": str(uuid4()),
            "owner": owner.strip(),
            "public_root": str(public_root),
            "private_case_index": (
                str(private_case_index) if private_case_index else None
            ),
            "scope": scope,
            "interval_hours": interval_hours,
            "initial_schedule_enabled": False,
            "cadence_is_statutory_deadline": False,
        }
    )
    root.mkdir(mode=0o700)
    (root / "jobs").mkdir(mode=0o700)
    (root / "schedules").mkdir(mode=0o700)
    _write(root / "config.json", config)
    return config


def record_schedule(
    root: Path, *, host_reference: str, active: bool, owner: str, at: datetime
) -> dict[str, Any]:
    """Retain the host tool's actual receipt after its authorized create/update call."""
    with _locked(root) as config:
        if (
            owner != config["owner"]
            or not host_reference.strip()
            or type(active) is not bool
        ):
            raise ContractError(
                "Schedule receipt needs the configured owner and actual host reference"
            )
        previous = [_record(path) for path in (root / "schedules").glob("*.json")]
        if any(
            _time(at) < datetime.fromisoformat(row["recorded_at"]) for row in previous
        ):
            raise ContractError("Schedule receipt cannot precede an existing receipt")
        receipt = _seal(
            {
                "service_id": config["service_id"],
                "host_reference": host_reference.strip(),
                "sequence": len(previous) + 1,
                "active": active,
                "recorded_at": _time(at).isoformat(),
                "assurance": "HOST_OPERATOR_ATTESTATION_NOT_INDEPENDENT_SCHEDULER_VERIFICATION",
            }
        )
        _write(root / "schedules" / (receipt["record_sha256"] + ".json"), receipt)
        return receipt


def _history(root: Path, service_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if (root / "jobs").is_symlink():
        raise ContractError("Monitor jobs cannot be a symbolic link")
    for directory in sorted((root / "jobs").iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            raise ContractError("Invalid monitor job directory")
        request = _record(directory / "request.json")
        if request["service_id"] != service_id or request["job_id"] != directory.name:
            raise ContractError("Monitor request belongs to another service or job")
        outcome_path = directory / "outcome.json"
        outcome = _record(outcome_path) if outcome_path.exists() else None
        if (
            outcome is not None
            and outcome["request_sha256"] != request["record_sha256"]
        ):
            raise ContractError("Monitor outcome belongs to another request")
        result.append({"request": request, "outcome": outcome})
    if {row["request"]["sequence"] for row in result} != set(range(1, len(result) + 1)):
        raise ContractError("Monitor job sequence is incomplete or duplicated")
    return sorted(result, key=lambda row: row["request"]["sequence"])


def status(root: Path, *, at: datetime) -> dict[str, Any]:
    """Read cadence and pending work without claiming a scan or legal clearance."""
    config = _record(root / "config.json")
    schedules = [_record(path) for path in (root / "schedules").glob("*.json")]
    if {row["sequence"] for row in schedules} != set(range(1, len(schedules) + 1)):
        raise ContractError("Monitor schedule sequence is incomplete or duplicated")
    schedule = max(schedules, key=lambda row: row["sequence"]) if schedules else None
    if any(row["service_id"] != config["service_id"] for row in schedules):
        raise ContractError("Schedule receipt belongs to another service")
    history = _history(root, config["service_id"])
    pending = [row["request"] for row in history if row["outcome"] is None]
    last_complete = next(
        (
            row
            for row in reversed(history)
            if row["outcome"]
            and row["outcome"]["coverage"] == "COMPLETE_DECLARED_SCOPE"
        ),
        None,
    )
    last_time = (
        datetime.fromisoformat(history[-1]["request"]["requested_at"])
        if history
        else None
    )
    now = _time(at)
    if last_time is not None and now < last_time:
        raise ContractError("Monitor clock precedes recorded work")
    next_due = (
        last_time + timedelta(hours=config["interval_hours"]) if last_time else now
    )
    return {
        "service_id": config["service_id"],
        "schedule_active": bool(schedule and schedule["active"]),
        "pending_jobs": [row["job_id"] for row in pending],
        "periodic_due": now >= next_due,
        "next_due": next_due.isoformat(),
        "last_complete_scan": (
            last_complete["request"]["scan"] if last_complete else None
        ),
        "professional_acceptance": False,
    }


def begin(
    root: Path, plan: dict[str, Any], *, trigger: str, at: datetime
) -> dict[str, Any]:
    """Open a fresh scan for the host model; periodic work stays off until configured."""
    with _locked(root) as config:
        current = status(root, at=at)
        if trigger not in ("PERIODIC", "OPEN_CASE", "CLOSE_CASE", "MANUAL_RETRY"):
            raise ContractError("Unknown monitor trigger")
        if trigger == "PERIODIC" and not current["schedule_active"]:
            return {"status": "DISABLED", **current}
        if current["pending_jobs"]:
            return {"status": "PENDING_HOST_RESEARCH", **current}
        if trigger == "PERIODIC" and not current["periodic_due"]:
            return {"status": "NOT_DUE", **current}
        if _scope(plan) != config["scope"]:
            raise ContractError(
                "Changed research scope requires a new reviewed service configuration"
            )
        scan = open_scan(plan, Path(config["public_root"]))
        sequence = len(_history(root, config["service_id"])) + 1
        job_id = "job_" + uuid4().hex
        directory = root / "jobs" / job_id
        directory.mkdir(mode=0o700)
        request = _seal(
            {
                "schema_version": "1.0",
                "service_id": config["service_id"],
                "job_id": job_id,
                "sequence": sequence,
                "trigger": trigger,
                "requested_at": _time(at).isoformat(),
                "plan_sha256": canonical_hash(plan),
                "scan": scan["directory"],
                "baseline_scan": current["last_complete_scan"],
                "host_action": "Read current public listings; review observed links, new documents, publication windows and pagination; finish the scan with explicit coverage.",
            }
        )
        _write(directory / "request.json", request)
        return {"status": "PENDING_HOST_RESEARCH", **request}


def _job(root: Path, job_id: str) -> tuple[Path, dict[str, Any]]:
    if not re.fullmatch(r"job_[0-9a-f]{32}", job_id):
        raise ContractError("Invalid monitor job ID")
    directory = root / "jobs" / job_id
    return directory, _record(directory / "request.json")


def finish(root: Path, job_id: str, *, at: datetime) -> dict[str, Any]:
    """Retain comparisons and private notices; partial scans never replace the baseline."""
    with _locked(root) as config:
        directory, request = _job(root, job_id)
        if request["service_id"] != config["service_id"] or not Path(
            request["scan"]
        ).resolve().is_relative_to(Path(config["public_root"]).resolve()):
            raise ContractError("Monitor scan is outside the configured service")
        final = read_final_scan(Path(request["scan"]))
        if final["plan_hash"] != request["plan_sha256"]:
            raise ContractError("Completed scan differs from the requested plan")
        if (directory / "outcome.json").exists():
            existing = _record(directory / "outcome.json")
            if existing["scan_sha256"] != final["final_hash"]:
                raise ContractError("Monitor result changed after completion")
            return existing
        if _time(at) < datetime.fromisoformat(request["requested_at"]):
            raise ContractError("Monitor completion precedes its request")
        comparison = (
            compare_scans(Path(request["baseline_scan"]), Path(request["scan"]))
            if request["baseline_scan"]
            else None
        )
        case_index = (
            _read(Path(config["private_case_index"]))
            if config["private_case_index"]
            else {"schema_version": "1.0", "cases": []}
        )
        validate(case_index, "case-index.schema.json")
        _write(directory / "case_index.json", case_index)
        queue: dict[str, Any] = (
            impact_queue(comparison, case_index)
            if comparison
            else {
                "schema_version": "1.0",
                "items": [],
                "case_index_hash": canonical_hash(case_index),
            }
        )
        _write(directory / "impact_queue.json", queue)
        if comparison is not None:
            _write(directory / "comparison.json", comparison)
        complete = final["snapshot"]["coverage"] == "COMPLETE_DECLARED_SCOPE"
        notice = not complete or comparison is None or bool(comparison["events"])
        outcome = _seal(
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "request_sha256": request["record_sha256"],
                "completed_at": _time(at).isoformat(),
                "scan_sha256": final["final_hash"],
                "coverage": final["snapshot"]["coverage"],
                "status": (
                    "BASELINE_RECORDED"
                    if comparison is None and complete
                    else final["status"]
                ),
                "source_events": len(comparison["events"]) if comparison else 0,
                "affected_cases": len({row["case_id"] for row in queue["items"]}),
                "notification_required": notice,
                "notification_delivered": False,
                "gaps": final["gaps"],
                "queue_sha256": canonical_hash(queue),
                "automatic_case_mutation": False,
                "source_activation": "NONE",
                "exhaustive_legal_monitoring": False,
            }
        )
        _write(directory / "outcome.json", outcome)
        return outcome


def fail(root: Path, job_id: str, *, reason: str, at: datetime) -> dict[str, Any]:
    """Close a failed host attempt explicitly while retaining the last complete scan."""
    with _locked(root):
        directory, request = _job(root, job_id)
        if not reason.strip() or _time(at) < datetime.fromisoformat(
            request["requested_at"]
        ):
            raise ContractError("Failure needs a reason and a valid completion time")
        outcome = _seal(
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "request_sha256": request["record_sha256"],
                "completed_at": _time(at).isoformat(),
                "coverage": "PARTIAL",
                "status": "HOST_RESEARCH_FAILED",
                "reason": reason.strip(),
                "scan_sha256": None,
                "notification_required": True,
                "notification_delivered": False,
                "automatic_case_mutation": False,
                "source_activation": "NONE",
            }
        )
        _write(directory / "outcome.json", outcome)
        return outcome
