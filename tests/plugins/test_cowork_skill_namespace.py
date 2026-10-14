"""The actual Claude release must enforce ownership for every custom skill."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.cowork_skill_names import (
    project_skill_names,
    validate_skill_names,
    validate_skill_zip,
)


def skill(name: str, body: str = "Execute the reviewed method.\n") -> bytes:
    return f"---\nname: {name}\ndescription: Synthetic workflow\n---\n{body}".encode()


def test_new_skill_gets_namespace_without_a_reserved_name_list():
    original = {"skills/future-workflow/SKILL.md": skill("future-workflow")}

    projected = project_skill_names(original)

    assert projected == {
        "skills/mparanza-future-workflow/SKILL.md": skill("mparanza-future-workflow")
    }
    assert original == {"skills/future-workflow/SKILL.md": skill("future-workflow")}
    assert project_skill_names(projected) == projected


def test_skill_paths_move_without_renaming_component_or_workflow_ids():
    original = {
        "skills/radar/SKILL.md": skill(
            "radar", "Read ../../modules/radar/skills/radar/SKILL.md.\n"
        ),
        "modules/radar/skills/radar/SKILL.md": skill("radar"),
        "scripts/helper.py": b'path = root / "skills" / "radar" / "SKILL.md"\n',
        "registry.json": b'{"workflow": "radar", "skill": "skills/radar/SKILL.md"}',
    }

    projected = project_skill_names(original)

    assert (
        b"../../modules/radar/skills/mparanza-radar/SKILL.md"
        in projected["skills/mparanza-radar/SKILL.md"]
    )
    assert "modules/radar/skills/mparanza-radar/SKILL.md" in projected
    assert b'"skills" / "mparanza-radar"' in projected["scripts/helper.py"]
    assert (
        projected["registry.json"]
        == b'{"workflow": "radar", "skill": "skills/mparanza-radar/SKILL.md"}'
    )


def test_relative_component_directory_and_native_skill_reference_are_preserved():
    original = {
        "modules/radar/skills/radar/SKILL.md": skill(
            "radar",
            "Read ../../scripts/run.py. Native `deep-research` is provided by the host.\n",
        ),
        "modules/radar/scripts/run.py": b"# Reviewed runtime\n",
    }

    projected = project_skill_names(original)

    assert (
        b"../../scripts/run.py"
        in projected["modules/radar/skills/mparanza-radar/SKILL.md"]
    )
    assert (
        b"Native `deep-research`"
        in projected["modules/radar/skills/mparanza-radar/SKILL.md"]
    )


def test_registered_internal_engine_instruction_uses_renamed_skill():
    original = {
        "components.json": json.dumps(
            {
                "plugins": ["router", "input-engine"],
                "workflow_roles": {
                    "router": {"internal_engines": ["input-engine"]},
                    "input-engine": {"kind": "internal_engine"},
                },
            }
        ).encode(),
        "skills/router/SKILL.md": skill(
            "router",
            "From the engine root read skills/input/SKILL.md. Keep modules/<module>/scripts/run.py and ./scripts/run.py.\n",
        ),
        "modules/input-engine/skills/input/SKILL.md": skill("input"),
    }

    projected = project_skill_names(original)

    instruction = projected["skills/mparanza-router/SKILL.md"]
    assert b"skills/mparanza-input/SKILL.md" in instruction
    assert b"modules/<module>/scripts/run.py" in instruction
    assert b"./scripts/run.py" in instruction
    validate_skill_names(projected)


def test_retired_unprefixed_link_to_owned_skill_is_rejected():
    entries = {
        "skills/mparanza-radar/SKILL.md": skill(
            "mparanza-radar", "Read ../radar/SKILL.md.\n"
        )
    }

    with pytest.raises(ValueError, match="broken skill reference"):
        validate_skill_names(entries)


def test_workflow_ids_in_prose_stay_canonical_while_explicit_invocations_change():
    original = {
        "skills/radar/SKILL.md": skill(
            "radar", "Run workflow `radar`; invoke `/vera:radar` or `/radar`.\n"
        )
    }

    projected = project_skill_names(original)

    text = projected["skills/mparanza-radar/SKILL.md"]
    assert b"workflow `radar`" in text
    assert b"`/vera:mparanza-radar`" in text
    assert b"`/mparanza-radar`" in text


def test_cross_product_router_is_external_but_own_missing_router_is_rejected():
    entries = {
        ".claude-plugin/plugin.json": b'{"name": "lucia"}',
        "skills/mparanza-review/SKILL.md": skill(
            "mparanza-review",
            "For the Vera product read skills/mparanza-vera/SKILL.md.\n",
        ),
    }

    validate_skill_names(entries)

    entries["skills/mparanza-review/SKILL.md"] = skill(
        "mparanza-review", "Read skills/mparanza-lucia/SKILL.md.\n"
    )
    with pytest.raises(ValueError, match="broken skill reference"):
        validate_skill_names(entries)


@pytest.mark.parametrize(
    "name",
    [
        "mparanza-anthropic-tools",
        "mparanza-claude-tools",
        "mparanza-Bad",
        "mparanza-bad_name",
        "mparanza-" + "x" * 56,
    ],
)
def test_invalid_or_provider_reserved_name_is_rejected(name: str):
    with pytest.raises(ValueError, match="invalid skill name|reserved word"):
        validate_skill_names({f"skills/{name}/SKILL.md": skill(name)})


def test_mismatched_skill_folder_is_rejected():
    with pytest.raises(ValueError, match="differs from its directory"):
        validate_skill_names(
            {"skills/mparanza-radar/SKILL.md": skill("mparanza-other")}
        )


def test_preexisting_prefixed_skill_cannot_be_overwritten():
    with pytest.raises(ValueError, match="projection collides"):
        project_skill_names(
            {
                "skills/radar/SKILL.md": skill("radar"),
                "skills/mparanza-radar/SKILL.md": skill("mparanza-radar"),
            }
        )


def test_broken_explicit_skill_link_is_rejected():
    with pytest.raises(ValueError, match="broken skill reference"):
        validate_skill_names(
            {
                "skills/mparanza-radar/SKILL.md": skill(
                    "mparanza-radar", "Read ../mparanza-missing/SKILL.md.\n"
                )
            }
        )


def test_finished_zip_rejects_unprefixed_skill_added_after_projection(tmp_path: Path):
    path = tmp_path / "candidate.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("skills/mparanza-radar/SKILL.md", skill("mparanza-radar"))
        archive.writestr("skills/new-unprefixed/SKILL.md", skill("new-unprefixed"))

    with pytest.raises(ValueError, match="must start with mparanza-"):
        validate_skill_zip(path)


def test_finished_zip_rejects_duplicate_member(tmp_path: Path):
    path = tmp_path / "duplicate.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("skills/mparanza-radar/SKILL.md", skill("mparanza-radar"))
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("skills/mparanza-radar/SKILL.md", skill("mparanza-radar"))

    with pytest.raises(ValueError, match="duplicate ZIP member"):
        validate_skill_zip(path)


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_all_installed_product_skills_use_owned_names(product: str):
    root = Path(__file__).resolve().parents[2]
    validate_skill_zip(
        root / "plugin_packages" / product / f"{product}-claude-plugin.zip"
    )
