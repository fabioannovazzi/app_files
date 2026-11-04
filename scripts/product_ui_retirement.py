"""Retire product-only inspectors; keep independent components and output assets."""

from __future__ import annotations

import ast
import hashlib
import json
import re

__all__ = ["retire_product_interfaces", "CLARA_WIDGETS", "LUCIA_RETIRED"]

CLARA_WIDGETS = {
    f"modules/{component}/assets/{asset}-review-widget.html"
    for component, asset in (
        ("distribution-analysis", "distribution"),
        ("mix-contribution-analysis", "mix-contribution"),
        ("period-comparison", "period-comparison"),
        ("scatter-bubble-analysis", "scatter-bubble"),
        ("set-overlap-analysis", "set-overlap"),
        ("variance-analysis", "variance-analysis"),
    )
}
LUCIA_RETIRED = {
    "modules/apertura-pratica/assets/apertura-pratica-review.html",
    "modules/apertura-pratica/scripts/review_server.py",
    "modules/prompt-optimizer/assets/legal-tax-model.html",
    "modules/prompt-optimizer/assets/prompt-optimizer-review-widget.html",
    "modules/deep-research-validator/assets/deep-research-review-widget.html",
}

CHART_REVIEW_COPY = {
    "Render review_payload.json with the MCP widget when available.": "Review the generated charts and report with Clara in this chat.",
    "Renderice review_payload.json con el widget MCP cuando esté disponible.": "Revise los gráficos y el informe con Clara en esta conversación.",
    "Cuando esté disponible, abra review_payload.json con el widget MCP.": "Revise los gráficos y el informe con Clara en esta conversación.",
    "Aprire review_payload.json con il widget MCP quando disponibile.": "Riesamina i grafici e il rapporto con Clara nella chat.",
    "Ouvrir review_payload.json avec le widget MCP lorsqu’il est disponible.": "Examinez les graphiques et le rapport avec Clara dans cette conversation.",
    "review_payload.json nach Verfügbarkeit im MCP-Widget öffnen.": "Prüfen Sie die Diagramme und den Bericht mit Clara in diesem Chat.",
    "Open scatter_bubble_review.html for the chart-first run UI.": "Review the generated charts and report with Clara in this chat.",
    "Abra scatter_bubble_review.html para revisar primero los gráficos de la ejecución.": "Revise los gráficos y el informe con Clara en esta conversación.",
}


def _scatter_note(text: str) -> str:
    """Keep review receipts and chart handoff without a second HTML shell."""
    function = next(
        item
        for item in ast.parse(text).body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_write_standalone_review_html"
    )
    lines = text.splitlines(keepends=True)
    lines[function.lineno - 1 : function.end_lineno] = [
        '''def _write_review_note(output_dir: Path, payload: dict[str, Any]) -> Path:
    """Keep the normal chart/report handoff without a metadata inspector."""
    path = output_dir / "scatter_bubble_review.md"
    path.write_text("Review the generated charts and report with Clara. Discuss findings in chat; preserve explicit decisions and validation before finalizing.\\n", encoding="utf-8")
    return path
'''
    ]
    result = (
        "".join(lines)
        .replace("_write_standalone_review_html", "_write_review_note")
        .replace("review_html_path", "review_note_path")
        .replace('"review_html"', '"review_note"')
        .replace("scatter_bubble_review.html", "scatter_bubble_review.md")
    )
    ast.parse(result)
    return result


def _rebind_courses(entries: dict[str, bytes], prefix: str, removed: set[str]) -> None:
    """Retain source provenance and pin the exact installed implementation."""
    index_name = prefix + "assets/courses/index.json"
    if index_name not in entries:
        return
    index = json.loads(entries[index_name])
    for workflow, record in index["courses"].items():
        name = prefix + f"assets/courses/{workflow}/course.json"
        before = entries[name]
        course = json.loads(before)
        sources = []
        for source in course["sources"]:
            path = source["path"]
            if path in removed:
                continue
            current = entries.get(prefix + path)
            if (
                current is not None
                and hashlib.sha256(current).hexdigest() != source["sha256"]
            ):
                source.setdefault("source_sha256", source["sha256"])
                source["sha256"] = hashlib.sha256(current).hexdigest()
            sources.append(source)
        course["sources"] = sources
        after = (json.dumps(course, ensure_ascii=False, indent=2) + "\n").encode()
        if after != before:
            entries[name] = after
            record.setdefault("source_sha256", hashlib.sha256(before).hexdigest())
            record["sha256"] = hashlib.sha256(after).hexdigest()
    entries[index_name] = (
        json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    ).encode()


def retire_product_interfaces(
    entries: dict[str, bytes], prefix: str, product: str
) -> None:
    """Retire only Clara/Lucia embedded copies, preserving independent siblings."""
    if product not in {"clara", "lucia"}:
        raise ValueError("Unsupported product UI projection")
    retired = set(CLARA_WIDGETS) if product == "clara" else set(LUCIA_RETIRED)
    if product == "clara":
        retired.add("modules/management-control-pack/scripts/preview_report.py")
    removed = {rel for rel in retired if prefix + rel in entries}
    for rel in removed:
        del entries[prefix + rel]
    for name in list(entries):
        if not name.startswith(prefix):
            continue
        rel = name.removeprefix(prefix)
        if name.endswith(".html"):
            allowed = {"vendor/modules/courseware/assets/chat.html"}
            allowed |= (
                {"ui/report.html"}
                if product == "clara"
                else {
                    "assets/playbook-editor.html",
                    "modules/apertura-pratica/assets/apertura-pratica-review-widget.html",
                }
            )
            output_template = product == "clara" and rel.startswith(
                "skills/html-deck/assets/"
            )
            if rel not in allowed and not output_template:
                raise ValueError("Unclassified product HTML: " + rel)
        elif name.endswith(".py") and "/scripts/" in name:
            text = entries[name].decode()
            if product == "clara" and rel.endswith("/scripts/review_session.py"):
                for before, after in CHART_REVIEW_COPY.items():
                    text = text.replace(before, after)
            if rel == "modules/scatter-bubble-analysis/scripts/review_session.py":
                text = _scatter_note(text)
            elif (
                rel == "modules/scatter-bubble-analysis/scripts/scatter_bubble_core.py"
            ):
                text = text.replace("review_html_path", "review_note_path")
            if rel in {
                "modules/prompt-optimizer/scripts/review_server.py",
                "modules/deep-research-validator/scripts/review_server.py",
            }:
                from scripts.vera_ui_retirement import _review_engine

                text = _review_engine(text.encode()).decode()
            entries[name] = text.encode()
        elif name.endswith(".md") and rel.startswith("modules/"):
            text = entries[name].decode()
            for heading in ("MCP Review UI", "Review UI", "MCP Review Handoff"):
                text = re.sub(
                    r"^## " + heading + r"\n.*?(?=^## |\Z)",
                    "## "
                    + heading
                    + "\n\nReview the professional result in chat and its normal charts/reports. Preserve exact-version validation, explicit decisions, save/apply and regeneration requirements. No metadata inspector or standalone browser editor is shipped in this product.\n\n",
                    text,
                    flags=re.S | re.M,
                )
            if (
                product == "lucia"
                and rel == "modules/apertura-pratica/skills/apertura-pratica/SKILL.md"
            ):
                start, end = text.index("5. For a multi-item review"), text.index(
                    "6. Apply only decisions"
                )
                text = (
                    text[:start]
                    + "5. Open the selected absolute run directory with `lucia_matter_open`. The native panel preserves pending decisions bound to the current intake. Saving does not apply decisions or accept the engagement. If unavailable, review the normal documents in chat and keep the UI check pending.\n\n"
                    + text[end:]
                )
            entries[name] = text.encode()
    _rebind_courses(entries, prefix, removed)
    entries[prefix + "ui/retired-browser-interfaces.json"] = (
        json.dumps(
            {
                "schema_version": 1,
                "product": product,
                "removed_paths": sorted(removed),
                "retained": "Output templates, calculations, validation and decision engines; useful controls use native app routes.",
            },
            indent=2,
        )
        + "\n"
    ).encode()
