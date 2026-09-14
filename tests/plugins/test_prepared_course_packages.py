"""Exercise the actual native archives and the deliberate Cowork omission."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("surface", ["plugin", "chatgpt-upload"])
def test_native_archive_can_load_every_own_course_without_repository_fallback(
    tmp_path, product, surface
):
    with ZipFile(
        ROOT / f"plugin_packages/{product}/{product}-{surface}.zip"
    ) as archive:
        archive.extractall(tmp_path / "installed")
    root = tmp_path / "installed"
    if surface == "plugin":
        root /= f"{product}-codex-plugin/plugins/{product}"
    script = """
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / 'vendor/modules'))
from courseware.library import CourseLibrary
index = json.loads((root / 'assets/courses/index.json').read_text(encoding="utf-8"))
library = CourseLibrary(root, set(index['courses']))
count = 0
for workflow, entry in index['courses'].items():
    for language in entry['languages']:
        library.load(workflow, language)
        count += 1
print(json.dumps({'workflows': len(index['courses']), 'locales': count}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(root)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert (
        json.loads(result.stdout)
        == {
            "vera": {"workflows": 32, "locales": 143},
            "clara": {"workflows": 12, "locales": 57},
            "lucia": {"workflows": 4, "locales": 20},
        }[product]
    )
    # Execute the actual thin CLI too: its eligible catalog must not come from
    # the course index or a guessed package root.
    result = subprocess.run(
        [sys.executable, str(root / "scripts/local_courses.py"), "list"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    catalog = json.loads(result.stdout)
    assert len(catalog) == {"vera": 32, "clara": 12, "lucia": 4}[product]
    assert (root / "vendor/modules/courseware/library.py").read_bytes() == (
        ROOT / "plugins/_shared/vendor/modules/courseware/library.py"
    ).read_bytes()
    assert "Prepared teaching kits" in (
        root / f"skills/learn-with-{product}/SKILL.md"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_cowork_archive_has_no_native_course_library(product):
    with ZipFile(
        ROOT / f"plugin_packages/{product}/{product}-claude-plugin.zip"
    ) as archive:
        names = archive.namelist()
    assert not any(
        part in name
        for name in names
        for part in (
            "courseware/",
            "assets/courses/",
            "local_courses.py",
            "learn-with-",
        )
    )
