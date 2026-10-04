"""Adapt reviewed costing results to the existing management-pack contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from costing_core import (
    calculate_costing,
    calculate_decisions,
    cents,
    records,
    require,
    text,
    total,
)

__all__ = ["build_costing_pack"]


def money(value: int) -> str:
    return f"{Decimal(value) / 100:.2f}"


def build_costing_pack(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a focused pack without inventing a general ledger or other sections."""
    require(isinstance(payload, dict), "SCHEMA", "Costing payload must be an object")
    require(
        payload.get("schema_version") == "vera.costing_case.v1",
        "SCHEMA",
        "Unsupported costing case",
    )
    entity = text(payload.get("entity"), "entity")
    question = text(payload.get("decision_question"), "decision question")
    language = payload.get("language", "it")
    audience = payload.get("audience", "internal")
    require(language in {"it", "en"}, "LANGUAGE", "Costing reports support it or en")
    require(
        audience in {"internal", "client", "public_demo"},
        "AUDIENCE",
        "Review the report audience",
    )
    case = payload.get("case")
    methods = payload.get("methods")
    calculated = calculate_costing(case, methods)
    require(
        audience != "public_demo" or case["meta"]["demonstration"],
        "AUDIENCE",
        "Public demonstrations require synthetic data",
    )
    decisions = calculate_decisions(
        payload.get("decisions", []), {e["id"] for e in case["evidence"]}
    )
    source = case["sourceTotals"]
    profit = total([source["revenueCents"], -source["costsCents"]])
    labels = {row["id"]: row["label"] for row in case["objects"]}
    rows, method_rows, decision_rows = [], [], []
    metrics: dict[str, dict[str, Any]] = {}

    def metric(identifier: str, label: str, value: int, section: str) -> None:
        metrics[identifier] = {
            "id": identifier,
            "label": label,
            "value": money(value),
            "unit": "EUR",
            "section": section,
        }

    for method in calculated["methods"]:
        name = method["method"]
        margin_key = (
            "cm1Cents"
            if name == "direct_costing"
            else "cm2Cents" if name == "direct_costing_evoluto" else "marginCents"
        )
        for row in method["objects"]:
            identifier = f"costing.{name}.{row['id']}.margin"
            metric(
                identifier, f"{labels[row['id']]} · {name}", row[margin_key], "costing"
            )
            rows.append(
                {
                    "object_id": row["id"],
                    "object": labels[row["id"]],
                    "method": name,
                    "revenue": money(row["revenueCents"]),
                    "variable_cost": money(row["variableCents"]),
                    "contribution_margin": money(row["cm1Cents"]),
                    "specific_fixed_cost": money(row["specificFixedCents"]),
                    "second_margin": money(row["cm2Cents"]),
                    "allocated_fixed_cost": (
                        money(row["allocatedFixedCents"])
                        if "allocatedFixedCents" in row
                        else None
                    ),
                    "margin": money(row[margin_key]),
                    "metric_id": identifier,
                }
            )
        retained = method.get(
            "fixedCents",
            method.get("retainedFixedCents", method.get("retainedCommonCents", 0)),
        )
        method_rows.append(
            {
                "method": name,
                "status": "available",
                "entity_profit": money(profit),
                "retained_cost": money(retained),
                "unused_capacity": money(method.get("unusedCapacityCents", 0)),
                "reason": "",
            }
        )
    for missing in calculated["unavailableMethods"]:
        method_rows.append(
            {
                "method": missing["method"],
                "status": "unavailable",
                "entity_profit": None,
                "retained_cost": None,
                "unused_capacity": None,
                "reason": missing["reason"],
            }
        )
    for decision in decisions:
        identifier = f"costing.decision.{decision['id']}.delta"
        metric(
            identifier,
            decision["label"],
            decision["deltaProfitCents"],
            "costing_decisions",
        )
        decision_rows.append(
            {
                "id": decision["id"],
                "type": decision["type"],
                "decision": decision["label"],
                "delta_profit": money(decision["deltaProfitCents"]),
                "stranded_fixed_cost": money(
                    decision["amounts"].get("strandedFixedCents", 0)
                ),
                "basis": decision["basis"],
                "status": decision["decision"],
                "metric_id": identifier,
            }
        )
    metric(
        "costing.entity.revenue", "Operating revenue", source["revenueCents"], "costing"
    )
    metric(
        "costing.entity.costs",
        "Consumed operating costs",
        source["costsCents"],
        "costing",
    )
    metric(
        "costing.entity.profit",
        "Operating profit within reviewed perimeter",
        profit,
        "costing",
    )
    controls = [
        {
            "role": "reviewed_source_revenue",
            "status": "passed",
            "actual": money(source["revenueCents"]),
            "expected": money(source["revenueCents"]),
            "difference": "0.00",
        },
        {
            "role": "reviewed_source_costs",
            "status": "passed",
            "actual": money(source["costsCents"]),
            "expected": money(source["costsCents"]),
            "difference": "0.00",
        },
    ]
    limitations = [
        "Source totals are reviewed input assertions; arithmetic does not prove source completeness.",
        "Consumed operating costs only: no automatic statutory or tax inventory valuation.",
        "Allocations do not establish avoidability, savings or a decision to discontinue an activity.",
        "Each view contains non-overlapping objects of one dimension; different views must not be added together.",
        "ERP connectors, food/recipe costing and production optimization are outside this implemented path.",
    ]
    limitations.extend(
        f"{row['method']}: {row['reason']}" for row in calculated["unavailableMethods"]
    )
    bridge = payload.get("accounting_bridge")
    if bridge is None:
        limitations.append(
            "No accounting-profit bridge supplied: reconciliation is limited to the reviewed costing source totals."
        )
    else:
        require(isinstance(bridge, dict), "BRIDGE", "Invalid accounting bridge")
        text(bridge.get("basis"), "accounting source basis")
        text(bridge.get("reviewer"), "accounting bridge reviewer")
        source_profit = cents(bridge.get("sourceProfitCents"))
        entries = records(bridge.get("entries"), "bridge")
        evidence = {e["id"] for e in case["evidence"]}
        require(
            bridge.get("sourceEvidenceId") in evidence,
            "BRIDGE",
            "Accounting source evidence required",
        )
        for entry in entries:
            text(entry.get("reason"), "bridge reason")
            require(
                entry.get("evidenceId") in evidence, "BRIDGE", "Unknown bridge evidence"
            )
        bridged = total(
            [source_profit, *[cents(e.get("profitEffectCents")) for e in entries]]
        )
        controls.append(
            {
                "role": "accounting_profit_bridge",
                "status": "passed" if bridged == profit else "failed",
                "actual": money(profit),
                "expected": money(bridged),
                "difference": money(profit - bridged),
            }
        )
    status = (
        "blocked"
        if any(c["status"] == "failed" for c in controls)
        else calculated["status"]
    )
    if case["meta"]["demonstration"]:
        limitations.append(
            "Synthetic demonstration: these results are not client or market evidence."
        )
    return {
        "schema_version": "vera.management_control_pack.v1",
        "workflow_id": "management-control-pack",
        "analysis_kind": "costing",
        "status": status,
        "report_status": "draft_pending_professional_review",
        "entity": entity,
        "language": language,
        "audience": audience,
        "currency": "EUR",
        "demonstration": case["meta"]["demonstration"],
        "reporting_period": {
            "start": case["meta"]["periodStart"],
            "end": case["meta"]["periodEnd"],
            "cutoff": case["meta"]["periodEnd"],
        },
        "coverage": [
            {"section": row["method"], "status": row["status"], "reason": row["reason"]}
            for row in method_rows
        ],
        "controls": controls,
        "metrics": metrics,
        "limitations": limitations,
        "source_lineage": {},
        "sections": {
            "costing": {
                "status": status,
                "question": question,
                "requested_methods": list(methods),
                "demonstration": case["meta"]["demonstration"],
                "rows": rows,
                "row_count": len(rows),
            },
            "costing_methods": {"status": status, "rows": method_rows},
            "costing_decisions": {
                "status": "available" if decision_rows else "not_requested",
                "rows": decision_rows,
            },
        },
        "costing_workpapers": {
            "case": case,
            "decisions": decisions,
            "accounting_bridge": bridge,
            "calculation": calculated,
        },
        "case_sha256": hashlib.sha256(
            (
                json.dumps(
                    payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                )
                + "\n"
            ).encode()
        ).hexdigest(),
    }
