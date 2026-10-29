"""Regressions for central theme propagation and offline UI preservation."""

from __future__ import annotations

import hashlib
import json

import pytest

from scripts import sync_vera_ui_theme, vera_ui_theme


@pytest.mark.parametrize(
    "path,expected",
    sync_vera_ui_theme.expected_resources().items(),
    ids=[path.name for path in sync_vera_ui_theme.expected_resources()],
)
def test_vera_workflow_resource_contains_current_shared_theme(path, expected):
    assert path.read_text(encoding="utf-8") == expected


def test_central_theme_edit_reaches_workspace_and_specialist_review(
    monkeypatch, tmp_path
):
    # A central edit must propagate to both independent rendering paths.
    theme_path = tmp_path / "theme.css"
    new_theme = ":root { --accent: #454545; --radius: 11px; }\n"
    theme_path.write_text(new_theme, encoding="utf-8")
    monkeypatch.setattr(vera_ui_theme, "THEME_PATH", theme_path)

    resources = sync_vera_ui_theme.expected_resources()

    workspace = sync_vera_ui_theme.ROOT / "plugins/vera/ui/workspace.css"
    vouching = (
        sync_vera_ui_theme.ROOT
        / "plugins/check-entries/assets/check-entries-review-widget.html"
    )
    assert resources[workspace].endswith(new_theme + vera_ui_theme.END + "\n")
    assert new_theme in resources[vouching]
    assert resources[vouching].count(vera_ui_theme.START) == 1


def test_theme_refresh_preserves_review_code_and_local_layout():
    html = (
        "<html><head><style>.queue { display: grid; }</style></head>"
        '<body><button id="save">Salva</button>'
        '<script>window.save = () => "unchanged";</script></body></html>'
    )
    first = vera_ui_theme.theme_html(html, theme=":root { --accent: #111111; }")

    refreshed = vera_ui_theme.theme_html(first, theme=":root { --accent: #222222; }")

    assert refreshed.count(vera_ui_theme.START) == 1
    assert "#111111" not in refreshed
    assert ".queue { display: grid; }" in refreshed
    assert html.split("</head>")[1] == refreshed.split("</head>")[1]
    assert "@import" not in refreshed


def test_host_packaging_uses_latest_theme_only_for_vera_ui(monkeypatch, tmp_path):
    theme_path = tmp_path / "theme.css"
    theme = ":root { --accent: #454545; }\n"
    theme_path.write_text(theme)
    monkeypatch.setattr(vera_ui_theme, "THEME_PATH", theme_path)
    prefix = "package/plugins/vera/"
    widget = (
        b"<style>.queue { display: grid; }</style><script>window.review = 1;</script>"
    )
    entries = {
        prefix + "ui/workspace.css": b"body { margin: 0; }",
        prefix
        + "modules/check-entries/assets/check-entries-review-widget.html": widget,
        prefix + "vendor/modules/courseware/assets/course.css": b"body { margin: 0; }",
        "package/plugins/clara/ui/workspace.css": b"original Clara CSS",
        prefix
        + "modules/management-control-pack/assets/budget-report.css": b"original report CSS",
    }

    vera_ui_theme.theme_package_resources(entries, prefix)

    assert entries[prefix + "ui/theme.css"] == theme.encode()
    assert theme.encode() in entries[prefix + "ui/workspace.css"]
    assert (
        theme.encode()
        in entries[prefix + "vendor/modules/courseware/assets/course.css"]
    )
    themed_widget = entries[
        prefix + "modules/check-entries/assets/check-entries-review-widget.html"
    ]
    assert theme.encode() in themed_widget
    assert themed_widget.endswith(b"<script>window.review = 1;</script>")
    assert entries["package/plugins/clara/ui/workspace.css"] == b"original Clara CSS"
    assert (
        entries[prefix + "modules/management-control-pack/assets/budget-report.css"]
        == b"original report CSS"
    )


@pytest.fixture
def lesson_entries():
    prefix = "package/plugins/vera/"
    relative = "vendor/modules/courseware/assets/chat.html"
    original_ui = b"<style>body { margin: 0; }</style><p>Lesson</p>"
    source_hash = hashlib.sha256(original_ui).hexdigest()
    course = json.dumps(
        {"sources": [{"path": relative, "sha256": source_hash}]}
    ).encode()
    entries = {
        prefix + relative: original_ui,
        prefix + "assets/courses/example/course.json": course,
        prefix
        + "assets/courses/index.json": json.dumps(
            {"courses": {"example": {"sha256": hashlib.sha256(course).hexdigest()}}}
        ).encode(),
    }

    return entries, prefix, relative, source_hash


def test_themed_lesson_binds_exact_shipped_ui(lesson_entries):
    entries, prefix, relative, source_hash = lesson_entries
    vera_ui_theme.theme_package_resources(entries, prefix)

    shipped_course = entries[prefix + "assets/courses/example/course.json"]
    source = json.loads(shipped_course)["sources"][0]
    assert source["source_sha256"] == source_hash
    assert source["sha256"] == hashlib.sha256(entries[prefix + relative]).hexdigest()
    record = json.loads(entries[prefix + "assets/courses/index.json"])["courses"][
        "example"
    ]
    assert record["sha256"] == hashlib.sha256(shipped_course).hexdigest()


def test_themed_lesson_rejects_stale_source(lesson_entries):
    entries, prefix, relative, source_hash = lesson_entries
    path = prefix + "assets/courses/example/course.json"
    course = json.loads(entries[path])
    course["sources"][0]["sha256"] = "0" * 64
    entries[path] = json.dumps(course).encode()
    entries[prefix + "assets/courses/index.json"] = json.dumps(
        {"courses": {"example": {"sha256": hashlib.sha256(entries[path]).hexdigest()}}}
    ).encode()

    with pytest.raises(ValueError, match="Stale course source"):
        vera_ui_theme.theme_package_resources(entries, prefix)
