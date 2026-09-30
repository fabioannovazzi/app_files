"""Reconcile operating capital and economic profit with the same dated factors."""

from __future__ import annotations

from valuation_engine import Ledger, ValuationError

__all__ = ["economic_profit"]


def economic_profit(
    ledger: Ledger, args: dict, factors: list[str], horizon: str
) -> tuple[str, dict[str, str], list[dict]]:
    """Enforce explicit accounting identities, not accounting or WACC judgments.

    Capital roll-forward and matched interval charges make the economic-profit
    and operating-cash-flow expressions algebraically equivalent. Keeping both
    in the ledger provides a reproducible check, not independent evidence that
    NOPAT, net reinvestment or the terminal enterprise value is appropriate.
    """
    count = len(factors)
    series = {}
    for key in ("operating_capital", "nopat", "net_reinvestment"):
        refs = args[key]
        expected_count = count + 1 if key == "operating_capital" else count
        if not isinstance(refs, list) or len(refs) != expected_count:
            raise ValuationError(
                f"Economic profit requires {expected_count} {key} amounts"
            )
        series[key] = [ledger.input(ref, ledger.currency) for ref in refs]
    if args["terminal_enterprise_value"] in [
        *args["nopat"],
        *args["net_reinvestment"],
    ]:
        raise ValuationError("Terminal enterprise value requires an independent input")
    terminal = ledger.input(args["terminal_enterprise_value"], ledger.currency)
    one = ledger.constant("economic/one", 1)
    previous_factor = one
    schedule, profit_present, cash_present = [], [], []
    for index, factor in enumerate(factors):
        name = f"economic/{index + 1}"
        opening, closing = series["operating_capital"][index : index + 2]
        nopat = series["nopat"][index]
        reinvestment = series["net_reinvestment"][index]
        expected = ledger.add(
            f"{name}/expected_closing", "sum", [opening, reinvestment]
        )
        difference = ledger.add(
            f"{name}/reconciliation", "subtract", [closing, expected]
        )
        if ledger.value(difference) != 0:
            raise ValuationError(
                f"Operating capital does not reconcile in period {index + 1}"
            )
        interval_factor = ledger.add(
            f"{name}/interval_factor", "divide", [factor, previous_factor], "ratio"
        )
        period_cost = ledger.add(
            f"{name}/period_cost", "subtract", [interval_factor, one], "ratio"
        )
        charge = ledger.add(
            f"{name}/capital_charge", "multiply", [opening, period_cost]
        )
        profit = ledger.add(f"{name}/profit", "subtract", [nopat, charge])
        profit_pv = ledger.add(f"{name}/pv_profit", "divide", [profit, factor])
        cash = ledger.add(f"{name}/fcff", "subtract", [nopat, reinvestment])
        cash_pv = ledger.add(f"{name}/pv_fcff", "divide", [cash, factor])
        profit_present.append(profit_pv)
        cash_present.append(cash_pv)
        schedule.append(
            {
                "opening_id": opening,
                "nopat_id": nopat,
                "reinvestment_id": reinvestment,
                "closing_id": closing,
                "expected_closing_id": expected,
                "difference_id": difference,
                "period_cost_id": period_cost,
                "capital_charge_id": charge,
                "economic_profit_id": profit,
                "pv_economic_profit_id": profit_pv,
                "fcff_id": cash,
                "pv_fcff_id": cash_pv,
            }
        )
        previous_factor = factor
    continuation = ledger.add(
        "continuing_economic_profit",
        "subtract",
        [terminal, series["operating_capital"][-1]],
    )
    pv_continuation = ledger.add(
        "pv_continuing_economic_profit", "divide", [continuation, horizon]
    )
    pv_profits = ledger.add("economic_profit_pv", "sum", profit_present)
    result = ledger.add(
        "value", "sum", [series["operating_capital"][0], pv_profits, pv_continuation]
    )
    terminal_pv = ledger.add("pv_terminal_enterprise", "divide", [terminal, horizon])
    cash_value = ledger.add(
        "operating_cashflow_value", "sum", [*cash_present, terminal_pv]
    )
    difference = ledger.add(
        "operating_cashflow_difference", "subtract", [result, cash_value]
    )
    return (
        result,
        {
            "opening_operating_capital": series["operating_capital"][0],
            "economic_profit_pv": pv_profits,
            "terminal_enterprise_value": terminal,
            "closing_operating_capital": series["operating_capital"][-1],
            "continuing_economic_profit": continuation,
            "pv_continuing_economic_profit": pv_continuation,
            "operating_cashflow_value": cash_value,
            "operating_cashflow_difference": difference,
        },
        schedule,
    )
