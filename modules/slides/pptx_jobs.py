from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from modules.utilities.json_record_store import JsonRecordStore

__all__ = [
    "PptxJob",
    "cleanup_expired_jobs",
    "create_job",
    "get_job",
    "mark_interrupted_jobs",
    "set_output_path",
    "update_job_status",
]

LOGGER = logging.getLogger(__name__)

_STORE_PATH = Path("tmp/pptx_jobs/pptx_jobs.json").resolve()
_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
_STORE = JsonRecordStore(_STORE_PATH)


@dataclass
class PptxJob:
    job_id: str
    deck_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    created_at: datetime
    source: Literal["rendered", "template"] = "rendered"
    detail: str | None = None
    output_path: Path | None = None


def _row_to_job(row: dict) -> PptxJob:
    created_at = datetime.fromisoformat(str(row["created_at"]))
    output_path = (
        Path(str(row["output_path"])).resolve() if row.get("output_path") else None
    )
    source = "rendered"
    source_value = str(row.get("source") or "").strip().lower()
    if source_value in {"rendered", "template"}:
        source = source_value
    return PptxJob(
        job_id=str(row["job_id"]),
        deck_id=str(row["deck_id"]),
        source=source,
        status=row["status"],
        detail=row.get("detail"),
        output_path=output_path,
        created_at=created_at,
    )


def create_job(
    job_id: str,
    deck_id: str,
    *,
    source: Literal["rendered", "template"] = "rendered",
) -> PptxJob:
    """Persist a new PPTX job and return the record."""
    created_at = datetime.now(UTC)
    _STORE.upsert(
        job_id,
        {
            "job_id": job_id,
            "deck_id": deck_id,
            "source": source,
            "status": "pending",
            "detail": None,
            "output_path": None,
            "created_at": created_at.isoformat(),
        },
    )
    return PptxJob(
        job_id=job_id,
        deck_id=deck_id,
        source=source,
        status="pending",
        created_at=created_at,
    )


def get_job(job_id: str) -> PptxJob | None:
    """Fetch a PPTX job by ID."""
    row = _STORE.get(job_id)
    if row is None:
        return None
    return _row_to_job(row)


def update_job_status(job_id: str, status: str, detail: str | None = None) -> None:
    """Update the status and optional detail message for a job."""
    _STORE.update(job_id, lambda row: {**row, "status": status, "detail": detail})


def mark_interrupted_jobs() -> int:
    """Fail PPTX jobs that cannot continue after a server restart."""

    detail = "PPTX export interrupted by server restart. Please run it again."
    rows = [
        row
        for row in _STORE.all()
        if str(row.get("status") or "") in {"pending", "running"}
    ]
    for row in rows:
        _STORE.update(
            str(row.get("job_id") or ""),
            lambda current: {**current, "status": "failed", "detail": detail},
        )
    return len(rows)


def set_output_path(job_id: str, output_path: Path | None) -> None:
    """Persist the output path for a job."""
    output_value = str(output_path) if output_path else None
    _STORE.update(job_id, lambda row: {**row, "output_path": output_value})


def cleanup_expired_jobs(ttl: timedelta) -> None:
    """Remove expired jobs and delete any associated output files."""
    cutoff = datetime.now(UTC) - ttl
    rows = [
        row
        for row in _STORE.all()
        if datetime.fromisoformat(str(row.get("created_at"))) < cutoff
    ]
    _STORE.delete_where(
        lambda row: datetime.fromisoformat(str(row.get("created_at"))) < cutoff
    )
    output_dir = _STORE_PATH.parent
    for row in rows:
        job_id = str(row["job_id"])
        output_path = row.get("output_path")
        paths_to_remove = [
            output_dir / f"{job_id}.pptx",
            output_dir / f"{job_id}.pptx.tmp",
        ]
        if output_path:
            paths_to_remove.append(Path(output_path))
        for path in paths_to_remove:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                LOGGER.warning("Failed to delete output path %s", path, exc_info=True)
