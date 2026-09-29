"""Auditable Decimal formulas; selection and economic judgment stay with people.

Fixed arithmetic supports reproducible calculation and workbook replay.
The register is a small expression tree, never executable source or Python eval.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

__all__ = ["ValuationError", "decimal", "calculate_method", "evaluate", "METHODS"]

METHODS = {
    "DCF_FCFF",
    "DCF_FCFE",
    "INCOME_EQUITY",
    "INCOME_EQUITY_FINITE",
    "RESIDUAL_INCOME_EQUITY",
    "HOLDING_SOTP",
    "NAV",
    "MIXED_EQUITY",
    "MULTIPLE",
    "APV",
}


class ValuationError(ValueError):
    """A calculation cannot satisfy its declared contract."""


def decimal(value: Any) -> Decimal:
    """Require finite, bounded decimal text; absent is never zero."""
    if (
        not isinstance(value, str)
        or len(value) > 80
        or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value)
    ):
        raise ValuationError("Expected finite canonical decimal text")
    return Decimal(value)


def evaluate(op: str, values: list[Decimal]) -> Decimal:
    """Evaluate only the small supported arithmetic vocabulary."""
    with localcontext() as ctx:
        ctx.prec = 40
        if op == "sum":
            return sum(values, Decimal(0))
        if op == "exp":
            if len(values) != 1 or abs(values[0]) > 100:
                raise ValuationError(
                    "Exponential exceeds the supported numeric range [-100, 100]"
                )
            return values[0].exp()
        if len(values) != 2:
            raise ValuationError("Binary operation needs two operands")
        left, right = values
        if op == "subtract":
            return left - right
        if op == "multiply":
            return left * right
        if op == "divide" and right != 0:
            return left / right
        if op == "power" and left > 0:
            return left**right
    raise ValuationError("Invalid arithmetic operation or denominator")


class Ledger:
    """Keep every formula, exact value and transitive input reference together."""

    def __init__(self, method_id: str, inputs: dict[str, dict], currency: str):
        self.prefix = method_id
        self.inputs = inputs
        self.currency = currency
        self.rows: dict[str, dict] = {}

    def input(self, ref: Any, unit: str) -> str:
        if not isinstance(ref, str) or ref not in self.inputs:
            raise ValuationError(f"Unknown input reference: {ref}")
        record = self.inputs[ref]
        if record["unit"] != unit:
            raise ValuationError(f"Incompatible unit for {ref}: expected {unit}")
        if record["value"] is None:
            raise ValuationError(f"Missing input: {ref}")
        value = decimal(record["value"])
        identifier = f"{self.prefix}/input/{ref}"
        self.rows[identifier] = {
            "id": identifier,
            "value": format(value, "f"),
            "unit": unit,
            "op": "input",
            "arguments": [],
            "input_ids": [ref],
        }
        return identifier

    def constant(self, name: str, value: int) -> str:
        identifier = f"{self.prefix}/constant/{name}"
        self.rows[identifier] = {
            "id": identifier,
            "value": str(value),
            "unit": "scalar",
            "op": "constant",
            "arguments": [],
            "input_ids": [],
        }
        return identifier

    def value(self, ref: str) -> Decimal:
        return decimal(self.rows[ref]["value"])

    def add(self, name: str, op: str, args: list[str], unit: str | None = None) -> str:
        identifier = f"{self.prefix}/{name}"
        if identifier in self.rows:
            raise ValuationError("Duplicate calculation ID")
        value = evaluate(op, [self.value(ref) for ref in args])
        self.rows[identifier] = {
            "id": identifier,
            "value": format(value, "f"),
            "unit": unit or self.currency,
            "op": op,
            "arguments": args,
            "input_ids": sorted(
                {item for ref in args for item in self.rows[ref]["input_ids"]}
            ),
        }
        return identifier


def _keys(args: dict, required: set[str], optional: set[str] | None = None) -> None:
    if (
        not isinstance(args, dict)
        or set(args) - required - (optional or set())
        or required - set(args)
    ):
        raise ValuationError(f"Expected method inputs: {sorted(required)}")


def _date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValuationError("Timing dates require YYYY-MM-DD text")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValuationError("Invalid timing date") from exc
    if result.isoformat() != value or result.year == 9999:
        raise ValuationError("Timing dates require canonical dates before year 9999")
    return result


def _year_fraction(
    ledger: Ledger, name: str, start: date, end: date, basis: str
) -> str:
    """Expose actual days and denominators as replayable integer arithmetic."""
    parts = []
    cursor = start
    while cursor < end:
        stop = end if basis == "ACT/365F" else min(end, date(cursor.year + 1, 1, 1))
        denominator = (
            365 if basis == "ACT/365F" else 366 if calendar.isleap(cursor.year) else 365
        )
        part = len(parts)
        parts.append(
            ledger.add(
                f"{name}/part-{part}",
                "divide",
                [
                    ledger.constant(f"{name}/days-{part}", (stop - cursor).days),
                    ledger.constant(f"{name}/year-{part}", denominator),
                ],
                "years",
            )
        )
        cursor = stop
    return ledger.add(name, "sum", parts, "years")


def _dated_factors(
    ledger: Ledger,
    timing: dict,
    count: int,
    *,
    terminal_convention: str = "annual_end_period_perpetuity_at_horizon",
) -> tuple[list[str], str, dict]:
    """Discount explicit dated flows; never infer a curve or prorate amounts."""
    _keys(
        timing,
        {
            "valuation_date",
            "period_end_dates",
            "cash_flow_timing",
            "day_count",
            "rate_compounding",
            "rate_model",
            "rate_ids",
            "rationale",
        },
        {"terminal_discount_rate"},
    )
    valuation_date = _date(timing["valuation_date"])
    ends = timing["period_end_dates"]
    if not isinstance(ends, list) or len(ends) != count:
        raise ValuationError("Provide one end date per explicit cash flow")
    dates = [_date(value) for value in ends]
    if any(right <= left for left, right in zip([valuation_date, *dates], dates)):
        raise ValuationError("Cash-flow periods must increase after the valuation date")
    if (dates[-1] - valuation_date).days > 36600:
        raise ValuationError(
            "Dated calculation horizon exceeds the supported 36600-day bound"
        )
    basis, convention = timing["day_count"], timing["cash_flow_timing"]
    if not all(
        isinstance(timing[key], str)
        for key in ("day_count", "cash_flow_timing", "rate_compounding", "rate_model")
    ):
        raise ValuationError("Timing conventions require explicit text identifiers")
    if basis not in {"ACT/365F", "ACT/ACT_ISDA"}:
        raise ValuationError("Choose ACT/365F or ACT/ACT_ISDA explicitly")
    if convention not in {"end_period", "mid_period"}:
        raise ValuationError("Choose end_period or mid_period explicitly")
    if timing["rate_compounding"] not in {"effective_annual", "continuous"}:
        raise ValuationError("Unsupported discount-rate compounding")
    model, rates = timing["rate_model"], timing["rate_ids"]
    if model not in {"flat", "spot_curve", "forward_curve"}:
        raise ValuationError("Choose flat, spot_curve or forward_curve explicitly")
    if not isinstance(rates, list) or len(rates) != (1 if model == "flat" else count):
        raise ValuationError("Rate IDs must match the selected flat or curve model")
    if (model == "spot_curve") != ("terminal_discount_rate" in timing):
        raise ValuationError(
            "Only a spot curve requires a separate horizon discount rate"
        )
    if (
        not isinstance(timing["rationale"], str)
        or not timing["rationale"].strip()
        or len(timing["rationale"]) > 20000
    ):
        raise ValuationError("Explain the cash timing, day count and rate model")

    one = ledger.constant("timing/one", 1)
    two = ledger.constant("timing/two", 2)

    def factor(name: str, rate_id: Any, years: str) -> str:
        rate = ledger.input(rate_id, "ratio")
        if timing["rate_compounding"] == "continuous":
            exponent = ledger.add(
                f"{name}/exponent", "multiply", [rate, years], "ratio"
            )
            return ledger.add(name, "exp", [exponent], "ratio")
        if ledger.value(rate) <= -1:
            raise ValuationError("Effective annual discount rates must exceed -1")
        base = ledger.add(f"{name}/base", "sum", [one, rate], "ratio")
        return ledger.add(name, "power", [base, years], "ratio")

    factors, schedule = [], []
    previous = valuation_date
    previous_time = ledger.constant("timing/zero", 0)
    accumulated = one
    for index, end in enumerate(dates, 1):
        end_time = _year_fraction(
            ledger, f"time/{index}/end", valuation_date, end, basis
        )
        duration = ledger.add(
            f"time/{index}/duration", "subtract", [end_time, previous_time], "years"
        )
        cash_time = end_time
        cash_duration = duration
        if convention == "mid_period":
            total = ledger.add(
                f"time/{index}/sum", "sum", [previous_time, end_time], "years"
            )
            cash_time = ledger.add(
                f"time/{index}/cash", "divide", [total, two], "years"
            )
            cash_duration = ledger.add(
                f"time/{index}/half", "divide", [duration, two], "years"
            )
        rate_id = rates[0] if model == "flat" else rates[index - 1]
        if model == "forward_curve":
            current = factor(f"discount/{index}/cash-period", rate_id, cash_duration)
            cash_factor = ledger.add(
                f"discount/{index}", "multiply", [accumulated, current], "ratio"
            )
            full = factor(f"discount/{index}/full-period", rate_id, duration)
            accumulated = ledger.add(
                f"discount/{index}/accumulated",
                "multiply",
                [accumulated, full],
                "ratio",
            )
        else:
            cash_factor = factor(f"discount/{index}", rate_id, cash_time)
        factors.append(cash_factor)
        schedule.append(
            {
                "start_date": previous.isoformat(),
                "end_date": end.isoformat(),
                "cash_time_id": cash_time,
                "discount_factor_id": cash_factor,
                "rate_id": rate_id,
            }
        )
        previous, previous_time = end, end_time
    horizon_factor = (
        accumulated
        if model == "forward_curve"
        else factor(
            "discount/terminal-horizon",
            timing["terminal_discount_rate"] if model == "spot_curve" else rates[0],
            previous_time,
        )
    )
    return (
        factors,
        horizon_factor,
        {
            "valuation_date": timing["valuation_date"],
            "day_count": basis,
            "cash_flow_timing": convention,
            "rate_compounding": timing["rate_compounding"],
            "rate_model": model,
            "rationale": timing["rationale"],
            "schedule": schedule,
            "terminal_time_id": previous_time,
            "terminal_discount_factor_id": horizon_factor,
            "terminal_value_convention": terminal_convention,
        },
    )


def calculate_method(method: dict, inputs: dict[str, dict], currency: str) -> dict:
    """Calculate one selected method, retaining equity versus enterprise basis."""
    kind = method["kind"]
    if kind not in METHODS:
        raise ValuationError("Unsupported valuation method")
    args = method["inputs"]
    ledger = Ledger(method["id"], inputs, currency)
    money = lambda ref: ledger.input(ref, currency)
    ratio = lambda ref: ledger.input(ref, "ratio")
    value_type = "equity"
    extras: dict[str, str] = {}
    timing_result = None
    residual_schedule = None
    holding_schedule = None
    if "timing" in method and kind not in {
        "DCF_FCFF",
        "DCF_FCFE",
        "INCOME_EQUITY_FINITE",
        "RESIDUAL_INCOME_EQUITY",
    }:
        raise ValuationError(
            "Explicit dated timing requires DCF, finite equity income or residual income"
        )

    def sequence(refs: Any, name: str, limit: int = 100) -> list[str]:
        if not isinstance(refs, list) or not 1 <= len(refs) <= limit:
            raise ValuationError(f"{name} requires 1..{limit} explicit amounts")
        return [money(ref) for ref in refs]

    def positive(ref: str) -> str:
        if ledger.value(ref) <= 0:
            raise ValuationError("Positive value required")
        return ref

    def nonnegative(ref: str) -> str:
        if ledger.value(ref) < 0:
            raise ValuationError("Nonnegative value required")
        return ref

    if kind in {"DCF_FCFF", "DCF_FCFE"}:
        dated = "timing" in method
        _keys(
            args,
            {"flows", "terminal_next_flow", "terminal_growth"}
            | ({"terminal_rate"} if dated else {"discount_rate"}),
            set() if dated else {"terminal_rate"},
        )
        flows = sequence(args["flows"], "DCF", 1200 if dated else 100)
        growth = ratio(args["terminal_growth"])
        terminal_rate = ratio(
            args["terminal_rate"] if "terminal_rate" in args else args["discount_rate"]
        )
        if ledger.value(growth) <= -1 or ledger.value(terminal_rate) <= ledger.value(
            growth
        ):
            raise ValuationError(
                "Require discount rate > -1 and terminal rate > growth > -1"
            )
        nxt = nonnegative(money(args["terminal_next_flow"]))
        if dated:
            factors, factor, timing_result = _dated_factors(
                ledger, method["timing"], len(flows)
            )
        else:
            rate = ratio(args["discount_rate"])
            if ledger.value(rate) <= -1:
                raise ValuationError("Discount rate must exceed -1")
            base = ledger.add(
                "discount_base", "sum", [ledger.constant("one", 1), rate], "ratio"
            )
            factors = [
                ledger.add(
                    f"discount/{t}",
                    "power",
                    [base, ledger.constant(f"year-{t}", t)],
                    "ratio",
                )
                for t in range(1, len(flows) + 1)
            ]
            factor = factors[-1]
        present = []
        for t, (flow, cash_factor) in enumerate(zip(flows, factors), 1):
            present.append(ledger.add(f"pv/{t}", "divide", [flow, cash_factor]))
        spread = ledger.add(
            "terminal_spread", "subtract", [terminal_rate, growth], "ratio"
        )
        terminal = ledger.add("terminal_value", "divide", [nxt, spread])
        terminal_pv = ledger.add("pv_terminal", "divide", [terminal, factor])
        result = ledger.add("value", "sum", [*present, terminal_pv])
        extras = {"terminal_value": terminal, "pv_terminal": terminal_pv}
        if ledger.value(result) != 0:
            extras["terminal_share"] = ledger.add(
                "terminal_share", "divide", [terminal_pv, result], "ratio"
            )
        value_type = "operating_enterprise" if kind == "DCF_FCFF" else "equity"
    elif kind == "INCOME_EQUITY_FINITE":
        _keys(args, {"incomes", "residual_value"})
        incomes = sequence(args["incomes"], "Finite equity incomes", 1200)
        if "timing" not in method:
            raise ValuationError("Finite equity income requires explicit dated timing")
        if args["residual_value"] in args["incomes"]:
            raise ValuationError(
                "Residual value requires an independent input, not a period income"
            )
        residual = money(args["residual_value"])
        factors, horizon, timing_result = _dated_factors(
            ledger,
            method["timing"],
            len(incomes),
            terminal_convention="explicit_equity_residual_at_horizon",
        )
        present = [
            ledger.add(f"pv/{t}", "divide", [income, factor])
            for t, (income, factor) in enumerate(zip(incomes, factors), 1)
        ]
        income_pv = ledger.add("income_pv", "sum", present)
        residual_pv = ledger.add("pv_residual", "divide", [residual, horizon])
        result = ledger.add("value", "sum", [income_pv, residual_pv])
        extras = {
            "income_pv": income_pv,
            "residual_value": residual,
            "pv_residual": residual_pv,
        }
        if ledger.value(result) != 0:
            extras["residual_share"] = ledger.add(
                "residual_share", "divide", [residual_pv, result], "ratio"
            )
    elif kind == "RESIDUAL_INCOME_EQUITY":
        from valuation_residual import residual_income

        _keys(
            args,
            {
                "book_equity",
                "incomes",
                "distributions",
                "contributions",
                "terminal_equity_value",
            },
        )
        incomes = sequence(args["incomes"], "Residual incomes", 1200)
        timing = method.get("timing")
        if not timing or timing["cash_flow_timing"] != "end_period":
            raise ValuationError("Residual income requires explicit end-period timing")
        if (
            timing["rate_model"] == "spot_curve"
            and timing.get("terminal_discount_rate") != timing["rate_ids"][-1]
        ):
            raise ValuationError(
                "Residual income requires the final spot rate at the horizon"
            )
        factors, horizon, timing_result = _dated_factors(
            ledger,
            timing,
            len(incomes),
            terminal_convention="terminal_equity_less_closing_book_equity",
        )
        result, extras, residual_schedule = residual_income(
            ledger, args, factors, horizon
        )
    elif kind == "HOLDING_SOTP":
        from valuation_holding import holding_sotp

        _keys(
            args,
            {
                "holdings",
                "parent_assets",
                "parent_liabilities",
                "holding_costs_pv",
                "tax_adjustment",
                "eliminations",
            },
        )
        result, extras, holding_schedule = holding_sotp(ledger, args)
    elif kind == "INCOME_EQUITY":
        _keys(args, {"normalized_equity_income", "cost_equity"})
        result = ledger.add(
            "value",
            "divide",
            [
                positive(money(args["normalized_equity_income"])),
                positive(ratio(args["cost_equity"])),
            ],
        )
    elif kind == "NAV":
        _keys(args, {"assets", "liabilities", "tax_adjustment"})
        assets = ledger.add("assets", "sum", sequence(args["assets"], "Assets"))
        if not isinstance(args["liabilities"], list) or len(args["liabilities"]) > 100:
            raise ValuationError("Liabilities require an explicit list")
        liabilities = ledger.add(
            "liabilities", "sum", [money(ref) for ref in args["liabilities"]]
        )
        net = ledger.add("net_assets", "subtract", [assets, liabilities])
        result = ledger.add("value", "subtract", [net, money(args["tax_adjustment"])])
    elif kind == "MIXED_EQUITY":
        _keys(args, {"adjusted_equity", "incomes", "normal_return", "excess_discount"})
        capital = money(args["adjusted_equity"])
        normal = nonnegative(ratio(args["normal_return"]))
        discount = ratio(args["excess_discount"])
        if ledger.value(discount) <= -1:
            raise ValuationError("Discount rate must exceed -1")
        base = ledger.add(
            "discount_base", "sum", [ledger.constant("one", 1), discount], "ratio"
        )
        normal_income = ledger.add("normal_income", "multiply", [capital, normal])
        present = []
        for t, income in enumerate(sequence(args["incomes"], "Incomes"), 1):
            excess = ledger.add(f"excess/{t}", "subtract", [income, normal_income])
            factor = ledger.add(
                f"discount/{t}",
                "power",
                [base, ledger.constant(f"year-{t}", t)],
                "ratio",
            )
            present.append(ledger.add(f"pv/{t}", "divide", [excess, factor]))
        result = ledger.add("value", "sum", [capital, *present])
    elif kind == "MULTIPLE":
        _keys(args, {"metric", "selected_multiple", "kind"})
        if args["kind"] not in {"EV_EBITDA", "EV_EBIT", "EV_REVENUE", "P_E"}:
            raise ValuationError("Unsupported multiple basis")
        result = ledger.add(
            "value",
            "multiply",
            [
                positive(money(args["metric"])),
                positive(ledger.input(args["selected_multiple"], "multiple")),
            ],
        )
        value_type = "equity" if args["kind"] == "P_E" else "operating_enterprise"
    else:
        _keys(args, {"unlevered_value", "pv_tax_shields", "pv_financing_costs"})
        gross = ledger.add(
            "gross",
            "sum",
            [
                money(args["unlevered_value"]),
                nonnegative(money(args["pv_tax_shields"])),
            ],
        )
        result = ledger.add(
            "value", "subtract", [gross, nonnegative(money(args["pv_financing_costs"]))]
        )
        value_type = "operating_enterprise"
    equity = result if value_type == "equity" else None
    if "bridge" in method:
        if value_type != "operating_enterprise":
            raise ValuationError(
                "Debt must not be deducted again from an equity-side result"
            )
        bridge = method["bridge"]
        _keys(
            bridge,
            {
                "financial_debt",
                "debt_like",
                "excess_cash",
                "non_operating_assets",
                "signed_adjustments",
            },
        )
        debt = ledger.add(
            "debt",
            "sum",
            [
                nonnegative(money(bridge["financial_debt"])),
                nonnegative(money(bridge["debt_like"])),
            ],
        )
        net = ledger.add("after_debt", "subtract", [result, debt])
        equity = ledger.add(
            "equity",
            "sum",
            [
                net,
                nonnegative(money(bridge["excess_cash"])),
                nonnegative(money(bridge["non_operating_assets"])),
                money(bridge["signed_adjustments"]),
            ],
        )
    output = {
        "method_id": method["id"],
        "kind": kind,
        "value_type": value_type,
        "value_id": result,
        "equity_id": equity,
        "detail_ids": extras,
        "convention": (
            "explicit_holding_parts"
            if holding_schedule is not None
            else (
                "explicit_dated_discount"
                if timing_result
                else "annual_end_year_constant_explicit_discount"
            )
        ),
        "timing": timing_result,
        "calculations": list(ledger.rows.values()),
    }
    if residual_schedule is not None:
        output["clean_surplus_schedule"] = residual_schedule
    if holding_schedule is not None:
        output["holding_schedule"] = holding_schedule
    return output
