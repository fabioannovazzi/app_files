"""Closed, content-free lifecycle fields and explicitly authored user feedback."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["WorkflowEvent", "pipeline_catalog"]


def pipeline_catalog() -> dict[str, str]:
    """Read the shipped user-process inventory; infrastructure has no rating."""
    path = Path(__file__).resolve().parents[2] / "plugins/vera/usage/pipelines.json"
    return json.loads(path.read_text(encoding="utf-8"))["pipelines"]


class WorkflowEvent(BaseModel):
    """Exact IDs, event ordering and field shapes are mechanical invariants."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    event_id: UUID
    run_id: UUID
    sequence: int = Field(ge=1, le=10000)
    kind: Literal[
        "started",
        "resumed",
        "completed",
        "failed",
        "cancelled",
        "receipt",
        "feedback_prompted",
        "feedback",
        "incident",
    ]
    occurred_at: datetime
    product_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=32)
    pipeline: str | None = Field(default=None, max_length=80)
    host: Literal["codex", "cowork", "chatgpt", "antigravity", "unknown"] | None = None
    sample_kind: Literal["user", "synthetic", "agent_test"] | None = None
    receipt_id: UUID | None = None
    receipt_version: str | None = Field(
        default=None, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=32
    )
    report_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    incident_report_id: UUID | None = None
    stars: int | None = Field(default=None, ge=1, le=5, strict=True)
    comment: str | None = Field(default=None, max_length=2000)
    feedback_source: Literal["user_chat", "user_form", "synthetic_test"] | None = None

    @model_validator(mode="after")
    def exact_event_shape(self) -> WorkflowEvent:
        """Reject accidental case fields and incomplete event-specific evidence."""
        if self.occurred_at.tzinfo is None:
            raise ValueError("A timezone is required")
        groups = {
            "started": {"pipeline", "host", "sample_kind"},
            "receipt": {"receipt_id", "receipt_version", "report_sha256"},
            "feedback": {"stars", "feedback_source", "comment"},
            "incident": {"incident_report_id"},
        }
        optional = {name for names in groups.values() for name in names}
        allowed = groups.get(self.kind, set())
        present = {name for name in optional if getattr(self, name) is not None}
        if present - allowed or (allowed - {"comment"}) - present:
            raise ValueError("Fields do not match this event kind")
        if self.kind == "started" and self.pipeline not in pipeline_catalog():
            raise ValueError("Unknown user-facing pipeline")
        return self
