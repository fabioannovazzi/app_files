"""Exact costing of reviewed, non-overlapping operating cost objects.

Fixed code is justified by cent-exact allocation and mechanically verifiable
source tie-outs. Cost behavior, traceability, drivers and avoidability are
authored judgments, never inferred from account names or business sectors.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

__all__ = [
    "METHODS",
    "CostingContractError",
    "allocate_cents",
    "calculate_costing",
    "calculate_decisions",
]

METHODS = ("direct_costing", "direct_costing_evoluto", "full_costing", "abc")
MAX_CENTS = 2**53 - 1
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_QUANTITY = re.compile(r"^\d+(?:\.\d{1,6})?$")


class CostingContractError(ValueError):
    """A mechanical case contract or selected method cannot be satisfied."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise CostingContractError(code, message)


def text(value: Any, label: str) -> str:
    require(
        isinstance(value, str) and bool(value.strip()) and len(value) <= 2400,
        "TEXT",
        f"{label} requires non-empty bounded text",
    )
    return str(value)


def cents(value: Any) -> int:
    require(
        type(value) is int and abs(value) <= MAX_CENTS,
        "CENTS",
        "Money must be safe integer cents, not floats or booleans",
    )
    return int(value)


def total(values: Sequence[int]) -> int:
    return cents(sum(cents(value) for value in values))


def quantity(value: Any) -> int:
    require(
        isinstance(value, str)
        and len(value) <= 30
        and _QUANTITY.fullmatch(value) is not None,
        "QUANTITY",
        "Drivers require nonnegative decimal strings with at most six places",
    )
    whole, _, fraction = value.partition(".")
    return int(whole) * 1_000_000 + int(fraction.ljust(6, "0"))


def records(value: Any, label: str) -> list[dict[str, Any]]:
    require(isinstance(value, list), "ROWS", f"{label} must be a list")
    require(len(value) <= 10000, "ROWS", f"{label} exceeds 10000 rows")
    seen: set[str] = set()
    for row in value:
        require(isinstance(row, dict), "ROWS", f"Invalid {label} row")
        identifier = row.get("id")
        require(
            isinstance(identifier, str) and _ID.fullmatch(identifier) is not None,
            "ID",
            f"Invalid {label} ID",
        )
        require(identifier not in seen, "DUPLICATE_ID", f"Duplicate {label} ID")
        seen.add(identifier)
    return list(value)


def allocate_cents(
    amount: int, weights: Mapping[str, str], capacity: str | None = None
) -> dict[str, Any]:
    """Allocate exact cents by largest remainder, retaining unused capacity."""
    cents(amount)
    require(isinstance(weights, dict) and bool(weights), "DRIVER", "Missing weights")
    require("~UNUSED" not in weights, "ID", "Reserved unused-capacity ID")
    units = {key: quantity(value) for key, value in sorted(weights.items())}
    used = sum(units.values())
    denominator = used if capacity is None else quantity(capacity)
    require(used <= denominator, "CAPACITY_EXCEEDED", "Usage exceeds reviewed capacity")
    if amount == 0:
        return {"byObject": dict.fromkeys(units, 0), "unusedCents": 0}
    require(denominator > 0, "ZERO_DRIVER", "Non-zero costs require a positive driver")
    if denominator > used:
        units["~UNUSED"] = denominator - used
    absolute = abs(amount)
    shares = {key: absolute * value // denominator for key, value in units.items()}
    remainder = absolute - sum(shares.values())
    priority = sorted(
        units, key=lambda key: (-(absolute * units[key] % denominator), key)
    )
    for key in priority[:remainder]:
        shares[key] += 1
    sign = -1 if amount < 0 else 1
    unused = sign * shares.pop("~UNUSED", 0)
    result = {key: sign * value for key, value in shares.items()}
    require(
        total([*result.values(), unused]) == amount, "ALLOCATION", "Allocation mismatch"
    )
    return {"byObject": result, "unusedCents": unused}


def _driver(value: Any, object_ids: set[str]) -> None:
    if value is None:
        return
    require(isinstance(value, dict), "DRIVER", "Driver must be an object")
    for key in ("name", "unit", "rationale"):
        text(value.get(key), f"driver.{key}")
    weights = value.get("weights")
    require(
        isinstance(weights, dict) and set(weights) == object_ids,
        "DRIVER_OBJECTS",
        "A driver must explicitly cover every cost object",
    )
    for weight in weights.values():
        quantity(weight)
    policy = value.get("capacityPolicy")
    require(policy in {"actual", "practical"}, "CAPACITY", "Invalid capacity policy")
    if policy == "practical":
        require(
            quantity(value.get("capacity")) > 0, "CAPACITY", "Capacity must be positive"
        )
    else:
        require(
            value.get("capacity") is None, "CAPACITY", "Actual capacity must be null"
        )


def _references(value: Any, evidence: set[str]) -> None:
    require(
        isinstance(value, list)
        and bool(value)
        and all(isinstance(ref, str) and ref in evidence for ref in value),
        "EVIDENCE",
        "Each amount requires known evidence references",
    )


def _validate(case: Mapping[str, Any], methods: Sequence[str]) -> None:
    require(isinstance(case, dict), "CASE", "Case must be an object")
    require(
        isinstance(methods, (list, tuple))
        and bool(methods)
        and all(isinstance(m, str) and m in METHODS for m in methods)
        and len(set(methods)) == len(methods),
        "METHODS",
        "Review the requested methods",
    )
    meta = case.get("meta")
    require(isinstance(meta, dict), "META", "Missing case metadata")
    for key in ("caseId", "clientId", "engagementId"):
        require(
            _ID.fullmatch(text(meta.get(key), key)) is not None, "ID", f"Invalid {key}"
        )
    require(
        meta.get("schemaVersion") == "1.0.0",
        "VERSION",
        "Unsupported reference contract",
    )
    require(
        meta.get("currency") == "EUR",
        "CURRENCY",
        "Normalize currency upstream; this costing path supports EUR",
    )
    require(
        meta.get("basis") == "accrual_consumed"
        and meta.get("perimeter") == "operating",
        "PERIMETER",
        "Review consumed operating costs for the period first",
    )
    require(
        type(meta.get("demonstration")) is bool,
        "DEMO",
        "Explicit demonstration flag required",
    )
    try:
        start = date.fromisoformat(meta["periodStart"])
        end = date.fromisoformat(meta["periodEnd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CostingContractError("PERIOD", "Invalid ISO costing period") from exc
    require(start <= end, "PERIOD", "Period start is after its end")
    objects = records(case.get("objects"), "objects")
    costs = records(case.get("costs"), "costs")
    pools = records(case.get("pools"), "pools")
    evidence = records(case.get("evidence"), "evidence")
    require(
        0 < len(objects) <= 200, "OBJECTS", "Use one view of at most 200 cost objects"
    )
    object_ids = {row["id"] for row in objects}
    pool_ids = {row["id"] for row in pools}
    evidence_ids = {row["id"] for row in evidence}
    for row in evidence:
        text(row.get("locator"), "evidence locator")
        require(
            row.get("kind")
            in {"document", "client_statement", "estimate", "synthetic"},
            "EVIDENCE",
            "Invalid evidence kind",
        )
        require(
            row.get("status")
            in {"documented", "declared", "approved_estimate", "synthetic"},
            "EVIDENCE",
            "Invalid evidence status",
        )
        require(
            meta["demonstration"]
            or (row["kind"] != "synthetic" and row["status"] != "synthetic"),
            "SYNTHETIC",
            "Synthetic evidence cannot qualify a live case",
        )
    dimensions: set[str] = set()
    for row in objects:
        text(row.get("label"), "object label")
        require(
            row.get("dimension")
            in {"product", "client", "channel", "job", "service", "segment"},
            "DIMENSION",
            "Unsupported cost-object dimension",
        )
        dimensions.add(row["dimension"])
        quantity(row.get("units"))
        text(row.get("unit"), "object unit")
        cents(row.get("revenueCents"))
        _references(row.get("evidenceIds"), evidence_ids)
    require(
        len(dimensions) == 1,
        "DIMENSION",
        "Do not add overlapping product, client and channel views",
    )
    for row in costs:
        text(row.get("label"), "cost label")
        cents(row.get("amountCents"))
        _references(row.get("evidenceIds"), evidence_ids)
        require(
            row.get("behavior") in {"fixed", "variable"},
            "BEHAVIOR",
            "Split mixed costs into reviewed components",
        )
        trace = row.get("traceability")
        require(
            trace in {"direct", "indirect", "entity"},
            "TRACEABILITY",
            "Review cost traceability",
        )
        if trace == "direct":
            require(
                row.get("objectId") in object_ids and row.get("poolId") is None,
                "COST_OBJECT",
                "Direct costs require one known object",
            )
        elif trace == "indirect":
            require(
                row.get("poolId") in pool_ids and row.get("objectId") is None,
                "COST_POOL",
                "Indirect costs require one known pool",
            )
        else:
            require(
                row["behavior"] == "fixed"
                and row.get("objectId") is None
                and row.get("poolId") is None,
                "ENTITY_COST",
                "Only reviewed fixed costs may remain at entity level",
            )
    for pool in pools:
        text(pool.get("label"), "pool label")
        _driver(pool.get("driver"), object_ids)
    _driver(case.get("traditionalDriver"), object_ids)
    _driver(case.get("commonDriver"), object_ids)
    require(
        case.get("commonPolicy") in {"allocate", "retain_entity"},
        "COMMON_POLICY",
        "Review common cost policy",
    )
    common_driver = case.get("commonDriver")
    if case["commonPolicy"] == "retain_entity":
        require(
            common_driver is None,
            "COMMON_POLICY",
            "Retained costs must not have an allocation driver",
        )
    elif common_driver is not None:
        require(
            common_driver["capacityPolicy"] == "actual",
            "COMMON_POLICY",
            "Common costs use an actual allocation basis",
        )
    source = case.get("sourceTotals")
    require(
        isinstance(source, dict),
        "SOURCE_TOTALS",
        "Independent reviewed source totals required",
    )
    _references(source.get("evidenceIds"), evidence_ids)
    require(
        total([row["revenueCents"] for row in objects])
        == cents(source.get("revenueCents")),
        "REVENUE_TIE_OUT",
        "Objects differ from reviewed source revenue",
    )
    require(
        total([row["amountCents"] for row in costs]) == cents(source.get("costsCents")),
        "COST_TIE_OUT",
        "Costs differ from reviewed source costs",
    )
    review = case.get("review")
    require(isinstance(review, dict), "REVIEW", "Mapping review required")
    text(review.get("mappingVersion"), "mapping version")
    text(review.get("note"), "mapping basis")
    if meta["demonstration"] and review.get("status") == "synthetic":
        return
    require(
        review.get("status") == "reviewed",
        "REVIEW",
        "Review mappings before calculation",
    )
    text(review.get("reviewer"), "mapping reviewer")
    text(review.get("reviewedAt"), "mapping review date")


def _allocation(
    amount: int, driver: Any, ids: Sequence[str], *, variable: bool = False
) -> dict[str, Any]:
    if amount == 0:
        return {"byObject": dict.fromkeys(ids, 0), "unusedCents": 0}
    require(
        driver is not None,
        "MISSING_DRIVER",
        "The requested method needs a reviewed allocation driver",
    )
    capacity = (
        None if variable or driver["capacityPolicy"] == "actual" else driver["capacity"]
    )
    return allocate_cents(amount, driver["weights"], capacity)


def _method(case: Mapping[str, Any], method: str) -> dict[str, Any]:
    costs = case["costs"]
    ids = [row["id"] for row in case["objects"]]

    def cost_sum(**filters: str) -> int:
        return total(
            [
                row["amountCents"]
                for row in costs
                if all(row.get(k) == v for k, v in filters.items())
            ]
        )

    allocations = []
    variable = dict.fromkeys(ids, 0)
    for pool in case["pools"]:
        allocation = _allocation(
            cost_sum(poolId=pool["id"], behavior="variable"),
            pool.get("driver"),
            ids,
            variable=True,
        )
        allocations.append({"poolId": pool["id"], **allocation})
        for identifier in ids:
            variable[identifier] = total(
                [variable[identifier], allocation["byObject"][identifier]]
            )
    objects = []
    for row in case["objects"]:
        identifier = row["id"]
        amount = total(
            [variable[identifier], cost_sum(objectId=identifier, behavior="variable")]
        )
        cm1 = total([row["revenueCents"], -amount])
        specific = cost_sum(objectId=identifier, behavior="fixed")
        objects.append(
            {
                "id": identifier,
                "revenueCents": row["revenueCents"],
                "variableCents": amount,
                "cm1Cents": cm1,
                "specificFixedCents": specific,
                "cm2Cents": total([cm1, -specific]),
            }
        )
    common = cost_sum(traceability="entity")
    indirect = cost_sum(traceability="indirect", behavior="fixed")
    specific_total = total([row["specificFixedCents"] for row in objects])
    profit = total(
        [case["sourceTotals"]["revenueCents"], -case["sourceTotals"]["costsCents"]]
    )
    result: dict[str, Any] = {
        "method": method,
        "objects": objects,
        "variableAllocations": allocations,
    }
    if method == "direct_costing":
        result.update(
            cm1Cents=total([row["cm1Cents"] for row in objects]),
            fixedCents=total([specific_total, indirect, common]),
        )
        reconciled = total([result["cm1Cents"], -result["fixedCents"]])
    elif method == "direct_costing_evoluto":
        result.update(
            cm2Cents=total([row["cm2Cents"] for row in objects]),
            retainedFixedCents=total([indirect, common]),
        )
        reconciled = total([result["cm2Cents"], -result["retainedFixedCents"]])
    else:
        common_allocation = _allocation(
            common if case["commonPolicy"] == "allocate" else 0,
            case.get("commonDriver"),
            ids,
        )
        fixed = (
            [
                {
                    "poolId": "TRADITIONAL",
                    **_allocation(indirect, case.get("traditionalDriver"), ids),
                }
            ]
            if method == "full_costing"
            else [
                {
                    "poolId": pool["id"],
                    **_allocation(
                        cost_sum(poolId=pool["id"], behavior="fixed"),
                        pool.get("driver"),
                        ids,
                    ),
                }
                for pool in case["pools"]
            ]
        )
        for row in objects:
            activity = total([item["byObject"][row["id"]] for item in fixed])
            allocated = total([activity, common_allocation["byObject"][row["id"]]])
            full_cost = total(
                [row["variableCents"], row["specificFixedCents"], allocated]
            )
            row.update(
                allocatedFixedCents=allocated,
                fullCostCents=full_cost,
                marginCents=total([row["revenueCents"], -full_cost]),
            )
            if method == "abc":
                row["activityFixedCents"] = activity
        unused = total([item["unusedCents"] for item in fixed])
        retained = common if case["commonPolicy"] == "retain_entity" else 0
        reconciled = total(
            [*[row["marginCents"] for row in objects], -unused, -retained]
        )
        result.update(
            unusedCapacityCents=unused,
            retainedCommonCents=retained,
            allocations=[*fixed, {"poolId": "COMMON", **common_allocation}],
        )
    require(
        reconciled == profit,
        "PROFIT_TIE_OUT",
        "Method does not reconcile to operating profit",
    )
    result["entityProfitCents"] = profit
    return result


def calculate_costing(
    case: Mapping[str, Any], methods: Sequence[str]
) -> dict[str, Any]:
    """Calculate only reviewed requested methods, with per-method coverage."""
    _validate(case, methods)
    available, unavailable = [], []
    for method in methods:
        try:
            available.append(_method(case, method))
        except CostingContractError as exc:
            if exc.code not in {"MISSING_DRIVER", "ZERO_DRIVER", "CAPACITY_EXCEEDED"}:
                raise
            unavailable.append({"method": method, "code": exc.code, "reason": str(exc)})
    return {
        "methods": available,
        "unavailableMethods": unavailable,
        "requestedMethods": list(methods),
        "status": (
            "blocked"
            if not available
            else "partial" if unavailable else "ready_for_review"
        ),
    }


def calculate_decisions(rows: Any, evidence_ids: set[str]) -> list[dict[str, Any]]:
    """Compare supplied incremental amounts; never infer cost avoidability."""
    formulas = {
        "incremental_order": {
            "revenueCents": 1,
            "variableCents": -1,
            "additionalFixedCents": -1,
            "opportunityCents": -1,
            "oneOffCents": -1,
        },
        "make_or_buy": {
            "avoidableMakeCents": 1,
            "releasedCapacityContributionCents": 1,
            "purchaseCents": -1,
            "transitionCents": -1,
        },
        "discontinue": {
            "lostRevenueCents": -1,
            "avoidedVariableCents": 1,
            "avoidableFixedCents": 1,
            "exitCents": -1,
            "replacementContributionCents": 1,
        },
    }
    results = []
    for row in records(rows, "decisions"):
        kind = row.get("type")
        require(
            isinstance(kind, str) and kind in formulas,
            "DECISION",
            "Unsupported decision calculation",
        )
        text(row.get("label"), "decision label")
        text(row.get("basis"), "decision assumptions")
        _references(row.get("evidenceIds"), evidence_ids)
        values = row.get("amounts")
        require(isinstance(values, dict), "DECISION", "Decision amounts required")
        expected = set(formulas[kind]) | (
            {"strandedFixedCents"} if kind != "incremental_order" else set()
        )
        require(
            set(values) == expected,
            "DECISION",
            "Provide every decision amount explicitly, including zeros",
        )
        require(
            all(cents(v) >= 0 for v in values.values()),
            "DECISION",
            "Decision amounts are nonnegative magnitudes",
        )
        delta = total([values[key] * sign for key, sign in formulas[kind].items()])
        results.append(
            {
                **row,
                "deltaProfitCents": delta,
                "decision": "professional_review_required",
                "economicSignal": (
                    "positive" if delta > 0 else "negative" if delta < 0 else "neutral"
                ),
            }
        )
    return results
