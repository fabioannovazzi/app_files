"""Localize the archive review's displayed fields without altering decisions."""

from __future__ import annotations

import base64
import json
from pathlib import Path

__all__ = ["customize_review"]


def customize_review(html: str) -> str:
    """Keep file paths, evidence and transport unchanged in the current widget."""
    root = Path(__file__).resolve().parents[1]
    words = json.loads(
        (root / "plugins/archive-organization/references/review-labels.json").read_text(
            encoding="utf-8"
        )
    )
    labels = {language: value["widget"] for language, value in words.items()}
    helpers = (
        "    const ARCHIVE_LABELS = "
        + json.dumps(labels, ensure_ascii=True)
        + ";\n"
        + """    function archiveLabels() { return ARCHIVE_LABELS[activeLanguage()] || ARCHIVE_LABELS.en; }
    function archiveValue(value, field) {
      return archiveLabels().values[field]?.[String(value)] ?? formatValue(value);
    }
"""
    )
    changes = [
        (
            "      const draftCount = state.recovery?.draftDecisionCount || 0;",
            "      const draftCount = hasUnsaved ? (state.recovery?.draftDecisionCount || 0) : 0;",
            1,
        ),
        (
            "      const fallbackActive = items().length > 0 && !canPersistThroughBridge();",
            "      const fallbackActive = !state.payload.local_review_read_only && items().length > 0 && !canPersistThroughBridge();",
            1,
        ),
        (
            "      return normalizedDecisionList(state.payload.applied_decisions?.decisions);",
            """      const decisions = state.payload.applied_decisions?.decisions || [];
      return normalizedDecisionList(decisions.filter(d => itemById(d.item_id)?.allowed_actions?.includes(d.reviewer_action)).map(d => ({
        item_id: d.item_id, action: d.reviewer_action, reviewer_note: d.reviewer_note,
        edit_value: d.reviewer_action === "edit" ? d.approved_target_relative_path : "",
      })));""",
            1,
        ),
        (
            "${outputLinkHtml(item.output_path)}",
            "${outputLinkHtml(item.output_path, true)}",
            1,
        ),
        (
            '      return items().filter((item) => String(item.item_type || "").includes("artifact") || item.output_path).map((item) => ({ path: item.output_path || item.title, kind: String(item.output_path || "file").split(".").pop(), status: item.data?.exists === false ? "missing" : "written" })).slice(0, 8);',
            "      return [];",
            1,
        ),
        (
            "    function humanize(value) {",
            helpers + "    function humanize(value) {",
            1,
        ),
        (
            '      const key = String(value || "");',
            '      const key = String(value || "");\n      if (archiveLabels().fields[key]) return archiveLabels().fields[key];',
            1,
        ),
        (
            "return GROUP_TEXT[lang]?.[group.title]",
            "return archiveLabels().groups[group.title] || GROUP_TEXT[lang]?.[group.title]",
            1,
        ),
        (
            "return GROUP_TEXT[lang]?.[group.empty]",
            "return archiveLabels().groups[group.empty] || GROUP_TEXT[lang]?.[group.empty]",
            1,
        ),
        (
            "evidenceValueHtml(value)}</div>",
            "evidenceValueHtml(archiveValue(value, key))}</div>",
            2,
        ),
        (
            'const label = activeLanguage() === "it" ? (downloadable ? "Scarica documento" : "Copia percorso") : (downloadable ? "Download file" : "Copy path");',
            'const label = archiveLabels().links[downloadable ? "download" : "copy"];',
            1,
        ),
        (
            'message.textContent = activeLanguage() === "it" ? (downloaded ? "Documento scaricato." : "Percorso copiato.") : (downloaded ? "File downloaded." : "Path copied.");',
            'message.textContent = archiveLabels().links[downloaded ? "downloaded" : "copied"];',
            1,
        ),
        (
            "      validateReviewerReference(decisions);",
            "      if (decisions.length && !reviewerAliasValue()) throw new Error(archiveLabels().reviewerRequired);\n      validateReviewerReference(decisions);",
            1,
        ),
    ]
    for before, after, expected in changes:
        if html.count(before) != expected:
            raise ValueError(f"Archive widget generation anchor changed: {before}")
        html = html.replace(before, after)
    css = """
    :root { --accent:#173f68; --accent-strong:#102f50; --accent-soft:#f0f6fb; }
    body { font-family:"Instrument Sans",sans-serif; }
    .row { grid-template-columns:minmax(0,1fr) 7rem; align-items:start; }
    .row > .type, .row .row-support { display:none; }
    .row .title { display:block; }

"""
    fonts = root / "plugins/comunicazione-professionale/assets/fonts"
    for weight, name in ((400, "Regular"), (600, "SemiBold")):
        encoded = base64.b64encode(
            (fonts / f"InstrumentSans-{name}.ttf").read_bytes()
        ).decode("ascii")
        css += f'\n@font-face {{font-family:"Instrument Sans";font-style:normal;font-weight:{weight};src:url(data:font/ttf;base64,{encoded}) format("truetype");}}'
    return html.replace("  </style>", css + "\n  </style>", 1)
