"""Vera ships native review surfaces without sibling browser editors."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.vera_ui_retirement import retire_browser_interfaces

ROOT = Path(__file__).resolve().parents[2]


def test_embedded_review_engines_survive_without_http_or_html_launchers():
    entries = {
        "scripts/serve_review_workbench.py": (
            ROOT / "scripts/serve_review_workbench.py"
        ).read_bytes(),
        "modules/open-item-reconciliation/scripts/review_server.py": (
            ROOT / "plugins/open-item-reconciliation/scripts/review_server.py"
        ).read_bytes(),
        "modules/archive-organization/assets/archive-organization-review-widget.html": b"retired editor",
        "modules/bilancio-xbrl-it/ui/workspace.html": b"retired duplicate",
        "modules/treasury-forecast/assets/review.html": b"retired editor",
        "ui/workspace.html": b"native app",
        "vendor/modules/courseware/assets/chat.html": b"native course app",
        "outside/normal-report.md": b"deliverable",
    }
    retire_browser_interfaces(entries, "")
    assert {name for name in entries if name.endswith(".html")} == {
        "ui/workspace.html",
        "vendor/modules/courseware/assets/chat.html",
    }
    for name in (
        "scripts/serve_review_workbench.py",
        "modules/open-item-reconciliation/scripts/review_server.py",
    ):
        tree = ast.parse(entries[name])
        functions = {
            item.name for item in tree.body if isinstance(item, ast.FunctionDef)
        }
        assert "build_session_payload" in functions
        assert "serve_review" not in functions
        assert "render_review_html" not in functions
        assert b"serve_forever" not in entries[name]
        assert b"BaseHTTPRequestHandler" not in entries[name]
    specialized = ast.parse(
        entries["modules/open-item-reconciliation/scripts/review_server.py"]
    )
    assert {"save_decisions", "apply_decisions"} <= {
        node.name for node in specialized.body if isinstance(node, ast.FunctionDef)
    }
    assert entries["outside/normal-report.md"] == b"deliverable"


def test_product_cleanup_does_not_remove_independent_plugin_editors():
    entries = {
        "vera/modules/report-builder/assets/report-builder-review-widget.html": b"Vera duplicate",
        "other/assets/review.html": b"independent product",
        "vera/ui/workspace.html": b"Vera native app",
    }
    retire_browser_interfaces(entries, "vera/")
    assert entries["other/assets/review.html"] == b"independent product"
    assert (
        "vera/modules/report-builder/assets/report-builder-review-widget.html"
        not in entries
    )
    assert entries["vera/ui/workspace.html"] == b"Vera native app"


def test_native_workspace_still_embeds_the_bilancio_area_renderer():
    source = (ROOT / "plugins/vera/mcp/workspace.cjs").read_text()
    assert "bilancio-xbrl-it/ui/area-review.js" in source
    assert "vera_workspace_management_commentary_preview" in source
    ui = (ROOT / "plugins/vera/ui/workspace.js").read_text()
    assert 'frame.setAttribute("sandbox","allow-scripts")' in ui
    assert "frame.srcdoc=preview.html" in ui
    assert ui.count('call("vera_workspace_management_commentary_preview"') == 1
    assert (
        'if(page.status==="accepted")main.append(button("Anteprima interattiva del rapporto"'
        in ui
    )
    assert "allow-same-origin" not in ui
