"""Shared reviewed planning contract and authoritative calculation register.

Determinism is limited to auditable arithmetic, identity, explicit permissions
and reference closure. People/models select sources, align observations, assess
materiality and author/review strategy; this module never infers those judgments.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from business_planning_core import CASE_SCHEMA as FINANCIAL_SCHEMA
from business_planning_core import build_business_plan

__all__ = [
    "CASE_SCHEMA",
    "PlanningError",
    "build_plan",
    "validate_plan",
    "digest",
    "verify_sources",
]
CASE_SCHEMA = "mparanza.business_planning_case.v3"
OPENING = (
    "cash",
    "accounts_receivable",
    "inventory",
    "other_current_assets",
    "net_fixed_assets",
    "other_non_current_assets",
    "accounts_payable",
    "debt",
    "other_liabilities",
    "equity",
)
INPUTS = (
    "revenue",
    "cogs",
    "operating_expenses",
    "depreciation_amortization",
    "interest_expense",
    "tax_expense",
    "capital_expenditure",
    "ending_accounts_receivable",
    "ending_inventory",
    "ending_other_current_assets",
    "ending_accounts_payable",
    "ending_other_liabilities",
    "debt_draws",
    "debt_repayments",
    "equity_contributions",
    "dividends",
)
EXTRAS = ("variable_cogs", "variable_operating_expenses")
ROLES = {
    "client_document",
    "user_statement",
    "professional_review",
    "financial_model",
    "external_evidence",
    "model_hypothesis",
}
KINDS = {"fact", "assumption", "hypothesis"}


class PlanningError(ValueError):
    """The case or report cannot satisfy its mechanical contract."""


def digest(value: Any) -> str:
    """Hash a JSON value reproducibly, rejecting nonfinite JSON numbers."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def number(value: Any) -> Decimal:
    """Require finite canonical decimal text, never binary floating inputs."""
    if not isinstance(value, str) or not re.fullmatch(
        r"-?(?:0|[1-9]\d*)(?:\.\d+)?", value
    ):
        raise PlanningError(f"Expected canonical decimal text: {value!r}")
    return Decimal(value)


def text_number(value: Decimal) -> str:
    return format(value, "f")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlanningError(message)


def indexed(items: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    require(isinstance(items, list), f"{label} must be a list")
    for item in items:
        identifier = item.get("id")
        if (
            not isinstance(identifier, str)
            or re.fullmatch(r"[a-z][a-z0-9_-]*", identifier) is None
        ):
            raise PlanningError(f"Invalid {label} ID: {identifier}")
        require(identifier not in result, f"Duplicate {label} ID: {identifier}")
        result[identifier] = item
    return result


def reviewed(record: dict[str, Any]) -> bool:
    """Check the explicit review attestation, not the reviewer's identity."""
    if record.get("status") not in {"reviewed", "confirmed"} or not record.get(
        "reviewer"
    ):
        return False
    try:
        timestamp = datetime.fromisoformat(record.get("reviewed_at", ""))
    except (TypeError, ValueError):
        return False
    return timestamp.tzinfo is not None and timestamp.utcoffset() is not None


def verify_sources(case: dict[str, Any], source_root: Path) -> None:
    """Verify every selected file, not just files referenced in the narrative."""
    root = source_root.resolve()
    sources = indexed(case["sources"], "source")
    require(bool(sources), "Select and register the source files first")
    paths = set()
    for source in sources.values():
        for field in (
            "path",
            "sha256",
            "version",
            "role",
            "review_status",
            "intended_audience",
            "confidentiality",
        ):
            require(bool(source.get(field)), f"Source {source['id']} missing {field}")
        require(source["role"] in ROLES, "Unknown source role")
        require(
            source["review_status"] in {"reviewed", "confirmed", "unverified"},
            "Unknown source review status",
        )
        require(
            isinstance(source["intended_audience"], list),
            "Source audience must be an explicit list",
        )
        restriction = source["confidentiality"]
        require(
            isinstance(restriction.get("allowed_audiences"), list)
            and bool(restriction.get("classification")),
            "Explicit confidentiality restrictions required",
        )
        relative = Path(source["path"])
        require(
            not relative.is_absolute(),
            "Source paths must be relative to the selected source root",
        )
        path = (root / relative).resolve()
        require(
            path.is_relative_to(root) and path.is_file(),
            f"Source outside root or missing: {source['id']}",
        )
        require(path not in paths, "Register each selected file only once")
        paths.add(path)
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"],
            f"Source hash mismatch: {source['id']}",
        )


def _review_case(case: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    require(
        case.get("schema_version") == CASE_SCHEMA,
        "Finalization requires the shared v3 case with provenance; legacy cases must be reviewed and migrated",
    )
    allowed = {
        "schema_version",
        "case_id",
        "entity_name",
        "company_stage",
        "planning_objective",
        "audience",
        "reporting_currency",
        "periods",
        "review",
        "sources",
        "evidence",
        "assumptions",
        "decisions",
        "observations",
        "resolutions",
        "financial",
        "narrative",
        "limitations",
        "required_sections",
    }
    require(
        set(case) - {"assessment", "commercial", "presentation"} == allowed,
        f"Shared case fields differ: {sorted(set(case) ^ allowed)}",
    )
    for key in (
        "case_id",
        "entity_name",
        "company_stage",
        "planning_objective",
        "audience",
    ):
        require(
            isinstance(case[key], str) and bool(case[key].strip()), f"Missing {key}"
        )
    require(
        (
            case["reporting_currency"] is None
            and case["financial"] is None
            and not case.get("commercial")
        )
        or (
            isinstance(case["reporting_currency"], str)
            and re.fullmatch(r"[A-Z]{3}", case["reporting_currency"]) is not None
        ),
        "Currency must be ISO-style uppercase code",
    )
    periods = case["periods"]
    require(
        (1 <= len(periods) <= 60 or (not periods and case["financial"] is None))
        and len(set(periods)) == len(periods),
        "Unique monthly periods required",
    )
    dates = [date.fromisoformat(p + "-01") for p in periods]
    ordinals = [d.year * 12 + d.month for d in dates]
    require(
        not ordinals
        or ordinals == list(range(ordinals[0], ordinals[0] + len(periods))),
        "Use contiguous ordered YYYY-MM periods",
    )
    sources = indexed(case["sources"], "source")
    evidence = indexed(case["evidence"], "evidence")
    assumptions = indexed(case["assumptions"], "assumption")
    decisions = indexed(case["decisions"], "decision")
    require(
        not (set(evidence) & set(assumptions)),
        "Evidence and assumption IDs must be disjoint",
    )
    issues = []
    if not reviewed(case["review"]):
        issues.append("Case professional review is incomplete")
    for record in [*evidence.values(), *assumptions.values()]:
        require(record.get("kind") in KINDS, f"Invalid evidence class: {record['id']}")
        require(
            bool(record.get("description")), "Evidence/assumption description required"
        )
        require(
            bool(record.get("source_ids"))
            and set(record["source_ids"]) <= set(sources),
            "Unknown or missing source reference",
        )
        if not reviewed(record):
            issues.append(
                f"Evidence/assumption {record['id']} is not confirmed by a reviewer"
            )
    for record in assumptions.values():
        require(
            record["kind"] in {"assumption", "hypothesis"},
            "Facts belong in the evidence register",
        )
        require(
            bool(record.get("rationale"))
            and (bool(record.get("effective_periods")) or not periods),
            "Assumption rationale and periods required",
        )
        require(
            set(record["effective_periods"]) <= set(periods),
            "Unknown assumption period",
        )
    for decision in decisions.values():
        require(
            bool(decision.get("rationale")),
            "Professional decision requires a rationale",
        )
        if not reviewed(decision):
            issues.append(f"Professional decision {decision['id']} remains unreviewed")
    for source in sources.values():
        if source["review_status"] == "unverified":
            issues.append(f"Source {source['id']} remains unverified")
    refs = {**evidence, **assumptions}
    used_sources = {s for r in refs.values() for s in r["source_ids"]}
    require(
        used_sources == set(sources),
        "Every selected source needs an evidence/assumption record (source coverage)",
    )
    require(
        set(case["required_sections"]) <= {"financial", "business_analysis"},
        "Unknown required section",
    )
    return {"sources": sources, "refs": refs, "decisions": decisions}, issues


def _financial(
    case: dict[str, Any], registries: dict[str, Any], issues: list[str]
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    financial = case["financial"]
    if financial is None:
        issues.append(
            "Financial model unavailable; no capital recommendation is supported"
        )
        return None, {}
    require(
        set(financial)
        in (
            {"opening_balance", "opening_refs", "scenarios"},
            {"opening_balance", "opening_refs", "scenarios", "channels"},
        ),
        "Unexpected financial fields",
    )
    require(
        set(financial["opening_balance"]) == set(OPENING),
        "Complete opening balance keys required; use null for unknowns",
    )
    require(
        set(financial["opening_refs"]) == set(OPENING),
        "Opening input reference coverage required",
    )
    refs = registries["refs"]
    source_ids: set[str] = set()
    missing = []

    def check_input(
        value: Any, bindings: list[str], label: str, period: str | None = None
    ) -> None:
        require(
            bool(bindings) and set(bindings) <= set(refs),
            f"Missing input lineage: {label}",
        )
        for ref in bindings:
            source_ids.update(refs[ref]["source_ids"])
            if period and refs[ref]["kind"] in {"assumption", "hypothesis"}:
                require(
                    period in refs[ref]["effective_periods"],
                    f"Assumption {ref} ineffective for {period}",
                )
        if value is None:
            missing.append(label)
        else:
            number(value)

    for key, value in financial["opening_balance"].items():
        check_input(value, financial["opening_refs"][key], f"opening/{key}")
    scenarios = indexed(financial["scenarios"], "scenario")
    require(1 <= len(scenarios) <= 8, "One to eight reviewed scenarios required")
    for scenario in scenarios.values():
        require(
            set(scenario) == {"id", "label", "schedule"}, "Unexpected scenario fields"
        )
        require(
            [r["period"] for r in scenario["schedule"]] == case["periods"],
            "Scenario period mismatch",
        )
        for row in scenario["schedule"]:
            require(
                set(row) == {"period", "input_refs", *INPUTS, *EXTRAS},
                "Unexpected or missing schedule fields; use null for unknowns",
            )
            require(
                set(row["input_refs"]) == set(INPUTS + EXTRAS),
                "Each input needs explicit lineage",
            )
            for key in INPUTS + EXTRAS:
                check_input(
                    row[key],
                    row["input_refs"][key],
                    f"{scenario['id']}/{row['period']}/{key}",
                    row["period"],
                )
    if missing:
        issues.extend(f"Missing financial input: {label}" for label in missing)
    incomplete_scenarios = {label.split("/", 1)[0] for label in missing}
    usable_scenarios = {
        key: value
        for key, value in scenarios.items()
        if key not in incomplete_scenarios
    }
    # Linked statements need opening balances, but a missing input in one
    # scenario must not suppress another independently complete scenario.
    if "opening" in incomplete_scenarios or not usable_scenarios:
        return None, {}
    # Use the shared linked-statement engine, fed only from this register.
    # Readiness is imposed separately; draft inputs are never represented as accepted.
    internal_case = {
        k: case[k]
        for k in (
            "case_id",
            "entity_name",
            "company_stage",
            "planning_objective",
            "audience",
            "reporting_currency",
            "periods",
        )
    }
    internal_case.update(
        {
            "schema_version": FINANCIAL_SCHEMA,
            "professional_lens": "accounting_financial",
            "reconciliation_tolerance": "0",
            "review": {
                "status": "reviewed",
                "reviewer": "calculation-only",
                "reviewed_at": "2000-01-01T00:00:00+00:00",
            },
            "evidence_register": [
                {
                    "id": r["id"],
                    "kind": (
                        "opening_fact"
                        if r["kind"] == "fact"
                        else "management_assumption"
                    ),
                    "description": r["description"],
                    "source_ref": ",".join(r["source_ids"]),
                    "status": "reviewed",
                }
                for r in refs.values()
            ],
            "opening_balance": {
                "values": financial["opening_balance"],
                "evidence_ids": sorted(
                    {r for values in financial["opening_refs"].values() for r in values}
                ),
            },
            "assumptions": [
                {
                    "id": "calculation-inputs",
                    "category": "reviewed input bindings",
                    "description": "Numerical projection only; actual review status is in the shared register.",
                    "evidence_ids": list(refs),
                    "effective_periods": case["periods"],
                    "rationale": "Mechanical statement projection",
                    "status": "confirmed",
                }
            ],
            "scenarios": [
                {
                    "id": s["id"],
                    "label": s["label"],
                    "schedule": [
                        {
                            **{k: r[k] for k in INPUTS},
                            "period": r["period"],
                            "assumption_ids": ["calculation-inputs"],
                        }
                        for r in s["schedule"]
                    ],
                }
                for s in usable_scenarios.values()
            ],
        }
    )
    statements = build_business_plan(internal_case)
    statements["unavailable_scenarios"] = sorted(incomplete_scenarios)
    if not statements["reconciliation"]["all_passed"]:
        issues.append("Financial statement reconciliation failed")
    calculations: dict[str, Any] = {}
    for scenario in statements["scenarios"]:
        cumulative_financing = Decimal(0)
        cash_min = number(financial["opening_balance"]["cash"])
        unfinanced_min = cash_min
        exhausted = False
        for index, row in enumerate(scenario["periods"]):
            period = row["period"]
            inputs = scenarios[scenario["id"]]["schedule"][index]
            vals = {k: number(inputs[k]) for k in INPUTS + EXTRAS}
            lineage = sorted(
                {
                    r
                    for prior in scenarios[scenario["id"]]["schedule"][: index + 1]
                    for bindings in prior["input_refs"].values()
                    for r in bindings
                }
                | {
                    r
                    for bindings in financial["opening_refs"].values()
                    for r in bindings
                }
            )

            def add(
                metric: str,
                value: Decimal | None,
                formula: str,
                unit: str | None = None,
                reason: str | None = None,
            ) -> None:
                cid = f"{scenario['id']}/{period}/{metric}"
                calculations[cid] = {
                    "id": cid,
                    "scenario": scenario["id"],
                    "period": period,
                    "metric": metric,
                    "value": text_number(value) if value is not None else None,
                    "unit": unit or case["reporting_currency"],
                    "formula": formula,
                    "basis_ids": lineage,
                    "source_ids": sorted(
                        {s for r in lineage for s in refs[r]["source_ids"]}
                    ),
                    "unavailable_reason": reason,
                }

            for group in ("profit_and_loss", "cash_flow", "balance_sheet"):
                for metric, value in row[group].items():
                    # Some statement names overlap with identical values; retain one authoritative ID.
                    if f"{scenario['id']}/{period}/{metric}" not in calculations:
                        add(
                            metric,
                            number(value),
                            f"Linked statements: {group}.{metric}",
                        )
            revenue = vals["revenue"]
            gross = number(row["profit_and_loss"]["gross_profit"])
            ebitda = number(row["profit_and_loss"]["ebitda"])
            require(
                Decimal(0) <= vals["variable_cogs"] <= vals["cogs"],
                "Variable COGS must reconcile to COGS",
            )
            require(
                Decimal(0)
                <= vals["variable_operating_expenses"]
                <= vals["operating_expenses"],
                "Variable operating expenses must reconcile",
            )
            contribution = (
                revenue - vals["variable_cogs"] - vals["variable_operating_expenses"]
            )
            cm_ratio = contribution / revenue if revenue else None
            fixed = (
                vals["cogs"]
                + vals["operating_expenses"]
                - vals["variable_cogs"]
                - vals["variable_operating_expenses"]
            )
            be = fixed / cm_ratio if cm_ratio is not None and cm_ratio > 0 else None
            add(
                "gross_margin",
                gross / revenue if revenue else None,
                "gross_profit / revenue",
                "ratio",
                "Undefined at zero revenue" if not revenue else None,
            )
            add(
                "contribution_margin",
                contribution,
                "revenue - variable_cogs - variable_operating_expenses",
            )
            add(
                "contribution_margin_ratio",
                cm_ratio,
                "contribution_margin / revenue",
                "ratio",
                "Undefined at zero revenue" if not revenue else None,
            )
            add(
                "ebitda_margin",
                ebitda / revenue if revenue else None,
                "ebitda / revenue",
                "ratio",
                "Undefined at zero revenue" if not revenue else None,
            )
            add(
                "break_even_revenue",
                be,
                "fixed operating costs / contribution margin ratio",
                reason=(
                    "Non-positive or undefined contribution ratio"
                    if be is None
                    else None
                ),
            )
            add(
                "margin_of_safety",
                (revenue - be) / revenue if be is not None and revenue else None,
                "(revenue - break_even_revenue) / revenue",
                "ratio",
                (
                    "Break-even or revenue unavailable"
                    if be is None or not revenue
                    else None
                ),
            )
            working_capital = sum(
                (
                    number(row["balance_sheet"][k])
                    for k in (
                        "accounts_receivable",
                        "inventory",
                        "other_current_assets",
                    )
                ),
                Decimal("0"),
            ) - sum(
                (
                    number(row["balance_sheet"][k])
                    for k in ("accounts_payable", "other_liabilities")
                ),
                Decimal("0"),
            )
            add(
                "working_capital",
                working_capital,
                "receivables + inventory + other current assets - payables - other operating liabilities",
            )
            ending_cash = number(row["cash_flow"]["ending_cash"])
            cumulative_financing += vals["debt_draws"] + vals["equity_contributions"]
            before = ending_cash - cumulative_financing
            cash_min = min(cash_min, ending_cash)
            unfinanced_min = min(unfinanced_min, before)
            add(
                "cash_before_financing",
                before,
                "ending_cash - cumulative debt draws - cumulative equity injections",
            )
            add(
                "minimum_cash",
                cash_min,
                "minimum opening/month-end cash through this period",
            )
            add(
                "funding_requirement",
                max(Decimal(0), -unfinanced_min),
                "max(0, -minimum cash before new financing through this period)",
            )
            add(
                "residual_funding_gap",
                max(Decimal(0), -cash_min),
                "max(0, -minimum cash after scheduled financing through this period)",
            )
            debt_service = vals["interest_expense"] + vals["debt_repayments"]
            cfads = (
                number(row["cash_flow"]["operating_cash_flow"])
                + vals["interest_expense"]
                - vals["capital_expenditure"]
            )
            add("debt_service", debt_service, "cash interest + principal repayments")
            add(
                "cfads",
                cfads,
                "operating cash flow + cash interest - capital expenditure",
            )
            add(
                "dscr",
                cfads / debt_service if debt_service else None,
                "CFADS / debt service; period-specific, not a covenant definition",
                "ratio",
                "Not applicable: no debt service" if not debt_service else None,
            )
            ocf = number(row["cash_flow"]["operating_cash_flow"])
            previous_cash = (
                number(financial["opening_balance"]["cash"])
                if not index
                else number(scenario["periods"][index - 1]["cash_flow"]["ending_cash"])
            )
            add(
                "opening_cash",
                previous_cash,
                "opening balance or prior period closing cash",
            )
            sources = (
                previous_cash
                + max(Decimal(0), ocf)
                + vals["debt_draws"]
                + vals["equity_contributions"]
            )
            uses = (
                max(Decimal(0), -ocf)
                + vals["capital_expenditure"]
                + vals["debt_repayments"]
                + vals["dividends"]
                + ending_cash
            )
            add(
                "sources",
                sources,
                "opening period cash + positive operating cash flow + debt draws + equity",
            )
            add(
                "uses",
                uses,
                "operating cash deficit + capex + debt repayments + dividends + closing cash (signed cash deficit retained)",
            )
            add("sources_uses_difference", sources - uses, "sources - uses")
            remaining = [
                number(r["cash_flow"]["ending_cash"])
                for r in scenario["periods"][index:]
            ]
            exhausted = exhausted or ending_cash < 0
            next_negative = next(
                (i for i, cash in enumerate(remaining) if cash < 0), None
            )
            runway = (
                Decimal(0)
                if exhausted
                else Decimal(next_negative) if next_negative is not None else None
            )
            add(
                "runway",
                runway,
                "complete monthly periods from this month's start until first modeled negative cash; zero once exhausted",
                "months",
                (
                    "No exhaustion within remaining forecast; beyond-horizon runway unknown"
                    if runway is None
                    else None
                ),
            )
            row["assumption_ids"] = sorted(
                {ref for bindings in inputs["input_refs"].values() for ref in bindings}
            )
        scenario.pop("summary")
        scenario["summary_calculation_ids"] = {
            metric: f"{scenario['id']}/{case['periods'][-1]}/{metric}"
            for metric in (
                "minimum_cash",
                "funding_requirement",
                "residual_funding_gap",
                "ending_cash",
            )
        }
    channel_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for channel in indexed(financial.get("channels", []), "channel row").values():
        require(
            set(channel)
            == {
                "id",
                "channel",
                "scenario",
                "period",
                "unit_label",
                "units",
                "revenue",
                "variable_costs",
                "input_refs",
            },
            "Unexpected channel input fields",
        )
        require(
            channel["scenario"] in scenarios and channel["period"] in case["periods"],
            "Unknown channel scenario or period",
        )
        require(
            bool(channel["channel"]) and bool(channel["unit_label"]),
            "Channel name and unit required",
        )
        require(
            set(channel["input_refs"]) == {"units", "revenue", "variable_costs"},
            "Channel input lineage required",
        )
        for field in ("units", "revenue", "variable_costs"):
            check_input(
                channel[field],
                channel["input_refs"][field],
                f"channel/{channel['id']}/{field}",
                channel["period"],
            )
            require(
                channel[field] is not None and number(channel[field]) >= 0,
                "Channel charts need complete nonnegative inputs",
            )
        channel_groups.setdefault((channel["scenario"], channel["period"]), []).append(
            channel
        )
    for (sid, period), channels in channel_groups.items():
        if sid in incomplete_scenarios:
            issues.append(
                f"Channel reconciliation unavailable for incomplete scenario: {sid}/{period}"
            )
            continue
        require(
            len({c["channel"] for c in channels}) == len(channels),
            "Duplicate channel in a scenario period",
        )
        require(
            len({c["unit_label"] for c in channels}) == 1,
            "Normalize channel units before comparison",
        )
        row_inputs = scenarios[sid]["schedule"][case["periods"].index(period)]
        require(
            sum(number(c["revenue"]) for c in channels)
            == number(row_inputs["revenue"]),
            "Channel revenue does not reconcile to the authoritative scenario",
        )
        require(
            sum(number(c["variable_costs"]) for c in channels)
            == number(row_inputs["variable_cogs"])
            + number(row_inputs["variable_operating_expenses"]),
            "Channel variable costs do not reconcile to the authoritative scenario",
        )
        for channel in channels:
            units, revenue, costs = (
                number(channel[k]) for k in ("units", "revenue", "variable_costs")
            )
            basis = sorted(
                {ref for bindings in channel["input_refs"].values() for ref in bindings}
            )
            for metric, value, unit, formula in (
                (
                    "revenue",
                    revenue,
                    case["reporting_currency"],
                    "reviewed channel revenue",
                ),
                (
                    "variable_costs",
                    costs,
                    case["reporting_currency"],
                    "reviewed channel variable costs",
                ),
                ("units", units, channel["unit_label"], "reviewed channel units"),
                (
                    "revenue_per_unit",
                    revenue / units if units else None,
                    f"{case['reporting_currency']}/{channel['unit_label']}",
                    "channel revenue / units",
                ),
                (
                    "variable_cost_per_unit",
                    costs / units if units else None,
                    f"{case['reporting_currency']}/{channel['unit_label']}",
                    "channel variable costs / units",
                ),
                (
                    "contribution_per_unit",
                    (revenue - costs) / units if units else None,
                    f"{case['reporting_currency']}/{channel['unit_label']}",
                    "(channel revenue - variable costs) / units",
                ),
            ):
                cid = f"{sid}/{period}/channel_{channel['id']}_{metric}"
                calculations[cid] = {
                    "id": cid,
                    "scenario": sid,
                    "period": period,
                    "metric": f"channel_{channel['id']}_{metric}",
                    "value": text_number(value) if value is not None else None,
                    "unit": unit,
                    "formula": formula,
                    "basis_ids": basis,
                    "source_ids": sorted(
                        {s for ref in basis for s in refs[ref]["source_ids"]}
                    ),
                    "unavailable_reason": (
                        "No channel units; unit economics undefined"
                        if value is None
                        else None
                    ),
                }
    return {
        "scenarios": statements["scenarios"],
        "reconciliation": statements["reconciliation"],
        "unavailable_scenarios": statements["unavailable_scenarios"],
    }, calculations


def _comparisons(
    case: dict[str, Any],
    regs: dict[str, Any],
    calculations: dict[str, Any],
    issues: list[str],
) -> list[dict[str, Any]]:
    observations = indexed(case["observations"], "observation")
    groups: dict[str, list[dict[str, Any]]] = {}
    for observation in observations.values():
        require(
            bool(observation.get("source_ids"))
            and set(observation["source_ids"]) <= set(regs["sources"]),
            "Observation source missing",
        )
        number(observation["value"])
        require(observation["period"] in case["periods"], "Unknown observation period")
        require(
            isinstance(observation["material"], bool),
            "Materiality must be explicitly reviewed",
        )
        key = (
            f"{observation['scenario']}/{observation['period']}/{observation['metric']}"
        )
        groups.setdefault(key, []).append(observation)
    resolutions = {r["calculation_id"]: r for r in case["resolutions"]}
    require(
        len(resolutions) == len(case["resolutions"]), "Duplicate conflict resolution"
    )
    require(set(resolutions) <= set(groups), "Resolution has no observation group")
    result = []
    for key, rows in groups.items():
        conflicting = len({number(r["value"]) for r in rows}) > 1
        material = any(r["material"] for r in rows)
        resolution = resolutions.get(key)
        selected = None
        if resolution:
            require(
                resolution["observation_id"] in {r["id"] for r in rows},
                "Resolution must select an observation in the comparison",
            )
            decision = regs["decisions"].get(resolution["decision_id"])
            require(
                decision is not None,
                "Conflict resolution needs a professional decision",
            )
            if reviewed(decision):
                selected = observations[resolution["observation_id"]]
        elif not conflicting:
            selected = rows[0]
        if material and conflicting and selected is None:
            issues.append(f"Unresolved material conflict: {key}")
        calc = calculations.get(key)
        if (
            material
            and selected is not None
            and (
                calc is None
                or calc["value"] is None
                or number(calc["value"]) != number(selected["value"])
            )
        ):
            issues.append(
                f"Accepted observation awaits an available authoritative calculation: {key}"
                if calc is None or calc["value"] is None
                else f"Accepted observation disagrees with authoritative calculation: {key}"
            )
        result.append(
            {
                "calculation_id": key,
                "observations": rows,
                "conflicting": conflicting,
                "material": material,
                "accepted_observation_id": selected["id"] if selected else None,
                "resolution": resolution,
            }
        )
    return result


def build_plan(
    case: dict[str, Any], *, source_root: Path, owner: str | None = None
) -> dict[str, Any]:
    """Build one product-independent plan; owner is an optional entry-adapter label."""
    require(owner in {None, "Vera", "Clara"}, "Unknown entry point")
    require(
        case.get("schema_version") == CASE_SCHEMA,
        "Finalization requires the shared v3 case with provenance; legacy cases must be reviewed and migrated",
    )
    regs, issues = _review_case(case)
    verify_sources(case, source_root)
    statements, calculations = _financial(case, regs, issues)
    from planning_commercial import calculate_commercial

    calculate_commercial(case, calculations, issues)
    comparisons = _comparisons(case, regs, calculations, issues)
    for comparison in comparisons:
        units = {row["unit"] for row in comparison["observations"]}
        require(len(units) == 1, "Reconcile source units before comparing values")
        for observation in comparison["observations"]:
            calculation = calculations.get(comparison["calculation_id"])
            require(
                observation["unit"] in {case["reporting_currency"], "ratio", "months"}
                and (calculation is None or observation["unit"] == calculation["unit"]),
                "Observation unit mismatch; reconcile units before comparison",
            )
            if (
                statements is not None
                and observation["metric"] == "ebitda"
                and observation["basis"] == "reported"
            ):
                cid = f"{observation['scenario']}/{observation['period']}/reported_ebitda_{observation['id']}"
                calculations[cid] = {
                    "id": cid,
                    "scenario": observation["scenario"],
                    "period": observation["period"],
                    "metric": f"reported_ebitda_{observation['id']}",
                    "value": observation["value"],
                    "unit": observation["unit"],
                    "formula": "Identity projection of reported source figure; not accepted model EBITDA",
                    "basis_ids": [observation["id"]],
                    "source_ids": observation["source_ids"],
                    "unavailable_reason": None,
                }
    narrative = case["narrative"]
    indexed(narrative, "narrative")
    if "financial" in case["required_sections"] and statements is None:
        issues.append("Required financial model is missing")
    # Keep all mechanical/narrative mismatches visible, but do not render rejected prose.
    from planning_report import review_narrative

    accepted, narrative_issues = review_narrative(case, calculations)
    issues.extend(narrative_issues)
    from planning_assessment import review_assessment

    issues.extend(review_assessment(case, accepted))
    if "business_analysis" in case["required_sections"] and not accepted:
        issues.append("Required reviewed business analysis is missing")
    if issues:
        if any(n["kind"] == "capital_recommendation" for n in accepted):
            issues.append(
                "Capital recommendation withheld until all material inputs, assumptions and conflicts are accepted"
            )
        accepted = [n for n in accepted if n["kind"] != "capital_recommendation"]
    status = "partial" if issues else "ready_for_professional_review"
    if any("disagrees" in i or "reconciliation failed" in i for i in issues):
        status = "blocked"
    plan = {
        "schema_version": "mparanza.business_planning_plan.v3",
        "workflow_id": "business-planning",
        "case_sha256": digest(case),
        "case": deepcopy(case),
        "status": status,
        "unresolved_matters": issues,
        "statements": statements,
        "calculations": calculations,
        "comparisons": comparisons,
        "accepted_narrative": accepted,
        "limitations": [
            *case["limitations"],
            "Monthly period-end cash cannot establish an intramonth liquidity minimum.",
            "Cash interest and tax are paid in the modeled period; deferred tax, leases and disposals are unsupported.",
            "Revenue break-even assumes the reviewed variable/fixed cost split remains valid.",
            "Funding requirement is the modeled pre-financing cash gap, not a recommended capital structure or contingency buffer.",
            "DSCR uses disclosed CFADS; lender covenant definitions may differ.",
            "Mechanical readiness is not an assessment of viability, market attractiveness or financeability.",
        ],
    }
    plan["calculations_sha256"] = digest(calculations)
    from planning_assessment import select_charts
    from planning_report import build_charts

    plan["charts"] = select_charts(plan, build_charts(plan))
    from planning_presentation import validate_presentation

    validate_presentation(plan)
    if plan["unresolved_matters"] and plan["status"] == "ready_for_professional_review":
        plan["status"] = "partial"
    plan["content_sha256"] = digest(plan)
    return plan


def validate_plan(plan: dict[str, Any], *, source_root: Path) -> None:
    """Replay all arithmetic/lineage/review gates before export; distrust supplied outputs."""
    expected = build_plan(plan["case"], source_root=source_root)
    require(
        plan == expected,
        "Report, calculations, IDs, hashes, or chart data differ from canonical replay",
    )
