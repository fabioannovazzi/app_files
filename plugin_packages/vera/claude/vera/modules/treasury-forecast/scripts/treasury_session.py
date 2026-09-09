"""Append treasury review versions and reject stale or changed source state."""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterator

from treasury_core import (
    TreasuryError,
    build_forecast,
    build_scenario,
    digest,
    validate_record,
)
from treasury_inputs import read_json
from treasury_report import write_artifacts

__all__ = [
    "create_session",
    "current_record",
    "review_session",
    "save_scenario",
    "source_check",
]


def _write(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}-{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            temporary.chmod(0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def _lock(output: Path) -> Iterator[None]:
    lock = output / ".treasury-review.lock"
    try:
        stream = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise TreasuryError(
            "Another review write is in progress; reload and retry"
        ) from exc
    try:
        with stream:
            stream.write("treasury review transaction\n")
            yield
    finally:
        lock.unlink(missing_ok=True)


def source_check(state: dict[str, Any]) -> None:
    """Exact hashes detect source changes; the CLI separately enforces archive binding."""
    for source in state["sources"]:
        path = Path(source["path"])
        if path.is_symlink() or not path.is_file():
            raise TreasuryError("A prepared source is missing or linked")
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise TreasuryError("A source changed after preparation; import a new run")


def _state(output: Path) -> dict[str, Any]:
    state = read_json(output / "treasury_session.json")
    if state.get("schema_version") != "vera.treasury_session.v1":
        raise TreasuryError("Unsupported treasury session")
    if state["state_sha256"] != digest(
        {k: v for k, v in state.items() if k != "state_sha256"}
    ):
        raise TreasuryError("Session integrity mismatch")
    source_check(state)
    return state


def current_record(output: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read and verify the current immutable version and its artifact inventory."""
    state = _state(output)
    version = state["record_sha256"]
    if (
        not isinstance(version, str)
        or len(version) != 64
        or any(c not in "0123456789abcdef" for c in version)
    ):
        raise TreasuryError("Invalid version identity")
    directory = output / "versions" / version
    if directory.is_symlink():
        raise TreasuryError("Linked version directory")
    inventory = read_json(directory / "artifact_manifest.json")
    if digest(inventory) != state["artifact_manifest_sha256"]:
        raise TreasuryError("Artifact inventory integrity mismatch")
    for name, expected in inventory["files"].items():
        if Path(name).name != name:
            raise TreasuryError("Invalid artifact path")
        path = directory / name
        if (
            path.is_symlink()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise TreasuryError("An immutable treasury artifact was changed")
    record = read_json(directory / "forecast.json")
    validate_record(record)
    if record["record_sha256"] != version:
        raise TreasuryError("Current version does not match its pointer")
    return state, record


def _store(output: Path, state: dict[str, Any], record: dict[str, Any]) -> None:
    versions = output / "versions"
    versions.mkdir(exist_ok=True)
    target = versions / record["record_sha256"]
    if not target.exists():
        staging = output / f".treasury-stage-{uuid.uuid4().hex}"
        try:
            names = write_artifacts(staging, record)
            inventory = {
                name: hashlib.sha256((staging / name).read_bytes()).hexdigest()
                for name in names
            }
            _write(staging / "artifact_manifest.json", {"files": inventory})
            staging.rename(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    else:
        stored = read_json(target / "forecast.json")
        validate_record(stored)
        if stored != record:
            raise TreasuryError("An existing version differs from its content identity")
    state["record_sha256"] = record["record_sha256"]
    state["artifact_manifest_sha256"] = digest(
        read_json(target / "artifact_manifest.json")
    )
    if record["record_sha256"] not in state["history"]:
        state["history"].append(record["record_sha256"])
    state.pop("state_sha256", None)
    state["state_sha256"] = digest(state)
    _write(output / "treasury_session.json", state)
    _write(
        output / "final_artifacts.json",
        {
            "workflow_id": "treasury-forecast",
            "status": record["status"],
            "record_sha256": record["record_sha256"],
            "calculation_complete": record["calculation_complete"],
            "current_version": f"versions/{record['record_sha256']}",
            "report": f"versions/{record['record_sha256']}/report.html",
            "workbook": f"versions/{record['record_sha256']}/tesoreria.xlsx",
            "forecast": f"versions/{record['record_sha256']}/forecast.json",
            "review_decisions_consumed": bool(record["decisions"] or record["review"]),
        },
    )
    _write(
        output / "model_context.json",
        {
            "record_sha256": record["record_sha256"],
            "status": record["status"],
            "company_name": record["company_name"],
            "as_of": record["as_of"],
            "calculation_complete": record["calculation_complete"],
            "issue_count": len(record["issues"]),
            "issues_preview": record["issues"][:100],
            "event_count": len(record["events"]),
            "events_preview": record["events"][:100],
            "preview_truncated": len(record["events"]) > 100
            or len(record["issues"]) > 100,
            "instructions": "Read the local record or original sources for selected relevant items. This preview does not limit what the selected host model may read. Do not treat a due date as a guaranteed receipt.",
        },
    )


def create_session(
    output: Path,
    inputs: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    source_paths: list[Path],
    context_path: Path,
) -> dict[str, Any]:
    """Start or resume the same exact intake without overwriting an earlier run."""
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    sources = [
        {
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(set(source_paths))
    ]
    prepared = {"inputs": inputs, "previous": previous}
    prepared_hash = digest(prepared)
    with _lock(output):
        if (output / "treasury_session.json").exists():
            state, record = current_record(output)
            if state["prepared_sha256"] != prepared_hash or state["sources"] != sources:
                raise TreasuryError(
                    "Different inputs cannot overwrite this treasury run"
                )
            return record
        state = {
            "schema_version": "vera.treasury_session.v1",
            "context_path": str(context_path.resolve()),
            "prepared_sha256": prepared_hash,
            "sources": sources,
            "history": [],
        }
        record = build_forecast(inputs, previous=previous)
        _write(output / "prepared_inputs.json", prepared)
        _write(
            output / "run_intake.json",
            {
                "workflow_id": "treasury-forecast",
                "client_id": inputs["client_id"],
                "engagement_id": inputs["engagement_id"],
                "as_of": inputs["as_of"],
                "coverage": inputs["coverage"],
                "sources": sources,
                "model_data": "Local scripts make no model or network calls. The selected Claude/Cowork runtime may read client tables, invoice evidence and review records to perform the professional task; no automatic anonymization.",
            },
        )
        _store(output, state, record)
        return record


def save_scenario(
    output: Path, *, expected_record_sha256: str, dates: dict[str, str]
) -> dict[str, Any]:
    """Persist a separate alternative bound to the exact current forecast."""
    with _lock(output):
        _, record = current_record(output)
        if record["record_sha256"] != expected_record_sha256:
            raise TreasuryError("Scenario baseline is stale")
        scenario = build_scenario(record, dates)
        path = output / f"scenario-{digest(scenario)}.json"
        if path.exists():
            if read_json(path) != scenario:
                raise TreasuryError("Saved alternative was changed")
        else:
            _write(path, scenario)
        return scenario


def review_session(
    output: Path,
    *,
    expected_record_sha256: str,
    decisions: dict[str, Any] | None = None,
    review: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Apply row edits or accept the exact displayed proposal in a new version."""
    with _lock(output):
        state, current = current_record(output)
        if current["record_sha256"] != expected_record_sha256:
            raise TreasuryError(
                "Stale browser or review file; reload the current version"
            )
        if current["status"] == "accepted":
            raise TreasuryError(
                "Accepted versions are immutable; start a new archive run"
            )
        prepared = read_json(output / "prepared_inputs.json")
        if digest(prepared) != state["prepared_sha256"]:
            raise TreasuryError("Prepared inputs were changed")
        merged = {**current["decisions"], **(decisions or {})}
        record = build_forecast(
            prepared["inputs"],
            previous=prepared["previous"],
            decisions=merged,
            review=review,
        )
        _store(output, state, record)
        return record
