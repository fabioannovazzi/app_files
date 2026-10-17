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
    owner: Literal["monitor", "vera", "fabio"]
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
    observed: str = Field(min_length=1, max_length=1500)
    inferred: str = Field(min_length=1, max_length=1500)
    unknown: str = Field(min_length=1, max_length=1500)
    blocker: str = Field(min_length=1, max_length=1500)
    next_action: NextAction
    next_check_at: datetime

    @field_validator("observed", "inferred", "unknown", "blocker")
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
        return "non disponibile"
    return (
        datetime.fromisoformat(value)
        .astimezone(ZoneInfo("Europe/Paris"))
        .strftime("%d/%m/%Y %H:%M %Z")
    )


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
    if review.next_action.owner == "vera" and (
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
        else (f"Computer {device_id[:8]}" if device_id else "Computer non identificato")
    )
    app_link = followup.get("app_link")
    app = app_link["native_app"] if app_link else followup["host"]
    app_name = {"cowork": "Claude Cowork", "codex": "Codex"}.get(
        app, "App non identificata"
    )
    if not app_link:
        app_name += " (dichiarata, collegamento non verificato)"
    contact = followup["reporter_contact"]
    contact_text = (
        f"{_date(contact['last_seen'])}; Vera {contact['product_version']} osservata dal reporter originale"
        if contact
        else "nessun contatto del reporter originale registrato"
    )
    state_names = {
        "published-awaiting-receipt": "pubblicato, ricevuta assente",
        "received-awaiting-reply": "ricevuto, risposta diagnostica assente",
        "responded": "risposta diagnostica ricevuta; recupero non dimostrato",
        "received-awaiting-action": "ricevuto, applicazione non registrata",
        "applied-awaiting-original-task": "applicato, attività originale ancora da verificare",
        "retry-in-progress": "tentativo originale avviato, esito assente",
        "retry-failed": "tentativo originale fallito",
        "outcome-failed": "esito di fallimento registrato",
        "action-required": "richiesto intervento",
        "evidence-unavailable": "evidenza tecnica non disponibile",
        "awaiting-original-task-verification": "tentativo riuscito, verifica originale assente",
        "verified-recovered": "attività originale verificata con esito positivo",
    }
    owner = {
        "monitor": "Agente di monitoraggio",
        "vera": "Vera interessata",
        "fabio": "Fabio",
    }[review.next_action.owner]
    identity = f"{machine} · {app_name}"
    if device_id and proven_label:
        identity += f" · codice {device_id[:8]}"
    rows = [
        ("Installazione", identity),
        (
            "Segnalazione originale",
            f"{_date(followup['original_reported_at'])} · {followup['workflow']} · Vera {followup['original_version']}",
        ),
        (
            "Rimedio",
            f"{followup['remedy_kind']} · revisione {review.remedy_revision}"
            + (
                f" · versione proposta {followup['required_version']}"
                if followup["required_version"]
                else ""
            )
            + f" · {state_names[followup['state']]}",
        ),
        ("Ultimo contatto", contact_text),
        ("Fatti", review.observed),
        ("Valutazione", review.inferred),
        ("Non sappiamo", review.unknown),
        ("Blocco", review.blocker),
        ("Prossima azione", f"{owner}: {review.next_action.instruction}"),
        ("Motivo", review.next_action.reason),
        ("Prossimo controllo", _date(review.next_check_at.isoformat())),
        (
            "Verifica richiesta",
            "Successo della stessa attività e degli stessi input, per il rapporto originale e la revisione applicabile. Un aggiornamento o una ricevuta non bastano.",
        ),
    ]
    body = "".join(
        f"<p><strong>{html.escape(key)}:</strong> {html.escape(value)}</p>"
        for key, value in rows
    )
    body += f'<p><a href="{CHAT_URL}">Vera incident monitoring</a>: apre la chat in Codex. Caso {html.escape(incident["incident_id"][:8])}.</p>'
    # Wording and scheduled check dates are not new recovery events.
    event_key = (
        f"{incident['incident_id']}|{followup['attention_key']}|actionable-followup|"
        f"{review.next_action.owner}|{review.next_action.action_id}"
    )
    return {
        "subject": f"Vera: {identity} · {followup['workflow']}",
        "html": body,
        "event_key": event_key,
        "report_id": followup["report_id"],
        "remedy_revision": review.remedy_revision,
        "next_action_owner": review.next_action.owner,
        "next_check_at": review.next_check_at.isoformat(),
        "original_task_verified": followup["original_task_verified"],
    }
