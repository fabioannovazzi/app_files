"""Construction records: fixed lineage and arithmetic, model-led case judgments."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import datetime
from fractions import Fraction
from typing import Any, cast

__all__ = [
    "apply_event",
    "assessment_basis",
    "create_case",
    "digest",
    "evaluate",
    "manual_basis",
    "manual_status",
    "validate_catalog",
    "verify_snapshot",
]

SCHEMA = "vera.assetti_construction.v1"
STAGES = {
    "unknown": None,
    "absence": 0,
    "partial": 1,
    "designed": 2,
    "operating": 3,
    "monitored": 4,
}
COLLECTIONS = (
    "visits",
    "answers",
    "evidence",
    "assessments",
    "decisions",
    "findings",
    "controls",
    "actions",
    "manuals",
    "adoptions",
    "executions",
    "operation_reviews",
    "artifacts",
    "objectives",
    "strategy_links",
    "kpis",
    "kpi_observations",
    "strategy_reviews",
)


def digest(value: Any) -> str:
    """Hash canonical UTF-8 JSON; hashes establish integrity, never truth."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def text(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"Missing {label}")
    return value


def fields(row: dict, *names: str) -> None:
    for name in names:
        text(row.get(name), name)


def timestamp(value: Any) -> str:
    value = text(value, "timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.utcoffset() is not None, "Timestamp needs a timezone")
    return value


def refs(value: Any, known: dict, label: str, *, empty: bool = False) -> list:
    require(isinstance(value, list) and (empty or bool(value)), f"Missing {label}")
    require(all(isinstance(v, str) and v in known for v in value), f"Unknown {label}")
    require(len(set(value)) == len(value), f"Duplicate {label}")
    return value


def score(value: Any, *, optional: bool = True) -> None:
    require(
        (optional and value is None) or (type(value) is int and 0 <= value <= 4),
        "Score must be an integer 0–4 or unknown",
    )


def validate_catalog(catalog: dict) -> None:
    """Weights and mappings are an explicit study proposal, not inferred law."""
    fields(catalog, "methodology_version", "status", "disclaimer")
    require(
        catalog["status"] in {"pilot_proposal", "approved", "retired"},
        "Invalid method status",
    )
    require(
        isinstance(catalog.get("domains"), list) and bool(catalog["domains"]),
        "Missing domains",
    )
    require(
        isinstance(catalog.get("criteria"), list) and bool(catalog["criteria"]),
        "Missing criteria",
    )
    domains = {}
    for rows, key in (
        (catalog["domains"], "domain"),
        (catalog["criteria"], "criterion"),
    ):
        seen = set()
        for row in rows:
            fields(row, "id")
            require(row["id"] not in seen, f"Duplicate {key}")
            seen.add(row["id"])
            weight = row.get("weight")
            require(
                type(weight) in (int, float) and math.isfinite(weight) and weight > 0,
                "Weights must be finite and positive",
            )
            if key == "domain":
                domains[row["id"]] = row
            else:
                fields(row, "title", "question", "expected_outcome")
                require(row.get("domain") in domains, "Unknown criterion domain")
                require(
                    set(row.get("anchors", {})) == {"0", "1", "2", "3", "4"},
                    "Missing anchors",
                )
    if catalog["status"] == "approved":
        fields(catalog, "approval_actor", "approval_statement", "approval_source")
        timestamp(catalog.get("approved_at"))
    if catalog.get("full_uni_mapping"):
        require(
            all(
                m.get("status") != "pending_full_text"
                for c in catalog["criteria"]
                for m in c.get("source_mapping", [])
            ),
            "UNI full-text mapping is pending",
        )
        fields(catalog, "mapping_review", "mapping_source")


def _seal(state: dict) -> dict:
    state.pop("snapshot_sha256", None)
    state["snapshot_sha256"] = digest(state)
    return state


def verify_snapshot(state: dict) -> None:
    require(state.get("schema_version") == SCHEMA, "Not a construction snapshot")
    require(
        state.get("snapshot_sha256")
        == digest({k: v for k, v in state.items() if k != "snapshot_sha256"}),
        "Snapshot digest mismatch",
    )


def create_case(
    *,
    client_id: str,
    engagement_id: str,
    case_id: str,
    entity_name: str,
    catalog: dict,
    actor: str,
    at: str,
) -> dict:
    """Open the same native archive engagement with all unvisited criteria unknown."""
    for name, value in locals().copy().items():
        if name != "catalog":
            text(value, name)
    timestamp(at)
    validate_catalog(catalog)
    state = {
        "schema_version": SCHEMA,
        "workflow_id": "adeguati-assetti",
        "mode": "construction",
        "client_id": client_id,
        "engagement_id": engagement_id,
        "case_id": case_id,
        "entity_name": entity_name,
        "revision": 0,
        "created_by": actor,
        "created_at": at,
        "scope": None,
        "catalog": copy.deepcopy(catalog),
        "cursor": {},
        "baseline_review": None,
        "legacy_reviews": {},
        "audit": [],
        "identity_assurance": "attributed_local_statement_not_authenticated_signature",
    }
    state.update({name: {} for name in COLLECTIONS})
    return _seal(state)


def _criterion(state: dict, criterion_id: str) -> dict:
    rows = {r["id"]: r for r in state["catalog"]["criteria"]}
    require(criterion_id in rows, "Unknown criterion")
    return rows[criterion_id]


def assessment_basis(state: dict, criterion_id: str) -> str:
    """Bind interpretation to method, scope, and every explicitly related fact."""
    criterion = _criterion(state, criterion_id)
    row = {
        k: v
        for k, v in state["assessments"].get(criterion_id, {}).items()
        if k not in {"qualification_review", "revision", "created_by", "created_at"}
    }
    evidence = {
        k: v
        for k, v in state["evidence"].items()
        if criterion_id in v["criterion_ids"] or k in row.get("evidence_refs", [])
    }
    answers = {
        k: v
        for k, v in state["answers"].items()
        if criterion_id in v.get("criterion_ids", [])
    }
    return digest(
        {
            "criterion": criterion,
            "catalog": digest(state["catalog"]),
            "scope": state["scope"],
            "assessment": row,
            "evidence": evidence,
            "answers": answers,
        }
    )


def _attestation(state: dict, row: dict) -> None:
    fields(row, "statement")
    refs(row.get("evidence_refs"), state["evidence"], "decision evidence")


def evaluate(state: dict) -> dict:
    """Apply BASE-1 only after explicit qualification; aggregate exact weights."""
    rows = []
    for criterion in state["catalog"]["criteria"]:
        cid = criterion["id"]
        raw = state["assessments"].get(cid, {})
        basis = assessment_basis(state, cid)
        reviewed = raw.get("qualification_review", {}).get("basis_sha256") == basis
        applicability = raw.get("applicability", "pending")
        na = (
            applicability == "not_applicable"
            and reviewed
            and bool(raw.get("na_reason"))
        )
        stage = raw.get("evidence_stage", "unknown")
        candidate = STAGES[stage]
        contradiction = raw.get("material_contradiction", False)
        base = (
            candidate
            if reviewed and applicability == "applicable" and not contradiction
            else None
        )
        current_decisions = [
            d for d in state["decisions"].values() if d["criterion_id"] == cid
        ]
        decision = current_decisions[-1] if current_decisions else None
        effective, status = base, "none"
        if decision:
            status = decision["status"]
            if status == "recorded":
                status = "recorded" if decision["basis_sha256"] == basis else "stale"
                if status == "recorded":
                    effective = decision["after_score"]
        if na:
            effective = None
        rows.append(
            {
                "id": cid,
                "title": criterion["title"],
                "domain": criterion["domain"],
                "weight": criterion["weight"],
                "excluded": na,
                "applicability": applicability,
                "qualification_pending": not reviewed,
                "claimed": raw.get("claimed_level"),
                "candidate": candidate,
                "base": base,
                "effective": effective,
                "target": raw.get("target_score"),
                "decision_status": status,
                "decision": decision,
                "beyond_verified_evidence": effective is not None
                and (base is None or effective > base),
                "unresolved_contradiction": contradiction,
                "proposal_digest": basis,
                "trace": {
                    "rule": "BASE-1",
                    "stage": stage,
                    "methodology": state["catalog"]["methodology_version"],
                    "evidence_refs": raw.get("evidence_refs", []),
                },
            }
        )
    weights = {d["id"]: Fraction(str(d["weight"])) for d in state["catalog"]["domains"]}

    def summary(key: str) -> dict:
        active = [r for r in rows if not r["excluded"]]
        if not active:
            return dict(
                index=None,
                coverage=None,
                lower=None,
                upper=None,
                status="no_applicable_criteria",
            )
        domain_total = sum(weights[d] for d in {r["domain"] for r in active})
        known, weighted = Fraction(0), Fraction(0)
        for row in active:
            domain_rows = [r for r in active if r["domain"] == row["domain"]]
            total = sum(Fraction(str(r["weight"])) for r in domain_rows)
            weight = (
                weights[row["domain"]]
                / domain_total
                * Fraction(str(row["weight"]))
                / total
            )
            if row[key] is not None:
                known += weight
                weighted += weight * row[key]
        return {
            "index": float(25 * weighted / known) if known else None,
            "coverage": float(100 * known),
            "lower": float(25 * weighted),
            "upper": float(25 * weighted + 100 * (1 - known)),
            "status": "covered" if known == 1 else "partial" if known else "unverified",
        }

    return {
        "rows": rows,
        "base": summary("base"),
        "professional": summary("effective"),
        "excluded_ids": [r["id"] for r in rows if r["excluded"]],
        "unknown_base_ids": [
            r["id"] for r in rows if not r["excluded"] and r["base"] is None
        ],
        "critical_findings": list(state["findings"].values()),
        "adequacy_judgment": None,
        "certification": False,
    }


def manual_basis(state: dict, control_ids: list[str]) -> dict:
    """Snapshot selected processes only, so independent work can continue."""
    refs(control_ids, state["controls"], "manual controls")
    controls = {cid: state["controls"][cid] for cid in control_ids}
    criteria = {cid for c in controls.values() for cid in c["criterion_ids"]}
    findings = {
        fid: state["findings"][fid]
        for c in controls.values()
        for fid in c["finding_ids"]
    }
    actions = {k: v for k, v in state["actions"].items() if v["control_id"] in controls}
    return {
        "scope": state["scope"],
        "catalog_sha256": digest(state["catalog"]),
        "controls": controls,
        "findings": findings,
        "actions": actions,
        "assessment_digests": {
            cid: assessment_basis(state, cid) for cid in sorted(criteria)
        },
        "score_decisions": {
            k: v for k, v in state["decisions"].items() if v["criterion_id"] in criteria
        },
        "objectives": state["objectives"],
        "kpis": state["kpis"],
        "strategy_links": state["strategy_links"],
        "artifacts": state["artifacts"],
    }


def manual_status(state: dict, manual_id: str) -> str:
    manual = state["manuals"][manual_id]
    if manual["basis_sha256"] != digest(manual_basis(state, manual["control_ids"])):
        return "needs_review"
    if not manual.get("professional_review"):
        return "draft"
    if any(
        a["manual_id"] == manual_id and a["manual_sha256"] == manual["manual_sha256"]
        for a in state["adoptions"].values()
    ):
        return "adopted"
    return "professionally_reviewed"


def _put(
    state: dict,
    collection: str,
    payload: dict,
    actor: str,
    at: str,
    *,
    immutable: bool = False,
) -> None:
    fields(payload, "id")
    previous = state[collection].get(payload["id"])
    require(
        not (immutable and previous),
        f"{collection} record already exists; append a new ID",
    )
    state[collection][payload["id"]] = {
        **copy.deepcopy(payload),
        "revision": (previous["revision"] + 1) if previous else 1,
        "created_by": actor,
        "created_at": at,
    }


def apply_event(state: dict, event: dict, *, actor: str, at: str) -> dict:
    """Return a new revision; declared actor is attribution, not authentication."""
    verify_snapshot(state)
    text(actor, "actor")
    timestamp(at)
    kind = text(event.get("kind"), "event kind")
    p = copy.deepcopy(event.get("payload"))
    require(isinstance(p, dict), "Event payload must be an object")
    p = cast(dict, p)
    result = copy.deepcopy(state)
    if kind == "scope":
        fields(p, "description", "proportionality", "limitations")
        result["scope"] = p
    elif kind == "methodology":
        validate_catalog(p)
        require(
            p["methodology_version"] != state["catalog"]["methodology_version"],
            "Method change needs a new version",
        )
        require(
            {c["id"] for c in p["criteria"]}
            == {c["id"] for c in state["catalog"]["criteria"]},
            "Keep criterion identities for historical comparison; open a new case for a different catalog",
        )
        result["catalog"] = p
    elif kind == "cursor":
        fields(p, "summary", "next_step")
        result["cursor"] = p
    elif kind in {"visit", "answer", "evidence"}:
        if kind == "visit":
            fields(p, "agenda", "participants", "observations", "limitations")
            fields(p, "date")
            collection = "visits"
        elif kind == "answer":
            fields(
                p, "question_id", "question", "original", "speaker", "mode", "status"
            )
            fields(p, "date")
            require(
                p["status"] in {"answered", "to_verify", "unknown"},
                "Invalid answer state",
            )
            require(
                p["mode"] in {"text", "html", "reviewed_transcript"},
                "Unsupported capture mode",
            )
            require(
                isinstance(p.get("summary", ""), str), "Summary must be separate text"
            )
            refs(
                p.get("evidence_refs", []),
                state["evidence"],
                "answer evidence",
                empty=True,
            )
            collection = "answers"
        else:
            fields(
                p,
                "source_id",
                "path",
                "sha256",
                "locator",
                "evidence_class",
                "limitations",
            )
            for date_field in ("event_date", "acquired_at", "period", "author"):
                require(
                    date_field in p
                    and (p[date_field] is None or isinstance(p[date_field], str)),
                    f"Record {date_field}, using null when unknown",
                )
            require(
                len(p["sha256"]) == 64
                and all(c in "0123456789abcdef" for c in p["sha256"]),
                "Invalid source hash",
            )
            require(
                p["evidence_class"]
                in {
                    "document",
                    "statement",
                    "observation",
                    "execution",
                    "decision",
                    "transcript",
                },
                "Invalid evidence class",
            )
            collection = "evidence"
        if kind != "visit":
            refs(
                p.get("criterion_ids"),
                {c["id"]: c for c in state["catalog"]["criteria"]},
                "criteria",
                empty=True,
            )
        _put(result, collection, p, actor, at)
    elif kind == "assessment":
        _criterion(state, text(p.get("id"), "criterion ID"))
        fields(p, "rationale", "adequacy_judgment")
        require(
            p.get("applicability") in {"pending", "applicable", "not_applicable"},
            "Invalid applicability",
        )
        require(p.get("evidence_stage") in STAGES, "Invalid evidence stage")
        score(p.get("claimed_level"))
        score(p.get("target_score"))
        require(
            type(p.get("material_contradiction")) is bool, "Declare contradiction state"
        )
        refs(
            p.get("evidence_refs"),
            state["evidence"],
            "assessment evidence",
            empty=p["evidence_stage"] == "unknown",
        )
        if p["material_contradiction"]:
            fields(p, "contradiction", "clarification_needed")
        if p["applicability"] == "not_applicable":
            fields(p, "na_reason")
        p.pop("qualification_review", None)
        _put(result, "assessments", p, actor, at)
    elif kind == "qualification_review":
        cid = text(p.get("criterion_id"), "criterion ID")
        require(cid in state["assessments"], "Missing assessment")
        require(
            p.get("basis_sha256") == assessment_basis(state, cid),
            "Qualification is stale",
        )
        _attestation(state, p)
        result["assessments"][cid]["qualification_review"] = {
            **p,
            "actor": actor,
            "at": at,
        }
    elif kind == "score_decision":
        cid = text(p.get("criterion_id"), "criterion ID")
        _criterion(state, cid)
        require(
            p.get("status") in {"proposed", "recorded", "revoked"},
            "Invalid score decision status",
        )
        fields(
            p,
            "reason_code",
            "rationale",
            "alternative_considered",
            "residual_risk",
            "action_impact",
            "review_trigger",
        )
        refs(p.get("evidence_refs"), state["evidence"], "decision evidence")
        score(p.get("after_score"), optional=False)
        score(p.get("before_score"))
        require(
            p.get("basis_sha256") == assessment_basis(state, cid), "Decision is stale"
        )
        row = next(r for r in evaluate(state)["rows"] if r["id"] == cid)
        require(
            row["applicability"] == "applicable",
            "Resolve applicability before an override",
        )
        require(
            p.get("before_score") == row["base"],
            "Decision must preserve the exact base",
        )
        if p["status"] == "recorded":
            _attestation(state, p)
        _put(result, "decisions", p, actor, at, immutable=True)
    elif kind == "baseline_review":
        require(state["scope"] is not None, "Scope required")
        require(
            p.get("assessment_sha256") == digest(evaluate(state)),
            "Baseline review is stale",
        )
        _attestation(state, p)
        require(
            not any(
                r["applicability"] == "not_applicable" and not r["excluded"]
                for r in evaluate(state)["rows"]
            ),
            "Unapproved N/A cannot be finalized",
        )
        result["baseline_review"] = {**p, "actor": actor, "at": at}
    elif kind in {"finding", "control", "action"}:
        if kind == "finding":
            fields(
                p,
                "observation",
                "interpretation",
                "consequence",
                "alternatives",
                "priority_reason",
            )
            refs(p.get("evidence_refs"), state["evidence"], "finding evidence")
            collection = "findings"
        elif kind == "control":
            fields(
                p,
                "title",
                "risk",
                "outcome",
                "owner",
                "decision_owner",
                "substitute",
                "inputs",
                "outputs",
                "frequency",
                "exceptions",
                "response_time",
                "archive",
                "execution_evidence",
            )
            require(
                p.get("role_status") in {"proposed", "confirmed"},
                "Role status required",
            )
            require(
                p.get("timing_status") in {"proposed", "confirmed"},
                "Timing status required",
            )
            require(
                isinstance(p.get("steps"), list) and bool(p["steps"]),
                "Control needs ordered steps",
            )
            for step in p["steps"]:
                text(step, "control step")
            refs(
                p.get("finding_ids"), state["findings"], "control findings", empty=True
            )
            require(
                isinstance(p.get("register_fields"), list)
                and bool(p["register_fields"]),
                "Control needs register fields",
            )
            require(
                all(isinstance(f, str) and f.strip() for f in p["register_fields"]),
                "Invalid register fields",
            )
            require(
                len(set(p["register_fields"])) == len(p["register_fields"]),
                "Duplicate register fields",
            )
            if p["role_status"] == "confirmed" or p["timing_status"] == "confirmed":
                refs(
                    p.get("confirmation_evidence"),
                    state["evidence"],
                    "role/timing confirmation",
                )
            collection = "controls"
        else:
            fields(
                p,
                "proposal",
                "owner",
                "timing",
                "priority_reason",
                "completion_criterion",
                "status",
            )
            require(p.get("control_id") in state["controls"], "Unknown action control")
            refs(p.get("finding_ids"), state["findings"], "action findings", empty=True)
            require(
                p["status"]
                in {
                    "proposed",
                    "agreed",
                    "in_progress",
                    "document_prepared",
                    "completed",
                    "rejected",
                    "deferred",
                },
                "Invalid action status",
            )
            require(
                p.get("owner_status") in {"proposed", "confirmed"},
                "Owner status required",
            )
            require(
                p.get("timing_status") in {"proposed", "confirmed"},
                "Timing status required",
            )
            if p["status"] in {"completed", "rejected"}:
                fields(p, "disposition", "residual_risk")
                refs(
                    p.get("disposition_evidence"),
                    state["evidence"],
                    "action disposition evidence",
                )
            if (
                p["owner_status"] == "confirmed"
                or p["timing_status"] == "confirmed"
                or p["status"] == "agreed"
            ):
                refs(
                    p.get("confirmation_evidence"),
                    state["evidence"],
                    "action confirmation evidence",
                )
            require(
                p.get("completion_kind") in {"document", "investigation", "operation"},
                "Declare action completion kind",
            )
            if p.get("completion_kind") == "operation" and p["status"] == "completed":
                refs(p.get("execution_ids"), state["executions"], "action execution")
                require(
                    all(
                        state["executions"][x]["control_id"] == p["control_id"]
                        and state["executions"][x]["kind"] == "real"
                        and state["executions"][x]["control_sha256"]
                        == digest(state["controls"][p["control_id"]])
                        for x in p["execution_ids"]
                    ),
                    "Completion requires real executions of the current control",
                )
            collection = "actions"
        if kind != "action":
            refs(
                p.get("criterion_ids"),
                {c["id"]: c for c in state["catalog"]["criteria"]},
                "criteria",
            )
        _put(result, collection, p, actor, at)
    elif kind == "manual_compile":
        fields(p, "id", "introduction", "limitations")
        basis = manual_basis(state, cast(list[str], p.get("control_ids")))
        p["snapshot"] = basis
        p["basis_sha256"] = digest(basis)
        p["professional_review"] = None
        p["manual_sha256"] = digest(p)
        _put(result, "manuals", p, actor, at, immutable=True)
    elif kind == "manual_review":
        mid = text(p.get("manual_id"), "manual ID")
        require(mid in state["manuals"], "Unknown manual")
        require(
            manual_status(state, mid) != "needs_review", "Manual dependencies changed"
        )
        require(
            p.get("manual_sha256") == state["manuals"][mid]["manual_sha256"],
            "Wrong manual version",
        )
        _attestation(state, p)
        included = state["manuals"][mid]["snapshot"]["findings"]
        require(
            isinstance(p.get("finding_dispositions"), dict)
            and set(p["finding_dispositions"]) == set(included),
            "Address every included finding",
        )
        for value in p["finding_dispositions"].values():
            text(value, "finding disposition")
        result["manuals"][mid]["professional_review"] = {**p, "actor": actor, "at": at}
    elif kind == "adoption":
        mid = text(p.get("manual_id"), "manual ID")
        require(
            mid in state["manuals"]
            and manual_status(state, mid) in {"professionally_reviewed", "adopted"},
            "Adoption requires the reviewed current manual",
        )
        require(
            p.get("manual_sha256") == state["manuals"][mid]["manual_sha256"],
            "Wrong adoption version",
        )
        fields(p, "competent_person", "decision", "effective_date", "reservations")
        _attestation(state, p)
        _put(result, "adoptions", p, actor, at, immutable=True)
    elif kind == "execution":
        cid = text(p.get("control_id"), "control ID")
        mid = text(p.get("manual_id"), "manual ID")
        require(
            mid in state["manuals"] and manual_status(state, mid) == "adopted",
            "Execution requires the current adopted manual",
        )
        require(
            cid in state["manuals"][mid]["control_ids"], "Control not in adopted manual"
        )
        require(
            p.get("control_sha256") == digest(state["controls"][cid]),
            "Wrong execution control version",
        )
        fields(
            p,
            "period",
            "cycle",
            "executor",
            "exceptions",
            "recipient",
            "decision",
            "closure",
        )
        require(
            p.get("kind") in {"real", "simulation"},
            "Distinguish real operation from simulation",
        )
        refs(p.get("evidence_refs"), state["evidence"], "execution evidence")
        _put(result, "executions", p, actor, at, immutable=True)
    elif kind == "operation_review":
        refs(p.get("execution_ids"), state["executions"], "operating review executions")
        fields(p, "scope", "sample", "conclusion", "limitations", "next_review")
        require(
            p.get("outcome")
            in {
                "design_only",
                "operating_supported",
                "operating_not_supported",
                "limited",
            },
            "Record the professional operating conclusion explicitly",
        )
        require(
            isinstance(p.get("action_dispositions"), dict)
            and set(p["action_dispositions"]) == set(state["actions"]),
            "Address every prior action",
        )
        for value in p["action_dispositions"].values():
            text(value, "action disposition")
        _attestation(state, p)
        p["sample_contains_real_executions_only"] = all(
            state["executions"][x]["kind"] == "real" for x in p["execution_ids"]
        )
        require(
            p["outcome"] != "operating_supported"
            or p["sample_contains_real_executions_only"],
            "Simulation cannot support a conclusion of actual operation",
        )
        p["control_ids"] = sorted(
            {state["executions"][x]["control_id"] for x in p["execution_ids"]}
        )
        require(
            p["outcome"] != "operating_supported"
            or all(
                state["executions"][x]["control_sha256"]
                == digest(state["controls"][state["executions"][x]["control_id"]])
                for x in p["execution_ids"]
            ),
            "Prior control versions cannot support current operation",
        )
        p["control_sha256"] = {
            cid: digest(state["controls"][cid]) for cid in p["control_ids"]
        }
        _put(result, "operation_reviews", p, actor, at, immutable=True)
    elif kind == "intake_import":
        from construction_intake import import_intake, parse_markdown

        fields(p, "content", "source_id")
        require(
            p["source_id"] in state["evidence"], "Import the original intake file first"
        )
        require(
            hashlib.sha256(p["content"].encode()).hexdigest()
            == state["evidence"][p["source_id"]]["sha256"],
            "Intake text differs from its original source",
        )
        import_intake(
            result,
            parse_markdown(p["content"]),
            source_id=p["source_id"],
            actor=actor,
            at=at,
        )
    elif kind in {
        "objective",
        "strategy_link",
        "kpi",
        "kpi_observation",
        "strategy_review",
        "artifact",
        "legacy_review",
    }:
        # Typed adapters own these contracts; imported content never becomes code.
        from construction_adapters import apply_typed_record

        apply_typed_record(result, kind, p, actor=actor, at=at)
    else:
        raise ValueError(f"Unsupported construction event: {kind}")
    result["revision"] += 1
    result["audit"].append(
        {
            "revision": result["revision"],
            "kind": kind,
            "actor": actor,
            "at": at,
            "payload": p,
            "before_sha256": state["snapshot_sha256"],
        }
    )
    return _seal(result)
