"""Compare like-for-like, reviewed register and liquidation amounts by code."""

from __future__ import annotations

from typing import Callable

from lipe_core import TREATMENTS, ZERO, ContractError, money

__all__ = ["reconcile"]

BASE_PERIOD = {
    "REGISTRATION": "base_period",
    "CHARGEABILITY": "tax_period",
    "DEDUCTION": "deduction_period",
}


def reconcile(
    case: dict,
    reference: Callable[[dict], str],
    check_amount: Callable[[str, str, str], None],
    blockers: list[str],
    findings: list[dict],
) -> list[dict]:
    """Keep absent lines distinct from printed zeros; never infer a tax cause."""
    documents = {item["period"]: item for item in case["liquidations"]}
    if len(documents) != len(case["liquidations"]):
        raise ContractError("Duplicate liquidation period")
    periods = {module["period"] for module in case["modules"]}
    if set(documents) - periods:
        raise ContractError("Liquidation outside the selected quarter")
    mappings = {(m["side"], m["code"]): m for m in case["mappings"]}
    output = []
    for period in sorted(periods):
        document = documents.get(period)
        if document is None:
            blockers.append(f"LIQUIDATION_MISSING:{period}")
            continue
        reference(document["evidence"])
        if document["review"]["status"] != "CONFIRMED":
            blockers.append(f"LIQUIDATION_NOT_REVIEWED:{period}")
        seen: set[tuple] = set()
        for section in document["sections"]:
            side = section["side"]
            basis = (side, section["base_basis"], section["tax_basis"])
            if basis in seen:
                raise ContractError("Duplicate liquidation comparison basis")
            seen.add(basis)
            base_period = BASE_PERIOD[section["base_basis"]]
            tax_basis = section["tax_basis"]
            tax_period = {
                "RECORDED": "base_period",
                "OUTPUT": "tax_period",
                "DEDUCTIBLE": "deduction_period",
            }[tax_basis]
            registered: dict[str, list[dict]] = {}
            for register in case["registers"]:
                if register["side"] != side:
                    continue
                for row in register["rows"]:
                    if row[base_period] == period or row[tax_period] == period:
                        registered.setdefault(row["code"], []).append(row)
            printed = {row["code"]: row for row in section["rows"]}
            if len(printed) != len(section["rows"]):
                raise ContractError("Duplicate code in liquidation section")
            for code in sorted(registered.keys() | printed.keys()):
                rows = registered.get(code, [])
                declared = printed.get(code)
                mapping = mappings.get((side, code))
                tax_known = tax_basis == "RECORDED" or bool(
                    mapping and mapping["review"]["status"] == "CONFIRMED"
                )
                base = sum(
                    (money(row["base"]) for row in rows if row[base_period] == period),
                    ZERO,
                )
                tax = ZERO
                for row in rows:
                    if row[tax_period] != period or not tax_known:
                        continue
                    if tax_basis == "RECORDED":
                        tax += money(row["tax"])
                    elif (
                        mapping
                        and TREATMENTS[mapping["treatment"]][
                            2 if tax_basis == "OUTPUT" else 3
                        ]
                    ):
                        tax += money(
                            row["tax" if tax_basis == "OUTPUT" else "deductible_tax"]
                        )
                base_difference = tax_difference = None
                if declared:
                    quote = reference(declared["evidence"])
                    for field in ("base", "tax"):
                        check_amount(declared[field], quote, document["number_format"])
                    if rows:
                        base_difference = f"{base - money(declared['base']):.2f}"
                        if tax_known:
                            tax_difference = f"{tax - money(declared['tax']):.2f}"
                status = (
                    "NOT_REPORTED"
                    if declared is None
                    else (
                        "NO_REGISTER_ROWS"
                        if not rows
                        else (
                            "BASIS_NOT_CONFIRMED"
                            if not tax_known
                            else (
                                "DIFFERENCE_TO_REVIEW"
                                if base_difference != "0.00" or tax_difference != "0.00"
                                else "MATCH"
                            )
                        )
                    )
                )
                item = {
                    "period": period,
                    "side": side,
                    "code": code,
                    "base_basis": section["base_basis"],
                    "tax_basis": tax_basis,
                    "register_base": f"{base:.2f}" if rows else None,
                    "register_tax": f"{tax:.2f}" if rows and tax_known else None,
                    "liquidation_base": declared["base"] if declared else None,
                    "liquidation_tax": declared["tax"] if declared else None,
                    "base_difference": base_difference,
                    "tax_difference": tax_difference,
                    "status": status,
                    "register_rows": [row["row_id"] for row in rows],
                    "register_evidence": [row["evidence"] for row in rows],
                    "liquidation_evidence": declared["evidence"] if declared else None,
                }
                output.append(item)
                if status != "MATCH":
                    findings.append(
                        dict(
                            code="CODE_LIQUIDATION_DIFFERENCE",
                            period=period,
                            vat_code=code,
                            side=side,
                            status=status,
                            meaning="Review the stated comparison basis and source lines; no cause or correction is inferred.",
                        )
                    )
        if not {"SALES", "PURCHASES"}.issubset({key[0] for key in seen}):
            blockers.append(f"LIQUIDATION_COVERAGE_INCOMPLETE:{period}")
    return output
