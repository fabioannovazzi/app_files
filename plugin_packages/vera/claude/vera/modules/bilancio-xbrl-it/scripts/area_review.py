"""Living area workpapers over reviewed facts, never keyword classification.

Exact reference closure, accounting populations and dependency hashes are
mechanical audit contracts. Document meaning and applicability are proposed by
the host model and confirmed separately by an authenticated professional.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "build_area_review",
    "review_catalogue",
    "review_source",
    "review_validation_issues",
    "propose_area_review",
    "confirm_area_review",
    "propose_qualitative_evidence",
    "review_qualitative_evidence",
    "record_area_controls",
    "verify_area_review",
    "record_review_source_replacement",
]


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def review_catalogue() -> dict[str, Any]:
    """Load host-controlled metadata, not a caller-supplied regulatory pack."""
    path = (
        Path(__file__).resolve().parents[1]
        / "rulepacks/it/review-catalogue-2026.1.json"
    )
    return json.loads(path.read_bytes())


def _material(value: Any) -> Any:
    """Ignore execution timestamps/revisions, never accounting or evidence values."""
    volatile = {
        "computation_context",
        "computed_at",
        "updated_at",
        "reviewed_at",
        "confirmed_at",
        "revision_id",
    }
    if isinstance(value, dict):
        return {k: _material(v) for k, v in value.items() if k not in volatile}
    if isinstance(value, list):
        return [_material(v) for v in value]
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 8000:
        raise ValueError(f"{field} requires bounded non-empty text")
    return value.strip()


def _docs(case: Mapping[str, Any], refs: list[str]) -> dict[str, str]:
    known = {d["document_id"]: d["sha256"] for d in case.get("source_documents", [])}
    if (
        not isinstance(refs, list)
        or not refs
        or len(refs) > 100
        or any(not isinstance(r, str) for r in refs)
        or len(set(refs)) != len(refs)
        or not set(refs) <= known.keys()
    ):
        raise ValueError("Review requires unique registered documentary evidence")
    return {r: known[r] for r in refs}


def _store(case: Mapping[str, Any]) -> dict[str, Any]:
    return case.get("area_review") or {"proposals": [], "qualitative": [], "events": []}


def verify_area_review(case: Mapping[str, Any]) -> None:
    """Verify the append-only event chain and its retained proposal identities."""
    data = _store(case)
    previous = "0" * 64
    for event in data["events"]:
        if event["previous_sha256"] != previous or event["sha256"] != _hash(
            {k: v for k, v in event.items() if k != "sha256"}
        ):
            raise ValueError("Area review decision register integrity failed")
        previous = event["sha256"]
        if "proposal_sha256" in event["payload"]:
            pool = data["proposals"] if event["kind"] == "PLAN" else data["qualitative"]
            found = next(
                (p for p in pool if p["id"] == event["payload"]["proposal_id"]), None
            )
            if not found or _hash(found) != event["payload"]["proposal_sha256"]:
                raise ValueError("Area review proposal integrity failed")


def _event(
    case: dict[str, Any], kind: str, payload: dict[str, Any], actor: str, revision: str
) -> dict[str, Any]:
    from xbrl_case import _ensure_revision, _mutate, _now, _record_event

    _ensure_revision(case, revision)
    verify_area_review(case)
    _mutate(case, actor, "area_review_" + kind.lower())
    data = case.setdefault(
        "area_review", {"proposals": [], "qualitative": [], "events": []}
    )
    record = {
        "kind": kind,
        "payload": deepcopy(payload),
        "actor": actor,
        "role": "PREPARER" if kind == "SOURCE_REPLACED" else "REVIEWER",
        "revision_id": case["revision_id"],
        "at": _now(),
        "previous_sha256": data["events"][-1]["sha256"] if data["events"] else "0" * 64,
    }
    record["sha256"] = _hash(record)
    data["events"].append(record)
    case["validation"] = None
    _record_event(
        case, "area_review_" + kind.lower(), actor, {"event_sha256": record["sha256"]}
    )
    return case


def _basis(case: Mapping[str, Any]) -> str:
    return _hash(
        {
            k: case.get(k)
            for k in (
                "trial_balance",
                "selected_form",
                "period",
                "rule_pack_versions",
                "oic_rule_pack_checksum",
                "source_documents",
            )
        }
    )


def _unique_id(data: Mapping[str, Any], value: str) -> str:
    from closing_workflow import _id

    value = _id(value, "proposal id")
    if any(p["id"] == value for key in ("proposals", "qualitative") for p in data[key]):
        raise ValueError("Review proposal identifiers cannot be reused")
    return value


def propose_area_review(
    case: dict[str, Any], payload: Mapping[str, Any], actor: str, revision: str
) -> dict[str, Any]:
    """Retain an interpretation; only the separate confirmation accepts it."""
    from xbrl_case import _ensure_revision, _mutate, _record_event

    _ensure_revision(case, revision)
    if not case.get("selected_form") or not case.get("trial_balance"):
        raise ValueError("Area planning requires reviewed accounts and a selected form")
    proposal_id = _unique_id(_store(case), payload["id"])
    content = deepcopy(dict(payload["content"]))
    if len(json.dumps(content).encode()) > 2_000_000:
        raise ValueError("Area proposal exceeds its bounded size")
    _validate_plan(case, content)
    proposal = {
        "id": proposal_id,
        "content": content,
        "prepared_by": actor,
        "reason": _text(payload["reason"], "Proposal reason"),
        "evidence": _docs(case, payload["evidence_refs"]),
        "basis_sha256": _basis(case),
        "status": "MODEL_SUGGESTED",
    }
    _mutate(case, actor, "area_review_proposed")
    data = case.setdefault(
        "area_review", {"proposals": [], "qualitative": [], "events": []}
    )
    data["proposals"].append(proposal)
    case["validation"] = None
    _record_event(case, "area_review_proposed", actor, {"id": proposal_id})
    return case


def _validate_plan(case: Mapping[str, Any], content: Mapping[str, Any]) -> None:
    pack = review_catalogue()
    areas = {a["id"] for a in pack["areas"]}
    dispositions = content["areas"]
    if (
        not isinstance(dispositions, list)
        or len(dispositions) != len(areas)
        or {a["area_id"] for a in dispositions} != areas
    ):
        raise ValueError("Every catalogue area needs one explicit disposition")
    active = {a["area_id"] for a in dispositions if a["status"] == "ACTIVE"}
    for area in dispositions:
        if area["status"] not in {
            "ACTIVE",
            "EXCLUDED",
            "UNDETERMINABLE",
            "OUT_OF_SCOPE",
        }:
            raise ValueError("Invalid area disposition")
        _text(area["reason"], "Area reason")
        _docs(case, area["evidence_refs"])
        if area.get("closing_area_id"):
            from closing_workflow import closing_status

            known = {a["area_id"] for a in closing_status(case)["areas"]}
            if area["closing_area_id"] not in known:
                raise ValueError("Unknown linked closing-review area")
    entries = (case.get("trial_balance") or {}).get("entries", [])
    assignments = content["account_areas"]
    if len(assignments) != len(entries) or {a["account_id"] for a in assignments} != {
        e["account_id"] for e in entries
    }:
        raise ValueError("Every account requires exactly one reviewed area assignment")
    if any(a["area_id"] not in active for a in assignments):
        raise ValueError(
            "An account cannot be assigned to an excluded or unresolved area"
        )
    if content["complexity"] not in {"SIMPLE", "COMPLEX"}:
        raise ValueError("Complexity must be professionally assessed")
    _text(content["complexity_reason"], "Complexity reason")
    if case["selected_form"] == "ORDINARY" and "CASH_FLOW" not in active:
        raise ValueError("Ordinary accounts require the cash-flow area")
    # Confirmed document evidence activates even an area with no account balance.
    for row in _qualitative_rows(case):
        if row["status"] == "APPLICABLE" and not set(row["area_ids"]) <= active:
            raise ValueError("Confirmed qualitative evidence prevents area exclusion")


def confirm_area_review(
    case: dict[str, Any], payload: Mapping[str, Any], actor: str, revision: str
) -> dict[str, Any]:
    data = _store(case)
    proposal = next(
        (p for p in data["proposals"] if p["id"] == payload["proposal_id"]), None
    )
    if not proposal or proposal["basis_sha256"] != _basis(case):
        raise ValueError("Missing or stale area proposal; refresh its evidence")
    _validate_plan(case, proposal["content"])
    if payload.get("source_versions_reviewed") is not True:
        raise ValueError(
            "Confirm source versions against the locked reporting-period OIC pack"
        )
    _text(payload["reason"], "Professional reason")
    if payload["oic_rule_pack_checksum"] != case["oic_rule_pack_checksum"]:
        raise ValueError("Review is bound to the exact reporting-period OIC pack")
    return _event(
        case,
        "PLAN",
        {
            **dict(payload),
            "proposal_sha256": _hash(proposal),
            "catalogue_sha256": _hash(review_catalogue()),
        },
        actor,
        revision,
    )


def review_source(
    case: Mapping[str, Any], document_id: str, *, offset: int = 0, limit: int = 4000
) -> dict[str, Any]:
    """Return an exact bounded excerpt of a registered, immutable source."""
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
        or not 1 <= limit <= 8000
    ):
        raise ValueError("Invalid source excerpt bounds")
    documents = {d["document_id"]: d for d in case.get("source_documents", [])}
    if document_id not in documents:
        raise ValueError("Unknown review document")
    extract = next(
        (
            e
            for e in [
                *((case.get("closing_workflow") or {}).get("source_extracts", [])),
                *case.get("review_source_extracts", []),
            ]
            if e["document_id"] == document_id
        ),
        {},
    )
    if extract and extract["source_sha256"] != documents[document_id]["sha256"]:
        raise ValueError("Source extraction checksum mismatch")
    text = extract.get("text", "")
    if text and extract["text_sha256"] != _hash(text):
        raise ValueError("Source extraction content mismatch")
    return {
        "document": documents[document_id],
        "offset": offset,
        "excerpt": text[offset : offset + limit],
        "total_characters": len(text),
        "has_more": offset + limit < len(text),
        "untrusted_content": True,
        "status": "EXTRACTED_UNREVIEWED" if text else "REQUIRES_QUALIFIED_EXTRACTION",
    }


def propose_qualitative_evidence(
    case: dict[str, Any], payload: Mapping[str, Any], actor: str, revision: str
) -> dict[str, Any]:
    from xbrl_case import _ensure_revision, _mutate, _record_event

    _ensure_revision(case, revision)
    proposal_id = _unique_id(_store(case), payload["id"])
    start, end = payload["start"], payload["end"]
    if (
        any(isinstance(x, bool) or not isinstance(x, int) for x in (start, end))
        or not 0 <= start < end <= start + 8000
    ):
        raise ValueError(
            "Qualitative evidence requires exact bounded character offsets"
        )
    source = review_source(
        case, payload["document_id"], offset=start, limit=end - start
    )
    _text(payload["quote"], "Exact source quote")
    if source["excerpt"] != payload["quote"]:
        raise ValueError("Quote does not match its registered source excerpt")
    flags = {f["flag"]: f for f in review_catalogue()["qualitative_flags"]}
    if payload["flag"] not in flags:
        raise ValueError("Unknown qualitative activation flag")
    period = payload["period"]
    if date.fromisoformat(period["start"]) > date.fromisoformat(period["end"]):
        raise ValueError("Invalid evidence period")
    if payload["outcome"] not in {
        "APPLICABLE",
        "NOT_APPLICABLE_WITH_EVIDENCE",
        "UNDETERMINABLE",
        "OUT_OF_ENGINE_SCOPE",
    }:
        raise ValueError("Invalid qualitative outcome")
    if payload.get("supersedes"):
        previous = next(
            (
                p
                for p in _store(case)["qualitative"]
                if p["id"] == payload["supersedes"]
            ),
            None,
        )
        if not previous or previous["flag"] != payload["flag"]:
            raise ValueError(
                "Qualitative replacement must reference an earlier proposal for the same flag"
            )
    proposal = {
        **deepcopy(dict(payload)),
        "id": proposal_id,
        "reason": _text(payload["reason"], "Interpretation reason"),
        "area_ids": flags[payload["flag"]]["areas"],
        "source_sha256": source["document"]["sha256"],
        "status": "MODEL_SUGGESTED",
        "prepared_by": actor,
    }
    _mutate(case, actor, "qualitative_evidence_proposed")
    data = case.setdefault(
        "area_review", {"proposals": [], "qualitative": [], "events": []}
    )
    data["qualitative"].append(proposal)
    case["validation"] = None
    _record_event(case, "qualitative_evidence_proposed", actor, {"id": proposal_id})
    return case


def _current_document(case: Mapping[str, Any], document_id: str) -> str:
    for event in _store(case)["events"]:
        if (
            event["kind"] == "SOURCE_REPLACED"
            and event["payload"]["old_document_id"] == document_id
        ):
            document_id = event["payload"]["new_document_id"]
    return document_id


def _source_changed(case: Mapping[str, Any], document_id: str) -> bool:
    documents = {
        d["document_id"]: d["sha256"] for d in case.get("source_documents", [])
    }
    return documents[document_id] != documents[_current_document(case, document_id)]


def review_qualitative_evidence(
    case: dict[str, Any], payload: Mapping[str, Any], actor: str, revision: str
) -> dict[str, Any]:
    proposal = next(
        (p for p in _store(case)["qualitative"] if p["id"] == payload["proposal_id"]),
        None,
    )
    if not proposal:
        raise ValueError("Unknown qualitative proposal")
    if payload["outcome"] not in {"CONFIRMED", "REJECTED"}:
        raise ValueError("Qualitative review requires an explicit disposition")
    if payload["outcome"] == "CONFIRMED":
        if (
            proposal["period"]["end"] < case["period"]["start"]
            or proposal["period"]["start"] > case["period"]["end"]
        ):
            raise ValueError(
                "Prior-only or future evidence cannot confirm current-period applicability"
            )
        if _source_changed(case, proposal["document_id"]):
            raise ValueError(
                "Replaced qualitative evidence requires a fresh interpretation"
            )
    _text(payload["reason"], "Professional reason")
    return _event(
        case,
        "QUALITATIVE",
        {**dict(payload), "proposal_sha256": _hash(proposal)},
        actor,
        revision,
    )


def _qualitative_rows(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    reviewed = {
        e["payload"]["proposal_id"]: e["payload"]
        for e in _store(case)["events"]
        if e["kind"] == "QUALITATIVE"
    }
    superseded = {
        p["supersedes"]
        for p in _store(case)["qualitative"]
        if p.get("supersedes")
        and reviewed.get(p["id"], {}).get("outcome") == "CONFIRMED"
    }
    result = []
    for proposal in _store(case)["qualitative"]:
        decision = reviewed.get(proposal["id"])
        status = (
            proposal["outcome"]
            if decision and decision["outcome"] == "CONFIRMED"
            else "REJECTED" if decision else "MODEL_SUGGESTED"
        )
        if decision and _source_changed(case, proposal["document_id"]):
            status = "REVIEW_REQUIRED"
        if proposal["id"] in superseded:
            status = "SUPERSEDED"
        result.append({**proposal, "status": status, "review": decision})
    return result


def record_review_source_replacement(
    case: dict[str, Any], old: str, new: str, actor: str, revision: str
) -> dict[str, Any]:
    if old == new or _current_document(case, old) != old:
        raise ValueError("Replace the current document revision only")
    _docs(case, [old, new])
    return _event(
        case,
        "SOURCE_REPLACED",
        {"old_document_id": old, "new_document_id": new},
        actor,
        revision,
    )


def _plan(case: Mapping[str, Any]) -> dict[str, Any] | None:
    events = [e for e in _store(case)["events"] if e["kind"] == "PLAN"]
    if not events:
        return None
    event = events[-1]
    proposal = next(
        p
        for p in _store(case)["proposals"]
        if p["id"] == event["payload"]["proposal_id"]
    )
    return {**proposal["content"], "review": event, "proposal_id": proposal["id"]}


def _profile(case: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    origin = (
        (case.get("closing_workflow") or {}).get("opening", {}).get("accounting_origin")
    )
    return (
        "STREAMLINED"
        if case.get("selected_form") in {"MICRO", "ABBREVIATED"}
        and origin == "CONTABILITA_INTERNA"
        and plan["complexity"] == "SIMPLE"
        else "FULL"
    )


def build_area_review(case: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute living workpapers and reopen only changed dependency hashes."""
    verify_area_review(case)
    pack, plan = review_catalogue(), _plan(case)
    base = {
        "catalogue_id": pack["id"],
        "catalogue_sha256": _hash(pack),
        "oic_rule_pack": case["rule_pack_versions"]["oic_rule_pack"],
        "oic_rule_pack_checksum": case["oic_rule_pack_checksum"],
        "coverage": pack["policy"]["coverage"],
        "qualitative": _qualitative_rows(case),
        "events": _store(case)["events"],
        "workpapers": [],
        "standards": [],
        "controls": [],
    }
    if not plan:
        return {
            **base,
            "status": "PLAN_REQUIRED",
            "profile": None,
            "unassigned_accounts": [
                e["account_id"]
                for e in (case.get("trial_balance") or {}).get("entries", [])
            ],
        }
    profile = _profile(case, plan)
    entries = (case.get("trial_balance") or {}).get("entries", [])
    assignment = {a["account_id"]: a["area_id"] for a in plan["account_areas"]}
    unknown = sorted({e["account_id"] for e in entries} ^ set(assignment))
    registry_current = (
        plan["review"]["payload"]["catalogue_sha256"] == _hash(pack)
        and plan["review"]["payload"]["oic_rule_pack_checksum"]
        == case["oic_rule_pack_checksum"]
    )
    dispositions = {a["area_id"]: a for a in plan["areas"]}
    rows = []
    qualitative = base["qualitative"]
    docs = {d["document_id"]: d for d in case.get("source_documents", [])}
    from closing_workflow import closing_status

    closing = closing_status(case) if case.get("closing_workflow") else {}
    totals: dict[tuple[str, str, str, str], Decimal] = {}
    allocations = [
        a for m in case.get("mappings", []) for a in m.get("allocations", [])
    ]
    allocations += [
        a for adjustment in case.get("adjustments", []) for a in adjustment["lines"]
    ]
    for allocation in allocations:
        key = (
            allocation["statement_section"],
            allocation["canonical_line"],
            allocation["xbrl_concept"],
            str(allocation["xbrl_sign_multiplier"]),
        )
        totals[key] = totals.get(key, Decimal(0)) + Decimal(
            allocation["current_amount"]
        )
    fact_index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for fact in case.get(
        "canonical_facts", (case.get("statements") or {}).get("facts", [])
    ):
        key = (
            fact["statement_section"],
            fact["key"],
            fact["xbrl_concept"],
            str(fact["xbrl_sign_multiplier"]),
        )
        fact_index.setdefault(key, []).append(fact)
    for area in [
        *pack["areas"],
        {
            "id": "GENERAL",
            "title": "Criteri e presentazione",
            "schedule_types": [],
            "note_sections": ["INTRODUCTION", "POLICIES"],
        },
    ]:
        area_id = area["id"]
        disposition = dispositions.get(
            area_id,
            {
                "status": "ACTIVE",
                "reason": "Revisione generale obbligatoria",
                "evidence_refs": [],
            },
        )
        population = [e for e in entries if assignment.get(e["account_id"]) == area_id]
        mappings = [
            m
            for m in case.get("mappings", [])
            if m["account_id"] in {e["account_id"] for e in population}
        ]
        allocation_keys = {
            (
                a["statement_section"],
                a["canonical_line"],
                a["xbrl_concept"],
                str(a["xbrl_sign_multiplier"]),
            )
            for m in mappings
            for a in m.get("allocations", [])
        }
        facts = [f for key in sorted(allocation_keys) for f in fact_index.get(key, [])]
        schedules = [
            s
            for s in case.get("schedules", [])
            if s.get("schedule_type") in area["schedule_types"]
        ]
        qualitative_links = [
            q
            for q in qualitative
            if area_id in q["area_ids"]
            and q["status"] not in {"REJECTED", "SUPERSEDED"}
        ]
        refs = set(disposition["evidence_refs"]) | {
            q["document_id"] for q in qualitative_links
        }
        evidence = [docs[_current_document(case, r)] for r in sorted(refs)]
        notes = [
            n
            for n in case.get("narrative_blocks", [])
            if n.get("section_id") in area["note_sections"]
        ]
        questions = [
            q
            for q in case.get("questionnaire", [])
            if q.get("note_section") in area["note_sections"]
        ]
        status = disposition["status"]
        positive = [q for q in qualitative_links if q["status"] == "APPLICABLE"]
        reason = positive[-1]["review"]["reason"] if positive else disposition["reason"]
        if positive:
            status = "ACTIVE"
        if any(
            q["status"]
            in {
                "MODEL_SUGGESTED",
                "UNDETERMINABLE",
                "REVIEW_REQUIRED",
                "OUT_OF_ENGINE_SCOPE",
            }
            for q in qualitative_links
        ):
            status = "REVIEW_REQUIRED"
        closing_scope = "area:" + str(disposition.get("closing_area_id", ""))
        if closing.get("dependencies", {}).get(closing_scope) in {
            "SUSPENDED",
            "REVIEW_REQUIRED",
        }:
            status = "REVIEW_REQUIRED"
        links = [
            {
                "account_id": m["account_id"],
                "allocation_id": allocation["allocation_id"],
                "canonical_line": allocation["canonical_line"],
                "current_amount": allocation["current_amount"],
                "fact_ids": [
                    f["fact_id"]
                    for f in fact_index.get(
                        (
                            allocation["statement_section"],
                            allocation["canonical_line"],
                            allocation["xbrl_concept"],
                            str(allocation["xbrl_sign_multiplier"]),
                        ),
                        [],
                    )
                ],
            }
            for m in mappings
            for allocation in m.get("allocations", [])
        ]
        reconciliations = []
        for fact in facts:
            key = (
                fact["statement_section"],
                fact["key"],
                fact["xbrl_concept"],
                str(fact["xbrl_sign_multiplier"]),
            )
            difference = Decimal(fact["current_value"]) - totals.get(key, Decimal(0))
            reconciliations.append(
                {
                    "fact_id": fact["fact_id"],
                    "difference": str(difference),
                    "status": "MATCH" if not difference else "MISMATCH",
                }
            )
        row = {
            **area,
            "area_id": area_id,
            "status": status,
            "reason": reason,
            "accounts": population,
            "mappings": mappings,
            "facts": facts,
            "schedules": schedules,
            "links": links,
            "reconciliations": reconciliations,
            "required_schedule_types": (
                area["schedule_types"] if status == "ACTIVE" else []
            ),
            "missing_schedule_types": (
                sorted(
                    set(area["schedule_types"])
                    - {s["schedule_type"] for s in schedules}
                )
                if status == "ACTIVE"
                else []
            ),
            "documents": evidence,
            "qualitative": qualitative_links,
            "notes": notes,
            "questions": questions,
            "open_issues": [
                i
                for i in closing.get("open_issues", [])
                if i.get("area_id") in {area_id, disposition.get("closing_area_id")}
            ],
            "controls": [],
        }
        # Volatile actor/timestamp/revision metadata is deliberately excluded.
        row["basis_sha256"] = _hash(
            _material(
                {
                    "accounts": population,
                    "mappings": mappings,
                    "facts": facts,
                    "schedules": schedules,
                    "notes": notes,
                    "questions": questions,
                    "disposition": disposition,
                    "sources": {
                        ref: docs[_current_document(case, ref)]["sha256"]
                        for ref in sorted(refs)
                    },
                    "qualitative": qualitative_links,
                    "closing_dependency": closing.get("dependencies", {}).get(
                        closing_scope
                    ),
                    "open_issues": row["open_issues"],
                    "reconciliations": reconciliations,
                    "profile": profile,
                    "oic_checksum": case["oic_rule_pack_checksum"],
                    "catalogue": _hash(pack),
                }
            )
        )
        rows.append(row)
    active = {r["area_id"] for r in rows if r["status"] != "EXCLUDED"}
    standard_rows = []
    controls = []
    decisions = {
        (e["payload"]["area_id"], e["payload"]["control_id"]): e
        for e in _store(case)["events"]
        if e["kind"] == "CONTROL"
    }
    for standard in pack["standards"]:
        linked = set(standard["areas"]) & active
        if standard["id"] in {"OIC_11", "OIC_12"}:
            linked = {"GENERAL"}
        period_eligible = not (
            standard["id"] == "OIC_34" and base["oic_rule_pack"] == "OIC_2016_2023.1"
        )
        if not period_eligible:
            linked = set()
        standard_rows.append(
            {
                **standard,
                "status": (
                    (
                        "APPLICABLE"
                        if all(
                            r["status"] == "ACTIVE"
                            for r in rows
                            if r["area_id"] in linked
                        )
                        else "REVIEW_REQUIRED"
                    )
                    if linked
                    else "NOT_ACTIVATED"
                ),
                "area_ids": sorted(linked),
                "period_eligible": period_eligible,
                "source_version_status": (
                    "PROFESSIONALLY_REVIEWED" if registry_current else "REVIEW_REQUIRED"
                ),
            }
        )
        prompts = [c for c in pack["controls"] if c["standard_id"] == standard["id"]]
        if not prompts:
            prompts = [
                {
                    "id": standard["id"] + ".SCOPE_AND_CONCLUSION",
                    "objective": "Documentare applicabilità, versione delle fonti, controlli svolti e conclusione professionale. Copertura analitica del principio da completare.",
                    "facet": "COVERAGE_GAP",
                }
            ]
        if profile == "STREAMLINED":
            prompts = [
                {
                    "id": standard["id"] + ".COMBINED",
                    "objective": "\n".join(p["objective"] for p in prompts),
                    "facet": "COMBINED",
                    "included_control_ids": [p["id"] for p in prompts],
                }
            ]
        for area_id in sorted(linked):
            workpaper = next(r for r in rows if r["area_id"] == area_id)
            for prompt in prompts:
                prior = decisions.get((area_id, prompt["id"]))
                state = "OPEN"
                if prior:
                    state = (
                        prior["payload"]["status"]
                        if prior["payload"]["basis_sha256"] == workpaper["basis_sha256"]
                        else "REVIEW_REQUIRED"
                    )
                    refs = prior["payload"]["evidence_refs"]
                    if any(_source_changed(case, ref) for ref in refs):
                        state = "REVIEW_REQUIRED"
                if not registry_current or workpaper["status"] != "ACTIVE":
                    state = "REVIEW_REQUIRED"
                control = {
                    **prompt,
                    "area_id": area_id,
                    "status": state,
                    "review": prior,
                }
                workpaper["controls"].append(control)
                controls.append(control)
    unresolved = (
        any(r["status"] == "MISMATCH" for a in rows for r in a["reconciliations"])
        or unknown
        or not registry_current
        or any(
            r["status"] in {"UNDETERMINABLE", "OUT_OF_SCOPE", "REVIEW_REQUIRED"}
            for r in rows
        )
        or any(c["status"] not in {"PASS", "NOT_APPLICABLE"} for c in controls)
    )
    return {
        **base,
        "status": "REVIEW_REQUIRED" if unresolved else "REVIEWED",
        "profile": profile,
        "unassigned_accounts": unknown,
        "workpapers": rows,
        "standards": standard_rows,
        "controls": controls,
        "plan_id": plan["proposal_id"],
        "registry_current": registry_current,
    }


def record_area_controls(
    case: dict[str, Any], payload: Mapping[str, Any], actor: str, revision: str
) -> dict[str, Any]:
    view = build_area_review(case)
    control = next(
        (
            c
            for c in view["controls"]
            if c["id"] == payload["control_id"] and c["area_id"] == payload["area_id"]
        ),
        None,
    )
    if not control or not view.get("registry_current"):
        raise ValueError("Review a current area plan before its controls")
    area = next(a for a in view["workpapers"] if a["area_id"] == payload["area_id"])
    if (
        payload["status"] not in {"PASS", "NOT_APPLICABLE", "OPEN"}
        or area["status"] != "ACTIVE"
    ):
        raise ValueError(
            "Only active, resolved areas can receive a professional control conclusion"
        )
    if any(r["status"] == "MISMATCH" for r in area["reconciliations"]):
        raise ValueError(
            "A mechanical workpaper reconciliation mismatch cannot be overridden"
        )
    _text(payload["reason"], "Control conclusion")
    _docs(case, payload["evidence_refs"])
    if payload.get("basis_sha256") != area["basis_sha256"]:
        raise ValueError("Stale workpaper dependency hash")
    return _event(case, "CONTROL", dict(payload), actor, revision)


def review_validation_issues(case: Mapping[str, Any]) -> list[dict[str, str]]:
    if not case.get("area_review"):
        return []
    review = build_area_review(case)
    if review["status"] != "REVIEWED":
        return [
            {
                "rule_id": "AREA.REVIEW_REQUIRED",
                "message": "Area workpapers, account coverage and applicable professional controls require current review.",
            }
        ]
    return []
