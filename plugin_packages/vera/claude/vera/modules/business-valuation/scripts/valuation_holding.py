"""Explicit holding-company parts, equity bridges and signed adjustments.

Fixed arithmetic and declared identity checks make the workpaper reproducible.
They do not decide ownership rights, valuation scope or economic duplication.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from valuation_engine import Ledger, ValuationError

__all__ = [
    "holding_sotp",
    "holding_evidence",
    "HOLDING_BASIS_LABELS",
    "PART_BASIS_LABELS",
]

HOLDING_BASIS_LABELS = {
    "parent_perimeter": "Perimetro autonomo della holding",
    "costs_basis": "Valore attuale dei costi holding",
    "tax_basis": "Effetti fiscali e loro base",
    "intragroup_basis": "Rapporti ed eliminazioni infragruppo",
    "overlap_review": "Verifica delle duplicazioni economiche",
    "rights_scope": "Diritti e perimetro del risultato holding",
}
PART_BASIS_LABELS = {
    "description": "Partecipazione e soggetto",
    "scope": "Perimetro della valutazione fornita",
    "ownership_basis": "Denominatore e significato della quota",
    "rights_basis": "Diritti e rettifica esplicita",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValuationError(message)


def holding_evidence(method: dict, mandate: dict, currency: str, sources: dict) -> dict:
    """Bind declared perimeters and review state without assessing their truth."""
    args = method["inputs"]
    records = [method["holding_basis"]]
    identities = []
    for part in args["holdings"]:
        basis = part["basis"]
        identities.append((basis["entity_id"], basis["interest_id"]))
        _require(
            basis["valuation_date"] == mandate["valuation_date"],
            "Each holding part must use the mandate valuation date",
        )
        _require(
            basis["currency"] == currency,
            "Holding parts require the case currency; no implicit FX conversion",
        )
        records.append(basis)
    _require(
        len(set(identities)) == len(identities),
        "The same declared entity and interest cannot be included twice",
    )
    records.extend(args["eliminations"])
    source_ids = sorted({ref for record in records for ref in record["source_ids"]})
    _require(
        set(source_ids) <= sources.keys(),
        "Holding bases and eliminations require declared evidence sources",
    )
    return {
        "source_ids": source_ids,
        "complete": all(record["status"] == "confirmed" for record in records),
    }


def holding_sotp(ledger: Ledger, args: dict) -> tuple[str, dict[str, str], dict]:
    """Compose explicit stakes and parent-only amounts; never apply a hidden discount."""
    for key in ("holdings", "parent_assets", "parent_liabilities", "eliminations"):
        _require(
            isinstance(args[key], list)
            and (1 if key == "holdings" else 0) <= len(args[key]) <= 100,
            f"Holding {key} requires an explicit bounded list",
        )
    money = lambda ref: ledger.input(ref, ledger.currency)
    monetary_refs: set[str] = set()

    def amount(ref: str, *, nonnegative: bool = False) -> str:
        result = money(ref)
        _require(
            not nonnegative or ledger.value(result) >= 0,
            "Holding debt, cash and cost amounts must be nonnegative",
        )
        monetary_refs.add(ref)
        return result

    parts, stakes, identifiers = [], [], set()
    ownership_totals: dict[tuple[str, str], Decimal] = {}
    for part in args["holdings"]:
        identifier = part["id"]
        _require(identifier not in identifiers, "Duplicate holding part ID")
        identifiers.add(identifier)
        prefix = f"holding/{identifier}"
        original = amount(part["value"])
        value_type = part["value_type"]
        equity = original
        bridge_ids = {}
        if value_type == "operating_enterprise":
            bridge = part["bridge"]
            bridge_ids = {
                key: amount(bridge[key], nonnegative=key != "signed_adjustments")
                for key in (
                    "financial_debt",
                    "debt_like",
                    "excess_cash",
                    "non_operating_assets",
                    "signed_adjustments",
                )
            }
            debt = ledger.add(
                f"{prefix}/debt",
                "sum",
                [bridge_ids["financial_debt"], bridge_ids["debt_like"]],
            )
            net = ledger.add(f"{prefix}/after_debt", "subtract", [original, debt])
            equity = ledger.add(
                f"{prefix}/equity",
                "sum",
                [
                    net,
                    bridge_ids["excess_cash"],
                    bridge_ids["non_operating_assets"],
                    bridge_ids["signed_adjustments"],
                ],
            )
        else:
            _require(
                "bridge" not in part,
                "Do not deduct debt again from holding equity or an interest value",
            )
        ownership = proportional = adjustment = None
        if value_type == "specific_interest":
            _require(
                "ownership" not in part
                and "rights_adjustment" not in part
                and part["basis"]["ownership_denominator_id"] is None,
                "A supplied specific-interest value cannot be scaled or adjusted again",
            )
            stake = original
        else:
            _require(
                value_type in {"operating_enterprise", "full_equity"},
                "Unknown holding value basis",
            )
            ownership = ledger.input(part["ownership"], "ratio")
            share = ledger.value(ownership)
            _require(
                0 <= share <= 1,
                "Declared holding ownership must lie between zero and one",
            )
            denominator = part["basis"]["ownership_denominator_id"]
            _require(
                bool(denominator),
                "A proportional holding requires an explicit ownership denominator",
            )
            key = (part["basis"]["entity_id"], denominator)
            with localcontext() as context:
                context.prec = 40
                ownership_totals[key] = ownership_totals.get(key, Decimal(0)) + share
            _require(
                ownership_totals[key] <= 1,
                "Declared ownership exceeds one for the same entity and denominator",
            )
            proportional = ledger.add(
                f"{prefix}/proportional", "multiply", [equity, ownership]
            )
            adjustment = amount(part["rights_adjustment"])
            stake = ledger.add(f"{prefix}/stake", "sum", [proportional, adjustment])
        stakes.append(stake)
        parts.append(
            {
                "id": identifier,
                "value_type": value_type,
                "basis": part["basis"],
                "original_id": original,
                "equity_id": equity if value_type != "specific_interest" else None,
                "ownership_id": ownership,
                "proportional_id": proportional,
                "rights_adjustment_id": adjustment,
                "stake_id": stake,
                "bridge_ids": bridge_ids,
            }
        )
    parent_refs = [
        *args["parent_assets"],
        *args["parent_liabilities"],
        args["holding_costs_pv"],
        args["tax_adjustment"],
    ]
    _require(
        len(parent_refs) == len(set(parent_refs)),
        "Parent monetary roles require distinct input records",
    )
    investments = ledger.add("holdings_value", "sum", stakes)
    assets = ledger.add(
        "parent_assets", "sum", [amount(ref) for ref in args["parent_assets"]]
    )
    liabilities = ledger.add(
        "parent_liabilities",
        "sum",
        [amount(ref, nonnegative=True) for ref in args["parent_liabilities"]],
    )
    costs = amount(args["holding_costs_pv"], nonnegative=True)
    tax = amount(args["tax_adjustment"])
    elimination_rows, elimination_ids, elimination_inputs, adjustments = (
        [],
        set(),
        set(),
        [],
    )
    for row in args["eliminations"]:
        _require(row["id"] not in elimination_ids, "Duplicate holding elimination ID")
        elimination_ids.add(row["id"])
        _require(
            set(row["affected_input_ids"]) <= monetary_refs,
            "Holding elimination must identify amounts actually included in this method",
        )
        _require(
            row["amount_input"] not in monetary_refs | elimination_inputs,
            "Holding elimination requires its own independent signed amount",
        )
        elimination_inputs.add(row["amount_input"])
        adjustment_id = money(row["amount_input"])
        adjustments.append(adjustment_id)
        elimination_rows.append({**row, "value_id": adjustment_id})
    eliminated = ledger.add("eliminations", "sum", adjustments)
    gross = ledger.add("holding_gross", "sum", [investments, assets, eliminated])
    deductions = ledger.add("holding_deductions", "sum", [liabilities, costs, tax])
    result = ledger.add("value", "subtract", [gross, deductions])
    return (
        result,
        {
            "holdings_value": investments,
            "parent_assets": assets,
            "parent_liabilities": liabilities,
            "holding_costs_pv": costs,
            "holding_tax_adjustment": tax,
            "holding_eliminations": eliminated,
        },
        {"parts": parts, "eliminations": elimination_rows},
    )
