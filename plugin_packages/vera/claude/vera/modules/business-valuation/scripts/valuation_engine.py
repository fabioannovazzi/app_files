"""Auditable Decimal formulas; selection and economic judgment stay with people.

Fixed arithmetic supports reproducible calculation and workbook replay.
The register is a small expression tree, never executable source or Python eval.
"""

from __future__ import annotations

import re
from decimal import Decimal, localcontext
from typing import Any

__all__ = ["ValuationError", "decimal", "calculate_method", "evaluate", "METHODS"]

METHODS = {
    "DCF_FCFF",
    "DCF_FCFE",
    "INCOME_EQUITY",
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

    def sequence(refs: Any, name: str) -> list[str]:
        if not isinstance(refs, list) or not 1 <= len(refs) <= 100:
            raise ValuationError(f"{name} requires 1..100 explicit amounts")
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
        _keys(
            args,
            {"flows", "discount_rate", "terminal_next_flow", "terminal_growth"},
            {"terminal_rate"},
        )
        flows = sequence(args["flows"], "DCF")
        rate = ratio(args["discount_rate"])
        growth = ratio(args["terminal_growth"])
        terminal_rate = ratio(args.get("terminal_rate", args["discount_rate"]))
        if (
            ledger.value(rate) <= -1
            or ledger.value(growth) <= -1
            or ledger.value(terminal_rate) <= ledger.value(growth)
        ):
            raise ValuationError(
                "Require discount rate > -1 and terminal rate > growth > -1"
            )
        nxt = nonnegative(money(args["terminal_next_flow"]))
        base = ledger.add(
            "discount_base", "sum", [ledger.constant("one", 1), rate], "ratio"
        )
        present = []
        factor = ""
        for t, flow in enumerate(flows, 1):
            factor = ledger.add(
                f"discount/{t}",
                "power",
                [base, ledger.constant(f"year-{t}", t)],
                "ratio",
            )
            present.append(ledger.add(f"pv/{t}", "divide", [flow, factor]))
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
    return {
        "method_id": method["id"],
        "kind": kind,
        "value_type": value_type,
        "value_id": result,
        "equity_id": equity,
        "detail_ids": extras,
        "convention": "annual_end_year_constant_explicit_discount",
        "calculations": list(ledger.rows.values()),
    }
