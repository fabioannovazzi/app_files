"""Reconcile explicit signed adjustments without choosing accounting treatments.

Fixed sums and exact dependency hashes are mechanically reproducible. Whether an
adjustment is appropriate, reversible or tax-relevant remains a reviewed choice.
"""

from __future__ import annotations

from copy import deepcopy

from valuation_case import digest, fields, indexed, require, reviewed, text
from valuation_engine import Ledger, ValuationError

__all__ = ["build_normalizations", "normalization_dependencies"]


def build_normalizations(
    case: dict, inputs: dict, sources: dict, mandate_dependency: str
) -> tuple[dict, list]:
    """Keep reported, signed changes and asserted adjusted values independently."""
    groups = indexed(case.get("normalizations", []))
    targets: set[str] = set()
    periods: set[tuple[int, str]] = set()
    for group in groups.values():
        fields(
            group,
            {"id", "year", "line", "reported_input", "adjusted_input", "adjustments"},
        )
        require(
            type(group["year"]) is int and 1 <= group["year"] <= 9998,
            "Invalid normalization year",
        )
        text(group["line"], "normalized statement line")
        target = text(group["adjusted_input"], "adjusted input ID")
        require(
            target in inputs and target not in targets,
            "Duplicate or unknown adjusted input",
        )
        require(
            (group["year"], group["line"]) not in periods,
            "Duplicate normalized year and line",
        )
        require(
            "plan_calculation_ids" not in inputs[target],
            "Revise and replay the plan instead of normalizing a plan output",
        )
        targets.add(target)
        periods.add((group["year"], group["line"]))
    results, calculations = {}, []
    for group in groups.values():
        target = group["adjusted_input"]
        reported = text(group["reported_input"], "reported input ID")
        require(
            reported in inputs and reported not in targets,
            "Reported inputs must be independent of adjusted outputs",
        )
        entries = indexed(group["adjustments"])
        require(bool(entries), "Declare at least one adjustment")
        used = {reported, target}
        source_ids: set[str] = set()
        rows, amount_ids = [], []
        for entry in entries.values():
            fields(
                entry,
                {
                    "id",
                    "amount_input",
                    "reason",
                    "accounting_check",
                    "economic_rationale",
                    "tax_treatment",
                    "reversibility",
                    "source_ids",
                    "locator",
                },
                {"review"},
            )
            amount = text(entry["amount_input"], "signed adjustment input ID")
            require(
                amount in inputs and amount not in targets and amount != reported,
                "Adjustment amount must be an independent input",
            )
            require(
                amount not in amount_ids,
                "An adjustment amount cannot be counted twice on one line",
            )
            amount_ids.append(amount)
            used.add(amount)
            for key in (
                "reason",
                "accounting_check",
                "economic_rationale",
                "tax_treatment",
                "reversibility",
                "locator",
            ):
                text(entry[key], key)
            require(
                isinstance(entry["source_ids"], list)
                and bool(entry["source_ids"])
                and all(isinstance(ref, str) for ref in entry["source_ids"])
                and set(entry["source_ids"]) <= sources.keys(),
                "Unresolved adjustment evidence",
            )
            refs = sorted(
                set(entry["source_ids"])
                | set(inputs[amount]["source_ids"])
                | set(inputs[reported]["source_ids"])
                | set(inputs[target]["source_ids"])
            )
            source_ids.update(refs)
            dependency = digest(
                {
                    "case_id": case["case_id"],
                    "entity_name": case["entity_name"],
                    "mandate": case["mandate"],
                    "mandate_details_sha256": mandate_dependency,
                    "currency": case["currency"],
                    "audience": case["audience"],
                    "synthetic": case["synthetic"],
                    "group": {
                        key: value
                        for key, value in group.items()
                        if key != "adjustments"
                    },
                    "adjustment": {
                        key: value for key, value in entry.items() if key != "review"
                    },
                    "inputs": [inputs[ref] for ref in (reported, amount, target)],
                    "sources": [sources[ref] for ref in refs],
                }
            )
            complete = all(
                inputs[ref]["status"] == "confirmed"
                for ref in (reported, amount, target)
            ) and all(sources[ref]["status"] == "reviewed" for ref in refs)
            rows.append(
                {
                    **deepcopy(entry),
                    "dependency_sha256": dependency,
                    "status": (
                        "accepted_workpaper"
                        if complete and reviewed(entry.get("review"), dependency)
                        else "ready_for_professional_review" if complete else "partial"
                    ),
                    "stale_review": bool(entry.get("review"))
                    and not reviewed(entry["review"], dependency),
                }
            )
        result = {
            "id": group["id"],
            "year": group["year"],
            "line": group["line"],
            "reported_input": reported,
            "adjusted_input": target,
            "input_ids": sorted(used),
            "source_ids": sorted(source_ids),
            "adjustments": rows,
            "status": (
                "accepted_workpaper"
                if all(row["status"] == "accepted_workpaper" for row in rows)
                else "partial"
            ),
        }
        ledger = Ledger(f"normalization/{group['id']}", inputs, case["currency"])
        try:
            original = ledger.input(reported, case["currency"])
            amounts = [ledger.input(ref, case["currency"]) for ref in amount_ids]
            total = ledger.add("adjustments", "sum", amounts)
            expected = ledger.add("adjusted", "sum", [original, total])
            asserted = ledger.input(target, case["currency"])
            difference = ledger.add("difference", "subtract", [asserted, expected])
            result.update(
                {
                    "adjustments_id": total,
                    "value_id": expected,
                    "difference_id": difference,
                }
            )
            require(
                ledger.value(difference) == 0,
                "Adjusted input does not reconcile to reported amount plus signed adjustments",
            )
        except ValuationError as exc:
            result.update({"status": "blocked", "reason": str(exc)})
        for row in ledger.rows.values():
            row["source_ids"] = sorted(
                {
                    source
                    for ref in row["input_ids"]
                    for source in inputs[ref]["source_ids"]
                }
                | source_ids
            )
            row["formula_version"] = "1"
            calculations.append(row)
        results[target] = result
    return results, calculations


def normalization_dependencies(used: list[str], groups: dict) -> list[dict]:
    """Return only affected journal groups and reject unreconciled amounts."""
    dependent = [groups[ref] for ref in sorted(set(used) & groups.keys())]
    for group in dependent:
        require(
            group["status"] != "blocked",
            f"Normalization {group['id']}: {group.get('reason', 'blocked')}",
        )
    return dependent
