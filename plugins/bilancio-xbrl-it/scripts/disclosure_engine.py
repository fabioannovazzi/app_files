#!/usr/bin/env python3
"""Effective-dated disclosure coverage and dynamic-questionnaire engine.

Rule evaluation is deterministic because the rule pack is an explicit,
versioned contract and conditions inspect only exact case fields. Ambiguous
legal or accounting applicability must be represented by a reviewer-owned
manual trigger flag; this module does not infer it from account descriptions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from difflib import unified_diff
from typing import Any, Mapping, Sequence

from schedule_engine import required_schedule_types

__all__ = [
    "NOTE_SECTIONS",
    "build_disclosure_coverage",
    "disclosure_answer_complete",
    "disclosure_rule_pack_hash",
    "manual_disclosure_flags",
    "note_outline",
    "normalize_narrative_blocks",
    "narrative_redline",
    "prior_narrative_suggestions",
]

NOTE_SECTIONS = (
    ("INTRODUCTION", "Informazioni introduttive e forma del bilancio"),
    ("POLICIES", "Criteri di redazione e principi contabili"),
    ("ASSETS", "Commenti e movimenti dell'attivo"),
    ("LIABILITIES_EQUITY", "Commenti e movimenti di passivo e patrimonio netto"),
    ("INCOME_STATEMENT", "Informazioni sul conto economico"),
    ("TAXES", "Imposte correnti, anticipate e differite"),
    ("EMPLOYEES_BODIES", "Dipendenti e organi sociali"),
    ("COMMITMENTS_RELATED", "Impegni, garanzie, parti correlate e fuori bilancio"),
    ("FINANCIAL_INSTRUMENTS", "Strumenti finanziari e derivati"),
    ("LEASES", "Operazioni di locazione finanziaria"),
    ("GROUP_PARTICIPATIONS", "Gruppo e partecipazioni"),
    ("POST_CLOSING_GOING_CONCERN", "Fatti successivi e continuità aziendale"),
    ("RESULT_ALLOCATION", "Destinazione dell'utile o copertura della perdita"),
    ("ADDITIONAL", "Informazioni aggiuntive specifiche"),
)
QUESTION_STATES = {
    "NOT_TRIGGERED",
    "OPEN",
    "ASSIGNED",
    "ANSWERED_UNREVIEWED",
    "ACCEPTED",
    "REJECTED",
    "NOT_APPLICABLE_CONFIRMED",
}
ACCEPTED_ANSWER_STATES = {"ACCEPTED", "NOT_APPLICABLE_CONFIRMED"}


def _has_substantive_value(value: Any) -> bool:
    """Return whether a reviewed answer contains an explicit structured value."""

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value) and any(
            _has_substantive_value(item) for item in value.values()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return bool(value) and any(_has_substantive_value(item) for item in value)
    return True


def disclosure_answer_complete(answer: Mapping[str, Any]) -> bool:
    """Verify that a terminal answer records a real professional confirmation."""

    status = str(answer.get("status", "")).upper()
    if status not in ACCEPTED_ANSWER_STATES:
        return False
    if not str(answer.get("confirmed_by", "")).strip():
        return False
    if status == "NOT_APPLICABLE_CONFIRMED":
        return bool(str(answer.get("reason", "")).strip())
    return _has_substantive_value(answer.get("value"))


def disclosure_rule_pack_hash(rule_pack: Mapping[str, Any]) -> str:
    """Return the canonical checksum used to lock disclosure behavior."""

    encoded = json.dumps(
        rule_pack, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manual_disclosure_flags(rule_pack: Mapping[str, Any]) -> set[str]:
    """Return exact semantic flags whose applicability requires professional review."""

    flags: set[str] = set()

    def collect(condition: Mapping[str, Any]) -> None:
        kind = str(condition.get("kind", "")).upper()
        if kind == "MANUAL_FLAG":
            flags.add(str(condition["flag"]))
        for child in condition.get("conditions", []):
            if isinstance(child, Mapping):
                collect(child)

    for rule in rule_pack.get("rules", []):
        trigger = rule.get("trigger")
        if isinstance(trigger, Mapping):
            collect(trigger)
    return flags


def _statement_amount(case: Mapping[str, Any], canonical_line: str) -> Decimal:
    return sum(
        (
            Decimal(str(fact["current_value"]))
            for fact in (case.get("statements") or {}).get("facts", [])
            if fact.get("key") == canonical_line
        ),
        Decimal("0"),
    )


def _schedule_types(case: Mapping[str, Any], complete_only: bool = False) -> set[str]:
    return {
        str(item["schedule_type"])
        for item in case.get("schedules", [])
        if not complete_only or item.get("status") == "COMPLETE"
    }


def _declared_schedule_triggers(case: Mapping[str, Any]) -> set[str]:
    triggers = {
        str(trigger).upper()
        for mapping in case.get("mappings", [])
        for allocation in mapping.get("allocations", [])
        for trigger in allocation.get("schedule_triggers", [])
    }
    triggers.update(
        str(item["schedule_type"]).upper()
        for item in (case.get("statutory_presentation") or {}).get(
            "derived_schedule_triggers", []
        )
    )
    return triggers


def _condition(
    condition: Mapping[str, Any], case: Mapping[str, Any]
) -> tuple[bool, str]:
    kind = str(condition["kind"]).upper()
    if kind == "ALWAYS":
        return True, "always applicable for the selected form"
    if kind == "MANUAL_FLAG":
        flag = str(condition["flag"])
        active = flag in set(case.get("disclosure_trigger_flags", []))
        return active, f"reviewer trigger {flag}"
    if kind == "STATEMENT_NONZERO":
        line = str(condition["canonical_line"])
        active = _statement_amount(case, line) != 0
        return active, f"statement line {line} is non-zero"
    if kind == "SCHEDULE_TYPE":
        schedule_type = str(condition["schedule_type"]).upper()
        active = schedule_type in (
            _schedule_types(case) | _declared_schedule_triggers(case)
        )
        return active, f"schedule {schedule_type} is present or reviewer-triggered"
    if kind in {"ANY", "ALL"}:
        results = [_condition(item, case) for item in condition.get("conditions", [])]
        active = (
            any(item[0] for item in results)
            if kind == "ANY"
            else all(item[0] for item in results)
        )
        reasons = "; ".join(item[1] for item in results if item[0])
        return active, reasons or f"{kind.lower()} condition not met"
    raise ValueError(f"Unsupported disclosure condition kind: {kind}")


def _requirement_complete(
    requirement: Mapping[str, Any], case: Mapping[str, Any]
) -> bool:
    kind = str(requirement["kind"]).upper()
    key = str(requirement["key"])
    if kind == "ANSWER":
        return any(
            answer.get("key") == key and disclosure_answer_complete(answer)
            for answer in case.get("disclosure_answers", [])
        )
    if kind == "SCHEDULE":
        return key.upper() in _schedule_types(case, complete_only=True)
    if kind == "STATEMENT_FACT":
        return any(
            fact.get("key") == key
            for fact in (case.get("statements") or {}).get("facts", [])
        )
    if kind == "NARRATIVE_SECTION":
        micro_reporting = case.get("micro_reporting") or {}
        if (
            case.get("selected_form") == "MICRO"
            and micro_reporting.get("mode") == "FOOTER_ONLY"
            and micro_reporting.get("status") == "CONFIRMED"
        ):
            return True
        return any(
            block.get("section_id") == key and block.get("status") == "ACCEPTED"
            for block in case.get("narrative_blocks", [])
        )
    raise ValueError(f"Unsupported disclosure requirement kind: {kind}")


def _validate_rule_pack(rule_pack: Mapping[str, Any], case: Mapping[str, Any]) -> None:
    period_start = date.fromisoformat(str(case["period"]["start"]))
    effective_from = date.fromisoformat(str(rule_pack["effective_from"]))
    effective_to = date.fromisoformat(str(rule_pack["effective_to"]))
    if not effective_from <= period_start <= effective_to:
        raise ValueError("Disclosure rule pack is not effective for the case period")
    rule_ids: set[str] = set()
    question_ids: set[str] = set()
    for rule in rule_pack.get("rules", []):
        rule_id = str(rule["id"])
        questions = list(rule.get("questions", []))
        if not questions and rule.get("question"):
            questions = [rule["question"]]
        if rule_id in rule_ids:
            raise ValueError("Disclosure rule IDs must be unique")
        rule_ids.add(rule_id)
        answer_keys = {
            str(item["key"])
            for item in rule.get("requirements", [])
            if str(item["kind"]).upper() == "ANSWER"
        }
        question_answer_keys = {str(item["answer_key"]) for item in questions}
        if not answer_keys <= question_answer_keys:
            raise ValueError(
                f"Rule {rule_id} must define one question for every answer requirement"
            )
        for question in questions:
            question_id = str(question["question_id"])
            if question_id in question_ids:
                raise ValueError("Disclosure question IDs must be unique")
            question_ids.add(question_id)
        severity = str(rule["severity_if_missing"])
        if severity not in {"BLOCKER", "HIGH", "MEDIUM", "LOW", "INFO"}:
            raise ValueError(f"Unsupported disclosure severity: {severity}")


def build_disclosure_coverage(
    case: Mapping[str, Any], rule_pack: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate applicable rules and build blocker-first structured questions."""

    _validate_rule_pack(rule_pack, case)
    selected_form = str(case.get("selected_form") or "")
    answers = {item["key"]: item for item in case.get("disclosure_answers", [])}
    coverage: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    for rule in rule_pack["rules"]:
        form_applies = selected_form in {str(value) for value in rule["forms"]}
        triggered, reason = _condition(rule["trigger"], case)
        triggered = form_applies and triggered
        requirements = []
        for requirement in rule.get("requirements", []):
            complete = triggered and _requirement_complete(requirement, case)
            requirements.append({**dict(requirement), "complete": complete})
        complete = triggered and all(item["complete"] for item in requirements)
        coverage.append(
            {
                "rule_id": rule["id"],
                "category": rule["category"],
                "triggered": triggered,
                "trigger_reason": reason if triggered else None,
                "complete": complete,
                "severity_if_missing": rule["severity_if_missing"],
                "legal_references": list(rule.get("legal_references", [])),
                "oic_references": list(rule.get("oic_references", [])),
                "requirements": requirements,
                "note_section": rule.get("note_section"),
            }
        )
        rule_questions = list(rule.get("questions", []))
        if not rule_questions and rule.get("question"):
            rule_questions = [rule["question"]]
        for question in rule_questions:
            answer = answers.get(question["answer_key"])
            if not triggered:
                state = "NOT_TRIGGERED"
            elif answer and answer.get("status") in ACCEPTED_ANSWER_STATES:
                state = (
                    str(answer["status"])
                    if disclosure_answer_complete(answer)
                    else "OPEN"
                )
            elif answer and answer.get("status") in QUESTION_STATES:
                state = answer["status"]
            elif complete:
                state = "ACCEPTED"
            else:
                state = "OPEN"
            questions.append(
                {
                    "question_id": question["question_id"],
                    "answer_key": question["answer_key"],
                    "title": question["title"],
                    "reason": reason if triggered else None,
                    "requested_fields": list(question.get("requested_fields", [])),
                    "evidence_requested": question.get("evidence_requested"),
                    "blocking": rule["severity_if_missing"] == "BLOCKER",
                    "source_rule": rule["id"],
                    "state": state,
                    "owner": answer.get("owner") if answer else None,
                }
            )
    schedules = {str(item["schedule_type"]): item for item in case.get("schedules", [])}
    for schedule_type in sorted(required_schedule_types(case)):
        schedule = schedules.get(schedule_type)
        if schedule is None:
            questions.append(
                {
                    "question_id": f"Q_SCHEDULE_{schedule_type}_MISSING",
                    "answer_key": f"schedule:{schedule_type}",
                    "title": f"Provide the required {schedule_type.lower()} schedule",
                    "reason": (
                        "Accepted statement facts or the selected statutory form "
                        "activate this supporting schedule."
                    ),
                    "requested_fields": [schedule_type],
                    "evidence_requested": "Upload or enter source-backed schedule data",
                    "blocking": True,
                    "source_rule": "SCHEDULE.REQUIRED",
                    "state": "OPEN",
                    "owner": None,
                    "resolution_operation": "RECORD_SCHEDULE",
                }
            )
            continue
        for issue_index, issue in enumerate(schedule.get("issues", []), start=1):
            rule_id = str(issue.get("rule_id", "SCHEDULE.INCOMPLETE"))
            row_id = str(issue.get("row_id", "schedule"))
            questions.append(
                {
                    "question_id": (
                        f"Q_{schedule_type}_{issue_index:03d}_"
                        + "".join(
                            character if character.isalnum() else "_"
                            for character in rule_id
                        )
                    ),
                    "answer_key": f"schedule:{schedule['schedule_id']}:{row_id}",
                    "title": f"Resolve {rule_id} for row {row_id}",
                    "reason": "The current supporting schedule is incomplete or does not reconcile.",
                    "requested_fields": [
                        str(issue.get("field") or rule_id.rsplit(".", 1)[-1])
                    ],
                    "evidence_requested": "Correct the schedule using reviewed source evidence",
                    "blocking": True,
                    "source_rule": rule_id,
                    "state": "OPEN",
                    "owner": None,
                    "resolution_operation": "RECORD_SCHEDULE",
                }
            )
    priority = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    coverage.sort(
        key=lambda item: (
            not item["triggered"],
            item["complete"],
            priority[item["severity_if_missing"]],
            item["rule_id"],
        )
    )
    questions.sort(
        key=lambda item: (
            item["state"] == "NOT_TRIGGERED",
            not item["blocking"],
            item["question_id"],
        )
    )
    return {
        "rule_pack_id": rule_pack["id"],
        "rule_pack_checksum": disclosure_rule_pack_hash(rule_pack),
        "coverage": coverage,
        "questions": questions,
        "triggered_count": sum(item["triggered"] for item in coverage),
        "complete_count": sum(
            item["triggered"] and item["complete"] for item in coverage
        ),
    }


def note_outline(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the fixed section model with linked triggered disclosure rules."""

    coverage = (case.get("disclosure_coverage") or {}).get("coverage", [])
    return [
        {
            "section_id": section_id,
            "title": title,
            "triggered_rule_ids": [
                item["rule_id"]
                for item in coverage
                if item.get("triggered") and item.get("note_section") == section_id
            ],
            "status": "EMPTY",
        }
        for section_id, title in NOTE_SECTIONS
    ]


def prior_narrative_suggestions(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return prior text facts as stale, unconfirmed suggestions only."""

    suggestions = []
    for fact in (case.get("prior_xbrl") or {}).get("facts", []):
        if fact.get("unit_ref") is not None or fact.get("nil") or not fact.get("value"):
            continue
        suggestions.append(
            {
                "suggestion_id": f"prior_narrative_{len(suggestions) + 1:05d}",
                "source_qname": fact["qname"],
                "text": fact["value"],
                "language": fact.get("language"),
                "source_refs": [fact["source_anchor"]["source_ref"]],
                "status": "UNCONFIRMED_STALE_SUGGESTION",
                "requires_redline": True,
            }
        )
    return suggestions


def narrative_redline(previous: str, current: str) -> list[str]:
    """Return a stable word-level redline for reviewer-visible prior text reuse."""

    # A deterministic diff is required here because the reviewer must be able to
    # reproduce exactly which prior words were removed or introduced.
    return list(
        unified_diff(
            previous.split(),
            current.split(),
            fromfile="previous_filed_text",
            tofile="current_draft",
            lineterm="",
        )
    )


def normalize_narrative_blocks(
    blocks: Sequence[Mapping[str, Any]], actor: str, output_language: str = "it"
) -> list[dict[str, Any]]:
    """Require every factual sentence to cite accepted structured evidence."""

    valid_sections = {item[0] for item in NOTE_SECTIONS}
    normalized: list[dict[str, Any]] = []
    block_ids: set[str] = set()
    normalized_output_language = output_language.strip().lower()
    if normalized_output_language not in {"it", "en"}:
        raise ValueError("Narrative output language must be it or en")
    for block in blocks:
        block_id = str(block["block_id"])
        if not block_id or block_id in block_ids:
            raise ValueError("Narrative block IDs must be present and unique")
        block_ids.add(block_id)
        section_id = str(block["section_id"])
        if section_id not in valid_sections:
            raise ValueError(f"Unknown note section: {section_id}")
        status = str(block.get("status", "DRAFT")).upper()
        if status not in {"DRAFT", "ACCEPTED", "REJECTED"}:
            raise ValueError(f"Unsupported narrative block status: {status}")
        language = str(block.get("language", normalized_output_language)).lower()
        if language != normalized_output_language:
            raise ValueError(
                "Narrative blocks cannot mix languages in one approved output"
            )
        claims = []
        for claim in block.get("claims", []):
            claim_kind = str(claim.get("kind", "FACTUAL")).upper()
            source_refs = sorted(
                {str(value) for value in claim.get("source_refs", []) if str(value)}
            )
            template_version = str(claim.get("template_version", ""))
            raw_assertions = claim.get("fact_assertions", [])
            if not isinstance(raw_assertions, list):
                raise ValueError("Narrative fact assertions must be a list")
            fact_assertions = [dict(item) for item in raw_assertions]
            semantic_support = claim.get("semantic_support")
            if semantic_support is not None and not isinstance(
                semantic_support, Mapping
            ):
                raise ValueError("Narrative semantic support must be an object")
            if claim_kind == "FACTUAL" and not source_refs:
                raise ValueError("Every factual narrative claim requires source refs")
            if claim_kind == "TEMPLATE" and not template_version:
                raise ValueError(
                    "Non-factual template text requires a template version"
                )
            if claim_kind not in {"FACTUAL", "TEMPLATE"}:
                raise ValueError("Narrative claim kind must be FACTUAL or TEMPLATE")
            claims.append(
                {
                    "sentence": str(claim["sentence"]),
                    "kind": claim_kind,
                    "source_refs": source_refs,
                    "template_version": template_version or None,
                    "fact_assertions": fact_assertions,
                    "semantic_support": (
                        dict(semantic_support) if semantic_support is not None else None
                    ),
                }
            )
        if not claims:
            raise ValueError("Narrative blocks require sentence-level claims")
        rendered_text = " ".join(str(claim["sentence"]).strip() for claim in claims)
        supplied_text = " ".join(str(block["text"]).split())
        if supplied_text != " ".join(rendered_text.split()):
            raise ValueError(
                "Narrative text must be composed exactly from its sentence-level claims"
            )
        normalized.append(
            {
                "block_id": block_id,
                "section_id": section_id,
                "text": str(block["text"]),
                "claims": claims,
                "status": status,
                "language": language,
                "reviewed_by": actor if status == "ACCEPTED" else None,
                "prior_suggestion_id": block.get("prior_suggestion_id"),
                "xbrl_concept": block.get("xbrl_concept"),
            }
        )
    return normalized
