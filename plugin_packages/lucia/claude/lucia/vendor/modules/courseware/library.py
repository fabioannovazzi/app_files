"""Load reviewed course content and render it without model or network calls.

The checks here concern exact product membership, file identity and language
coverage. They do not judge professional relevance, correctness or understanding.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from .policy import local_unavailability, unavailable_local_workflows

__all__ = ["CourseError", "CourseLibrary", "main"]

_RESULT_COLUMNS = {
    "check_results.csv": [
        "movement_number",
        "entry_date",
        "amount_signed",
        "currency",
        "matched_support",
        "amount_found",
        "review_notes",
        "source_row",
    ],
    "journal_sample.csv": [
        "entry_date",
        "movement_number",
        "line_number",
        "account",
        "line_desc",
        "amount_signed",
        "currency",
        "source_row",
    ],
    "fatture_summary.csv": [
        "invoice_number",
        "invoice_date",
        "total_amount",
        "currency",
        "anomalies",
        "file_name",
    ],
    "structured_fiscal_fields.csv": [
        "file_name",
        "label",
        "value",
        "confidence",
        "evidence",
        "warnings",
    ],
}


class CourseError(ValueError):
    """A course cannot be safely reused with the current installed workflow."""


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(root: Path, relative: str) -> Path:
    path = root / relative
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise CourseError("Course paths must be relative and contained")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise CourseError(f"Missing or foreign course file: {relative}")
    return path


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _pdf_pages(source: Path, destination: Path, prefix: str, ui: dict[str, Any]) -> str:
    """Render the original lesson PDF for hosts without an embedded PDF viewer."""
    try:
        import pymupdf
    except ImportError as exc:
        raise CourseError(
            "PDF lesson previews require PyMuPDF in the selected runtime; "
            "run this helper with the product's ready managed Python."
        ) from exc
    figures = []
    try:
        with pymupdf.open(source) as document:
            if document.needs_pass or not document.page_count:
                raise CourseError("The lesson PDF cannot be opened for preview")
            for number, page in enumerate(document, start=1):
                filename = f"{prefix}-page-{number}.png"
                page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(
                    destination / filename
                )
                label = ui["pdf_page"].format(page=number, total=document.page_count)
                figures.append(
                    f"<figure class='source-pdf-page'><figcaption>{_esc(label)}</figcaption>"
                    f"<img src='{_esc(filename)}' alt='{_esc(source.name)} — {_esc(label)}'>"
                    "</figure>"
                )
    except (RuntimeError, ValueError) as exc:
        raise CourseError(
            f"The lesson PDF could not be rendered: {source.name}"
        ) from exc
    return "".join(figures)


def _list(values: list[str]) -> str:
    return (
        "<ol class='method'>"
        + "".join(f"<li>{_esc(value)}</li>" for value in values)
        + "</ol>"
    )


def _csv_input(text: str, ui: dict[str, Any] | None = None) -> str:
    """Label known teaching fields while preserving monetary and unknown text."""
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return ""
    labels = (ui or {}).get("csv_input_fields", {})
    values = (ui or {}).get("csv_input_values", {})
    head = "".join(
        f"<th scope='col'>{_esc(labels.get(value, value))}</th>" for value in rows[0]
    )
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{_esc(values.get(rows[0][index], {}).get(value, value) if index < len(rows[0]) else value)}</td>"
            for index, value in enumerate(row)
        )
        + "</tr>"
        for row in rows[1:]
    )
    return (
        "<div class='table-scroll'><table><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


def _xml_input(text: str, ui: dict[str, Any]) -> str:
    """Read invoice fields without validating, inferring or changing the XML."""
    from defusedxml import ElementTree as ET
    from defusedxml.common import DefusedXmlException

    raw = f"<pre class='source-text'>{_esc(text)}</pre>"
    # Unsupported or malformed XML remains inspectable as escaped source.
    if (
        len(text) > 1_000_000
        or "<!DOCTYPE" in text.upper()
        or "<!ENTITY" in text.upper()
    ):
        return raw
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException):
        return raw
    if root.tag.rsplit("}", 1)[-1] != "FatturaElettronica":
        return raw
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    labels = ui["invoice_fields"]

    def row(key: str, value: str | None) -> str:
        return (
            f"<tr><th scope='row'>{_esc(labels[key])}</th><td>{_esc(value)}</td></tr>"
            if value
            else ""
        )

    header = root.find("FatturaElettronicaHeader")
    parties = ""
    if header is not None:
        for key, node in [
            ("supplier", "CedentePrestatore"),
            ("customer", "CessionarioCommittente"),
        ]:
            party = header.find(node + "/DatiAnagrafici/Anagrafica")
            if party is not None:
                name = (
                    party.findtext("Denominazione")
                    or " ".join(
                        party.findtext(field, "") for field in ("Nome", "Cognome")
                    ).strip()
                )
                parties += row(key, name)
    tables = []
    for body in root.findall("FatturaElettronicaBody"):
        details = body.find("DatiGenerali/DatiGeneraliDocumento")
        if details is None:
            continue
        rows = parties + "".join(
            row(key, details.findtext(tag))
            for key, tag in [
                ("number", "Numero"),
                ("date", "Data"),
                ("type", "TipoDocumento"),
                ("currency", "Divisa"),
                ("total", "ImportoTotaleDocumento"),
            ]
        )
        for line in body.findall("DatiBeniServizi/DettaglioLinee"):
            rows += row("description", line.findtext("Descrizione"))
        tables.append(
            "<div class='table-scroll'><table><tbody>" + rows + "</tbody></table></div>"
        )
    if not tables:
        return raw
    return (
        f"<p>{_esc(ui['invoice_reading_note'])}</p>"
        + "".join(tables)
        + f"<details><summary>{_esc(ui['full_file'])}</summary>{raw}</details>"
    )


def _text_outline(
    text: str,
    images: dict[str, str] | None = None,
    links: dict[str, str] | None = None,
) -> str:
    """Format Markdown and plain disclosures; never execute supplied HTML."""
    blocks = []
    paragraph = []
    listing = None
    lines = [*text.splitlines(), ""]
    index = 0
    disclosure_depth = 0

    def inline(value: str) -> str:
        def plain(part: str) -> str:
            pieces = re.split(r"(`[^`]+`)", part)
            return "".join(
                (
                    f"<code>{_esc(piece[1:-1])}</code>"
                    if len(piece) > 2 and piece.startswith("`") and piece.endswith("`")
                    else re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", _esc(piece))
                )
                for piece in pieces
            )

        parts = []
        end = 0
        for match in re.finditer(r"(?<!!)\[([^\]]+)\]\((<[^>]+>|[^)]+)\)", value):
            parts.append(plain(value[end : match.start()]))
            label, target = match.groups()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            if links and target in links:
                parts.append(f"<a href='{_esc(links[target])}'>{_esc(label)}</a>")
            else:
                # Preserve an unrecorded reference as readable, inert text.
                # Only recorded inputs above become navigable local links.
                parts.append(f"{_esc(label)} ({_esc(target)})")
            end = match.end()
        parts.append(plain(value[end:]))
        return "".join(parts)

    def cells(line: str) -> list[str]:
        return [
            cell.strip().replace(r"\|", "|")
            for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))
        ]

    while index < len(lines):
        line = lines[index].strip()
        index += 1
        disclosure = re.fullmatch(r"<details><summary>([^<>]+)</summary>", line)
        close_disclosure = line == "</details>" and disclosure_depth > 0
        if disclosure or close_disclosure or line == "<!-- Review Handoff -->":
            if paragraph:
                blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
                paragraph = []
            if listing:
                blocks.append(f"</{listing}>")
                listing = None
            if disclosure:
                # Reconstruct only this passive form; attributes and HTML in
                # the label are not accepted or forwarded to the browser.
                blocks.append(
                    f"<details><summary>{_esc(disclosure.group(1))}</summary>"
                )
                disclosure_depth += 1
            elif close_disclosure:
                blocks.append("</details>")
                disclosure_depth -= 1
            continue
        if "|" in line and index < len(lines):
            header = cells(line)
            separator = cells(lines[index])
            if len(header) == len(separator) and all(
                re.fullmatch(r":?-{3,}:?", cell) for cell in separator
            ):
                if paragraph:
                    blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
                    paragraph = []
                if listing:
                    blocks.append(f"</{listing}>")
                    listing = None
                index += 1
                rows = []
                while index < len(lines) and "|" in lines[index]:
                    row = cells(lines[index])
                    if len(row) != len(header):
                        break
                    rows.append(row)
                    index += 1
                blocks.append(
                    "<div class='table-scroll markdown-table' tabindex='0'><table><thead><tr>"
                    + "".join(f"<th scope='col'>{_esc(v)}</th>" for v in header)
                    + "</tr></thead><tbody>"
                    + "".join(
                        "<tr>" + "".join(f"<td>{inline(v)}</td>" for v in row) + "</tr>"
                        for row in rows
                    )
                    + "</tbody></table></div>"
                )
                continue
        prefix, _, content = line.partition(" ")
        heading = 1 <= len(prefix) <= 6 and set(prefix) == {"#"}
        bullet = line.startswith(("- ", "* "))
        ordered = re.fullmatch(r"([0-9]{1,9})[.)]\s+(.+)", line)
        list_kind = "ul" if bullet else "ol" if ordered else None
        picture = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line)
        if not line or heading or list_kind or picture:
            if paragraph:
                blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
                paragraph = []
            if listing and listing != list_kind:
                blocks.append(f"</{listing}>")
                listing = None
        if picture:
            caption, target = picture.groups()
            if images and target in images:
                blocks.append(
                    f"<figure class='result-chart'><img src='{_esc(images[target])}' "
                    f"alt='{_esc(caption)}' loading='lazy'><figcaption>{_esc(caption)}</figcaption></figure>"
                )
            else:
                blocks.append(
                    f"<p>{_esc(caption)} <span class='caption'>({_esc(target)})</span></p>"
                )
        elif heading:
            level = min(len(prefix) + 2, 6)
            blocks.append(f"<h{level}>{_esc(content)}</h{level}>")
        elif list_kind:
            if not listing:
                start = (
                    f" start='{int(ordered.group(1))}'"
                    if ordered and int(ordered.group(1)) != 1
                    else ""
                )
                blocks.append(f"<{list_kind}{start}>")
                listing = list_kind
            item = ordered.group(2) if ordered else line[2:]
            blocks.append(f"<li>{inline(item)}</li>")
        elif line:
            if listing:
                blocks.append(f"</{listing}>")
                listing = None
            paragraph.append(line)
    blocks.extend("</details>" for _ in range(disclosure_depth))
    return "".join(blocks)


class CourseLibrary:
    """Read only courses belonging to the caller's current eligible catalog."""

    def __init__(self, plugin_root: Path, eligible: set[str]) -> None:
        self.root = plugin_root.resolve()
        self.product = _read(self.root / ".claude-plugin/plugin.json")["name"]
        self.assets = self.root / "assets/courses"
        self.index = _read(self.assets / "index.json")
        self.eligible = eligible - unavailable_local_workflows(self.product)
        if self.index.get("product") != self.product:
            raise CourseError("The course catalog belongs to another product")

    def catalog(self) -> list[dict[str, Any]]:
        """Return only installed courses, including their explicit locales."""
        return [
            {"workflow": key, **value}
            for key, value in sorted(self.index["courses"].items())
            if key in self.eligible
        ]

    def load(self, workflow: str, language: str) -> dict[str, Any]:
        """Fail closed on foreign, unavailable, altered or stale course content."""
        if reason := local_unavailability(self.product, workflow):
            raise CourseError(reason)
        if workflow not in self.eligible or workflow not in self.index["courses"]:
            raise CourseError("Choose a course from this product's installed catalog")
        entry = self.index["courses"][workflow]
        if language not in entry["languages"]:
            raise CourseError(
                "This course supports: "
                + ", ".join(entry["languages"])
                + "; ask the user to select one, without silently translating"
            )
        manifest = _inside(self.assets, entry["path"])
        if _digest(manifest) != entry["sha256"]:
            raise CourseError("Course content changed; rebuild the reviewed catalog")
        course = _read(manifest)
        if course.get("schema") == "mparanza.course.v1":
            from . import legacy

            try:
                return legacy.CourseLibrary(self.root, self.eligible).load(
                    workflow, language
                )
            except legacy.CourseError as exc:
                raise CourseError(str(exc)) from exc
        if (
            course.get("schema") != "mparanza.teaching_kit.v2"
            or course.get("product") != self.product
            or course.get("workflow") != workflow
            or sorted(course["locales"]) != sorted(entry["languages"])
            or len(course["seconds"]) != 6
            or any(
                type(seconds) is not int or seconds <= 0
                for seconds in course["seconds"]
            )
            or not 300 <= sum(course["seconds"]) <= 480
        ):
            raise CourseError("Invalid course identity, language coverage or duration")
        if course["group"] not in {"workflow", "supporting_task"}:
            raise CourseError("Invalid teaching-kit catalogue group")
        content = course["locales"][language]
        for field in (
            "title",
            "goal",
            "scenario",
            "scope",
            "inputs",
            "request",
            "review",
            "practice",
            "success",
            "repeat",
        ):
            if not isinstance(content.get(field), str) or not content[field].strip():
                raise CourseError(f"Teaching kit is missing its {field}")
        for field in ("steps", "deliverables", "checkpoints"):
            if (
                not isinstance(content.get(field), list)
                or not content[field]
                or any(
                    not isinstance(value, str) or not value.strip()
                    for value in content[field]
                )
            ):
                raise CourseError(f"Teaching kit is missing its {field}")
        for source in course["sources"]:
            # The package contains its own component; source checkouts use the
            # explicitly pinned sibling component, never an installed plugin.
            relative = source["path"]
            candidate = self.root / relative
            if (
                not candidate.is_file()
                and "repository_path" in source
                and (self.root.parent.parent / ".git").exists()
            ):
                candidate = _inside(self.root.parent.parent, source["repository_path"])
            else:
                candidate = _inside(self.root, relative)
            if _digest(candidate) != source["sha256"]:
                raise CourseError(
                    f"Course needs editorial refresh after a workflow change: {relative}"
                )
        selected_roles = set()
        seen_paths = set()
        for asset in course.get("files", []):
            path = _inside(manifest.parent, asset["path"])
            if _digest(path) != asset["sha256"]:
                raise CourseError("Teaching input changed; review and rebuild its kit")
            if (
                asset["path"] in seen_paths
                or asset["role"] not in {"source", "practice"}
                or not set(asset["languages"]) <= set(entry["languages"])
            ):
                raise CourseError(
                    "Teaching kits may contain only uniquely identified source and practice files"
                )
            seen_paths.add(asset["path"])
            if language in asset["languages"]:
                selected_roles.add(asset["role"])
        if selected_roles != {"source", "practice"}:
            raise CourseError(
                "Teaching kit needs source and practice files in the selected language"
            )
        return course

    def render(self, workflow: str, language: str, destination: Path) -> dict[str, Any]:
        """Materialize prepared content in a fresh local directory; record no lesson."""
        course = self.load(workflow, language)
        if course["schema"] == "mparanza.course.v1":
            from . import legacy

            try:
                return legacy.CourseLibrary(self.root, self.eligible).render(
                    workflow, language, destination
                )
            except legacy.CourseError as exc:
                raise CourseError(str(exc)) from exc
        destination = destination.expanduser().absolute()
        if any(path.is_symlink() for path in (destination, *destination.parents)):
            raise CourseError("Use an ordinary local destination, not a symlink")
        if destination.exists():
            raise CourseError("Use a fresh course directory; preserve existing work")
        destination.mkdir(parents=True)
        copy = course["locales"][language]
        shared_assets = Path(__file__).parent / "assets"
        ui = _read(shared_assets / "languages.json")[language]
        for asset in (
            "course.css",
            "InstrumentSans-Regular.ttf",
            "InstrumentSans-SemiBold.ttf",
            "OFL.txt",
        ):
            shutil.copyfile(_inside(shared_assets, asset), destination / asset)
        source_dir = (self.assets / self.index["courses"][workflow]["path"]).parent
        files = []
        for asset in course.get("files", []):
            if language not in asset["languages"]:
                continue
            target = destination / asset["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_inside(source_dir, asset["path"]), target)
            displayed = dict(asset)
            # A linked XML/Markdown file is not a browser document in every host.
            # Provide an escaped reading view; the workflow still receives the
            # original, byte-identical file, never this presentation wrapper.
            if target.suffix.lower() in {
                ".xml",
                ".md",
                ".txt",
                ".pdf",
                ".csv",
                ".xlsx",
                ".xlsm",
                ".docx",
            }:
                preview = (
                    "input-"
                    + hashlib.sha256(asset["path"].encode()).hexdigest()[:16]
                    + ".html"
                )
                step = 1 if asset["role"] == "source" else 5
                office_input = target.suffix.lower() in {".xlsx", ".xlsm", ".docx"}
                if target.suffix.lower() in {".xlsx", ".docx"}:
                    from .document_view import office_body

                    content = office_body(target, ui)
                elif office_input:
                    content = f"<p>{_esc(ui['office_input_note'].format(product=self.product.title()))}</p>"
                elif target.suffix.lower() == ".pdf":
                    content = _pdf_pages(target, destination, Path(preview).stem, ui)
                else:
                    content = f"<pre class='source-text'>{_esc(target.read_text(encoding='utf-8'))}</pre>"
                if target.suffix.lower() == ".csv":
                    content = _csv_input(target.read_text(encoding="utf-8-sig"), ui)
                elif target.suffix.lower() == ".xml":
                    content = _xml_input(target.read_text(encoding="utf-8"), ui)
                elif target.suffix.lower() == ".md":
                    content = (
                        _text_outline(target.read_text(encoding="utf-8"))
                        + f"<details><summary>{_esc(ui['full_file'])}</summary>{content}</details>"
                    )
                body = (
                    f"<main class='report'><a href='course.html#step-{step}'>{_esc(ui['back_to_lesson'])}</a>"
                    f"<section><p class='eyebrow'>{_esc(ui['input_preview'])}</p>"
                    f"<h1>{_esc(target.name)}</h1><p class='caption'>{_esc(asset['path'])}</p>"
                    + (
                        ""
                        if office_input
                        else f"<p>{_esc(ui['input_preview_note'])}</p>"
                    )
                    + f"<p><a href='{_esc(asset['path'])}' download>{_esc(ui['download_original'])}</a></p>"
                    f"{content}"
                    "</section></main>"
                )
                (destination / preview).write_text(
                    self._shell(target.name, language, body), encoding="utf-8"
                )
                displayed["preview_path"] = preview
            files.append(displayed)
        (destination / "course.html").write_text(
            self._page(course, copy, ui, language, files), encoding="utf-8"
        )
        (destination / "teacher.md").write_text(
            self._teacher(course, copy, ui), encoding="utf-8"
        )
        # This is an instruction handoff, never an execution or review receipt.
        execution = {
            "schema": "mparanza.teaching_execution_request.v1",
            "product": self.product,
            "workflow": workflow,
            "language": language,
            "skill": str(self.root / "skills" / workflow / "SKILL.md"),
            "request": copy["request"],
            "source_files": [
                str(destination / f["path"]) for f in files if f["role"] == "source"
            ],
            "practice_files": [
                str(destination / f["path"]) for f in files if f["role"] == "practice"
            ],
            "execution": course["execution"],
            "steps": copy["steps"],
            "checkpoints": copy["checkpoints"],
            "deliverables": copy["deliverables"],
            "practice": copy["practice"],
            "success": copy["success"],
            "sources": course["sources"],
            "execution_receipt": False,
            "rule": "Read the current own-product skill and delegated procedure completely. Prepare the real bound tutorial case from source_files. Execute one authorized working-thread step at a time. Open and explain the actual outputs. Rendering this kit completes no demo, practice or understanding checkpoint. Never replace a missing or blocked pipeline with authored output. Keep the tutorial local; a hosted step needs the user's separate explicit choice and normal workflow authority.",
        }
        (destination / "execution-request.json").write_text(
            json.dumps(execution, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        receipt = {
            "product": self.product,
            "workflow": workflow,
            "language": language,
            "course_revision": course["revision"],
            "prepared_material_only": True,
            "execution_receipt": False,
            "understanding_confirmed": False,
            "course": str(destination / "course.html"),
            "execution_request": str(destination / "execution-request.json"),
            "source_files": execution["source_files"],
            "practice_files": execution["practice_files"],
            "teacher": str(destination / "teacher.md"),
            "sources": course["sources"],
            "prepared_artifacts": [
                {
                    "path": path.relative_to(destination).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in sorted(destination.rglob("*"))
                if path.is_file()
            ],
        }
        (destination / "course-provenance.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return receipt

    def _shell(self, title: str, language: str, body: str) -> str:
        return (
            "<!doctype html>\n" + f"<html lang='{_esc(language)}'><head>"
            "<meta charset='utf-8'><meta name='google' content='notranslate'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'self'; font-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'\">"
            f"<title>{_esc(title)}</title><link rel='stylesheet' href='course.css'></head>"
            f"<body>{body}</body></html>\n"
        )

    def results(
        self,
        workflow: str,
        language: str,
        lesson: Path,
        record: str,
        destination: Path,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Present verified outputs and original downloads without changing the run."""
        from .execution import collect_execution

        course = self.load(workflow, language)
        lesson = lesson.resolve(strict=True)
        execution = _read(_inside(lesson, record))
        evidence = collect_execution(
            root=lesson,
            plugin_root=self.root,
            product=self.product,
            workflow=workflow,
            phase=execution["phase"],
            worker_thread_id=None,
            record_path=record,
            artifacts=execution["outputs"],
        )
        destination = destination.expanduser().absolute()
        if destination.exists() or any(p.is_symlink() for p in destination.parents):
            raise CourseError("Use a fresh ordinary result-view directory")
        assets = Path(__file__).parent / "assets"
        ui = _read(assets / "languages.json")[language]
        sections = []
        result_navigation = []
        downloads = []
        document_views = []
        source_pdf_previews = []
        source_links = {}
        source_labels = {}
        input_names = [Path(item["path"]).name for item in execution["inputs"]]
        website = {}
        decks = {}
        if self.product == "clara" and workflow in {"deck-correction", "html-deck"}:
            from .deck_view import deck_files

            decks = deck_files(lesson, execution, self.root)
            downloads.extend(
                (source, relative, digest)
                for source, (relative, digest) in decks.items()
            )
        if workflow == "presenza-digitale-studio":
            from .website_view import website_files

            website = website_files(lesson, execution)
            downloads.extend(
                (source, relative, digest)
                for source, (relative, digest) in website.items()
            )
        # Citations may open only inputs already verified by this execution.
        # Unknown paths and network URLs remain inert Markdown text.
        for index, item in enumerate(execution["inputs"]):
            source = _inside(lesson, item["path"])
            if source in decks:
                source_links[str(source)] = decks[source][0]
                source_labels[str(source)] = ui["original_deck"]
                continue
            if source.suffix.lower() not in {
                ".md",
                ".txt",
                ".csv",
                ".xml",
                ".json",
                ".xlsx",
                ".docx",
                ".pdf",
            }:
                continue
            view_path = f"source-{index + 1:02d}.html"
            download = f"outputs/source-{index + 1:02d}-{source.name}"
            source_links[str(source)] = view_path
            source_label = source.name
            if input_names.count(source.name) > 1:
                relative = Path(item["path"])
                phase = relative.parts[0].partition("-")[0]
                context = (
                    ui[f"{phase}_source"]
                    if phase in {"demo", "practice"}
                    else relative.parent.as_posix()
                )
                source_label = f"{context} — {source.name}"
            source_labels[str(source)] = source_label
            downloads.append((source, download, item["sha256"]))
            if source.suffix.lower() in {".xlsx", ".docx"}:
                from .document_view import office_body

                source_body = office_body(source, ui)
            elif source.suffix.lower() == ".pdf":
                source_body = f"<!--source-pdf-{index}-->"
                source_pdf_previews.append((source, view_path, source_body))
            else:
                source_text = source.read_text(encoding="utf-8-sig")
                source_body = f"<pre class='source-text'>{_esc(source_text)}</pre>"
                if source.suffix.lower() == ".csv":
                    source_body = _csv_input(source_text, ui)
                elif source.suffix.lower() == ".md":
                    source_body = _text_outline(source_text)
            document_views.append(
                (
                    view_path,
                    self._shell(
                        source_label,
                        language,
                        f"<main class='report'><a href='course.html'>{_esc(ui['back_to_results'])}</a>"
                        f"<h1>{_esc(source_label)}</h1><p>{_esc(item['path'])}</p>"
                        f"{source_body}"
                        f"<p><a href='{_esc(download)}' download='{_esc(source.name)}'>{_esc(ui['download_original'])}</a></p></main>",
                    ),
                )
            )
        # This workflow delivers its readable assignment plan in the standard
        # run review; its JSON contract is the machine handoff, not the first read.
        primary_result = (
            "codex_run_review.md"
            if (self.product, workflow) == ("clara", "advisory-brief-planner")
            else (
                "report.html"
                if (self.product, workflow) == ("clara", "attribute-reporting")
                else None
            )
        )
        ordered_outputs = sorted(
            execution["outputs"],
            key=lambda item: (
                0
                if Path(item["path"]).name == primary_result
                else (
                    2
                    if Path(item["path"]).name
                    in {
                        "artifact_card.md",
                        "codex_run_review.md",
                        "validation_package.md",
                    }
                    else 1
                )
            ),
        )
        result_links = {
            str(_inside(lesson, item["path"])): f"#result-{index + 1:02d}"
            for index, item in enumerate(ordered_outputs)
        }
        for index, item in enumerate(ordered_outputs):
            source = _inside(lesson, item["path"])
            # Resolve relative citations against this actual output, and only
            # to already verified input/output records. No link discovery.
            verified_links = {**source_links, **result_links}
            output_source_links = {
                **verified_links,
                **{
                    Path(os.path.relpath(path, source.parent)).as_posix(): view
                    for path, view in verified_links.items()
                },
            }
            binary_document = source.suffix.lower() in {".xlsx", ".docx", ".pdf"}
            binary_image = source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            binary_package = bool(decks) and source.suffix.lower() == ".zip"
            if source in website and source.suffix.lower() != ".html":
                # Assets travel with the real site; do not display CSS as a lesson.
                continue
            if not (
                binary_document or binary_image or binary_package
            ) and source.suffix.lower() not in {
                ".csv",
                ".md",
                ".txt",
                ".json",
                ".jsonl",
                ".html",
                ".xml",
            }:
                raise CourseError(
                    "Unsupported result format; use a reviewed document or text output"
                )
            download = f"outputs/{index + 1:02d}-{source.name}"
            downloads.append((source, download, item["sha256"]))
            link = f"<p><a href='{_esc(download)}' download='{_esc(source.name)}'>{_esc(ui['download_original'])}</a></p>"
            text = (
                ""
                if (binary_document or binary_image or binary_package)
                else source.read_text(encoding="utf-8-sig")
            )
            content = (
                f"<p>{_esc(ui['native_result_note'])}</p>"
                if binary_document
                else f"<pre class='source-text'>{_esc(text)}</pre>"
            )
            if binary_image:
                from PIL import Image, UnidentifiedImageError

                try:
                    with Image.open(source) as picture:
                        expected_format = {
                            ".png": "PNG",
                            ".jpg": "JPEG",
                            ".jpeg": "JPEG",
                            ".webp": "WEBP",
                        }[source.suffix.lower()]
                        if (
                            picture.format != expected_format
                            or picture.width * picture.height > 40_000_000
                        ):
                            raise CourseError(
                                "Result image has an unsupported format or size"
                            )
                        picture.verify()
                except (
                    UnidentifiedImageError,
                    OSError,
                    Image.DecompressionBombError,
                ) as exc:
                    raise CourseError("Result image is unreadable") from exc
                label = ui["result_files"].get(source.name, source.name)
                content = f"<figure class='result-chart'><img src='{_esc(download)}' alt='{_esc(label)}' loading='lazy'></figure>"
            elif source in decks:
                content = f"<p><a class='button' href='{_esc(decks[source][0])}'>{_esc(ui['open_result'])}</a></p>"
            elif source in website:
                content = f"<p><a class='button' href='{_esc(website[source][0])}'>{_esc(ui['open_result'])}</a></p>"
                assets_links = "".join(
                    f"<li><a href='{_esc(relative)}' download='{_esc(asset.name)}'>{_esc(asset.name)}</a></li>"
                    for asset, (relative, _) in website.items()
                    if asset.suffix.lower() != ".html"
                )
                if assets_links:
                    content += f"<details><summary>{_esc(ui['website_assets'])}</summary><ul>{assets_links}</ul></details>"
            elif source.suffix.lower() == ".html":
                from .html_view import passive_html_body

                reading_body = passive_html_body(
                    text,
                    omit_controls=workflow
                    in {"business-planning", "attribute-reporting"},
                    report_metadata=(
                        workflow == "business-planning"
                        or (self.product, workflow) == ("clara", "attribute-reporting")
                    ),
                )
                view_path = f"result-{index + 1:02d}.html"
                label = ui["result_files"].get(source.name, source.name)
                input_links = "".join(
                    f"<li><a href='{_esc(view)}'>{_esc(source_labels[path])}</a></li>"
                    for path, view in source_links.items()
                )
                source_section = (
                    f"<section><h2>{_esc(ui['input_preview'])}</h2><ul>{input_links}</ul></section>"
                    if input_links
                    else ""
                )
                document_views.append(
                    (
                        view_path,
                        self._shell(
                            label,
                            language,
                            f"<main class='report'><a href='course.html'>{_esc(ui['back_to_results'])}</a>"
                            f"<h1>{_esc(label)}</h1><p>{_esc(ui['html_reading_note'])}</p>"
                            f"<article class='html-reading'>{reading_body}</article>"
                            + source_section
                            + link
                            + "</main>",
                        ),
                    )
                )
                content = f"<p><a class='button' href='{view_path}'>{_esc(ui['open_result'])}</a></p>"
                link = ""
            elif source.suffix.lower() in {".xlsx", ".docx"}:
                from .document_view import office_body

                view_path = f"result-{index + 1:02d}.html"
                label = ui["result_files"].get(source.name, source.name)
                document_body = (
                    f"<main class='report'><a href='course.html'>{_esc(ui['back_to_results'])}</a>"
                    f"<h1>{_esc(label)}</h1><p class='caption'>{_esc(source.name)}</p>"
                    + office_body(
                        source,
                        ui,
                        first_sheet=(
                            "Exceptions"
                            if source.name == "exception_workpaper.xlsx"
                            else None
                        ),
                    )
                    + link
                    + "</main>"
                )
                document_views.append(
                    (view_path, self._shell(label, language, document_body))
                )
                content = f"<p><a class='button' href='{view_path}'>{_esc(ui['open_result'])}</a></p>"
                link = ""
            elif source.suffix.lower() == ".csv":
                if (
                    source.name
                    in {"scenario_summary.csv", "assumption_application_ledger.csv"}
                    and workflow == "sales-plan"
                ):
                    from .sales_plan_view import sales_plan_body

                    table = sales_plan_body(source.name, text, ui, language)
                    content = (
                        table
                        + f"<details><summary>{_esc(ui['full_file'])}</summary>{content}</details>"
                    )
                    label = ui["result_files"].get(source.name, source.name)
                    sections.append(
                        f"<section id='result-{index + 1:02d}'><h2>{_esc(label)}</h2><p class='caption'>{_esc(source.name)}</p>{link}{content}</section>"
                    )
                    continue
                reader = csv.DictReader(io.StringIO(text))
                fields = reader.fieldnames or []
                preferred = columns or _RESULT_COLUMNS.get(source.name, fields)
                if workflow == "previdenza-inps" and not columns:
                    preferred = {
                        "timeline.csv": [
                            "date",
                            "description",
                            "source_fact_ids",
                            "review_status",
                        ],
                        "evidence_matrix.csv": [
                            "fact_id",
                            "statement",
                            "review_status",
                            "document_id",
                            "locator_kind",
                            "locator_value",
                            "quote",
                        ],
                        "file_inventory.csv": [
                            "document_id",
                            "relative_path",
                            "readability",
                            "limitations",
                        ],
                    }.get(source.name, preferred)
                shown = [c for c in preferred if c in fields] or fields
                rows = list(reader)
                head = "".join(
                    f"<th scope='col'>{_esc(ui['result_columns'].get(c, c))}</th>"
                    for c in shown
                )
                cells = "".join(
                    "<tr>"
                    + "".join(
                        f"<td>{_esc(ui.get('result_values', {}).get(c, {}).get(row.get(c), row.get(c)) or '')}</td>"
                        for c in shown
                    )
                    + "</tr>"
                    for row in rows
                )
                table = (
                    f"<div class='table-scroll'><table><thead><tr>{head}</tr></thead><tbody>{cells}</tbody></table></div>"
                    if rows
                    else f"<p>{_esc(ui['no_rows'])}</p>"
                )
                content = (
                    table
                    + f"<details><summary>{_esc(ui['full_file'])}</summary>{content}</details>"
                )
            elif source.name == "client_email.txt":
                content = (
                    _text_outline(text, links=output_source_links)
                    + f"<details><summary>{_esc(ui['full_file'])}</summary>{content}</details>"
                )
            elif source.suffix.lower() == ".md":
                # Resolve only sibling images already covered by execution evidence.
                # Never fetch Markdown URLs or discover files outside the record.
                images = {
                    Path(
                        other["path"]
                    ).name: f"outputs/{n + 1:02d}-{Path(other['path']).name}"
                    for n, other in enumerate(ordered_outputs)
                    if Path(other["path"]).parent == Path(item["path"]).parent
                    and Path(other["path"]).suffix.lower()
                    in {".png", ".jpg", ".jpeg", ".webp"}
                }
                content = (
                    _text_outline(text, images, output_source_links)
                    + f"<details><summary>{_esc(ui['full_file'])}</summary>{content}</details>"
                )
            elif source.suffix.lower() in {".json", ".jsonl", ".xml"}:
                content = f"<details><summary>{_esc(ui['full_file'])}</summary>{content}</details>"
            technical_summary = (
                source.name
                in {
                    "artifact_card.md",
                    "run_summary.md",
                    "codex_run_review.md",
                    "validation_package.md",
                }
                or (
                    (self.product, workflow) == ("clara", "attribute-reporting")
                    and (
                        source.name == "execution_notes.md"
                        or source.suffix.lower() == ".csv"
                    )
                )
                or (
                    source.name == "review_dossier.md"
                    and any(
                        Path(other["path"]).name == "review_dossier.html"
                        and Path(other["path"]).parent == Path(item["path"]).parent
                        for other in ordered_outputs
                    )
                )
            )
            if source.name == primary_result:
                technical_summary = False
            if technical_summary and len(ordered_outputs) > 1:
                content = f"<details><summary>{_esc(ui['full_file'])}</summary><pre class='source-text'>{_esc(text)}</pre></details>"
            label = ui["result_files"].get(source.name, source.name)
            if source in website:
                label = ui["website_result"]
            if (
                source.suffix.lower() == ".md"
                and (label == source.name or source.name == primary_result)
                and not technical_summary
            ):
                # Content-addressed filenames identify versions, not documents.
                # Prefer the document's own plain title in the reading view.
                heading, _, body_text = text.partition("\n")
                if heading.startswith("# ") and heading[2:].strip():
                    label = heading[2:].strip()
                    content = (
                        _text_outline(body_text, images, output_source_links)
                        + f"<details><summary>{_esc(ui['full_file'])}</summary>"
                        + f"<pre class='source-text'>{_esc(text)}</pre></details>"
                    )
            if technical_summary and len(ordered_outputs) == 1:
                # A summary can be the workflow's actual delivered result.
                # Do not hide the only result because of its conventional filename.
                heading, _, body_text = text.partition("\n")
                if heading.startswith("# "):
                    label = heading[2:].strip()
                    content = _text_outline(body_text, links=output_source_links)
            if source.suffix.lower() == ".xml":
                label = ui["xml_result"]
            if source in decks and workflow == "deck-correction":
                label = ui["corrected_deck"]
            if (self.product, workflow) == ("clara", "advisory-case-director"):
                # Native workpaper history retains its original title and bytes.
                # Identify its role in the reading view instead of presenting an
                # earlier recommendation as another current document.
                if source.suffix.lower() == ".md" and source.stem.startswith(
                    "advisory_workpaper."
                ):
                    label = f"{ui['previous_version']} — {label}"
                result_navigation.append(
                    f"<a href='#result-{index + 1:02d}'>{_esc(label)}</a>"
                )
            sections.append(
                f"<section id='result-{index + 1:02d}'><h2>{_esc(label)}</h2><p class='caption'>{_esc(source.name)}</p>{link}{content}</section>"
            )
        title = course["locales"][language]["title"]
        input_index = (
            f"<section><h2>{_esc(ui['input_preview'])}</h2><ul>"
            + "".join(
                f"<li><a href='{_esc(view)}'>{_esc(source_labels[path])}</a></li>"
                for path, view in source_links.items()
            )
            + "</ul></section>"
            if source_links
            else ""
        )
        body = (
            f"<main class='report'><p class='eyebrow'>{_esc(ui['live_results'])}</p>"
            f"<h1>{_esc(title)}</h1><p>{_esc(ui['result_view_note'])}</p>"
            + (
                f"<nav aria-label='{_esc(ui['result_navigation'])}'>"
                + "".join(result_navigation)
                + "</nav>"
                if len(result_navigation) > 1
                else ""
            )
            + "".join(sections)
            + input_index
            + "</main>"
        )
        destination.mkdir(parents=True)
        (destination / "outputs").mkdir()
        for source, view_path, placeholder in source_pdf_previews:
            pages = _pdf_pages(source, destination, Path(view_path).stem, ui)
            document_views = [
                (
                    (relative, page.replace(placeholder, pages))
                    if relative == view_path
                    else (relative, page)
                )
                for relative, page in document_views
            ]
        for source, relative, expected_hash in downloads:
            copied = destination / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, copied)
            if _digest(copied) != expected_hash:
                raise CourseError("Result changed while preparing its download")
        for relative, page in document_views:
            (destination / relative).write_text(page, encoding="utf-8")
        for name in (
            "course.css",
            "InstrumentSans-Regular.ttf",
            "InstrumentSans-SemiBold.ttf",
            "OFL.txt",
        ):
            shutil.copyfile(_inside(assets, name), destination / name)
        (destination / "course.html").write_text(
            self._shell(title, language, body), encoding="utf-8"
        )
        provenance = {
            "presentation_only": True,
            "execution": evidence,
            "outputs": execution["outputs"],
        }
        (destination / "result-view.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {"course": str(destination / "course.html"), **provenance}

    def _page(
        self,
        course: dict[str, Any],
        copy: dict[str, Any],
        ui: dict[str, Any],
        language: str,
        files: list[dict[str, Any]],
    ) -> str:
        labels = ui["stages"]
        nav = "".join(
            f"<a href='#step-{i}'><span>0{i+1}</span>{_esc(label)}</a>"
            for i, label in enumerate(labels)
        )

        def file_links(role: str) -> str:
            selected = [file for file in files if file["role"] == role]
            names = [Path(file["path"]).name for file in selected]
            links = []
            for file in selected:
                path = Path(file["path"])
                label = path.name
                if names.count(label) > 1:
                    # Keep the client/subfolder visible when basenames collide.
                    label = Path(*path.parts[2:]).as_posix()
                links.append(
                    f"<li><a href='{_esc(file.get('preview_path', file['path']))}'>{_esc(label)}</a></li>"
                )
            return "".join(links)

        downloads = file_links("source")
        practice_files = file_links("practice")
        parts = [
            f"<p class='lead'>{_esc(copy['scenario'])}</p><p>{_esc(copy['scope'])}</p>",
            f"<p>{_esc(copy['inputs'])}</p><ul>{downloads}</ul><blockquote>{_esc(copy['request'])}</blockquote>",
            _list(copy["steps"])
            + f"<aside class='paired'>{_esc(ui['live_rule'])}</aside>",
            _list(copy["deliverables"]) + f"<p>{_esc(copy['review'])}</p>",
            _list(copy["checkpoints"]) + f"<p>{_esc(ui['checkpoint_rule'])}</p>",
            f"<blockquote>{_esc(copy['practice'])}</blockquote><ul>{practice_files}</ul><p>{_esc(copy['success'])}</p><p>{_esc(copy['repeat'])}</p>",
        ]
        sections = "".join(
            f"<section id='step-{i}' class='lesson-step'><div class='section-label'><span>0{i+1}</span><h2>{_esc(labels[i])}</h2></div>"
            f"<div class='section-body'>{part}</div></section>"
            for i, part in enumerate(parts)
        )
        body = (
            f"<header class='masthead'><b>{_esc(self.product.title())}</b><span>{_esc(ui['series'])}</span><span>5–8 min · {_esc(language.upper())}</span></header>"
            f"<main><div class='hero'><p class='eyebrow'>{_esc(ui['prepared'])}</p><h1>{_esc(copy['title'])}</h1>"
            f"<p class='lead'>{_esc(copy['goal'])}</p><p class='caption'>{_esc(ui['timing'])}</p></div>"
            f"<aside class='paired'><b>{_esc(ui['two_threads'])}</b><p>{_esc(ui['pair_explanation'])}</p></aside>"
            f"<nav aria-label='{_esc(ui['contents'])}'>{nav}</nav>{sections}"
            f"<footer><p>{_esc(ui['kit_notice'])}</p><p>{_esc(ui['privacy'])}</p>"
            f"<a href='course-provenance.json'>{_esc(ui['provenance'])}</a> · {_esc(course['revision'])}</footer></main>"
        )
        return self._shell(copy["title"], language, body)

    def _teacher(
        self, course: dict[str, Any], copy: dict[str, Any], ui: dict[str, Any]
    ) -> str:
        blocks = [
            copy["goal"] + "\n\n" + copy["scenario"] + "\n\n" + copy["scope"],
            copy["inputs"] + "\n\n" + copy["request"],
            "\n\n".join(copy["steps"]) + "\n\n" + ui["live_rule"],
            "\n\n".join(copy["deliverables"]) + "\n\n" + copy["review"],
            "\n\n".join(copy["checkpoints"]) + "\n\n" + ui["checkpoint_rule"],
            copy["practice"] + "\n\n" + copy["success"] + "\n\n" + copy["repeat"],
        ]
        text = f"# {copy['title']}\n\n{ui['timing']}\n\n{ui['pair_explanation']}\n\n{ui['teacher_rule']}\n\n"
        for i, block in enumerate(blocks):
            text += f"## {i+1}. {ui['stages'][i]} · {course['seconds'][i]} s\n\n{ui['cues'][i]}\n\n{block}\n\n"
        return text + ui["kit_notice"] + "\n\n" + ui["privacy"] + "\n"


def main(plugin_root: Path, eligible: set[str], argv: list[str] | None = None) -> int:
    """Local CLI: catalog, inspect or render packaged content without user telemetry."""
    from .execution import ExecutionError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("list", "show", "render", "serve", "results")
    )
    parser.add_argument("--workflow")
    parser.add_argument("--language")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--lesson-dir", type=Path)
    parser.add_argument("--execution-record")
    parser.add_argument("--columns", nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.action == "serve":
            if not args.output_dir:
                parser.error("serve requires --output-dir pointing to a rendered kit")
            from .preview import serve

            serve(args.output_dir)
            return 0
        library = CourseLibrary(plugin_root, eligible)
        if args.action == "list":
            result: Any = library.catalog()
        else:
            if not args.workflow or not args.language:
                parser.error("--workflow and --language are required")
            if args.action == "results":
                if (
                    not args.output_dir
                    or not args.lesson_dir
                    or not args.execution_record
                ):
                    parser.error(
                        "results requires --lesson-dir, --execution-record and --output-dir"
                    )
                result = library.results(
                    args.workflow,
                    args.language,
                    args.lesson_dir,
                    args.execution_record,
                    args.output_dir,
                    args.columns,
                )
            elif args.action == "render":
                if not args.output_dir:
                    parser.error("render requires --output-dir")
                result = library.render(args.workflow, args.language, args.output_dir)
            else:
                course = library.load(args.workflow, args.language)
                result = {
                    "product": course["product"],
                    "workflow": course["workflow"],
                    "language": args.language,
                    "revision": course["revision"],
                    "seconds": course["seconds"],
                    "sources_current": True,
                    "source_count": len(course["sources"]),
                    "execution": course["execution"],
                    "group": course["group"],
                    "content": course["locales"][args.language],
                    "files": [asset["path"] for asset in course.get("files", [])],
                }
        # JSON escapes preserve all localized text on legacy Windows consoles.
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (
        CourseError,
        ExecutionError,
        OSError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        parser.exit(2, f"Course unavailable: {exc}\n")
    return 0
