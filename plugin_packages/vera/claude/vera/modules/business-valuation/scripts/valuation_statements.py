"""Reconcile supplied statement balances and movements with exact Decimal lineage.

Arithmetic, explicit dates and reference identity are mechanically verifiable.
Classification, perimeter completeness and movement meaning remain reviewed choices.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

from valuation_case import _bind_normalizations, digest, indexed, require, reviewed
from valuation_engine import Ledger, ValuationError

__all__ = ["build_statements", "statement_dependencies"]


def _closing_refs(statement: dict) -> list[str]:
    return [
        ref for key in ("assets", "liabilities", "equity") for ref in statement[key]
    ]


def _reconcile(statement: dict, ledger: Ledger, registry: dict, prior: dict) -> dict:
    """Compare independently supplied stocks and movements; never invent a plug."""
    start = date.fromisoformat(statement["period_start"])
    end = date.fromisoformat(statement["period_end"])
    require(start <= end, "Statement period is reversed")
    totals = {
        key: ledger.add(
            key, "sum", [ledger.input(ref, ledger.currency) for ref in statement[key]]
        )
        for key in ("assets", "liabilities", "equity")
    }
    funding = ledger.add(
        "liabilities-equity", "sum", [totals["liabilities"], totals["equity"]]
    )
    difference = ledger.add(
        "balance-difference", "subtract", [totals["assets"], funding]
    )
    rows, issues = [], []
    checks = [
        {
            "id": "balance",
            "label": "Attivo e passività più patrimonio netto",
            "expected_id": totals["assets"],
            "actual_id": funding,
            "difference_id": difference,
        }
    ]
    if ledger.value(difference) != 0:
        issues.append("Assets do not equal liabilities plus equity")
    for row in statement["rollforwards"]:
        prefix = row["id"]
        opening = ledger.input(row["opening_input"], ledger.currency)
        movements = ledger.add(
            f"{prefix}/movements",
            "sum",
            [ledger.input(ref, ledger.currency) for ref in row["movement_inputs"]],
        )
        expected = ledger.add(f"{prefix}/expected-close", "sum", [opening, movements])
        closing = ledger.input(row["closing_input"], ledger.currency)
        delta = ledger.add(f"{prefix}/difference", "subtract", [closing, expected])
        checks.append(
            {
                "id": prefix,
                "label": row["description"],
                "expected_id": expected,
                "actual_id": closing,
                "difference_id": delta,
            }
        )
        result = {
            **deepcopy(row),
            "movements_id": movements,
            "expected_id": expected,
            "difference_id": delta,
            "continuity": "independently_sourced_opening",
        }
        if ledger.value(delta) != 0:
            issues.append(
                f"Roll-forward {prefix}: opening plus movements differs from closing"
            )
        previous_id = row["prior_statement_id"]
        if previous_id is not None:
            previous = registry[previous_id]
            require(
                previous_id in prior, "Prior statement must precede the current period"
            )
            require(
                start > date.min
                and date.fromisoformat(previous["period_end"])
                == start - timedelta(days=1),
                "Prior statement must close immediately before this period",
            )
            require(
                previous["perimeter_id"] == statement["perimeter_id"]
                and previous["basis"] == statement["basis"],
                "Continuity requires the same explicit perimeter and accounting basis",
            )
            require(
                prior[previous_id]["status"] != "blocked",
                "Prior statement is unreconciled",
            )
            previous_close = ledger.input(row["prior_closing_input"], ledger.currency)
            continuity = ledger.add(
                f"{prefix}/continuity-difference", "subtract", [opening, previous_close]
            )
            checks.append(
                {
                    "id": f"{prefix}/continuity",
                    "label": f"Continuità: {row['description']}",
                    "expected_id": previous_close,
                    "actual_id": opening,
                    "difference_id": continuity,
                }
            )
            result.update(
                {
                    "continuity": "prior_statement_compared",
                    "continuity_difference_id": continuity,
                }
            )
            if ledger.value(continuity) != 0:
                issues.append(
                    f"Roll-forward {prefix}: opening differs from prior closing"
                )
        rows.append(result)
    return {
        "total_ids": totals,
        "balance_difference_id": difference,
        "rollforwards": rows,
        "checks": checks,
        "issues": issues,
    }


def build_statements(
    case: dict,
    inputs: dict,
    sources: dict,
    normalizations: dict,
    mandate_dependency: str,
) -> tuple[dict, list]:
    """Preserve failed checks and invalidate only explicitly dependent workpapers."""
    registry = indexed(case.get("statements", []))
    for statement in registry.values():
        closing = _closing_refs(statement)
        require(
            len(set(closing)) == len(closing),
            "A closing input cannot occupy multiple statement lines",
        )
        refs = set(closing) | set(statement["bound_input_ids"])
        rolls = indexed(statement["rollforwards"])
        require(
            len({row["closing_input"] for row in rolls.values()}) == len(rolls),
            "Duplicate closing balance in roll-forwards",
        )
        require(
            (not rolls and statement["coverage"] == "balance_only")
            or (
                statement["coverage"] == "balance_and_movements"
                and {row["closing_input"] for row in rolls.values()} == set(closing)
            ),
            "Movement coverage must include every declared closing line",
        )
        for row in rolls.values():
            require(
                row["opening_input"] != row["closing_input"]
                and not {row["opening_input"], row["closing_input"]}
                & set(row["movement_inputs"]),
                "Opening, closing and movements must be independent inputs",
            )
            refs.update(
                [row["opening_input"], row["closing_input"], *row["movement_inputs"]]
            )
            previous_id = row["prior_statement_id"]
            require(
                (previous_id is None) == (row["prior_closing_input"] is None),
                "Prior statement and closing input must be supplied together",
            )
            if previous_id is not None:
                require(
                    previous_id in registry and previous_id != statement["id"],
                    "Unresolved prior statement",
                )
                require(
                    row["prior_closing_input"] in _closing_refs(registry[previous_id]),
                    "Prior closing input must belong to that statement",
                )
                require(
                    row["prior_closing_input"] != row["opening_input"],
                    "Continuity requires an independently supplied opening balance",
                )
                refs.add(row["prior_closing_input"])
        require(refs <= inputs.keys(), "Unresolved statement input")
        require(
            set(statement["source_ids"]) <= sources.keys(),
            "Unresolved statement evidence",
        )
    results, calculations = {}, []
    for statement in sorted(
        registry.values(), key=lambda row: (row["period_end"], row["id"])
    ):
        ledger = Ledger(f"statement/{statement['id']}", inputs, case["currency"])
        result = {**deepcopy(statement), "issues": [], "status": "blocked"}
        dependent_normalizations = []
        try:
            require(
                statement["period_end"] <= case["mandate"]["information_cutoff"],
                "Statement period exceeds the information cutoff",
            )
            result.update(_reconcile(statement, ledger, registry, results))
            dependent_normalizations = _bind_normalizations(
                {"calculations": list(ledger.rows.values())}, normalizations
            )
        except ValuationError as exc:
            result["issues"].append(str(exc))
        prior = [
            results[ref]
            for ref in sorted(
                {
                    row["prior_statement_id"]
                    for row in statement["rollforwards"]
                    if row["prior_statement_id"] is not None
                }
            )
            if ref in results
        ]
        used = set(statement["bound_input_ids"]) | set(_closing_refs(statement))
        for row in statement["rollforwards"]:
            used.update(
                [row["opening_input"], row["closing_input"], *row["movement_inputs"]]
            )
            if row["prior_closing_input"] is not None:
                used.add(row["prior_closing_input"])
        used.update(ref for row in ledger.rows.values() for ref in row["input_ids"])
        used.update(ref for previous in prior for ref in previous["input_ids"])
        source_ids = (
            set(statement["source_ids"])
            | {ref for key in used for ref in inputs[key]["source_ids"]}
            | {ref for group in dependent_normalizations for ref in group["source_ids"]}
            | {ref for previous in prior for ref in previous["source_ids"]}
        )
        dependency = digest(
            {
                "case_id": case["case_id"],
                "mandate_details_sha256": mandate_dependency,
                "statement": {
                    key: value for key, value in statement.items() if key != "review"
                },
                "inputs": [inputs[key] for key in sorted(used)],
                "sources": [sources[key] for key in sorted(source_ids)],
                "normalizations": dependent_normalizations,
                "prior_statements": [
                    {
                        key: previous.get(key)
                        for key in ("id", "dependency_sha256", "status", "review")
                    }
                    for previous in prior
                ],
            }
        )
        complete = (
            all(
                inputs[key]["value"] is not None
                and inputs[key]["status"] == "confirmed"
                for key in used
            )
            and all(sources[key]["status"] == "reviewed" for key in source_ids)
            and all(
                row["status"] == "accepted_workpaper"
                for row in [*dependent_normalizations, *prior]
            )
        )
        if not result["issues"]:
            result["status"] = (
                "accepted_workpaper"
                if complete and reviewed(statement.get("review"), dependency)
                else "ready_for_professional_review" if complete else "partial"
            )
        result.update(
            {
                "dependency_sha256": dependency,
                "stale_review": bool(statement.get("review"))
                and not reviewed(statement["review"], dependency),
                "input_ids": sorted(used),
                "source_ids": sorted(source_ids),
                "bound_input_ids": sorted(
                    set(statement["bound_input_ids"]) | set(_closing_refs(statement))
                ),
                "scope": "explicit_statement_arithmetic_not_classification_or_completeness_opinion",
            }
        )
        for row in ledger.rows.values():
            row.update({"source_ids": sorted(source_ids), "formula_version": "1"})
            calculations.append(row)
        results[statement["id"]] = result
    return results, calculations


def statement_dependencies(used: list[str], statements: dict) -> list[dict]:
    """Select only declared amount bindings; an invalid statement blocks its branch."""
    dependent = [
        row for row in statements.values() if set(used) & set(row["bound_input_ids"])
    ]
    for row in dependent:
        require(
            row["status"] != "blocked",
            f"Statement {row['id']}: {'; '.join(row['issues'])}",
        )
    return dependent
