"""Replay the existing v3 plan and build an explicit cash-tax FCFF bridge."""

from __future__ import annotations

import shutil
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory

from valuation_case import fields, indexed, read_json, require, source_paths
from valuation_engine import decimal

__all__ = ["bridge_plan"]


def bridge_plan(case: dict, source_root: Path, replay_parent: Path) -> dict:
    """Verify mapped source bytes via the shared compiler, not a parallel forecast.

    Original source paths are reconstructed only below the bound run's scratch
    directory. The final bridge retains hashes, periods and upstream calculation IDs.
    """
    binding = case["plan_binding"]
    fields(
        binding,
        {
            "source_id",
            "source_map",
            "scenario_id",
            "cash_operating_taxes",
            "opening_operating_nwc",
            "annual_input_ids",
            "operating_classification",
            "tax_refund_basis",
        },
    )
    require(
        bool(binding["operating_classification"]),
        "Review which current balances are operating and exclude debt-like items",
    )
    sources = indexed(case["sources"])
    paths = dict(zip(sources, source_paths(case, source_root)))
    require(binding["source_id"] in sources, "Plan source must be registered")
    plan = read_json(paths[binding["source_id"]])
    require(
        plan["schema_version"] == "mparanza.business_planning_plan.v3",
        "Use the finalized shared v3 plan artifact",
    )
    upstream = plan["case"]
    require(
        upstream["reporting_currency"] == case["currency"],
        "Plan currency differs from valuation",
    )
    require(
        upstream["audience"] == case["audience"], "Plan audience differs from valuation"
    )
    require(
        plan["status"] == "ready_for_professional_review",
        "Plan must pass its existing completeness and calculation gates",
    )
    mapping = binding["source_map"]
    require(
        isinstance(mapping, dict)
        and set(mapping) == {row["id"] for row in upstream["sources"]},
        "Map every original plan source to an exact valuation receipt",
    )
    module = Path(__file__).resolve().parents[2] / "business-planning/scripts"
    require(module.is_dir(), "Shared Business Planning component is required")
    if str(module) not in sys.path:
        sys.path.insert(0, str(module))
    from planning_workflow import validate_plan

    replay_parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="plan-replay-", dir=replay_parent) as scratch:
        root = Path(scratch)
        for row in upstream["sources"]:
            target = root / row["path"]
            require(
                not Path(row["path"]).is_absolute()
                and ".." not in Path(row["path"]).parts,
                "Invalid original source path",
            )
            mapped = mapping[row["id"]]
            require(
                mapped in sources and sources[mapped]["sha256"] == row["sha256"],
                "Mapped plan source digest differs",
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(paths[mapped], target)
        validate_plan(plan, source_root=root)
    periods = upstream["periods"]
    require(
        bool(periods) and periods[0].endswith("-01") and len(periods) % 12 == 0,
        "Annual valuation bridge requires complete January-December years; no invented stub conversion",
    )
    require(
        case["mandate"]["valuation_date"] == f"{int(periods[0][:4])-1}-12-31",
        "End-year bridge requires valuation on the preceding year end",
    )
    scenarios = [
        row
        for row in upstream["financial"]["scenarios"]
        if row["id"] == binding["scenario_id"]
    ]
    require(len(scenarios) == 1, "Select one existing plan scenario")
    inputs = indexed(case["inputs"])
    taxes = binding["cash_operating_taxes"]
    require(
        isinstance(taxes, dict) and set(taxes) == set(periods),
        "Explicit cash operating taxes required for every month",
    )

    def amount(ref: str) -> Decimal:
        require(
            ref in inputs and inputs[ref]["unit"] == case["currency"],
            "Missing or incompatible bridge input",
        )
        return decimal(inputs[ref]["value"])

    previous = amount(binding["opening_operating_nwc"])
    monthly, annual = [], []
    with localcontext() as ctx:
        ctx.prec = 40
        running = Decimal(0)
        annual_ids = []
        for row in scenarios[0]["schedule"]:
            period = row["period"]
            values = {
                key: decimal(row[key])
                for key in (
                    "revenue",
                    "cogs",
                    "operating_expenses",
                    "depreciation_amortization",
                    "capital_expenditure",
                    "ending_accounts_receivable",
                    "ending_inventory",
                    "ending_other_current_assets",
                    "ending_accounts_payable",
                    "ending_other_liabilities",
                )
            }
            tax = amount(taxes[period])
            require(
                tax >= 0 or bool(binding["tax_refund_basis"]),
                "Negative cash operating tax requires an explicit refund basis",
            )
            nwc = (
                values["ending_accounts_receivable"]
                + values["ending_inventory"]
                + values["ending_other_current_assets"]
                - values["ending_accounts_payable"]
                - values["ending_other_liabilities"]
            )
            ebit = (
                values["revenue"]
                - values["cogs"]
                - values["operating_expenses"]
                - values["depreciation_amortization"]
            )
            delta = nwc - previous
            fcff = (
                ebit
                - tax
                + values["depreciation_amortization"]
                - values["capital_expenditure"]
                - delta
            )
            ids = [
                f"{binding['scenario_id']}/{period}/{metric}"
                for metric in ("ebit", "working_capital")
            ]
            require(
                all(identifier in plan["calculations"] for identifier in ids),
                "Missing shared calculation lineage",
            )
            monthly.append(
                {
                    "period": period,
                    "ebit": str(ebit),
                    "cash_operating_taxes": str(tax),
                    "delta_nwc": str(delta),
                    "ending_nwc": str(nwc),
                    "fcff": str(fcff),
                    "plan_calculation_ids": ids,
                    "tax_input_id": taxes[period],
                }
            )
            previous = nwc
            running += fcff
            annual_ids.extend(ids)
            if period.endswith("-12"):
                annual.append(
                    {
                        "year": period[:4],
                        "fcff": str(running),
                        "ending_nwc": str(nwc),
                        "plan_calculation_ids": annual_ids,
                    }
                )
                running, annual_ids = Decimal(0), []
        require(
            len(binding["annual_input_ids"]) == len(annual),
            "Bind one FCFF input per complete year",
        )
        for ref, row in zip(binding["annual_input_ids"], annual):
            require(
                amount(ref) == decimal(row["fcff"]),
                "Valuation flow differs from replayed plan bridge",
            )
            require(
                binding["source_id"] in inputs[ref]["source_ids"],
                "Annual flow must reference its plan artifact",
            )
            require(
                inputs[ref].get("plan_calculation_ids") == row["plan_calculation_ids"],
                "Annual flow must retain exact upstream calculation IDs",
            )
    return {
        "plan_sha256": sources[binding["source_id"]]["sha256"],
        "plan_case_sha256": plan["case_sha256"],
        "scenario_id": binding["scenario_id"],
        "monthly": monthly,
        "annual": annual,
        "binding": binding,
    }
