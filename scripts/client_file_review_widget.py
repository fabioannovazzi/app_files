"""Present the intake payload's actual request and draft before its decision."""

from __future__ import annotations

import json

__all__ = ["customize_review"]

_LABELS = {
    "it": [
        "Richiesta proposta",
        "Anteprima della bozza",
        "Campo",
        "Valore",
        "Motivi",
        "Documenti ricevuti",
        "Documento da chiarire",
        "Richieste al cliente",
        "Dati fiscali",
        "Memo dello studio",
        "Bozza email",
    ],
    "en": [
        "Proposed request",
        "Draft preview",
        "Field",
        "Value",
        "Reasons",
        "Received documents",
        "Uncertain document",
        "Client requests",
        "Fiscal data",
        "Studio memo",
        "Email draft",
    ],
    "fr": [
        "Demande proposée",
        "Aperçu du brouillon",
        "Champ",
        "Valeur",
        "Motifs",
        "Documents reçus",
        "Document à clarifier",
        "Demandes au client",
        "Données fiscales",
        "Note du cabinet",
        "Brouillon du courriel",
    ],
    "de": [
        "Vorgeschlagene Anfrage",
        "Entwurfsvorschau",
        "Feld",
        "Wert",
        "Gründe",
        "Erhaltene Dokumente",
        "Zu klärendes Dokument",
        "Mandantenanfragen",
        "Steuerdaten",
        "Kanzleinotiz",
        "E-Mail-Entwurf",
    ],
    "es": [
        "Solicitud propuesta",
        "Vista previa del borrador",
        "Campo",
        "Valor",
        "Motivos",
        "Documentos recibidos",
        "Documento por aclarar",
        "Solicitudes al cliente",
        "Datos fiscales",
        "Nota del despacho",
        "Borrador del correo",
    ],
}
_KEYS = [
    "request_text",
    "preview",
    "label",
    "value",
    "reasons",
    "document_inventory",
    "uncertain_file",
    "missing_document_request",
    "extracted_fiscal_field",
    "draft_memo_section",
    "draft_client_email",
]


def customize_review(html: str) -> str:
    """Keep save/apply behavior intact and render only existing payload fields."""
    labels = {
        lang: dict(zip(_KEYS, values, strict=True)) for lang, values in _LABELS.items()
    }
    anchor = '      const key = String(value || "");'
    if html.count(anchor) != 1:
        raise ValueError("Client review label insertion point changed")
    html = html.replace(
        anchor,
        anchor
        + "\n      const labels = "
        + json.dumps(labels, ensure_ascii=True)
        + ";\n      if (labels[activeLanguage()]?.[key]) return labels[activeLanguage()][key];",
    )
    html = html.replace(
        "${decisionControlsHtml(item)}${workflowDetailHtml(item)}",
        "${workflowDetailHtml(item)}${decisionControlsHtml(item)}",
    )
    html = html.replace(
        "    function valueForField(item, field) {",
        """    function valueForField(item, field) {
      if (field === "preview" && ["draft_client_email", "draft_memo_section"].includes(item.item_type)) {
        const effects = state.payload.applied_decisions?.effects || [];
        const applied = effects.find(effect => effect.item_id === item.id && effect.applied === true
          && effect.artifact_update === "target_artifact_updated" && effect.target_artifact === item.output_path);
        if (typeof applied?.edit_value === "string") return applied.edit_value;
      }""",
        1,
    )
    return html.replace(
        "  </style>",
        "    .workflow-card--draft { grid-column: 1 / -1; }\n"
        "    .workflow-card--draft .kv > div:nth-child(even) { white-space: pre-wrap; }\n  </style>",
        1,
    )
