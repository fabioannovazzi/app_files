"""Verify installed bytes and actual cross-surface teaching boundaries."""

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("product", ["clara", "lucia"])
@pytest.mark.parametrize("surface", ["plugin", "chatgpt-upload"])
def test_installable_archive_runs_without_repository_fallback(
    product, surface, tmp_path
):
    with ZipFile(
        ROOT / f"plugin_packages/{product}/{product}-{surface}.zip"
    ) as archive:
        archive.extractall(tmp_path / "installed")
    root = tmp_path / "installed"
    if surface == "plugin":
        root /= f"{product}-codex-plugin/plugins/{product}"
    state = tmp_path / "local-profile"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/local_onboarding.py"),
            "begin",
            "--state-root",
            str(state),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["product"] == product
    shared = root / "vendor/modules/desktop_teaching"
    assert (shared / "onboarding.py").read_bytes() == (
        ROOT / "plugins/_shared/vendor/modules/desktop_teaching/onboarding.py"
    ).read_bytes()
    skill = root / f"skills/learn-with-{product}/SKILL.md"
    assert "one bounded step at a time" in skill.read_text(encoding="utf-8")
    assert (root / f"skills/{product}/references/local-onboarding.md").exists()
    # The current specialist contract must survive Marketplace projection.
    specialist = "reporting-engine" if product == "clara" else "apertura-pratica"
    text = (root / f"skills/{specialist}/SKILL.md").read_text(encoding="utf-8")
    assert "local-onboarding.md" in text
    if product == "clara":
        assert "budget_report.py" in text


@pytest.mark.parametrize("product", ["clara", "lucia"])
def test_cowork_written_teaching_has_no_native_onboarding_gate(product):
    with ZipFile(
        ROOT / f"plugin_packages/{product}/{product}-claude-plugin.zip"
    ) as archive:
        assert any(
            name.endswith(f"skills/learn-with-{product}/SKILL.md")
            for name in archive.namelist()
        )
        for name in archive.namelist():
            assert not any(
                part in name
                for part in (
                    "local_onboarding",
                    "local_teaching",
                    "desktop_teaching",
                    "assets/onboarding",
                )
            )
            if name.endswith("SKILL.md"):
                text = archive.read(name).decode()
                assert "OPENAI_ONBOARDING" not in text
                assert "local-onboarding.md" not in text


@pytest.mark.parametrize("product", ["clara", "lucia"])
def test_five_language_page_explains_visible_pair_and_natural_lesson(product):
    text = (ROOT / "static/shared/product-function-pages.js").read_text(
        encoding="utf-8"
    )
    offset = text.index(f'"learn-with-{product}": ') + len(f'"learn-with-{product}": ')
    entry, _ = json.JSONDecoder().raw_decode(text[offset:])
    assert set(entry["copy"]) == {"it", "en", "fr", "de", "es"}
    assert entry["product"] == product.title()
    assert "3–4" in entry["copy"]["it"]["work"]
    assert "due chat" in entry["copy"]["it"]["useWhen"]
    assert entry["copy"]["it"]["professionalRoleTitle"] == "Tu chiedi e provi"
    assert "Mparanza" in entry["copy"]["it"]["modelData"]
    assert f"../learn-with-{product}/index.html" in (
        ROOT / f"static/shared/{product}/index.html"
    ).read_text(encoding="utf-8")
