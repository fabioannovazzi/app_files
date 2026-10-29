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


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_host_packaging_themes_product_ui_and_preserves_reports(
    monkeypatch, tmp_path, product
):
    theme_path = tmp_path / "theme.css"
    theme = ":root { --accent: #454545; }\n"
    theme_path.write_text(theme)
    monkeypatch.setattr(vera_ui_theme, "THEME_PATH", theme_path)
    prefix = f"package/plugins/{product}/"
    widget = (
        b"<style>.queue { display: grid; }</style><script>window.review = 1;</script>"
    )
    entries = {
        prefix + "ui/workspace.css": b"body { margin: 0; }",
        prefix
        + "modules/check-entries/assets/check-entries-review-widget.html": widget,
        prefix + "vendor/modules/courseware/assets/course.css": b"body { margin: 0; }",
        "package/plugins/other/ui/workspace.css": b"unrelated CSS",
        prefix
        + "modules/management-control-pack/assets/budget-report.css": b"original report CSS",
    }

    vera_ui_theme.theme_package_resources(entries, prefix)

    assert entries[prefix + "ui/theme.css"] == theme.encode()
    assert theme.encode() in entries[prefix + "ui/workspace.css"]
    assert (
        theme.encode()
        in entries[prefix + "vendor/modules/courseware/assets/course.css"]
    ) == (product == "vera")
    themed_widget = entries[
        prefix + "modules/check-entries/assets/check-entries-review-widget.html"
    ]
    assert theme.encode() in themed_widget
    assert themed_widget.endswith(b"<script>window.review = 1;</script>")
    assert entries["package/plugins/other/ui/workspace.css"] == b"unrelated CSS"
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


def test_course_shell_theme_is_idempotent_and_preserves_content():
    original = '<head><link rel="stylesheet" href="course.css"></head><body>Lesson<script>copyPrompt()</script></body>'
    themed = vera_ui_theme.theme_course_page(original)
    assert themed == vera_ui_theme.theme_course_page(themed)
    assert themed.split("</head>")[1] == original.split("</head>")[1]
    assert themed.count("workflow-theme.css") == 1


@pytest.mark.parametrize(
    "relative",
    [
        "assets/playbook-editor.html",
        "modules/apertura-pratica/assets/apertura-pratica-review.html",
    ],
)
def test_local_legal_editors_receive_same_packaged_theme(relative):
    prefix = "package/plugins/lucia/"
    original = b'<style>main{max-width:900px}</style><button id="save">Save</button><script>persist()</script>'
    entries = {prefix + relative: original}
    vera_ui_theme.theme_package_resources(entries, prefix)
    assert vera_ui_theme.THEME_PATH.read_bytes() in entries[prefix + relative]
    assert (
        entries[prefix + relative].split(b"</style>")[1]
        == original.split(b"</style>")[1]
    )


@pytest.mark.parametrize("product", ["clara", "lucia"])
def test_lesson_theme_keeps_shared_report_styles_unchanged(tmp_path, product):
    import importlib.util

    module_path = (
        sync_vera_ui_theme.ROOT / "plugins/_shared/vendor/modules/courseware/theme.py"
    )
    spec = importlib.util.spec_from_file_location("lesson_theme", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / product
    (root / "ui").mkdir(parents=True)
    theme = b":root { --accent: #35463f; }"
    (root / "ui/theme.css").write_bytes(theme)
    destination = tmp_path / "lesson"
    destination.mkdir()
    report_css = b"body { color: navy; }"
    (destination / "course.css").write_bytes(report_css)
    page = '<head><link rel="stylesheet" href="course.css"></head><body>Lesson</body>'

    themed = module.theme_lesson(page, product, root, destination)

    assert 'href="workflow-theme.css"' in themed
    assert (destination / "workflow-theme.css").read_bytes() == theme
    assert (destination / "course.css").read_bytes() == report_css
    assert themed.split("</head>")[1] == page.split("</head>")[1]


def test_missing_cosmetic_theme_does_not_block_lesson_delivery(tmp_path):
    import importlib.util

    module_path = (
        sync_vera_ui_theme.ROOT / "plugins/_shared/vendor/modules/courseware/theme.py"
    )
    spec = importlib.util.spec_from_file_location("missing_lesson_theme", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.__file__ = str(tmp_path / "vendor/modules/courseware/theme.py")
    page = "<head></head><body>Useful lesson content</body>"

    result = module.theme_lesson(page, "clara", tmp_path / "clara", tmp_path)

    assert result == page
