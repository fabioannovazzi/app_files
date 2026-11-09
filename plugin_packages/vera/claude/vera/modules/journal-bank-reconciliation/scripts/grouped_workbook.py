"""The final, consistently structured four-sheet reconciliation deliverable."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import xlsxwriter

__all__ = ["export_final_workbook"]

LABELS = {
    "concordant": "Concorde",
    "proposed": "Proposta da confermare",
    "difference": "Scostamento",
    "unmatched": "Non rilevato nella fonte opposta",
    "needs_review": "Da approfondire",
}


def _movement_caption(row: Mapping[str, Any], label: str) -> str:
    """Keep each source's own reference and counterparty beside its workbook ID."""
    reference = str(row.get("reference") or "")
    counterparty = str(row.get("beneficiary") or "")
    identifier = f"{label} · {reference}" if reference else label
    return f"{identifier}\n{counterparty}" if counterparty else identifier


def export_final_workbook(
    path: Path,
    result: Mapping[str, Any],
    bank: Sequence[Mapping[str, Any]],
    journal: Sequence[Mapping[str, Any]],
    *,
    source_evidence: Mapping[str, str] | None = None,
    client_label: str = "",
) -> None:
    """Render checked group decisions, preserving distinct accounting statuses.

    Formulas perform only mechanical totals/counts. Semantic conclusions come
    from the retained review; no amount-only rule invents a relationship here.
    The normal producer uses the existing declared, portable XLSX dependency.
    """
    summary = result["summary"]
    currency = summary["currency"]
    relations = result["relations"]
    evidence = source_evidence or {}
    bank_labels = {
        row["transaction_id"]: f"B{number:03d}" for number, row in enumerate(bank, 1)
    }
    journal_labels = {
        row["transaction_id"]: f"C{number:03d}" for number, row in enumerate(journal, 1)
    }
    bank_group = {row_id: group for group in relations for row_id in group["bank_ids"]}
    journal_group = {
        row_id: group for group in relations for row_id in group["journal_ids"]
    }
    bank_by_id = {row["transaction_id"]: row for row in bank}
    journal_by_id = {row["transaction_id"]: row for row in journal}
    if len(bank_group) != len(bank) or len(journal_group) != len(journal):
        raise ValueError("Final workbook requires complete non-reusing source coverage")
    with xlsxwriter.Workbook(
        path, {"strings_to_formulas": False, "strings_to_urls": False}
    ) as book:
        base = {
            "font_name": "Arial",
            "font_size": 10,
            "font_color": "#182536",
            "valign": "top",
        }
        text = book.add_format({**base, "text_wrap": True})
        title = book.add_format(
            {**base, "bold": True, "font_size": 16, "font_color": "#163E66"}
        )
        note = book.add_format(
            {**base, "italic": True, "font_color": "#526173", "text_wrap": True}
        )
        header = book.add_format(
            {
                **base,
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#163E66",
                "text_wrap": True,
            }
        )
        money = book.add_format({**base, "num_format": '#,##0.00;[Red](#,##0.00);"–"'})
        integer = book.add_format({**base, "num_format": "0"})
        date_format = book.add_format({**base, "num_format": "dd/mm/yyyy"})
        bold = book.add_format({**base, "bold": True})
        status_formats = {
            "concordant": book.add_format(
                {**base, "font_color": "#246044", "text_wrap": True}
            ),
            "proposed": book.add_format(
                {**base, "font_color": "#8A6315", "text_wrap": True}
            ),
            "difference": book.add_format(
                {**base, "font_color": "#9C3030", "text_wrap": True}
            ),
            "unmatched": book.add_format(
                {**base, "font_color": "#9C3030", "text_wrap": True}
            ),
            "needs_review": book.add_format(
                {**base, "font_color": "#8A6315", "text_wrap": True}
            ),
        }
        sheets = {
            name: book.add_worksheet(name)
            for name in ("Sintesi", "Relazioni", "Banca", "Partitario")
        }
        for sheet in sheets.values():
            sheet.hide_gridlines(2)
            sheet.set_default_row(16)
            sheet.set_landscape()
            sheet.fit_to_pages(1, 0)
            sheet.set_margins(0.3, 0.3, 0.4, 0.4)
            sheet.set_footer("&CPagina &P di &N")
        relation_rows = {g["id"]: number + 6 for number, g in enumerate(relations)}
        source_rows: dict[str, int] = {}
        for name, rows, mapping in (
            ("Banca", bank, bank_group),
            ("Partitario", journal, journal_group),
        ):
            sheet = sheets[name]
            sheet.merge_range("A1:L1", name, title)
            sheet.merge_range(
                "A2:L2",
                "Ogni riga appartiene a una sola relazione. I riferimenti alla fonte restano visibili.",
                note,
            )
            columns = [
                "ID movimento",
                "Relazione",
                "Data",
                "Riferimento originale",
                "Controparte",
                "Descrizione",
                f"Importo {currency}",
                "Esito",
                "File / pagina o foglio / riga",
                "Evidenza originale",
                "Documenti richiesti",
                "Metodo",
            ]
            sheet.write_row(4, 0, columns, header)
            for column, width in enumerate(
                (12, 13, 13, 24, 32, 52, 17, 25, 48, 70, 55, 18)
            ):
                sheet.set_column(column, column, width)
            sheet.freeze_panes(5, 2)
            for index, row in enumerate(rows, 5):
                group = mapping[row["transaction_id"]]
                labels = bank_labels if name == "Banca" else journal_labels
                sheet.write_string(index, 0, labels[row["transaction_id"]], text)
                sheet.write_url(
                    index,
                    1,
                    f"internal:'Relazioni'!A{relation_rows[group['id']]}",
                    text,
                    group["id"],
                )
                sheet.write_datetime(
                    index,
                    2,
                    date.fromisoformat(str(row["transaction_date"])),
                    date_format,
                )
                sheet.write_string(index, 3, str(row.get("reference") or ""), text)
                sheet.write_string(index, 4, str(row.get("beneficiary") or ""), text)
                sheet.write_string(index, 5, str(row.get("description") or ""), text)
                sheet.write_number(
                    index, 6, float(Decimal(str(row["amount_signed"]))), money
                )
                sheet.write_string(
                    index, 7, LABELS[group["status"]], status_formats[group["status"]]
                )
                locator = f"{row['source_file']} · {row['source_sheet']} · riga {row['source_row']}"
                sheet.write_string(index, 8, locator, text)
                sheet.write_string(
                    index, 9, evidence.get(str(row["transaction_id"]), ""), text
                )
                sheet.write_string(
                    index, 10, "\n".join(group["required_documents"]), text
                )
                sheet.write_string(
                    index,
                    11,
                    (
                        "Rigoroso"
                        if group.get("method") == "strict"
                        else "Revisione a gruppo"
                    ),
                    text,
                )
                sheet.set_row(index, 52)
                source_rows[str(row["transaction_id"])] = index + 1
            sheet.autofilter(4, 0, max(4, len(rows) + 4), 11)
            sheet.repeat_rows(0, 4)
            sheet.print_area(0, 0, len(rows) + 4, 11)

        sheet = sheets["Relazioni"]
        sheet.merge_range("A1:J1", "Relazioni tra banca e partitario", title)
        sheet.merge_range(
            "A2:J2",
            "Gruppi espliciti, importi controllati e verifiche ancora necessarie. Nessuna scrittura è stata registrata.",
            note,
        )
        sheet.write_row(
            4,
            0,
            [
                "Relazione",
                "Movimenti banca",
                "Righe partitario",
                f"Totale banca {currency}",
                f"Totale partitario {currency}",
                f"Differenza {currency}",
                "Esito",
                "Operazione",
                "Evidenza / spiegazione",
                "Verifica / documenti necessari",
            ],
            header,
        )
        for column, width in enumerate((13, 34, 34, 18, 18, 18, 25, 40, 75, 70)):
            sheet.set_column(column, column, width)
        sheet.freeze_panes(5, 1)
        bank_end = max(6, len(bank) + 5)
        journal_end = max(6, len(journal) + 5)
        for index, group in enumerate(relations, 5):
            excel_row = index + 1
            sheet.write_string(index, 0, group["id"], text)
            caption_lines = 1
            for column, key in ((1, "bank_ids"), (2, "journal_ids")):
                labels = bank_labels if key == "bank_ids" else journal_labels
                records = bank_by_id if key == "bank_ids" else journal_by_id
                caption = "\n".join(
                    _movement_caption(records[i], labels[i]) for i in group[key]
                )
                caption_lines = max(caption_lines, len(caption.splitlines()))
                sheet.write_string(index, column, caption, text)
            sheet.write_formula(
                index,
                3,
                f"=SUMIF(Banca!$B$6:$B${bank_end},A{excel_row},Banca!$G$6:$G${bank_end})",
                money,
                float(Decimal(group["bank_sum"])),
            )
            sheet.write_formula(
                index,
                4,
                f"=SUMIF(Partitario!$B$6:$B${journal_end},A{excel_row},Partitario!$G$6:$G${journal_end})",
                money,
                float(Decimal(group["journal_sum"])),
            )
            sheet.write_formula(
                index,
                5,
                f"=D{excel_row}-E{excel_row}",
                money,
                float(Decimal(group["difference"])),
            )
            sheet.write_string(
                index, 6, LABELS[group["status"]], status_formats[group["status"]]
            )
            sheet.write_string(index, 7, group["title"], text)
            sheet.write_string(index, 8, group["rationale"], text)
            sheet.write_string(index, 9, "\n".join(group["required_documents"]), text)
            minimum_height = 72 if group.get("method") != "strict" else 44
            sheet.set_row(index, min(409, max(minimum_height, caption_lines * 16)))
        sheet.autofilter(4, 0, max(4, len(relations) + 4), 9)
        sheet.repeat_rows(0, 4)
        sheet.print_area(0, 0, len(relations) + 4, 9)

        sheet = sheets["Sintesi"]
        sheet.set_column("A:A", 44)
        sheet.set_column("B:B", 22)
        sheet.set_column("C:C", 22)
        sheet.set_column("D:F", 24)
        sheet.merge_range(
            "A1:F1",
            f"{client_label + ' — ' if client_label else ''}Riconciliazione banca / partitario",
            title,
        )
        dates = sorted(str(row["transaction_date"]) for row in bank)
        period = f"{dates[0]} – {dates[-1]}" if dates else "Nessun movimento bancario"
        sheet.merge_range(
            "A2:F2",
            f"Periodo dei movimenti: {period}. Valuta {currency}. Revisione completata; verifiche documentali come indicate.",
            note,
        )
        sheet.write_row(
            4, 0, ["Controllo", "Banca", "Partitario", "Banca meno partitario"], header
        )
        for index, (label, positive) in enumerate(
            (("Entrate", True), ("Uscite", False)), 5
        ):
            sheet.write(index, 0, label, text)
            values = []
            for column, (name, rows, end) in enumerate(
                (("Banca", bank, bank_end), ("Partitario", journal, journal_end)), 1
            ):
                value = sum(
                    (
                        Decimal(str(row["amount_signed"]))
                        for row in rows
                        if (Decimal(str(row["amount_signed"])) > 0) == positive
                    ),
                    Decimal(0),
                )
                if not positive:
                    value = -value
                criterion = '">0"' if positive else '"<0"'
                formula = (
                    "" if positive else "-"
                ) + f"SUMIF({name}!$G$6:$G${end},{criterion},{name}!$G$6:$G${end})"
                sheet.write_formula(index, column, "=" + formula, money, float(value))
                values.append(value)
            sheet.write_formula(
                index, 3, f"=B{index+1}-C{index+1}", money, float(values[0] - values[1])
            )
        sheet.write(7, 0, "Variazione netta", bold)
        sheet.write_formula(7, 1, "=B6-B7", money, float(Decimal(summary["bank_net"])))
        sheet.write_formula(
            7, 2, "=C6-C7", money, float(Decimal(summary["journal_net"]))
        )
        sheet.write_formula(
            7, 3, "=B8-C8", money, float(Decimal(summary["bank_minus_journal"]))
        )
        sheet.write_row(
            10, 0, ["Copertura e stato delle righe banca", "Numero"], header
        )
        sheet.write(11, 0, "Movimenti bancari", text)
        sheet.write_number(11, 1, len(bank), integer)
        sheet.write(12, 0, "Righe del partitario", text)
        sheet.write_number(12, 1, len(journal), integer)
        sheet.write(13, 0, "Abbinamenti rigorosi conservati", text)
        sheet.write_number(13, 1, summary["strict_match_count"], integer)
        for index, status in enumerate(LABELS, 14):
            count = summary["bank_status_counts"].get(status, 0)
            sheet.write(index, 0, LABELS[status], text)
            sheet.write_formula(
                index,
                1,
                f'=COUNTIF(Banca!$H$6:$H${bank_end},"{LABELS[status]}")',
                integer,
                count,
            )
        notes = [
            "Le corrispondenze riguardano il movimento del conto banca. Non certificano l'allocazione a una fattura né la corretta contropartita contabile.",
            "Gli importi e le date di ogni fonte restano invariati. I raggruppamenti e gli scarti sono espliciti nel foglio Relazioni.",
            "Le proposte richiedono i documenti indicati. Non sono automaticamente promosse a corrispondenze confermate.",
            "I totali sono variazioni dei movimenti forniti. Per confermare il saldo finale servono estratti con saldi iniziale e finale datati.",
        ]
        for index, line in enumerate(notes, 21):
            sheet.merge_range(index, 0, index, 5, line, note)
            sheet.set_row(index, 34)
        sheet.print_area("A1:F25")
        sheet.set_portrait()
