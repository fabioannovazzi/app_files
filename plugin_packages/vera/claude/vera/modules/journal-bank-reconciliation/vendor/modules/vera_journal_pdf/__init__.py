"""Physical reconstruction of reviewed registration-style text PDF journals."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

__all__ = ["inspect_registration_pdf", "read_registration_pdf"]
LOGGER = logging.getLogger(__name__)
ZERO = Decimal("0")


def _coordinate(value: Any) -> float:
    """Validate a finite PDF coordinate; persisted decimals use canonical text."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("PDF coordinates must be finite decimal text or numbers")
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(
            "PDF coordinates must be finite decimal text or numbers"
        ) from exc
    if not math.isfinite(result):
        raise ValueError("PDF coordinates must be finite decimal text or numbers")
    return result


def inspect_registration_pdf(path: Path) -> dict[str, Any]:
    """Return bounded physical evidence; the host model selects column semantics."""
    import pdfplumber
    from pdfplumber.utils.exceptions import PdfminerException

    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    samples: list[dict[str, Any]] = []
    try:
        with pdfplumber.open(path) as document:
            count = len(document.pages)
            for index in sorted({0, min(1, count - 1), count - 1}) if count else []:
                page = document.pages[index]
                try:
                    words = page.extract_words(x_tolerance=1, y_tolerance=2)
                    samples.append(
                        {
                            "page": index + 1,
                            "width": str(page.width),
                            "height": str(page.height),
                            "word_count": len(words),
                            "truncated": len(words) > 300,
                            "words": [
                                {
                                    "text": str(w["text"])[:100],
                                    "x0": str(w["x0"]),
                                    "x1": str(w["x1"]),
                                    "top": str(w["top"]),
                                }
                                for w in words[:300]
                            ],
                        }
                    )
                finally:
                    page.close()
    except PdfminerException as exc:
        raise ValueError("PDF source could not be inspected") from exc
    return {
        "source_sha256": digest,
        "page_count": count,
        "sampled_pages": samples,
        "coordinate_unit": "PDF points; canonical decimal text",
        "purpose": "Physical layout evidence for model-led review; no postings extracted",
    }


def _read_registration_pdf(
    path: Path,
    layout: dict[str, Any] | None = None,
    *,
    currency: str = "EUR",
    retain_partial: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read a reviewed registration layout, keeping physical posting lineage.

    Fixed coordinates are justified by their explicit reviewed meaning and
    exact registration balance checks; unreviewed column semantics never
    authorize these rows to enter a sampling population.
    """
    if layout and layout.get("recovery_currency", currency) != currency:
        raise ValueError(
            "PDF recovery currency differs from the reviewed workflow currency"
        )
    if layout and "agent_adapter" in layout:
        from .adapter import read_adapter_pdf

        return read_adapter_pdf(path, layout, currency=currency)
    if not layout:
        return [], {
            "parser": "text_pdf",
            "accepted": False,
            "candidate_row_count": 0,
            "emitted_row_count": 0,
            "rejected_row_count": 0,
            "rejected_rows": [],
            "status": "unsupported_source_layout",
            "reason": "reviewed_registration_pdf_layout_required",
        }
    import pdfplumber
    from pdfplumber.utils.exceptions import PdfminerException

    columns = layout.get("columns")
    required = {"account_debit", "account_credit", "debit", "credit", "description"}
    if not isinstance(columns, dict) or set(columns) != required:
        raise ValueError(
            "PDF layout needs exact account, description, debit and credit bands"
        )
    bands: dict[str, tuple[float, float]] = {}
    for field, bounds in columns.items():
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError(f"Invalid PDF coordinate band: {field}")
        low, high = (_coordinate(value) for value in bounds)
        if not 0 <= low < high:
            raise ValueError(f"Invalid PDF coordinate band: {field}")
        bands[field] = (low, high)
    ordered = sorted(bands.values())
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("PDF coordinate bands must not overlap")
    body_value = layout.get("body")
    if not isinstance(body_value, list) or len(body_value) != 2:
        raise ValueError("PDF layout needs a finite top/bottom body range")
    body = tuple(_coordinate(value) for value in body_value)
    if not 0 <= body[0] < body[1]:
        raise ValueError("PDF layout needs a finite top/bottom body range")
    ignored = layout.get("ignored_line_prefixes", [])
    if not isinstance(ignored, list) or any(
        not isinstance(v, str) or not v.strip() for v in ignored
    ):
        raise ValueError("PDF ignored line prefixes must be explicit nonempty labels")
    header = re.compile(
        r"^(?P<number>\d+)\s*-{2,}\s*(?P<date>\d{2}/\d{2}/\d{4})\s*-{2,}(?P<description>.*)$"
    )
    continuation = re.compile(
        r"^seguito registrazione del\s+(?P<date>\d{2}/\d{2}/\d{4})\s*$", re.IGNORECASE
    )
    money = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$|^-?\d+,\d{2}$")
    from .rules import (
        CONTINUATION,
        HEADER,
        RULE_KEYS,
        RuleLayout,
        money_candidate,
        negative_notation,
        signed_amount,
    )

    rules = RuleLayout(layout) if RULE_KEYS.intersection(layout) else None
    try:
        eligibility = (
            rules.negative_eligibility(path, bands) if rules is not None else None
        )
    except PdfminerException:
        if not retain_partial:
            raise
        # Read the surviving pages below; a later decoder failure must not erase
        # postings already readable elsewhere in the immutable source.
        eligibility = None
        if rules is not None:
            rules.removed = 0
    if (
        rules is not None
        and eligibility is not None
        and eligibility["issue_count"]
        and not retain_partial
    ):
        return [], {
            "parser": "registration_pdf",
            "accepted": False,
            "page_count": eligibility["page_count"],
            "candidate_row_count": 0,
            "emitted_row_count": 0,
            "rejected_row_count": eligibility["issue_count"],
            "rejected_rows": eligibility["issues"][:50],
            "rejected_rows_truncated": eligibility["issue_count"] > 50,
            "negative_amount_eligibility": eligibility,
            "reason": "registration_pdf_incomplete_or_unbalanced",
            **rules.diagnostics(),
        }
    if rules is not None and rules.border:
        header, continuation = HEADER, CONTINUATION
    records: list[dict[str, Any]] = []
    registration: dict[str, Any] | None = None
    pending_accounts: dict[str, str] = {}
    pending_description = ""
    errors: list[dict[str, Any]] = (
        list(eligibility["issues"]) if eligibility and retain_partial else []
    )
    candidate_count = 0
    page_count = 0

    def reject(page: int, row: int, reason: str) -> None:
        if retain_partial or len(errors) < 50:
            errors.append({"source_page": page, "source_row": row, "reason": reason})

    def close_registration(page: int, row: int) -> None:
        if registration is not None:
            if registration["postings"] == 0:
                reject(page, row, "registration_has_no_postings")
            if registration["debit"] != registration["credit"]:
                reject(page, row, "registration_debit_credit_do_not_balance")
        if pending_accounts:
            reject(page, row, "account_without_amount")

    with pdfplumber.open(path) as document:
        for page_number, page in enumerate(document.pages, start=1):
            page_count = page_number
            LOGGER.info("PDF_JOURNAL_PAGE source=%s page=%s", path.name, page_number)
            try:
                if body[1] > page.height or ordered[-1][1] > page.width:
                    reject(page_number, 0, "reviewed_coordinates_outside_page")
                    if not retain_partial:
                        break
                    registration = None
                    pending_accounts = {}
                    pending_description = ""
                    continue
                words = (
                    rules.words(page, page_number, reject)
                    if rules is not None
                    else page.extract_words(x_tolerance=1, y_tolerance=2)
                )
                page_postings = 0
                continuation_seen = False
                header_seen = False
                lines: list[list[dict[str, Any]]] = []
                for word in sorted(
                    words, key=lambda w: (float(w["top"]), float(w["x0"]))
                ):
                    if rules is None and not body[0] <= float(word["top"]) < body[1]:
                        continue
                    if (
                        not lines
                        or abs(float(lines[-1][0]["top"]) - float(word["top"])) > 2
                    ):
                        lines.append([])
                    lines[-1].append(word)
                if not lines:
                    reject(page_number, 0, "page_has_no_body_text")
                for row_number, line in enumerate(lines, start=1):
                    line.sort(key=lambda w: float(w["x0"]))
                    text = " ".join(str(w["text"]) for w in line).strip()
                    if rules is not None:
                        if rules.total(line, bands, page_number, row_number, reject):
                            continue
                        if not body[0] <= float(line[0]["top"]) < body[1]:
                            if (
                                any(money_candidate(str(w["text"])) for w in line)
                                or header.fullmatch(text)
                                or continuation.fullmatch(text)
                            ):
                                reject(
                                    page_number,
                                    row_number,
                                    "accounting_content_outside_reviewed_body",
                                )
                            continue
                        if rules.border and set(text) <= set("+- "):
                            continue
                    match = header.fullmatch(text)
                    if match:
                        header_seen = True
                        if rules is not None:
                            if match["number"] in rules.seen_registrations:
                                reject(
                                    page_number,
                                    row_number,
                                    "duplicate_registration_number",
                                )
                            rules.seen_registrations.add(match["number"])
                        close_registration(page_number, row_number)
                        pending_accounts = {}
                        pending_description = ""
                        try:
                            registration_date = datetime.strptime(
                                match["date"], "%d/%m/%Y"
                            ).date()
                        except ValueError:
                            if not retain_partial:
                                raise
                            reject(page_number, row_number, "invalid_registration_date")
                            registration = None
                            continue
                        registration = {
                            "date": registration_date,
                            "number": match["number"],
                            "description": match["description"].strip(),
                            "debit": ZERO,
                            "credit": ZERO,
                            "postings": 0,
                        }
                        continue
                    match = continuation.fullmatch(text)
                    if match:
                        continuation_seen = True
                        try:
                            continuation_date = datetime.strptime(
                                match["date"], "%d/%m/%Y"
                            ).date()
                        except ValueError:
                            if not retain_partial:
                                raise
                            reject(page_number, row_number, "invalid_continuation_date")
                            registration = None
                            pending_accounts = {}
                            pending_description = ""
                            continue
                        if (
                            registration is None
                            or registration["date"] != continuation_date
                        ):
                            reject(
                                page_number,
                                row_number,
                                "continuation_without_matching_registration",
                            )
                        continue
                    if (
                        rules is not None
                        and rules.border
                        and (
                            text.startswith(("+", "-"))
                            or "seguito registrazione" in text.casefold()
                        )
                    ):
                        reject(
                            page_number,
                            row_number,
                            "unrecognized_decorated_registration_line",
                        )
                        if retain_partial:
                            registration = None
                            pending_accounts = {}
                            pending_description = ""
                        continue
                    if any(
                        (
                            text.casefold() == prefix.casefold()
                            if rules is not None
                            else text.casefold().startswith(prefix.casefold())
                        )
                        for prefix in ignored
                    ):
                        if rules is not None and any(
                            money_candidate(str(w["text"])) for w in line
                        ):
                            reject(
                                page_number,
                                row_number,
                                "monetary_line_cannot_be_ignored",
                            )
                        continue
                    cells: dict[str, list[str]] = {field: [] for field in bands}
                    unassigned_money = False
                    for word in line:
                        center = (float(word["x0"]) + float(word["x1"])) / 2
                        owners = [
                            field
                            for field, (left, right) in bands.items()
                            if left <= center < right
                        ]
                        if len(owners) == 1:
                            owner = owners[0]
                            left, right = bands[owner]
                            if owner != "description" and (
                                float(word["x0"]) < left - 1
                                or float(word["x1"]) > right + 1
                            ):
                                reject(
                                    page_number,
                                    row_number,
                                    "word_crosses_reviewed_column",
                                )
                            cells[owner].append(str(word["text"]))
                        elif (
                            money_candidate(str(word["text"]))
                            if rules is not None
                            else money.fullmatch(str(word["text"]))
                        ):
                            unassigned_money = True
                        elif rules is not None:
                            reject(
                                page_number, row_number, "text_outside_reviewed_bands"
                            )
                    values = {
                        field: " ".join(parts).strip() for field, parts in cells.items()
                    }
                    if unassigned_money:
                        reject(
                            page_number,
                            row_number,
                            "monetary_value_outside_reviewed_bands",
                        )
                    for side in ("debit", "credit"):
                        account = values[f"account_{side}"]
                        if account:
                            if side in pending_accounts:
                                reject(
                                    page_number,
                                    row_number,
                                    "second_account_before_amount",
                                )
                            pending_accounts[side] = account
                    description = values["description"]
                    if description:
                        pending_description = " ".join(
                            filter(None, [pending_description, description])
                        )
                    if values["debit"] and values["credit"]:
                        reject(
                            page_number,
                            row_number,
                            "two_posting_sides_on_one_physical_row_require_review",
                        )
                        if retain_partial:
                            pending_accounts = {}
                            pending_description = ""
                        continue
                    emitted = False
                    for side in ("debit", "credit"):
                        amount_text = values[side]
                        if not amount_text:
                            continue
                        candidate_count += 1
                        if rules is not None:
                            if rules.page_total_count:
                                reject(
                                    page_number,
                                    row_number,
                                    "posting_after_running_total",
                                )
                            if (
                                page_number > 1
                                and not header_seen
                                and not continuation_seen
                            ):
                                reject(
                                    page_number,
                                    row_number,
                                    "posting_without_page_continuation",
                                )
                        notation = negative_notation(amount_text)
                        issue = (
                            rules.amount_issue(amount_text)
                            if rules is not None
                            else (
                                "unsupported_negative_amount_notation"
                                if notation in ("trailing_minus", "parentheses")
                                else None
                            )
                        )
                        if issue:
                            reject(page_number, row_number, issue)
                            if retain_partial:
                                pending_accounts.pop(side, None)
                            continue
                        if (
                            not (
                                money_candidate(amount_text)
                                if rules is not None
                                else money.fullmatch(amount_text)
                            )
                            or registration is None
                            or side not in pending_accounts
                        ):
                            reject(
                                page_number,
                                row_number,
                                "posting_requires_registration_account_and_amount",
                            )
                            if retain_partial:
                                pending_accounts.pop(side, None)
                            continue
                        amount = signed_amount(amount_text)
                        source_amount = amount
                        output_side = side
                        if amount < ZERO and rules is None:
                            reject(
                                page_number,
                                row_number,
                                "negative_amount_side_requires_review",
                            )
                            continue
                        if (
                            notation is not None
                            and rules is not None
                            and rules.negative_semantics == "opposite_side"
                        ):
                            output_side = "credit" if side == "debit" else "debit"
                            amount = -amount
                        record = {
                            "entry_date": registration["date"].isoformat(),
                            "movement_number": registration["number"],
                            "account": pending_accounts.pop(side),
                            "line_desc": " ".join(
                                filter(
                                    None,
                                    [registration["description"], pending_description],
                                )
                            ),
                            "debit": str(amount) if output_side == "debit" else "0",
                            "credit": str(amount) if output_side == "credit" else "0",
                            "currency": currency,
                            "unit": "currency",
                            "reported_increment": "0.01",
                            "source_file": path.name,
                            "source_sheet": "PDF",
                            "source_page": page_number,
                            "source_row": row_number,
                            **(
                                {
                                    "source_amount_text": amount_text,
                                    "source_amount_side": side,
                                    "negative_amount_semantics": rules.negative_semantics,
                                }
                                if notation is not None and rules is not None
                                else {}
                            ),
                        }
                        records.append(record)
                        page_postings += 1
                        if rules is not None:
                            # Printed totals use signed source columns even when
                            # the reviewed output moves reversals to the other side.
                            rules.running[side] += source_amount
                        registration[output_side] += amount
                        registration["postings"] += 1
                        emitted = True
                    if emitted:
                        pending_description = ""
                    elif (
                        description
                        and not pending_accounts
                        and records
                        and (
                            rules is None
                            or (
                                registration is not None
                                and registration["postings"] > 0
                            )
                        )
                    ):
                        # Description-only continuations belong to the preceding posting.
                        previous = records[-1]
                        previous["line_desc"] = " ".join(
                            filter(None, [previous["line_desc"], description])
                        )
                        pending_description = ""
                if rules is not None:
                    if not page_postings:
                        reject(page_number, 0, "page_has_no_postings")
                    rules.close_page(page_number, reject)
                if errors and not retain_partial:
                    break
            except PdfminerException:
                if not retain_partial:
                    raise
                reject(page_number, 0, "page_decode_failed")
                registration = None
                pending_accounts = {}
                pending_description = ""
            finally:
                page.close()
    close_registration(page_count, 0)
    accepted = bool(records) and not errors
    qualified_records = records if accepted else []
    return qualified_records, {
        "parser": "registration_pdf",
        "accepted": accepted,
        "page_count": page_count,
        "candidate_row_count": candidate_count,
        "emitted_row_count": len(qualified_records),
        "rejected_row_count": len(errors),
        "rejected_rows": errors[:50],
        **(
            {
                "readable_rows": records,
                "readable_row_count": len(records),
                "unresolved_issues": errors,
                "requires_mapping_qualification": True,
                "negative_amount_eligibility": eligibility,
            }
            if retain_partial
            else {}
        ),
        "reason": None if accepted else "registration_pdf_incomplete_or_unbalanced",
        **(rules.diagnostics() if rules is not None else {}),
    }


def read_registration_pdf(
    path: Path,
    layout: dict[str, Any] | None = None,
    *,
    currency: str = "EUR",
    retain_partial: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reconstruct the complete source, converting PDF decoder failures to diagnostics."""
    from pdfplumber.utils.exceptions import PdfminerException

    try:
        return _read_registration_pdf(
            path, layout, currency=currency, retain_partial=retain_partial
        )
    except PdfminerException as exc:
        raise ValueError("PDF source could not be reconstructed") from exc
