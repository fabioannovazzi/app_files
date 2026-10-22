"""Evidence-bound alert rendering; diagnosis and next-action choice remain AI-led."""

from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.operational_incidents.contracts import scrub

__all__ = ["AlertReview", "followup_hash", "render_alert"]

CHAT_URL = "codex://threads/01a13901-2f7d-72a2-ba4c-fd1b1a898889"


class NextAction(BaseModel):
    """An agent-selected action, accountable owner and inspected justification."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$")
    owner: Literal["monitor", "vera", "clara", "lucia", "fabio"]
    instruction: str = Field(min_length=1, max_length=1500)
    reason: str = Field(min_length=1, max_length=1500)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    @field_validator("instruction", "reason")
    @classmethod
    def technical_text(cls, value: str) -> str:
        return scrub(value)


class AlertReview(BaseModel):
    """Require an exact reviewed episode, blocker, unknowns and scheduled action."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    incident_id: UUID
    report_id: UUID
    remedy_revision: int = Field(ge=1)
    followup_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    impact: str = Field(min_length=1, max_length=1500)
    actions_taken: str = Field(min_length=1, max_length=2000)
    user_action: str = Field(min_length=1, max_length=1500)
    verification: str = Field(min_length=1, max_length=1500)
    observed: str = Field(min_length=1, max_length=1500)
    inferred: str = Field(min_length=1, max_length=1500)
    unknown: str = Field(min_length=1, max_length=1500)
    blocker: str = Field(min_length=1, max_length=1500)
    next_action: NextAction
    next_check_at: datetime

    @field_validator(
        "observed",
        "inferred",
        "unknown",
        "blocker",
        "impact",
        "actions_taken",
        "user_action",
        "verification",
    )
    @classmethod
    def technical_text(cls, value: str) -> str:
        return scrub(value)

    @field_validator("next_check_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Next check requires a timezone")
        local = value.astimezone(ZoneInfo("Europe/Paris"))
        if not (
            8 <= local.hour < 23
            or (local.hour == 23 and local.minute == 0 and local.second == 0)
        ):
            raise ValueError(
                "Next check must be inside the monitoring operating window"
            )
        return value


def followup_hash(followup: dict[str, Any]) -> str:
    """Bind AI review to the exact identity, delivery and progress inspected."""
    return hashlib.sha256(
        json.dumps(
            followup, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _date(value: str | None) -> str:
    if value is None:
        return "not available"
    return (
        datetime.fromisoformat(value)
        .astimezone(ZoneInfo("Europe/Paris"))
        .strftime("%d/%m/%Y %H:%M %Z")
    )


def _technical_details(incident: dict[str, Any], report_id: str) -> str:
    """Expose exact source locations and producer facts for the reviewed report."""
    details = []
    for report in [*incident.get("reports", []), *incident.get("evidence", [])]:
        if (
            report.get("report_id") != report_id
            and report.get("evidence_for_report_id") != report_id
        ):
            continue
        for diagnostic in report.get("diagnostics", []):
            frames = diagnostic.get("technical_frames", [])
            facts = diagnostic.get("technical_facts", {})
            if not frames and not facts:
                continue
            parts = [diagnostic["error_type"]]
            parts.extend(
                f"{frame['file']}:{frame['line']} ({frame['function']})"
                for frame in frames
            )
            for key, value in facts.items():
                if type(value) is bool:
                    rendered = "yes" if value else "no"
                elif key in {
                    "archive_state.mode",
                    "archive_state.private_creation_mode",
                    "archive_state.forbidden_mode_bits",
                }:
                    rendered = f"0o{value:o}"
                else:
                    rendered = str(value)
                parts.append(f"{key}={rendered}")
            details.append("; ".join(parts))
    return " | ".join(dict.fromkeys(details))


def render_alert(
    incident: dict[str, Any],
    review: AlertReview,
    device_labels: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Render observed metadata, never raw diagnostics or guessed machine ownership.

    Fixed matching/escaping makes assertions inspectable and prevents stale
    reviews or an unreceived remedy from being reported as an active Vera task.
    Semantics, diagnosis and the choice of justified action belong to the agent.
    """
    if str(review.incident_id) != incident["incident_id"]:
        raise ValueError("Review belongs to another incident")
    followup = next(
        (
            row
            for row in incident["remedy_followups"]
            if row["report_id"] == str(review.report_id)
            and row["remedy_revision"] == review.remedy_revision
        ),
        None,
    )
    if followup is None or followup_hash(followup) != review.followup_sha256:
        raise ValueError("Review must match the current exact followup evidence")
    if review.next_check_at <= (now or datetime.now(timezone.utc)):
        raise ValueError("Next check must be in the future")
    product = followup.get("product", "vera")
    title = product.title()
    if (
        review.next_action.owner in {"vera", "clara", "lucia"}
        and review.next_action.owner != product
    ):
        raise ValueError("The next action belongs to another product")
    if review.next_action.owner in {"vera", "clara", "lucia"} and (
        not followup["received_at"] or followup["overdue"]
    ):
        raise ValueError(
            "An unreceived or overdue remedy needs a monitor or justified human action"
        )
    device_id = followup.get("device_id")
    label = device_labels.get(device_id, {})
    proven_label = bool(label.get("verified_at") and label.get("evidence_ref"))
    machine = (
        label["label"]
        if proven_label
        else (f"Computer {device_id[:8]}" if device_id else "Unidentified computer")
    )
    app_link = followup.get("app_link")
    app = app_link["native_app"] if app_link else followup["host"]
    app_name = {"cowork": "Claude Cowork", "codex": "Codex"}.get(
        app, "Unidentified app"
    )
    if not app_link:
        app_name += " (reported; app link unverified)"
    contact = followup["reporter_contact"]
    contact_text = (
        f"{_date(contact['last_seen'])}; {title} {contact['product_version']} observed at the original reporter contact"
        if contact
        else "no contact from the original reporter recorded"
    )
    state_names = {
        "investigating": "investigating; no remedy assigned",
        "published-awaiting-receipt": "published; receipt unconfirmed",
        "received-awaiting-reply": "received; diagnostic reply missing",
        "responded": "diagnostic reply received; recovery unverified",
        "received-awaiting-action": "received; application unrecorded",
        "applied-awaiting-original-task": "applied; original task unverified",
        "retry-in-progress": "original retry started; result missing",
        "retry-failed": "original retry failed",
        "outcome-failed": "failure recorded",
        "action-required": "action required",
        "evidence-unavailable": "technical evidence unavailable",
        "awaiting-original-task-verification": "retry succeeded; original task unverified",
        "verified-recovered": "original task verified successfully",
    }
    owner = {
        "monitor": "Recovery monitor",
        "vera": "Affected Vera session",
        "clara": "Affected Clara session",
        "lucia": "Affected Lucia session",
        "fabio": "Fabio",
    }[review.next_action.owner]
    identity = f"{machine} · {app_name} · {followup.get('platform', 'unknown')} worker"
    if device_id and proven_label:
        identity += f" · ID {device_id[:8]}"
    rows = [
        ("Problem and impact", f"{review.observed} {review.impact}"),
        ("Diagnosis", review.inferred),
        ("Work done and result", review.actions_taken),
        ("Missing evidence and blocker", f"{review.unknown} {review.blocker}"),
        ("Next action", f"{owner}: {review.next_action.instruction}"),
        ("Action needed from Fabio", review.user_action),
        ("Success criterion", review.verification),
    ]
    technical = _technical_details(incident, str(review.report_id))
    if technical:
        rows.insert(2, ("Technical evidence", technical))
    body = "".join(
        f"<p><strong>{html.escape(key)}:</strong> {html.escape(value)}</p>"
        for key, value in rows
    )
    metadata = (
        f"{identity} · {followup['workflow']} · {title} {followup['original_version']}"
        f" · original failure {_date(followup['original_reported_at'])}. "
        f"{followup['remedy_kind']} revision {review.remedy_revision}: {state_names[followup['state']]}"
        + (
            f"; proposed version {followup['required_version']}"
            if followup["required_version"]
            else ""
        )
        + f". Last contact: {contact_text}. Next check: {_date(review.next_check_at.isoformat())}."
    )
    body += f'<p>{html.escape(metadata)}</p><p><a href="{CHAT_URL}">Vera incident monitoring</a>: opens the chat in Codex. Case {html.escape(incident["incident_id"][:8])}; report {html.escape(str(review.report_id)[:8])}.</p>'
    # Wording and scheduled check dates are not new recovery events.
    event_key = (
        f"{incident['incident_id']}|{followup['attention_key']}|actionable-followup|"
        f"{review.next_action.owner}|{review.next_action.action_id}"
    )
    return {
        "subject": f"{title}: {identity} · {followup['workflow']}",
        "html": body,
        "event_key": event_key,
        "report_id": followup["report_id"],
        "remedy_revision": review.remedy_revision,
        "next_action_owner": review.next_action.owner,
        "next_check_at": review.next_check_at.isoformat(),
        "original_task_verified": followup["original_task_verified"],
    }
