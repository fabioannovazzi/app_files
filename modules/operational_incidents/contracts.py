"""Fixed transport and recovery boundaries; diagnosis remains model-led."""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

__all__ = [
    "Diagnostic",
    "TechnicalFrame",
    "Report",
    "Remedy",
    "Credentials",
    "DeviceCredentials",
    "ReporterStatus",
    "Outcome",
    "RecoveryEvent",
    "scrub",
]

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


class DeviceCredentials(StrictModel):
    """Proof of an anonymous identity persisted by the native host helper."""

    device_id: UUID
    device_key: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    native_app: Literal["codex", "cowork"] | None = None


class ReporterStatus(StrictModel):
    """Observed reporting-process capabilities, separate from an old failure."""

    session_id: UUID
    protocol: int = Field(ge=0, le=3)
    product_version: str = Field(
        min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.+-]+$"
    )
    host: Literal["codex", "cowork", "unknown"]
    platform: Literal["macos", "windows", "linux", "unknown"]
    runtime_version: str | None = Field(
        default=None, max_length=100, pattern=r"^[A-Za-z0-9_. +()-]+$"
    )


class TechnicalFrame(StrictModel):
    """Package-relative source coordinates; never locals, arguments or case text."""

    file: str = Field(max_length=250, pattern=r"^[A-Za-z0-9_./-]+$")
    line: int = Field(ge=1)
    function: str = Field(max_length=200, pattern=r"^[A-Za-z0-9_.<>]+$")

    @field_validator("file")
    @classmethod
    def relative_source(cls, value: str) -> str:
        if value.startswith("/") or ".." in value.split("/"):
            raise ValueError("Technical source must be package-relative")
        return value


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
    technical_frames: list[TechnicalFrame] = Field(default_factory=list, max_length=100)
    technical_facts: dict[str, StrictInt | StrictBool] = Field(
        default_factory=dict, max_length=100
    )

    @field_validator("technical_facts")
    @classmethod
    def technical_fact_labels(
        cls, values: dict[str, int | bool]
    ) -> dict[str, int | bool]:
        """Keep producer-selected measurements separate from redacted prose."""
        if any(not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key) for key in values):
            raise ValueError("Technical fact labels must be technical identifiers")
        return values

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        return scrub(value)


class Report(StrictModel):
    evidence_for_report_id: UUID | None = None
    response_to_remedy_revision: int | None = Field(default=None, ge=1)
    report_id: UUID
    product: Literal["vera", "clara", "lucia"] = "vera"
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
    worker_runtime_version: str | None = Field(
        default=None, max_length=100, pattern=r"^[A-Za-z0-9_. +()-]+$"
    )
    worker_platform: Literal["macos", "windows", "linux", "unknown"] | None = None
    workflow: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    stage: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    diagnostics: list[Diagnostic] = Field(min_length=1, max_length=512)
    measurements: dict[str, int | bool] = Field(default_factory=dict, max_length=100)
    unavailable: list[str] = Field(default_factory=list, max_length=100)
    capture_state: Literal["legacy", "pending", "complete", "unavailable"] = "legacy"
    session_id: UUID | None = None
    operation_id: UUID | None = None
    input_binding: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def structured_capture(self) -> Report:
        """A completeness claim requires an actual technical code or source location."""
        if (
            self.response_to_remedy_revision is not None
            and self.evidence_for_report_id is None
        ):
            raise ValueError("A diagnostic reply must supplement its original report")
        if self.capture_state == "complete" and not any(
            item.error_code or item.technical_frames for item in self.diagnostics
        ):
            raise ValueError("Complete capture requires technical evidence")
        return self

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
    target_report_id: UUID | None = None
    kind: Literal[
        "investigating",
        "diagnostic-request",
        "resume",
        "update",
        "automatic",
        "user-action",
    ]
    summary: str = Field(min_length=1, max_length=4000)
    evidence: str = Field(min_length=1, max_length=16000)
    required_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    action: Literal["retry-dependency-setup", "retry-verified-preparation"] | None = (
        None
    )
    instructions: str | None = Field(default=None, max_length=8000)
    expected_outcome: str = Field(min_length=1, max_length=4000)
    requested_evidence: list[
        Literal[
            "retained-technical-error",
            "package-integrity",
            "worker-runtime",
            "host-tool-availability",
            "original-task-availability",
        ]
    ] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def agent_exchange(self) -> Remedy:
        """Limit requests to technical evidence; no remote executable payloads."""
        if self.kind == "diagnostic-request" and (
            not self.requested_evidence or not self.instructions
        ):
            raise ValueError(
                "A diagnostic request needs evidence fields and instructions"
            )
        if self.kind != "diagnostic-request" and self.requested_evidence:
            raise ValueError("Only a diagnostic request can request evidence")
        if self.kind == "resume" and not self.instructions:
            raise ValueError("Resuming the original task needs diagnosed instructions")
        return self


class Outcome(StrictModel):
    report_id: UUID | None = None
    outcome_id: UUID
    incident_id: UUID
    remedy_revision: int = Field(ge=1)
    status: Literal["recovered", "failed", "action-required"]
    diagnostics: list[Diagnostic] = Field(default_factory=list, max_length=512)
    execution_succeeded: bool = False
    operation_id: UUID | None = None
    input_binding: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    original_task_verified: bool = False


class RecoveryEvent(StrictModel):
    """An observed step for one original report and applicable remedy revision."""

    event_id: UUID
    incident_id: UUID
    report_id: UUID
    remedy_revision: int = Field(ge=1)
    kind: Literal[
        "remedy-received",
        "remedy-applied",
        "retry-started",
        "retry-failed",
        "retry-succeeded",
        "capture-unavailable",
    ]
    operation_id: UUID | None = None
