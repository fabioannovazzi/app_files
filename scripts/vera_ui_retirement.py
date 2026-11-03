"""Remove obsolete browser editors from Vera while retaining native review engines."""

from __future__ import annotations

import ast
import json
import re

__all__ = ["retire_browser_interfaces"]

# These are the five advertised app shells. Reports are generated at run time,
# not packaged editor templates. Independent sibling plugins are not changed.
APP_HTML = frozenset(
    {
        "ui/workspace.html",
        "ui/studio-work.html",
        "ui/research-sources.html",
        "modules/browser-automation/ui/agenzia.html",
        "vendor/modules/courseware/assets/chat.html",
    }
)
RETIRED_HTML = frozenset(
    {
        "modules/adeguati-assetti/assets/construction-intake.html",
        "modules/bilancio-xbrl-it/ui/workspace.html",
        "modules/treasury-forecast/assets/review.html",
        "modules/prompt-optimizer/assets/legal-tax-model.html",
        "ui/course-chat.html",
        *[
            "modules/" + component + "/assets/" + asset
            for component, asset in (
                ("archive-organization", "archive-organization-review-widget.html"),
                ("check-entries", "check-entries-review-widget.html"),
                (
                    "client-file-preparation",
                    "client-file-preparation-review-widget.html",
                ),
                ("concordato-plan-review", "concordato-plan-review-widget.html"),
                ("deep-research-validator", "deep-research-review-widget.html"),
                ("journal-bank-reconciliation", "journal-bank-review-widget.html"),
                ("journal-sampling", "journal-sampling-review-widget.html"),
                ("new-client", "new-client-review-widget.html"),
                (
                    "open-item-reconciliation",
                    "open-item-reconciliation-review-widget.html",
                ),
                ("previdenza-inps", "previdenza-inps-review-widget.html"),
                ("prompt-optimizer", "prompt-optimizer-review-widget.html"),
                ("registro-imprese-sari", "registro-imprese-sari-review-widget.html"),
                ("report-builder", "report-builder-review-widget.html"),
                ("variance-analysis", "variance-analysis-review-widget.html"),
            )
        ],
    }
)
BROWSER_FUNCTIONS = frozenset(
    {
        "_validate_loopback_host",
        "_review_url",
        "_server_class",
        "_widget_path",
        "_script_json",
        "_bridge_html",
        "render_review_html",
        "_widget_html",
        "create_review_http_server",
        "_review_output_path",
        "_handler",
        "serve_review",
        "_parser",
        "main",
    }
)


def _review_engine(content: bytes) -> bytes:
    """Retain data/persistence functions, removing HTTP, HTML and CLI launchers."""
    text = content.decode()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    cuts = []
    for item in tree.body:
        remove = (
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name in BROWSER_FUNCTIONS
        )
        remove |= (
            isinstance(item, ast.If)
            and ast.unparse(item.test) == "__name__ == '__main__'"
        )
        remove |= isinstance(item, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in item.targets
        )
        if isinstance(item, ast.Import):
            remove |= any(
                alias.name in {"webbrowser", "socket", "ipaddress"}
                for alias in item.names
            )
        if isinstance(item, ast.ImportFrom):
            remove |= item.module in {"http", "http.server", "urllib.parse"}
        if remove:
            cuts.append(
                (
                    min(
                        [item.lineno]
                        + [d.lineno for d in getattr(item, "decorator_list", [])]
                    ),
                    item.end_lineno,
                )
            )
    for start, end in sorted(cuts, reverse=True):
        del lines[start - 1 : end]
    result = "".join(lines).rstrip() + "\n"
    ast.parse(result)
    return result.encode()


def retire_browser_interfaces(entries: dict[str, bytes], prefix: str) -> None:
    """Retire only Vera's embedded copies; native producer and review APIs survive."""
    removed = set()
    for name in list(entries):
        if not name.startswith(prefix):
            continue
        rel = name.removeprefix(prefix)
        if rel in RETIRED_HTML:
            removed.add(rel)
            del entries[name]
        elif rel.endswith(".html") and rel not in APP_HTML:
            raise ValueError("Unclassified Vera HTML template: " + rel)
        elif rel in {
            "modules/treasury-forecast/scripts/treasury_server.py",
            "modules/treasury-forecast/assets/review.js",
            "modules/treasury-forecast/assets/review.css",
            "modules/treasury-forecast/assets/custom_select.js",
            "modules/management-control-pack/scripts/preview_report.py",
            "modules/bilancio-xbrl-it/ui/workspace.js",
            "modules/bilancio-xbrl-it/ui/workspace.css",
        }:
            removed.add(rel)
            del entries[name]
        elif (
            rel.endswith("/scripts/review_server.py")
            or rel == "scripts/serve_review_workbench.py"
        ):
            entries[name] = _review_engine(entries[name])
    # The canonical registry also serves sibling products. Advertise only the
    # entrypoints retained in this Vera projection.
    registry_name = prefix + "skills/vera/references/workflow-registry.json"
    if registry_name in entries:
        registry = json.loads(entries[registry_name])
        for component in registry["components"]:
            component["python_entrypoints"] = [
                path for path in component["python_entrypoints"] if path not in removed
            ]
        entries[registry_name] = (
            json.dumps(registry, ensure_ascii=False, indent=2) + "\n"
        ).encode()
    # Retired widget files were implementation inputs only while they existed.
    # Remove those exact receipt rows, retaining every engine/security input.
    retired_assets = {
        gone.split("/", 2)[-1] for gone in removed if gone.startswith("modules/")
    }
    for name in list(entries):
        if not name.startswith(prefix):
            continue
        if name.endswith(".py"):
            text = entries[name].decode()
            # Build hosts may predate the managed Python runtime. Parse only
            # the reviewed receipt declarations that actually need rewriting;
            # unrelated runtime modules can use newer Python syntax.
            if not any(path in text for path in retired_assets):
                continue
            tree = ast.parse(text)
            cuts = set()
            for item in ast.walk(tree):
                if isinstance(item, ast.Tuple):
                    hits = [
                        e
                        for e in item.elts
                        if isinstance(e, ast.Constant) and e.value in retired_assets
                    ]
                    if hits and len(item.elts) <= 4:
                        cuts.add((item.lineno, item.end_lineno))
                    else:
                        cuts.update((e.lineno, e.end_lineno) for e in hits)
            lines = text.splitlines(keepends=True)
            for start, end in sorted(cuts, reverse=True):
                del lines[start - 1 : end]
            text = "".join(lines)
            if name.endswith("/journal_sampling_core.py"):
                start = text.index("    embedded_adapter = (")
                end = text.index("\ndef _implementation_receipts", start)
                text = text[:start] + "\n" + text[end:]
            ast.parse(text)
            entries[name] = text.encode()
        elif name.endswith("/mcp/server.cjs"):
            text = entries[name].decode()

            def retained_row(match):
                return (
                    ""
                    if any(
                        json.dumps(path) in match.group(0) for path in retired_assets
                    )
                    else match.group(0)
                )

            text = re.sub(
                r"^([ \t]*)\[\n.*?^\1\],?\n", retained_row, text, flags=re.S | re.M
            )
            text = "\n".join(
                line
                for line in text.split("\n")
                if not (
                    any(json.dumps(path) in line for path in retired_assets)
                    and (
                        line.strip().startswith("[")
                        or re.fullmatch(r'\s*"[^"\n]+",?\s*', line)
                    )
                )
            )
            if name.endswith("/journal-sampling/mcp/server.cjs"):
                start = text.index("  const widget = readJournalImplementationText(")
                end = text.index(
                    "\n}\n\nvalidateJournalImplementationConfiguration", start
                )
                text = text[:start] + text[end:]
            text = re.sub(
                r"function resources\(\) \{.*?^\}",
                "function resources() { return []; }",
                text,
                flags=re.S | re.M,
            )
            text = re.sub(
                r"function resourceText\(uri\) \{.*?^\}",
                'function resourceText(uri) { throw new Error("Use vera_open_review for the saved work"); }',
                text,
                flags=re.S | re.M,
            )
            entries[name] = text.encode()
        elif name.endswith("/bilancio-xbrl-it/mcp/native-workspace.cjs"):
            text = entries[name].decode()
            text = re.sub(
                r"function readResource\(\) \{.*?^\}",
                'function readResource() { throw new Error("Use vera_open_review for the saved work"); }',
                text,
                flags=re.S | re.M,
            )
            entries[name] = text.encode()
    for name in list(entries):
        if not name.startswith(prefix + "modules/") or not name.endswith(".md"):
            continue
        text = entries[name].decode()
        rel = name.removeprefix(prefix)
        native_docs = (
            "Apri la revisione del lavoro esatto con `vera_open_review`. "
            "Conserva validazione, save/apply e rigenerazione degli artefatti nel "
            "contratto esistente. Se la revisione MCP non è disponibile, esamina "
            "i documenti in chat e lascia le decisioni in attesa: un'approvazione "
            "in conversazione non è una revisione applicata.\n\n"
        )
        document_sections = {
            "modules/client-file-preparation/references/workflow-reference.md": (
                ("## MCP Review Handoff", "## Integrity And Review Contract"),
            ),
            "modules/client-file-preparation/README.md": (
                ("Il widget usa", "Per arrivare allo stato finale"),
            ),
            "modules/new-client/README.md": (
                (
                    "Se i tool MCP del client non sono disponibili",
                    "## Fonti e template",
                ),
            ),
            "modules/open-item-reconciliation/README.md": (
                ("## Review browser locale e UI MCP", "I descrittori di avvio"),
                (
                    "La sequenza `validate_open_item_reconciliation_review`",
                    "## Diagnostica run",
                ),
            ),
        }
        for start_marker, end_marker in document_sections.get(rel, ()):
            start = text.find(start_marker)
            end = text.find(end_marker, start)
            if start < 0 or end < 0:
                raise ValueError("Native review documentation boundary is missing")
            heading = start_marker + "\n\n" if start_marker.startswith("## ") else ""
            text = text[:start] + heading + native_docs + text[end:]
        if not name.endswith("/SKILL.md"):
            # Component READMEs list the retired render tools as well as CLIs.
            text = re.sub(
                r"^.*`?render_[a-z_]+_review`?.*(?:\n[ \t]+[^\n]+)*",
                "Open the exact saved work with `vera_open_review`.",
                text,
                flags=re.M,
            )
            entries[name] = text.encode()
            continue
        text = text.replace(
            "before\n     `render_archive_organization_review`.",
            "and open the exact saved work with `vera_open_review`.",
        ).replace("to render, save, and apply calls", "to save and apply calls")
        text = text.replace(
            "If\nvalidation passes, call `render_check_entries_review` with only that reference;\n"
            "the server sends the complete payload to the widget through component-only\n"
            "metadata, not model-visible structured content.",
            "Open the exact saved work with `vera_open_review`; do not pass the component "
            "validation reference to that opener.",
        )
        text = text.replace(
            "Pass only that reference to\n`render_open_item_reconciliation_review`; "
            "the server sends the complete payload to\nthe widget through component-only "
            "metadata, not model-visible structured\ncontent.",
            "Open the exact saved work with `vera_open_review`; do not pass the component "
            "validation reference to that opener.",
        )
        text = text.replace(
            "Render the metadata inspector\n   with `render_variance_analysis_review` "
            "only when the user needs technical trace details.",
            "Open the exact saved work with `vera_open_review` when interactive review is needed.",
        )
        text = text.replace(
            "then call `render_client_file_preparation_review` once validation succeeds.",
            "then open the exact saved work with `vera_open_review`.",
        ).replace("render_client_file_preparation_review\n", "vera_open_review\n")
        if "/modules/deep-research-validator/" in "/" + name:
            start = text.find("This projects the saved issues, cycles,")
            if start >= 0:
                end = text.find("For a completed run,", start)
                if end < 0:
                    raise ValueError("Deep research completed-run safeguard is missing")
                text = (
                    text[:start]
                    + "Review the saved issues, cycles, source captures, original and opposing "
                    "opinions, assessment and comparison in chat and their retained documents. "
                    "Validate the hash-bound local review reference and preserve the existing "
                    "save/apply contract. This workflow has no native review route; do not launch "
                    "another widget. Declared status and display limits do not certify closure, "
                    "coverage or legal quality. Read the original artifacts for substantive review.\n"
                    + text[end:]
                )
        # Replace only numbered render steps; the following substantive review,
        # validation, persistence and professional safeguards remain intact.
        text = re.sub(
            r"^(\d+)\. [^\n]*`render_[a-z_]+_review`[^\n]*\n(?: {3}[^\n]*\n)*",
            r"\1. Open the exact saved work with `vera_open_review`; do not pass component validation fields to this opener.\n",
            text,
            flags=re.M,
        )
        # These two skills describe browser recovery outside their UI section.
        # Retain the no-write-back safeguard when that retired transport is absent.
        if "/modules/client-file-preparation/" in "/" + name:
            text = re.sub(
                r"   MCP server owns validation, HTML widget rendering, and decision persistence;"
                r".*?A final-ready review must record a stable",
                "   Native MCP owns validation and decision persistence. If it is unavailable,\n"
                "   leave decisions pending and review Markdown in chat. A final-ready review "
                "must record a stable",
                text,
                flags=re.S,
            )
        for component, start_marker, end_marker in (
            (
                "client-file-preparation",
                "If the host MCP tools are unavailable, do not replace write-back",
                "6. Inspect nearby source files",
            ),
            (
                "new-client",
                "If the host MCP tools are unavailable, start the packaged local workbench",
                "## Expected artifacts",
            ),
        ):
            if f"/modules/{component}/" not in "/" + name:
                continue
            start = text.find(start_marker)
            if start >= 0:
                end = text.find(end_marker, start)
                if end < 0:
                    raise ValueError("Native fallback safeguard boundary is missing")
                text = (
                    text[:start]
                    + "If the native MCP review is unavailable, review the Markdown artifacts "
                    "in chat and leave decisions pending. A conversational approval is not "
                    "an applied professional review. Resume the exact saved work with "
                    "`vera_open_review` when the native service is available.\n\n"
                    + text[end:]
                )
        if "/modules/management-control-pack/" in "/" + name:
            start = text.find(
                "Open the final interactive HTML in Codex through the bound local preview:"
            )
            end = text.find("Visually inspect the final HTML.", start)
            if start >= 0 and end >= 0:
                text = (
                    text[:start]
                    + (
                        "Open the exact work with `vera_open_review`, then Commento e rapporto and "
                        "Anteprima interattiva del rapporto. The app verifies the original report receipt "
                        "and renders its month controls in an isolated frame. Keep the normal HTML and "
                        "workbook exports. No localhost preview process is shipped in Vera.\n\n"
                    )
                    + text[end:]
                )
        native_review = (
            "## MCP Review UI\n\nDeliver results in chat and their normal documents. "
            "For an interactive review open the exact saved work with `vera_open_review`. "
            "If that workflow has no review route, retain the review in chat and documents. "
            "Use the native editor for actual decisions; preserve unresolved items and exact-version "
            "save/apply and regeneration requirements. No standalone browser server or component widget is shipped.\n\n"
        )
        for heading in ("MCP Review UI",):
            text = re.sub(
                r"^## " + heading + r"\n.*?(?=^## |\Z)",
                native_review,
                text,
                flags=re.S | re.M,
            )
        start = text.find("## Browser Review UI And MCP Widget\n")
        if start >= 0:
            end = text.find("Review actions cannot waive", start)
            if end < 0:
                raise ValueError("Open-item review safeguards are missing")
            text = (
                text[:start]
                + native_review.replace(
                    "## MCP Review UI", "## Browser Review UI And MCP Widget", 1
                )
                + text[end:]
            )
        entries[name] = text.encode()
    # Course records pin actual installed bytes. Do not leave retired assets in
    # their source list or silently claim the unchanged source hash was installed.
    import hashlib

    index_name = prefix + "assets/courses/index.json"
    if index_name in entries:
        index = json.loads(entries[index_name])
        for workflow, record in index["courses"].items():
            name = prefix + f"assets/courses/{workflow}/course.json"
            before = entries[name]
            course = json.loads(before)
            changed = False
            sources = []
            for source in course["sources"]:
                path = source["path"]
                if path in removed:
                    changed = True
                    continue
                current = entries.get(prefix + path)
                if (
                    current is not None
                    and hashlib.sha256(current).hexdigest() != source["sha256"]
                ):
                    source.setdefault("source_sha256", source["sha256"])
                    source["sha256"] = hashlib.sha256(current).hexdigest()
                    changed = True
                sources.append(source)
            if changed:
                course["sources"] = sources
                entries[name] = (
                    json.dumps(course, ensure_ascii=False, indent=2) + "\n"
                ).encode()
                record.setdefault("source_sha256", hashlib.sha256(before).hexdigest())
                record["sha256"] = hashlib.sha256(entries[name]).hexdigest()
        entries[index_name] = (
            json.dumps(index, ensure_ascii=False, indent=2) + "\n"
        ).encode()
    entries[prefix + "ui/retired-browser-interfaces.json"] = (
        json.dumps(
            {
                "schema_version": 1,
                "removed_paths": sorted(removed),
                "review_engine_only": "Python payload and decision engines retained without browser/HTTP launchers",
            },
            indent=2,
        )
        + "\n"
    ).encode()
