from __future__ import annotations

import posixpath
import re
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "filename",
    ["lucia-plugin.zip", "lucia-chatgpt-upload.zip", "lucia-claude-plugin.zip"],
)
def test_packaged_lucia_workflow_references_resolve(filename: str) -> None:
    with ZipFile(ROOT / "plugin_packages" / "lucia" / filename) as archive:
        names = archive.namelist()
        for workflow in ("comunicazione-professionale", "presenza-digitale-studio"):
            wrapper = min(
                (
                    name
                    for name in names
                    if name.endswith(f"skills/{workflow}/SKILL.md")
                ),
                key=len,
            )
            text = " ".join(archive.read(wrapper).decode().split())
            assert (
                "`Plugin Improvement Feedback` section in `../lucia/SKILL.md`" in text
            )
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(wrapper), "../lucia/SKILL.md")
            )
            assert "## Plugin Improvement Feedback" in archive.read(target).decode()

        skill = next(
            name
            for name in names
            if name.endswith(
                "modules/apertura-pratica/skills/apertura-pratica/SKILL.md"
            )
        )
        reference = re.search(
            r"`([^`]*references/source-registry.json)`", archive.read(skill).decode()
        )
        assert reference is not None
        target = posixpath.normpath(
            posixpath.join(posixpath.dirname(skill), reference.group(1))
        )
        assert target in names
