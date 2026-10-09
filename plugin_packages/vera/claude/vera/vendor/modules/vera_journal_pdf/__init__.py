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
                            "width": page.width,
                            "height": page.height,
                            "word_count": len(words),
                            "truncated": len(words) > 300,
                            "words": [
                                {
                                    "text": str(w["text"])[:100],
                                    "x0": w["x0"],
                                    "x1": w["x1"],
                                    "top": w["top"],
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
        "purpose": "Physical layout evidence for model-led review; no postings extracted",
    }


def _read_registration_pdf(
    path: Path,
    layout: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read a reviewed registration layout, keeping physical posting lineage.

    Fixed coordinates are justified by their explicit reviewed meaning and
    exact registration balance checks; unreviewed column semantics never
    authorize these rows to enter a sampling population.
    """
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

    columns = layout.get("columns")
    required = {"account_debit", "account_credit", "debit", "credit", "description"}
    if not isinstance(columns, dict) or set(columns) != required:
        raise ValueError(
            "PDF layout needs exact account, description, debit and credit bands"
        )
    bands: dict[str, tuple[float, float]] = {}
    for field, bounds in columns.items():
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                for v in bounds
            )
            or not 0 <= bounds[0] < bounds[1]
        ):
            raise ValueError(f"Invalid PDF coordinate band: {field}")
        bands[field] = (float(bounds[0]), float(bounds[1]))
    ordered = sorted(bands.values())
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("PDF coordinate bands must not overlap")
    body = layout.get("body")
    if (
        not isinstance(body, list)
        or len(body) != 2
        or any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            for v in body
        )
        or not 0 <= body[0] < body[1]
    ):
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
    records: list[dict[str, Any]] = []
    registration: dict[str, Any] | None = None
    pending_accounts: dict[str, str] = {}
    pending_description = ""
    errors: list[dict[str, Any]] = []
    candidate_count = 0
    page_count = 0

    def reject(page: int, row: int, reason: str) -> None:
        if len(errors) < 50:
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
                    break
                words = page.extract_words(x_tolerance=1, y_tolerance=2)
                lines: list[list[dict[str, Any]]] = []
                for word in sorted(
                    words, key=lambda w: (float(w["top"]), float(w["x0"]))
                ):
                    if not body[0] <= float(word["top"]) < body[1]:
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
                    match = header.fullmatch(text)
                    if match:
                        close_registration(page_number, row_number)
                        pending_accounts = {}
                        pending_description = ""
                        registration = {
                            "date": datetime.strptime(match["date"], "%d/%m/%Y").date(),
                            "number": match["number"],
                            "description": match["description"].strip(),
                            "debit": ZERO,
                            "credit": ZERO,
                            "postings": 0,
                        }
                        continue
                    match = continuation.fullmatch(text)
                    if match:
                        if (
                            registration is None
                            or registration["date"]
                            != datetime.strptime(match["date"], "%d/%m/%Y").date()
                        ):
                            reject(
                                page_number,
                                row_number,
                                "continuation_without_matching_registration",
                            )
                        continue
                    if any(
                        text.casefold().startswith(prefix.casefold())
                        for prefix in ignored
                    ):
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
                        elif money.fullmatch(str(word["text"])):
                            unassigned_money = True
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
                        continue
                    emitted = False
                    for side in ("debit", "credit"):
                        amount_text = values[side]
                        if not amount_text:
                            continue
                        candidate_count += 1
                        if (
                            not money.fullmatch(amount_text)
                            or registration is None
                            or side not in pending_accounts
                        ):
                            reject(
                                page_number,
                                row_number,
                                "posting_requires_registration_account_and_amount",
                            )
                            continue
                        amount = Decimal(amount_text.replace(".", "").replace(",", "."))
                        if amount < ZERO:
                            reject(
                                page_number,
                                row_number,
                                "negative_amount_side_requires_review",
                            )
                            continue
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
                            "debit": str(amount) if side == "debit" else "0",
                            "credit": str(amount) if side == "credit" else "0",
                            "currency": "EUR",
                            "unit": "currency",
                            "reported_increment": "0.01",
                            "source_file": path.name,
                            "source_sheet": "PDF",
                            "source_page": page_number,
                            "source_row": row_number,
                        }
                        records.append(record)
                        registration[side] += amount
                        registration["postings"] += 1
                        emitted = True
                    if emitted:
                        pending_description = ""
                    elif description and not pending_accounts and records:
                        # Description-only continuations belong to the preceding posting.
                        previous = records[-1]
                        previous["line_desc"] = " ".join(
                            filter(None, [previous["line_desc"], description])
                        )
                        pending_description = ""
                if errors:
                    break
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
        "rejected_rows": errors,
        "reason": None if accepted else "registration_pdf_incomplete_or_unbalanced",
    }


def read_registration_pdf(
    path: Path,
    layout: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reconstruct the complete source, converting PDF decoder failures to diagnostics."""
    from pdfplumber.utils.exceptions import PdfminerException

    try:
        return _read_registration_pdf(path, layout)
    except PdfminerException as exc:
        raise ValueError("PDF source could not be reconstructed") from exc
