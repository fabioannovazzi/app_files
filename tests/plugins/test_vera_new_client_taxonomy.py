from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

LEGACY_COMPETING_PATHS = (
    Path("plugins/client-intake"),
    Path("plugins/client-onboarding"),
    Path("plugins/vera/skills/client-intake"),
    Path("plugins/vera/skills/client-onboarding"),
    Path("static/shared/client-intake"),
    Path("static/shared/client-onboarding"),
)

FILE_PREPARATION_SKILL = Path(
    "plugins/client-file-preparation/skills/client-file-preparation/SKILL.md"
)
RETIRED_FILE_PREPARATION_SKILL = Path(
    "plugins/client-file-preparation/skills/prepare-client-file/SKILL.md"
)

FILE_PREPARATION_GUIDES = (
    Path("plugins/client-file-preparation/README.md"),
    Path("plugins/client-file-preparation/INSTALLA_PLUGIN_CODEX.md"),
    Path("plugins/client-file-preparation/COME_USARE_LO_ZIP.md"),
    Path("plugins/client-file-preparation/references/workflow-reference.md"),
)


@pytest.mark.parametrize("relative_path", LEGACY_COMPETING_PATHS)
def test_vera_removes_competing_new_client_workflow_paths(
    relative_path: Path,
) -> None:
    assert not (ROOT / relative_path).exists()


def test_vera_uses_one_new_client_workflow_with_a_subordinate_file_engine() -> None:
    components = json.loads(
        (ROOT / "plugins" / "vera" / "components.json").read_text(encoding="utf-8")
    )["plugins"]

    assert (ROOT / "plugins" / "new-client").is_dir()
    assert (ROOT / "plugins" / "client-file-preparation").is_dir()
    assert (ROOT / "plugins" / "vera" / "skills" / "new-client").is_dir()
    assert (ROOT / "static" / "shared" / "new-client" / "index.html").is_file()
    assert "new-client" in components
    assert "client-file-preparation" in components


def test_file_preparation_exposes_one_canonical_internal_skill() -> None:
    content = (ROOT / FILE_PREPARATION_SKILL).read_text(encoding="utf-8")

    assert "\nname: client-file-preparation\n" in content
    assert not (ROOT / RETIRED_FILE_PREPARATION_SKILL).exists()


@pytest.mark.parametrize("relative_path", FILE_PREPARATION_GUIDES)
def test_file_preparation_guides_route_users_to_new_client(
    relative_path: Path,
) -> None:
    content = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "New Client" in content
    assert "Usa il plugin Client File Preparation" not in content
    assert "Installa o abilita `Client File Preparation`" not in content


def test_new_client_schema_and_provenance_use_workflow_neutral_names() -> None:
    new_client_root = ROOT / "plugins" / "new-client"
    schema = json.loads(
        (new_client_root / "schemas" / "new_client_input.schema.json").read_text(
            encoding="utf-8"
        )
    )
    provenance = json.loads(
        (new_client_root / "references" / "research-provenance.json").read_text(
            encoding="utf-8"
        )
    )

    assert schema["title"] == "Vera New Client Input"
    assert {entry["reference_id"] for entry in provenance["entries"]} == {
        "external_mandate_material",
        "external_fee_schedule_2026",
    }
    assert "francesco" not in json.dumps(provenance).casefold()


def test_vera_current_surfaces_do_not_publish_the_competing_names() -> None:
    current_paths = (
        ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json",
        ROOT / "plugins" / "vera" / ".mcp.json",
        ROOT / "plugins" / "vera" / "components.json",
        ROOT / "plugins" / "vera" / "README.md",
        ROOT / "plugins" / "vera" / "skills" / "vera" / "SKILL.md",
        ROOT / "plugins" / "vera" / "skills" / "new-client" / "SKILL.md",
        ROOT / "plugins" / "new-client" / ".codex-plugin" / "plugin.json",
        ROOT / "plugins" / "new-client" / "README.md",
        ROOT / "plugins" / "new-client" / "skills" / "new-client" / "SKILL.md",
        ROOT / "plugins" / "client-file-preparation" / ".codex-plugin" / "plugin.json",
        ROOT / "plugins" / "client-file-preparation" / "README.md",
        ROOT / "modules" / "pdp" / "api.py",
        ROOT / "static" / "shared" / "vera" / "index.html",
        ROOT / "static" / "shared" / "new-client" / "index.html",
        ROOT / "static" / "shared" / "new-client" / "geneva.html",
        ROOT / "static" / "shared" / "new-client" / "zurich.html",
        ROOT / "static" / "shared" / "new-client" / "uk.html",
        ROOT / "static" / "shared" / "new-client" / "jurisdiction-pages.js",
        ROOT / "static" / "shared" / "video-library.js",
        ROOT / "static" / "shared" / "vera-scope.js",
    )

    for path in current_paths:
        content = path.read_text(encoding="utf-8").casefold()
        assert "client-intake" not in content, path
        assert "client-onboarding" not in content, path
        assert "client intake" not in content, path
        assert "client onboarding" not in content, path
