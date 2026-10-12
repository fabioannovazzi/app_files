"""Fixed transport and recovery boundaries; diagnosis remains model-led."""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ["Diagnostic", "Report", "Remedy", "Credentials", "Outcome", "scrub"]

# These rules remove mechanically identifiable paths/credentials from technical
# messages. They do not decide the incident's cause or classify user documents.
_PRIVATE_PATTERNS = (
    re.compile(
        r"(?i)\b(?:authorization|password|passwd|secret|token|api[_-]?key)\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]+\b"),
    re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\r\n\"'<>|:;]+"),
    re.compile(r"/(?:Users|home|root|private|tmp|var|mnt|Volumes)/[^\r\n\"'<>|:;]+"),
    re.compile(r"https?://[^\s\"'<>]+"),
)


def scrub(value: str) -> str:
    """Remove path, network target and secret values without truncating errors."""
    result = value
    for pattern in _PRIVATE_PATTERNS:
        result = pattern.sub("[private value removed]", result)
    return result


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    installation_id: UUID
    installation_key: str = Field(
        min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )


class Diagnostic(StrictModel):
    component: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    error_type: str = Field(min_length=1, max_length=150, pattern=r"^[A-Za-z0-9_.:-]+$")
    error_code: str | None = Field(
        default=None, max_length=150, pattern=r"^[A-Za-z0-9_.: -]+$"
    )
    errno: int | None = None
    exit_code: int | None = None
    message: str = Field(min_length=1, max_length=65536)
    stage: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    evidence_source: Literal[
        "observed-tool-result", "runtime-exception", "technical-log"
    ]

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        return scrub(value)


class Report(StrictModel):
    report_id: UUID
    product: Literal["vera"] = "vera"
    product_version: str = Field(
        min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.+-]+$"
    )
    host: Literal["codex", "cowork", "unknown"]
    platform: Literal["macos", "windows", "linux", "unknown"]
    host_version: str | None = Field(
        default=None, max_length=100, pattern=r"^[A-Za-z0-9_. +()-]+$"
    )
    runtime_version: str | None = Field(
        default=None, max_length=100, pattern=r"^[A-Za-z0-9_. +()-]+$"
    )
    workflow: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    stage: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    diagnostics: list[Diagnostic] = Field(min_length=1, max_length=512)
    measurements: dict[str, int | bool] = Field(default_factory=dict, max_length=100)
    unavailable: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("unavailable")
    @classmethod
    def clean_unavailable(cls, values: list[str]) -> list[str]:
        if any(len(value) > 2000 for value in values):
            raise ValueError("An unavailable-measurement explanation is too long")
        return [scrub(value) for value in values]

    @field_validator("measurements")
    @classmethod
    def mechanical_labels(cls, values: dict[str, Any]) -> dict[str, Any]:
        if any(not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key) for key in values):
            raise ValueError("Measurement labels must be technical identifiers")
        return values


class Remedy(StrictModel):
    kind: Literal["investigating", "update", "automatic", "user-action"]
    summary: str = Field(min_length=1, max_length=4000)
    evidence: str = Field(min_length=1, max_length=16000)
    required_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    action: Literal["retry-dependency-setup", "retry-verified-preparation"] | None = (
        None
    )
    instructions: str | None = Field(default=None, max_length=8000)
    expected_outcome: str = Field(min_length=1, max_length=4000)


class Outcome(StrictModel):
    report_id: UUID | None = None
    outcome_id: UUID
    incident_id: UUID
    remedy_revision: int = Field(ge=1)
    status: Literal["recovered", "failed", "action-required"]
    diagnostics: list[Diagnostic] = Field(default_factory=list, max_length=512)
    execution_succeeded: bool = False
