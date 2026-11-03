"""Vera ships native review surfaces without sibling browser editors."""

from __future__ import annotations

import ast
import re
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


def test_native_client_skills_preserve_pending_review_without_browser_fallback():
    entries = {
        f"modules/{component}/skills/{component}/SKILL.md": (
            ROOT / f"plugins/{component}/skills/{component}/SKILL.md"
        ).read_bytes()
        for component in ("new-client", "client-file-preparation")
    }
    for component, document in (
        ("new-client", "README.md"),
        ("client-file-preparation", "README.md"),
        ("client-file-preparation", "references/workflow-reference.md"),
        ("open-item-reconciliation", "README.md"),
    ):
        entries[f"modules/{component}/{document}"] = (
            ROOT / f"plugins/{component}/{document}"
        ).read_bytes()
    retire_browser_interfaces(entries, "")
    for name, content in entries.items():
        if not name.endswith(".md"):
            continue
        assert b"python scripts/review_server.py" not in content
        assert b"python -I -B scripts/review_server.py" not in content
        assert b"serve_review_workbench.py" not in content
        assert b"vera_open_review" in content
        if name.endswith("/SKILL.md"):
            assert b"leave decisions pending" in content
            assert (
                b"conversational approval is not an applied professional review"
                in content
            )
    assert (
        b"I descrittori di avvio"
        in entries["modules/open-item-reconciliation/README.md"]
    )
    assert (
        b"## MCP Review Handoff"
        in entries["modules/client-file-preparation/references/workflow-reference.md"]
    )


def test_retirement_preserves_newer_managed_python_sources_on_older_build_hosts(
    monkeypatch,
):
    parse = ast.parse
    runtime_source = b'result = f"{metric["value"]:,.0f}"\n'

    def legacy_parse(source, **kwargs):
        # Reproduce the pre-3.12 rejection observed in the completed CI job.
        if source == runtime_source.decode():
            raise SyntaxError("f-string requires the managed Python runtime")
        return parse(source, **kwargs)

    monkeypatch.setattr(ast, "parse", legacy_parse)
    entries = {
        "modules/management-control-pack/scripts/management_control_core.py": runtime_source,
        "modules/archive-organization/assets/archive-organization-review-widget.html": b"retired editor",
        "ui/workspace.html": b"native app",
    }
    retire_browser_interfaces(entries, "")
    assert (
        entries["modules/management-control-pack/scripts/management_control_core.py"]
        == runtime_source
    )


def test_projected_component_instructions_do_not_call_retired_render_tools():
    components = (
        "archive-organization",
        "check-entries",
        "client-file-preparation",
        "concordato-plan-review",
        "deep-research-validator",
        "journal-bank-reconciliation",
        "journal-sampling",
        "new-client",
        "open-item-reconciliation",
        "previdenza-inps",
        "registro-imprese-sari",
        "report-builder",
        "variance-analysis",
    )
    entries = {
        f"modules/{component}/{path.relative_to(ROOT / 'plugins' / component)}": path.read_bytes()
        for component in components
        for path in (ROOT / "plugins" / component).rglob("*.md")
    }
    retire_browser_interfaces(entries, "")
    for name, content in entries.items():
        if name.endswith(("/SKILL.md", "/README.md")):
            assert not re.search(rb"render_[a-z_]+_review", content), name
    deep = entries["modules/deep-research-validator/skills/deep-research/SKILL.md"]
    assert b"This workflow has no native review route" in deep
    assert b"For a completed run," in deep


def test_cowork_projects_native_fallback_without_reintroducing_browser_servers():
    from scripts.build_claude_plugin_zip import (
        _project_client_file_preparation_cowork_skill,
        _project_new_client_cowork_skill,
    )

    entries = {
        f"modules/{component}/skills/{component}/SKILL.md": (
            ROOT / f"plugins/{component}/skills/{component}/SKILL.md"
        ).read_bytes()
        for component in ("new-client", "client-file-preparation")
    }
    retire_browser_interfaces(entries, "")
    for component, project in (
        ("new-client", _project_new_client_cowork_skill),
        ("client-file-preparation", _project_client_file_preparation_cowork_skill),
    ):
        text = entries[f"modules/{component}/skills/{component}/SKILL.md"].decode()
        cowork = project(text)
        assert "optional native MCP review is unavailable" in cowork
        assert "leave decisions pending" in cowork
        assert "scripts/review_server.py" not in cowork


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
