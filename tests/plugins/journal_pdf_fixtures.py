"""Invented ruled journals with independently specified posting totals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.pdfgen import canvas

__all__ = ["write_grid_pdf", "grid_layout", "write_negative_grid_pdf"]
POSITIONS = [20, 96.8, 173.6, 404, 485.6, 567.2]


def write_negative_grid_pdf(
    path: Path,
    *,
    amount: str = "25,88-",
    total: str = "74,12",
    pages: int = 1,
    counterpart: str | None = None,
    same_side: bool = False,
) -> dict[str, Any]:
    """Print explicit reversals and independent source controls; no derived oracle."""
    pdf = canvas.Canvas(str(path), pagesize=(600, 800))
    for number in range(1, pages + 1):
        pdf.setFont("Courier", 8)
        pdf.drawString(20, 750, f"+----+ {number} ---- 01/01/2023 ----+----+")
        for y in (720, 700):
            for x in POSITIONS:
                pdf.drawString(x, y, "!")
        pdf.drawString(24.8, 720, "1.01.001")
        pdf.drawString(178.4, 720, "OPS! SRLS")
        pdf.drawRightString(480, 720, amount)
        pdf.drawString(24.8 if same_side else 101.6, 700, "2.01.001")
        pdf.drawString(178.4, 700, "ACEA ATO 2 S.P.A.")
        pdf.drawRightString(480 if same_side else 562, 700, counterpart or amount)
        pdf.drawString(178.4, 680, "TOTALI PROGRESSIVI")
        pdf.drawRightString(480, 680, total)
        pdf.drawRightString(562, 680, total)
        pdf.showPage()
    pdf.save()
    layout = grid_layout()
    layout["running_totals"].update(opening_debit="100", opening_credit="100")
    return layout


def grid_layout() -> dict[str, Any]:
    return {
        "body": ["20", "770"],
        "columns": {
            "account_debit": ["20", "98"],
            "account_credit": ["98", "174"],
            "description": ["174", "404"],
            "debit": ["404", "486"],
            "credit": ["486", "580"],
        },
        "ignored_line_prefixes": ["+-"],
        "rule_characters": {
            "text": "!",
            "x0": [str(v) for v in POSITIONS],
            "tolerance": "0.5",
        },
        "border_art": {"characters": "+-"},
        "running_totals": {
            "labels": ["TOTALI PROGRESSIVI"],
            "opening_debit": "0",
            "opening_credit": "0",
            "required_each_page": True,
        },
    }


def write_grid_pdf(
    path: Path,
    *,
    pages: int = 2,
    issue: str | None = None,
) -> dict[str, Any]:
    """Each page contributes a 32.94 registration; the first two share another 100."""
    pdf = canvas.Canvas(str(path), pagesize=(600, 800))

    def line(
        y: float,
        debit_account: str = "",
        credit_account: str = "",
        description: str = "",
        debit: str = "",
        credit: str = "",
        shift: float = 0,
    ) -> None:
        for x in POSITIONS:
            pdf.drawString(x + shift, y, "!")
        pdf.drawString(24.8 + shift, y, debit_account)
        pdf.drawString(101.6 + shift, y, credit_account)
        pdf.drawString(178.4 + shift, y, description)
        pdf.drawRightString(480 + shift, y, debit)
        pdf.drawRightString(562 + shift, y, credit)

    def money(cents: int) -> str:
        return f"{cents // 100:,}.{cents % 100:02}".translate(str.maketrans(",.", ".,"))

    running_debit = running_credit = 0
    for index in range(pages):
        pdf.setFont("Courier", 8)
        shift = 3 if issue == "shift" and index == pages - 1 else 0
        if pages > 1 and index == 0:
            pdf.drawString(20, 750, "+----+----+ 1 ---- 01/01/2024 ----+----+")
            line(
                730,
                "2.04.001 ABCDEF",
                description="Opening posting",
                debit="100,00",
                shift=shift,
            )
            running_debit += 10000
        elif index == 1 or issue == "orphan":
            date = "02/01/2024" if issue == "continuation_date" else "01/01/2024"
            if issue != "missing_continuation":
                pdf.drawString(
                    20, 750, f"+----+----+ seguito registrazione del {date} ----+----+"
                )
            line(
                730,
                credit_account="1.01.001",
                description="Continued posting",
                credit="100,00",
                shift=shift,
            )
            running_credit += 10000
        if not (pages > 1 and index == 0):
            number = index + 2
            trailing = " unexpected" if issue == "malformed_header" else ""
            pdf.drawString(
                20, 690, f"+----+----+ {number} ---- 01/01/2024 ----+----+{trailing}"
            )
            line(
                670,
                "2.04.001 ABCDEF",
                description="Example! punctuation",
                debit="32,94",
                shift=shift,
            )
            line(650, description="Invoice continuation", shift=shift)
            line(
                630,
                credit_account="9.01.001",
                description="Revenue",
                credit="27,00",
                shift=shift,
            )
            credit = "5,93" if issue == "unbalanced" else "5,94"
            line(
                610,
                credit_account="2.16.002",
                description="VAT",
                credit=credit,
                shift=shift,
            )
            running_debit += 3294
            running_credit += 3293 if issue == "unbalanced" else 3294
        if issue == "unassigned_money":
            pdf.drawString(580, 590, "9,00")
        pdf.drawString(178.4, 560, "T O T A L I P R O G R E S S I V I")
        pdf.drawRightString(
            480, 560, money(running_debit + (100 if issue == "wrong_total" else 0))
        )
        pdf.drawRightString(562, 560, money(running_credit))
        pdf.showPage()
    pdf.save()
    return grid_layout()
