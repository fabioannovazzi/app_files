"""Source-reference bank extraction with independent coverage and balance checks.

The host interprets statement layout and document purpose. Fixed code reconstructs
values from the PDF and checks exact arithmetic; it never invents transactions or
treats a payment receipt as proof of a complete statement population.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .adapter import _bands, _run_adapter, source_inventory
from .rules import RuleLayout, money_candidate, signed_amount

__all__ = ["read_bank_pdf"]


def read_bank_pdf(
    path: Path, layout: dict[str, Any], *, currency: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read proposed bank movements; failed checks retain unqualified entries."""
    from .recovery import _identity

    identity = _identity(path, currency)
    if layout.get("source_sha256") != identity["source_sha256"]:
        raise ValueError("Bank layout must be bound to the exact PDF")
    if layout.get("recovery_currency") != currency:
        raise ValueError("Bank recovery currency differs from the reviewed layout")
    if layout.get("document_kind") != "bank_statement":
        raise ValueError("Bank recovery requires a reviewed bank_statement document")
    order = layout.get("transaction_order", "ascending")
    if order not in {"ascending", "descending"}:
        raise ValueError("Review ascending or descending statement order")
    bands = _bands(layout, source_role="bank")
    rules = RuleLayout(layout)
    inventory = source_inventory(path, layout, source_role="bank")
    proposal = _run_adapter(layout, inventory)
    if _identity(path, currency) != identity:
        raise ValueError("Source or independent checker changed during bank recovery")
    issues = list(inventory["issues"])
    words = {w["id"]: w for p in inventory["pages"] for w in p["words"]}
    used: set[str] = set()

    def reject(page: int, row: int, reason: str) -> None:
        issues.append({"source_page": page, "source_row": row, "reason": reason})

    def position(word: dict[str, Any]) -> tuple[int, int]:
        return word["page"], word["row"]

    def refs(value: Any, *, optional: bool = False) -> list[dict[str, Any]]:
        if optional and value == []:
            return []
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(v, str) or v not in words for v in value)
            or len(set(value)) != len(value)
        ):
            raise ValueError("invalid_source_reference")
        result = [words[v] for v in value]
        if result != sorted(result, key=lambda w: (*position(w), float(w["x0"]))):
            raise ValueError("source_references_out_of_order")
        return result

    def within(word: dict[str, Any], band: str) -> bool:
        return (
            band in bands
            and bands[band][0] <= float(word["x0"])
            and float(word["x1"]) <= bands[band][1]
            and rules.body[0] <= float(word["top"]) < rules.body[1]
        )

    def money(word: dict[str, Any], column: str) -> Decimal:
        if not within(word, column) or column not in {
            "amount",
            "debit",
            "credit",
            "balance",
        }:
            raise ValueError("amount_outside_reviewed_side")
        if not money_candidate(word["text"]):
            raise ValueError("unsupported_source_amount")
        if rules.amount_issue(word["text"]):
            raise ValueError(rules.amount_issue(word["text"]))
        return signed_amount(word["text"])

    def claim(word: dict[str, Any]) -> None:
        if word["id"] in used:
            raise ValueError("duplicate_source_amount")
        used.add(word["id"])

    controls: dict[str, tuple[Decimal, dict[str, Any]]] = {}
    proposed_controls = layout.get("statement_controls", {})
    if not isinstance(proposed_controls, dict):
        raise ValueError("Statement controls must be reviewed source references")
    for kind, control in proposed_controls.items():
        try:
            if kind not in {
                "opening_balance",
                "closing_balance",
                "debit_total",
                "credit_total",
            }:
                raise ValueError("invalid_bank_control")
            if not isinstance(control, dict) or set(control) != {
                "label",
                "amount",
                "column",
            }:
                raise ValueError("invalid_bank_control")
            amount_word = refs([control["amount"]])[0]
            labels = refs(control["label"])
            if (
                any(position(w) != position(amount_word) for w in labels)
                or not any(c.isalpha() for w in labels for c in w["text"])
                or any(money_candidate(w["text"]) for w in labels)
            ):
                raise ValueError("invalid_bank_control_label")
            value = money(amount_word, control["column"])
            claim(amount_word)
            controls[kind] = (value, amount_word)
        except (ValueError, KeyError, TypeError) as exc:
            reject(
                0,
                0,
                str(exc) if isinstance(exc, ValueError) else "invalid_bank_control",
            )
    balance_controls = {"opening_balance", "closing_balance"} <= controls.keys()
    total_controls = {"debit_total", "credit_total"} <= controls.keys()
    if not balance_controls and not total_controls:
        reject(0, 0, "bank_requires_independent_printed_controls")
    if bool("opening_balance" in controls) != bool("closing_balance" in controls):
        reject(0, 0, "incomplete_bank_balance_controls")
    if bool("debit_total" in controls) != bool("credit_total" in controls):
        reject(0, 0, "incomplete_bank_total_controls")

    records = []
    for candidate in proposal["rows"]:
        page = row = 0
        try:
            if not isinstance(candidate, dict) or set(candidate) != {
                "amount",
                "column",
                "date",
                "value_date",
                "description",
                "reference",
                "balance",
            }:
                raise ValueError("invalid_bank_movement_proposal")
            amount_word = refs([candidate["amount"]])[0]
            page, row = position(amount_word)
            column = candidate["column"]
            if column not in {"amount", "debit", "credit"}:
                raise ValueError("invalid_bank_movement_column")
            value = money(amount_word, column)
            dates = refs(candidate["date"])
            if any(not within(w, "date") or position(w) != (page, row) for w in dates):
                raise ValueError("bank_date_outside_movement")
            date_format = layout.get("date_format", "%d/%m/%Y")
            try:
                date = datetime.strptime(
                    " ".join(w["text"] for w in dates), date_format
                ).date()
            except ValueError as exc:
                raise ValueError("invalid_bank_date") from exc
            value_dates = refs(candidate["value_date"], optional=True)
            value_date = ""
            if value_dates:
                if any(
                    not within(w, "value_date") or position(w) != (page, row)
                    for w in value_dates
                ):
                    raise ValueError("bank_value_date_outside_movement")
                try:
                    value_date = (
                        datetime.strptime(
                            " ".join(w["text"] for w in value_dates), date_format
                        )
                        .date()
                        .isoformat()
                    )
                except ValueError as exc:
                    raise ValueError("invalid_bank_date") from exc
            description = refs(candidate["description"], optional=True)
            reference = refs(candidate["reference"], optional=True)
            for name, tokens in (
                ("description", description),
                ("reference", reference),
            ):
                if any(not within(w, name) for w in tokens):
                    raise ValueError("bank_text_outside_reviewed_column")
            balance_word = (
                refs([candidate["balance"]])[0]
                if candidate["balance"] is not None
                else None
            )
            balance = None
            if balance_word is not None:
                if position(balance_word) != (page, row):
                    raise ValueError("bank_balance_outside_movement")
                balance = money(balance_word, "balance")
            # Bank credits increase the balance; debits decrease it. Signed
            # amount columns already express the source's reviewed cash direction.
            amount = -value if column == "debit" else value
            if column in {"debit", "credit"} and value < 0:
                if rules.negative_semantics != "signed_side":
                    raise ValueError("bank_negative_amount_requires_signed_side")
            claim(amount_word)
            if balance_word is not None:
                claim(balance_word)
            record = {
                "source_file": path.name,
                "source_page": page,
                "source_row": row,
                "entry_date": date.isoformat(),
                "value_date": value_date,
                "line_desc": " ".join(w["text"] for w in description),
                "reference": " ".join(w["text"] for w in reference),
                "amount": str(amount),
                "currency": currency,
                "debit": str(-amount if amount < 0 else Decimal(0)),
                "credit": str(amount if amount > 0 else Decimal(0)),
            }
            records.append((record, description + reference, balance))
        except (ValueError, KeyError, TypeError) as exc:
            reject(
                page,
                row,
                (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "invalid_bank_movement_proposal"
                ),
            )
    records.sort(key=lambda item: (item[0]["source_page"], item[0]["source_row"]))
    for index, (record, tokens, _) in enumerate(records):
        start = record["source_page"], record["source_row"]
        end = (
            (records[index + 1][0]["source_page"], records[index + 1][0]["source_row"])
            if index + 1 < len(records)
            else (len(inventory["pages"]) + 1, 0)
        )
        if any(not start <= position(w) < end for w in tokens):
            reject(*start, "bank_text_crosses_movement")
        if any(
            position(w) == position(c[1]) for w in tokens for c in controls.values()
        ):
            reject(*start, "bank_text_crosses_control")
    # Every source monetary token in the reviewed body needs a disposition.
    # Balanced omissions and unproposed transactions therefore cannot pass.
    monetary = {"amount", "debit", "credit", "balance"} & bands.keys()
    for word in words.values():
        if not rules.body[0] <= float(word["top"]) < rules.body[1]:
            continue
        text_bands = set(bands) - monetary
        if (
            money_candidate(word["text"])
            and word["id"] not in used
            and not any(within(word, name) for name in text_bands)
        ):
            reject(*position(word), "unclaimed_source_amount")
        elif (
            any(within(word, name) for name in monetary)
            and any(c.isdigit() for c in word["text"])
            and not money_candidate(word["text"])
        ):
            reject(*position(word), "unrecognized_numeric_content_in_amount_band")
    total = sum((Decimal(r[0]["amount"]) for r in records), Decimal(0))
    if balance_controls:
        opening, closing = controls["opening_balance"], controls["closing_balance"]
        if opening[0] + total != closing[0]:
            reject(0, 0, "bank_opening_movements_closing_mismatch")
        chronological = records if order == "ascending" else list(reversed(records))
        running = opening[0]
        for record, _, balance in chronological:
            running += Decimal(record["amount"])
            if balance is not None and balance != running:
                reject(
                    record["source_page"],
                    record["source_row"],
                    "bank_running_balance_mismatch",
                )
        if records:
            first = records[0][0]["source_page"], records[0][0]["source_row"]
            last = records[-1][0]["source_page"], records[-1][0]["source_row"]
            before, after = (
                (opening[1], closing[1])
                if order == "ascending"
                else (closing[1], opening[1])
            )
            if not position(before) < first <= last < position(after):
                reject(0, 0, "bank_controls_do_not_bound_movements")
    elif any(balance is not None for _, _, balance in records):
        reject(0, 0, "bank_running_balances_require_opening_control")
    if total_controls:
        for side in ("debit", "credit"):
            expected = sum((Decimal(r[0][side]) for r in records), Decimal(0))
            if controls[side + "_total"][0] != expected:
                reject(0, 0, "bank_printed_movement_total_mismatch")
    if not records:
        reject(0, 0, "bank_statement_has_no_readable_movements")
    accepted = bool(records) and not issues
    diagnostics = {
        "accepted": accepted,
        "reason": None if accepted else "bank_pdf_incomplete_or_unbalanced",
        "page_count": len(inventory["pages"]),
        "readable_rows": [r[0] for r in records],
        "readable_row_count": len(records),
        "rejected_rows": issues[:50],
        "unresolved_issues": issues,
        "population_operations_allowed": False,
        "statement_control_count": len(controls),
    }
    return [r[0] for r in records] if accepted else [], diagnostics
