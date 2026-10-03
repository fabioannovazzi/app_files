"""Create a paginated LIPE review summary from the saved case and result only."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import reportlab
from lipe_core import money
from lipe_review_outputs import RESOLUTIONS, STATES
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

__all__ = ["write_pdf"]

NAVY = colors.HexColor("#123A5C")
GREY = colors.HexColor("#535D66")
ROW_LABELS = {
    "vp2": "VP2 - Operazioni attive",
    "vp3": "VP3 - Operazioni passive",
    "vp4": "VP4 - IVA esigibile",
    "vp5": "VP5 - IVA detratta",
    "vp6_debit": "VP6 - Debito",
    "vp6_credit": "VP6 - Credito",
    "vp7": "VP7 - Debito precedente",
    "vp8": "VP8 - Credito precedente",
    "vp9": "VP9 - Credito annuale",
    "vp10": "VP10 - Auto UE",
    "vp11": "VP11 - Crediti d'imposta",
    "vp12": "VP12 - Interessi",
    "vp13": "VP13 - Acconto",
    "vp14_debit": "VP14 - Da versare",
    "vp14_credit": "VP14 - A credito",
}


def _euros(value: str | None, missing: str = "non disponibile") -> str:
    return (
        missing
        if value is None
        else f"{money(value):,.2f}".translate(str.maketrans(",.", ".,")) + " EUR"
    )


def _source(ref: dict) -> str:
    return f"{ref['source_id']}, p. {ref['page']}"


def write_pdf(case: dict, result: dict, path: Path) -> None:
    """Write an exclusive, private PDF; no network, HTML or executable links."""
    font_root = Path(reportlab.__file__).resolve().parent / "fonts"
    for name, filename in (("LipeVera", "Vera.ttf"), ("LipeVeraBold", "VeraBd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_root / filename)))
    supported = pdfmetrics.getFont("LipeVera").face.charToGlyph
    styles = {
        "body": ParagraphStyle(
            "body", fontName="LipeVera", fontSize=9, leading=13, spaceAfter=7
        ),
        "title": ParagraphStyle(
            "title",
            fontName="LipeVeraBold",
            fontSize=22,
            leading=27,
            textColor=NAVY,
            spaceAfter=14,
        ),
        "heading": ParagraphStyle(
            "heading",
            fontName="LipeVeraBold",
            fontSize=13,
            leading=18,
            textColor=NAVY,
            spaceBefore=13,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "small": ParagraphStyle(
            "small",
            fontName="LipeVera",
            fontSize=7.5,
            leading=10,
            textColor=GREY,
            spaceAfter=6,
        ),
        "number": ParagraphStyle(
            "number", fontName="LipeVera", fontSize=8, leading=11, alignment=TA_RIGHT
        ),
        "table": ParagraphStyle("table", fontName="LipeVera", fontSize=8, leading=11),
    }
    story = []
    replaced: set[str] = set()

    def para(value: object, style: str = "body") -> Paragraph:
        text = " ".join(str(value).split())
        text = text.translate({ord(char): "-" for char in "–—‑"})
        for char in set(text):
            if ord(char) not in supported:
                replaced.add(char)
                text = text.replace(char, f"[U+{ord(char):04X}]")
        return Paragraph(escape(text), styles[style])

    def add(value: object, style: str = "body") -> None:
        story.append(para(value, style))

    def table(rows: list[list[object]], widths: list[float]) -> None:
        cells = [
            [
                para(value, "number" if row and col else "table")
                for col, value in enumerate(values)
            ]
            for row, values in enumerate(rows)
        ]
        grid = LongTable(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        grid.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F5")),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, NAVY),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#D8DEE4")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.extend([grid, Spacer(1, 8)])

    add("LIPE", "title")
    client = (
        case["correspondence"]["client_label"]
        if case["correspondence"]
        else case["client_id"]
    )
    add(f"{client} | {case['tax_year']} | Trimestre {case['quarter']}")
    add("Sintesi per revisione - nessuna autorizzazione alla trasmissione")
    if case["data_origin"] == "SYNTHETIC":
        add("DATI SINTETICI - nessun cliente o giudizio professionale reale.")
    add(
        "Esito: "
        + (
            "bozza da rivedere"
            if result["status"] == "DRAFT_FOR_REVIEW"
            else "calcolo bloccato"
        )
    )
    add(f"Risultato: {result['result_hash']}", "small")
    add(f"Input: {result['input_hash']}", "small")
    add(
        "Gli importi derivano dai registri e dalle attribuzioni dichiarate nel fascicolo. Le conferme sono attribuite al revisore indicato, senza autenticarne l'identità. Questa sintesi non certifica la correttezza fiscale."
    )

    add("Righi VP", "heading")
    if result["modules"]:
        modules = result["modules"]
        rows = [["Importi in euro", *[f"Periodo {m['period']}" for m in modules]]]
        rows += [
            [label, *[_euros(m["rows"][key], "non compilato") for m in modules]]
            for key, label in ROW_LABELS.items()
        ]
        table(rows, [205, *([306 / len(modules)] * len(modules))])
        add(
            "I righi non compilabili restano distinti dallo zero. Formule e composizione per riga/codice sono in workpaper.xlsx e result.json.",
            "small",
        )
        for module in modules:
            refs = [
                item["evidence"]
                for item in result["composition"]
                if any(
                    part["period"] == module["period"] for part in item["contributions"]
                )
            ] + [module["evidence"], case["opening"]["evidence"]]
            add(
                f"Periodo {module['period']} - fonti: "
                + "; ".join(dict.fromkeys(_source(ref) for ref in refs)),
                "small",
            )
        add("Versamenti", "heading")
        payments = {
            module["period"]: module["principal_paid"] for module in case["modules"]
        }
        payment_rows = []
        for module in modules:
            due, paid = module["rows"]["vp14_debit"], payments[module["period"]]
            difference = (
                None
                if due is None or paid is None
                else f"{money(due) - money(paid):.2f}"
            )
            payment_rows.append(
                [
                    module["period"],
                    _euros(due, "non compilato"),
                    _euros(paid),
                    _euros(difference, "non calcolabile"),
                ]
            )
        table(
            [["Periodo", "VP14 dovuto", "Capitale F24", "Scarto dovuto - F24"]]
            + payment_rows,
            [55, 152, 152, 152],
        )
        for module in modules:
            payment_label = {
                "NOT_VERIFIED": "versamento non verificato",
                "NOT_COMPARABLE_ANNUAL_SETTLEMENT": "non confrontabile con liquidazione annuale",
                "DEFERRED": "debito riportato al periodo successivo",
                "MATCH": "importi dichiarati coincidenti",
                "DIFFERENCE_TO_REVIEW": "scarto da esaminare",
            }[module["payment_status"]]
            add(
                f"Periodo {module['period']} - {payment_label}; fonte versamento: {_source(module['evidence'])}.",
                "small",
            )
        add(
            "Il confronto non prova da solo omissione o ritardo. Il capitale F24 dichiarato esclude sanzioni e interessi da ravvedimento. Debiti differiti e liquidazione annuale vanno letti nel dettaglio del fascicolo."
        )
    else:
        add(
            "Non sono esposti righi da inserire: risolvere i blocchi e produrre una nuova revisione."
        )
    for blocker in result["blockers"]:
        add(blocker, "small")

    add("Riconciliazione per codice", "heading")
    for item in result["reconciliation"]:
        side = {
            "SALES": "vendite",
            "PURCHASES": "acquisti",
            "INTEGRATION": "integrazioni",
        }[item["side"]]
        add(f"Periodo {item['period']} | {side} | codice {item['code']}")
        add(
            f"Base registro {_euros(item['register_base'])}; liquidazione {_euros(item['liquidation_base'])}; scarto {_euros(item['base_difference'])}. IVA registro {_euros(item['register_tax'])}; liquidazione {_euros(item['liquidation_tax'])}; scarto {_euros(item['tax_difference'])}."
        )
        refs = item["register_evidence"] + (
            [item["liquidation_evidence"]] if item["liquidation_evidence"] else []
        )
        add(
            f"Criteri: {item['base_basis']} / {item['tax_basis']}. Fonti: "
            + "; ".join(dict.fromkeys(_source(ref) for ref in refs)),
            "small",
        )
        if item["explanations"]:
            for explanation in item["explanations"]:
                add(
                    f"{explanation['observation_id']}: {explanation['assessment']} ({STATES[explanation['state']]})."
                )
        elif item["status"] != "MATCH":
            add(
                "Causa da chiarire sulle fonti; nessuna causa fiscale è desunta dallo scarto."
            )

    add("Osservazioni e decisioni", "heading")
    if not result["observations"]:
        add(
            "Nessuna anomalia semantica registrata. Questo non prova l'assenza di errori."
        )
    for item in result["observations"]:
        add(
            f"{item['observation_id']} | {item['category']} | {item['title']}",
            "heading",
        )
        add(
            f"Stato: {STATES[item['state']]}. Valutazione proposta: {item['assessment']}"
        )
        for document in item["documents"]:
            formatted = dict(document)
            if document["date"]:
                formatted["date"] = date.fromisoformat(document["date"]).strftime(
                    "%d/%m/%Y"
                )
            fields = "; ".join(
                f"{label}: {formatted[key] or 'non disponibile'}"
                for key, label in (
                    ("protocol", "Protocollo"),
                    ("invoice_number", "Fattura"),
                    ("date", "Data"),
                    ("counterparty", "Controparte"),
                )
            )
            add(
                f"{fields}; importo {_euros(document['amount'])} ({document['amount_basis'] or 'base non determinata'}). Fonte: {_source(document['evidence'])}."
            )
        for effect in item["vp6_effect"]:
            add(
                f"Effetto proposto su VP6, periodo {effect['period']}: {_euros(effect['amount'], 'non determinato')}. {effect['basis'].rstrip('.')}. Non applicato automaticamente."
            )
        add(f"Azione proposta: {item['proposed_action']}")
        add(
            "Fonti: "
            + "; ".join(dict.fromkeys(_source(ref) for ref in item["evidence"])),
            "small",
        )
        if item["decision"]:
            decision = item["decision"]
            add(
                f"Decisione dichiarata: {RESOLUTIONS[decision['resolution']]}. Revisore: {decision['review']['reviewer']}; data: {decision['review']['reviewed_on']}. {decision['review']['reason']}"
            )

    add("Documenti e limiti della revisione", "heading")
    for source in case["sources"]:
        add(f"{source['source_id']}: {source['path']}")
        add(f"SHA-256: {source['sha256']}", "small")
    add(
        "Le citazioni puntuali, le righe di origine e le decisioni complete sono conservate in case.json, result.json e anomalies.json. La bozza review-request.md non è stata inviata. Una modifica agli input richiede un nuovo calcolo e la revisione delle decisioni non più riferite ai dati correnti."
    )
    add("Quali dati arrivano al modello", "heading")
    add(
        "Il modello dell'host può leggere documenti, identificativi, importi e decisioni per l'analisi. Questo generatore PDF non effettua chiamate di rete o a modelli. Il report della sessione deve descrivere l'esposizione effettiva, che il generatore locale non può misurare."
    )
    if replaced:
        add(
            "Caratteri non disponibili nel font sono indicati con il codice Unicode [U+XXXX]; il testo originale resta nei file JSON.",
            "small",
        )

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("LipeVera", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(42, 28, f"LIPE | bozza | {result['result_hash'][:16]}")
        canvas.drawRightString(A4[0] - 42, 28, f"Pagina {doc.page}")
        canvas.restoreState()

    with path.open("xb") as stream:
        path.chmod(0o600)
        document = SimpleDocTemplate(
            stream,
            pagesize=A4,
            leftMargin=42,
            rightMargin=42,
            topMargin=40,
            bottomMargin=44,
            title="LIPE - sintesi per revisione",
            author="LIPE",
        )
        document.build(story, onFirstPage=footer, onLaterPages=footer)
