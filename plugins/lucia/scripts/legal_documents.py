#!/usr/bin/env python3
"""Local evidence packs for Lucia. No network, OCR or model client."""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import io
import json
import logging
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from legal_docx import inspect_docx
from lxml import etree as ET

__all__ = [
    "prepare",
    "read_pack",
    "compare",
    "validate_review",
    "render",
    "draft",
    "main",
]

LOGGER = logging.getLogger(__name__)
WORKFLOWS = (
    "revisione-contratti",
    "confronto-documenti",
    "revisione-documentale",
    "redazione-da-modello",
    "controllo-documento",
)
STATUSES = ("supported", "not-stated", "unreadable", "not-reviewed")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _text(node: Any) -> str:
    """Preserve visible text, tabs and breaks, including deleted revision text."""
    pieces = []
    for element in node.iter():
        if element.tag in (W + "t", W + "delText"):
            pieces.append(element.text or "")
        elif element.tag == W + "tab":
            pieces.append("\t")
        elif element.tag in (W + "br", W + "cr"):
            pieces.append("\n")
    return "".join(pieces)


def _parse_xml(data: bytes) -> Any:
    if b"<!DOCTYPE" in data.upper():
        raise ValueError("Document XML must not contain a DTD.")
    return ET.fromstring(
        data, parser=ET.XMLParser(resolve_entities=False, no_network=True)
    )


def _docx_parts(archive: zipfile.ZipFile) -> list[str]:
    """Include body, tables, notes, headers, footers and comments with stable anchors."""
    return sorted(
        name
        for name in archive.namelist()
        if re.fullmatch(
            r"word/(document|footnotes|endnotes|comments|header\d+|footer\d+)\.xml",
            name,
        )
    )


def _extract(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    units: list[dict[str, Any]] = []
    warnings: list[str] = []
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        for number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), 1
        ):
            if line.strip():
                units.append({"anchor": f"line:{number}", "text": line})
    elif suffix == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError

        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDF: supply an accessible copy.")
            for number, page in enumerate(reader.pages, 1):
                value = page.extract_text() or ""
                units.append({"anchor": f"page:{number}", "text": value})
                if not value.strip():
                    warnings.append(
                        f"page:{number}: no extractable text; image or empty page requires inspection"
                    )
        except PyPdfError as error:
            raise ValueError(f"PDF could not be read: {error}") from error
        warnings.append(
            "PDF text extraction does not verify layout, images, signatures or reading order; inspect the original."
        )
    elif suffix == ".docx":
        inspection = inspect_docx(path)
        warnings.extend(inspection["warnings"])
        for paragraph in inspection["paragraphs"]:
            anchor = paragraph["anchor"]
            units.append({"anchor": anchor, "text": paragraph["text"]})
            if paragraph["original_text"] != paragraph["text"]:
                units.append(
                    {
                        "anchor": anchor + "/original",
                        "text": paragraph["original_text"],
                        "view": "original",
                    }
                )
            units.append(
                {
                    "anchor": anchor + "/structure",
                    "text": json.dumps(paragraph, ensure_ascii=False),
                    "view": "structure",
                }
            )
        for key in ("styles", "style_defaults", "numbering", "comments", "properties"):
            units.append(
                {
                    "anchor": "package/" + key,
                    "text": json.dumps(inspection.get(key, []), ensure_ascii=False),
                    "view": "structure",
                }
            )
    else:
        raise ValueError(
            f"Unsupported format {suffix or '(none)'}; supply PDF, DOCX, UTF-8 TXT or Markdown."
        )
    if not any(unit["text"].strip() for unit in units):
        warnings.append("No readable text. Do not infer that clauses are absent.")
    return units, warnings


def prepare(
    run_dir: Path, files: list[Path], workflow: str, topics: list[str]
) -> dict[str, Any]:
    """Snapshot selected originals and extract a complete, untruncated evidence pack."""
    if (
        workflow not in WORKFLOWS
        or not files
        or not topics
        or len(topics) != len(set(topics))
    ):
        raise ValueError(
            "Choose a registered workflow, at least one file and unique review topics."
        )
    if any(not topic.strip() for topic in topics):
        raise ValueError("Review topics cannot be blank.")
    if workflow == "confronto-documenti" and len(files) < 2:
        raise ValueError("Comparison needs at least two selected documents.")
    resolved = [path.resolve(strict=True) for path in files]
    if any(not path.is_file() for path in resolved):
        raise ValueError("Inputs must be individual files, not folders.")
    if run_dir.exists():
        raise ValueError(
            "Run directory already exists. Use a new run; existing evidence is never overwritten."
        )
    run_dir.mkdir(parents=True)
    originals = run_dir / "originals"
    originals.mkdir()
    sources = []
    for number, path in enumerate(resolved, 1):
        source_id = f"D{number:03}"
        snapshot = originals / (source_id + path.suffix.lower())
        shutil.copyfile(path, snapshot)
        source: dict[str, Any] = {
            "id": source_id,
            "name": path.name,
            "snapshot": str(snapshot.relative_to(run_dir)),
            "sha256": _hash(snapshot.read_bytes()),
        }
        try:
            units, warnings = _extract(snapshot)
            source.update(units=units, warnings=warnings, error=None)
        except (
            ValueError,
            UnicodeError,
            zipfile.BadZipFile,
            ET.XMLSyntaxError,
            OSError,
        ) as error:
            source.update(units=[], warnings=[], error=str(error))
        sources.append(source)
    pack = {
        "schema_version": 1,
        "workflow": workflow,
        "topics": topics,
        "sources": sources,
    }
    _write_json(run_dir / "evidence.json", pack)
    (run_dir / "evidence.sha256").write_text(
        _hash((run_dir / "evidence.json").read_bytes()) + "\n", encoding="utf-8"
    )
    review = {
        "context": {
            "represented_party": "",
            "jurisdiction": "",
            "relationship": "",
            "formation": "",
            "forum": "",
            "legal_basis": "",
            "firm_instructions": "",
            "instructions": "",
            "assumptions": [],
        },
        "coverage": {
            source["id"]: {
                "reviewed_anchors": [],
                "limitations": source["warnings"],
                "original_inspected": False,
            }
            for source in sources
        },
        "items": [
            {
                "source_id": source["id"],
                "topic": topic,
                "status": "not-reviewed",
                "summary": "",
                "reasoning": "",
                "proposal": "",
                "citations": [],
            }
            for source in sources
            for topic in topics
        ],
        "takeaways": [],
    }
    if workflow == "confronto-documenti":
        review["differences"] = {topic: "" for topic in topics}
    _write_json(run_dir / "review.json", review)
    return pack


def read_pack(run_dir: Path) -> dict[str, Any]:
    """Reject drift in extracted evidence and snapshots before using stored results."""
    evidence = run_dir / "evidence.json"
    if (
        _hash(evidence.read_bytes())
        != (run_dir / "evidence.sha256").read_text().strip()
    ):
        raise ValueError("Extracted evidence changed; prepare a new run.")
    pack = _load(evidence)
    if "playbook" in pack:
        selected = pack["playbook"]
        if (
            selected["snapshot"] != "playbook.json"
            or _hash((run_dir / "playbook.json").read_bytes()) != selected["sha256"]
        ):
            raise ValueError("Selected firm workflow changed; prepare a new run.")
    for source in pack["sources"]:
        path = (run_dir / source["snapshot"]).resolve()
        if not path.is_relative_to((run_dir / "originals").resolve()):
            raise ValueError("Snapshot escaped the originals directory.")
        if _hash(path.read_bytes()) != source["sha256"]:
            raise ValueError(f"Original snapshot changed: {source['id']}")
    return pack


def compare(run_dir: Path, before: str, after: str, view: str = "final") -> Path:
    """Produce a literal text diff; moved clauses and legal significance need model review."""
    if view not in {"final", "original"}:
        raise ValueError("Choose final or original revision text.")
    sources = {source["id"]: source for source in read_pack(run_dir)["sources"]}
    if before == after or before not in sources or after not in sources:
        raise ValueError("Choose two different source IDs from this run.")
    for key in (before, after):
        if sources[key]["error"] or not sources[key]["units"]:
            raise ValueError(f"Cannot compare unreadable source: {key}")
    texts = []
    for key in (before, after):
        units = sources[key]["units"]
        originals = {
            unit["anchor"].removesuffix("/original"): unit["text"]
            for unit in units
            if unit.get("view") == "original"
        }
        texts.append(
            [
                (
                    originals.get(unit["anchor"], unit["text"])
                    if view == "original"
                    else unit["text"]
                )
                + "\n"
                for unit in units
                if unit.get("view", "final") == "final"
            ]
        )
    diff = "".join(difflib.unified_diff(*texts, fromfile=before, tofile=after))
    target = (
        run_dir
        / f"comparison-{before}-{after}{'-original' if view == 'original' else ''}.diff"
    )
    target.write_text(
        diff
        or "No differences in extracted text. This does not establish identical formatting or files.\n",
        encoding="utf-8",
    )
    return target


def _normalize(value: str) -> str:
    return " ".join(value.split())


def validate_review(run_dir: Path, review: dict[str, Any]) -> dict[str, Any]:
    """Check coverage, schema and quote occurrence, never legal or semantic correctness."""
    pack = read_pack(run_dir)
    sources = {source["id"]: source for source in pack["sources"]}
    errors: list[str] = []
    incomplete: list[str] = []
    checked_quotes = []
    schema = _load(Path(__file__).with_name("legal_documents_review.schema.json"))
    schema_errors = [
        f"{error.json_path}: {error.message}"
        for error in Draft202012Validator(schema).iter_errors(review)
    ]
    if schema_errors:
        return {
            "valid": False,
            "coverage_complete": False,
            "errors": schema_errors,
            "limitations": [],
            "quote_checks": [],
        }
    labels = _load(Path(__file__).with_name("legal_documents_labels.json"))[
        review["context"].get("language", "it")
    ]
    coverage = review.get("coverage", {})
    if set(coverage) != set(sources):
        errors.append("Coverage must include exactly the selected source IDs.")
    complete_sources = set()
    for source_id, source in sources.items():
        current = coverage.get(source_id, {})
        anchors = {unit["anchor"] for unit in source["units"]}
        reviewed = current.get("reviewed_anchors", [])
        if not isinstance(reviewed, list) or any(
            not isinstance(anchor, str) for anchor in reviewed
        ):
            errors.append(f"{source_id}: reviewed_anchors must be a list of anchors")
            continue
        if set(reviewed) - anchors:
            errors.append(f"{source_id}: unknown coverage anchors")
        if (
            not source["error"]
            and anchors
            and any(unit["text"].strip() for unit in source["units"])
            and set(reviewed) == anchors
            and not current.get("limitations")
            and (not source["warnings"] or current.get("original_inspected") is True)
        ):
            complete_sources.add(source_id)
        else:
            incomplete.append(f"{source_id}: {labels['coverage_incomplete']}")
    for source_id, current in coverage.items():
        incomplete.extend(f"{source_id}: {limit}" for limit in current["limitations"])
    for source in sources.values():
        if source["error"]:
            incomplete.append(f"{source['id']}: {source['error']}")
    if pack["workflow"] == "confronto-documenti":
        differences = review.get("differences", {})
        if set(differences) != set(pack["topics"]) or any(
            not value.strip() for value in differences.values()
        ):
            errors.append(
                "Comparison requires a separate difference explanation for every topic."
            )
    items = review.get("items", [])
    expected = {(source_id, topic) for source_id in sources for topic in pack["topics"]}
    seen = set()
    for number, item in enumerate(items, 1):
        source_id, topic = item.get("source_id"), item.get("topic")
        key = (source_id, topic)
        if key not in expected or key in seen:
            errors.append(f"Item {number}: unknown or duplicate source/topic")
        seen.add(key)
        status = item.get("status")
        if status not in STATUSES:
            errors.append(f"Item {number}: invalid status")
        if any(
            not isinstance(item.get(field), str)
            for field in ("summary", "reasoning", "proposal")
        ):
            errors.append(
                f"Item {number}: summary, reasoning and proposal must be strings"
            )
        citations = item.get("citations", [])
        if status == "supported" and (
            not citations or not item.get("summary", "").strip()
        ):
            errors.append(
                f"Item {number}: supported findings need a summary and exact source quotations"
            )
        if status == "not-stated" and source_id not in complete_sources:
            errors.append(
                f"Item {number}: absence cannot be asserted from incomplete coverage"
            )
        if status in ("not-reviewed", "unreadable"):
            incomplete.append(f"{source_id} / {topic}: {labels['statuses'][status]}")
        for citation in citations:
            cited_id = citation.get("source_id")
            anchor = citation.get("anchor")
            quote = citation.get("quote", "")
            source = sources.get(cited_id, {})
            unit = next(
                (unit for unit in source.get("units", []) if unit["anchor"] == anchor),
                None,
            )
            matched = bool(
                unit
                and isinstance(quote, str)
                and _normalize(quote)
                and _normalize(quote) in _normalize(unit["text"])
            )
            if cited_id != source_id:
                errors.append(
                    f"Item {number}: citation belongs to a different document"
                )
            if not matched:
                errors.append(
                    f"Item {number}: quotation not found at {cited_id} / {anchor}"
                )
            checked_quotes.append(
                {
                    "item": number,
                    "source_id": cited_id,
                    "anchor": anchor,
                    "matched": matched,
                }
            )
    if expected - seen:
        errors.append("Missing source/topic cells; retain unreviewed cells explicitly.")
    return {
        "valid": not errors,
        "coverage_complete": not incomplete,
        "errors": errors,
        "limitations": incomplete,
        "quote_checks": checked_quotes,
        "meaning": "Quote checks establish text occurrence only. Coverage is declared by the reviewing model; legal support and completeness require lawyer review.",
    }


def _safe_cell(value: str) -> str:
    """Prevent formula execution when opening model-authored spreadsheet cells."""
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _html_table(headings: list[str], rows: list[list[str]]) -> str:
    def escape(value: str) -> str:
        return html.escape(value).replace("\n", "<br>")

    head = "<tr>" + "".join(f"<th>{escape(cell)}</th>" for cell in headings) + "</tr>"
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f'<div class="scroll"><table><thead>{head}</thead><tbody>{body}</tbody></table></div>'


def _retire_reports(run_dir: Path) -> None:
    """Retain old generated artifacts under unambiguous names before rerendering."""
    for name in ("review.html", "review.csv", "review.xlsx", "delivery.json"):
        path = run_dir / name
        if path.is_file():
            path.rename(run_dir / f"previous-{_hash(path.read_bytes())[:12]}-{name}")


def render(run_dir: Path, review_path: Path) -> Path:
    """Save review context, evidence, coverage and comparison in each deliverable."""
    _retire_reports(run_dir)
    review = _load(review_path)
    validation = validate_review(run_dir, review)
    _write_json(run_dir / "validation.json", validation)
    if not validation["valid"]:
        raise ValueError(
            "Review validation failed; see validation.json. Previous reports have been retired."
        )
    pack = read_pack(run_dir)
    lang = review["context"].get("language", "it")
    labels = _load(Path(__file__).with_name("legal_documents_labels.json"))[lang]
    source_labels = {
        source["id"]: source["id"] + " · " + source["name"]
        for source in pack["sources"]
    }
    headings = labels["headings"]
    rows = []
    cells = {}
    for item in review["items"]:
        citations = "\n".join(
            f"{c['source_id']} / {c['anchor']}: {c['quote']}" for c in item["citations"]
        )
        status = labels["statuses"][item["status"]]
        rows.append(
            [
                source_labels[item["source_id"]],
                item["topic"],
                status,
                item["summary"],
                item["reasoning"],
                item["proposal"],
                citations,
            ]
        )
        cells[item["source_id"], item["topic"]] = (
            status + "\n" + item["summary"] + "\n" + citations
        )
    if pack["workflow"] == "confronto-documenti":
        matrix_headings = [headings[1], *source_labels.values(), labels["difference"]]
        matrix_rows = [
            [
                topic,
                *[cells[source["id"], topic] for source in pack["sources"]],
                review["differences"][topic],
            ]
            for topic in pack["topics"]
        ]
    else:
        matrix_headings = [headings[0], *pack["topics"]]
        matrix_rows = [
            [
                source_labels[source["id"]],
                *[cells[source["id"], topic] for topic in pack["topics"]],
            ]
            for source in pack["sources"]
        ]
    overall_status = (
        labels["complete"] if validation["coverage_complete"] else labels["partial"]
    )
    context_rows = [
        [labels["status"], overall_status],
        [labels["caveat"], labels["quote_meaning"]],
    ]
    for key, label in labels["context_labels"].items():
        value = review["context"][key]
        context_rows.append(
            [label, "\n".join(value) if isinstance(value, list) else value]
        )
    context_rows += [
        [labels["takeaways"], takeaway] for takeaway in review["takeaways"]
    ]
    context_rows += [[labels["limits"], limit] for limit in validation["limitations"]]
    source_rows = []
    for source in pack["sources"]:
        cov = review["coverage"][source["id"]]
        source_rows.append(
            [
                source_labels[source["id"]],
                source["sha256"],
                f"{len(cov['reviewed_anchors'])}/{len(source['units'])}",
                "\n".join(source["warnings"]),
                source["error"] or "",
                "\n".join(cov["limitations"]),
                str(cov["original_inspected"]),
            ]
        )
    title = "Lucia · " + labels["workflows"][pack["workflow"]]
    tables = _html_table(labels["context_headings"], context_rows)
    tables += f'<h2>{html.escape(labels["matrix"])}</h2>' + _html_table(
        matrix_headings, matrix_rows
    )
    tables += f'<h2>{html.escape(labels["details"])}</h2>' + _html_table(headings, rows)
    tables += f'<h2>{html.escape(labels["sources"])}</h2>' + _html_table(
        labels["source_headings"], source_rows
    )
    document = f"""<!doctype html><html lang="{lang}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>{html.escape(title)}</title><style>body{{font:16px/1.55 system-ui,sans-serif;color:#142337;margin:40px auto;max-width:1440px;padding:0 24px}}h1,h2{{color:#002060}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border-bottom:1px solid #ccd6e0;padding:12px;text-align:left;vertical-align:top;min-width:140px;overflow-wrap:anywhere}}th{{color:#002060}}.scroll{{overflow:auto}}@media print{{body{{margin:0}}}}</style><h1>{html.escape(title)}</h1><p>{html.escape(overall_status)}</p>{tables}<h2>{html.escape(labels['privacy_title'])}</h2><p>{html.escape(labels['privacy'])}</p></html>"""
    target = run_dir / "review.html"
    target.write_text(document, encoding="utf-8")
    with (run_dir / "review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        # Repeat context and limitations in every row, so filtering/exporting does not remove them.
        csv_context = "\n".join(f"{label}: {value}" for label, value in context_rows)
        csv_rows = [[*row, csv_context] for row in rows]
        csv_headings = [*headings, labels["context"]]
        if pack["workflow"] == "confronto-documenti":
            csv_headings.append(labels["difference"])
            csv_rows = [[*row, review["differences"][row[1]]] for row in csv_rows]
        writer.writerow([_safe_cell(cell) for cell in csv_headings])
        writer.writerows([[_safe_cell(cell) for cell in row] for row in csv_rows])
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = [
        (
            labels["context"],
            labels["context_headings"],
            context_rows + [[labels["privacy_title"], labels["privacy"]]],
        ),
        (labels["matrix"], matrix_headings, matrix_rows),
        (labels["details"], headings, rows),
        (labels["sources"], labels["source_headings"], source_rows),
    ]
    for name, columns, values in sheets:
        sheet = workbook.create_sheet(name)
        sheet.append([_safe_cell(cell) for cell in columns])
        for row in values:
            # Excel has a 32767-character cell limit; do not silently discard evidence.
            if any(len(cell) > 32767 for cell in row):
                raise ValueError(
                    "A review cell exceeds Excel's text limit; shorten the finding and keep precise quotations."
                )
            sheet.append([_safe_cell(cell) for cell in row])
        sheet.freeze_panes = "B2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 42
            column[0].font = Font(bold=True, color="002060")
            for cell in column:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    workbook.save(run_dir / "review.xlsx")
    _write_json(
        run_dir / "delivery.json",
        {
            "review_sha256": _hash(review_path.read_bytes()),
            "evidence_sha256": _hash((run_dir / "evidence.json").read_bytes()),
            "outputs": {
                name: _hash((run_dir / name).read_bytes())
                for name in (
                    "review.html",
                    "review.csv",
                    "review.xlsx",
                    "validation.json",
                )
            },
            "status": overall_status,
        },
    )
    return target


def _replace_runs(paragraph: Any, old: str, new: str) -> None:
    """Replace one literal span across Word runs, preserving surrounding run formatting."""
    nodes = list(paragraph.iter(W + "t"))
    value = "".join(node.text or "" for node in nodes)
    if not old or value.count(old) != 1:
        raise ValueError(
            "Each draft replacement must match exactly once in its paragraph."
        )
    start, end = value.index(old), value.index(old) + len(old)
    offset = 0
    inserted = False
    for node in nodes:
        text = node.text or ""
        left, right = max(0, start - offset), min(len(text), end - offset)
        if left < right:
            node.text = text[:left] + (new if not inserted else "") + text[right:]
            node.set(XML_SPACE, "preserve")
            inserted = True
        offset += len(text)


def draft(run_dir: Path, source_id: str, changes_path: Path) -> Path:
    """Apply explicit, reviewed replacements to a new copy of a supplied template."""
    pack = read_pack(run_dir)
    source = next(
        (source for source in pack["sources"] if source["id"] == source_id), None
    )
    if source is None or source["error"]:
        raise ValueError("Choose a readable template in this evidence pack.")
    original = run_dir / source["snapshot"]
    changes = _load(changes_path)
    if not isinstance(changes, list) or not changes:
        raise ValueError(
            "Supply a nonempty list of exact replacements with their factual basis."
        )
    for change in changes:
        if (
            not isinstance(change, dict)
            or any(
                not isinstance(change.get(key), str) or not change[key].strip()
                for key in ("anchor", "old", "basis")
            )
            or not isinstance(change.get("new"), str)
        ):
            raise ValueError(
                "Each replacement needs anchor, old, new and a nonempty factual basis."
            )
    target = run_dir / ("draft" + original.suffix)
    if target.exists():
        raise ValueError(
            "A draft already exists. Prepare a new revision run to retain its history."
        )
    if original.suffix in (".txt", ".md"):
        lines = original.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        for change in changes:
            match = re.fullmatch(r"line:(\d+)", change["anchor"])
            if match is None or not 1 <= int(match[1]) <= len(lines):
                raise ValueError("Invalid template line anchor.")
            index = int(match[1]) - 1
            if lines[index].count(change["old"]) != 1:
                raise ValueError("Draft replacement is missing or ambiguous.")
            lines[index] = lines[index].replace(change["old"], change["new"], 1)
        result = "".join(lines).encode("utf-8")
    elif original.suffix == ".docx":
        if any("\n" in change["new"] or "\t" in change["new"] for change in changes):
            raise ValueError(
                "DOCX replacements containing breaks or tabs require a document editor."
            )
        with zipfile.ZipFile(original) as archive:
            roots = {
                name: _parse_xml(archive.read(name)) for name in _docx_parts(archive)
            }
            changed = set()
            for change in changes:
                match = re.fullmatch(r"(word/[\w]+\.xml)#p(\d+)", change["anchor"])
                if match is None or match[1] not in roots:
                    raise ValueError("Invalid template paragraph anchor.")
                root = roots[match[1]]
                paragraphs = list(root.iter(W + "p"))
                if not 1 <= int(match[2]) <= len(paragraphs):
                    raise ValueError("Invalid template paragraph number.")
                paragraph = paragraphs[int(match[2]) - 1]
                unsafe = (
                    "ins",
                    "del",
                    "moveFrom",
                    "moveTo",
                    "fldChar",
                    "fldSimple",
                    "drawing",
                    "object",
                    "tab",
                    "br",
                )
                if any(
                    node.tag in {W + name for name in unsafe}
                    for node in paragraph.iter()
                ):
                    raise ValueError(
                        "Template paragraph contains revisions, fields or objects. Use a document editor on a copy and review visually."
                    )
                _replace_runs(paragraph, change["old"], change["new"])
                changed.add(match[1])
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as destination:
                for info in archive.infolist():
                    value = (
                        ET.tostring(
                            roots[info.filename], encoding="utf-8", xml_declaration=True
                        )
                        if info.filename in changed
                        else archive.read(info.filename)
                    )
                    destination.writestr(info, value)
            result = output.getvalue()
    else:
        raise ValueError(
            "Automatic template editing supports DOCX, TXT and Markdown; PDF needs an editable source."
        )
    target.write_bytes(result)
    _write_json(
        run_dir / "draft-changes.json",
        {
            "source_id": source_id,
            "original_sha256": source["sha256"],
            "draft_sha256": _hash(result),
            "changes": changes,
            "status": "Draft for lawyer review; formatting and factual/legal correctness require inspection.",
        },
    )
    return target


def main(argv: list[str] | None = None) -> int:
    """Run local document preparation, comparison, review or template drafting."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("prepare")
    init.add_argument("--run-dir", type=Path, required=True)
    init.add_argument("--workflow", choices=WORKFLOWS, required=True)
    init.add_argument("--file", type=Path, action="append", required=True)
    init.add_argument("--topic", action="append", required=True)
    diff = sub.add_parser("compare")
    diff.add_argument("--run-dir", type=Path, required=True)
    diff.add_argument("--before", required=True)
    diff.add_argument("--after", required=True)
    diff.add_argument("--view", choices=("final", "original"), default="final")
    review = sub.add_parser("render")
    review.add_argument("--run-dir", type=Path, required=True)
    review.add_argument("--review", type=Path, required=True)
    edit = sub.add_parser("draft")
    edit.add_argument("--run-dir", type=Path, required=True)
    edit.add_argument("--template", required=True)
    edit.add_argument("--changes", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(args.run_dir, args.file, args.workflow, args.topic)
            LOGGER.info("Evidence and review scaffold: %s", args.run_dir)
        elif args.command == "compare":
            LOGGER.info(
                "Literal text comparison: %s",
                compare(args.run_dir, args.before, args.after, args.view),
            )
        elif args.command == "render":
            LOGGER.info("Review: %s", render(args.run_dir, args.review))
        else:
            LOGGER.info("Draft: %s", draft(args.run_dir, args.template, args.changes))
    except (ValueError, OSError, KeyError, TypeError) as error:
        LOGGER.error("%s", error)
        return 2
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
