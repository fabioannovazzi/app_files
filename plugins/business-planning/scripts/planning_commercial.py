"""Optional price/volume economics, usable before a complete cash-flow forecast."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from planning_workflow import number, require, text_number

__all__ = ["calculate_commercial"]


def calculate_commercial(
    case: dict[str, Any], calculations: dict[str, Any], issues: list[str]
) -> None:
    """Calculate explicitly scoped unit economics and reconcile whole-business rows."""
    refs = {r["id"]: r for r in [*case["evidence"], *case["assumptions"]]}
    seen = set()
    for row in case.get("commercial", []):
        require(
            set(row)
            == {
                "scenario",
                "period",
                "units",
                "net_price",
                "variable_cost_per_unit",
                "fixed_cost",
                "basis_ids",
                "cost_scope",
            },
            "Unexpected commercial driver fields",
        )
        sid, period = row["scenario"], row["period"]
        require(
            isinstance(sid, str) and bool(sid) and "/" not in sid,
            "Invalid commercial scenario",
        )
        require(period in case["periods"], "Unknown commercial period")
        require((sid, period) not in seen, "Duplicate commercial period")
        seen.add((sid, period))
        require(
            bool(row["cost_scope"]),
            "Explain what the commercial costs include and exclude",
        )
        basis = row["basis_ids"]
        require(
            bool(basis) and set(basis) <= set(refs), "Commercial input lineage required"
        )
        for rid in basis:
            if refs[rid]["kind"] in {"assumption", "hypothesis"}:
                require(
                    period in refs[rid]["effective_periods"],
                    "Commercial assumption is ineffective",
                )
        keys = ("units", "net_price", "variable_cost_per_unit", "fixed_cost")
        if any(row[k] is None for k in keys):
            issues.append(
                f"Commercial economics {sid}/{period} incomplete; missing drivers are not zero"
            )
            continue
        units, price, variable, fixed = (number(row[k]) for k in keys)
        require(
            all(v >= 0 for v in (units, price, variable, fixed)),
            "Commercial drivers must be nonnegative",
        )
        contribution = price - variable
        revenue = units * price
        operating_result = units * contribution - fixed
        metrics = {
            "units": (units, "units", "Accepted volume assumption"),
            "net_price": (
                price,
                case["reporting_currency"] + "/unit",
                "Accepted net realized price",
            ),
            "revenue": (revenue, case["reporting_currency"], "units * net_price"),
            "contribution_per_unit": (
                contribution,
                case["reporting_currency"] + "/unit",
                "net_price - variable_cost_per_unit",
            ),
            "operating_result": (
                operating_result,
                case["reporting_currency"],
                "units * contribution_per_unit - fixed_cost; within disclosed cost scope",
            ),
            "break_even_units": (
                fixed / contribution if contribution > 0 else None,
                "units",
                "fixed_cost / contribution_per_unit; no finite break-even at nonpositive contribution",
            ),
        }
        sources = sorted({s for rid in basis for s in refs[rid]["source_ids"]})
        for metric, (value, unit, formula) in metrics.items():
            cid = f"{sid}/{period}/commercial_{metric}"
            calculations[cid] = dict(
                id=cid,
                scenario=sid,
                period=period,
                metric=f"commercial_{metric}",
                value=text_number(value) if isinstance(value, Decimal) else None,
                unit=unit,
                formula=formula + "; " + row["cost_scope"],
                basis_ids=basis,
                source_ids=sources,
                unavailable_reason=(
                    "Contribution is not positive" if value is None else None
                ),
            )
        for metric, value in (("revenue", revenue), ("ebitda", operating_result)):
            linked = calculations.get(f"{sid}/{period}/{metric}")
            if (
                linked
                and linked["value"] is not None
                and number(linked["value"]) != value
            ):
                issues.append(
                    f"Commercial {metric} disagrees with authoritative financial model: {sid}/{period}"
                )
    if case.get("commercial") and case["financial"] is None:
        issues.append(
            "Commercial economics describe the disclosed cost scope; cash survival and a capital recommendation remain unestablished"
        )
