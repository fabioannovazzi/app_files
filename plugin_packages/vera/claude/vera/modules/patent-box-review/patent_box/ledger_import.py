"""Evidence-preserving ledger intake and explicitly proposed normalization.

Code parses selected cells, checks a closed population and performs Decimal
arithmetic. The host model proposes field meanings, exclusions, rates, fiscal
limits and duplicate dispositions; those are not inferred by a classifier.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import defaultdict
from decimal import Decimal, localcontext
from pathlib import Path, PurePosixPath
from typing import Any, TypedDict

from .contracts import ContractError, canonical_hash, indexed, validate
from .engine import money

__all__ = ["inspect_table", "normalize_population", "normalization_markdown"]
MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 100000
MAX_COLUMNS = 500
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class _ParsedAmount(TypedDict):
    amount: Decimal
    currency: str
    original_ledger_key: str


def _column(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _source(path: Path, evidence: dict[str, Any]) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ContractError("Ledger must be a bounded selected regular file")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != evidence["sha256"]:
        raise ContractError("Selected ledger bytes changed")
    return raw


def _csv_rows(
    raw: bytes, options: dict[str, Any]
) -> dict[int, dict[str, dict[str, str]]]:
    if options["delimiter"] not in (",", ";", "\t") or options["encoding"] not in (
        "utf-8",
        "utf-8-sig",
        "cp1252",
    ):
        raise ContractError("Choose an explicit supported CSV delimiter and encoding")
    rows = {}
    reader = csv.reader(
        io.StringIO(raw.decode(options["encoding"])),
        delimiter=options["delimiter"],
        strict=True,
    )
    for number, values in enumerate(reader, 1):
        if number > MAX_ROWS or len(values) > MAX_COLUMNS:
            raise ContractError("CSV population exceeds table limits")
        rows[number] = {
            _column(i): {"value": value, "kind": "TEXT"}
            for i, value in enumerate(values, 1)
        }
    return rows


def _xlsx_rows(raw: bytes, sheet_name: str) -> dict[int, dict[str, dict[str, str]]]:
    """Read raw OOXML numbers exactly; never evaluate formulas or external links."""
    from defusedxml import ElementTree

    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if (
            len(names) > 2048
            or len(names) != len(set(names))
            or sum(i.file_size for i in infos) > 64 * 1024 * 1024
        ):
            raise ContractError(
                "Workbook archive exceeds bounds or has duplicate entries"
            )
        if any(
            i.file_size > MAX_BYTES
            or PurePosixPath(i.filename).is_absolute()
            or ".." in PurePosixPath(i.filename).parts
            for i in infos
        ):
            raise ContractError("Workbook contains an unsafe or oversized part")

        def xml(name: str) -> Any:
            if name not in names:
                raise ContractError("Required worksheet part is missing")
            return ElementTree.fromstring(
                archive.read(name),
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )

        workbook = xml("xl/workbook.xml")
        chosen = [
            s
            for s in workbook.findall("s:sheets/s:sheet", NS)
            if s.attrib["name"] == sheet_name
        ]
        if len(chosen) != 1:
            raise ContractError("Select one exact workbook sheet")
        rid = chosen[0].attrib[
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        ]
        relationships = xml("xl/_rels/workbook.xml.rels")
        targets = [r for r in relationships if r.attrib.get("Id") == rid]
        if len(targets) != 1 or targets[0].attrib.get("TargetMode") == "External":
            raise ContractError("External or ambiguous worksheet relationship")
        target = PurePosixPath(targets[0].attrib["Target"])
        if ".." in target.parts:
            raise ContractError("Worksheet relationship traversal is forbidden")
        part = (
            str(target).lstrip("/")
            if target.is_absolute()
            else str(PurePosixPath("xl") / target)
        )
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = [
                "".join(
                    t.text or ""
                    for t in node.findall("s:t", NS) + node.findall("s:r/s:t", NS)
                )
                for node in xml("xl/sharedStrings.xml").findall("s:si", NS)
            ]
        sheet = xml(part)
        rows: dict[int, dict[str, dict[str, str]]] = {}
        for row in sheet.findall("s:sheetData/s:row", NS):
            number = int(row.attrib["r"])
            if not 1 <= number <= MAX_ROWS or number in rows:
                raise ContractError("Invalid or duplicate worksheet row")
            cells: dict[str, dict[str, str]] = {}
            for cell in row.findall("s:c", NS):
                address = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*)", cell.attrib["r"])
                if address is None or int(address.group(2)) != number:
                    raise ContractError(
                        "Worksheet cell location disagrees with its row"
                    )
                column = address.group(1)
                if column in cells or len(cells) >= MAX_COLUMNS:
                    raise ContractError("Duplicate cell or excessive worksheet width")
                value_node = cell.find("s:v", NS)
                value = (
                    value_node.text
                    if value_node is not None and value_node.text
                    else ""
                )
                formula = cell.find("s:f", NS)
                cell_type = cell.attrib.get("t", "n")
                if formula is not None:
                    value, kind = formula.text or "", "FORMULA"
                elif cell_type == "s":
                    position = int(value)
                    if not 0 <= position < len(shared):
                        raise ContractError("Invalid shared-string reference")
                    value, kind = shared[position], "TEXT"
                elif cell_type == "inlineStr":
                    value = "".join(n.text or "" for n in cell.findall("s:is//s:t", NS))
                    kind = "TEXT"
                else:
                    kind = {
                        "n": "NUMBER",
                        "str": "TEXT",
                        "b": "BOOLEAN",
                        "e": "ERROR",
                        "d": "TEXT",
                    }.get(cell_type, "UNSUPPORTED")
                cells[column] = {"value": value, "kind": kind}
            rows[number] = cells
        return rows


def _pdf_rows(
    raw: bytes, extraction: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[int, dict[str, Any]]]:
    """Keep model-proposed table cells tied to selected literal page passages."""
    from pypdf import PdfReader

    if (
        set(extraction) != {"columns", "rows", "rationale"}
        or not isinstance(extraction["rationale"], str)
        or not extraction["rationale"].strip()
    ):
        raise ContractError(
            "PDF extraction needs columns, located rows and a rationale"
        )
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted or len(reader.pages) > 1000:
        raise ContractError(
            "Encrypted or excessive PDF requires another selected evidence format"
        )
    columns = extraction["columns"]
    indexed(columns, "column_id")
    if not 1 <= len(columns) <= MAX_COLUMNS or any(
        set(c) != {"column_id", "label"}
        or not re.fullmatch(r"[A-Z]{1,3}", c["column_id"])
        for c in columns
    ):
        raise ContractError("Invalid proposed PDF columns")
    if not 1 <= len(extraction["rows"]) <= MAX_ROWS:
        raise ContractError("Invalid proposed PDF row count")
    texts = {}
    rows = {}
    expected = {c["column_id"] for c in columns}
    for number, proposed in enumerate(extraction["rows"], 1):
        if (
            set(proposed) != {"page", "quote", "cells"}
            or type(proposed["page"]) is not int
            or not 1 <= proposed["page"] <= len(reader.pages)
        ):
            raise ContractError("Invalid PDF page locator")
        page = proposed["page"]
        if page not in texts:
            text = reader.pages[page - 1].extract_text()
            if not text.strip() or len(text.encode("utf-8")) > MAX_BYTES:
                raise ContractError(
                    "PDF needs explicit OCR or another selected text source"
                )
            texts[page] = " ".join(text.split())
        quote = " ".join(proposed["quote"].split())
        if not quote or quote not in texts[page] or set(proposed["cells"]) != expected:
            raise ContractError(
                "Proposed PDF row is not supported by the cited page passage"
            )
        for value in proposed["cells"].values():
            if not isinstance(value, str) or (
                value.strip() and " ".join(value.split()) not in quote
            ):
                raise ContractError("PDF cell text is absent from its cited passage")
        rows[number] = {
            "cells": {
                c: {"value": v, "kind": "TEXT"} for c, v in proposed["cells"].items()
            },
            "locator": f"page {page}: {proposed['quote']}",
        }
    return columns, rows


def inspect_table(
    path: Path, evidence: dict[str, Any], options: dict[str, Any]
) -> dict[str, Any]:
    """Read only the selected source and sheet/range, retaining original cell strings."""
    validate(options, "ledger-selection.schema.json")
    raw = _source(path, evidence)
    common = {
        "format",
        "sheet",
        "header_row",
        "first_row",
        "last_row",
        "delimiter",
        "encoding",
        "pdf_extraction",
    }
    if set(options) != common or options["format"] not in ("CSV", "XLSX", "PDF"):
        raise ContractError("Table selection needs the exact documented options")
    table_id = "T." + canonical_hash(
        {
            "source_sha256": evidence["sha256"],
            "evidence_id": evidence["evidence_id"],
            "options": options,
        }
    )
    if options["format"] == "PDF":
        if (
            options["sheet"] is not None
            or options["header_row"] is not None
            or options["first_row"] is not None
            or options["last_row"] is not None
        ):
            raise ContractError("PDF rows use page citations, not spreadsheet ranges")
        columns, selected = _pdf_rows(raw, options["pdf_extraction"])
        extraction_assurance = "MODEL_TABLE_PROPOSAL_WITH_LITERAL_PAGE_REFERENCES"
    else:
        if options["pdf_extraction"] is not None:
            raise ContractError(
                "PDF extraction cannot be mixed with a spreadsheet source"
            )
        header, first, last = (
            options["header_row"],
            options["first_row"],
            options["last_row"],
        )
        if (
            any(type(n) is not int for n in (header, first, last))
            or not 1 <= header < first <= last <= MAX_ROWS
        ):
            raise ContractError("Select an explicit header and closed data-row range")
        if options["format"] == "CSV":
            if options["sheet"] is not None:
                raise ContractError("CSV has no worksheet")
            raw_rows = _csv_rows(raw, options)
        else:
            if not isinstance(options["sheet"], str) or not options["sheet"].strip():
                raise ContractError("XLSX needs an exact sheet name")
            raw_rows = _xlsx_rows(raw, options["sheet"])
        if header not in raw_rows or last > max(raw_rows, default=0):
            raise ContractError("Selected range exceeds the source population")
        columns = [
            {"column_id": col, "label": cell["value"]}
            for col, cell in raw_rows[header].items()
        ]
        allowed_columns = {col["column_id"] for col in columns}
        if not columns:
            raise ContractError("Selected header is empty")
        selected = {}
        for number in range(first, last + 1):
            cells = raw_rows.get(number, {})
            if set(cells) - allowed_columns:
                raise ContractError(
                    "Data extends beyond the selected header; review the mapping"
                )
            selected[number] = {
                "cells": {
                    c: cells.get(c, {"value": "", "kind": "EMPTY"})
                    for c in allowed_columns
                },
                "locator": f"{options['sheet'] or 'CSV'}, source row {number}",
            }
        extraction_assurance = "EXACT_SELECTED_CELLS_NOT_ACCOUNTING_CLASSIFICATION"
    rows = []
    for number, row in selected.items():
        origin = canonical_hash(
            {
                "source_sha256": evidence["sha256"],
                "sheet": options["sheet"],
                "row_number": number,
                "locator": row["locator"],
            }
        )
        rows.append(
            {
                "row_ref": table_id + f":r{number}",
                "origin_key": origin,
                "source_row": number,
                **row,
            }
        )
    result = {
        "schema_version": "1.0",
        "table_id": table_id,
        "source_evidence_id": evidence["evidence_id"],
        "source_sha256": evidence["sha256"],
        "options": options,
        "columns": columns,
        "rows": rows,
        "extraction_assurance": extraction_assurance,
    }
    result["table_digest"] = canonical_hash(result)
    return result


def _cell(row: dict[str, Any], column: str) -> dict[str, str]:
    if column not in row["cells"]:
        raise ContractError("Mapping refers to an unknown source column")
    cell = row["cells"][column]
    if cell["kind"] in ("FORMULA", "ERROR", "UNSUPPORTED", "BOOLEAN"):
        raise ContractError(
            "Mapped cell cannot be evaluated; select a reviewed values-only export"
        )
    return cell


def _decimal(cell: dict[str, str], mapping: dict[str, Any]) -> Decimal:
    raw = cell["value"].strip()
    if len(raw) > 64:
        raise ContractError("Source amount has excessive precision")
    if cell["kind"] == "NUMBER":
        if not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]{1,2})?", raw):
            raise ContractError("Invalid OOXML numeric value")
        value = Decimal(raw)
    else:
        negative = raw.startswith("(") and raw.endswith(")")
        if negative:
            if not mapping["parentheses_negative"]:
                raise ContractError(
                    "Parenthesized amount requires an explicit negative-number mapping"
                )
            raw = "-" + raw[1:-1]
        decimal, thousands = (
            mapping["decimal_separator"],
            mapping["thousands_separator"],
        )
        if thousands == decimal:
            raise ContractError("Decimal and thousands separators must differ")
        digits = (
            r"[0-9]+"
            if thousands is None
            else rf"(?:[0-9]+|[0-9]{{1,3}}(?:{re.escape(thousands)}[0-9]{{3}})+)"
        )
        if not re.fullmatch(rf"-?{digits}(?:{re.escape(decimal)}[0-9]{{1,12}})?", raw):
            raise ContractError("Amount does not match the reviewed numeric format")
        if thousands:
            raw = raw.replace(thousands, "")
        value = Decimal(raw.replace(decimal, "."))
    if not value.is_finite() or abs(value) >= Decimal("1e14"):
        raise ContractError("Source amount exceeds the supported range")
    with localcontext() as context:
        context.prec = 80
        exponent = value.normalize().as_tuple().exponent
        if isinstance(exponent, int) and exponent < -12:
            raise ContractError("Source amount has more than twelve decimal places")
    return value


def normalize_population(
    tables: list[dict[str, Any]], plan: dict[str, Any], evidence_ids: set[str]
) -> dict[str, Any]:
    """Produce a traceable proposal; unresolved duplicate groups block affected costs."""
    validate(plan, "ledger-normalization.schema.json")
    table_index = indexed(tables, "table_id")
    mappings = indexed(plan["mappings"], "table_id")
    if not plan["purpose"].strip() or any(
        not m["mapping_rationale"].strip() for m in mappings.values()
    ):
        raise ContractError("Normalization needs a purpose and mapping rationale")
    if set(table_index) != set(mappings):
        raise ContractError(
            "Normalization must map the exact selected table population"
        )
    rows: dict[str, dict[str, Any]] = {}
    for table in tables:
        if (
            canonical_hash({k: v for k, v in table.items() if k != "table_digest"})
            != table["table_digest"]
        ):
            raise ContractError("Table snapshot changed")
        if table["source_evidence_id"] not in evidence_ids:
            raise ContractError("Table evidence is outside the selected run")
        for row in table["rows"]:
            if row["row_ref"] in rows:
                raise ContractError("Repeated source row")
            rows[row["row_ref"]] = {
                **row,
                "table_id": table["table_id"],
                "evidence_id": table["source_evidence_id"],
            }
    non_data = indexed(plan["non_data_rows"], "row_ref")
    excluded = indexed(plan["excluded_rows"], "row_ref")
    if not (set(non_data) | set(excluded)) <= set(rows) or set(non_data) & set(
        excluded
    ):
        raise ContractError("Unknown or overlapping row disposition")
    if any(
        not r["reason"].strip()
        for r in list(non_data.values()) + list(excluded.values())
    ):
        raise ContractError("Every excluded/non-data row needs a rationale")
    parsed: dict[str, _ParsedAmount] = {}
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    identities: dict[tuple[str, ...], list[str]] = defaultdict(list)
    origins: dict[str, list[str]] = defaultdict(list)
    ledger_keys: dict[tuple[str, str], list[str]] = defaultdict(list)
    for ref, row in rows.items():
        if ref in non_data:
            continue
        mapping = mappings[row["table_id"]]
        if (mapping["currency_column"] is None) == (
            mapping["currency_constant"] is None
        ):
            raise ContractError(
                "Currency needs exactly one source column or explicit constant"
            )
        currency = (
            mapping["currency_constant"]
            if mapping["currency_column"] is None
            else _cell(row, mapping["currency_column"])["value"].strip()
        )
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ContractError("Currency needs a reviewed three-letter code")
        row_key = _cell(row, mapping["row_key_column"])["value"].strip()
        if not row_key:
            raise ContractError("Every data row needs its original ledger key")
        value = _decimal(_cell(row, mapping["amount_column"]), mapping)
        parsed[ref] = {
            "amount": value,
            "currency": currency,
            "original_ledger_key": row_key,
        }
        with localcontext() as context:
            context.prec = 60
            totals[row["table_id"], currency] += value
        fields = tuple(
            _cell(row, c)["value"].strip() for c in mapping["economic_key_columns"]
        )
        if any(not field for field in fields):
            raise ContractError(
                "Economic identity columns contain blanks; review the mapping"
            )
        identities[(*fields, currency, str(value.normalize()))].append(ref)
        origins[row["origin_key"]].append(ref)
        ledger_keys[row["table_id"], row_key].append(ref)
    control_totals = {}
    for total in plan["control_totals"]:
        key = (total["table_id"], total["currency"])
        if (
            key in control_totals
            or key[0] not in table_index
            or total["evidence_id"] not in evidence_ids
        ):
            raise ContractError("Invalid control-total scope or evidence")
        expected = Decimal(total["value"])
        source_cell = total["source_cell"]
        if source_cell:
            source_row = rows.get(source_cell["row_ref"])
            if (
                source_row is None
                or source_row["table_id"] != key[0]
                or source_row["evidence_id"] != total["evidence_id"]
            ):
                raise ContractError("Control-total cell belongs to another table")
            if (
                _decimal(_cell(source_row, source_cell["column_id"]), mappings[key[0]])
                != expected
            ):
                raise ContractError(
                    "Control total differs from its selected source cell"
                )
        control_totals[key] = expected
    if set(totals) != set(control_totals) or any(
        totals[k] != control_totals[k] for k in totals
    ):
        raise ContractError(
            "Selected accounting population does not reconcile to control totals"
        )
    rates = indexed(plan["fx_rates"], "rate_id")
    for rate in rates.values():
        if (
            rate["evidence_id"] not in evidence_ids
            or not rate["locator"].strip()
            or not rate["rationale"].strip()
            or Decimal(rate["eur_per_unit"]) <= 0
        ):
            raise ContractError("FX rate needs positive value and selected provenance")
    consumed: dict[str, str] = {}
    costs, trace = [], []
    for item in plan["costs"]:
        if (
            not item["rationale"].strip()
            or not set(item["evidence_ids"]) <= evidence_ids
        ):
            raise ContractError(
                "Cost normalization needs selected evidence and rationale"
            )
        components = []
        with localcontext() as context:
            context.prec = 60
            total_eur = Decimal(0)
            for component in item["components"]:
                ref = component["row_ref"]
                if ref not in parsed or ref in consumed or ref in excluded:
                    raise ContractError(
                        "Cost references a missing, excluded or already consumed row"
                    )
                row, source_value = rows[ref], parsed[ref]
                if row["evidence_id"] not in item["evidence_ids"]:
                    raise ContractError("Cost omits a contributing evidence document")
                rate_id = component["fx_rate_id"]
                fx_rate = Decimal(1)
                if source_value["currency"] == "EUR":
                    if rate_id is not None:
                        raise ContractError(
                            "EUR source rows do not need a conversion rate"
                        )
                else:
                    if (
                        rate_id not in rates
                        or rates[rate_id]["from_currency"] != source_value["currency"]
                    ):
                        raise ContractError(
                            "Foreign amount requires its own reviewed conversion rate"
                        )
                    fx_rate = Decimal(rates[rate_id]["eur_per_unit"])
                converted = source_value["amount"] * fx_rate
                total_eur += converted
                consumed[ref] = item["cost_id"]
                components.append(
                    {
                        "row_ref": ref,
                        "evidence_id": row["evidence_id"],
                        "locator": row["locator"],
                        "original_ledger_key": source_value["original_ledger_key"],
                        "source_amount": str(source_value["amount"]),
                        "source_currency": source_value["currency"],
                        "fx_rate_id": rate_id,
                        "eur_per_unit": str(fx_rate),
                        "unrounded_eur": str(converted),
                    }
                )
            if not 0 <= total_eur < Decimal("1e14"):
                raise ContractError(
                    "Net normalized cost must be nonnegative and within supported range"
                )
            book = money(total_eur)
            if Decimal(item["income_max"]) > Decimal(book) or Decimal(
                item["irap_max"]
            ) > Decimal(book):
                raise ContractError(
                    "Proposed fiscal basis exceeds normalized accounting cost"
                )
            ledger_key = "N." + canonical_hash(
                sorted(rows[c["row_ref"]]["origin_key"] for c in item["components"])
            )
            costs.append(
                {
                    "cost_id": item["cost_id"],
                    "ledger_row_key": ledger_key,
                    "period_id": item["period_id"],
                    "account": item["account"],
                    "category": item["category"],
                    "evidence_id": components[0]["evidence_id"],
                    "currency": "EUR",
                    "book_amount": book,
                    "income_max": item["income_max"],
                    "irap_max": item["irap_max"],
                }
            )
            trace.append(
                {
                    "cost_id": item["cost_id"],
                    "ledger_row_key": ledger_key,
                    "components": components,
                    "unrounded_eur": str(total_eur),
                    "book_amount": book,
                    "rounding_delta": str(Decimal(book) - total_eur),
                    "rationale": item["rationale"],
                }
            )
    indexed(costs, "cost_id")
    indexed(costs, "ledger_row_key")
    if set(consumed) | set(excluded) | set(non_data) != set(rows):
        raise ContractError(
            "Closed population has rows without an explicit disposition"
        )
    for exclusion in excluded.values():
        if (
            not set(exclusion["evidence_ids"]) <= evidence_ids
            or rows[exclusion["row_ref"]]["evidence_id"]
            not in exclusion["evidence_ids"]
        ):
            raise ContractError("Exclusion needs its selected source evidence")
    candidates = {
        tuple(sorted(group))
        for group in list(identities.values())
        + list(origins.values())
        + list(ledger_keys.values())
        if len(group) > 1
    }
    reviews = {}
    for item in plan["duplicate_reviews"]:
        group = tuple(sorted(item["row_refs"]))
        if (
            group in reviews
            or not set(group) <= set(parsed)
            or not item["reason"].strip()
            or not set(item["evidence_ids"]) <= evidence_ids
        ):
            raise ContractError(
                "Duplicate review has invalid scope, evidence or rationale"
            )
        if not {rows[r]["evidence_id"] for r in group} <= set(item["evidence_ids"]):
            raise ContractError("Duplicate review omits contributing source evidence")
        if item["decision"] == "DISTINCT" and len(
            {rows[r]["origin_key"] for r in group}
        ) < len(group):
            raise ContractError(
                "The same physical source row cannot be declared distinct"
            )
        reviews[group] = item
        candidates.add(group)  # Host-discovered semantic duplicates are also reviewed.
        retained = item["retained_row_ref"]
        if item["decision"] == "DUPLICATE":
            if (
                retained not in group
                or retained not in consumed
                or not (set(group) - {retained}) <= set(excluded)
            ):
                raise ContractError(
                    "Confirmed duplicates require one retained row and explicit exclusions"
                )
        elif retained is not None:
            raise ContractError("Only a confirmed duplicate group has a retained row")
    findings = []
    blocked = set()
    for group in sorted(candidates):
        decision = reviews.get(group)
        resolved = decision is not None and decision["decision"] != "UNRESOLVED"
        affected = sorted({consumed[r] for r in group if r in consumed})
        if not resolved:
            blocked.update(affected)
        findings.append(
            {
                "finding_id": "D." + canonical_hash(group),
                "row_refs": list(group),
                "status": "RESOLVED" if resolved else "REQUIRES_REVIEW",
                "cost_ids": affected,
                "decision": decision,
                "automatic_exclusion": False,
            }
        )
    if (
        not plan["population_duplicate_review"]["assessment"].strip()
        or not set(plan["population_duplicate_review"]["evidence_ids"]) <= evidence_ids
    ):
        raise ContractError(
            "Population duplicate review needs selected evidence and an assessment"
        )
    if not {t["source_evidence_id"] for t in tables} <= set(
        plan["population_duplicate_review"]["evidence_ids"]
    ):
        raise ContractError("Population duplicate review omits selected ledgers")
    with localcontext() as context:
        context.prec = 60
        normalized_total = money(
            sum((Decimal(c["book_amount"]) for c in costs), Decimal(0))
        )
    result = {
        "schema_version": "1.0",
        "status": "PROPOSED_REQUIRES_REVIEW",
        "plan_hash": canonical_hash(plan),
        "mapping_decisions": plan["mappings"],
        "reviewed_control_totals": plan["control_totals"],
        "fx_rates": plan["fx_rates"],
        "population_duplicate_review": plan["population_duplicate_review"],
        "table_digests": sorted(t["table_digest"] for t in tables),
        "costs": costs,
        "trace": trace,
        "ledger_control_total": normalized_total,
        "source_control_totals": [
            {"table_id": t, "currency": currency, "amount": str(value)}
            for (t, currency), value in sorted(totals.items())
        ],
        "excluded_rows": [
            {
                **row,
                "source_amount": str(parsed[ref]["amount"]),
                "source_currency": parsed[ref]["currency"],
            }
            for ref, row in excluded.items()
        ],
        "non_data_rows": plan["non_data_rows"],
        "duplicate_findings": findings,
        "blocked_cost_ids": sorted(blocked),
        "professional_approval": False,
    }
    result["normalization_digest"] = canonical_hash(result)
    return result


def normalization_markdown(result: dict[str, Any]) -> str:
    """Show original amounts, conversion and grouping choices before approval."""
    lines = [
        "# Patent Box — proposta di normalizzazione costi",
        "",
        "PROPOSTA DA RIVEDERE; nessuna approvazione professionale implicita.",
        "",
        f"Totale contabile normalizzato: EUR {result['ledger_control_total']}",
        "",
    ]
    lines += ["## Mappature e quadrature proposte", ""]
    for mapping in result["mapping_decisions"]:
        lines += [
            f"- {mapping['table_id']}: importo {mapping['amount_column']}, identificativo {mapping['row_key_column']}, chiave economica {', '.join(mapping['economic_key_columns'])}. {mapping['mapping_rationale']}"
        ]
    for total in result["reviewed_control_totals"]:
        lines += [
            f"- Totale originale {total['value']} {total['currency']}: {total['evidence_id']}, {total['locator']}."
        ]
    for rate in result["fx_rates"]:
        lines += [
            f"- Cambio {rate['rate_id']}: EUR {rate['eur_per_unit']} per {rate['from_currency']}, {rate['rate_date']}; {rate['evidence_id']}, {rate['locator']}. {rate['rationale']}"
        ]
    costs = indexed(result["costs"], "cost_id")
    for cost in result["trace"]:
        fiscal = costs[cost["cost_id"]]
        lines += [
            f"## {cost['cost_id']} — EUR {cost['book_amount']}",
            "",
            cost["rationale"],
            f"Basi candidate: redditi EUR {fiscal['income_max']}; IRAP EUR {fiscal['irap_max']}.",
        ]
        for row in cost["components"]:
            lines.append(
                f"- {row['evidence_id']}, {row['locator']}; riga {row['original_ledger_key']}: {row['source_amount']} {row['source_currency']}; cambio EUR/unità {row['eur_per_unit']}; EUR non arrotondati {row['unrounded_eur']}."
            )
        lines += [
            f"Differenza di arrotondamento esplicita: EUR {cost['rounding_delta']}",
            "",
        ]
    lines += [
        "## Duplicati da rivedere",
        "",
        result["population_duplicate_review"]["assessment"],
    ]
    for row in result["duplicate_findings"]:
        lines += [
            f"- {row['finding_id']}: {row['status']}; costi {', '.join(row['cost_ids'])}; nessuna esclusione automatica."
        ]
        if row["decision"]:
            lines.append(
                f"  Decisione proposta: {row['decision']['decision']}; {row['decision']['reason']}"
            )
        lines.append("  Righe: " + ", ".join(row["row_refs"]))
    lines += ["", "## Righe escluse e non contabili", ""]
    for row in result["excluded_rows"] + result["non_data_rows"]:
        lines.append(f"- {row['row_ref']}: {row['reason']}")
    return "\n".join(lines) + "\n"
