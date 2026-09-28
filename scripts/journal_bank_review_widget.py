"""Localize the actual reconciliation record fields shown in the review."""

import json

_KEYS = [
    "journal_date",
    "journal_amount",
    "journal_description",
    "bank_date",
    "bank_amount",
    "bank_description",
    "stage",
    "shared_references",
    "amount_delta",
    "date_diff_days",
    "review_note",
]
_LABELS = {
    "it": [
        "Data contabile",
        "Importo contabile",
        "Descrizione contabile",
        "Data banca",
        "Importo bancario",
        "Descrizione banca",
        "Metodo",
        "Riferimenti comuni",
        "Differenza importi",
        "Differenza giorni",
        "Nota di revisione",
    ],
    "en": [
        "Journal date",
        "Journal amount",
        "Journal description",
        "Bank date",
        "Bank amount",
        "Bank description",
        "Method",
        "Shared references",
        "Amount difference",
        "Days apart",
        "Review note",
    ],
    "fr": [
        "Date comptable",
        "Montant comptable",
        "Libellé comptable",
        "Date bancaire",
        "Montant bancaire",
        "Libellé bancaire",
        "Méthode",
        "Références communes",
        "Écart de montant",
        "Écart en jours",
        "Note de revue",
    ],
    "de": [
        "Buchungsdatum",
        "Buchungsbetrag",
        "Buchungstext",
        "Bankdatum",
        "Bankbetrag",
        "Banktext",
        "Methode",
        "Gemeinsame Referenzen",
        "Betragsdifferenz",
        "Tagesdifferenz",
        "Prüfnotiz",
    ],
    "es": [
        "Fecha contable",
        "Importe contable",
        "Descripción contable",
        "Fecha bancaria",
        "Importe bancario",
        "Descripción bancaria",
        "Método",
        "Referencias comunes",
        "Diferencia de importe",
        "Diferencia en días",
        "Nota de revisión",
    ],
}


def customize_review(html: str) -> str:
    labels = {
        language: dict(zip(_KEYS, values)) for language, values in _LABELS.items()
    }
    return html.replace(
        "    function humanize(value) {",
        "    const JOURNAL_BANK_LABELS = "
        + json.dumps(labels, ensure_ascii=True)
        + ";\n"
        "    function humanize(value) {\n"
        "      const label = JOURNAL_BANK_LABELS[activeLanguage()]?.[String(value || '')];\n"
        "      if (label) return label;",
        1,
    )
