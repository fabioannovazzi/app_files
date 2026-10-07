from __future__ import annotations

import hashlib
import json
import posixpath
import re
from pathlib import Path
from zipfile import ZipFile

import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]
VERA = ROOT / "plugins/vera"
REFERENCE = "skills/vera/references/connected-studio-knowledge.md"
MARKER = "<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->"
PROFESSIONAL_SKILLS = {
    path.parent.name for path in (VERA / "skills").glob("*/SKILL.md")
} - {"learn-with-vera", "privacy-surface-review", "organizzazione-lavoro"}


def _package_entries(filename: str) -> dict[str, bytes]:
    """Read the built host package using its actual product-root prefix."""
    with ZipFile(ROOT / "plugin_packages/vera" / filename) as archive:
        names = archive.namelist()
        manifests = [
            name
            for name in names
            if name.endswith(
                (".codex-plugin/plugin.json", ".claude-plugin/plugin.json")
            )
            and json.loads(archive.read(name))["name"] == "vera"
        ]
        assert len(manifests) == 1
        prefix = (
            manifests[0]
            .removesuffix(".codex-plugin/plugin.json")
            .removesuffix(".claude-plugin/plugin.json")
        )
        return {
            name.removeprefix(prefix): archive.read(name)
            for name in names
            if not name.endswith("/")
        }


@pytest.mark.parametrize(
    "filename",
    ["vera-plugin.zip", "vera-chatgpt-upload.zip", "vera-claude-plugin.zip"],
)
def test_host_packages_retain_resolvable_direct_knowledge_contracts(
    filename: str,
) -> None:
    entries = _package_entries(filename)

    assert REFERENCE in entries
    for skill in PROFESSIONAL_SKILLS:
        name = f"skills/{skill}/SKILL.md"
        # A host may deliberately omit a desktop-only professional function.
        if name not in entries:
            continue
        text = entries[name].decode()
        assert text.count(MARKER) == 1, (filename, skill)
        block = text.split(MARKER, 1)[1].split(
            "<!-- VERA_CONNECTED_KNOWLEDGE_END -->", 1
        )[0]
        links = re.findall(r"`([^`]+\.md)`", block)
        assert len(links) == 1
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), links[0]))
        assert target == REFERENCE
        assert target in entries
    # Shared components also serve other products: the new Vera wrapper policy
    # must never leak into their executable contracts.
    for name, content in entries.items():
        if name.startswith("modules/") and name.endswith("/SKILL.md"):
            assert MARKER.encode() not in content, (filename, name)


def test_compiled_vera_lessons_pin_shared_knowledge_source() -> None:
    expected_digest = hashlib.sha256((VERA / REFERENCE).read_bytes()).hexdigest()
    courses = list((VERA / "assets/courses").glob("*/course.json"))
    assert courses
    for path in courses:
        course = json.loads(path.read_text())
        matches = [
            source for source in course["sources"] if source["path"] == REFERENCE
        ]
        assert len(matches) == 1, path
        assert matches[0]["sha256"] == expected_digest


def test_repository_boundary_is_registered_for_each_professional_workstream() -> None:
    manifests = list((VERA / "privacy/workstreams").glob("*.json"))
    assert manifests
    for path in manifests:
        manifest = json.loads(path.read_text())
        if manifest["role"] != "workflow":
            continue
        boundaries = [
            boundary
            for boundary in manifest["external_boundaries"]
            if boundary["id"] == "host-connected-studio-knowledge"
        ]
        assert len(boundaries) == 1, path
        assert boundaries[0]["kind"] == "external_connector"
        assert boundaries[0]["optional"] is True
        assert boundaries[0]["requires_confirmation"] is True
        assert f"plugins/vera/{REFERENCE}" in manifest["governed_repository_paths"]


@pytest.mark.parametrize(
    "filename",
    ["vera-plugin.zip", "vera-chatgpt-upload.zip", "vera-claude-plugin.zip"],
)
def test_studio_work_service_uses_register_and_host_calendar_contract(
    filename: str,
) -> None:
    """The operational service does not acquire a workpaper repository contract."""
    entries = _package_entries(filename)
    text = entries["skills/organizzazione-lavoro/SKILL.md"].decode()
    assert "vera_studio_work_*" in text
    assert "connected calendar plugin" in text
    assert MARKER not in text
    assert "Never manufacture evidence" in text
    assert "privacy/services/studio-work.json" in entries
