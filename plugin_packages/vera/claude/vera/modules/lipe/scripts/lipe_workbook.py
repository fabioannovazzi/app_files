"""Portable three-sheet LIPE workpaper with inspectable, cached Excel formulas."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import xlsxwriter
from lipe_core import money
from xlsxwriter.utility import xl_col_to_name

__all__ = ["write_workbook"]

FIELDS = (
    "vp2",
    "vp3",
    "vp4",
    "vp5",
    "vp6_debit",
    "vp6_credit",
    "vp7",
    "vp8",
    "vp9",
    "vp10",
    "vp11",
    "vp12",
    "vp13",
    "vp14_debit",
    "vp14_credit",
)
LABELS = (
    "VP2 · Operazioni attive",
    "VP3 · Operazioni passive",
    "VP4 · IVA esigibile",
    "VP5 · IVA detratta",
    "VP6 · Debito",
    "VP6 · Credito",
    "VP7 · Debito precedente",
    "VP8 · Credito precedente",
    "VP9 · Credito annuale",
    "VP10 · Auto UE",
    "VP11 · Crediti d'imposta",
    "VP12 · Interessi",
    "VP13 · Acconto",
    "VP14 · Da versare",
    "VP14 · A credito",
)
STATUS = {
    "MATCH": "Coincide",
    "NOT_REPORTED": "Codice assente in liquidazione",
    "NO_REGISTER_ROWS": "Nessuna riga di registro",
    "BASIS_NOT_CONFIRMED": "Criterio da confermare",
    "DIFFERENCE_TO_REVIEW": "Scarto da esaminare",
}
BASIS = {
    "REGISTRATION": "Registrazione",
    "CHARGEABILITY": "Esigibilità",
    "DEDUCTION": "Detrazione",
    "RECORDED": "IVA registrata",
    "OUTPUT": "IVA esigibile",
    "DEDUCTIBLE": "IVA detraibile",
}


def _source(ref: dict | None) -> str:
    return (
        "Non disponibile" if ref is None else f"{ref['source_id']} · p. {ref['page']}"
    )


def _number(value: str | None) -> float | None:
    return None if value is None else float(money(value))


def _formats(book: Any) -> dict:
    common = {"font_name": "Arial", "font_size": 10, "valign": "vcenter"}
    return {
        "text": book.add_format(common),
        "wrapped": book.add_format({**common, "text_wrap": True, "valign": "top"}),
        "title": book.add_format({**common, "font_size": 16, "font_color": "#123A5C"}),
        "header": book.add_format(
            {
                **common,
                "bold": True,
                "bg_color": "#123A5C",
                "font_color": "#FFFFFF",
                "align": "center",
                "text_wrap": True,
            }
        ),
        "note": book.add_format({**common, "italic": True, "font_color": "#535D66"}),
        "input": book.add_format(
            {
                **common,
                "num_format": "#,##0.00;[Red](#,##0.00);0.00",
                "font_color": "#245B94",
            }
        ),
        "money": book.add_format(
            {**common, "num_format": "#,##0.00;[Red](#,##0.00);0.00"}
        ),
        "percent": book.add_format(
            {**common, "num_format": "0%", "font_color": "#245B94"}
        ),
        "warning": book.add_format(
            {**common, "font_color": "#9C2424", "bg_color": "#FCE8E6"}
        ),
    }


def _sheet(
    book: Any, name: str, title: str, case: dict, result: dict, fmt: dict
) -> Any:
    sheet = book.add_worksheet(name)
    sheet.hide_gridlines(2)
    sheet.set_default_row(20)
    sheet.set_column("A:A", 3)
    sheet.set_column("B:B", 29, fmt["text"])
    sheet.set_column("C:P", 18, fmt["text"])
    sheet.write_string("B2", title, fmt["title"])
    sheet.write_string(
        "B3",
        f"LIPE · {case['tax_year']} · trimestre {case['quarter']} · {case['client_id']}",
        fmt["text"],
    )
    origin = "DATI SINTETICI · " if case["data_origin"] == "SYNTHETIC" else ""
    sheet.write_string(
        "B4",
        origin
        + "Bozza da rivedere. Le modifiche Excel non approvano né aggiornano il fascicolo.",
        fmt["note"],
    )
    sheet.write_string(
        "B5",
        "Celle blu: dati del fascicolo. Vuoto: dato assente o rigo non compilabile. Importi in euro.",
        fmt["note"],
    )
    sheet.set_tab_color("#123A5C")
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.set_paper(9)
    sheet.set_footer("LIPE · bozza · &P / &N")
    sheet.repeat_rows(0, 5)
    sheet.set_header("&L" + result["result_hash"][:16])
    return sheet


def _reconciliation(sheet: Any, result: dict, fmt: dict) -> None:
    headers = [
        "Periodo",
        "Registro",
        "Codice IVA",
        "Criterio base",
        "Criterio IVA",
        "Base registro",
        "Base liquidazione",
        "Scarto base",
        "IVA registro",
        "IVA liquidazione",
        "Scarto IVA",
        "Esito",
        "Fonti registro",
        "Fonte liquidazione",
        "Righe registro",
        "Spiegazione registrata",
    ]
    sheet.write_row("B7", headers, fmt["header"])
    sheet.set_row(6, 32)
    sheet.set_column("B:B", 10)
    sheet.set_column("M:M", 29)
    sheet.set_column("N:P", 34)
    sheet.set_column("Q:Q", 65, fmt["wrapped"])
    for index, item in enumerate(result["reconciliation"], 8):
        values = [
            item["period"],
            {
                "SALES": "Vendite",
                "PURCHASES": "Acquisti",
                "INTEGRATION": "Integrazioni",
            }[item["side"]],
            item["code"],
            BASIS[item["base_basis"]],
            BASIS[item["tax_basis"]],
            *[
                _number(item[k])
                for k in (
                    "register_base",
                    "liquidation_base",
                    "base_difference",
                    "register_tax",
                    "liquidation_tax",
                    "tax_difference",
                )
            ],
            STATUS[item["status"]],
            "; ".join(dict.fromkeys(_source(ref) for ref in item["register_evidence"])),
            _source(item["liquidation_evidence"]),
            "; ".join(item["register_rows"]),
            "\n".join(
                f"{explanation['observation_id']}: {explanation['assessment']} "
                + (
                    "(decisione registrata)"
                    if explanation["state"] == "RESOLUTION_RECORDED"
                    else "(proposta da rivedere)"
                )
                for explanation in item["explanations"]
            )
            or (
                "Nessuno scarto numerico"
                if item["status"] == "MATCH"
                else "Da chiarire"
            ),
        ]
        sheet.write_row(index - 1, 1, values, fmt["text"])
        sheet.write_string(index - 1, 16, values[-1], fmt["wrapped"])
        # Excel caps row height: retain the full text and point to the dossier.
        # Long explanations remain inspectable in the formula bar and dossier.
        explanation_lines = sum(
            max(1, (len(line) + 59) // 60) for line in values[-1].splitlines()
        )
        sheet.set_row(index - 1, min(400, max(20, explanation_lines * 15 + 5)))
        if explanation_lines > 26:
            sheet.write_comment(
                index - 1,
                16,
                "Testo completo in anomalies.md; ogni osservazione conserva fonti e decisione.",
            )
        for col in (6, 7, 9, 10):
            sheet.write(index - 1, col, values[col - 1], fmt["input"])
        for target, left, right, key in (
            ("I", "G", "H", "base_difference"),
            ("L", "J", "K", "tax_difference"),
        ):
            sheet.write_formula(
                f"{target}{index}",
                f'=IF(COUNT({left}{index}:{right}{index})=2,ROUND({left}{index}-{right}{index},2),"")',
                fmt["money"],
                _number(item[key]) if item[key] is not None else "",
            )
        # Meaning of absence comes from reviewed evidence, not the numeric scarto.
        sheet.write_formula(
            f"M{index}",
            f'=IF(OR(COUNT(G{index}:H{index})<2,COUNT(J{index}:K{index})<2),"{STATUS[item["status"]]}",IF(OR(I{index}<>0,L{index}<>0),"Scarto da esaminare","Coincide"))',
            fmt["text"],
            STATUS[item["status"]],
        )
    end = max(8, len(result["reconciliation"]) + 7)
    sheet.autofilter(f"B7:Q{end}")
    sheet.freeze_panes(7, 4)
    for col in ("I", "L"):
        sheet.conditional_format(
            f"{col}8:{col}{end}",
            {"type": "cell", "criteria": "!=", "value": 0, "format": fmt["warning"]},
        )
    sheet.print_area(f"B2:Q{end}")


def _vp(sheet: Any, case: dict, result: dict, fmt: dict) -> None:
    code_by_row = {
        row["row_id"]: row["code"] for reg in case["registers"] for row in reg["rows"]
    }
    contributions = [
        (line, part) for line in result["composition"] for part in line["contributions"]
    ]
    sheet.write_row(
        "B60",
        ["Periodo", "Codice IVA", "Rigo VP", "Importo", "Riga registro", "Fonte"],
        fmt["header"],
    )
    for row_number, (line, part) in enumerate(contributions, 61):
        sheet.write_row(
            row_number - 1,
            1,
            [
                part["period"],
                code_by_row[line["row_id"]],
                part["field"],
                _number(part["amount"]),
                line["row_id"],
                _source(line["evidence"]),
            ],
            fmt["text"],
        )
        sheet.write_number(row_number - 1, 4, _number(part["amount"]), fmt["input"])
    end = max(61, len(contributions) + 60)
    sheet.write_string("B6", "Dati e decisioni registrate", fmt["header"])
    for row, label in enumerate(
        (
            "Credito precedente disponibile",
            "Piccolo debito precedente",
            "Credito sottratto al riporto",
            "Credito annuale",
            "Versamenti auto UE",
            "Crediti d'imposta",
            "Acconto",
            "Rinvio piccolo debito (1/0)",
            "Interesse trimestrale",
            "Fonte rettifiche / versamenti",
        ),
        7,
    ):
        sheet.write_string(row - 1, 1, label, fmt["text"])
    sheet.set_column("B:B", 34)
    sheet.set_column("C:E", 24)
    sheet.set_column("F:G", 32)
    sheet.write_string("B18", "Ricalcolo con formule", fmt["header"])
    sheet.write_column("B19", LABELS, fmt["text"])
    sheet.write_string("B34", "Debito rinviato", fmt["text"])
    sheet.write_string("B36", "Scarto assoluto dal motore", fmt["text"])
    sheet.write_string("B38", "Risultato del motore (confronto)", fmt["header"])
    sheet.write_column("B39", LABELS, fmt["text"])
    for offset, module in enumerate(result["modules"], 2):
        col, prev = xl_col_to_name(offset), xl_col_to_name(offset - 1)
        inputs = case["modules"][offset - 2]
        rows = module["rows"]
        q4 = case["regime"] == "QUARTERLY_OPTION" and module["period"] == 4
        interest = 0.01 if case["regime"] == "QUARTERLY_OPTION" and not q4 else 0
        sheet.write_number(f"{col}6", module["period"], fmt["header"])
        sheet.write_number(f"{col}18", module["period"], fmt["header"])
        if offset == 2:
            for row, key in ((7, "credit"), (8, "small_debit")):
                sheet.write_number(
                    f"{col}{row}", _number(case["opening"][key]), fmt["input"]
                )
        else:
            previous = result["modules"][offset - 3]["rows"]
            sheet.write_formula(
                f"{col}7", f"={prev}33", fmt["money"], _number(previous["vp14_credit"])
            )
            sheet.write_formula(
                f"{col}8", f"={prev}34", fmt["money"], _number(rows["vp7"])
            )
        for row, key in (
            (9, "credit_withheld"),
            (10, "vp9"),
            (11, "vp10"),
            (12, "vp11"),
            (13, "vp13"),
        ):
            sheet.write_number(f"{col}{row}", _number(inputs[key]), fmt["input"])
        sheet.write_number(
            f"{col}14", int(bool(inputs["defer_small_debit"])), fmt["text"]
        )
        sheet.write_number(f"{col}15", interest, fmt["percent"])
        sheet.write_string(f"{col}16", _source(inputs["evidence"]), fmt["note"])
        sheet.write_string(
            f"{col}17",
            (
                "Apertura: " + _source(case["opening"]["evidence"])
                if offset == 2
                else "Riporto dal periodo precedente"
            ),
            fmt["note"],
        )
        formulas = [
            f'=ROUND(SUMIFS($E$61:$E${end},$B$61:$B${end},{col}$6,$D$61:$D${end},"{key}"),2)'
            for key in FIELDS[:4]
        ]
        formulas += [
            f"=MAX(ROUND({col}21-{col}22,2),0)",
            f"=MAX(ROUND({col}22-{col}21,2),0)",
            f"={col}8",
            f"=ROUND({col}7-{col}9,2)",
            f"={col}10",
            f"={col}11",
            f"={col}12",
            f"=ROUND(MAX({col}23-{col}24+{col}25-{col}26-{col}27-{col}28-{col}29,0)*{col}15,2)",
            f"={col}13",
            f"=MAX(ROUND({col}23-{col}24+{col}25-{col}26-{col}27-{col}28-{col}29+{col}30-{col}31,2),0)",
            f"=MAX(ROUND(-({col}23-{col}24+{col}25-{col}26-{col}27-{col}28-{col}29+{col}30-{col}31),2),0)",
        ]
        check_terms = []
        for row, (field, formula) in enumerate(zip(FIELDS, formulas), 19):
            value = _number(rows[field])
            if value is not None:
                sheet.write_formula(f"{col}{row}", formula, fmt["money"], value)
                sheet.write_number(f"{col}{row + 20}", value, fmt["input"])
                check_terms.append(f"ABS({col}{row}-{col}{row + 20})")
        if not q4:
            sheet.write_formula(
                f"{col}34",
                f"=IF({col}14=1,{col}32,0)",
                fmt["money"],
                _number(rows["vp14_debit"]) if inputs["defer_small_debit"] else 0,
            )
        sheet.write_formula(
            f"{col}36", "=ROUND(" + "+".join(check_terms) + ",2)", fmt["money"], 0
        )
        sheet.conditional_format(
            f"{col}36",
            {"type": "cell", "criteria": "!=", "value": 0, "format": fmt["warning"]},
        )
    sheet.write_string(
        "B56",
        "Le formule ricostruiscono i valori dalle attribuzioni confermate; non classificano le operazioni.",
        fmt["note"],
    )
    sheet.write_string(
        "B57",
        "Q4 per opzione: VP11, VP12 e VP14 non compilabili. Il vuoto è intenzionale.",
        fmt["note"],
    )
    sheet.write_string(
        "B58",
        "Composizione per codice e riga · fonti e conferme complete in case.json e result.json",
        fmt["note"],
    )
    sheet.freeze_panes(6, 2)
    sheet.print_area(f"B2:G{end}")


def _payments(sheet: Any, case: dict, result: dict, fmt: dict) -> None:
    sheet.write_row(
        "B7",
        [
            "Periodo",
            "VP14 dovuto",
            "Capitale F24",
            "Rinvio (1/0)",
            "F24 meno dovuto",
            "Esito",
            "Fonte",
        ],
        fmt["header"],
    )
    sheet.set_row(6, 32)
    sheet.set_column("B:B", 10)
    sheet.set_column("G:H", 35)
    labels = {
        "MATCH": "Coincide",
        "NOT_VERIFIED": "Versamento non verificato",
        "DEFERRED": "Debito rinviato",
        "DIFFERENCE_TO_REVIEW": "Scarto da esaminare",
        "NOT_COMPARABLE_ANNUAL_SETTLEMENT": "Liquidazione annuale: non confrontabile",
    }
    for row, module in enumerate(result["modules"], 8):
        inputs = case["modules"][row - 8]
        col = xl_col_to_name(row - 6)
        paid, due = _number(inputs["principal_paid"]), _number(
            module["rows"]["vp14_debit"]
        )
        sheet.write_number(f"B{row}", module["period"], fmt["text"])
        sheet.write_formula(
            f"C{row}",
            f'=IF(COUNT(VP!{col}32)=1,VP!{col}32,"")',
            fmt["money"],
            due if due is not None else "",
        )
        sheet.write(f"D{row}", paid, fmt["input"])
        sheet.write_formula(
            f"E{row}",
            f"=VP!{col}14",
            fmt["text"],
            int(bool(inputs["defer_small_debit"])),
        )
        difference = (
            float(money(inputs["principal_paid"]) - money(module["rows"]["vp14_debit"]))
            if paid is not None and due is not None
            else ""
        )
        sheet.write_formula(
            f"F{row}",
            f'=IF(COUNT(C{row}:D{row})=2,ROUND(D{row}-C{row},2),"")',
            fmt["money"],
            difference,
        )
        sheet.write_formula(
            f"G{row}",
            f'=IF(COUNT(D{row})=0,"Versamento non verificato",IF(COUNT(C{row})=0,"Liquidazione annuale: non confrontabile",IF(E{row}=1,"Debito rinviato",IF(F{row}=0,"Coincide","Scarto da esaminare"))))',
            fmt["text"],
            labels[module["payment_status"]],
        )
        sheet.write_string(f"H{row}", _source(inputs["evidence"]), fmt["note"])
    sheet.write_string(
        "B13",
        "Confronto del solo capitale IVA documentato. Sanzioni, interessi F24, termini e rimedi richiedono revisione.",
        fmt["note"],
    )
    sheet.write_string(
        "B14",
        "Un versamento mancante non è uno zero. Il VP14 non viene sostituito dall'importo pagato.",
        fmt["note"],
    )
    sheet.conditional_format(
        "F8:F10",
        {"type": "cell", "criteria": "!=", "value": 0, "format": fmt["warning"]},
    )
    sheet.print_area("B2:H14")


def write_workbook(case: dict, result: dict, path: Path) -> None:
    """Write a draft with source references; blocked inputs have no plausible VP."""
    with path.open("xb") as stream:
        path.chmod(0o600)
        with xlsxwriter.Workbook(
            stream, {"strings_to_formulas": False, "strings_to_urls": False}
        ) as book:
            book.set_properties(
                {
                    "title": "LIPE · bozza per revisione",
                    "comments": "Result SHA256: " + result["result_hash"],
                }
            )
            fmt = _formats(book)
            sheets = [
                _sheet(book, name, title, case, result, fmt)
                for name, title in (
                    ("Riconciliazione", "Registri e liquidazioni"),
                    ("VP", "Ricalcolo dei righi VP"),
                    ("F24", "Confronto dei versamenti"),
                )
            ]
            if result["status"] != "DRAFT_FOR_REVIEW":
                for sheet in sheets:
                    sheet.write_string(
                        "B7",
                        "CALCOLO BLOCCATO · dati o conferme mancanti",
                        fmt["warning"],
                    )
                    for row, blocker in enumerate(result["blockers"], 9):
                        sheet.write_string(row - 1, 1, blocker, fmt["text"])
                return
            _reconciliation(sheets[0], result, fmt)
            _vp(sheets[1], case, result, fmt)
            _payments(sheets[2], case, result, fmt)
