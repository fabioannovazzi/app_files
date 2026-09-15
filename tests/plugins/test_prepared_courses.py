"""Course isolation, stale-source handling, real corpus rendering and privacy."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
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
RELEASE = json.loads((ROOT / "scripts/course_materials/release_plan.json").read_text())
PREPARED = [(p, w) for p, w in COURSES if f"{p}/{w}" in RELEASE["prepared"]]
LOCALIZED = [
    (product, workflow, language)
    for product, workflow in PREPARED
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
    original = ROOT / "plugins/vera/assets/courses/fatture-xml-check/course.json"
    course = json.loads(original.read_text(encoding="utf-8"))
    skill = root / "skills/variance-analysis/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Own installed variance method\n", encoding="utf-8")
    course["sources"] = [
        {"path": "skills/variance-analysis/SKILL.md", "sha256": digest(skill)}
    ]
    course["workflow"] = "variance-analysis"
    manifest = root / "assets/courses/variance-analysis/course.json"
    for asset in course["files"]:
        target = manifest.parent / asset["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original.parent / asset["path"], target)
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
    expected_schema = (
        "mparanza.teaching_kit.v2"
        if (product, workflow) in PREPARED
        else "mparanza.course.v1"
    )
    assert course["schema"] == expected_schema


@pytest.mark.parametrize("product,workflow", PREPARED)
def test_each_kit_explains_first_use_and_supplies_actual_inputs(product, workflow):
    course = CourseLibrary(ROOT / "plugins" / product, builder._eligible(product)).load(
        workflow, "it"
    )
    content = course["locales"]["it"]
    assert content["request"]
    assert content["steps"]
    assert content["deliverables"]
    assert content["review"]
    assert content["practice"] != content["request"]
    assert content["success"]
    assert content["repeat"]
    assert not {"output_rows", "conclusion", "answer", "result_title"} & set(content)


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
    "workflow", ["brand-fit", "hosted-interview", "research-video"]
)
def test_hosted_clara_workflows_remain_installed_but_have_no_local_lesson(
    workflow, monkeypatch
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from desktop_teaching.onboarding import (
        OnboardingError,
        eligible_workflows,
        teaching_contract,
    )

    root = ROOT / "plugins/clara"
    assert (root / "skills" / workflow / "SKILL.md").is_file()
    assert workflow not in builder._eligible("clara")
    assert workflow not in eligible_workflows(root)
    library = CourseLibrary(root, {workflow})
    assert library.catalog() == []
    with pytest.raises(CourseError, match="requires hosted services"):
        library.load(workflow, "it")
    with pytest.raises(OnboardingError, match="requires hosted services"):
        teaching_contract(root, workflow)


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


@pytest.mark.parametrize(
    "product,workflow,packaged,repository",
    [
        (
            "clara",
            "attribute-reporting",
            "modules/attribute-reporting/vendor/modules/pdp/attribute_table_templates.py",
            "modules/pdp/attribute_table_templates.py",
        ),
        (
            "vera",
            "bilancio-oic",
            "modules/bilancio-xbrl-it/rulepacks/it/disclosures-2026.1.json",
            "plugins/bilancio-xbrl-it/rulepacks/it/disclosures-2026.1.json",
        ),
        (
            "vera",
            "browser-automation",
            "modules/browser-automation/scripts/discovery_runtime.mjs",
            "plugins/browser-automation/scripts/discovery_runtime.mjs",
        ),
    ],
)
def test_kit_fingerprints_include_actual_bundled_engine_dependencies(
    product, workflow, packaged, repository
):
    records = builder._source_records(product, workflow)
    matches = [record for record in records if record["path"] == packaged]
    assert matches == [
        {
            "path": packaged,
            "repository_path": repository,
            "sha256": digest(ROOT / repository),
        }
    ]


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
    # Windows resolves a POSIX root path against the current drive; both hosts
    # must reject it, whether at syntax or resolved-containment checks.
    with pytest.raises(
        CourseError, match="relative and contained|Missing or foreign course file"
    ):
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
    with pytest.raises(CourseError, match="Teaching input changed"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "it")


@pytest.mark.parametrize(
    "product,workflow",
    [
        ("vera", "fatture-xml-check"),
        ("clara", "html-deck"),
        ("lucia", "apertura-pratica"),
    ],
)
def test_render_supplies_inputs_and_worker_request_without_manufacturing_a_result(
    tmp_path, product, workflow
):
    library = CourseLibrary(ROOT / "plugins" / product, builder._eligible(product))
    output = tmp_path / product

    receipt = library.render(workflow, "it", output)

    assert receipt["prepared_material_only"] is True
    assert receipt["execution_receipt"] is False
    assert receipt["understanding_confirmed"] is False
    assert receipt["source_files"]
    assert receipt["practice_files"]
    request = json.loads(
        (output / "execution-request.json").read_text(encoding="utf-8")
    )
    assert request["product"] == product
    assert request["workflow"] == workflow
    assert request["execution_receipt"] is False
    assert request["source_files"] == receipt["source_files"]
    assert not (output / "example.html").exists()
    page = (output / "course.html").read_text(encoding="utf-8")
    assert "Due chat, una lezione" in page
    assert "execution-request.json" not in page
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
    assert result["content"]["checkpoints"]


def test_cli_preserves_localized_symbols_on_legacy_windows_console(
    monkeypatch, isolated
):
    root, _, _ = isolated
    alter_course(
        isolated, lambda course: course["locales"]["en"].update(title="Δ 预算")
    )
    buffer = io.BytesIO()
    console = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)

    assert (
        main(
            root,
            {"variance-analysis"},
            ["show", "--workflow", "variance-analysis", "--language", "en"],
        )
        == 0
    )

    console.flush()
    result = json.loads(buffer.getvalue().decode("cp1252"))
    assert result["content"]["title"] == "Δ 预算"


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
        "workflow_kits": len(COURSES),
        "localized_kits": len(LOCALIZED)
        + sum(
            len(
                json.loads(
                    (
                        ROOT
                        / "scripts/course_materials/published"
                        / key
                        / "course.json"
                    ).read_text()
                )["locales"]
            )
            for key in RELEASE["retained"]
        ),
        "missing_translations": [],
    }


def test_compiler_removes_retired_specimens_and_rejects_stale_extra_files(tmp_path):
    kit = tmp_path / "generated-kit"
    current = kit / "files/input/invoice.xml"
    current.parent.mkdir(parents=True)
    current.write_text("current fictional source", encoding="utf-8")
    old = kit / "files/executed-starter/old-result.html"
    old.parent.mkdir()
    old.write_text("retired output specimen", encoding="utf-8")
    expected = {"course.json", "files/input/invoice.xml"}
    with pytest.raises(ValueError, match="Unreferenced generated teaching files"):
        builder._generated_files(kit, expected, check=True)
    assert old.exists()
    builder._generated_files(kit, expected)
    assert not old.parent.exists()
    assert current.read_text(encoding="utf-8") == "current fictional source"
    builder._generated_files(kit, expected, check=True)


def test_compiler_refuses_linked_generated_assets_without_touching_target(tmp_path):
    kit = tmp_path / "generated-kit"
    kit.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("preserve", encoding="utf-8")
    (kit / "linked-input").symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        builder._generated_files(kit, set())
    assert outside.read_text(encoding="utf-8") == "preserve"


def test_compiler_rejects_cross_language_file_collision_before_changing_kit(
    tmp_path, monkeypatch
):
    authoring = tmp_path / "authoring"
    write_json(
        authoring / "kits.json",
        {
            "vera/previdenza-inps": {
                "files": [
                    {
                        "source": "italian.csv",
                        "path": "files/input/periods.csv",
                        "role": "source",
                        "languages": ["it"],
                    },
                    {
                        "source": "english.csv",
                        "path": "files/input/periods.csv",
                        "role": "source",
                        "languages": ["en"],
                    },
                ]
            }
        },
    )
    write_json(
        authoring / "release_plan.json",
        {"prepared": ["vera/previdenza-inps"], "retained": {}},
    )
    kit = tmp_path / "plugins/vera/assets/courses/previdenza-inps"
    kit.mkdir(parents=True)
    existing = kit / "existing-artifact.txt"
    existing.write_text("Preserve the existing kit on invalid authoring input")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "AUTHORING", authoring)
    monkeypatch.setattr(
        builder,
        "_eligible",
        lambda product: {"previdenza-inps"} if product == "vera" else set(),
    )
    monkeypatch.setattr(
        builder,
        "_locales",
        lambda: {"vera/previdenza-inps": {lang: {} for lang in builder.LANGUAGES}},
    )
    with pytest.raises(ValueError, match="unique destinations across all languages"):
        builder.build(require_complete=False)
    assert list(kit.iterdir()) == [existing]
    assert (
        existing.read_text() == "Preserve the existing kit on invalid authoring input"
    )


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
        "inputs",
        "steps",
        "deliverables",
        "review",
        "checkpoints",
        "practice",
        "success",
        "repeat",
    }
    assert all(content.values())
    assert all(content["steps"])
    assert all(content["checkpoints"])
    destination = tmp_path / "lesson"

    library.render(workflow, language, destination)

    page = (destination / "course.html").read_text(encoding="utf-8")
    assert f"<html lang='{language}'>" in page
    assert page.count("class='lesson-step'") == 6
    assert "execution-request.json" not in page
    assert "<script" not in page
    assert "https://" not in page
    assert not (destination / "example.html").exists()
    assert (destination / "execution-request.json").is_file()


@pytest.mark.parametrize("language", builder.LANGUAGES)
def test_lucia_website_kit_remains_owned_by_lucia(language):
    library = CourseLibrary(ROOT / "plugins/lucia", builder._eligible("lucia"))
    course = library.load("presenza-digitale-studio", language)
    content = course["locales"][language]
    assert "Lucia" in content["request"]
    assert "Vera" not in json.dumps(content)
    assert course["product"] == "lucia"


def test_precomputed_output_cannot_be_packaged_as_a_teaching_input(isolated):
    root, _, _ = isolated
    alter_course(isolated, lambda course: course["files"][0].update(role="output"))
    with pytest.raises(CourseError, match="source and practice files"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "it")


def test_kit_cannot_omit_the_learners_practice_inputs(isolated):
    root, _, _ = isolated
    alter_course(
        isolated,
        lambda course: course.update(
            files=[f for f in course["files"] if f["role"] == "source"]
        ),
    )
    with pytest.raises(CourseError, match="needs source and practice"):
        CourseLibrary(root, {"variance-analysis"}).load("variance-analysis", "it")


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
