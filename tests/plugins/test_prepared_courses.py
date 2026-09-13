"""Course isolation, stale-source handling, real corpus rendering and privacy."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))
from courseware.library import CourseError, CourseLibrary, main

spec = importlib.util.spec_from_file_location(
    "course_build", ROOT / "scripts/course_materials/build_catalog.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
COURSES = [
    (product, workflow)
    for product in ("vera", "clara", "lucia")
    for workflow in sorted(builder._eligible(product))
]
LOCALIZED = [
    (product, workflow, language)
    for product, workflow in COURSES
    for language in builder.LIMITED_LANGUAGES.get(
        f"{product}/{workflow}", builder.LANGUAGES
    )
]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def isolated(tmp_path):
    """An installed product with one authored course and a local method source."""
    root = tmp_path / "vera"
    original = ROOT / "plugins/vera/assets/courses/variance-analysis/course.json"
    course = json.loads(original.read_text(encoding="utf-8"))
    skill = root / "skills/variance-analysis/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Own installed variance method\n", encoding="utf-8")
    course["sources"] = [
        {"path": "skills/variance-analysis/SKILL.md", "sha256": digest(skill)}
    ]
    course["files"] = []
    manifest = root / "assets/courses/variance-analysis/course.json"
    write_json(manifest, course)
    write_json(root / ".codex-plugin/plugin.json", {"name": "vera"})
    index = {
        "product": "vera",
        "courses": {
            "variance-analysis": {
                "path": "variance-analysis/course.json",
                "sha256": digest(manifest),
                "languages": list(course["locales"]),
            }
        },
    }
    write_json(root / "assets/courses/index.json", index)
    return root, manifest, skill


def alter_course(isolated, change):
    root, path, _ = isolated
    course = json.loads(path.read_text(encoding="utf-8"))
    change(course)
    write_json(path, course)
    index_path = root / "assets/courses/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["courses"]["variance-analysis"]["sha256"] = digest(path)
    write_json(index_path, index)


@pytest.mark.parametrize("product,workflow", COURSES)
def test_every_installed_workflow_has_a_source_current_course(product, workflow):
    library = CourseLibrary(ROOT / "plugins" / product, builder._eligible(product))

    course = library.load(workflow, "it")

    assert course["product"] == product
    assert course["workflow"] == workflow
    assert sum(course["seconds"]) == 390
    assert course["sources"]
    assert course["example_kind"] == "authored_synthetic_specimen_not_execution_receipt"


@pytest.mark.parametrize("product,workflow", COURSES)
def test_each_course_has_a_specific_case_result_check_and_answer(product, workflow):
    course = CourseLibrary(ROOT / "plugins" / product, builder._eligible(product)).load(
        workflow, "it"
    )
    content = course["locales"]["it"]

    assert len(content["input_rows"]) >= 2
    assert len(content["output_rows"]) >= 2
    assert len(content["method"]) == 3
    assert len(content["scenario"].split()) >= 25
    assert len(content["answer"].split()) >= 12
    assert content["answer"] != content["question"]
    assert content["scope"]
    assert content["basis"]


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_catalog_exactly_covers_current_product_and_no_retired_ids(product):
    expected = builder._eligible(product)
    catalog = CourseLibrary(ROOT / "plugins" / product, expected).catalog()

    assert {row["workflow"] for row in catalog} == expected
    assert (
        not {"report-builder", "check-entries", "bilancio-xbrl-it", "interview"}
        & expected
    )


@pytest.mark.parametrize(
    "foreign", ["reporting-engine", "hosted-interview", "../clara/reporting-engine"]
)
def test_foreign_workflow_never_resolves_from_course_catalog(isolated, foreign):
    root, _, _ = isolated
    with pytest.raises(CourseError, match="this product"):
        CourseLibrary(root, {"variance-analysis"}).load(foreign, "it")


def test_removed_workflow_cannot_reuse_its_old_course(isolated):
    root, _, _ = isolated
    library = CourseLibrary(root, set())
    assert library.catalog() == []
    with pytest.raises(CourseError, match="this product"):
        library.load("variance-analysis", "it")


def test_unsupported_language_is_not_silently_translated(isolated):
    root, _, _ = isolated
    with pytest.raises(CourseError, match="select one"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "ja")


def test_source_change_requires_editorial_refresh(isolated):
    root, _, skill = isolated
    skill.write_text("# Changed method\n", encoding="utf-8")
    with pytest.raises(CourseError, match="editorial refresh"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "it")


def test_missing_source_cannot_fall_back_to_another_installation(isolated):
    root, _, skill = isolated
    skill.unlink()
    with pytest.raises(CourseError, match="Missing or foreign"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "it")


def test_foreign_symlink_source_is_rejected(isolated, tmp_path):
    root, _, skill = isolated
    foreign = tmp_path / "foreign.md"
    foreign.write_bytes(skill.read_bytes())
    skill.unlink()
    skill.symlink_to(foreign)
    with pytest.raises(CourseError, match="Missing or foreign"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "it")


def test_altered_material_is_detected_before_rendering(isolated, tmp_path):
    root, manifest, _ = isolated
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    destination = tmp_path / "untouched"
    with pytest.raises(CourseError, match="content changed"):
        CourseLibrary(root, {"variance-analysis"}).render(
            "variance-analysis", "it", destination
        )
    assert not destination.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("product", "clara"),
        ("workflow", "reporting-engine"),
        ("seconds", [20] * 6),
        ("schema", "unknown"),
    ],
)
def test_invalid_course_contract_is_rejected(isolated, field, value):
    root, _, _ = isolated
    alter_course(isolated, lambda course: course.update({field: value}))
    with pytest.raises(CourseError, match="Invalid course"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "it")


@pytest.mark.parametrize("path", ["../foreign.md", "/tmp/foreign.md", ""])
def test_course_file_paths_cannot_escape_their_root(isolated, path):
    root, _, _ = isolated
    alter_course(
        isolated,
        lambda course: course.update(files=[{"path": path, "sha256": "0" * 64}]),
    )
    with pytest.raises(CourseError, match="relative and contained"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "it")


def test_changed_attached_example_is_rejected(isolated):
    root, manifest, _ = isolated
    attachment = manifest.parent / "fixture.csv"
    attachment.write_text("amount\n10\n", encoding="utf-8")
    alter_course(
        isolated,
        lambda course: course.update(
            files=[{"path": "fixture.csv", "sha256": digest(attachment)}]
        ),
    )
    attachment.write_text("amount\n11\n", encoding="utf-8")
    with pytest.raises(CourseError, match="Prepared example changed"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "it")


@pytest.mark.parametrize(
    "product,workflow",
    [
        ("vera", "fatture-xml-check"),
        ("clara", "reporting-engine"),
        ("lucia", "apertura-pratica"),
    ],
)
def test_render_delivers_case_example_voice_guide_and_actual_starter_without_completing_a_lesson(
    tmp_path, product, workflow
):
    library = CourseLibrary(ROOT / "plugins" / product, builder._eligible(product))
    output = tmp_path / product

    receipt = library.render(workflow, "it", output)

    assert receipt["prepared_material_only"] is True
    assert receipt["execution_receipt"] is False
    assert receipt["understanding_confirmed"] is False
    assert (output / "files/executed-starter/provenance.json").is_file()
    assert (output / "source.md").read_text(encoding="utf-8").startswith("# ")
    assert (output / "input.csv").is_file()
    page = (output / "course.html").read_text(encoding="utf-8")
    assert "Due chat, una lezione" in page
    assert "<details>" in page
    assert "<html lang='it'>" in page
    assert "<script" not in page
    assert "https://" not in page
    assert not list(output.rglob("profile.json"))
    assert not list(output.rglob("session.json"))


def test_render_preserves_existing_files(isolated, tmp_path):
    root, _, _ = isolated
    output = tmp_path / "lesson"
    output.mkdir()
    sentinel = output / "notes.md"
    sentinel.write_text("My notes", encoding="utf-8")
    with pytest.raises(CourseError, match="preserve existing"):
        CourseLibrary(root, {"variance-analysis"}).render(
            "variance-analysis", "it", output
        )
    assert sentinel.read_text(encoding="utf-8") == "My notes"


def test_render_refuses_symlink_destination(isolated, tmp_path):
    root, _, _ = isolated
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(CourseError, match="not a symlink"):
        CourseLibrary(root, {"variance-analysis"}).render(
            "variance-analysis", "it", link / "course"
        )


def test_html_escapes_case_text_and_keeps_it_as_evidence(isolated, tmp_path):
    root, _, _ = isolated
    alter_course(
        isolated,
        lambda course: course["locales"]["it"].update(
            title="<script>alert('x')</script>"
        ),
    )
    output = tmp_path / "escaped"
    CourseLibrary(root, {"variance-analysis"}).render("variance-analysis", "it", output)
    page = (output / "course.html").read_text(encoding="utf-8")
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_cli_lists_own_courses(isolated, capsys):
    root, _, _ = isolated
    assert main(root, {"variance-analysis"}, ["list"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["workflow"] == "variance-analysis"


def test_cli_shows_prepared_source_checked_content(isolated, capsys):
    root, _, _ = isolated
    assert (
        main(
            root,
            {"variance-analysis"},
            ["show", "--workflow", "variance-analysis", "--language", "it"],
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["workflow"] == "variance-analysis"
    assert result["language"] == "it"
    assert result["sources_current"] is True
    assert "locales" not in result
    assert result["content"]["question"]


def test_cli_preserves_localized_symbols_on_legacy_windows_console(monkeypatch):
    buffer = io.BytesIO()
    console = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)

    assert (
        main(
            ROOT / "plugins/vera",
            builder._eligible("vera"),
            ["show", "--workflow", "management-control-pack", "--language", "en"],
        )
        == 0
    )

    console.flush()
    result = json.loads(buffer.getvalue().decode("cp1252"))
    assert "Δ" in json.dumps(result["content"], ensure_ascii=False)


@pytest.mark.parametrize("default_encoding", ["utf-8", "cp1252"])
def test_complete_compiled_catalog_matches_authoring_and_current_sources(
    monkeypatch, default_encoding
):
    original_read_text = Path.read_text

    def read_with_host_default(path, encoding=None, errors=None):
        return original_read_text(
            path, encoding=encoding or default_encoding, errors=errors
        )

    monkeypatch.setattr(Path, "read_text", read_with_host_default)
    assert builder.build(check=True) == {
        "workflows": 44,
        "localized_courses": 200,
        "missing_translations": {},
    }


@pytest.mark.parametrize("product,workflow,language", LOCALIZED)
def test_every_supported_locale_has_complete_renderable_material(
    tmp_path, product, workflow, language
):
    library = CourseLibrary(ROOT / "plugins" / product, builder._eligible(product))
    content = library.load(workflow, language)["locales"][language]
    assert set(content) == {
        "title",
        "goal",
        "scenario",
        "request",
        "scope",
        "input_columns",
        "input_rows",
        "basis",
        "method",
        "result_title",
        "conclusion",
        "output_columns",
        "output_rows",
        "check",
        "question",
        "answer",
        "practice",
        "next",
    }
    assert all(content.values())
    assert len(content["method"]) == 3
    assert all(
        len(row) == len(content["input_columns"]) for row in content["input_rows"]
    )
    assert all(
        len(row) == len(content["output_columns"]) for row in content["output_rows"]
    )
    destination = tmp_path / "lesson"

    library.render(workflow, language, destination)

    page = (destination / "course.html").read_text(encoding="utf-8")
    assert f"<html lang='{language}'>" in page
    assert page.count("class='lesson-step'") == 6
    assert "<details>" in page
    assert "<script" not in page
    assert "https://" not in page
    assert (destination / "example.html").is_file()


@pytest.mark.parametrize("language", builder.LANGUAGES)
def test_lucia_website_case_has_legal_services_in_each_language(language):
    library = CourseLibrary(ROOT / "plugins/lucia", builder._eligible("lucia"))
    content = library.load("presenza-digitale-studio", language)["locales"][language]
    assert (
        content["input_rows"][1][1]
        == {
            "it": "Contratti e controversie commerciali",
            "en": "Contracts and commercial disputes",
            "fr": "Contrats et litiges commerciaux",
            "de": "Verträge und Handelsstreitigkeiten",
            "es": "Contratos y controversias comerciales",
        }[language]
    )
    assert "Vera" not in json.dumps(content)


def test_chart_uses_authored_case_values_and_localized_labels(tmp_path):
    library = CourseLibrary(ROOT / "plugins/clara", builder._eligible("clara"))
    library.render("attribute-reporting", "es", tmp_path / "chart")
    page = (tmp_path / "chart/example.html").read_text(encoding="utf-8")
    assert "width='600.000'" in page
    assert "width='300.000'" in page
    assert "Nuevos" in page and "60 %" in page and "30 %" in page


def test_cli_refuses_foreign_workflow(isolated, capsys):
    root, _, _ = isolated
    with pytest.raises(SystemExit) as error:
        main(
            root,
            {"variance-analysis"},
            ["show", "--workflow", "reporting-engine", "--language", "it"],
        )
    assert error.value.code == 2
    assert "Course unavailable" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [["show"], ["render", "--workflow", "variance-analysis", "--language", "it"]],
)
def test_cli_requires_explicit_identity_and_destination(isolated, argv):
    root, _, _ = isolated
    with pytest.raises(SystemExit) as error:
        main(root, {"variance-analysis"}, argv)
    assert error.value.code == 2
