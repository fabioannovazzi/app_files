"""Offline interview handoff: versioned UTF-8 text, never executable instructions."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from construction_core import digest, fields, require, text

__all__ = ["import_intake", "parse_markdown", "render_form", "render_markdown"]

INTAKE_SCHEMA = "vera.assetti_intake.v1"
PREFIX = "# Scheda di visita per Vera\n\n```assetti-intake-json\n"


def render_markdown(payload: dict) -> str:
    """Keep delimiter characters escaped in JSON and indent human-readable answers."""
    encoded = json.dumps(
        payload, ensure_ascii=False, indent=2, allow_nan=False
    ).replace("`", "\\u0060")
    lines = [
        PREFIX + encoded + "\n```\n",
        "Le risposte sono dichiarazioni da verificare; non approvano voti o esclusioni.\n",
    ]
    for answer in payload["answers"]:
        lines.append(f"## {answer['question_id']}\n")
        for value in (
            answer["question"],
            answer["status"],
            answer["original"],
            answer["notes"],
            ", ".join(answer["attachment_refs"]),
        ):
            lines.append("\n".join("    " + line for line in value.split("\n")) + "\n")
    return "\n".join(lines)


def parse_markdown(content: str) -> dict:
    """Reject ambiguous or malformed versions; the readable text must match JSON."""
    require(content.startswith(PREFIX), "Not a supported Vera intake Markdown")
    encoded, separator, _ = content[len(PREFIX) :].partition("\n```\n")
    require(bool(separator), "Missing structured intake terminator")
    payload = json.loads(encoded)
    require(
        isinstance(payload, dict) and payload.get("schema_version") == INTAKE_SCHEMA,
        "Unsupported intake schema",
    )
    fields(
        payload,
        "practice_id",
        "client_id",
        "engagement_id",
        "session_id",
        "date",
        "declared_author",
        "questionnaire_version",
    )
    require(
        type(payload.get("revision")) is int and payload["revision"] >= 1,
        "Invalid intake revision",
    )
    require(
        payload.get("mode") in {"html", "text", "reviewed_transcript"},
        "Unsupported intake mode",
    )
    require(isinstance(payload.get("answers"), list), "Missing interview answers")
    seen = set()
    for answer in payload["answers"]:
        fields(answer, "question_id", "question", "status")
        require(answer["question_id"] not in seen, "Duplicate intake question")
        seen.add(answer["question_id"])
        require(
            answer["status"] in {"answered", "to_verify", "unknown"},
            "Invalid intake answer state",
        )
        require(
            isinstance(answer.get("original"), str)
            and isinstance(answer.get("notes"), str),
            "Answer and notes must be text",
        )
        require(
            isinstance(answer.get("attachment_refs"), list)
            and all(isinstance(x, str) for x in answer["attachment_refs"]),
            "Invalid attachment references",
        )
        require(
            isinstance(answer.get("criterion_ids"), list),
            "Missing answer criterion bindings",
        )
        require(
            not any(
                k in answer
                for k in (
                    "score",
                    "qualification_review",
                    "na_approved",
                    "professional_decision",
                )
            ),
            "Intake cannot approve assessments",
        )
    require(
        content == render_markdown(payload),
        "Readable answers differ from structured data; re-export the edited draft",
    )
    return payload


def import_intake(
    state: dict, payload: dict, *, source_id: str, actor: str, at: str
) -> None:
    """Consume a bound original once, with explicit conflicts for parallel edits."""
    from construction_core import _put

    require(
        payload["practice_id"] == state["case_id"]
        and payload["client_id"] == state["client_id"]
        and payload["engagement_id"] == state["engagement_id"],
        "Intake belongs to another practice",
    )
    require(
        payload["questionnaire_version"] == state["catalog"]["methodology_version"],
        "Questionnaire version changed",
    )
    require(source_id in state["evidence"], "Import the original interview file first")
    sessions = state.setdefault("intake_sessions", {})
    sid = payload["session_id"]
    previous = sessions.get(sid)
    current_digest = digest(payload)
    if previous:
        if previous["payload_sha256"] == current_digest:
            return
        require(
            payload["revision"] > previous["revision"],
            "Conflicting intake revision; compare both drafts",
        )
        require(
            payload.get("parent_sha256") == previous["payload_sha256"],
            "Conflicting intake parent; compare both drafts",
        )
    known = {c["id"] for c in state["catalog"]["criteria"]}
    for row in payload["answers"]:
        require(
            all(cid in known for cid in row["criterion_ids"]),
            "Unknown intake criterion",
        )
        answer = {
            "id": sid + "/" + row["question_id"],
            "question_id": row["question_id"],
            "question": row["question"],
            "original": row["original"] or "Non fornito",
            "summary": "",
            "speaker": payload["declared_author"],
            "date": payload["date"],
            "mode": payload["mode"],
            "status": row["status"],
            "criterion_ids": row["criterion_ids"],
            "evidence_refs": [source_id],
            "attachment_refs": row["attachment_refs"],
            "notes": row["notes"],
            "unresolved_attachment_refs": [
                r for r in row["attachment_refs"] if r not in state["evidence"]
            ],
        }
        _put(state, "answers", answer, actor, at)
    sessions[sid] = {
        "unobserved_parent_sha256": (
            previous.get("unobserved_parent_sha256")
            if previous
            else payload.get("parent_sha256")
        ),
        "revision": payload["revision"],
        "payload_sha256": current_digest,
        "source_id": source_id,
        "payload": payload,
    }


def render_form(state: dict, *, questions: list[dict] | None = None) -> str:
    """Emit a standalone page; no remote assets, storage, microphone or network."""
    sessions = list(state.get("intake_sessions", {}).values())
    saved = sessions[-1]["payload"] if sessions else None
    if (
        saved
        and saved["questionnaire_version"] != state["catalog"]["methodology_version"]
    ):
        saved = None
    if questions is None and saved:
        questions = [
            {
                "id": r["question_id"],
                "question": r["question"],
                "criterion_ids": r["criterion_ids"],
            }
            for r in saved["answers"]
        ]
    if questions is None:
        questions = [
            {
                "id": "OPENING",
                "question": "Raccontami come funziona l’azienda e chi segue le attività principali.",
                "criterion_ids": [],
            }
        ]
        questions.extend(
            {"id": c["id"], "question": c["question"], "criterion_ids": [c["id"]]}
            for c in state["catalog"]["criteria"]
        )
    require(
        isinstance(questions, list) and bool(questions), "Provide at least one question"
    )
    known = {c["id"] for c in state["catalog"]["criteria"]}
    seen = set()
    for question in questions:
        fields(question, "id", "question")
        require(question["id"] not in seen, "Duplicate question ID")
        seen.add(question["id"])
        require(
            isinstance(question.get("criterion_ids"), list)
            and all(cid in known for cid in question["criterion_ids"]),
            "Unknown question criterion",
        )
    initial = None
    if saved:
        initial = json.loads(json.dumps(saved))
        previous = {row["question_id"]: row for row in initial["answers"]}
        for question in questions:
            if question["id"] in previous:
                original = previous[question["id"]]
                require(
                    original["question"] == question["question"]
                    and original["criterion_ids"] == question["criterion_ids"],
                    "A changed question needs a new ID; preserve its original answer",
                )
            else:
                initial["answers"].append(
                    {
                        "question_id": question["id"],
                        "question": question["question"],
                        "criterion_ids": question["criterion_ids"],
                        "original": "",
                        "status": "unknown",
                        "notes": "",
                        "attachment_refs": [],
                    }
                )
        questions = [
            {
                "id": row["question_id"],
                "question": row["question"],
                "criterion_ids": row["criterion_ids"],
            }
            for row in initial["answers"]
        ]
    config = {
        "schema_version": INTAKE_SCHEMA,
        "practice_id": state["case_id"],
        "client_id": state["client_id"],
        "engagement_id": state["engagement_id"],
        "questionnaire_version": state["catalog"]["methodology_version"],
        "entity_name": state["entity_name"],
        "questions": questions,
        "saved_intake": saved,
        "initial_intake": initial,
        "resume_summary": state["cursor"].get("summary", ""),
        "next_step": state["cursor"].get("next_step", ""),
    }
    template = (
        Path(__file__).resolve().parents[1] / "assets/construction-intake.html"
    ).read_text(encoding="utf-8")
    encoded = (
        json.dumps(config, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    module = Path(__file__).resolve().parents[1]
    candidates = [
        module / "vendor/modules/courseware/assets/InstrumentSans-Regular.ttf",
        module.parent.parent
        / "vendor/modules/courseware/assets/InstrumentSans-Regular.ttf",
        module.parent
        / "_shared/vendor/modules/courseware/assets/InstrumentSans-Regular.ttf",
    ]
    font = next((p for p in candidates if p.is_file()), None)
    font_face = (
        "@font-face{font-family:'Instrument Sans';font-style:normal;font-weight:100 900;src:url(data:font/ttf;base64,"
        + base64.b64encode(font.read_bytes()).decode()
        + ") format('truetype');}"
        if font
        else ""
    )
    return (
        template.replace("__CASE_TITLE__", html.escape(state["entity_name"]))
        .replace("__CONFIG_JSON__", encoded)
        .replace("__FONT_FACE__", font_face)
    )
