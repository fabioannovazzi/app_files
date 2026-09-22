"""Verify approved skill identities in the artifacts users actually install."""

from __future__ import annotations

import re
from pathlib import Path
from posixpath import dirname, normpath
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
RENAMES = [
    ("vera", "prompt-optimizer", "legal-tax-answer-planner"),
    ("lucia", "prompt-optimizer", "legal-tax-answer-planner"),
    ("vera", "deep-research-validator", "legal-tax-answer-review"),
    ("lucia", "deep-research-validator", "legal-tax-answer-review"),
    ("vera", "check-entries", "vouching"),
    ("vera", "bilancio-xbrl-it", "bilancio-oic"),
    ("vera", "passive-invoice-audit", "purchase-invoice-review"),
    ("vera", "report-builder", "financial-report-builder"),
    ("clara", "interview", "hosted-interview"),
]


@pytest.mark.parametrize(("product", "retired", "skill"), RENAMES)
@pytest.mark.parametrize("host", ["codex", "chatgpt", "cowork"])
def test_installed_skill_identity_matches_approved_name(
    product: str, retired: str, skill: str, host: str
) -> None:
    archives = {
        "codex": (
            f"{product}-plugin.zip",
            f"{product}-codex-plugin/plugins/{product}/",
        ),
        "chatgpt": (f"{product}-chatgpt-upload.zip", ""),
        "cowork": (f"{product}-claude-plugin.zip", ""),
    }
    filename, prefix = archives[host]
    old_path = f"{prefix}skills/{retired}/SKILL.md"
    new_path = f"{prefix}skills/{skill}/SKILL.md"

    with ZipFile(ROOT / "plugin_packages" / product / filename) as archive:
        assert old_path not in archive.namelist()
        if product == "clara" and host == "cowork":
            # Hosted participant interviews remain unsupported on this host.
            assert new_path not in archive.namelist()
            return
        text = archive.read(new_path).decode("utf-8")

    assert f"\nname: {skill}\n" in text
    assert not (ROOT / "plugins" / product / "skills" / retired).exists()


@pytest.mark.parametrize("product", ["vera", "lucia"])
@pytest.mark.parametrize("host", ["codex", "chatgpt", "cowork"])
def test_packaged_opposing_opinion_scope_reference_resolves(
    product: str, host: str
) -> None:
    """The installed opposing-opinion instructions must resolve their scope file."""
    archives = {
        "codex": (
            f"{product}-plugin.zip",
            f"{product}-codex-plugin/plugins/{product}/",
        ),
        "chatgpt": (f"{product}-chatgpt-upload.zip", ""),
        "cowork": (f"{product}-claude-plugin.zip", ""),
    }
    filename, prefix = archives[host]
    skill_path = (
        f"{prefix}modules/deep-research-validator/skills/adversarial-opinion/SKILL.md"
    )
    with ZipFile(ROOT / "plugin_packages" / product / filename) as archive:
        instruction = archive.read(skill_path).decode("utf-8")

        reference = re.search(r"`([^`]+/adversarial-scope\.md)`", instruction)

        assert reference is not None
        target = normpath(f"{dirname(skill_path)}/{reference.group(1)}")
        assert target in archive.namelist()
        assert archive.read(target).strip()
