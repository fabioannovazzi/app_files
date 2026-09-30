"""Reconcile explicit clean-surplus amounts and reproducible residual-income math."""

from __future__ import annotations

from valuation_engine import Ledger, ValuationError

__all__ = ["residual_income"]


def residual_income(
    ledger: Ledger, args: dict, factors: list[str], horizon: str
) -> tuple[str, dict[str, str], list[dict]]:
    """Use exact accounting identities; never infer adjustments or owner payments.

    The interval equity charge follows the same cumulative discount factors as
    the residual income. This preserves the clean-surplus telescoping identity,
    including explicit contributions and nonannual intervals. It does not prove
    accounting adequacy, distributability or the selected terminal equity value.
    """
    count = len(factors)
    series = {}
    for key in ("book_equity", "incomes", "distributions", "contributions"):
        refs = args[key]
        expected_count = count + 1 if key == "book_equity" else count
        if not isinstance(refs, list) or len(refs) != expected_count:
            raise ValuationError(
                f"Residual income requires {expected_count} {key} amounts"
            )
        series[key] = [ledger.input(ref, ledger.currency) for ref in refs]
    if args["terminal_equity_value"] in args["incomes"]:
        raise ValuationError("Terminal equity value requires an independent input")
    terminal = ledger.input(args["terminal_equity_value"], ledger.currency)
    one = ledger.constant("residual/one", 1)
    previous_factor = one
    schedule, present, owner_present = [], [], []
    for index, factor in enumerate(factors):
        name = f"residual/{index + 1}"
        opening, closing = series["book_equity"][index : index + 2]
        income = series["incomes"][index]
        distribution = series["distributions"][index]
        contribution = series["contributions"][index]
        if min(ledger.value(distribution), ledger.value(contribution)) < 0:
            raise ValuationError("Distributions and contributions must be nonnegative")
        gross = ledger.add(
            f"{name}/gross_equity", "sum", [opening, income, contribution]
        )
        expected = ledger.add(
            f"{name}/expected_closing", "subtract", [gross, distribution]
        )
        difference = ledger.add(
            f"{name}/reconciliation", "subtract", [closing, expected]
        )
        if ledger.value(difference) != 0:
            raise ValuationError(
                f"Clean surplus does not reconcile in period {index + 1}"
            )
        interval_factor = ledger.add(
            f"{name}/interval_factor", "divide", [factor, previous_factor], "ratio"
        )
        period_cost = ledger.add(
            f"{name}/period_cost", "subtract", [interval_factor, one], "ratio"
        )
        charge = ledger.add(f"{name}/equity_charge", "multiply", [opening, period_cost])
        residual = ledger.add(f"{name}/income", "subtract", [income, charge])
        pv = ledger.add(f"{name}/pv", "divide", [residual, factor])
        net_owner = ledger.add(
            f"{name}/net_owner_payment", "subtract", [distribution, contribution]
        )
        owner_pv = ledger.add(f"{name}/pv_owner_payment", "divide", [net_owner, factor])
        present.append(pv)
        owner_present.append(owner_pv)
        schedule.append(
            {
                "opening_id": opening,
                "income_id": income,
                "distribution_id": distribution,
                "contribution_id": contribution,
                "closing_id": closing,
                "expected_closing_id": expected,
                "difference_id": difference,
                "period_cost_id": period_cost,
                "equity_charge_id": charge,
                "residual_income_id": residual,
                "pv_residual_income_id": pv,
            }
        )
        previous_factor = factor
    continuation = ledger.add(
        "continuing_residual", "subtract", [terminal, series["book_equity"][-1]]
    )
    pv_continuation = ledger.add(
        "pv_continuing_residual", "divide", [continuation, horizon]
    )
    pv_incomes = ledger.add("residual_income_pv", "sum", present)
    result = ledger.add(
        "value", "sum", [series["book_equity"][0], pv_incomes, pv_continuation]
    )
    terminal_pv = ledger.add("pv_terminal_equity", "divide", [terminal, horizon])
    owner_value = ledger.add(
        "owner_cashflow_value", "sum", [*owner_present, terminal_pv]
    )
    crosscheck = ledger.add(
        "owner_cashflow_difference", "subtract", [result, owner_value]
    )
    return (
        result,
        {
            "opening_book_equity": series["book_equity"][0],
            "residual_income_pv": pv_incomes,
            "terminal_equity_value": terminal,
            "closing_book_equity": series["book_equity"][-1],
            "continuing_residual": continuation,
            "pv_continuing_residual": pv_continuation,
            "owner_cashflow_value": owner_value,
            "owner_cashflow_difference": crosscheck,
        },
        schedule,
    )
