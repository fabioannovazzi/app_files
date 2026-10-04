"""Read reviewed invoice evidence without inventing an electronic invoice format."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

__all__ = ["load_reviewed_invoices"]


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing {name}")
    return value


def _amount(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", value)
        or abs(Decimal(value)) > Decimal("999999999999.99")
    ):
        raise ValueError("Expected reviewed canonical decimal amount")
    return value


def load_reviewed_invoices(path: Path) -> list[dict[str, Any]]:
    """Bind reviewed fields and line locators to exact source files and extract digest."""
    payload = json.loads(path.read_text())
    if (
        payload.get("schema_version") != "vera.reviewed_invoices.v1"
        or payload.get("jurisdiction") != "CH-GE"
    ):
        raise ValueError("Expected reviewed CH-GE invoice population")
    review = payload.get("professional_review", {})
    content = {k: v for k, v in payload.items() if k != "professional_review"}
    content_hash = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    if review.get("content_sha256") != content_hash or review.get(
        "reviewer_role"
    ) not in {"authorized_user", "professional_reviewer"}:
        raise ValueError(
            "Invoice extraction needs a decision bound to its exact content"
        )
    _text(review.get("reviewer_ref"), "reviewer reference")
    date.fromisoformat(review["reviewed_at"])
    if not isinstance(payload.get("invoices"), list) or not payload["invoices"]:
        raise ValueError("Reviewed invoice population is empty")
    invoices = []
    for index, row in enumerate(payload["invoices"]):
        relative = Path(_text(row.get("source_path"), "source path"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(
                "Invoice source must be relative to the reviewed population"
            )
        source = (path.parent / relative).resolve(strict=True)
        if not source.is_relative_to(path.parent.resolve()) or not source.is_file():
            raise ValueError("Invoice source leaves the bound population")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if source_hash != row.get("source_sha256"):
            raise ValueError("Invoice source digest mismatch")
        fields = row["fields"]
        required = {
            "supplier_vat",
            "supplier_name",
            "customer_tax_id",
            "customer_name",
            "invoice_number",
            "invoice_date",
            "document_type",
            "currency",
            "gross_amount",
            "lines",
            "vat_summaries",
            "credit_note",
        }
        if set(fields) != required:
            raise ValueError(
                "Reviewed invoice fields differ from the extraction contract"
            )
        for key in required - {
            "lines",
            "vat_summaries",
            "credit_note",
            "supplier_vat",
            "customer_tax_id",
            "customer_name",
        }:
            _text(fields[key], key)
        for key in ("supplier_vat", "customer_tax_id", "customer_name"):
            if not isinstance(fields[key], str):
                raise ValueError(
                    "Unknown party fields must be empty text, never inferred"
                )
        if fields["currency"] not in {"CHF", "EUR"}:
            raise ValueError("Qualify the invoice currency explicitly (CHF or EUR)")
        date.fromisoformat(fields["invoice_date"])
        _amount(fields["gross_amount"])
        if type(fields["credit_note"]) is not bool:
            raise ValueError("Credit-note meaning must be reviewed explicitly")
        _text(row.get("locator"), "invoice locator")
        if not isinstance(fields["lines"], list) or not fields["lines"]:
            raise ValueError(
                "Reviewed invoice lines are required for semantic screening"
            )
        for line in fields["lines"]:
            _text(line.get("description"), "line description")
            _text(line.get("locator"), "line locator")
            _amount(line["line_total"])
        if not isinstance(fields["vat_summaries"], list):
            raise ValueError("Use an explicit empty tax summary when not established")
        for summary in fields["vat_summaries"]:
            for key in ("vat_rate", "taxable_amount", "vat_amount"):
                _amount(summary[key])
        invoices.append(
            {
                **fields,
                "invoice_id": hashlib.sha256(
                    f"{content_hash}:{index}".encode()
                ).hexdigest()[:24],
                "body_index": index,
                "source_identifier": relative.as_posix(),
                "source_sha256": source_hash,
                "source_locator": row["locator"],
                "source_format": "reviewed_document",
                "input_valid": True,
                "extraction_sha256": content_hash,
                "parse_error": "",
            }
        )
    return invoices
