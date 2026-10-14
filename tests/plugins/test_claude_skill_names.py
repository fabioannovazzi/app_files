from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _builder():
    spec = importlib.util.spec_from_file_location(
        "claude_skill_names_builder", ROOT / "scripts/build_claude_plugin_zip.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("product", ["vera", "lucia"])
def test_claude_release_research_skill_avoids_anthropic_reserved_name(product):
    builder = _builder()
    _, packages = builder.load_configuration()
    package = next(item for item in packages if item.plugin == product)

    entries = builder.claude_package_entries(package)

    public = "skills/mparanza-deep-research/SKILL.md"
    shared = "modules/deep-research-validator/skills/" "mparanza-deep-research/SKILL.md"
    assert public in entries
    assert shared in entries
    assert b"name: mparanza-deep-research\n" in entries[public]
    assert b"name: mparanza-deep-research\n" in entries[shared]
    assert "skills/deep-research/SKILL.md" not in entries
    assert (
        b"../mparanza-deep-research/SKILL.md"
        in entries["skills/quesito-legale-fiscale/SKILL.md"]
    )
    course = json.loads(entries["assets/courses/quesito-legale-fiscale/course.json"])
    course_sources = {source["path"]: source["sha256"] for source in course["sources"]}
    assert course_sources[shared] == hashlib.sha256(entries[shared]).hexdigest()
    loop = "modules/deep-research-validator/skills/mparanza-deep-research/references/research-loop.md"
    assert course_sources[loop] == hashlib.sha256(entries[loop]).hexdigest()


@pytest.mark.parametrize(
    "name", ["deep-research", "'deep-research'", '"deep-research"']
)
def test_skill_name_projection_preserves_method_and_updates_relative_references(name):
    builder = _builder()
    original = {
        "skills/deep-research/SKILL.md": (
            f"---\nname: {name}\ndescription: Fixture\n---\n"
            "Read modules/deep-research-validator/skills/deep-research/SKILL.md.\n"
        ).encode(),
        "modules/deep-research-validator/skills/deep-research/SKILL.md": (
            f"---\nname: {name}\ndescription: Shared method\n---\n"
            "Keep the deep-research-validator workflow and its research method.\n"
        ).encode(),
        "skills/legal-tax-answer-review/SKILL.md": (
            b"---\nname: legal-tax-answer-review\ndescription: Review\n---\n"
            b"Read ../deep-research/SKILL.md.\n"
        ),
        "registry.json": json.dumps(
            {"skills": ["skills/deep-research/SKILL.md"]}
        ).encode(),
    }

    projected = builder.project_cowork_skill_names(original)

    assert (
        b"name: mparanza-deep-research\n"
        in projected["skills/mparanza-deep-research/SKILL.md"]
    )
    assert b"Keep the deep-research-validator workflow and its research method." in (
        projected[
            "modules/deep-research-validator/skills/mparanza-deep-research/SKILL.md"
        ]
    )
    assert (
        b"../mparanza-deep-research/SKILL.md"
        in projected["skills/legal-tax-answer-review/SKILL.md"]
    )
    assert json.loads(projected["registry.json"]) == {
        "skills": ["skills/mparanza-deep-research/SKILL.md"]
    }
    assert "skills/deep-research/SKILL.md" in original
    assert builder.project_cowork_skill_names(projected) == projected


def test_skill_name_projection_rejects_conflicting_alias_directory():
    builder = _builder()
    original = {
        "skills/deep-research/SKILL.md": (
            b"---\nname: deep-research\ndescription: Fixture\n---\nResearch.\n"
        ),
        "skills/mparanza-deep-research/SKILL.md": (
            b"---\nname: mparanza-deep-research\ndescription: Other\n---\nOther.\n"
        ),
    }

    with pytest.raises(ValueError, match="skill name projection collides"):
        builder.project_cowork_skill_names(original)


def test_clara_release_contains_no_anthropic_reserved_research_skill():
    builder = _builder()
    _, packages = builder.load_configuration()
    package = next(item for item in packages if item.plugin == "clara")

    entries = builder.claude_package_entries(package)

    assert "skills/deep-research/SKILL.md" not in entries
    assert all(
        b"\nname: deep-research\n" not in content
        for name, content in entries.items()
        if name.endswith("/SKILL.md")
    )


def test_unbundled_native_research_reference_is_not_renamed():
    builder = _builder()
    original = {
        "skills/other/SKILL.md": (
            b"---\nname: other\ndescription: Fixture\n---\n"
            b"The host may provide its own `deep-research` skill.\n"
        )
    }

    projected = builder.project_cowork_skill_names(original)

    assert projected == original
