"""Deterministic arithmetic after explicit professional classifications.

No semantic legal decisions, tax return transmission, signatures or network IO.
All output is a review draft. JSON reviewer names are attestations, not identity
authentication; a production host must authenticate and persist those decisions.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from .contracts import ContractError, canonical_hash, indexed, validate, verify_evidence

__all__ = ["amount", "money", "calculate", "approval_record"]

MONEY = Decimal("0.01")
TAXES = ("income", "irap")
CASE_GATES = ("SUBJECT", "OPTION", "HISTORY")
IP_GATES = ("IP", "RIGHTS", "ACTIVITY", "USE")
LINE_GATES = ("COST", "LINKAGE", "ALLOCATION", "INCENTIVES")


def amount(value: str) -> Decimal:
    return Decimal(value)


def money(value: Decimal) -> str:
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), ".2f")


def _status(
    controls: list[dict[str, Any]],
    required: Any,
    evidence_ids: set[str],
    source_ids: set[str],
    as_of: date,
) -> tuple[str, list[str]]:
    records = indexed(controls, "gate")
    problems = []
    failed = False
    for gate in required:
        row = records.get(gate)
        if row is None:
            problems.append(f"{gate}:NOT_TESTED")
            continue
        if row["status"] != "PASS":
            problems.append(f"{gate}:{row['status']}")
        if row["status"] in ("PASS", "FAIL"):
            review_problems = []
            if (
                not row["reviewer"]
                or not row["reviewer"].strip()
                or not row["reviewed_on"]
                or date.fromisoformat(row["reviewed_on"]) > as_of
            ):
                review_problems.append(f"{gate}:MISSING_OR_FUTURE_REVIEW")
            if not row["conclusion"].strip():
                review_problems.append(f"{gate}:MISSING_RATIONALE")
            if not row["evidence_ids"] or not set(row["evidence_ids"]) <= evidence_ids:
                review_problems.append(f"{gate}:MISSING_EVIDENCE")
            if not row["source_ids"] or not set(row["source_ids"]) <= source_ids:
                review_problems.append(f"{gate}:MISSING_SOURCE")
            problems.extend(review_problems)
            # An unreviewed negative claim is not a definitive exclusion.
            if row["status"] == "FAIL" and not review_problems:
                failed = True
    return ("EXCLUDED" if failed else "SUSPENDED" if problems else "INCLUDED"), problems


def calculate(
    case: dict[str, Any],
    rules: dict[str, Any],
    *,
    evidence_root: str | Path,
    as_of: str,
) -> dict[str, Any]:
    validate(case, "case.schema.json")
    validate(rules, "ruleset.schema.json")
    today = date.fromisoformat(as_of)
    if case["demo"] != rules["demo"]:
        raise ContractError("Demo and real inputs cannot be mixed")
    if (
        rules["status"] != "REVIEWED"
        or not rules["reviewer"]
        or not rules["reviewer"].strip()
    ):
        raise ContractError("Ruleset requires professional review")
    if not rules["reviewed_on"] or not rules["sources_checked_on"]:
        raise ContractError("Ruleset review date and source preflight date required")
    if date.fromisoformat(rules["reviewed_on"]) > today:
        raise ContractError("Ruleset review is in the future")
    if (
        not date.fromisoformat(rules["valid_from"])
        <= today
        <= date.fromisoformat(rules["valid_until"])
    ):
        raise ContractError("Ruleset outside its explicit review-validity window")
    checked = date.fromisoformat(rules["sources_checked_on"])
    if checked > today or (today - checked).days > rules["max_source_age_days"]:
        raise ContractError("Source preflight stale or in the future")
    sources = indexed(rules["sources"], "source_id")
    if not sources or any(
        s["status"] != "REVIEWED" or not s["snapshot_sha256"] for s in sources.values()
    ):
        raise ContractError("Every active rule source needs a reviewed snapshot")
    if not case["demo"] and any(
        s["authority_type"] == "SYNTHETIC" for s in sources.values()
    ):
        raise ContractError("Synthetic sources are forbidden on real cases")
    evidence = verify_evidence(case["evidence"], evidence_root)
    for source in sources.values():
        ev = evidence.get(source["snapshot_evidence_id"])
        if not ev or ev["sha256"] != source["snapshot_sha256"]:
            raise ContractError("Source snapshot does not match case evidence")
    eids, sids = set(evidence), set(sources)
    periods = indexed(case["periods"], "period_id")
    ordered = sorted(periods.values(), key=lambda p: p["sequence"])
    for i, period in enumerate(ordered):
        if period["start"] > period["end"]:
            raise ContractError("Invalid fiscal period")
        if i:
            prior = ordered[i - 1]
            if period["sequence"] != prior["sequence"] + 1:
                raise ContractError("Fiscal period sequence has a gap or duplicate")
            if date.fromisoformat(period["start"]) != date.fromisoformat(
                prior["end"]
            ) + timedelta(days=1):
                raise ContractError("Fiscal periods overlap or are not contiguous")
    current = periods.get(case["claim_period_id"])
    if not current:
        raise ContractError("Unknown claim period")
    if not (
        rules["tax_period_start_min"]
        <= current["start"]
        <= rules["tax_period_start_max"]
    ):
        raise ContractError("Tax period not covered by ruleset")
    ips = indexed(case["ips"], "ip_id")
    costs = indexed(case["costs"], "cost_id")
    allocations = indexed(case["allocations"], "allocation_id")
    if sum((amount(c["book_amount"]) for c in costs.values()), Decimal(0)) != amount(
        case["ledger_control_total"]
    ):
        raise ContractError(
            "Accounting population does not reconcile to its reviewed control total"
        )
    # ID duplicates and duplicate source rows must both be checked.
    indexed(case["costs"], "ledger_row_key")
    for cost in costs.values():
        if cost["period_id"] not in periods or cost["evidence_id"] not in evidence:
            raise ContractError("Unknown cost period/evidence")
        if amount(cost["income_max"]) > amount(cost["book_amount"]) or amount(
            cost["irap_max"]
        ) > amount(cost["book_amount"]):
            raise ContractError("Reviewed tax basis exceeds normalized source cost")
    used = {(cid, tax): Decimal(0) for cid in costs for tax in TAXES}
    for line in allocations.values():
        if line["cost_id"] not in costs or line["ip_id"] not in ips:
            raise ContractError("Unknown cost/IP reference")
        for tax in TAXES:
            used[line["cost_id"], tax] += amount(line[f"{tax}_amount"])
    for cid, cost in costs.items():
        for tax in TAXES:
            if used[cid, tax] > amount(cost[f"{tax}_max"]):
                raise ContractError(f"Overallocation of {cid}/{tax}")
    history = indexed(case["prior_claims"], "claim_id")
    historical = {(cid, tax): Decimal(0) for cid in costs for tax in TAXES}
    for prior in history.values():
        if (
            prior["cost_id"] not in costs
            or prior["claim_period_id"] not in periods
            or prior["evidence_id"] not in evidence
        ):
            raise ContractError("Unknown prior-claim reference")
        if periods[prior["claim_period_id"]]["sequence"] >= current["sequence"]:
            raise ContractError("Prior claims must precede this claim")
        if (
            periods[prior["claim_period_id"]]["sequence"]
            < periods[costs[prior["cost_id"]]["period_id"]]["sequence"]
        ):
            raise ContractError("Prior claim predates the cost period")
        for tax in TAXES:
            historical[prior["cost_id"], tax] += amount(prior[f"{tax}_amount"])
    prior_conflicts = set()
    for cid, cost in costs.items():
        for tax in TAXES:
            if historical[cid, tax] > amount(cost[f"{tax}_max"]):
                raise ContractError("Historical claims exceed source basis")
            if historical[cid, tax] + used[cid, tax] > amount(cost[f"{tax}_max"]):
                prior_conflicts.add(cid)
    common_status, common_reasons = _status(
        case["controls"], CASE_GATES, eids, sids, today
    )
    totals = {
        status: {tax: Decimal(0) for tax in TAXES}
        for status in ("INCLUDED", "EXCLUDED", "SUSPENDED")
    }
    by_ip = {ip: {tax: Decimal(0) for tax in TAXES} for ip in ips}
    lines = []
    for line in allocations.values():
        cost, ip = costs[line["cost_id"]], ips[line["ip_id"]]
        ip_gates = list(IP_GATES) + (["OUTSOURCING"] if ip["outsourced"] else [])
        if line["mode"] == "PREMIAL":
            ip_gates.append("PREMIAL")
        ip_status, reasons = _status(ip["controls"], ip_gates, eids, sids, today)
        line_status, line_reasons = _status(
            line["controls"], LINE_GATES, eids, sids, today
        )
        reasons = common_reasons + reasons + line_reasons
        statuses = [common_status, ip_status, line_status]
        if ip["type"] not in rules["ip_types"]:
            statuses.append("EXCLUDED")
            reasons.append("IP_TYPE_NOT_ELIGIBLE")
        if cost["cost_id"] in prior_conflicts:
            statuses.append("SUSPENDED")
            reasons.append("POSSIBLE_DOUBLE_CLAIM")
        if line["mode"] == "ORDINARY" and cost["period_id"] != case["claim_period_id"]:
            statuses.append("EXCLUDED")
            reasons.append("ORDINARY_PERIOD_MISMATCH")
        if line["mode"] == "PREMIAL":
            event = ip["premial_event"]
            if not event:
                statuses.append("SUSPENDED")
                reasons.append("PREMIAL_EVENT_MISSING")
            else:
                if event["period_id"] not in periods:
                    raise ContractError("Unknown premial event period")
                ep = periods[event["period_id"]]
                if not ep["start"] <= event["date"] <= ep["end"]:
                    raise ContractError("Premial event date outside its period")
                if not set(event["evidence_ids"]) <= eids or not event["evidence_ids"]:
                    statuses.append("SUSPENDED")
                    reasons.append("PREMIAL_EVENT_EVIDENCE_MISSING")
                valid_kinds = (
                    rules["premial_event_kinds"][ip["type"]]
                    if ip["type"] in rules["premial_event_kinds"]
                    else []
                )
                if event["kind"] not in valid_kinds:
                    statuses.append("SUSPENDED")
                    reasons.append("PREMIAL_EVENT_KIND_NOT_REVIEWED")
                distance = ep["sequence"] - periods[cost["period_id"]]["sequence"]
                if not 1 <= distance <= rules["premial_periods"]:
                    statuses.append("EXCLUDED")
                    reasons.append("OUTSIDE_PREMIAL_WINDOW")
                if current["sequence"] < ep["sequence"]:
                    statuses.append("EXCLUDED")
                    reasons.append("EVENT_AFTER_CLAIM")
                # Entry is tied to the fiscal period in progress at the anchor,
                # not universally to a calendar-year start or the event date.
                if ep["end"] < rules["premial_entry_anchor_date"]:
                    statuses.append("SUSPENDED")
                    reasons.append("EVENT_REQUIRES_TRANSITION_REVIEW")
        status = (
            "EXCLUDED"
            if "EXCLUDED" in statuses
            else "SUSPENDED" if "SUSPENDED" in statuses else "INCLUDED"
        )
        for tax in TAXES:
            value = amount(line[f"{tax}_amount"])
            totals[status][tax] += value
            if status == "INCLUDED":
                by_ip[ip["ip_id"]][tax] += value
        lines.append(
            {
                "allocation_id": line["allocation_id"],
                "cost_id": cost["cost_id"],
                "ip_id": ip["ip_id"],
                "mode": line["mode"],
                "status": status,
                "reasons": reasons,
                "income_amount": line["income_amount"],
                "irap_amount": line["irap_amount"],
            }
        )
    # Aggregate exact decimal bases first; round only the final tax-specific variation.
    variations = {
        tax: money(totals["INCLUDED"][tax] * amount(rules["enhancement_rate"]))
        for tax in TAXES
    }
    unallocated = {
        tax: money(
            sum(
                (amount(c[f"{tax}_max"]) - used[cid, tax] for cid, c in costs.items()),
                Decimal(0),
            )
        )
        for tax in TAXES
    }
    penalty = _penalty(case["penalty_protection"], eids, sids, today)
    result = {
        "schema_version": "1.0",
        "status": "DRAFT_FOR_PROFESSIONAL_REVIEW",
        "demo": case["demo"],
        "case_id": case["case_id"],
        "claim_period_id": case["claim_period_id"],
        "as_of": as_of,
        "input_hash": canonical_hash(case),
        "rules_hash": canonical_hash(rules),
        "ruleset_id": rules["ruleset_id"],
        "rule_ids": rules["rule_ids"],
        "lines": lines,
        "bases": {
            s: {t: money(v) for t, v in values.items()} for s, values in totals.items()
        },
        "included_by_ip": {
            i: {t: money(v) for t, v in values.items()} for i, values in by_ip.items()
        },
        "unallocated_bases": unallocated,
        "additional_deduction": variations,
        "penalty_protection": penalty,
        "tax_saving": None,
        "tax_saving_reason": "Requires separate reviewed rates, losses, tax capacity and incentive coordination.",
        "not_a_tax_return": True,
    }
    result["result_hash"] = canonical_hash(result)
    return result


def _penalty(
    record: dict[str, Any], eids: set[str], sids: set[str], today: date
) -> dict[str, Any]:
    if not record["requested"]:
        return {"status": "NOT_REQUESTED", "reasons": []}
    status, reasons = _status(
        record["controls"],
        ("DOC_A", "DOC_B", "SIGNATURE", "TIMESTAMP", "COMMUNICATION", "RETENTION"),
        eids,
        sids,
        today,
    )
    if status != "INCLUDED":
        return {"status": "NOT_READY", "reasons": reasons}
    return {
        "status": "REVIEWED_REQUIREMENTS_ONLY",
        "reasons": [
            "Idoneità e spettanza restano valutabili dagli organi di controllo."
        ],
    }


def approval_record(
    case: dict[str, Any],
    rules: dict[str, Any],
    result: dict[str, Any],
    reviewer: str,
    decision: str,
    as_of: str,
) -> dict[str, Any]:
    """Bind a proposed host-side decision to exact bytes; never authenticate a signer."""
    if not reviewer.strip() or decision not in ("APPROVE_DRAFT", "REQUEST_CHANGES"):
        raise ContractError("Reviewer and allowed decision required")
    if result["input_hash"] != canonical_hash(case) or result[
        "rules_hash"
    ] != canonical_hash(rules):
        raise ContractError("Stale result cannot be approved")
    payload = {k: v for k, v in result.items() if k != "result_hash"}
    if canonical_hash(payload) != result["result_hash"]:
        raise ContractError("Result integrity failed")
    if as_of < result["as_of"]:
        raise ContractError("Review predates calculation")
    return {
        "case_id": case["case_id"],
        "input_hash": result["input_hash"],
        "rules_hash": result["rules_hash"],
        "result_hash": result["result_hash"],
        "reviewer": reviewer,
        "decision": decision,
        "reviewed_on": as_of,
        "authentication": "REQUIRES_HOST_IDENTITY",
        "signature": None,
    }
