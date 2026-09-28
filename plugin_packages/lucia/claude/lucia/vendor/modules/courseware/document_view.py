"""Read verified Office outputs as escaped HTML without executing their contents."""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from typing import Any

__all__ = ["office_body"]

_MAX_ROWS = 500
_MAX_COLUMNS = 80


def _esc(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        value = value.isoformat()
    return html.escape(str(value), quote=True)


def _table(rows: list[list[object]], *, span_titles: bool = False) -> str:
    if not rows:
        return ""

    def cells(row: list[object], tag: str) -> str:
        if (
            span_titles
            and row[0] not in (None, "")
            and all(value in (None, "") for value in row[1:])
        ):
            return f"<{tag} colspan='{len(row)}'>{_esc(row[0])}</{tag}>"
        scope = " scope='col'" if tag == "th" else ""
        return "".join(f"<{tag}{scope}>{_esc(v)}</{tag}>" for v in row)

    head = cells(rows[0], "th")
    body = "".join("<tr>" + cells(row, "td") + "</tr>" for row in rows[1:])
    return (
        "<div class='table-scroll' tabindex='0'><table><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


def _sheet_hidden_cells(path: Path, member: str) -> tuple[set[int], set[int]]:
    """Read visibility metadata without loading a complete worksheet into memory."""
    from zipfile import ZipFile

    from defusedxml.ElementTree import iterparse

    hidden_columns: set[int] = set()
    hidden_rows: set[int] = set()
    with ZipFile(path) as archive, archive.open(member) as source:
        for event, element in iterparse(source, events=("start", "end")):
            tag = element.tag.rsplit("}", 1)[-1]
            if (
                event == "start"
                and tag == "col"
                and element.get("hidden") in {"1", "true"}
            ):
                hidden_columns.update(
                    range(
                        max(1, int(element.get("min", "1"))),
                        min(_MAX_COLUMNS, int(element.get("max", "1"))) + 1,
                    )
                )
            if event == "start" and tag == "row":
                number = int(element.get("r", "0"))
                if number > _MAX_ROWS:
                    break
                if element.get("hidden") in {"1", "true"}:
                    hidden_rows.add(number)
            if event == "end":
                element.clear()
    return hidden_columns, hidden_rows


def _stored_value(cell: Any) -> object:
    """Respect simple percentage units without evaluating formulas or editing cells."""
    value = cell.value
    pattern = re.fullmatch(
        r"0(?:\.(0{1,12}))?%", getattr(cell, "number_format", "") or ""
    )
    if pattern and isinstance(value, (int, float)) and not isinstance(value, bool):
        decimal = Decimal(str(value))
        if decimal.is_finite():
            places = len(pattern.group(1) or "")
            with localcontext() as context:
                context.prec = max(
                    28,
                    len(decimal.as_tuple().digits)
                    + abs(decimal.adjusted())
                    + places
                    + 5,
                )
                shown = (decimal * 100).quantize(
                    Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP
                )
            return f"{shown:.{places}f}%"
    return value


def _workbook_body(
    path: Path, ui: dict[str, Any], first_sheet: str | None = None
) -> str:
    from openpyxl import load_workbook

    values = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    formulas = None
    try:
        formulas = load_workbook(
            path, read_only=True, data_only=False, keep_links=False
        )
        visible = [s for s in values if s.sheet_state == "visible"]
        if first_sheet:
            visible.sort(key=lambda sheet: sheet.title != first_sheet)
        parts = [f"<p>{_esc(ui['workbook_reading_note'])}</p>"]
        for i, sheet in enumerate(visible):
            data = []
            hidden_columns, hidden_rows = _sheet_hidden_cells(
                path, formulas[sheet.title]._worksheet_path
            )
            source_rows = formulas[sheet.title].iter_rows(
                max_row=min(sheet.max_row or 1, _MAX_ROWS),
                max_col=min(sheet.max_column or 1, _MAX_COLUMNS),
            )
            cached_rows = sheet.iter_rows(
                max_row=min(sheet.max_row or 1, _MAX_ROWS),
                max_col=min(sheet.max_column or 1, _MAX_COLUMNS),
            )
            for row_number, (source, cached) in enumerate(
                zip(source_rows, cached_rows), start=1
            ):
                if row_number in hidden_rows:
                    continue
                data.append(
                    [
                        (
                            ui["formula_cache_missing"]
                            if original.data_type == "f" and cell.value is None
                            else _stored_value(cell)
                        )
                        for column_number, (original, cell) in enumerate(
                            zip(source, cached), start=1
                        )
                        if column_number not in hidden_columns
                    ]
                )
            # A workflow may lead with its review sheet; retain every visible sheet.
            limited = (sheet.max_row or 0) > _MAX_ROWS or (
                sheet.max_column or 0
            ) > _MAX_COLUMNS
            notice = (
                f"<p>{_esc(ui['sheet_preview_limit'].format(rows=_MAX_ROWS, columns=_MAX_COLUMNS))}</p>"
                if limited
                else ""
            )
            # Styled empty margins are not content. Keep interior cells and rows
            # in order, but do not force the reader through an empty print area.
            while data and all(value in (None, "") for value in data[0]):
                data.pop(0)
            while data and all(value in (None, "") for value in data[-1]):
                data.pop()
            width = max(
                (
                    i + 1
                    for row in data
                    for i, value in enumerate(row)
                    if value not in (None, "")
                ),
                default=0,
            )
            data = [row[:width] for row in data]
            content = _table(data, span_titles=True)
            if first_sheet == "Exceptions" and sheet.title == first_sheet and data:
                fields = ui["invoice_exception_fields"]
                headers = data[0]
                if all(key in headers for key in fields):
                    records = []
                    for row in data[1:]:
                        cells = "".join(
                            f"<tr><th scope='row'>{_esc(label)}</th>"
                            f"<td>{_esc(row[headers.index(key)])}</td></tr>"
                            for key, label in fields.items()
                        )
                        records.append(f"<table><tbody>{cells}</tbody></table>")
                    content = (
                        (
                            "".join(records)
                            if records
                            else f"<p>{_esc(ui['no_rows'])}</p>"
                        )
                        + f"<details><summary>{_esc(ui['full_file'])}</summary>{content}</details>"
                    )
            parts.append(
                f"<details id='sheet-{i}' class='sheet-view'{' open' if i == 0 else ''}>"
                f"<summary>{_esc(sheet.title)}</summary>{notice}{content}</details>"
            )
        return "".join(parts)
    finally:
        values.close()
        if formulas is not None:
            formulas.close()


def _word_body(path: Path, ui: dict[str, Any]) -> str:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(path)
    parts = [f"<p>{_esc(ui['word_reading_note'])}</p>"]
    for element in document.element.body:
        if element.tag == qn("w:p"):
            paragraph = Paragraph(element, document)
            text = paragraph.text
            if not text.strip():
                continue
            style = paragraph.style.name if paragraph.style else ""
            tag = (
                "h2"
                if style in {"Title", "Heading 1"}
                else "h3" if style.startswith("Heading") else "p"
            )
            parts.append(f"<{tag}>{_esc(text)}</{tag}>")
        elif element.tag == qn("w:tbl"):
            table = Table(element, document)
            parts.append(
                _table([[cell.text for cell in row.cells] for row in table.rows])
            )
    return "".join(parts)


def office_body(
    path: Path, ui: dict[str, Any], *, first_sheet: str | None = None
) -> str:
    """Present only local stored values/text; no macros, formulas or remote links run."""
    if path.suffix.lower() == ".xlsx":
        return _workbook_body(path, ui, first_sheet)
    if path.suffix.lower() == ".docx":
        return _word_body(path, ui)
    raise ValueError("Reading view requires a Word or Excel document")
