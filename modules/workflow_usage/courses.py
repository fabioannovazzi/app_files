"""Completion of a Vera lesson is independent of any professional workflow run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator

__all__ = ["Completion", "SCHEMA", "record", "levels"]

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS vera_course_completions (event_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL, course_id TEXT NOT NULL, completed_at TEXT NOT NULL)",
)


def _catalogue() -> set[str]:
    path = (
        Path(__file__).resolve().parents[2] / "plugins/vera/assets/courses/index.json"
    )
    return {"get-started", *json.loads(path.read_bytes())["courses"]}


class Completion(BaseModel):
    """Only these three fields may leave a completed lesson checkpoint."""

    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    course_id: str
    completed_at: AwareDatetime

    @field_validator("course_id")
    @classmethod
    def known_course(cls, value: str) -> str:
        if value not in _catalogue():
            raise ValueError("Unknown Vera course")
        return value


def record(
    connection: Any, sql: Callable[[str], str], owner: str, event: Completion
) -> bool:
    """Replays must refer to exactly the same installation and completion."""
    values = (
        str(event.event_id),
        owner,
        event.course_id,
        event.completed_at.isoformat(),
    )
    connection.execute(
        sql(
            "INSERT INTO vera_course_completions VALUES (?,?,?,?) ON CONFLICT (event_id) DO NOTHING"
        ),
        values,
    )
    row = connection.execute(
        sql("SELECT * FROM vera_course_completions WHERE event_id=?"), (values[0],)
    ).fetchone()
    return (row["installation_id"], row["course_id"], row["completed_at"]) == values[1:]


def levels(connection: Any, sql: Callable[[str], str]) -> dict[str, str]:
    """Count distinct proven computers per course, retaining unattributed completions."""
    epoch = connection.execute(
        sql(
            "SELECT e.agent_devices_json FROM vera_workflow_testing_epochs e LEFT JOIN workflow_testing_epoch_products p ON p.epoch_id=e.epoch_id "
            "WHERE COALESCE(p.product,'vera')='vera' ORDER BY e.started_at DESC,e.epoch_id DESC LIMIT 1"
        )
    ).fetchone()
    agents = set(json.loads(epoch["agent_devices_json"])) if epoch else set()
    by_course: dict[str, set[str | None]] = {}
    for row in connection.execute(
        sql(
            "SELECT DISTINCT c.course_id,d.device_id FROM vera_course_completions c "
            "LEFT JOIN operational_device_links d ON d.installation_id=c.installation_id"
        )
    ).fetchall():
        by_course.setdefault(row["course_id"], set()).add(row["device_id"])
    result = dict.fromkeys(_catalogue(), "untried")
    for course, computers in by_course.items():
        if course not in result:
            continue
        professional = len(computers - agents - {None}) if epoch else 0
        if professional >= 3:
            result[course] = "repeated"
        elif professional:
            result[course] = "tried"
        elif computers & agents:
            result[course] = "agent"
        else:
            result[course] = "completed"
    # Agent acceptance is independent of learner finishes. It can supply the
    # quarter circle, but must never add a machine or hide a higher status.
    evidence = json.loads(
        Path(__file__).with_name("course_agent_evidence.json").read_bytes()
    )
    for course in evidence["courses"]:
        if result.get(course) in {"untried", "completed"}:
            result[course] = "agent"
    return result
