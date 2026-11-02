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
    html = html.replace(
        '<div class="top-actions">',
        '<div class="top-actions"><button type="button" id="open-bank-panel" class="secondary"></button>',
        1,
    ).replace(
        "    function renderChrome() {",
        """    const openPanel = document.getElementById("open-bank-panel");
    const openPanelLabels = {it:"Apri pannello", en:"Open panel", fr:"Ouvrir le panneau", de:"Panel öffnen", es:"Abrir panel"};
    const inlineLabels = {it:"Il pannello rimane nella chat.", en:"The review remains in the chat.", fr:"La revue reste dans la discussion.", de:"Die Prüfung bleibt im Chat.", es:"La revisión permanece en el chat."};
    openPanel.addEventListener("click", async () => {
      try {
        const result = await window.mparanzaReviewHost.requestDisplayMode("fullscreen");
        document.documentElement.dataset.reviewDisplayMode = result.mode;
        if (result.mode !== "fullscreen") setSaveStatus(inlineLabels[activeLanguage()], "");
      } catch (error) { setSaveStatus(error.message, "error"); }
    });
    function renderChrome() {
      openPanel.textContent = openPanelLabels[activeLanguage()];""",
    )
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
