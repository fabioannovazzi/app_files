"""Exact LIPE arithmetic on explicitly reviewed facts, never tax classification.

Decimal arithmetic, source hashes, reconciliation and period constraints are
mechanically verifiable. Code meaning, tax entitlement, completeness and period
attribution are professional judgments supplied with evidence, not inferred here.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import jsonschema

__all__ = ["ContractError", "calculate", "digest", "money", "read_json", "validate"]

ROOT = Path(__file__).resolve().parents[1]
ZERO = Decimal("0.00")
CENT = Decimal("0.01")
THRESHOLD = Decimal("100.00")
MONEY = re.compile(r"-?(?:0|[1-9][0-9]{0,10})\.[0-9]{2}\Z")
# Mapping is selected by the professional, not guessed from a vendor code.
TREATMENTS = {
    "SALE_TAXABLE": ("SALES", True, True, False),
    "SALE_NO_OUTPUT_VAT": ("SALES", True, False, False),
    "SALE_EXCLUDED": ("SALES", False, False, False),
    "PURCHASE": ("PURCHASES", True, False, True),
    "PURCHASE_REVERSE_CHARGE": ("PURCHASES", True, True, True),
    "PURCHASE_EXCLUDED": ("PURCHASES", False, False, False),
    "INTEGRATION_MIRROR": ("INTEGRATION", False, False, False),
}


class ContractError(ValueError):
    """An input cannot support a trustworthy result."""


def digest(value: Any) -> str:
    """Bind JSON values, including decisions and the complete source inventory."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ContractError(f"Non-finite JSON number: {value}")


def read_json(path: Path) -> dict:
    """Reject duplicate keys and non-standard NaN/Infinity input."""
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=_nonfinite,
    )


def money(value: str) -> Decimal:
    """Require canonical bounded decimal strings; never coerce floats or null."""
    if not isinstance(value, str) or not MONEY.fullmatch(value):
        raise ContractError(f"Invalid money: {value!r}")
    return Decimal(value)


def validate(case: dict) -> None:
    """Validate the complete input shape using JSON Schema, including dates."""
    schema = read_json(ROOT / "schemas/case.schema.json")
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(case), key=lambda e: str(e.json_path))
    if errors:
        raise ContractError(f"{errors[0].json_path}: {errors[0].message}")


def _unique(rows: list[dict], key: str) -> dict[str, dict]:
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ContractError(f"Duplicate {key}")
    return result


def _evidence(case: dict, source_root: Path) -> dict[str, dict]:
    sources = _unique(case["sources"], "source_id")
    for source in sources.values():
        path = (source_root / source["path"]).resolve()
        if Path(source["path"]).is_absolute() or not path.is_relative_to(
            source_root.resolve()
        ):
            raise ContractError("Evidence path escapes source root")
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ContractError(f"Source changed: {source['source_id']}")
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ContractError(
                    "Encrypted PDF: provide an authorized readable copy"
                )
            source = dict(source, pages=[p.extract_text() or "" for p in reader.pages])
        elif path.suffix.lower() in {".txt", ".csv", ".md"}:
            source = dict(source, pages=[path.read_text(encoding="utf-8-sig")])
        else:
            raise ContractError("Use PDF or readable UTF-8 text/CSV evidence")
        sources[source["source_id"]] = source
    return sources


def _reference(ref: dict, sources: dict[str, dict]) -> str:
    source = sources.get(ref["source_id"])
    if source is None or ref["page"] > len(source["pages"]):
        raise ContractError("Unknown source or page")
    if ref["quote"] not in source["pages"][ref["page"] - 1]:
        raise ContractError("Evidence quotation not found on the stated page")
    return ref["quote"]


def _confirmed(review: dict | None) -> bool:
    return bool(review and review["status"] == "CONFIRMED")


def _amount_in_quote(amount: str, quote: str, locale: str) -> None:
    # Exact printed numeric tokens prevent a supported quote masking a mistyped amount.
    if locale == "it-IT":
        tokens = re.findall(
            r"(?<![\w.,])-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?![\w,]|\.\d)", quote
        )
        values = [token.replace(".", "").replace(",", ".") for token in tokens]
    else:
        tokens = re.findall(
            r"(?<![\w.,])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\w,]|\.\d)", quote
        )
        values = [token.replace(",", "") for token in tokens]
    if money(amount) not in [Decimal(value) for value in values]:
        raise ContractError(f"Amount {amount} absent from source quotation")


def _periods(case: dict) -> list[int]:
    quarter = case["quarter"]
    if case["regime"] == "MONTHLY":
        return list(range(quarter * 3 - 2, quarter * 3 + 1))
    return [quarter]


def calculate(case: dict, source_root: Path) -> dict:
    """Return a persisted-ready draft or an explicit blocker, never a filed return."""
    validate(case)
    sources = _evidence(case, source_root)
    blockers: list[str] = []
    findings: list[dict] = []
    expected = _periods(case)
    if [module["period"] for module in case["modules"]] != expected:
        raise ContractError(
            "Modules must cover the full quarter in chronological order"
        )
    if not _confirmed(case["scope_review"]):
        blockers.append("SCOPE_NOT_CONFIRMED")
    if case["unsupported_features"]:
        blockers.append("UNSUPPORTED_TAX_REGIME_OR_FEATURE")
    if case["opening"] is None or not _confirmed(case["opening"]["review"]):
        blockers.append("OPENING_BALANCE_UNKNOWN")
    else:
        _reference(case["opening"]["evidence"], sources)
    mapping: dict[tuple[str, str], dict] = {}
    for entry in case["mappings"]:
        key = (entry["side"], entry["code"])
        if key in mapping:
            raise ContractError("Duplicate code mapping in the selected case scope")
        if TREATMENTS[entry["treatment"]][0] != entry["side"]:
            raise ContractError("Mapping treatment and register side disagree")
        mapping[key] = entry
    registers = _unique(case["registers"], "register_id")
    row_ids: set[str] = set()
    row_evidence: set[tuple] = set()
    row_map: dict[str, dict] = {}
    totals = {
        period: {key: ZERO for key in ("vp2", "vp3", "vp4", "vp5")}
        for period in expected
    }
    composition: list[dict] = []
    for register in registers.values():
        if register["period"] > (12 if case["regime"] == "MONTHLY" else 4):
            raise ContractError("Register period incompatible with periodicity")
        if not _confirmed(register["review"]):
            blockers.append(f"REGISTER_NOT_REVIEWED:{register['register_id']}")
        quoted_total = _reference(register["evidence"], sources)
        for field in ("printed_base", "printed_tax"):
            _amount_in_quote(register[field], quoted_total, register["number_format"])
        base_sum = tax_sum = ZERO
        for row in register["rows"]:
            if row["row_id"] in row_ids:
                raise ContractError("Duplicate row_id: possible double counting")
            row_ids.add(row["row_id"])
            row_map[row["row_id"]] = dict(row, side=register["side"])
            quote = _reference(row["evidence"], sources)
            evidence_key = (
                row["evidence"]["source_id"],
                row["evidence"]["page"],
                quote,
            )
            if evidence_key in row_evidence:
                raise ContractError(
                    "Duplicate row evidence: use a distinct source locator"
                )
            row_evidence.add(evidence_key)
            for field in ("base", "tax"):
                _amount_in_quote(row[field], quote, register["number_format"])
            base, tax, deductible = (
                money(row[k]) for k in ("base", "tax", "deductible_tax")
            )
            base_sum += base
            tax_sum += tax
            if abs(deductible) > abs(tax) or deductible * tax < ZERO:
                raise ContractError(
                    "Deduction must have the tax sign and cannot exceed tax"
                )
            if not _confirmed(row["review"]):
                blockers.append(f"ROW_NOT_REVIEWED:{row['row_id']}")
            entry = mapping.get((register["side"], row["code"]))
            if entry is None or not _confirmed(entry["review"]):
                blockers.append(f"CODE_NOT_CONFIRMED:{register['side']}:{row['code']}")
                continue
            side, include_base, output_tax, input_tax = TREATMENTS[entry["treatment"]]
            if not input_tax and deductible != ZERO:
                raise ContractError("Deduction supplied for a non-deducting treatment")
            limit = 12 if case["regime"] == "MONTHLY" else 4
            if any(
                row[k] > limit
                for k in ("base_period", "tax_period", "deduction_period")
            ):
                raise ContractError("Row period incompatible with periodicity")
            if row["base_period"] != register["period"]:
                raise ContractError(
                    "Taxable base must stay in its reviewed registration period"
                )
            contributions = []
            for period, field, amount in (
                (
                    row["base_period"],
                    "vp2" if side == "SALES" else "vp3",
                    base if include_base else ZERO,
                ),
                (row["tax_period"], "vp4", tax if output_tax else ZERO),
                (row["deduction_period"], "vp5", deductible if input_tax else ZERO),
            ):
                if period in totals and amount != ZERO:
                    totals[period][field] += amount
                    contributions.append(
                        {"period": period, "field": field, "amount": f"{amount:.2f}"}
                    )
            composition.append(
                {
                    "row_id": row["row_id"],
                    "register_id": register["register_id"],
                    "treatment": entry["treatment"],
                    "evidence": row["evidence"],
                    "contributions": contributions,
                }
            )
        if (base_sum, tax_sum) != (
            money(register["printed_base"]),
            money(register["printed_tax"]),
        ):
            blockers.append(f"REGISTER_TOTAL_MISMATCH:{register['register_id']}")
    for period in expected:
        sides = {
            r["side"]
            for r in registers.values()
            if r["period"] == period and _confirmed(r["review"])
        }
        if not {"SALES", "PURCHASES"}.issubset(sides):
            blockers.append(f"REGISTER_COVERAGE_INCOMPLETE:{period}")
    mirrored_ids: set[str] = set()
    for row in row_map.values():
        if row["side"] == "INTEGRATION":
            targets = [row_map.get(target) for target in row["mirror_of"]]
            if not targets or any(
                target is None or target["side"] != "PURCHASES" for target in targets
            ):
                blockers.append(f"INTEGRATION_UNLINKED:{row['row_id']}")
            elif any(
                mapping.get(("PURCHASES", target["code"]), {}).get("treatment")
                != "PURCHASE_REVERSE_CHARGE"
                for target in targets
                if target
            ):
                blockers.append(
                    f"INTEGRATION_TARGET_NOT_REVERSE_CHARGE:{row['row_id']}"
                )
            elif set(row["mirror_of"]) & mirrored_ids:
                blockers.append(f"INTEGRATION_TARGET_REPEATED:{row['row_id']}")
            elif any(
                sum((money(target[field]) for target in targets if target), ZERO)
                != money(row[field])
                for field in ("base", "tax")
            ):
                blockers.append(f"INTEGRATION_TAX_MISMATCH:{row['row_id']}")
            mirrored_ids.update(row["mirror_of"])
        elif row["mirror_of"]:
            raise ContractError(
                "Only an integration mirror can reference purchase rows"
            )
    for module in case["modules"]:
        if not _confirmed(module["review"]):
            blockers.append(f"ADJUSTMENTS_NOT_REVIEWED:{module['period']}")
        _reference(module["evidence"], sources)
    result = {
        "schema_version": "1.0",
        "pipeline": "LIPE",
        "status": "BLOCKED" if blockers else "DRAFT_FOR_REVIEW",
        "case_id": case["case_id"],
        "client_id": case["client_id"],
        "engagement_id": case["engagement_id"],
        "tax_year": case["tax_year"],
        "quarter": case["quarter"],
        "regime": case["regime"],
        "data_origin": case["data_origin"],
        "input_hash": digest(case),
        "rules_hash": hashlib.sha256(
            (ROOT / "references/rules.json").read_bytes()
        ).hexdigest(),
        "engine_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "blockers": sorted(set(blockers)),
        "findings": findings,
        "modules": [],
        "composition": composition,
        "qualification": "PILOT_NOT_PROFESSIONALLY_ACCEPTED",
        "export_status": "NOT_AUTHORIZED",
    }
    if not blockers:
        result["modules"] = _settle(case, totals, findings)
    result["result_hash"] = digest(result)
    return result


def _settle(case: dict, totals: dict[int, dict], findings: list[dict]) -> list[dict]:
    opening = case["opening"]
    credit, debt = money(opening["credit"]), money(opening["small_debit"])
    if case["regime"] == "QUARTERLY_OPTION" and debt:
        raise ContractError(
            "Quarterly small-debit interest carry requires a separately qualified principal/interest basis"
        )
    if credit < ZERO or not ZERO <= debt <= THRESHOLD or (credit and debt):
        raise ContractError("Invalid opening credit/small debit")
    output = []
    for module in case["modules"]:
        period = module["period"]
        monthly = case["regime"] == "MONTHLY"
        q4_option = case["regime"] == "QUARTERLY_OPTION" and period == 4
        if period == 1 and (credit or debt):
            raise ContractError(
                "Prior-year credit belongs in VP9; VP7/VP8 forbidden in period 1"
            )
        if debt and ((monthly and period == 12) or (not monthly and period == 4)):
            raise ContractError("VP7 forbidden in December/fourth quarter")
        withheld = money(module["credit_withheld"])
        if not ZERO <= withheld <= credit:
            raise ContractError("Credit withheld from carry exceeds available credit")
        rows = dict(totals[period])
        net = rows["vp4"] - rows["vp5"]
        rows.update(
            vp6_debit=max(net, ZERO),
            vp6_credit=max(-net, ZERO),
            vp7=debt,
            vp8=credit - withheld,
        )
        rows.update(
            {key: money(module[key]) for key in ("vp9", "vp10", "vp11", "vp13")}
        )
        if any(rows[key] < ZERO for key in ("vp10", "vp11", "vp13")):
            raise ContractError("VP10, VP11 and VP13 must be nonnegative")
        if period == 1 and rows["vp9"] < ZERO:
            raise ContractError("Negative VP9 forbidden in the first period")
        last = period == (12 if monthly else 4)
        if rows["vp13"] and (
            not last
            or rows["vp13"] < Decimal("103.29")
            or module["vp13_method"] is None
        ):
            raise ContractError(
                "Acconto requires final period, minimum 103.29 and method"
            )
        if not rows["vp13"] and module["vp13_method"] is not None:
            raise ContractError("Acconto method without amount")
        balance = net + debt - rows["vp8"] - rows["vp9"] - rows["vp10"]
        if rows["vp11"] > max(balance, ZERO) or (q4_option and rows["vp11"]):
            raise ContractError(
                "VP11 exceeds available debit or is forbidden in quarter 5"
            )
        balance -= rows["vp11"]
        interest = ZERO
        if case["regime"] == "QUARTERLY_OPTION" and period < 4:
            interest = (max(balance, ZERO) * Decimal("0.01")).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
        rows["vp12"] = interest
        balance += interest - rows["vp13"]
        rows["vp14_debit"], rows["vp14_credit"] = max(balance, ZERO), max(
            -balance, ZERO
        )
        if q4_option:
            # Official instructions: quarter code 5, VP11/12/14 not completed.
            rows["vp11"] = rows["vp12"] = rows["vp14_debit"] = rows["vp14_credit"] = (
                None
            )
        deferred = module["defer_small_debit"]
        due = rows["vp14_debit"]
        may_carry = (monthly and period < 11) or (not monthly and period < 3)
        if deferred and (due is None or not ZERO < due <= THRESHOLD or not may_carry):
            raise ContractError(
                "Small-debit carry not permitted for this amount/period"
            )
        if deferred and case["regime"] == "QUARTERLY_OPTION":
            raise ContractError(
                "Quarterly small-debit interest carry is not qualified in this pilot"
            )
        if (
            due is not None
            and ZERO < due <= THRESHOLD
            and may_carry
            and deferred is None
        ):
            raise ContractError("Confirm whether the small debit was paid or deferred")
        paid = (
            None
            if module["principal_paid"] is None
            else money(module["principal_paid"])
        )
        if paid is not None and paid < ZERO:
            raise ContractError("Paid principal must be nonnegative")
        if deferred and paid not in (None, ZERO):
            raise ContractError("Cannot carry a debit that is also reported paid")
        payment_status = (
            "NOT_VERIFIED"
            if paid is None
            else (
                "NOT_COMPARABLE_ANNUAL_SETTLEMENT"
                if due is None
                else (
                    "DEFERRED"
                    if deferred
                    else "MATCH" if paid == due else "DIFFERENCE_TO_REVIEW"
                )
            )
        )
        if payment_status == "DIFFERENCE_TO_REVIEW":
            findings.append(
                {
                    "code": "PAYMENT_DIFFERENCE",
                    "period": period,
                    "due": f"{due:.2f}",
                    "paid": f"{paid:.2f}",
                    "meaning": "Difference only; lateness, omission and remedies need professional review.",
                }
            )
        if (
            module["liquidation_vat"] is not None
            and money(module["liquidation_vat"]) != net
        ):
            findings.append(
                {
                    "code": "REGISTER_LIQUIDATION_DIFFERENCE",
                    "period": period,
                    "register_net_vat": f"{net:.2f}",
                    "reported_liquidation": module["liquidation_vat"],
                    "meaning": "Investigate source entries; no automatic diagnosis of closing-entry errors.",
                }
            )
        output.append(
            {
                "period": period,
                "xml_period": 5 if q4_option else period,
                "rows": {
                    key: None if value is None else f"{value:.2f}"
                    for key, value in rows.items()
                },
                "vp13_method": module["vp13_method"],
                "payment_status": payment_status,
                "evidence": module["evidence"],
            }
        )
        credit = rows["vp14_credit"] or ZERO
        debt = due if deferred else ZERO
    return output
