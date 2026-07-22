from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from extract_documents import DocumentEvidence  # noqa: E402

__all__ = [
    "FiscalField",
    "SUMMARY_COPY",
    "localize_field_label",
    "localize_warning",
    "parse_structured_fiscal_fields",
    "write_fiscal_fields_csv",
    "write_fiscal_fields_jsonl",
    "write_fiscal_fields_summary",
]

LOGGER = logging.getLogger(__name__)

CURRENCY_PREFIX = r"(?:€|£|CHF|GBP)\s*"
AMOUNT_PATTERN = (
    rf"(?:{CURRENCY_PREFIX})?-?(?:\d{{1,3}}(?:[.,]\d{{3}})+|\d+)(?:[.,]\d{{2}})?"
)
TAX_CODE_RE = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")
VAT_RE = re.compile(r"\b\d{11}\b")
YEAR_RE = re.compile(r"\b20[0-4]\d\b")
CH_AHV_RE = re.compile(r"\b756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}\b")
UK_NINO_RE = re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b")

SUPPORTED_LANGUAGES = ("it", "en", "fr", "de", "es")

SUMMARY_COPY = {
    "it": {
        "title": "Dati fiscali strutturati",
        "limitation": (
            "Questa sezione riporta campi estratti da testo leggibile. Ogni "
            "valore va verificato sul documento originale prima dell'uso operativo."
        ),
        "field_count": "Campi estratti",
        "document_type_count": "Tipologie documento",
        "empty": ("Nessun campo fiscale strutturato estratto dai documenti leggibili."),
        "additional_fields": "... altri {count} campi nel CSV.",
    },
    "en": {
        "title": "Structured fiscal data",
        "limitation": (
            "This section reports fields extracted from readable text. Verify every "
            "value against the original document before operational use."
        ),
        "field_count": "Extracted fields",
        "document_type_count": "Document types",
        "empty": (
            "No structured fiscal fields were extracted from the readable documents."
        ),
        "additional_fields": "... {count} more fields in the CSV.",
    },
    "fr": {
        "title": "Données fiscales structurées",
        "limitation": (
            "Cette section présente les champs extraits du texte lisible. Chaque "
            "valeur doit être vérifiée dans le document original avant toute "
            "utilisation opérationnelle."
        ),
        "field_count": "Champs extraits",
        "document_type_count": "Types de documents",
        "empty": (
            "Aucun champ fiscal structuré n’a été extrait des documents lisibles."
        ),
        "additional_fields": "... {count} champs supplémentaires dans le CSV.",
    },
    "de": {
        "title": "Strukturierte Steuerdaten",
        "limitation": (
            "Dieser Abschnitt enthält Felder, die aus lesbarem Text extrahiert "
            "wurden. Jeder Wert muss vor der operativen Verwendung anhand des "
            "Originaldokuments geprüft werden."
        ),
        "field_count": "Extrahierte Felder",
        "document_type_count": "Dokumentarten",
        "empty": (
            "Aus den lesbaren Dokumenten wurden keine strukturierten Steuerfelder "
            "extrahiert."
        ),
        "additional_fields": "... {count} weitere Felder in der CSV-Datei.",
    },
    "es": {
        "title": "Datos fiscales estructurados",
        "limitation": (
            "Esta sección presenta campos extraídos de texto legible. Cada valor "
            "debe verificarse en el documento original antes de su uso operativo."
        ),
        "field_count": "Campos extraídos",
        "document_type_count": "Tipos de documento",
        "empty": (
            "No se extrajeron campos fiscales estructurados de los documentos "
            "legibles."
        ),
        "additional_fields": "... {count} campos adicionales en el CSV.",
    },
}

FIELD_LABELS = {
    "it": {
        "Salaire brut / Bruttolohn": "Retribuzione lorda",
        "Salaire net / Nettolohn": "Retribuzione netta",
        "Revenu imposable / steuerbares Einkommen": "Reddito imponibile",
        "Fortune imposable / steuerbares Vermögen": "Patrimonio imponibile",
        "Impôt anticipé / Verrechnungssteuer": "Imposta preventiva",
        "Impôt cantonal / Kantonssteuer": "Imposta cantonale",
        "Impôt communal / Gemeindesteuer": "Imposta comunale",
        "Impôt fédéral direct / direkte Bundessteuer": "Imposta federale diretta",
        "National Insurance number": "Numero di National Insurance",
        "Unique Taxpayer Reference": "Riferimento unico del contribuente",
        "Total pay": "Retribuzione totale",
        "Tax deducted": "Imposta trattenuta",
        "National Insurance": "National Insurance",
        "Student loan": "Prestito studentesco",
        "Benefits": "Benefit",
        "Bank interest": "Interessi bancari",
        "Dividends": "Dividendi",
        "Amount due": "Importo dovuto",
        "Repayment due": "Rimborso dovuto",
    },
    "en": {
        "Codice fiscale individuato": "Tax code identified",
        "Partita IVA / codice numerico a 11 cifre": (
            "VAT number / 11-digit numeric code"
        ),
        "Anno individuato": "Year identified",
        "Codice tributo": "Tax payment code",
        "Anno riferimento": "Reference year",
        "Importo a debito versato": "Debit amount paid",
        "Importo a credito compensato": "Credit amount offset",
        "Importo a debito": "Debit amount",
        "Rateazione / mese": "Instalment / month",
        "Importo a credito": "Credit amount",
        "Redditi lavoro dipendente e assimilati": ("Employment and equivalent income"),
        "Redditi pensione": "Pension income",
        "Ritenute IRPEF": "IRPEF withholdings",
        "Addizionale regionale": "Regional surtax",
        "Addizionale comunale": "Municipal surtax",
        "Trattamento integrativo": "Supplementary treatment",
        "Giorni lavoro dipendente": "Days of employment",
        "Importo da trattenere": "Amount to withhold",
        "Importo da rimborsare": "Amount to refund",
        "Saldo e primo acconto": "Balance and first advance payment",
        "Secondo o unico acconto": "Second or single advance payment",
        "Reddito complessivo": "Total income",
        "Imposta lorda": "Gross tax",
        "Imposta netta": "Net tax",
        "Differenza": "Difference",
        "Numero AVS/AHV individuato": "AVS/AHV number identified",
        "Salaire brut / Bruttolohn": "Gross salary",
        "Salaire net / Nettolohn": "Net salary",
        "Revenu imposable / steuerbares Einkommen": "Taxable income",
        "Fortune imposable / steuerbares Vermögen": "Taxable wealth",
        "Impôt anticipé / Verrechnungssteuer": "Withholding tax",
        "Impôt cantonal / Kantonssteuer": "Cantonal tax",
        "Impôt communal / Gemeindesteuer": "Municipal tax",
        "Impôt fédéral direct / direkte Bundessteuer": "Direct federal tax",
    },
    "fr": {
        "Codice fiscale individuato": "Code fiscal identifié",
        "Partita IVA / codice numerico a 11 cifre": (
            "Numéro de TVA / code numérique à 11 chiffres"
        ),
        "Anno individuato": "Année identifiée",
        "Codice tributo": "Code fiscal de paiement",
        "Anno riferimento": "Année de référence",
        "Importo a debito versato": "Montant débiteur versé",
        "Importo a credito compensato": "Montant créditeur compensé",
        "Importo a debito": "Montant débiteur",
        "Rateazione / mese": "Échelonnement / mois",
        "Importo a credito": "Montant créditeur",
        "Redditi lavoro dipendente e assimilati": (
            "Revenus d’activité salariée et assimilés"
        ),
        "Redditi pensione": "Revenus de pension",
        "Ritenute IRPEF": "Retenues IRPEF",
        "Addizionale regionale": "Impôt régional additionnel",
        "Addizionale comunale": "Impôt communal additionnel",
        "Trattamento integrativo": "Traitement complémentaire",
        "Giorni lavoro dipendente": "Jours de travail salarié",
        "Importo da trattenere": "Montant à retenir",
        "Importo da rimborsare": "Montant à rembourser",
        "Saldo e primo acconto": "Solde et premier acompte",
        "Secondo o unico acconto": "Deuxième ou unique acompte",
        "Reddito complessivo": "Revenu total",
        "Imposta lorda": "Impôt brut",
        "Imposta netta": "Impôt net",
        "Differenza": "Différence",
        "Numero AVS/AHV individuato": "Numéro AVS/AHV identifié",
        "Salaire brut / Bruttolohn": "Salaire brut",
        "Salaire net / Nettolohn": "Salaire net",
        "Revenu imposable / steuerbares Einkommen": "Revenu imposable",
        "Fortune imposable / steuerbares Vermögen": "Fortune imposable",
        "Impôt anticipé / Verrechnungssteuer": "Impôt anticipé",
        "Impôt cantonal / Kantonssteuer": "Impôt cantonal",
        "Impôt communal / Gemeindesteuer": "Impôt communal",
        "Impôt fédéral direct / direkte Bundessteuer": "Impôt fédéral direct",
        "National Insurance number": "Numéro d’assurance nationale",
        "Unique Taxpayer Reference": "Référence fiscale unique",
        "Total pay": "Rémunération totale",
        "Tax deducted": "Impôt retenu",
        "National Insurance": "Assurance nationale",
        "Student loan": "Prêt étudiant",
        "Benefits": "Avantages",
        "Bank interest": "Intérêts bancaires",
        "Dividends": "Dividendes",
        "Amount due": "Montant dû",
        "Repayment due": "Remboursement dû",
    },
    "de": {
        "Codice fiscale individuato": "Ermittelte italienische Steuernummer",
        "Partita IVA / codice numerico a 11 cifre": (
            "Umsatzsteuer-ID / 11-stelliger Zahlencode"
        ),
        "Anno individuato": "Ermitteltes Jahr",
        "Codice tributo": "Steuerzahlungscode",
        "Anno riferimento": "Bezugsjahr",
        "Importo a debito versato": "Gezahlter Sollbetrag",
        "Importo a credito compensato": "Verrechneter Habenbetrag",
        "Importo a debito": "Sollbetrag",
        "Rateazione / mese": "Ratenzahlung / Monat",
        "Importo a credito": "Habenbetrag",
        "Redditi lavoro dipendente e assimilati": (
            "Einkünfte aus nichtselbstständiger Arbeit und gleichgestellte Einkünfte"
        ),
        "Redditi pensione": "Renteneinkünfte",
        "Ritenute IRPEF": "IRPEF-Abzüge",
        "Addizionale regionale": "Regionalzuschlag",
        "Addizionale comunale": "Kommunalzuschlag",
        "Trattamento integrativo": "Ergänzungsleistung",
        "Giorni lavoro dipendente": "Arbeitstage",
        "Importo da trattenere": "Einzubehaltender Betrag",
        "Importo da rimborsare": "Zu erstattender Betrag",
        "Saldo e primo acconto": "Saldo und erste Vorauszahlung",
        "Secondo o unico acconto": "Zweite oder einmalige Vorauszahlung",
        "Reddito complessivo": "Gesamteinkommen",
        "Imposta lorda": "Bruttosteuer",
        "Imposta netta": "Nettosteuer",
        "Differenza": "Differenz",
        "Numero AVS/AHV individuato": "Ermittelte AHV/AVS-Nummer",
        "Salaire brut / Bruttolohn": "Bruttolohn",
        "Salaire net / Nettolohn": "Nettolohn",
        "Revenu imposable / steuerbares Einkommen": "Steuerbares Einkommen",
        "Fortune imposable / steuerbares Vermögen": "Steuerbares Vermögen",
        "Impôt anticipé / Verrechnungssteuer": "Verrechnungssteuer",
        "Impôt cantonal / Kantonssteuer": "Kantonssteuer",
        "Impôt communal / Gemeindesteuer": "Gemeindesteuer",
        "Impôt fédéral direct / direkte Bundessteuer": "Direkte Bundessteuer",
        "National Insurance number": "National-Insurance-Nummer",
        "Unique Taxpayer Reference": "Einheitliche Steuerzahlerreferenz",
        "Total pay": "Gesamtlohn",
        "Tax deducted": "Einbehaltene Steuer",
        "National Insurance": "National Insurance",
        "Student loan": "Studiendarlehen",
        "Benefits": "Sachleistungen",
        "Bank interest": "Bankzinsen",
        "Dividends": "Dividenden",
        "Amount due": "Fälliger Betrag",
        "Repayment due": "Fällige Erstattung",
    },
    "es": {
        "Codice fiscale individuato": "Código fiscal identificado",
        "Partita IVA / codice numerico a 11 cifre": (
            "Número de IVA / código numérico de 11 dígitos"
        ),
        "Anno individuato": "Año identificado",
        "Codice tributo": "Código de pago tributario",
        "Anno riferimento": "Año de referencia",
        "Importo a debito versato": "Importe deudor pagado",
        "Importo a credito compensato": "Importe acreedor compensado",
        "Importo a debito": "Importe deudor",
        "Rateazione / mese": "Fraccionamiento / mes",
        "Importo a credito": "Importe acreedor",
        "Redditi lavoro dipendente e assimilati": (
            "Rendimientos del trabajo y asimilados"
        ),
        "Redditi pensione": "Rendimientos de pensiones",
        "Ritenute IRPEF": "Retenciones IRPEF",
        "Addizionale regionale": "Recargo regional",
        "Addizionale comunale": "Recargo municipal",
        "Trattamento integrativo": "Tratamiento complementario",
        "Giorni lavoro dipendente": "Días de trabajo por cuenta ajena",
        "Importo da trattenere": "Importe que se debe retener",
        "Importo da rimborsare": "Importe que se debe reembolsar",
        "Saldo e primo acconto": "Saldo y primer pago a cuenta",
        "Secondo o unico acconto": "Segundo o único pago a cuenta",
        "Reddito complessivo": "Renta total",
        "Imposta lorda": "Impuesto bruto",
        "Imposta netta": "Impuesto neto",
        "Differenza": "Diferencia",
        "Numero AVS/AHV individuato": "Número AVS/AHV identificado",
        "Salaire brut / Bruttolohn": "Salario bruto",
        "Salaire net / Nettolohn": "Salario neto",
        "Revenu imposable / steuerbares Einkommen": "Renta imponible",
        "Fortune imposable / steuerbares Vermögen": "Patrimonio imponible",
        "Impôt anticipé / Verrechnungssteuer": "Impuesto anticipado",
        "Impôt cantonal / Kantonssteuer": "Impuesto cantonal",
        "Impôt communal / Gemeindesteuer": "Impuesto municipal",
        "Impôt fédéral direct / direkte Bundessteuer": "Impuesto federal directo",
        "National Insurance number": "Número de National Insurance",
        "Unique Taxpayer Reference": "Referencia única del contribuyente",
        "Total pay": "Retribución total",
        "Tax deducted": "Impuesto retenido",
        "National Insurance": "National Insurance",
        "Student loan": "Préstamo estudiantil",
        "Benefits": "Prestaciones",
        "Bank interest": "Intereses bancarios",
        "Dividends": "Dividendos",
        "Amount due": "Importe debido",
        "Repayment due": "Reembolso debido",
    },
}

CONFIDENCE_LABELS = {
    "it": {"alta": "alta", "media": "media", "bassa": "bassa"},
    "en": {"alta": "high", "media": "medium", "bassa": "low"},
    "fr": {"alta": "élevée", "media": "moyenne", "bassa": "faible"},
    "de": {"alta": "hoch", "media": "mittel", "bassa": "niedrig"},
    "es": {"alta": "alta", "media": "media", "bassa": "baja"},
}

WARNING_LABELS = {
    "it": {
        "campo da verificare su layout originale": (
            "campo da verificare su layout originale"
        )
    },
    "en": {
        "campo da verificare su layout originale": (
            "field to verify against the original layout"
        )
    },
    "fr": {
        "campo da verificare su layout originale": (
            "champ à vérifier dans la mise en page originale"
        )
    },
    "de": {
        "campo da verificare su layout originale": (
            "Feld anhand des Originallayouts prüfen"
        )
    },
    "es": {
        "campo da verificare su layout originale": (
            "campo que debe verificarse en el diseño original"
        )
    },
}


@dataclass(frozen=True)
class FiscalField:
    """One structured fiscal field extracted from document text."""

    relative_path: str
    file_name: str
    document_kind: str
    section: str
    field_code: str
    label: str
    value: str
    normalized_value: str
    value_type: str
    confidence: str
    evidence: str
    warnings: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)

    def as_row(self) -> dict[str, str]:
        """Return a CSV-friendly representation."""

        return {
            "relative_path": self.relative_path,
            "file_name": self.file_name,
            "document_kind": self.document_kind,
            "section": self.section,
            "field_code": self.field_code,
            "label": self.label,
            "value": self.value,
            "normalized_value": self.normalized_value,
            "value_type": self.value_type,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "warnings": " | ".join(self.warnings),
        }


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\r", "\n")).strip()


def _normalize_amount(value: str) -> str:
    cleaned = re.sub(r"€|£|CHF|GBP", "", value, flags=re.IGNORECASE)
    cleaned = cleaned.replace(" ", "").strip()
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return str(Decimal(cleaned).quantize(Decimal("0.01")))
    except InvalidOperation:
        return value.strip()


def _snippet(text: str, start: int, end: int, radius: int = 80) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return _collapse(text[left:right])


def _field(
    evidence: DocumentEvidence,
    document_kind: str,
    section: str,
    field_code: str,
    label: str,
    value: str,
    value_type: str,
    source_text: str,
    match: re.Match[str] | None,
    confidence: str = "media",
    warnings: Sequence[str] = (),
) -> FiscalField:
    normalized = _normalize_amount(value) if value_type == "amount" else value.strip()
    context = (
        _snippet(source_text, match.start(), match.end())
        if match is not None
        else _collapse(value)
    )
    return FiscalField(
        relative_path=evidence.relative_path,
        file_name=evidence.file_name,
        document_kind=document_kind,
        section=section,
        field_code=field_code,
        label=label,
        value=value.strip(),
        normalized_value=normalized,
        value_type=value_type,
        confidence=confidence,
        evidence=context,
        warnings=tuple(warnings),
    )


def _detect_kind(evidence: DocumentEvidence, text: str) -> str:
    searchable = (
        f"{evidence.category} {evidence.file_name} {_collapse(text[:2000])}".lower()
    )
    if re.search(r"\bf24\b|codice\s+tributo|sezione\s+erario", searchable):
        return "F24"
    if re.search(r"certificazione\s+unica|\bcu\b|sostituto\s+d[' ]imposta", searchable):
        return "CU"
    if re.search(r"\b730\b|dichiarazione\s+precompilata|730-3", searchable):
        return "730"
    if re.search(
        r"redditi\s+persone\s+fisiche|redditi\s+pf|modello\s+redditi", searchable
    ):
        return "Redditi PF"
    if re.search(
        r"geneva tax documents|\bgeneva\b|\bgeneve\b|etat de geneve|afc geneve",
        searchable,
    ):
        return "Geneva tax documents"
    if re.search(
        r"zurich tax documents|\bzurich\b|\bzuerich\b|steueramt zurich|steueramt zuerich",
        searchable,
    ):
        return "Zurich tax documents"
    if re.search(
        r"ch salary certificate|certificat de salaire|certificato di salario|lohnausweis|salary certificate",
        searchable,
    ):
        return "CH salary certificate"
    if re.search(
        r"ch tax return|declaration fiscale|declaration d impot|steuererklarung|steuererklärung",
        searchable,
    ):
        return "CH tax return"
    if re.search(
        r"ch tax assessment|avis de taxation|bordereau|veranlagung|tax assessment",
        searchable,
    ):
        return "CH tax assessment"
    if re.search(
        r"uk p60|uk p45|uk p11d|\bp60\b|\bp45\b|\bp11d\b",
        searchable,
    ):
        return "UK year-end payroll"
    if re.search(r"uk payslip|\bpayslip\b|pay slip", searchable):
        return "UK payslip"
    if re.search(
        r"uk self assessment|self assessment|\bsa100\b|\bsa302\b|\butr\b",
        searchable,
    ):
        return "UK Self Assessment"
    if re.search(r"uk hmrc|hmrc|paye coding notice|tax code notice", searchable):
        return "UK HMRC notice"
    if re.search(
        r"uk bank|interest certificate|dividend voucher|consolidated tax voucher",
        searchable,
    ):
        return "UK bank/investment tax certificate"
    return "documento fiscale"


def _parse_common_fields(
    evidence: DocumentEvidence, kind: str, text: str
) -> list[FiscalField]:
    fields: list[FiscalField] = []
    for index, match in enumerate(TAX_CODE_RE.finditer(text), start=1):
        fields.append(
            _field(
                evidence,
                kind,
                "identificativi",
                f"codice_fiscale_{index}",
                "Codice fiscale individuato",
                match.group(0),
                "text",
                text,
                match,
                confidence="alta",
            )
        )
    for index, match in enumerate(VAT_RE.finditer(text), start=1):
        fields.append(
            _field(
                evidence,
                kind,
                "identificativi",
                f"partita_iva_o_codice_11_{index}",
                "Partita IVA / codice numerico a 11 cifre",
                match.group(0),
                "text",
                text,
                match,
            )
        )
    for index, match in enumerate(YEAR_RE.finditer(text), start=1):
        fields.append(
            _field(
                evidence,
                kind,
                "periodo",
                f"anno_{index}",
                "Anno individuato",
                match.group(0),
                "year",
                text,
                match,
            )
        )
    return fields


def _parse_labeled_amounts(
    evidence: DocumentEvidence,
    kind: str,
    text: str,
    section: str,
    specs: Sequence[tuple[str, str, str]],
    confidence: str = "media",
) -> list[FiscalField]:
    fields: list[FiscalField] = []
    for field_code, label, label_pattern in specs:
        pattern = re.compile(
            rf"(?:{label_pattern})\s*(?:[:\-]|\s)\s*(?P<amount>{AMOUNT_PATTERN})",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            fields.append(
                _field(
                    evidence,
                    kind,
                    section,
                    field_code,
                    label,
                    match.group("amount"),
                    "amount",
                    text,
                    match,
                    confidence=confidence,
                )
            )
    return fields


def _parse_f24(evidence: DocumentEvidence, text: str) -> list[FiscalField]:
    fields = _parse_common_fields(evidence, "F24", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    row_index = 1
    explicit_patterns = [
        (
            "codice_tributo",
            "Codice tributo",
            r"codice\s+tributo\s*[:\-]?\s*(\d{4})",
            "code",
        ),
        (
            "anno_riferimento",
            "Anno riferimento",
            r"anno\s+(?:di\s+)?riferimento\s*[:\-]?\s*(20[0-4]\d)",
            "year",
        ),
        (
            "importo_debito",
            "Importo a debito versato",
            rf"importo\s+a\s+debito\s+versato\s*[:\-]?\s*({AMOUNT_PATTERN})",
            "amount",
        ),
        (
            "importo_credito",
            "Importo a credito compensato",
            rf"importo\s+a\s+credito\s+compensato\s*[:\-]?\s*({AMOUNT_PATTERN})",
            "amount",
        ),
    ]
    for field_code, label, pattern, value_type in explicit_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            fields.append(
                _field(
                    evidence,
                    "F24",
                    "f24",
                    field_code,
                    label,
                    match.group(1),
                    value_type,
                    text,
                    match,
                    confidence="alta",
                )
            )

    row_re = re.compile(
        rf"\b(?P<code>\d{{4}})\b\s+(?:(?P<rate>\d{{2,4}})\s+)?"
        rf"(?P<year>20[0-4]\d)\s+(?P<debit>{AMOUNT_PATTERN})"
        rf"(?:\s+(?P<credit>{AMOUNT_PATTERN}))?",
        re.IGNORECASE,
    )
    for line in lines:
        for match in row_re.finditer(line):
            prefix = f"riga_{row_index}"
            fields.extend(
                [
                    _field(
                        evidence,
                        "F24",
                        "f24_righe",
                        f"{prefix}_codice_tributo",
                        "Codice tributo",
                        match.group("code"),
                        "code",
                        text,
                        match,
                    ),
                    _field(
                        evidence,
                        "F24",
                        "f24_righe",
                        f"{prefix}_anno_riferimento",
                        "Anno riferimento",
                        match.group("year"),
                        "year",
                        text,
                        match,
                    ),
                    _field(
                        evidence,
                        "F24",
                        "f24_righe",
                        f"{prefix}_importo_debito",
                        "Importo a debito",
                        match.group("debit"),
                        "amount",
                        text,
                        match,
                    ),
                ]
            )
            if match.group("rate"):
                fields.append(
                    _field(
                        evidence,
                        "F24",
                        "f24_righe",
                        f"{prefix}_rateazione",
                        "Rateazione / mese",
                        match.group("rate"),
                        "code",
                        text,
                        match,
                    )
                )
            if match.group("credit"):
                fields.append(
                    _field(
                        evidence,
                        "F24",
                        "f24_righe",
                        f"{prefix}_importo_credito",
                        "Importo a credito",
                        match.group("credit"),
                        "amount",
                        text,
                        match,
                    )
                )
            row_index += 1
    return fields


def _parse_cu(evidence: DocumentEvidence, text: str) -> list[FiscalField]:
    fields = _parse_common_fields(evidence, "CU", text)
    fields.extend(
        _parse_labeled_amounts(
            evidence,
            "CU",
            text,
            "cu_dati_fiscali",
            [
                (
                    "redditi_lavoro_dipendente",
                    "Redditi lavoro dipendente e assimilati",
                    r"(?:punto\s*1\s*)?redditi\s+lavoro\s+dipendente(?:\s+e\s+assimilati)?",
                ),
                (
                    "redditi_pensione",
                    "Redditi pensione",
                    r"(?:punto\s*3\s*)?redditi\s+di\s+pensione",
                ),
                (
                    "ritenute_irpef",
                    "Ritenute IRPEF",
                    r"(?:punto\s*21\s*)?ritenute\s+irpef",
                ),
                (
                    "addizionale_regionale",
                    "Addizionale regionale",
                    r"addizionale\s+regionale",
                ),
                (
                    "addizionale_comunale",
                    "Addizionale comunale",
                    r"addizionale\s+comunale",
                ),
                (
                    "trattamento_integrativo",
                    "Trattamento integrativo",
                    r"trattamento\s+integrativo",
                ),
            ],
            confidence="media",
        )
    )
    for match in re.finditer(
        rf"\bpunto\s*(?P<point>\d{{1,4}})\s*(?:[:\-]|\s)\s*(?P<value>{AMOUNT_PATTERN})",
        text,
        re.IGNORECASE,
    ):
        point = match.group("point")
        fields.append(
            _field(
                evidence,
                "CU",
                "cu_punti_numerici",
                f"punto_{point}",
                f"Punto CU {point}",
                match.group("value"),
                "amount",
                text,
                match,
            )
        )
    for match in re.finditer(
        r"giorni\s+(?:di\s+)?lavoro\s+dipendente\s*[:\-]?\s*(?P<days>\d{1,3})",
        text,
        re.IGNORECASE,
    ):
        fields.append(
            _field(
                evidence,
                "CU",
                "cu_dati_fiscali",
                "giorni_lavoro_dipendente",
                "Giorni lavoro dipendente",
                match.group("days"),
                "integer",
                text,
                match,
            )
        )
    return fields


def _parse_model_rows(
    evidence: DocumentEvidence,
    kind: str,
    text: str,
    prefixes: Sequence[str],
) -> list[FiscalField]:
    fields: list[FiscalField] = []
    prefix_pattern = "|".join(re.escape(prefix) for prefix in prefixes)
    row_re = re.compile(rf"\b(?P<row>(?:{prefix_pattern})\d{{1,3}})\b", re.IGNORECASE)
    for line in text.splitlines():
        row_matches = list(row_re.finditer(line))
        for position, match in enumerate(row_matches):
            row = match.group("row").upper()
            next_start = (
                row_matches[position + 1].start()
                if position + 1 < len(row_matches)
                else len(line)
            )
            body = line[match.end() : next_start]
            amounts = re.findall(AMOUNT_PATTERN, body)
            if not amounts:
                continue
            quadro_match = re.match(r"[A-Z]+", row)
            quadro = quadro_match.group(0) if quadro_match else row
            for index, amount in enumerate(amounts[:12], start=1):
                fields.append(
                    _field(
                        evidence,
                        kind,
                        f"quadro_{quadro}",
                        f"{row}_importo_{index}",
                        f"{row} importo {index}",
                        amount,
                        "amount",
                        line,
                        match,
                        confidence="media",
                        warnings=("campo da verificare su layout originale",),
                    )
                )
    return fields


def _parse_730(evidence: DocumentEvidence, text: str) -> list[FiscalField]:
    fields = _parse_common_fields(evidence, "730", text)
    fields.extend(
        _parse_labeled_amounts(
            evidence,
            "730",
            text,
            "730_liquidazione",
            [
                (
                    "importo_da_trattenere",
                    "Importo da trattenere",
                    r"importo\s+da\s+trattenere",
                ),
                (
                    "importo_da_rimborsare",
                    "Importo da rimborsare",
                    r"importo\s+da\s+rimborsare",
                ),
                (
                    "saldo_e_primo_acconto",
                    "Saldo e primo acconto",
                    r"saldo\s+e\s+primo\s+acconto",
                ),
                (
                    "secondo_o_unico_acconto",
                    "Secondo o unico acconto",
                    r"secondo\s+o\s+unico\s+acconto",
                ),
            ],
        )
    )
    fields.extend(
        _parse_model_rows(
            evidence,
            "730",
            text,
            ["RA", "RB", "RC", "RP", "RN", "RV", "RX", "LC", "E", "F"],
        )
    )
    return fields


def _parse_redditi_pf(evidence: DocumentEvidence, text: str) -> list[FiscalField]:
    fields = _parse_common_fields(evidence, "Redditi PF", text)
    fields.extend(
        _parse_labeled_amounts(
            evidence,
            "Redditi PF",
            text,
            "redditi_pf_riepilogo",
            [
                (
                    "reddito_complessivo",
                    "Reddito complessivo",
                    r"reddito\s+complessivo",
                ),
                ("imposta_lorda", "Imposta lorda", r"imposta\s+lorda"),
                ("imposta_netta", "Imposta netta", r"imposta\s+netta"),
                ("differenza", "Differenza", r"\bdifferenza\b"),
            ],
        )
    )
    fields.extend(
        _parse_model_rows(
            evidence,
            "Redditi PF",
            text,
            [
                "RA",
                "RB",
                "RC",
                "RP",
                "RN",
                "RV",
                "RX",
                "LM",
                "RE",
                "RF",
                "RG",
                "RR",
                "RS",
                "RW",
                "RT",
                "RM",
                "RL",
            ],
        )
    )
    return fields


def _parse_swiss_tax_document(
    evidence: DocumentEvidence, text: str, kind: str
) -> list[FiscalField]:
    fields = _parse_common_fields(evidence, kind, text)
    for index, match in enumerate(CH_AHV_RE.finditer(text), start=1):
        fields.append(
            _field(
                evidence,
                kind,
                "identificativi",
                f"ahv_avs_{index}",
                "Numero AVS/AHV individuato",
                match.group(0),
                "text",
                text,
                match,
                confidence="alta",
            )
        )
    fields.extend(
        _parse_labeled_amounts(
            evidence,
            kind,
            text,
            "ch_fields",
            [
                (
                    "salary_gross",
                    "Salaire brut / Bruttolohn",
                    r"salaire\s+brut|bruttolohn|gross\s+salary",
                ),
                (
                    "salary_net",
                    "Salaire net / Nettolohn",
                    r"salaire\s+net|nettolohn|net\s+salary",
                ),
                (
                    "taxable_income",
                    "Revenu imposable / steuerbares Einkommen",
                    r"revenu\s+imposable|steuerbares\s+einkommen|taxable\s+income",
                ),
                (
                    "taxable_wealth",
                    "Fortune imposable / steuerbares Vermögen",
                    r"fortune\s+imposable|steuerbares\s+vermogen|steuerbares\s+vermögen|taxable\s+wealth",
                ),
                (
                    "withholding_tax",
                    "Impôt anticipé / Verrechnungssteuer",
                    r"impot\s+anticipe|impôt\s+anticipé|verrechnungssteuer|withholding\s+tax",
                ),
                (
                    "cantonal_tax",
                    "Impôt cantonal / Kantonssteuer",
                    r"impot\s+cantonal|impôt\s+cantonal|kantonssteuer",
                ),
                (
                    "municipal_tax",
                    "Impôt communal / Gemeindesteuer",
                    r"impot\s+communal|impôt\s+communal|gemeindesteuer",
                ),
                (
                    "federal_tax",
                    "Impôt fédéral direct / direkte Bundessteuer",
                    r"impot\s+federal\s+direct|impôt\s+fédéral\s+direct|direkte\s+bundessteuer",
                ),
            ],
        )
    )
    return fields


def _parse_uk_tax_document(
    evidence: DocumentEvidence, text: str, kind: str
) -> list[FiscalField]:
    fields = _parse_common_fields(evidence, kind, text)
    for index, match in enumerate(UK_NINO_RE.finditer(text), start=1):
        fields.append(
            _field(
                evidence,
                kind,
                "identifiers",
                f"national_insurance_number_{index}",
                "National Insurance number",
                match.group(0),
                "text",
                text,
                match,
                confidence="alta",
            )
        )
    for match in re.finditer(
        r"\bUTR\s*[:\-]?\s*(?P<utr>\d{10})\b", text, re.IGNORECASE
    ):
        fields.append(
            _field(
                evidence,
                kind,
                "identifiers",
                "utr",
                "Unique Taxpayer Reference",
                match.group("utr"),
                "text",
                text,
                match,
                confidence="alta",
            )
        )
    fields.extend(
        _parse_labeled_amounts(
            evidence,
            kind,
            text,
            "uk_fields",
            [
                (
                    "total_pay",
                    "Total pay",
                    r"total\s+pay|pay\s+in\s+this\s+employment|taxable\s+pay",
                ),
                (
                    "tax_deducted",
                    "Tax deducted",
                    r"tax\s+deducted|paye\s+tax|income\s+tax",
                ),
                (
                    "national_insurance",
                    "National Insurance",
                    r"national\s+insurance|employee\s+nic|nic",
                ),
                ("student_loan", "Student loan", r"student\s+loan"),
                ("benefits", "Benefits", r"benefits|benefits\s+in\s+kind"),
                (
                    "bank_interest",
                    "Bank interest",
                    r"bank\s+interest|interest\s+received",
                ),
                ("dividends", "Dividends", r"dividends|dividend\s+income"),
                ("amount_due", "Amount due", r"amount\s+due|tax\s+due"),
                ("repayment_due", "Repayment due", r"repayment\s+due|tax\s+repayment"),
            ],
        )
    )
    return fields


def _dedupe(fields: Iterable[FiscalField]) -> list[FiscalField]:
    seen: set[tuple[str, str, str, str, str]] = set()
    deduped: list[FiscalField] = []
    for field in fields:
        key = (
            field.relative_path,
            field.document_kind,
            field.section,
            field.field_code,
            field.normalized_value,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(field)
    return deduped


def parse_structured_fiscal_fields(
    evidence: Sequence[DocumentEvidence],
    output_dir: Path | str,
) -> list[FiscalField]:
    """Parse structured fiscal fields from extracted document text."""

    output_path = Path(output_dir)
    fields: list[FiscalField] = []
    for item in evidence:
        if not item.readable or not item.text_path:
            continue
        text_path = output_path / item.text_path
        try:
            text = text_path.read_text(encoding="utf-8")
        except OSError:
            continue
        kind = _detect_kind(item, text)
        if kind == "F24":
            fields.extend(_parse_f24(item, text))
        elif kind == "CU":
            fields.extend(_parse_cu(item, text))
        elif kind == "730":
            fields.extend(_parse_730(item, text))
        elif kind == "Redditi PF":
            fields.extend(_parse_redditi_pf(item, text))
        elif kind.startswith(("Geneva", "Zurich", "CH ")):
            fields.extend(_parse_swiss_tax_document(item, text, kind))
        elif kind.startswith("UK "):
            fields.extend(_parse_uk_tax_document(item, text, kind))
    return _dedupe(fields)


def write_fiscal_fields_jsonl(
    fields: Iterable[FiscalField],
    output_path: Path | str,
) -> Path:
    """Write structured fiscal fields as JSONL."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for field in fields:
            handle.write(json.dumps(field.as_json(), ensure_ascii=False) + "\n")
    return path


def write_fiscal_fields_csv(
    fields: Iterable[FiscalField],
    output_path: Path | str,
) -> Path:
    """Write structured fiscal fields to CSV."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "relative_path",
        "file_name",
        "document_kind",
        "section",
        "field_code",
        "label",
        "value",
        "normalized_value",
        "value_type",
        "confidence",
        "evidence",
        "warnings",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for field in fields:
            writer.writerow(field.as_row())
    return path


def _localize_field_label(label: str, language: str) -> str:
    translated = FIELD_LABELS[language].get(label)
    if translated is not None:
        return translated

    cu_point = re.fullmatch(r"Punto CU (?P<point>\d+)", label)
    if cu_point:
        point = cu_point.group("point")
        return {
            "it": f"Punto CU {point}",
            "en": f"CU point {point}",
            "fr": f"Point CU {point}",
            "de": f"CU-Feld {point}",
            "es": f"Punto CU {point}",
        }[language]

    model_amount = re.fullmatch(r"(?P<row>[A-Z]+\d+) importo (?P<position>\d+)", label)
    if model_amount:
        row = model_amount.group("row")
        position = model_amount.group("position")
        return {
            "it": f"{row} importo {position}",
            "en": f"{row} amount {position}",
            "fr": f"{row} montant {position}",
            "de": f"{row} Betrag {position}",
            "es": f"{row} importe {position}",
        }[language]
    return label


def localize_field_label(label: str, language: str) -> str:
    """Return a fiscal-field label in one of the supported working languages."""

    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    return _localize_field_label(label, language)


def localize_warning(warning: str, language: str) -> str:
    """Return a fiscal-field warning in one supported working language."""

    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    return WARNING_LABELS[language].get(warning, warning)


def write_fiscal_fields_summary(
    fields: Sequence[FiscalField],
    output_path: Path | str,
    *,
    language: str = "it",
) -> Path:
    """Write a readable summary of structured fiscal fields."""

    language = language.strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Lingua non supportata: {language}. "
            f"Valori ammessi: {', '.join(SUPPORTED_LANGUAGES)}"
        )
    copy = SUMMARY_COPY[language]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    by_kind: dict[str, list[FiscalField]] = {}
    for field in fields:
        by_kind.setdefault(field.document_kind, []).append(field)

    lines = [
        f"# {copy['title']}",
        "",
        copy["limitation"],
        "",
        f"- {copy['field_count']}: {len(fields)}",
        f"- {copy['document_type_count']}: {len(by_kind)}",
        "",
    ]
    if not fields:
        lines.append(copy["empty"])
    for kind, kind_fields in sorted(by_kind.items()):
        lines.extend([f"## {kind}", ""])
        grouped: dict[str, list[FiscalField]] = {}
        for field in kind_fields:
            grouped.setdefault(field.relative_path, []).append(field)
        for relative_path, document_fields in sorted(grouped.items()):
            lines.extend([f"### `{relative_path}`", ""])
            for field in document_fields[:40]:
                label = _localize_field_label(field.label, language)
                confidence = CONFIDENCE_LABELS[language].get(
                    field.confidence, field.confidence
                )
                warnings = [localize_warning(item, language) for item in field.warnings]
                warning = f" — {', '.join(warnings)}" if warnings else ""
                lines.append(
                    f"- {label} (`{field.field_code}`): {field.normalized_value}"
                    f" [{confidence}]{warning}"
                )
            if len(document_fields) > 40:
                lines.append(
                    f"- {copy['additional_fields'].format(count=len(document_fields) - 40)}"
                )
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _load_document_evidence(path: Path) -> list[DocumentEvidence]:
    evidence: list[DocumentEvidence] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            data = json.loads(line)
            evidence.append(
                DocumentEvidence(
                    relative_path=data["relative_path"],
                    file_name=data["file_name"],
                    extension=data["extension"],
                    category=data["category"],
                    extraction_method=data["extraction_method"],
                    readable=bool(data["readable"]),
                    needs_ocr=bool(data["needs_ocr"]),
                    ocr_available=bool(data["ocr_available"]),
                    page_count=int(data["page_count"]),
                    char_count=int(data["char_count"]),
                    text_path=data["text_path"],
                    confidence=data["confidence"],
                    detected_fields_json=data["detected_fields_json"],
                    notes=tuple(data.get("notes", ())),
                )
            )
    return evidence


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estrae campi fiscali strutturati dai testi già estratti."
    )
    parser.add_argument(
        "extracted_dir",
        type=Path,
        help="Cartella extracted prodotta dal workflow.",
    )
    parser.add_argument(
        "--language",
        choices=SUPPORTED_LANGUAGES,
        default="it",
        help="Lingua del riepilogo leggibile.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    evidence = _load_document_evidence(args.extracted_dir / "documents.jsonl")
    fields = parse_structured_fiscal_fields(evidence, args.extracted_dir)
    write_fiscal_fields_csv(fields, args.extracted_dir / "structured_fiscal_fields.csv")
    write_fiscal_fields_jsonl(
        fields, args.extracted_dir / "structured_fiscal_fields.jsonl"
    )
    write_fiscal_fields_summary(
        fields,
        args.extracted_dir.parent / "08_dati_fiscali_strutturati.md",
        language=args.language,
    )
    LOGGER.info("Estratti %s campi fiscali strutturati.", len(fields))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
