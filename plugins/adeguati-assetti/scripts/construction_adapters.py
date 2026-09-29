"""Typed strategy and artifact links; financial engines remain in their workflows."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import cast

from construction_core import _attestation, _put, digest, fields, refs, require, text

__all__ = ["apply_typed_record", "budget_rows", "kpi_value", "validate_plan_binding"]


def decimal_value(value: str) -> Decimal:
    """Accept finite decimal strings only; missing data never becomes zero."""
    require(isinstance(value, str), "Amount must be decimal text")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Invalid decimal amount") from error
    require(result.is_finite(), "Amount must be finite")
    return result


def kpi_value(contract: dict, observation: dict) -> dict:
    """Evaluate a chosen value or ratio, never a semantic or adequacy threshold."""
    if contract["operation"] == "value":
        value = observation.get("value")
        if value is None:
            fields(observation, "missing_reason")
            return {"value": None, "reason": observation["missing_reason"]}
        return {"value": str(decimal_value(value)), "reason": None}
    numerator, denominator = observation.get("numerator"), observation.get(
        "denominator"
    )
    if numerator is None or denominator is None:
        fields(observation, "missing_reason")
        return {"value": None, "reason": observation["missing_reason"]}
    denominator_value = decimal_value(denominator)
    if denominator_value == 0:
        return {
            "value": None,
            "reason": "Denominatore nullo; indicatore non calcolabile",
        }
    scale = Decimal(100) if contract["operation"] == "percent" else Decimal(1)
    return {
        "value": str(scale * decimal_value(numerator) / denominator_value),
        "reason": None,
    }


def validate_plan_binding(plan: dict, binding: dict) -> None:
    """Verify exact v3 artifact/scenario/cycle lineage without recalculating a plan."""
    require(
        plan.get("schema_version") == "mparanza.business_planning_plan.v3",
        "Unsupported Business Planning contract",
    )
    require(
        plan.get("content_sha256")
        == digest({k: v for k, v in plan.items() if k != "content_sha256"}),
        "Business Plan digest mismatch",
    )
    case = plan["case"]
    require(plan["case_sha256"] == digest(case), "Business Plan case digest mismatch")
    require(
        plan["calculations_sha256"] == digest(plan["calculations"]),
        "Business Plan calculation digest mismatch",
    )
    require(binding.get("case_id") == case["case_id"], "Wrong Business Plan case")
    require(binding.get("cycle") == case["cycle"], "Wrong Business Plan cycle")
    require(
        binding.get("currency") == case["reporting_currency"],
        "Wrong Business Plan currency",
    )
    require(binding.get("periods") == case["periods"], "Wrong Business Plan periods")
    scenarios = (
        case.get("financial", {}).get("scenarios", []) if case.get("financial") else []
    )
    require(
        binding.get("scenario_id") in {r["id"] for r in scenarios},
        "Unknown Business Plan scenario",
    )
    require(
        plan["status"] == "ready_for_professional_review",
        "Business Plan is partial or blocked",
    )
    require(
        binding.get("review_status") == "reviewed",
        "Plan binding requires explicit professional review",
    )
    fields(binding, "reviewer", "review_statement", "limitations")


def budget_rows(plan: dict, binding: dict, mapping: dict) -> list[dict]:
    """Map reviewed calculation IDs; exact totals, periods and signs are mandatory."""
    validate_plan_binding(plan, binding)
    require(
        mapping.get("plan_sha256") == plan["content_sha256"],
        "Mapping refers to another plan",
    )
    require(
        mapping.get("scenario") in {"Budget", "Forecast"},
        "Select Budget or Forecast explicitly",
    )
    fields(mapping, "reviewer", "decision", "mapping_version")
    rows = mapping.get("rows")
    require(isinstance(rows, list) and bool(rows), "No reviewed mapping rows")
    rows = cast(list[dict], rows)
    output, seen = [], set()
    totals: dict[str, Decimal] = {}
    for row in rows:
        cid = row.get("calculation_id")
        require(
            cid in plan["calculations"] and cid not in seen,
            "Unknown or duplicate calculation ID",
        )
        seen.add(cid)
        calc = plan["calculations"][cid]
        require(calc["scenario"] == binding["scenario_id"], "Wrong mapped scenario")
        require(calc["period"] in binding["periods"], "Wrong mapped period")
        require(
            calc.get("unit") == binding["currency"],
            "Nonmonetary calculation cannot become a Budget amount",
        )
        require(
            type(row.get("sign")) is int and row["sign"] in {-1, 1},
            "Explicit sign mapping required",
        )
        fields(row, "account_id", "category")
        amount = decimal_value(calc["value"]) * row["sign"]
        key = calc["period"] + "/" + row["category"]
        totals[key] = totals.get(key, Decimal(0)) + amount
        output.append(
            {
                "period": calc["period"],
                "scenario": mapping["scenario"],
                "account_id": row["account_id"],
                "category": row["category"],
                "amount": str(amount),
                "calculation_id": cid,
                "plan_sha256": plan["content_sha256"],
                "mapping_version": mapping["mapping_version"],
            }
        )
    expected = mapping.get("control_totals")
    require(
        isinstance(expected, dict) and set(expected) == set(totals),
        "Missing mapping control totals",
    )
    expected = cast(dict, expected)
    require(
        all(decimal_value(expected[k]) == v for k, v in totals.items()),
        "Budget mapping does not reconcile",
    )
    return output


def apply_typed_record(state: dict, kind: str, p: dict, *, actor: str, at: str) -> None:
    """Validate explicit model-authored contracts; never execute imported formula text."""
    immutable = False
    if kind == "objective":
        fields(p, "description", "perspective", "owner", "scope", "period")
        require(
            p.get("owner_status") in {"proposed", "confirmed"},
            "Objective owner status required",
        )
        refs(p.get("evidence_refs"), state["evidence"], "objective sources")
        collection = "objectives"
    elif kind == "strategy_link":
        require(
            p.get("from_id") in state["objectives"]
            and p.get("to_id") in state["objectives"],
            "Unknown strategy objective",
        )
        fields(p, "hypothesis", "limitations")
        require(
            p.get("status") in {"to_test", "supported", "contested"},
            "Invalid strategy link state",
        )
        refs(
            p.get("evidence_refs", []),
            state["evidence"],
            "strategy evidence",
            empty=p["status"] == "to_test",
        )
        collection = "strategy_links"
    elif kind == "kpi":
        require(p.get("objective_id") in state["objectives"], "KPI needs an objective")
        fields(
            p,
            "definition",
            "formula",
            "formula_version",
            "unit",
            "population",
            "data_owner",
            "frequency",
            "period",
            "cutoff",
            "null_policy",
            "direction",
        )
        require(
            p.get("operation") in {"value", "ratio", "percent"},
            "Unsupported KPI arithmetic; formula text is never executed",
        )
        refs(p.get("evidence_refs"), state["evidence"], "KPI sources")
        require(
            p.get("target_status") in {"unknown", "proposed", "accepted"},
            "Invalid target state",
        )
        if p["target_status"] == "accepted":
            _attestation(state, p)
            require(p.get("target") is not None, "Accepted target cannot be unknown")
        previous = state["kpis"].get(p.get("id"))
        if previous and any(
            previous[f] != p[f] for f in ("formula", "population", "operation", "unit")
        ):
            require(
                previous["formula_version"] != p["formula_version"],
                "Formula/population change needs a new series version",
            )
        collection = "kpis"
    elif kind == "kpi_observation":
        kid = p.get("kpi_id")
        require(kid in state["kpis"], "Unknown KPI")
        contract = state["kpis"][kid]
        require(
            p.get("contract_sha256") == digest(contract),
            "KPI observation has a stale definition",
        )
        fields(p, "period", "population", "coverage", "available_at", "review_status")
        refs(p.get("evidence_refs"), state["evidence"], "KPI observation sources")
        p["result"] = kpi_value(contract, p)
        p["contract"] = contract.copy()
        p["target_status"] = contract["target_status"]
        collection, immutable = "kpi_observations", True
    elif kind == "strategy_review":
        refs(
            p.get("observation_ids"),
            state["kpi_observations"],
            "strategy review observations",
        )
        fields(p, "explanations", "hypotheses", "decision", "next_review")
        refs(
            p.get("action_ids", []),
            state["actions"],
            "strategy review actions",
            empty=True,
        )
        _attestation(state, p)
        collection, immutable = "strategy_reviews", True
    elif kind == "artifact":
        fields(
            p,
            "workflow_id",
            "module_version",
            "run_id",
            "artifact_id",
            "source_id",
            "sha256",
            "scope",
            "currency",
            "review_status",
            "limitations",
        )
        require(
            p.get("client_id") == state["client_id"]
            and p.get("engagement_id") == state["engagement_id"],
            "Artifact belongs to another client or engagement",
        )
        require(
            p.get("source_id") in state["evidence"],
            "Artifact needs exact imported evidence",
        )
        require(
            p["sha256"] == state["evidence"][p["source_id"]]["sha256"],
            "Artifact source hash mismatch",
        )
        require(
            p.get("review_status") in {"draft", "reviewed"},
            "Invalid artifact review status",
        )
        require(
            isinstance(p.get("periods"), list)
            and bool(p["periods"])
            and all(isinstance(x, str) and x.strip() for x in p["periods"]),
            "Artifact periods are required",
        )
        require(
            p.get("adapter_status")
            in {"reviewed_external", "native_contract_verified"},
            "Declare adapter capability",
        )
        if p["review_status"] == "reviewed":
            fields(p, "reviewer", "review_statement")
        if (
            p["workflow_id"] == "business-planning"
            and p["adapter_status"] == "native_contract_verified"
        ):
            validate_plan_binding(p.get("document", {}), p)
        elif p["adapter_status"] == "native_contract_verified":
            raise ValueError(
                "Adapter not qualified; use a reviewed external artifact with explicit limits"
            )
        collection = "artifacts"
    else:
        legacy = p.get("record", {})
        require(
            legacy.get("schema_version") == 1
            and legacy.get("workflow_id") == "adeguati-assetti",
            "Expected historical v1 review",
        )
        require(
            legacy.get("client_id") == state["client_id"]
            and legacy.get("engagement_id") == state["engagement_id"],
            "Legacy review belongs to another client or engagement",
        )
        require(
            legacy.get("record_sha256")
            == digest({k: v for k, v in legacy.items() if k != "record_sha256"}),
            "Historical review digest mismatch",
        )
        refs(p.get("evidence_refs"), state["evidence"], "legacy review evidence")
        p["migration_limit"] = (
            "Original v1 preserved. Missing scores stay unknown; historical completed actions do not establish adoption or operation."
        )
        collection, immutable = "legacy_reviews", True
    _put(state, collection, p, actor, at, immutable=immutable)
