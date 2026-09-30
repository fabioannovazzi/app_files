"""Exact P1 workpapers on model-selected, evidenced inputs.

Arithmetic, references and dates have mechanically checkable contracts. Source
relevance, branch selection, valuation, accounting policy and legal applicability
remain the model/professional's explicit decisions, never inferred by this code.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

from fusione_model import CaseError, decimal_string, fraction_string, identifier, text

__all__ = ["derive", "selected_references", "BRANCHES", "ASSUMPTIONS"]
BRANCHES = {"ordinary_domestic_oic", "wholly_owned_domestic_oic"}
ASSUMPTIONS = {
    "domestic_oic",
    "incorporation",
    "homogeneous_rights",
    "no_cash_adjustment",
    "no_own_or_reciprocal_holdings",
    "no_mlbo",
    "no_special_regulated_or_crisis_case",
}
REF_KEYS = {"operation_id", "id", "version", "sha256"}


def selected_references(value: Any) -> dict[str, dict[str, Any]]:
    """Collect exact references already selected in the request, not semantic dependencies."""
    found: dict[str, dict[str, Any]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if set(node) == REF_KEYS:
                key = identifier(node["id"])
                if key in found and found[key] != node:
                    raise CaseError(
                        "One workpaper cannot mix revisions of the same input."
                    )
                found[key] = node
            else:
                for child in node.values():
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return found


def shape(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CaseError(f"{label} requires exactly: {', '.join(sorted(keys))}.")
    return value


def fraction(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def money(value: Fraction) -> str:
    """Serialize terminating exact values without Decimal context rounding."""
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise CaseError(
            "Non-terminating monetary amount requires a reviewed rounding allocation."
        )
    places = max(2, twos, fives)
    scaled = value.numerator * (10**places // value.denominator)
    absolute = str(abs(scaled)).zfill(places + 1)
    return ("-" if scaled < 0 else "") + absolute[:-places] + "." + absolute[-places:]


class Inputs:
    """Resolve only the exact already-authorized records supplied by the transaction."""

    def __init__(self, records: dict[str, dict[str, Any]]):
        self.records = records

    def record(self, ref: Any, kind: str) -> dict[str, Any]:
        shape(ref, REF_KEYS, "reference")
        row = self.records[ref["id"]]
        if row["kind"] != kind or any(row[key] != ref[key] for key in REF_KEYS):
            raise CaseError(f"Expected exact {kind} reference.")
        return row

    def fact(self, ref: Any, value_kind: str) -> Any:
        row = self.record(ref, "Fact")["data"]
        if row["fact_status"] != "known" or row["value_kind"] != value_kind:
            raise CaseError(f"A known {value_kind} fact is required.")
        return row["value"]

    def number(self, ref: Any, *, positive: bool = False) -> Fraction:
        value = Fraction(decimal_string(self.fact(ref, "decimal")))
        if positive and value <= 0:
            raise CaseError("A strictly positive input is required.")
        return value

    def result(self, ref: Any, kind: str) -> dict[str, Any]:
        data = self.record(ref, kind)["data"]
        if (
            data.get("engine_version") != "fusione.p1.v1"
            or data["result"] is None
            or data["issues"]
        ):
            raise CaseError("Resolve the prerequisite P1 workpaper first.")
        return data["result"]

    def plan(self, ref: Any) -> dict[str, Any]:
        return self.result(ref, "BranchDecision")

    def rules(self, refs: Any) -> None:
        if not isinstance(refs, list) or not refs:
            raise CaseError("Select at least one exact source-backed rule.")
        for ref in refs:
            self.record(ref, "RuleVersion")


def branch(request: dict[str, Any], source: Inputs) -> tuple[dict[str, Any], list[str]]:
    shape(
        request,
        {
            "branch",
            "acquirer",
            "target",
            "assumptions",
            "ownership",
            "ownership_edge",
            "rationale",
            "rules",
        },
        "branch request",
    )
    if request["branch"] not in BRANCHES:
        return {"branch": request["branch"], "support_status": "unsupported"}, [
            "unsupported_branch"
        ]
    a = source.record(request["acquirer"], "Entity")
    b = source.record(request["target"], "Entity")
    if a["id"] == b["id"]:
        raise CaseError("Select two distinct companies.")
    shape(request["assumptions"], ASSUMPTIONS, "explicit P1 scope assumptions")
    issues = [
        name
        for name, ref in request["assumptions"].items()
        if source.fact(ref, "boolean") is not True
    ]
    # This verifies declared scope codes; it does not classify an entity from its name.
    if any(
        r["data"]["residence"] != "IT" or r["data"]["accounting_framework"] != "OIC"
        for r in (a, b)
    ):
        issues.append("company_scope_requires_review")
    owned = fraction_string(source.fact(request["ownership"], "fraction"))
    expected = 0 if request["branch"] == "ordinary_domestic_oic" else 1
    if owned != expected:
        issues.append("ownership_outside_selected_branch")
    if expected == 1:
        edge = source.record(request["ownership_edge"], "OwnershipEdge")["data"]
        if (
            edge["holder"] != a["id"]
            or edge["company"] != b["id"]
            or fraction_string(edge["ratio"]) != 1
        ):
            issues.append("direct_ownership_not_demonstrated")
    elif request["ownership_edge"] is not None:
        raise CaseError("The independent branch has no direct ownership edge.")
    source.rules(request["rules"])
    return {
        "branch": request["branch"],
        "acquirer": a["id"],
        "target": b["id"],
        "ownership": fraction(owned),
        "rationale": source.fact(request["rationale"], "text"),
        "support_status": "p1_workpapers",
        "legal_execution": "not_authorized",
    }, issues


def valuation(
    request: dict[str, Any], source: Inputs
) -> tuple[dict[str, Any], list[str]]:
    shape(
        request,
        {
            "plan",
            "company",
            "basis",
            "value",
            "debt",
            "cash",
            "adjustments",
            "method",
            "valuation_date",
        },
        "valuation request",
    )
    plan = source.plan(request["plan"])
    company = source.record(request["company"], "Entity")["id"]
    if company not in {plan["acquirer"], plan["target"]}:
        raise CaseError("Valuation company is outside this plan.")
    base = source.number(request["value"], positive=True)
    if request["basis"] == "equity":
        if any(request[key] is not None for key in ("debt", "cash", "adjustments")):
            raise CaseError("An equity value cannot also include an enterprise bridge.")
        debt = cash = adjustments = Fraction(0)
    elif request["basis"] == "enterprise":
        debt, cash, adjustments = (
            source.number(request[k]) for k in ("debt", "cash", "adjustments")
        )
        if debt < 0 or cash < 0:
            raise CaseError(
                "Debt and cash must be non-negative; adjustments are signed."
            )
    else:
        raise CaseError("Choose equity or enterprise explicitly.")
    equity = base - debt + cash + adjustments
    return {
        "plan": request["plan"],
        "company": company,
        "basis": request["basis"],
        "base": money(base),
        "debt": money(debt),
        "cash": money(cash),
        "adjustments": money(adjustments),
        "equity": money(equity),
        "method": source.fact(request["method"], "text"),
        "valuation_date": source.fact(request["valuation_date"], "date"),
        "congruity": "requires_professional_review",
    }, ([] if equity > 0 else ["nonpositive_equity"])


def shareholders(
    rows: Any, source: Inputs, total: Fraction, unit_type: str
) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise CaseError("An explicit shareholder allocation is required.")
    result = []
    ids = set()
    for row in rows:
        shape(row, {"id", "name", "units"}, "shareholder")
        key = identifier(row["id"])
        if key in ids:
            raise CaseError("Duplicate shareholder ID.")
        ids.add(key)
        units = source.number(row["units"], positive=True)
        if unit_type == "shares" and units.denominator != 1:
            raise CaseError("Share counts must be integers.")
        result.append(
            {
                "id": key,
                "name": source.fact(row["name"], "text"),
                "units": fraction(units),
            }
        )
    if sum((Fraction(r["units"]) for r in result), Fraction(0)) != total:
        raise CaseError("Shareholder units do not reconcile to the declared total.")
    return result


def exchange(
    request: dict[str, Any], source: Inputs
) -> tuple[dict[str, Any], list[str]]:
    shape(
        request,
        {
            "plan",
            "valuation_a",
            "valuation_b",
            "units_a",
            "units_b",
            "nominal",
            "unit_type",
            "shareholders_a",
            "shareholders_b",
            "allocation_policy",
        },
        "exchange request",
    )
    plan = source.plan(request["plan"])
    unit_type = request["unit_type"]
    if unit_type not in {"shares", "capital_units"}:
        raise CaseError("Distinguish shares from explicitly defined capital units.")
    na = source.number(request["units_a"], positive=True)
    nominal = source.number(request["nominal"], positive=True)
    owners_a = shareholders(request["shareholders_a"], source, na, unit_type)
    wholly = plan["branch"] == "wholly_owned_domestic_oic"
    owners_b: list[dict[str, Any]] = []
    ratio = new = Fraction(0)
    if wholly:
        if (
            any(
                request[k] is not None
                for k in ("valuation_a", "valuation_b", "units_b")
            )
            or request["shareholders_b"] != []
        ):
            raise CaseError(
                "Wholly owned incorporation issues no replacement units to the acquirer."
            )
    else:
        va, vb = (
            source.result(request[key], "Valuation")
            for key in ("valuation_a", "valuation_b")
        )
        if (
            va["company"] != plan["acquirer"]
            or vb["company"] != plan["target"]
            or any(v["plan"] != request["plan"] for v in (va, vb))
        ):
            raise CaseError("Valuations do not match the selected companies and plan.")
        if va["valuation_date"] != vb["valuation_date"]:
            raise CaseError("Align valuation dates before computing exchange ratios.")
        nb = source.number(request["units_b"], positive=True)
        owners_b = shareholders(request["shareholders_b"], source, nb, unit_type)
        ea, eb = Fraction(va["equity"]), Fraction(vb["equity"])
        ratio = (eb / nb) / (ea / na)
        new = na * eb / ea
    total = na + new
    allocations = []
    issues = []
    for company, owners, multiplier in (
        (plan["acquirer"], owners_a, Fraction(1)),
        (plan["target"], owners_b, ratio),
    ):
        for owner in owners:
            units = Fraction(owner["units"]) * multiplier
            if unit_type == "shares" and units.denominator != 1:
                issues.append("fractional_shares_require_dedicated_allocation")
            allocations.append(
                {
                    **owner,
                    "company": company,
                    "resulting_units": fraction(units),
                    "resulting_fraction": fraction(units / total),
                    "fractional_remainder": fraction(
                        units - units.numerator // units.denominator
                    ),
                }
            )
    return {
        "plan": request["plan"],
        "branch": plan["branch"],
        "unit_type": unit_type,
        "exchange_ratio": None if wholly else fraction(ratio),
        "new_units": fraction(new),
        "total_units": fraction(total),
        "capital_increase_exact": fraction(new * nominal),
        "allocations": allocations,
        "allocation_policy": source.fact(request["allocation_policy"], "text"),
        "rounding": "none; exact fractions retained",
        "congruity": "not_certified",
    }, sorted(set(issues))


def balance_rows(
    rows: Any, source: Inputs, *, prefix: str
) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise CaseError("Supply explicit reviewed balance rows.")
    result = {}
    for row in rows:
        shape(row, {"id", "label", "category", "balance"}, "balance row")
        key = identifier(row["id"])
        if key in result or row["category"] not in {"asset", "liability", "equity"}:
            raise CaseError("Duplicate account or unsupported balance category.")
        text(row["label"], "account label")
        result[key] = {
            "id": f"{prefix}_{key}",
            "label": row["label"],
            "category": row["category"],
            "balance": source.number(row["balance"]),
        }
    return result


def bridge(request: dict[str, Any], source: Inputs) -> tuple[dict[str, Any], list[str]]:
    shape(
        request,
        {
            "plan",
            "exchange",
            "balances_a",
            "balances_b",
            "date_a",
            "date_b",
            "investment_account",
            "eliminations",
            "difference_allocations",
            "accounting_policy",
            "tax_register",
        },
        "accounting bridge",
    )
    plan = source.plan(request["plan"])
    ex = source.result(request["exchange"], "ExchangeModel")
    if ex["plan"] != request["plan"]:
        raise CaseError("Exchange model belongs to another plan revision.")
    dates = [source.fact(request[k], "date") for k in ("date_a", "date_b")]
    if dates[0] != dates[1]:
        raise CaseError("Align the reviewed balance dates before consolidation.")
    a, b = (
        balance_rows(request[k], source, prefix=p)
        for k, p in (("balances_a", "a"), ("balances_b", "b"))
    )
    issues = []
    for name, rows in (("acquirer", a), ("target", b)):
        if sum((r["balance"] for r in rows.values()), Fraction(0)) != 0:
            issues.append(f"unbalanced_{name}_trial_balance")
    net_b = -sum(
        (r["balance"] for r in b.values() if r["category"] == "equity"), Fraction(0)
    )
    if net_b <= 0:
        issues.append("nonpositive_target_net_assets_require_dedicated_review")
    opening = {r["id"]: dict(r) for r in a.values()}
    opening.update({r["id"]: dict(r) for r in b.values() if r["category"] != "equity"})
    journal = []
    eliminated = set()
    if not isinstance(request["eliminations"], list):
        raise CaseError("Eliminations must be an explicit list.")
    for pair in request["eliminations"]:
        shape(pair, {"a", "b", "eligible"}, "elimination pair")
        if pair["a"] not in a or pair["b"] not in b:
            raise CaseError("Elimination account is absent from the reviewed balances.")
        ra, rb = a[pair["a"]], b[pair["b"]]
        if (
            {ra["category"], rb["category"]} != {"asset", "liability"}
            or ra["id"] in eliminated
            or rb["id"] in eliminated
        ):
            raise CaseError(
                "Eliminate each selected asset/liability pair at most once."
            )
        eliminated.update((ra["id"], rb["id"]))
        difference = ra["balance"] + rb["balance"]
        if not source.fact(pair["eligible"], "boolean") or difference != 0:
            issues.append(
                f"unresolved_intercompany:{pair['a']}:{pair['b']}:{money(difference)}"
            )
            continue
        for row in (ra, rb):
            journal.append(
                {
                    "account": row["id"],
                    "signed_debit": money(-row["balance"]),
                    "reason": "reviewed reciprocal balance elimination",
                }
            )
            opening[row["id"]]["balance"] = Fraction(0)
    increase = Fraction(ex["capital_increase_exact"])
    if plan["branch"] == "wholly_owned_domestic_oic":
        if request["investment_account"] not in a:
            raise CaseError(
                "Participation account is absent from the acquirer balances."
            )
        investment = a[request["investment_account"]]
        if (
            investment["category"] != "asset"
            or investment["balance"] < 0
            or investment["id"] in eliminated
        ):
            raise CaseError("Select a non-negative, uneliminated participation asset.")
        consideration = investment["balance"]
        opening[investment["id"]]["balance"] = Fraction(0)
        journal.append(
            {
                "account": investment["id"],
                "signed_debit": money(-consideration),
                "reason": "participation cancellation",
            }
        )
        difference_type = "annullamento"
    else:
        if request["investment_account"] is not None:
            raise CaseError(
                "Independent-company exchange has no participation cancellation."
            )
        consideration = increase
        opening["new_capital"] = {
            "id": "new_capital",
            "label": "Aumento capitale",
            "category": "equity",
            "balance": -increase,
        }
        journal.append(
            {
                "account": "new_capital",
                "signed_debit": money(-increase),
                "reason": "new capital for target shareholders",
            }
        )
        difference_type = "concambio"
    difference = consideration - net_b
    allocations = request["difference_allocations"]
    if not isinstance(allocations, list):
        raise CaseError("Difference allocations must be explicit.")
    if allocations:
        postings = balance_rows(allocations, source, prefix="allocation")
        if sum((r["balance"] for r in postings.values()), Fraction(0)) != difference:
            issues.append("difference_allocation_does_not_reconcile")
        opening.update({r["id"]: r for r in postings.values()})
    elif difference:
        opening["difference_pending"] = {
            "id": "difference_pending",
            "label": "Differenza da analizzare; non un attivo o una riserva approvati",
            "category": "unallocated",
            "balance": difference,
        }
        issues.append("difference_allocation_requires_professional_policy")
    fiscal = []
    fiscal_ids = set()
    if not isinstance(request["tax_register"], list):
        raise CaseError(
            "Tax registers must be explicit, including an empty reviewed list."
        )
    for row in request["tax_register"]:
        shape(
            row,
            {"id", "owner", "category", "book", "tax", "assessment"},
            "fiscal position",
        )
        if row["id"] in fiscal_ids:
            raise CaseError("Fiscal register IDs must be unique.")
        fiscal_ids.add(identifier(row["id"]))
        if row["category"] not in {
            "asset",
            "liability",
            "shareholder_cost",
            "reserve",
            "loss",
        }:
            raise CaseError("Unknown fiscal register category.")
        fiscal.append(
            {
                "id": identifier(row["id"]),
                "owner": source.fact(row["owner"], "text"),
                "category": row["category"],
                "book": money(source.number(row["book"])),
                "tax": money(source.number(row["tax"])),
                "assessment": source.fact(row["assessment"], "text"),
                "tax_treatment": "professionally_supplied; not computed",
            }
        )
    # The acquirer's existing ledger plus this complete journal must equal the
    # proposed opening ledger. No entries are posted to any accounting system.
    opening_journal = [
        {
            "account": r["id"],
            "signed_debit": money(r["balance"]),
            "reason": "target asset/liability assumption",
        }
        for r in b.values()
        if r["category"] != "equity"
    ]
    opening_journal.extend(journal)
    opening_journal.extend(
        {
            "account": r["id"],
            "signed_debit": money(r["balance"]),
            "reason": (
                "reviewed difference allocation"
                if r["category"] != "unallocated"
                else "unresolved difference; not approved"
            ),
        }
        for r in opening.values()
        if r["id"].startswith("allocation_") or r["id"] == "difference_pending"
    )
    journal_residual = sum(
        (Fraction(r["signed_debit"]) for r in opening_journal), Fraction(0)
    )
    if journal_residual:
        issues.append("opening_journal_does_not_reconcile")
    balances = [{**row, "balance": money(row["balance"])} for row in opening.values()]
    residual = sum((row["balance"] for row in opening.values()), Fraction(0))
    if residual:
        issues.append("opening_balance_does_not_reconcile")
    return {
        "plan": request["plan"],
        "balance_date": dates[0],
        "target_net_assets": money(net_b),
        "difference_type": difference_type,
        "difference_signed_debit": money(difference),
        "difference_nature": (
            "disavanzo" if difference > 0 else "avanzo" if difference < 0 else "none"
        ),
        "opening_balances": balances,
        "elimination_journal": journal,
        "opening_residual": money(residual),
        "opening_journal": opening_journal,
        "journal_residual": money(journal_residual),
        "accounting_policy": source.fact(request["accounting_policy"], "text"),
        "tax_register": fiscal,
        "automatic_goodwill": False,
        "posting_status": "draft_not_posted",
    }, sorted(set(issues))


def offset_day(anchor: date, count: int, unit: str) -> date:
    if type(count) is not int or abs(count) > 1200:
        raise CaseError("Use an explicit integer offset within 1200 units.")
    if unit == "days":
        return anchor + timedelta(days=count)
    if unit != "months":
        raise CaseError("Calendar units must be days or months.")
    year, month = divmod(anchor.year * 12 + anchor.month - 1 + count, 12)
    return date(year, month + 1, min(anchor.day, monthrange(year, month + 1)[1]))


def calendar(
    request: dict[str, Any], source: Inputs
) -> tuple[dict[str, Any], list[str]]:
    shape(request, {"plan", "events", "computation_policy"}, "calendar request")
    source.plan(request["plan"])
    if not isinstance(request["events"], list) or not request["events"]:
        raise CaseError("Select at least one reviewed calendar event.")
    result = []
    issues = []
    ids = set()
    for row in request["events"]:
        shape(
            row,
            {
                "id",
                "label",
                "anchors",
                "count",
                "unit",
                "rule",
                "owner",
                "actual",
                "constraint",
                "adjusted_boundary",
                "adjustment_reason",
            },
            "calendar event",
        )
        key = identifier(row["id"])
        if key in ids:
            raise CaseError("Calendar event IDs must be unique.")
        ids.add(key)
        text(row["label"], "event label")
        source.record(row["rule"], "RuleVersion")
        if not isinstance(row["anchors"], list) or not row["anchors"]:
            raise CaseError("Select all relevant dated event facts.")
        anchors = [
            date.fromisoformat(source.fact(ref, "date")) for ref in row["anchors"]
        ]
        anchor = max(anchors)
        computed = offset_day(anchor, row["count"], row["unit"])
        boundary = computed
        reason = None
        if row["adjusted_boundary"] is not None:
            boundary = date.fromisoformat(source.fact(row["adjusted_boundary"], "date"))
            reason = source.fact(row["adjustment_reason"], "text")
        elif row["adjustment_reason"] is not None:
            raise CaseError("An adjustment reason requires its reviewed boundary.")
        if row["constraint"] not in {"not_before", "not_after"}:
            raise CaseError(
                "Specify whether this event is an earliest or latest boundary."
            )
        actual = (
            source.fact(row["actual"], "date") if row["actual"] is not None else None
        )
        check = "not_evidenced"
        if actual is not None:
            actual_day = date.fromisoformat(actual)
            passes = (
                actual_day >= boundary
                if row["constraint"] == "not_before"
                else actual_day <= boundary
            )
            check = (
                "within_reviewed_boundary" if passes else "outside_reviewed_boundary"
            )
            if not passes:
                issues.append(f"calendar_violation:{key}")
        result.append(
            {
                "id": key,
                "label": row["label"],
                "anchor": anchor.isoformat(),
                "count": row["count"],
                "unit": row["unit"],
                "computed_boundary": computed.isoformat(),
                "reviewed_boundary": boundary.isoformat(),
                "adjustment_reason": reason,
                "constraint": row["constraint"],
                "actual": actual,
                "check": check,
                "rule": row["rule"],
                "owner": source.fact(row["owner"], "text"),
            }
        )
    return {
        "plan": request["plan"],
        "events": result,
        "computation_policy": source.fact(request["computation_policy"], "text"),
        "convention": "anchor day excluded for positive day offsets; calendar months clamp to last valid day; no automatic holiday or waiver inference",
        "execution_permission": "not_determined_by_calendar",
    }, issues


SECTIONS = {
    "mandate",
    "objectives",
    "due_diligence",
    "feasibility",
    "articles",
    "profit_participation",
    "accounting_effective_date",
    "special_rights",
    "management_advantages",
    "tax_review",
    "execution_checklist",
    "cutover",
    "post_merger_checks",
}


def document(
    request: dict[str, Any], source: Inputs
) -> tuple[dict[str, Any], list[str]]:
    shape(
        request,
        {"plan", "exchange", "bridge", "calendar", "sections", "title"},
        "review dossier",
    )
    plan = source.plan(request["plan"])
    papers = {
        kind: source.result(request[key], kind)
        for key, kind in (
            ("exchange", "ExchangeModel"),
            ("bridge", "BookBridge"),
            ("calendar", "Deadline"),
        )
    }
    if any(row["plan"] != request["plan"] for row in papers.values()):
        raise CaseError("Dossier inputs must use the exact same plan revision.")
    if (
        source.record(request["bridge"], "BookBridge")["data"]["request"]["exchange"]
        != request["exchange"]
    ):
        raise CaseError("Dossier exchange differs from the accounting bridge input.")
    shape(request["sections"], SECTIONS, "model-authored dossier sections")
    text(request["title"], "dossier title")
    sections = {
        name: source.fact(ref, "text") for name, ref in request["sections"].items()
    }
    return {
        "plan": request["plan"],
        "title": request["title"],
        "branch": plan["branch"],
        "companies": [plan["acquirer"], plan["target"]],
        "sections": sections,
        "workpapers": papers,
        "document_status": "draft_for_professional_and_notarial_review",
        "signature": "not_performed",
        "filing": "not_performed",
        "legal_effect": "not_verified",
        "professional_acceptance": "not_established_by_software_tests",
    }, []


def derive(
    kind: str, request: dict[str, Any], records: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """Compute one selected workpaper; no approval or legal branch is inferred."""
    handlers = {
        "BranchDecision": branch,
        "Valuation": valuation,
        "ExchangeModel": exchange,
        "BookBridge": bridge,
        "Deadline": calendar,
        "LegalDocument": document,
    }
    if kind not in handlers:
        raise CaseError("Unsupported workpaper kind.")
    return handlers[kind](request, Inputs(records))
