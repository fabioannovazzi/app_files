from __future__ import annotations

import base64
import re
from pathlib import Path

__all__ = ["customize_review"]


def customize_review(html: str) -> str:
    """Compose the accounting desk without changing other widget consumers."""
    assets = Path(__file__).with_name("review_widgets")
    css = (assets / "open_item.css").read_text(encoding="utf-8")
    font_root = assets.parents[1] / "plugins/comunicazione-professionale/assets/fonts"
    for weight, name in [(400, "Regular"), (600, "SemiBold")]:
        encoded = base64.b64encode(
            (font_root / f"InstrumentSans-{name}.ttf").read_bytes()
        ).decode("ascii")
        css += f'\n@font-face {{font-family:"Instrument Sans";font-style:normal;font-weight:{weight};src:url(data:font/ttf;base64,{encoded}) format("truetype");}}'
    javascript = (assets / "open_item.js").read_text(encoding="utf-8")
    # Replace complete top-level functions only; retain the shared persistence,
    # validation, recovery and event handlers unchanged.
    functions = re.findall(
        r"^    function (\w+)\([^\n]*.*?(?=^    function |\Z)",
        javascript,
        flags=re.MULTILINE | re.DOTALL,
    )
    for name in functions:
        pattern = rf"^    function {name}\([^\n]*.*?(?=^    (?:function |const |document\.|window\.|state\.)|\Z)"
        replacement = re.search(pattern, javascript, flags=re.MULTILINE | re.DOTALL)
        if replacement is None:
            raise ValueError(f"missing review function: {name}")
        html, count = re.subn(
            pattern,
            lambda _: replacement.group(0),
            html,
            count=1,
            flags=re.MULTILINE | re.DOTALL,
        )
        if count != 1:
            raise ValueError(f"unknown shared review function: {name}")
    strings = (assets / "open_item_i18n.json").read_text(encoding="utf-8")
    # Keep the server bridge insertion point immediately before CONFIG.
    html = re.sub(
        r"(    const CONFIG = [^\n]+\n)",
        lambda match: match[0] + f"    const DESK_TEXT = {strings};\n",
        html,
        count=1,
    )
    helpers = javascript.split("    function ", 1)[0]
    html = html.replace(
        "    const PANEL_KEYS = ", helpers + "    const PANEL_KEYS = ", 1
    )
    html = html.replace("  </style>", css + "\n  </style>", 1)
    start = html.index('      <section class="run-context"')
    end = html.index('      <section class="review-actions">', start)
    diagnostics = html[start:end]
    html = html[:start] + html[end:]
    action_start = html.index('      <section class="review-actions">')
    action_end = html.index('      <section class="state-strip"', action_start)
    actions = html[action_start:action_end]
    html = html[:action_start] + html[action_end:]
    html = html.replace(
        '      <section class="artifact-strip" id="artifact-strip"></section>',
        actions
        + '<details class="desk-diagnostics"><summary id="diagnostics-title"></summary>'
        + diagnostics
        + '<section class="artifact-strip" id="artifact-strip"></section></details>',
    )
    html = html.replace(
        '<div class="action-buttons">',
        '<p id="desk-save-help"></p><div class="action-buttons">',
        1,
    )
    html = html.replace(
        '<section class="toolbar">',
        '<section class="toolbar"><p id="desk-section-help"></p>',
        1,
    )
    html = html.replace(
        '<div class="review-store" id="review-store"></div>',
        '<div class="review-store" id="review-store" aria-live="polite"></div>',
        1,
    )
    html = html.replace(
        '<div class="recovery-panel" id="recovery-panel"></div>',
        '<details id="checkpoint-details"><summary id="checkpoint-title"></summary><label class="field"><span id="checkpoint-label"></span><input id="review-checkpoint" type="text" maxlength="64" autocomplete="off" spellcheck="false"></label></details><div class="recovery-panel" id="recovery-panel"></div>',
        1,
    )
    html = html.replace(
        '<span class="status-message" id="save-status">',
        '<span class="status-message" id="save-status" role="status">',
        1,
    )
    # Keep exports for offline recovery, remove bulk accounting approval.
    html = html.replace(
        '<button class="button" id="use-recommended"',
        '<button hidden class="button" id="use-recommended"',
        1,
    )
    exports = []
    for button_id in ["copy-decisions", "download-decisions"]:
        pattern = rf'<button[^>]+id="{button_id}"[^>]*>.*?</button>'
        match = re.search(pattern, html)
        if match is None:
            raise ValueError(f"missing recovery control: {button_id}")
        exports.append(match[0])
        html = html.replace(match[0], "", 1)
    html = html.replace(
        '<summary id="diagnostics-title"></summary>',
        '<summary id="diagnostics-title"></summary><div class="action-buttons">'
        + "".join(exports)
        + "</div>",
        1,
    )
    html = html.replace(
        'result.message || uiText("decisionsSaved", "Decisions saved.")',
        'result.copied || result.persisted === false ? deskText("notPersisted") : deskText("saveSuccess")',
    )
    html = html.replace(
        'result.message || uiText("decisionsApplied", "Decisions applied.")',
        'deskText("applySuccess")',
    )
    html = html.replace(
        '"Enter the predecessor SHA-256 checkpoint retained through the separate review channel."',
        'deskText("checkpointPrompt")',
    )
    html = html.replace(
        '"A valid external predecessor checkpoint is required before apply."',
        'deskText("checkpointRequired")',
    )
    html = html.replace(
        "if (result.applied_decisions) state.payload.applied_decisions = result.applied_decisions;",
        "if (result.applied_decisions) { state.payload.applied_decisions = result.applied_decisions; state.payload.ui_decisions = { ...state.payload.ui_decisions, decisions: result.applied_decisions.decisions }; }",
    )
    return html
