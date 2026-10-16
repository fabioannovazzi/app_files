"""Reviewed closing entries, exact replacement accounts, and durable decisions.

Only explicit professional decisions establish sufficiency, applicability and
accounting treatment. Fixed rules enforce journal arithmetic, evidence closure,
revision integrity and the supplied replacement-account contract because these
properties are mechanically verifiable. No source is posted or sent here.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "closing_status",
    "closing_source_extract",
    "closing_validation_issues",
    "ingest_closing_trial_balance",
    "open_closing_reconsideration",
    "propose_closing_adjustment",
    "propose_closing_review",
    "record_closing_decision",
    "require_closing_ready",
    "start_closing_workflow",
    "verify_closing_register",
]

REQUIREMENT_STATES = frozenset(
    {
        "AVAILABLE_SUFFICIENT",
        "AVAILABLE_INSUFFICIENT",
        "AVAILABLE_STALE",
        "MISSING",
        "REVIEW_REQUIRED",
        "NOT_APPLICABLE",
        "NOT_DETERMINABLE",
    }
)
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 8000:
        raise ValueError(f"{label} requires bounded non-empty text")
    return text


def _id(value: Any, label: str) -> str:
    text = str(value or "")
    if not SAFE_ID.fullmatch(text):
        raise ValueError(f"{label} requires a safe stable identifier")
    return text


def _workflow(case: Mapping[str, Any]) -> dict[str, Any]:
    value = case.get("closing_workflow")
    if not isinstance(value, dict):
        raise ValueError("Start the reviewed closing workflow first")
    verify_closing_register(case)
    return value


def _documents(case: Mapping[str, Any], refs: Sequence[str]) -> list[dict[str, str]]:
    if isinstance(refs, (str, bytes)) or not refs:
        raise ValueError("Every decision requires registered documentary evidence")
    known = {str(d["document_id"]): d for d in case["source_documents"]}
    if len(refs) > 100 or len(set(refs)) != len(refs):
        raise ValueError("Evidence requires at most 100 unique document identifiers")
    if not set(refs) <= known.keys():
        raise ValueError("Closing evidence references an unknown document")
    return [{"document_id": ref, "sha256": known[ref]["sha256"]} for ref in refs]


def verify_closing_register(case: Mapping[str, Any]) -> None:
    """Reject changed, reordered or broken decision chains on every case load."""
    workflow = case.get("closing_workflow")
    if workflow is None:
        return
    previous = workflow["genesis_sha256"]
    if previous != _hash(workflow["opening"]):
        raise ValueError("Closing opening record integrity verification failed")
    ids: set[str] = set()
    for event in workflow["events"]:
        content = {k: v for k, v in event.items() if k != "sha256"}
        if (
            event["record_id"] in ids
            or event["previous_sha256"] != previous
            or event["sha256"] != _hash(content)
        ):
            raise ValueError("Closing decision register integrity verification failed")
        ids.add(event["record_id"])
        decision = event["decision"]
        if decision.get("proposal_sha256"):
            proposals = (
                workflow["proposals"]
                if event["kind"] == "ADJUSTMENT"
                else workflow["review_proposals"]
            )
            proposal = next(
                (p for p in proposals if p["proposal_id"] == decision["proposal_id"]),
                None,
            )
            if proposal is None or _hash(proposal) != decision["proposal_sha256"]:
                raise ValueError(
                    "Closing decision proposal integrity verification failed"
                )
        if event["kind"] == "SCREENING":
            version = next(
                (
                    v
                    for v in workflow["versions"]
                    if v["version_id"] == decision["version_id"]
                ),
                None,
            )
            if (
                version is None
                or _hash(version["trial_balance"]) != decision["version_sha256"]
            ):
                raise ValueError(
                    "Closing screened source integrity verification failed"
                )
        previous = event["sha256"]
    if workflow["head_sha256"] != previous:
        raise ValueError("Closing decision register head does not match its events")
    documents = {d["document_id"]: d["sha256"] for d in case["source_documents"]}
    for event in workflow["events"]:
        if any(
            documents.get(ref["document_id"]) != ref["sha256"]
            for ref in event["evidence"]
        ):
            raise ValueError("Closing decision documentary evidence integrity failed")
    for extract in workflow["source_extracts"]:
        if documents.get(extract["document_id"]) != extract["source_sha256"]:
            raise ValueError("Closing source extraction identity integrity failed")
        if "text" in extract and _hash(extract["text"]) != extract["text_sha256"]:
            raise ValueError("Closing source extraction content integrity failed")


def _append(
    case: dict[str, Any],
    payload: Mapping[str, Any],
    kind: str,
    actor: str,
    role: str,
) -> dict[str, Any]:
    from xbrl_case import _now

    workflow = _workflow(case)
    record_id = _id(payload["record_id"], "record_id")
    if any(e["record_id"] == record_id for e in workflow["events"]):
        raise ValueError("Closing decision identifiers cannot be reused or overwritten")
    event = {
        "record_id": record_id,
        "kind": kind,
        "actor": actor,
        "role": role,
        "reason": _text(payload["reason"], "Decision reason"),
        "evidence": _documents(case, payload["evidence_refs"]),
        "recorded_at": _now(),
        "revision_id": case["revision_id"],
        "previous_sha256": workflow["head_sha256"],
        "decision": deepcopy(dict(payload["decision"])),
    }
    if payload.get("effective_date"):
        event["effective_date"] = date.fromisoformat(
            str(payload["effective_date"])
        ).isoformat()
    event["sha256"] = _hash(event)
    workflow["events"].append(event)
    workflow["head_sha256"] = event["sha256"]
    return event


def start_closing_workflow(
    case: dict[str, Any],
    payload: Mapping[str, Any],
    actor: str,
    revision: str,
) -> dict[str, Any]:
    """Record the explicit origin before a source or professional review exists."""
    from xbrl_case import _ensure_revision, _mutate, _now, _record_event

    _ensure_revision(case, revision)
    if (
        case.get("closing_workflow")
        or case.get("trial_balance")
        or case.get("selected_form")
    ):
        raise ValueError(
            "Closing workflow must start once, before trial-balance intake"
        )
    if case.get("unsupported_reasons"):
        raise ValueError("Unsupported cases cannot start a closing workflow")
    origin = str(payload["accounting_origin"])
    if origin not in {"CONTABILITA_INTERNA", "CONTABILITA_ESTERNA"}:
        raise ValueError("The professional must explicitly identify accounting origin")
    opening = {"accounting_origin": origin, "actor": actor, "recorded_at": _now()}
    if payload.get("effective_date"):
        opening["effective_date"] = date.fromisoformat(
            str(payload["effective_date"])
        ).isoformat()
    _mutate(case, actor, "closing_workflow_started")
    case["closing_workflow"] = {
        "schema_version": 1,
        "opening": opening,
        "genesis_sha256": _hash(opening),
        "head_sha256": _hash(opening),
        "events": [],
        "proposals": [],
        "review_proposals": [],
        "versions": [],
        "source_extracts": [],
    }
    _record_event(
        case, "closing_workflow_started", actor, {"accounting_origin": origin}
    )
    return case


def _active_adjustments(workflow: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    proposals = {p["proposal_id"]: p for p in workflow["proposals"]}
    active: dict[str, dict[str, Any]] = {}
    for event in workflow["events"]:
        if event["kind"] == "ADJUSTMENT" and event["decision"]["outcome"] == "APPROVED":
            decision = event["decision"]
            active.pop(decision.get("supersedes"), None)
            active[event["record_id"]] = proposals[decision["proposal_id"]]
    return active


def closing_source_extract(source: Path, document: Mapping[str, Any]) -> dict[str, Any]:
    """Retain bounded untrusted evidence for an explicitly requested review view."""
    record = {
        "document_id": document["document_id"],
        "source_sha256": document["sha256"],
        "status": "REQUIRES_QUALIFIED_EXTRACTION",
        "untrusted_content": True,
    }
    if source.suffix.lower() == ".pdf":
        import fitz

        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != document["sha256"]:
            raise ValueError("Review PDF changed during evidence extraction")
        try:
            with fitz.open(stream=content, filetype="pdf") as pdf:
                if pdf.is_encrypted or len(pdf) > 200:
                    return record
                pages = [page.get_text() for page in pdf]
        except (fitz.FileDataError, RuntimeError):
            return record
        # Never present an incomplete or image-only document as extracted text.
        if not pages or any(not page.strip() for page in pages):
            return record
        text = "\n".join(pages)
        if len(text.encode()) > 65536:
            return record
        return {
            **record,
            "status": "EXTRACTED_UNREVIEWED",
            "text": text,
            "text_sha256": _hash(text),
            "locator": "PDF pages in source order",
            "pages": [
                {"page": i + 1, "characters": len(t)} for i, t in enumerate(pages)
            ],
        }
    if (
        source.suffix.lower() not in {".txt", ".md", ".csv", ".json"}
        or source.stat().st_size > 65536
    ):
        return record
    content = source.read_bytes()
    if hashlib.sha256(content).hexdigest() != document["sha256"]:
        raise ValueError("Closing source changed during evidence extraction")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return record
    return {
        **record,
        "status": "EXTRACTED_UNREVIEWED",
        "locator": "complete UTF-8 source",
        "text": text,
        "text_sha256": _hash(text),
    }


def _adjustment_basis(workflow: Mapping[str, Any]) -> str:
    return _hash(_active_adjustments(workflow))


def _expected_entries(workflow: Mapping[str, Any]) -> dict[str, Decimal]:
    baseline = workflow["versions"][0]["trial_balance"]["entries"]
    expected = {r["account_code"]: Decimal(r["closing_signed"]) for r in baseline}
    for proposal in _active_adjustments(workflow).values():
        for line in proposal["lines"]:
            expected[line["account_code"]] += Decimal(line["debit"]) - Decimal(
                line["credit"]
            )
    return expected


def _reconcile(
    workflow: Mapping[str, Any], trial_balance: Mapping[str, Any]
) -> dict[str, Any]:
    expected = _expected_entries(workflow)
    actual = {r["account_code"]: r for r in trial_balance["entries"]}
    baseline = {
        r["account_code"]: r
        for r in workflow["versions"][0]["trial_balance"]["entries"]
    }
    differences: list[dict[str, Any]] = []
    for code in sorted(expected.keys() | actual.keys()):
        if code not in expected or code not in actual:
            differences.append(
                {
                    "account_code": code,
                    "field": "account_population",
                    "difference": "MISSING_OR_NEW",
                }
            )
            continue
        difference = Decimal(actual[code]["closing_signed"]) - expected[code]
        if difference:
            differences.append(
                {
                    "account_code": code,
                    "field": "closing_signed",
                    "difference": str(difference),
                }
            )
        if not difference:
            for field, expected_side in (
                ("closing_debit", max(expected[code], Decimal(0))),
                ("closing_credit", max(-expected[code], Decimal(0))),
            ):
                side_difference = Decimal(actual[code][field]) - expected_side
                if side_difference:
                    differences.append(
                        {
                            "account_code": code,
                            "field": field,
                            "difference": str(side_difference),
                        }
                    )
        for field in (
            "prior_closing_signed",
            "prior_closing_debit",
            "prior_closing_credit",
            "account_description",
        ):
            if baseline[code][field] != actual[code][field]:
                differences.append(
                    {
                        "account_code": code,
                        "field": field,
                        "expected": baseline[code][field],
                        "observed": actual[code][field],
                    }
                )
    return {
        "status": "MATCH" if not differences else "MISMATCH",
        "differences": differences,
        "adjustment_basis_sha256": _adjustment_basis(workflow),
    }


def ingest_closing_trial_balance(
    case: dict[str, Any],
    source: Path,
    payload: Mapping[str, Any],
    actor: str,
    revision: str,
) -> dict[str, Any]:
    """Retain a replacement candidate without promoting its accounting amounts."""
    from xbrl_case import _ensure_revision, _mutate, _record_event, ingest_trial_balance

    _ensure_revision(case, revision)
    workflow = _workflow(case)
    if not workflow["versions"]:
        raise ValueError("A reviewed baseline is required before replacement intake")
    version_id = _id(payload["version_id"], "version_id")
    if any(v["version_id"] == version_id for v in workflow["versions"]):
        raise ValueError("Trial-balance version identifiers cannot be reused")
    parsed_case = deepcopy(case)
    parsed_case.pop("closing_workflow")
    ingest_trial_balance(
        parsed_case,
        source,
        actor,
        revision,
        payload.get("sheet"),
        column_mapping=payload.get("column_mapping"),
        blank_balance_cells_are_zero=payload.get("blank_balance_cells_are_zero", False),
    )
    trial_balance = parsed_case["trial_balance"]
    document = parsed_case["source_documents"][-1]
    # Stable account identity follows the reviewed code, not incoming row order.
    baseline_ids = {
        r["account_code"]: r["account_id"]
        for r in workflow["versions"][0]["trial_balance"]["entries"]
    }
    account_ids = {
        r["account_id"]: baseline_ids.get(r["account_code"], r["account_id"])
        for r in trial_balance["entries"]
    }
    source_refs = {
        a["source_ref"]: document["document_id"] + "_" + a["source_ref"]
        for a in trial_balance["source_anchors"]
    }
    for entry in trial_balance["entries"]:
        entry["account_id"] = account_ids[entry["account_id"]]
        entry["source_refs"] = [source_refs[ref] for ref in entry["source_refs"]]
    for anchor in trial_balance["source_anchors"]:
        anchor["account_id"] = account_ids[anchor["account_id"]]
        anchor["source_ref"] = source_refs[anchor["source_ref"]]
    document["purpose"] = "CLOSING_TRIAL_BALANCE_CANDIDATE"
    reconciliation = _reconcile(workflow, trial_balance)
    _mutate(case, actor, "closing_trial_balance_received")
    case["source_documents"].append(document)
    workflow["versions"].append(
        {
            "version_id": version_id,
            "document_id": document["document_id"],
            "trial_balance": trial_balance,
            "reconciliation": reconciliation,
        }
    )
    case["validation"] = None
    _record_event(
        case,
        "closing_trial_balance_received",
        actor,
        {
            "version_id": version_id,
            "reconciliation": reconciliation,
        },
    )
    return case


def propose_closing_adjustment(
    case: dict[str, Any],
    payload: Mapping[str, Any],
    actor: str,
    revision: str,
) -> dict[str, Any]:
    """Store an exact, evidence-linked suggestion without approving or posting it."""
    from xbrl_case import _ensure_revision, _mutate, _record_event, normalize_decimal

    _ensure_revision(case, revision)
    workflow = _workflow(case)
    status = closing_status(case)
    if not status["fascicolo_sufficient"] or not status["baseline_screened"]:
        raise ValueError("Review fascicolo and baseline screening before adjustments")
    proposal_id = _id(payload["proposal_id"], "proposal_id")
    if any(p["proposal_id"] == proposal_id for p in workflow["proposals"]):
        raise ValueError("Adjustment proposal identifiers cannot be reused")
    codes = {
        r["account_code"] for r in workflow["versions"][0]["trial_balance"]["entries"]
    }
    lines = []
    for raw in payload["lines"]:
        code = str(raw["account_code"])
        debit, credit = normalize_decimal(raw["debit"]), normalize_decimal(
            raw["credit"]
        )
        if code not in codes or min(debit, credit) < 0 or bool(debit) == bool(credit):
            raise ValueError(
                "Closing lines require a known account and one positive debit or credit"
            )
        lines.append({"account_code": code, "debit": str(debit), "credit": str(credit)})
    if not 2 <= len(lines) <= 100 or sum(
        Decimal(l["debit"]) - Decimal(l["credit"]) for l in lines
    ):
        raise ValueError(
            "Closing adjustment debit and credit lines must balance exactly"
        )
    proposal = {
        "proposal_id": proposal_id,
        "subject_key": _id(payload["subject_key"], "subject_key"),
        "reason": _text(payload["reason"], "Adjustment reason"),
        "evidence": _documents(case, payload["evidence_refs"]),
        "prepared_by": actor,
        "lines": lines,
    }
    _mutate(case, actor, "closing_adjustment_proposed")
    workflow["proposals"].append(proposal)
    case["validation"] = None
    _record_event(
        case, "closing_adjustment_proposed", actor, {"proposal_id": proposal_id}
    )
    return case


def propose_closing_review(
    case: dict[str, Any],
    payload: Mapping[str, Any],
    actor: str,
    revision: str,
) -> dict[str, Any]:
    """Retain model/preparer interpretation without accepting its conclusions."""
    from xbrl_case import _ensure_revision, _mutate, _record_event

    _ensure_revision(case, revision)
    workflow = _workflow(case)
    proposal_id = _id(payload["proposal_id"], "proposal_id")
    if any(p["proposal_id"] == proposal_id for p in workflow["review_proposals"]):
        raise ValueError("Closing review proposal identifiers cannot be reused")
    if payload["kind"] not in {"FASCICOLO", "SCREENING", "AREAS"}:
        raise ValueError("Unknown closing review proposal kind")
    content = deepcopy(dict(payload["content"]))
    if len(json.dumps(content).encode()) > 65536:
        raise ValueError("Closing interpretation exceeds the bounded proposal size")
    proposal = {
        "proposal_id": proposal_id,
        "kind": payload["kind"],
        "content": content,
        "reason": _text(payload["reason"], "Proposal reason"),
        "evidence": _documents(case, payload["evidence_refs"]),
        "prepared_by": actor,
        "status": "MODEL_SUGGESTED",
    }
    _mutate(case, actor, "closing_review_proposed")
    workflow["review_proposals"].append(proposal)
    case["validation"] = None
    _record_event(case, "closing_review_proposed", actor, {"proposal_id": proposal_id})
    return case


def closing_status(case: Mapping[str, Any]) -> dict[str, Any]:
    """Project current states from immutable events; never rewrite a decision."""
    workflow = _workflow(case)
    states: dict[str, str] = {}
    requirements: dict[str, dict[str, Any]] = {}
    areas: dict[str, dict[str, Any]] = {}
    area_decisions: dict[str, str] = {}
    issues: dict[str, dict[str, Any]] = {}
    reconsiderations: dict[str, dict[str, Any]] = {}
    dependencies: dict[str, str] = {}
    baseline_screened = False
    sufficient = False
    selected_version = (
        workflow["versions"][0]["version_id"] if workflow["versions"] else None
    )
    screening: dict[str, Any] | None = None
    for event in workflow["events"]:
        record_id, kind, decision = event["record_id"], event["kind"], event["decision"]
        states[record_id] = "VALID"
        if kind == "FASCICOLO":
            requirements.update(
                {r["requirement_id"]: r for r in decision["requirements"]}
            )
            sufficient = decision["sufficient_to_start"]
        elif kind == "ISSUE":
            issues[decision["issue_id"]] = decision
        elif kind == "SCREENING":
            if (
                screening
                and screening["version_id"] != workflow["versions"][0]["version_id"]
            ):
                states[screening["record_id"]] = "SUPERSEDED"
            screening = {**decision, "record_id": record_id}
            selected_version = decision["version_id"]
            baseline_screened = True
            for scope in dependencies:
                dependencies[scope] = "REVIEW_REQUIRED"
        elif kind == "AREAS":
            for area in decision["areas"]:
                predecessor = area_decisions.get(area["area_id"])
                if predecessor:
                    states[predecessor] = "PARTIALLY_SUPERSEDED"
                area_decisions[area["area_id"]] = record_id
            areas.update({a["area_id"]: deepcopy(a) for a in decision["areas"]})
            issues.update({i["issue_id"]: i for i in decision.get("open_issues", [])})
        elif kind == "RECONSIDERATION":
            states[record_id] = "OPEN"
            reconsiderations[record_id] = {**decision, "state": "OPEN"}
            for target in decision["decision_ids"]:
                states[target] = "REVIEW_REQUIRED"
            for area_id in decision["area_ids"]:
                areas[area_id]["status"] = "REVIEW_REQUIRED"
                states[area_decisions[area_id]] = "PARTIAL_REVIEW_REQUIRED"
            for scope in decision["scopes"]:
                dependencies[scope] = "SUSPENDED"
        elif kind == "ADJUSTMENT" and decision["outcome"] == "APPROVED":
            if decision.get("supersedes"):
                states[decision["supersedes"]] = "SUPERSEDED"
            for review_id in decision.get("resolves_reconsiderations", []):
                reconsiderations[review_id]["state"] = "CLOSED"
                states[review_id] = "CLOSED"
            if screening and decision.get("supersedes"):
                states[screening["record_id"]] = "SUPERSEDED"
        elif kind == "CONTROL_REVIEW":
            for scope in decision["scopes"]:
                dependencies[scope] = "VALID"
    active = _active_adjustments(workflow)
    covered_documents = {
        ref["document_id"] for event in workflow["events"] for ref in event["evidence"]
    } | {
        ref["document_id"]
        for proposal in workflow["proposals"]
        for ref in proposal["evidence"]
    }
    area_data = case.get("area_review") or {}
    for event in area_data.get("events", []):
        payload = event["payload"]
        if event["kind"] == "PLAN":
            proposal = next(
                p for p in area_data["proposals"] if p["id"] == payload["proposal_id"]
            )
            covered_documents.update(proposal["evidence"])
            covered_documents.update(
                ref for a in proposal["content"]["areas"] for ref in a["evidence_refs"]
            )
        elif event["kind"] == "QUALITATIVE":
            proposal = next(
                p for p in area_data["qualitative"] if p["id"] == payload["proposal_id"]
            )
            covered_documents.add(proposal["document_id"])
        elif event["kind"] == "CONTROL":
            covered_documents.update(payload["evidence_refs"])
    unreviewed_sources = (
        [
            d["document_id"]
            for d in case["source_documents"]
            if d["purpose"]
            not in {
                "TRIAL_BALANCE",
                "TRIAL_BALANCE_PDF",
                "CLOSING_TRIAL_BALANCE_CANDIDATE",
            }
            and d["document_id"] not in covered_documents
        ]
        if baseline_screened
        else []
    )
    decided_proposals = {
        e["decision"]["proposal_id"]
        for e in workflow["events"]
        if e["kind"] == "ADJUSTMENT"
    }
    pending_proposals = [
        p["proposal_id"]
        for p in workflow["proposals"]
        if p["proposal_id"] not in decided_proposals
    ]
    screened_current_basis = bool(
        screening
        and screening["adjustment_basis_sha256"] == _adjustment_basis(workflow)
    )
    reviews_open = any(r["state"] == "OPEN" for r in reconsiderations.values())
    ready = bool(
        sufficient
        and screening
        and screening["closing_entries_included"]
        and screened_current_basis
        and not reviews_open
        and not pending_proposals
        and not unreviewed_sources
    )
    requests = [
        {"requirement_id": r["requirement_id"], "description": r["description"]}
        for r in requirements.values()
        if r.get("request_from_client")
    ]
    return {
        "accounting_origin": workflow["opening"]["accounting_origin"],
        "fascicolo_sufficient": sufficient,
        "baseline_screened": baseline_screened,
        "requirements": list(requirements.values()),
        "request_draft": {"status": "DRAFT", "items": requests, "sent": False},
        "decision_states": states,
        "areas": list(areas.values()),
        "open_issues": [i for i in issues.values() if i["status"] != "RESOLVED"],
        "reconsiderations": reconsiderations,
        "dependencies": dependencies,
        "active_adjustments": active,
        "selected_version_id": selected_version,
        "pending_adjustment_proposals": pending_proposals,
        "unreviewed_document_ids": unreviewed_sources,
        "current_trial_balance_valid": screened_current_basis and not reviews_open,
        "form_and_mapping_allowed": ready,
        "closure_allowed": ready
        and not any(i["status"] != "RESOLVED" for i in issues.values())
        and all(s == "VALID" for s in dependencies.values()),
        "register_count": len(workflow["events"]),
        "register_head_sha256": workflow["head_sha256"],
    }


def _validate_decision(
    case: Mapping[str, Any], payload: Mapping[str, Any], actor: str
) -> None:
    from xbrl_case import ParserConvention

    workflow = _workflow(case)
    kind, decision = payload["kind"], payload["decision"]
    status = closing_status(case)
    if decision.get("proposal_id") and kind != "ADJUSTMENT":
        proposal = next(
            (
                p
                for p in workflow["review_proposals"]
                if p["proposal_id"] == decision["proposal_id"]
            ),
            None,
        )
        if proposal is None or proposal["kind"] != kind:
            raise ValueError(
                "Professional decision references an incompatible interpretation proposal"
            )
    if kind == "FASCICOLO":
        requirements = decision["requirements"]
        known = {r["requirement_id"]: r for r in status["requirements"]}
        for item in requirements:
            _id(item["requirement_id"], "requirement_id")
            _text(item["description"], "Requirement description")
            _text(item["reason"], "Requirement reason")
            if item["status"] not in REQUIREMENT_STATES:
                raise ValueError("Unknown evidence sufficiency state")
            refs = item["evidence_refs"]
            if refs:
                _documents(case, refs)
            elif item["status"] not in {"MISSING", "NOT_APPLICABLE"}:
                raise ValueError("An available requirement needs documentary evidence")
            if item.get("request_from_client") and item["status"] not in {
                "MISSING",
                "AVAILABLE_STALE",
                "AVAILABLE_INSUFFICIENT",
            }:
                raise ValueError(
                    "Client requests can contain only confirmed documentary gaps"
                )
            known[item["requirement_id"]] = item
        if not isinstance(decision["sufficient_to_start"], bool):
            raise ValueError(
                "Fascicolo sufficiency requires an explicit professional decision"
            )
        if decision["sufficient_to_start"]:
            routed = {
                i.get("requirement_id")
                for i in status["open_issues"]
                if i.get("area_id")
            }
            if not known or any(
                r["status"] not in {"AVAILABLE_SUFFICIENT", "NOT_APPLICABLE"}
                and not (
                    r["status"] == "REVIEW_REQUIRED" and r["requirement_id"] in routed
                )
                for r in known.values()
            ):
                raise ValueError(
                    "Unresolved evidence requirements prevent a sufficient fascicolo"
                )
    elif kind == "SCREENING":
        if not status["fascicolo_sufficient"]:
            raise ValueError("Fascicolo must be sufficient before screening")
        version = next(
            (
                v
                for v in workflow["versions"]
                if v["version_id"] == decision["version_id"]
            ),
            None,
        )
        if version is None:
            raise ValueError("Screening references an unknown trial-balance version")
        ParserConvention(decision["convention"])
        if (
            version["trial_balance"]["layout"] == "CLOSING_BALANCES_ONLY"
            and decision["convention"] != "SIGNED_BALANCE_ONLY"
        ):
            raise ValueError("A closing-only source has no turnover columns to confirm")
        if decision["convention"] == "UNKNOWN" or not isinstance(
            decision["closing_entries_included"], bool
        ):
            raise ValueError(
                "Screening requires explicit convention and closing-entry assessment"
            )
        if set(decision["checks"]) != {
            "period",
            "comparative",
            "debit_credit",
            "closing_entries",
        } or any(value is not True for value in decision["checks"].values()):
            raise ValueError("Every screening check must be reviewed explicitly")
        if Decimal(version["trial_balance"]["calibration"]["closing_difference"]):
            raise ValueError("Trial balance debit and credit must reconcile exactly")
        if any(r["state"] == "OPEN" for r in status["reconsiderations"].values()):
            raise ValueError("An open reconsideration prevents screening confirmation")
        if status["baseline_screened"]:
            if status["pending_adjustment_proposals"]:
                raise ValueError(
                    "Review every proposed closing adjustment before confirming replacement accounts"
                )
            if (
                not decision["closing_entries_included"]
                or _reconcile(workflow, version["trial_balance"])["status"] != "MATCH"
            ):
                raise ValueError(
                    "Replacement trial balance does not exactly reflect approved adjustments"
                )
    elif kind == "ADJUSTMENT":
        proposal = next(
            (
                p
                for p in workflow["proposals"]
                if p["proposal_id"] == decision["proposal_id"]
            ),
            None,
        )
        if proposal is None or decision["outcome"] not in {"APPROVED", "REJECTED"}:
            raise ValueError(
                "Adjustment decision requires a known proposal and explicit outcome"
            )
        if proposal["prepared_by"] == actor:
            raise ValueError(
                "Adjustment preparer and professional approver must be distinct"
            )
        if any(
            e["kind"] == "ADJUSTMENT"
            and e["decision"]["proposal_id"] == proposal["proposal_id"]
            for e in workflow["events"]
        ):
            raise ValueError("A decided proposal cannot receive a second decision")
        if decision["outcome"] == "APPROVED":
            predecessors = {
                r: p
                for r, p in status["active_adjustments"].items()
                if p["subject_key"] == proposal["subject_key"]
            }
            if set(predecessors) != (
                {decision["supersedes"]} if decision.get("supersedes") else set()
            ):
                raise ValueError(
                    "A replacement must explicitly supersede the one active decision for its subject"
                )
            for review_id in decision.get("resolves_reconsiderations", []):
                review = status["reconsiderations"].get(review_id)
                if (
                    not review
                    or review["state"] != "OPEN"
                    or set(review["decision_ids"]) != set(predecessors)
                ):
                    raise ValueError(
                        "Replacement does not resolve the selected reconsideration"
                    )
                if any(
                    a
                    not in {
                        x["area_id"] for x in status["areas"] if x["status"] == "ACTIVE"
                    }
                    for a in review["area_ids"]
                ):
                    raise ValueError(
                        "Review affected area applicability before closing reconsideration"
                    )
    elif kind == "AREAS":
        if not decision.get("proposal_id"):
            raise ValueError(
                "Area applicability requires a retained interpretation proposal before confirmation"
            )
        if not status["form_and_mapping_allowed"]:
            # A post-closing evidence decision may resolve only its affected areas.
            affected = {
                a
                for r in status["reconsiderations"].values()
                if r["state"] == "OPEN"
                for a in r["area_ids"]
            }
            if (
                not affected
                or not {a["area_id"] for a in decision["areas"]} <= affected
            ):
                raise ValueError(
                    "Reviewed accounts are required before area applicability"
                )
        for area in decision["areas"]:
            _id(area["area_id"], "area_id")
            _text(area["reason"], "Area applicability reason")
            if area["status"] not in {"ACTIVE", "EXCLUDED"}:
                raise ValueError(
                    "Area applicability requires an explicit professional disposition"
                )
        for issue in decision.get("open_issues", []):
            _validate_issue(issue)
    elif kind == "ISSUE":
        _validate_issue(decision)
    elif kind == "FORM":
        require_closing_ready(case, "form")
        if decision["form"] not in (case.get("form_analysis") or {}).get(
            "eligible_forms", []
        ):
            raise ValueError(
                "Closing form decision must select an eligible statutory form"
            )
    elif kind == "CONTROL_REVIEW":
        if not status["current_trial_balance_valid"]:
            raise ValueError(
                "A replacement must be acquired and screened before dependent controls resume"
            )
        if (
            decision["version_id"] != status["selected_version_id"]
            or not decision["workpaper_refs"]
        ):
            raise ValueError("Control review requires current-version workpapers")
        _documents(case, decision["workpaper_refs"])
        if not decision["scopes"] or any(
            s not in status["dependencies"]
            or status["dependencies"][s] != "REVIEW_REQUIRED"
            for s in decision["scopes"]
        ):
            raise ValueError("Only reopened dependent controls can be confirmed")
    else:
        raise ValueError("Unsupported closing professional decision kind")


def _validate_issue(issue: Mapping[str, Any]) -> None:
    _id(issue["issue_id"], "issue_id")
    _id(issue["area_id"], "area_id")
    _text(issue["description"], "Issue description")
    if issue["status"] not in {"OPEN", "ROUTED", "RESOLVED"}:
        raise ValueError("Unknown professional issue status")


def record_closing_decision(
    case: dict[str, Any],
    payload: Mapping[str, Any],
    actor: str,
    revision: str,
) -> dict[str, Any]:
    """Apply one reviewer-owned decision; authority is enforced by CaseService."""
    from xbrl_case import (
        _clear_accounting_dependent_reviews,
        _ensure_revision,
        _mutate,
        _record_event,
    )

    _ensure_revision(case, revision)
    # Validate the complete event before mutating a caller's in-memory case.
    probe = deepcopy(case)
    _append(probe, payload, str(payload["kind"]), actor, "REVIEWER")
    _validate_decision(case, payload, actor)
    workflow = _workflow(case)
    kind, decision = str(payload["kind"]), deepcopy(dict(payload["decision"]))
    _mutate(case, actor, "closing_professional_decision")
    if kind == "SCREENING":
        version = next(
            v for v in workflow["versions"] if v["version_id"] == decision["version_id"]
        )
        decision["adjustment_basis_sha256"] = _adjustment_basis(workflow)
        decision["approved_decision_ids"] = list(_active_adjustments(workflow))
        decision["version_sha256"] = _hash(version["trial_balance"])
        if case["trial_balance"] != version["trial_balance"]:
            # Global computed statements must be rebuilt, while source decisions,
            # unaffected mappings and form choice remain available for review.
            before = {
                r["account_code"]: r["closing_signed"]
                for r in case["trial_balance"]["entries"]
            }
            changed_ids = {
                r["account_id"]
                for r in version["trial_balance"]["entries"]
                if before.get(r["account_code"]) != r["closing_signed"]
            }
            mappings = [
                deepcopy(m)
                for m in case["mappings"]
                if m["account_id"] not in changed_ids
            ]
            _clear_accounting_dependent_reviews(case)
            case["mappings"] = mappings
        case["trial_balance"] = deepcopy(version["trial_balance"])
        case["trial_balance"]["confirmed_convention"] = decision["convention"]
        case["trial_balance"]["closing_entries_review"] = {
            "appears_included": decision["closing_entries_included"],
            "status": "USER_CONFIRMED",
            "confirmed_by": actor,
        }
        case["trial_balance"]["calibration"]["closing_entries_assessment"] = deepcopy(
            case["trial_balance"]["closing_entries_review"]
        )
    elif kind == "FORM":
        _clear_accounting_dependent_reviews(case)
        case["selected_form"] = decision["form"]
    if decision.get("proposal_id"):
        proposals = (
            workflow["proposals"]
            if kind == "ADJUSTMENT"
            else workflow["review_proposals"]
        )
        proposal = next(
            p for p in proposals if p["proposal_id"] == decision["proposal_id"]
        )
        decision["proposal_sha256"] = _hash(proposal)
    event_payload = {**payload, "decision": decision}
    _append(case, event_payload, kind, actor, "REVIEWER")
    case["validation"] = None
    _record_event(
        case,
        "closing_professional_decision",
        actor,
        {"record_id": payload["record_id"], "kind": kind},
    )
    return case


def open_closing_reconsideration(
    case: dict[str, Any],
    payload: Mapping[str, Any],
    actor: str,
    revision: str,
) -> dict[str, Any]:
    """Record new evidence and suspend explicitly identified dependent reviews."""
    from xbrl_case import _ensure_revision, _mutate, _record_event

    _ensure_revision(case, revision)
    status = closing_status(case)
    decision = payload["decision"]
    active = status["active_adjustments"]
    if (
        not decision["decision_ids"]
        or not set(decision["decision_ids"]) <= active.keys()
    ):
        raise ValueError("Reconsideration must identify active adjustment decisions")
    if any(status["decision_states"][r] != "VALID" for r in decision["decision_ids"]):
        raise ValueError(
            "An adjustment already under reconsideration cannot be reopened twice"
        )
    if not decision["scopes"] or "validation" not in decision["scopes"]:
        raise ValueError(
            "Reconsideration must suspend its dependencies and overall validation"
        )
    mandatory_mappings = {
        "mapping:" + line["account_code"]
        for record_id in decision["decision_ids"]
        for line in active[record_id]["lines"]
    }
    if not mandatory_mappings <= set(decision["scopes"]):
        raise ValueError(
            "Reconsideration must suspend mapping for every affected account"
        )
    known_scopes = (
        {"validation"}
        | {"area:" + a["area_id"] for a in status["areas"]}
        | {"mapping:" + row["account_code"] for row in case["trial_balance"]["entries"]}
    )
    if not set(decision["scopes"]) <= known_scopes or len(
        set(decision["scopes"])
    ) != len(decision["scopes"]):
        raise ValueError(
            "Reconsideration scopes must be unique and refer to existing case dependencies"
        )
    if not set(decision["area_ids"]) <= {a["area_id"] for a in status["areas"]}:
        raise ValueError("Reconsideration references unknown areas")
    _append(deepcopy(case), payload, "RECONSIDERATION", actor, "PREPARER")
    _mutate(case, actor, "closing_reconsideration_opened")
    _append(case, payload, "RECONSIDERATION", actor, "PREPARER")
    case["validation"] = None
    _record_event(
        case,
        "closing_reconsideration_opened",
        actor,
        {"record_id": payload["record_id"]},
    )
    return case


def require_closing_ready(case: Mapping[str, Any], stage: str) -> None:
    """Enforce mechanical stage prerequisites without selecting accounting policy."""
    if not case.get("closing_workflow"):
        return
    status = closing_status(case)
    if not status["form_and_mapping_allowed"]:
        raise ValueError(
            "Closing fascicolo, screening and approved adjustments must be reviewed before form or mapping"
        )
    if stage == "mapping" and not any(
        e["kind"] == "FORM" for e in case["closing_workflow"]["events"]
    ):
        raise ValueError("Record the professional form decision before mapping")


def closing_validation_issues(case: Mapping[str, Any]) -> list[dict[str, str]]:
    """Keep unresolved closing work blocking across the ordinary approval path."""
    if not case.get("closing_workflow"):
        return []
    status = closing_status(case)
    issues = []
    if not status["form_and_mapping_allowed"]:
        issues.append(
            {
                "rule_id": "CLOSING.REVIEW_REQUIRED",
                "message": "Closing evidence, screening or replacement accounts remain unreviewed",
            }
        )
    for scope, state in status["dependencies"].items():
        if state != "VALID":
            issues.append(
                {
                    "rule_id": "CLOSING.DEPENDENCY_REVIEW_REQUIRED",
                    "message": f"{scope}: {state}",
                }
            )
    for issue in status["open_issues"]:
        issues.append(
            {
                "rule_id": "CLOSING.OPEN_PROFESSIONAL_ISSUE",
                "message": f"{issue['issue_id']}: {issue['description']}",
            }
        )
    return issues
