"""Product builds retain useful native controls without duplicate inspectors."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts import build_codex_plugin_zip as builder
from scripts.product_ui_retirement import (
    CLARA_WIDGETS,
    LUCIA_RETIRED,
    retire_product_interfaces,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "product,removed", [("clara", CLARA_WIDGETS), ("lucia", LUCIA_RETIRED)]
)
def test_retirement_is_product_scoped_and_unknown_html_requires_classification(
    product, removed
):
    prefix = "package/plugins/" + product + "/"
    entries = {
        prefix + next(iter(removed)): b"retired",
        "independent/assets/widget.html": b"independent",
        prefix + "vendor/modules/courseware/assets/chat.html": b"course",
    }
    retire_product_interfaces(entries, prefix, product)
    assert entries["independent/assets/widget.html"] == b"independent"
    assert entries[prefix + "vendor/modules/courseware/assets/chat.html"] == b"course"
    entries[prefix + "assets/unreviewed-editor.html"] = b"unknown"
    with pytest.raises(ValueError, match="Unclassified"):
        retire_product_interfaces(entries, prefix, product)


@pytest.mark.parametrize("product,html_count", [("clara", 29), ("lucia", 3)])
def test_real_product_projection_preserves_deliverables_and_new_native_shells(
    monkeypatch, tmp_path, product, html_count
):
    # This tests projection only; full release builds separately exercise discovery.
    monkeypatch.setattr(builder, "add_vera_execution_manifest", lambda *args: None)
    target = next(item for item in builder.load_packages() if item.plugin == product)
    entries = builder.source_zip_entries(target)
    prefix = f"{target.package_root}/plugins/{product}/"
    html = [
        name.removeprefix(prefix)
        for name in entries
        if name.startswith(prefix) and name.endswith(".html")
    ]
    assert len(html) == html_count
    retired = json.loads(entries[prefix + "ui/retired-browser-interfaces.json"])[
        "removed_paths"
    ]
    assert all(prefix + path not in entries for path in retired)
    if product == "clara":
        assert (
            len([name for name in html if name.startswith("skills/html-deck/assets/")])
            == 27
        )
        session = entries[
            prefix + "modules/scatter-bubble-analysis/scripts/review_session.py"
        ].decode()
        assert "_write_standalone_review_html" not in session
        assert "scatter-bubble-review-widget.html" not in session
        assert "review_note_path" in session
        # Exercise the projected generator, rather than asserting its text alone.
        function = next(
            item
            for item in ast.parse(session).body
            if isinstance(item, ast.FunctionDef) and item.name == "_write_review_note"
        )
        namespace = {"Path": Path, "Any": object}
        exec(
            compile(
                ast.Module(body=[function], type_ignores=[]), "<projected-note>", "exec"
            ),
            namespace,
        )
        note = namespace["_write_review_note"](tmp_path, {})
        assert note.name == "scatter_bubble_review.md"
        assert "generated charts" in note.read_text()
        assert not (tmp_path / "scatter_bubble_review.html").exists()
    else:
        assert "assets/playbook-editor.html" in html
        assert (
            "modules/apertura-pratica/assets/apertura-pratica-review-widget.html"
            in html
        )
        assert "modules/apertura-pratica/scripts/apertura_pratica_core.py" in [
            name.removeprefix(prefix) for name in entries if name.startswith(prefix)
        ]
