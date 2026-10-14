"""Named review queues over existing producer item types; no semantic inference."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

__all__ = ["intake_queue", "xml_invoice_page", "notice_reference_page"]

VIEWS = {
    "INTAKE_FISCAL": {"extracted_fiscal_field", "document_inventory", "uncertain_file"},
    "INTAKE_XML": {
        "formal_xml_anomaly",
        "formal_xml_duplicate_group",
        "duplicate_warning",
    },
    "INTAKE_NOTES": {
        "draft_memo_section",
        "missing_document_request",
        "uncertain_file",
    },
}


def intake_queue(
    items: list[dict[str, Any]], view: str
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Filter the complete queue before paging and retain exact item identities."""
    if view not in {"REVIEW", *VIEWS}:
        raise ValueError("Unknown intake review view")

    def matches(item: dict[str, Any], requested: str) -> bool:
        if item["item_type"] not in VIEWS[requested]:
            return False
        if requested == "INTAKE_XML" and item["item_type"] == "duplicate_warning":
            return str(item.get("source_path", "")).lower().endswith(".xml")
        return True

    counts = {key: sum(matches(item, key) for item in items) for key in VIEWS}
    return (
        items if view == "REVIEW" else [item for item in items if matches(item, view)],
        counts,
    )


def xml_invoice_page(
    directory: Path, offset: int, item_id: str | None = None
) -> dict[str, Any]:
    """Page exact producer invoice bodies without making clean bodies mandatory review items."""
    path = directory / "extracted/fatture_xml.jsonl"
    if not path.is_file():
        return {"items": [], "total": 0, "selection": None}
    if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("XML body records escape their declared producer directory")
    manifest = json.loads(
        (directory / "final_artifacts.json").read_text(encoding="utf-8")
    )
    expected = next(
        (
            record
            for record in manifest["outputs"]
            if record["path"] == "extracted/fatture_xml.jsonl"
        ),
        None,
    )
    if expected is None:
        raise ValueError("XML bodies are absent from the producer artifact manifest")
    fingerprint = hashlib.sha256()
    items = []
    selection = None
    total = 0
    with path.open("rb") as handle:
        while raw := handle.readline(2_000_001):
            fingerprint.update(raw)
            if len(raw) > 2_000_000:
                raise ValueError(
                    "One XML body exceeds the complete-record native limit"
                )
            if not raw.strip():
                continue
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("XML producer body must be an object")
            total += 1
            reference = f"xml-body-{total}"
            if offset <= total - 1 < offset + 30 or reference == item_id:
                item = {
                    "id": reference,
                    "item_type": "xml_invoice_body",
                    "title": f"{data['file_name']} · {data['body_index']}",
                    "source_path": data["relative_path"],
                    "output_path": "extracted/fatture_xml.jsonl",
                    "allowed_actions": [],
                    "data": data,
                    "evidence": [
                        {
                            "kind": "verified_producer_metadata",
                            "source_sha256": data["source_sha256"],
                            "body_index": data["body_index"],
                        }
                    ],
                }
                if offset <= total - 1 < offset + 30:
                    items.append(item)
                if reference == item_id:
                    selection = item
    if fingerprint.hexdigest() != expected["sha256"]:
        raise ValueError("XML body bytes differ from the producer artifact manifest")
    return {"items": items, "total": total, "selection": selection}


def notice_reference_page(
    directory: Path, offset: int, item_id: str | None = None
) -> dict[str, Any]:
    """Present producer-extracted dates/references without converting them to legal deadlines."""
    relative = "avviso/deadlines_and_amounts.csv"
    path = directory / relative
    if not path.is_file():
        return {"items": [], "total": 0, "selection": None}
    if (
        path.is_symlink()
        or not path.resolve().is_relative_to(directory.resolve())
        or path.stat().st_size > 8_000_000
    ):
        raise ValueError(
            "Notice reference source is unavailable or exceeds its complete-file limit"
        )
    raw = path.read_bytes()
    manifest = json.loads(
        (directory / "final_artifacts.json").read_text(encoding="utf-8")
    )
    expected = next(
        (record for record in manifest["outputs"] if record["path"] == relative), None
    )
    if expected is None or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
        raise ValueError(
            "Notice references differ from their producer artifact manifest"
        )
    records = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    items = []
    selection = None
    for index, record in enumerate(records, 1):
        if record["type"] not in {"date", "amount", "protocol"}:
            raise ValueError("Unknown producer notice reference type")
        reference = f"notice-ref-{index}"
        if offset <= index - 1 < offset + 30 or reference == item_id:
            item = {
                "id": reference,
                "item_type": "notice_extracted_reference",
                "title": record["value"],
                "source_path": record["relative_path"],
                "output_path": relative,
                "allowed_actions": [],
                "data": record,
                "evidence": [{"kind": "producer_extraction_not_legal_deadline"}],
            }
            if offset <= index - 1 < offset + 30:
                items.append(item)
            if reference == item_id:
                selection = item
    return {"items": items, "total": len(records), "selection": selection}
