"""Measure recorded first-pass proposals without inferring tax correctness.

Exact unit keys, append-only snapshots and integer denominators make the counts
reproducible. The model proposes classes; the professional declares corrections.
These local records do not authenticate either actor or establish accuracy.
"""

from __future__ import annotations

import argparse
import calendar
import json
import logging
import re
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import lipe_catalog as catalog
from lipe_core import ContractError, check_references, digest, read_json, validate

__all__ = ["capture_first_pass", "record_review", "report", "main"]


def _object(properties: dict) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def _proposal_schema() -> dict:
    entry = read_json(catalog.SCHEMA)["properties"]
    return _object(
        {
            "side": entry["side"],
            "code": entry["code"],
            "tax_class": entry["tax_class"],
            "confidence": entry["confidence"],
            "evidence": entry["evidence"],
        }
    )


def _scope(case: dict) -> dict:
    # A new run/case filename must not turn a corrected code into a first pass.
    return {
        key: case[key]
        for key in (
            "client_id",
            "engagement_id",
            "data_origin",
            "tax_year",
            "quarter",
            "software",
        )
    }


def _inventory(case: dict) -> dict[tuple[str, str], list[dict]]:
    inventory: dict[tuple[str, str], list[dict]] = {}
    for register in case["registers"]:
        for row in register["rows"]:
            inventory.setdefault((register["side"], row["code"]), []).append(
                row["evidence"]
            )
    for liquidation in case["liquidations"]:
        for section in liquidation["sections"]:
            for row in section["rows"]:
                inventory.setdefault((section["side"], row["code"]), []).append(
                    row["evidence"]
                )
    return inventory


def _catalog_candidate(state: dict, case: dict, side: str, code: str) -> dict:
    start_month, end_month = (case["quarter"] - 1) * 3 + 1, case["quarter"] * 3
    start = date(case["tax_year"], start_month, 1)
    end = date(
        case["tax_year"], end_month, calendar.monthrange(case["tax_year"], end_month)[1]
    )
    dates = {start, end}
    for row in catalog._latest(state).values():
        entry = catalog._entry_at(state, row)
        if (entry["software"], entry["side"], entry["code"]) != (
            case["software"],
            side,
            code,
        ):
            continue
        if entry["scope"] == "CLIENT" and entry["client_id"] != case["client_id"]:
            continue
        since = date.fromisoformat(entry["valid_from"])
        if start < since < end:
            dates.add(since)
        if entry["valid_until"] is not None:
            until = date.fromisoformat(entry["valid_until"])
            if start <= until < end:
                dates.add(until + timedelta(days=1))
    checks = [
        {
            "on_date": when.isoformat(),
            **catalog._lookup(
                state,
                studio_id=state["metadata"]["studio_id"],
                client_id=case["client_id"],
                software=case["software"],
                side=side,
                code=code,
                on_date=when.isoformat(),
            ),
        }
        for when in sorted(dates)
    ]
    available = (
        all(item["status"] == "CANDIDATE_FOR_CASE_REVIEW" for item in checks)
        and len({digest(item["candidate"]) for item in checks}) == 1
    )
    return {
        "available": available,
        "tax_class": checks[0]["candidate"] if available else None,
        "checks": [
            {key: item[key] for key in ("on_date", "status", "scope", "binding")}
            for item in checks
        ],
    }


def _validate_class(side: str, value: dict) -> None:
    catalog.validate_tax_class(side, value)


def _quoted_code(code: str, evidence: list[dict]) -> None:
    if not any(
        re.search(r"(?<!\w)" + re.escape(code) + r"(?!\w)", ref["quote"])
        for ref in evidence
    ):
        raise ContractError("Measured code is absent from the quoted evidence")


def _unit_id(scope: dict, side: str, code: str) -> str:
    return digest({"scope": scope, "side": side, "code": code})


def capture_first_pass(
    path: Path,
    case: dict,
    source_root: Path,
    proposal_packet: dict,
    *,
    expected_head: str,
) -> dict:
    """Snapshot every newly seen code before review; repeated runs add no units."""
    validate(case)
    expected_periods = (
        list(range((case["quarter"] - 1) * 3 + 1, case["quarter"] * 3 + 1))
        if case["regime"] == "MONTHLY"
        else [case["quarter"]]
    )
    if [module["period"] for module in case["modules"]] != expected_periods:
        raise ContractError("Measurement period must match the case's complete quarter")
    catalog._validate(
        proposal_packet,
        _object(
            {
                "timing_declaration": {"const": "BEFORE_PROFESSIONAL_REVIEW"},
                "model_proposals": {"type": "array", "items": _proposal_schema()},
            }
        ),
    )
    inventory = _inventory(case)
    if not inventory:
        raise ContractError("No code population to measure")
    proposals = {}
    refs = [ref for values in inventory.values() for ref in values]
    for item in proposal_packet["model_proposals"]:
        key = (item["side"], item["code"])
        if key not in inventory or key in proposals:
            raise ContractError("Model proposals must name distinct observed codes")
        _validate_class(item["side"], item["tax_class"])
        _quoted_code(item["code"], item["evidence"])
        proposals[key] = item
        refs.extend(item["evidence"])
    check_references(case["sources"], refs, source_root)
    scope = _scope(case)
    with closing(catalog._connect(path, write=True)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        state = catalog._history(connection)
        catalog._verify_objects(path, state)
        if state["head_hash"] != expected_head:
            raise ContractError("Catalog changed; reload before measurement")
        context = case["catalog_context"]
        if context != {
            "catalog_id": state["metadata"]["catalog_id"],
            "studio_id": state["metadata"]["studio_id"],
        }:
            raise ContractError("Measurement case must identify the selected catalog")
        known = {
            unit["unit_id"]
            for row in state["events"]
            if row["event"]["kind"] == "FIRST_PASS"
            for unit in row["event"]["units"]
        }
        units = []
        for (side, code), evidence in sorted(inventory.items()):
            identity = _unit_id(scope, side, code)
            if identity in known:
                continue
            if any(
                mapping["side"] == side
                and mapping["code"] == code
                and mapping["review"]["status"] == "CONFIRMED"
                for mapping in case["mappings"]
            ):
                raise ContractError(
                    "Capture the first pass before confirming case mappings"
                )
            candidate = _catalog_candidate(state, case, side, code)
            model = proposals.get((side, code))
            if model is not None:
                proposed = model["tax_class"]
                recognized = (
                    proposed["treatment"] is not None
                    and Decimal(model["confidence"]["value"])
                    >= Decimal(state["metadata"]["minimum_confidence"])
                    and (
                        candidate["available"]
                        or all(
                            check["status"] == "UNKNOWN_CODE"
                            for check in candidate["checks"]
                        )
                    )
                )
                method = "MODEL"
            else:
                proposed = candidate["tax_class"]
                recognized = candidate["available"]
                method = "CATALOG" if recognized else "NONE"
            units.append(
                {
                    "unit_id": identity,
                    "side": side,
                    "code": code,
                    "inventory_evidence": evidence,
                    "catalog": candidate,
                    "model_proposal": model,
                    "proposal": proposed,
                    "method": method,
                    "recognized": recognized,
                }
            )
        if not units:
            return {
                "status": "ALREADY_RECORDED",
                "head_hash": state["head_hash"],
                "new_units": 0,
                "previously_recorded_units": len(inventory),
            }
        return catalog._append(
            connection,
            state,
            {
                "kind": "FIRST_PASS",
                "scope": scope,
                "case_id": case["case_id"],
                "case_hash": digest(case),
                "catalog_head_hash": state["head_hash"],
                "minimum_confidence": state["metadata"]["minimum_confidence"],
                "timing_declaration": proposal_packet["timing_declaration"],
                "timing_authenticated": False,
                "source_objects": catalog._capture_objects(
                    path, case["sources"], source_root
                ),
                "sources": case["sources"],
                "units": units,
                "previously_recorded_units": len(inventory) - len(units),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def record_review(
    path: Path,
    decision: dict,
    source_root: Path,
    *,
    expected_head: str,
    supersedes: str | None = None,
) -> dict:
    """Append an attributed correction tied to one preserved first-pass unit."""
    entry = read_json(catalog.SCHEMA)["properties"]
    catalog._validate(
        decision,
        _object(
            {
                "unit_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "outcome": {
                    "enum": ["CONFIRMED", "CORRECTED", "RESOLVED_NEW", "UNRESOLVED"]
                },
                "tax_class": {"anyOf": [entry["tax_class"], {"type": "null"}]},
                "sources": entry["sources"],
                "evidence": entry["evidence"],
                "review": catalog.REVIEW_SCHEMA,
            }
        ),
    )
    check_references(decision["sources"], decision["evidence"], source_root)
    with closing(catalog._connect(path, write=True)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        state = catalog._history(connection)
        catalog._verify_objects(path, state)
        if state["head_hash"] != expected_head:
            raise ContractError("Catalog changed; reload before recording review")
        targets = [
            (row, unit)
            for row in state["events"]
            if row["event"]["kind"] == "FIRST_PASS"
            for unit in row["event"]["units"]
            if unit["unit_id"] == decision["unit_id"]
        ]
        if len(targets) != 1:
            raise ContractError("Review must identify one recorded first-pass unit")
        first, unit = targets[0]
        _quoted_code(unit["code"], decision["evidence"])
        previous = [
            row
            for row in state["events"]
            if row["event"]["kind"] == "METRIC_REVIEW"
            and row["event"]["decision"]["unit_id"] == decision["unit_id"]
        ]
        if supersedes != (previous[-1]["event_hash"] if previous else None):
            raise ContractError("Review must supersede its exact latest revision")
        chosen = decision["tax_class"]
        if chosen is None:
            expected = "UNRESOLVED"
        else:
            _validate_class(unit["side"], chosen)
            if chosen["treatment"] is None:
                raise ContractError("A resolved review needs a known treatment")
            expected = (
                "RESOLVED_NEW"
                if unit["proposal"] is None
                else "CONFIRMED" if chosen == unit["proposal"] else "CORRECTED"
            )
        if decision["outcome"] != expected:
            raise ContractError("Review outcome disagrees with the preserved proposal")
        return catalog._append(
            connection,
            state,
            {
                "kind": "METRIC_REVIEW",
                "first_pass_event_hash": first["event_hash"],
                "decision": decision,
                "supersedes": supersedes,
                "source_objects": catalog._capture_objects(
                    path, decision["sources"], source_root
                ),
                "identity_authenticated": False,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def _rate(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "percent": (
            str(
                (Decimal(numerator) * 100 / denominator).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )
            if denominator
            else None
        ),
    }


def report(path: Path) -> dict:
    """Count first snapshots and first resolved reviews; never merge real/demo data."""
    state = catalog.history(path)
    reviews: dict[str, list[dict]] = {}
    for row in state["events"]:
        if row["event"]["kind"] == "METRIC_REVIEW":
            decision = row["event"]["decision"]
            reviews.setdefault(decision["unit_id"], []).append(decision)
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in state["events"]:
        if row["event"]["kind"] != "FIRST_PASS":
            continue
        scope = row["event"]["scope"]
        key = (
            scope["data_origin"],
            scope["software"]["name"],
            scope["software"]["version"],
        )
        for unit in row["event"]["units"]:
            resolutions = [
                item
                for item in reviews.get(unit["unit_id"], [])
                if item["outcome"] != "UNRESOLVED"
            ]
            groups.setdefault(key, []).append(
                {
                    **unit,
                    "first_resolution": resolutions[0] if resolutions else None,
                    "latest_review": reviews.get(unit["unit_id"], [None])[-1],
                }
            )
    cohorts = []
    for (origin, name, version), units in sorted(groups.items()):
        reviewed_proposals = [
            item
            for item in units
            if item["proposal"] is not None and item["first_resolution"] is not None
        ]
        cohorts.append(
            {
                "data_origin": origin,
                "software": {"name": name, "version": version},
                "units": len(units),
                "recognition": _rate(
                    sum(item["recognized"] for item in units), len(units)
                ),
                "catalog_availability": _rate(
                    sum(item["catalog"]["available"] for item in units), len(units)
                ),
                "first_resolution_coverage": _rate(
                    sum(item["first_resolution"] is not None for item in units),
                    len(units),
                ),
                "professional_class_change": _rate(
                    sum(
                        item["first_resolution"]["outcome"] == "CORRECTED"
                        for item in reviewed_proposals
                    ),
                    len(reviewed_proposals),
                ),
                "currently_unresolved": sum(
                    item["latest_review"] is None
                    or item["latest_review"]["outcome"] == "UNRESOLVED"
                    for item in units
                ),
                "resolved_without_initial_proposal": sum(
                    item["first_resolution"] is not None and item["proposal"] is None
                    for item in units
                ),
            }
        )
    return {
        "schema_version": "lipe.metrics.v1",
        "catalog_id": state["metadata"]["catalog_id"],
        "head_hash": state["head_hash"],
        "cohorts": cohorts,
        "unit": "One client/engagement/year/quarter/software/version/register-side/code; repeat reads do not add observations.",
        "recognition_definition": "A catalog candidate consistent throughout the quarter, or a recorded model proposal with known treatment meeting the declared cutoff and no unresolved catalog block, before professional review.",
        "correction_definition": "Exact full tax-class change in the first resolved attributed professional review among units that had a first-pass proposal. Text-only class edits also count; this is not independently measured tax error.",
        "coverage_limit": "Only recorded inventories are measured; omitted cases or late first-pass recording cannot be detected. No generalization to unseen software or cases.",
        "identity_and_timing_authenticated": False,
        "remote_sharing": False,
    }


def main(argv: list[str] | None = None) -> int:
    """Persist private local measurement receipts; do not transmit telemetry."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("first-pass")
    capture.add_argument("--case", type=Path, required=True)
    capture.add_argument("--proposals", type=Path, required=True)
    capture.add_argument("--source-root", type=Path, required=True)
    capture.add_argument("--expected-head", required=True)
    capture.add_argument("--client-engagement", type=Path)
    review = sub.add_parser("review")
    review.add_argument("--decision", type=Path, required=True)
    review.add_argument("--source-root", type=Path, required=True)
    review.add_argument("--expected-head", required=True)
    review.add_argument("--supersedes")
    summary = sub.add_parser("report")
    for command in (capture, review, summary):
        command.add_argument("--catalog", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    case = read_json(args.case) if args.command == "first-pass" else None
    if case is not None and case["data_origin"] != "SYNTHETIC":
        from lipe import _archive

        args.source_root, archive_output = _archive(
            case, args.case, args.client_engagement
        )
        if not args.output.resolve().is_relative_to(archive_output.resolve()):
            raise ContractError(
                "Real measurement receipt belongs in the selected Archive run"
            )
    with args.output.open("x", encoding="utf-8") as receipt:
        args.output.chmod(0o600)
        if args.command == "first-pass":
            result = capture_first_pass(
                args.catalog,
                case,
                args.source_root,
                read_json(args.proposals),
                expected_head=args.expected_head,
            )
        elif args.command == "review":
            result = record_review(
                args.catalog,
                read_json(args.decision),
                args.source_root,
                expected_head=args.expected_head,
                supersedes=args.supersedes,
            )
        else:
            result = report(args.catalog)
        receipt.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    logging.info("LIPE measurements %s: %s", args.command, args.output)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
