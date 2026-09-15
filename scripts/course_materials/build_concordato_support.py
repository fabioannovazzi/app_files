"""Render the fictional management source pack; never generate review answers."""

from __future__ import annotations

import argparse
import json
import tempfile
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

__all__ = ["build"]

ROOT = Path(__file__).resolve().parent
INK = colors.HexColor("#243441")
PALE = colors.HexColor("#edf1f3")
BODY = ParagraphStyle(
    "Body", fontName="Helvetica", fontSize=10, leading=14, textColor=INK, spaceAfter=9
)
TITLE = ParagraphStyle(
    "Title",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=19,
    leading=23,
    spaceAfter=10,
)
HEADING = ParagraphStyle(
    "Heading",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=12,
    leading=16,
    spaceBefore=12,
    spaceAfter=8,
)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=9, leading=12)


def _paragraph(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(escape(text, quote=False), style)


def _amount(value: int, language: str) -> str:
    separator = {"en": ",", "fr": " ", "it": ".", "de": ".", "es": "."}[language]
    return f"{value:,}".replace(",", separator)


def _table(rows: list[list[str]], widths: list[int]) -> Table:
    table = Table(
        [[_paragraph(cell, SMALL) for cell in row] for row in rows], colWidths=widths
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#d6dfe4")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def build(target: Path | None = None) -> None:
    """Create two-page source documents for both phases in each language."""
    texts = json.loads((ROOT / "concordato_support.json").read_text())
    target = target or ROOT / "inputs/concordato"
    target.mkdir(parents=True, exist_ok=True)
    for language, t in texts.items():
        for phase in ("demo", "practice"):
            funding = 50000 if phase == "demo" else 30000
            closing = [5000, 30000 + funding, 55000 + funding, funding - 50000]
            path = target / f"management-{phase}-{language}.pdf"
            document = SimpleDocTemplate(
                str(path),
                pagesize=A4,
                leftMargin=48,
                rightMargin=48,
                topMargin=42,
                bottomMargin=40,
                title=t["title"],
                author="Fictional teaching case",
                invariant=1,
            )
            supplier_rows = [t["creditor_headers"]] + [
                [
                    f"{name}\n{refs}",
                    _amount(claim, language),
                    _amount(payment, language),
                ]
                for name, refs, claim, payment in [
                    ("Alba Componenti", "AC-118 / AC-127", 100000, 65000),
                    ("Borea Materiali", "BM-044 / BM-052", 60000, 39000),
                    ("Cima Trasporti", "CT-071 / CT-079", 40000, 26000),
                ]
            ]
            liquidation_rows = [[t["liquidation"], "EUR"]] + [
                [label, _amount(amount, language)]
                for label, amount in zip(
                    t["liquidation_labels"],
                    [80000, 30000, 20000, -40000, 90000],
                    strict=True,
                )
            ]
            movements = [
                [0, *closing[:3]],
                [75000] * 4,
                [50000] * 4,
                [0, funding, 0, 0],
                [20000, 0, 0, 0],
                [0, 0, 0, 130000],
                closing,
            ]
            cash_rows = [t["cash_headers"]] + [
                [label, *[_amount(value, language) for value in values]]
                for label, values in zip(t["cash_labels"], movements, strict=True)
            ]
            story = [
                _paragraph(t["title"], TITLE),
                _paragraph(t["subtitle"], SMALL),
                _paragraph(t["fiction"], SMALL),
                _paragraph(t["creditors"], HEADING),
                _paragraph(t["creditor_intro"]),
                _table(supplier_rows, [279, 90, 130]),
                Spacer(1, 9),
                _paragraph(t["creditor_footer"], SMALL),
                _paragraph(t["liquidation"], HEADING),
                _paragraph(t["liquidation_intro"]),
                _table(liquidation_rows, [369, 130]),
                Spacer(1, 9),
                _paragraph(t["liquidation_footer"], SMALL),
                PageBreak(),
                _paragraph(t["cash"], TITLE),
                _paragraph(t["subtitle"], SMALL),
                _paragraph(t["operations"]),
                _table(cash_rows, [199, 75, 75, 75, 75]),
                Spacer(1, 12),
                _paragraph(t[f"funding_{phase}"]),
                _paragraph(t["perimeter"], HEADING),
                _paragraph(t["perimeter_text"]),
                _paragraph(t["fiction"], SMALL),
            ]

            def footer(canvas, doc, page_label=t["page"]):
                canvas.setFont("Helvetica", 8)
                canvas.setFillColor(INK)
                canvas.drawString(48, 22, "Officina Riva | EUR | 14.09.2026")
                canvas.drawRightString(A4[0] - 48, 22, f"{page_label} {doc.page} / 2")

            document.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed source PDFs without changing them",
    )
    options = parser.parse_args()
    if options.check:
        with tempfile.TemporaryDirectory(prefix="concordato-source-check-") as scratch:
            generated = Path(scratch)
            build(generated)
            for expected in generated.glob("*.pdf"):
                committed = ROOT / "inputs/concordato" / expected.name
                if (
                    not committed.is_file()
                    or committed.read_bytes() != expected.read_bytes()
                ):
                    raise SystemExit(
                        f"Stale fictional source PDF: {expected.name}; run build_concordato_support.py"
                    )
    else:
        build()
