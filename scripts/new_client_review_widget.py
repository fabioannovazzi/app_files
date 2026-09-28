"""Show grouped New Client facts without hiding nested records or changing review."""

from __future__ import annotations

import base64
import json
from pathlib import Path

__all__ = ["customize_review"]


def customize_review(html: str) -> str:
    """Display the exact public payload; only schema labels and enums translate."""
    root = Path(__file__).resolve().parents[1]
    labels = json.loads(
        (root / "plugins/new-client/references/review-labels.json").read_text()
    )
    helpers = (
        "    const NEW_CLIENT_LABELS = "
        + json.dumps(labels, ensure_ascii=True)
        + ";\n"
        + r"""
    function newClientLabels() { return NEW_CLIENT_LABELS[activeLanguage()] || NEW_CLIENT_LABELS.en; }
    function newClientError(message) {
      const match = String(message || "").match(/^New Client temporal validity expired on (\d{4}-\d{2}-\d{2}); regenerate the package before Apply$/);
      return match ? newClientLabels().expired.replace("{date}", match[1]) : message;
    }
    function newClientValue(value, key) {
      if (value == null || value === "") return newClientLabels().missing;
      if (Array.isArray(value)) {
        if (!value.length) return newClientLabels().none;
        return `<div class="new-client-records">${value.map(record => `<div class="new-client-record">${newClientValue(record, key)}</div>`).join("")}</div>`;
      }
      if (typeof value === "object") {
        if (value.fact_code && Object.prototype.hasOwnProperty.call(value, "value")) {
          const extra = Object.fromEntries(Object.entries(value).filter(([field]) => !["fact_code", "value", "verification_status"].includes(field)));
          return `<strong>${esc(humanize(value.fact_code))}</strong><p>${newClientValue(value.value, "value")}</p><small>${newClientValue(value.verification_status, "verification_status")}</small>${Object.keys(extra).length ? newClientValue(extra, "") : ""}`;
        }
        const first = ["party_facts", "services", "tax_fact_statuses"];
        const entries = Object.entries(value).sort(([a], [b]) => (first.includes(a) ? first.indexOf(a) : first.length) - (first.includes(b) ? first.indexOf(b) : first.length));
        return `<dl class="new-client-facts">${entries.map(([field, entry]) => `<dt>${esc(humanize(field))}</dt><dd>${newClientValue(entry, field)}</dd>`).join("")}</dl>`;
      }
      const coded = /(?:status(?:es)?|types?|kinds?|roles?|codes?|outcomes?)$/.test(key);
      const display = coded ? (newClientLabels().fields[String(value)] || newClientLabels().values[String(value)] || formatValue(value)) : formatValue(value);
      return esc(display);
    }
    function newClientDetailHtml(item) {
      return `<section class="new-client-detail"><h4>${esc(item.title)}</h4>${newClientValue(item.data || {}, "")}</section>`;
    }
"""
    )
    changes = [
        (
            '      node.textContent = message || "";',
            '      node.textContent = newClientError(message) || "";',
        ),
        (
            '    function setRecoveryIssue(kind, title, body, toolName = "", errorMessage = "") {',
            """    function setRecoveryIssue(kind, title, body, toolName = "", errorMessage = "") {
      const localized = newClientError(errorMessage);
      if (localized !== errorMessage) {
        body = localized;
        errorMessage = localized;
      }""",
        ),
        (
            "    function normalizedDecisionRecord(decision) {",
            """    function normalizedDecisionRecord(decision) {
      if (decision?.reuse_saved_details === true) {
        const saved = state.payload.ui_decisions?.decisions?.find(entry => entry.item_id === decision.item_id && entry.action === decision.action);
        if (saved) decision = saved;
      }""",
        ),
        (
            "      const result = parseToolResult(await window.openai.callTool(saveTool, saveToolArgs()));",
            "      const submittedDecisions = collectDecisionInputs();\n"
            "      const result = parseToolResult(await window.openai.callTool(saveTool, saveToolArgs()));",
        ),
        (
            "      if (result.ui_decisions) state.payload.ui_decisions = result.ui_decisions;\n      return result;",
            """      if (result.ui_decisions) {
        state.payload.ui_decisions = result.ui_decisions;
        const current = collectDecisionInputs();
        for (const submitted of submittedDecisions) {
          const live = current.find(decision => decision.item_id === submitted.item_id);
          if (live && decisionSignature([live]) === decisionSignature([submitted])) {
            state.decisions[submitted.item_id].reuse_saved_details = true;
          }
        }
      }
      return result;""",
        ),
        (
            "      const draftCount = state.recovery?.draftDecisionCount || 0;",
            "      const draftCount = hasUnsaved ? (state.recovery?.draftDecisionCount || 0) : 0;",
        ),
        (
            '        setSaveStatus(result.message || uiText("decisionsSaved", "Decisions saved."), "ok");',
            '        setSaveStatus(uiText("decisionsSaved", "Decisions saved."), "ok");',
        ),
        ("    function humanize(value) {", helpers + "    function humanize(value) {"),
        (
            '      const key = String(value || "");',
            '      const key = String(value || "");\n      if (newClientLabels().fields[key]) return newClientLabels().fields[key];',
        ),
        (
            "    function workflowDetailHtml(item) {",
            "    function workflowDetailHtml(item) {\n      return newClientDetailHtml(item);",
        ),
        (
            "${decisionControlsHtml(item)}${workflowDetailHtml(item)}${evidenceHtml(item)}",
            "${workflowDetailHtml(item)}${evidenceHtml(item)}${decisionControlsHtml(item)}",
        ),
    ]
    for before, after in changes:
        if html.count(before) != 1:
            raise ValueError(f"New Client widget generation anchor changed: {before}")
        html = html.replace(before, after)
    css = """
    :root { --accent:#173f68; --accent-strong:#102f50; --accent-soft:#f0f6fb; }
    body { font-family:"Instrument Sans",sans-serif; }
    .row { grid-template-columns:minmax(0,1fr) 7rem; align-items:start; }
    .row > .type { display:none; }
    .row .title { min-width:0; overflow-wrap:anywhere; }
    .new-client-detail { margin-top:1rem; }
    .new-client-detail h4 { margin:0 0 1rem; }
    .new-client-facts { display:grid; grid-template-columns:minmax(8rem,30%) minmax(0,1fr); gap:.6rem 1rem; margin:0; }
    .new-client-facts dt { color:#58616a; font-size:.85rem; }
    .new-client-facts dd { margin:0; min-width:0; overflow-wrap:anywhere; }
    .new-client-records { display:grid; gap:.8rem; }
    .new-client-record { padding:.8rem 0; border-bottom:1px solid #e7e9ed; }
    .new-client-record p { margin:.25rem 0; }
    .new-client-record small { color:#58616a; }
    .new-client-record .new-client-facts { grid-template-columns:minmax(5rem,35%) minmax(0,1fr); }
    @media (max-width:700px) { .new-client-facts,.new-client-record .new-client-facts {grid-template-columns:1fr;} }
"""
    for weight, name in ((400, "Regular"), (600, "SemiBold")):
        font = (
            root
            / f"plugins/_shared/vendor/modules/courseware/assets/InstrumentSans-{name}.ttf"
        )
        encoded = base64.b64encode(font.read_bytes()).decode("ascii")
        css += f'@font-face{{font-family:"Instrument Sans";font-style:normal;font-weight:{weight};src:url(data:font/ttf;base64,{encoded}) format("truetype");}}'
    return html.replace("</style>", css + "\n</style>", 1)
