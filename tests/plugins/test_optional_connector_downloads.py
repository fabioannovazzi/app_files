"""Keep the optional download independent and discoverable from each Vera ZIP."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from bs4 import BeautifulSoup

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]
GUIDE = "skills/vera/references/optional-integrations.md"
DOWNLOAD = (
    ROOT / "static/shared/vera-integrazioni/downloads/anonymization-connectors.zip"
)


@pytest.mark.parametrize(
    "path,prefix",
    [
        ("plugin_packages/vera/vera-plugin.zip", "vera-codex-plugin/plugins/vera/"),
        ("plugin_packages/vera/vera-chatgpt-upload.zip", ""),
        ("static/shared/vera/downloads/vera-cowork-plugin.zip", ""),
        ("static/shared/vera/downloads/vera-antigravity-plugin.zip", "vera/"),
    ],
)
def test_vera_host_zip_includes_optional_guidance_without_installing_engines(
    path, prefix
):
    with ZipFile(ROOT / path) as archive:
        guide = archive.read(prefix + GUIDE).decode()
        skill = archive.read(prefix + "skills/vera/SKILL.md").decode()
        names = archive.namelist()
    assert "anonymization-connectors.zip" in guide
    assert "Codex" in guide and "Cowork" in guide and "Antigravity" in guide
    assert "| Codex | `codex-mcp.toml` |" in guide
    assert "| Claude Cowork | `cowork-connector.zip` |" in guide
    assert "| Google Antigravity | `antigravity-mcp.json` |" in guide
    assert "optional-integrations.md" in skill
    assert "No Second Brain installer" in guide
    assert not any("mparanza_privacy_filter" in name for name in names)


def test_connector_download_is_reproducible_and_excludes_unrelated_local_files(
    tmp_path, monkeypatch
):
    import shutil

    spec = importlib.util.spec_from_file_location(
        "connector_download_builder", ROOT / "scripts/build_anonymization_connectors.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    clean = builder.build_bytes()
    copied = tmp_path / "connector"
    shutil.copytree(
        builder.SOURCE,
        copied,
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )
    (copied / ".env").write_text("PRIVATE=not_for_distribution")
    (copied / "client-original.txt").write_text("Private client document")
    (copied / "model").mkdir()
    (copied / "model/weights.bin").write_bytes(b"Do not bundle models")
    monkeypatch.setattr(builder, "SOURCE", copied)

    actual = builder.build_bytes()

    assert actual == clean == DOWNLOAD.read_bytes()


@pytest.mark.parametrize("lang", ["it", "en", "fr", "de", "es"])
def test_download_guide_and_second_brain_hosts_are_localized_with_data_section_last(
    lang,
):
    page = (ROOT / "static/shared/vera-integrazioni/index.html").read_text()
    start = page.index("{", page.index("const copy ="))
    copy, _ = json.JSONDecoder().raw_decode(page[start:])
    soup = BeautifulSoup(page, "html.parser")

    assert soup.select_one('a[download][href="downloads/anonymization-connectors.zip"]')
    assert soup.select_one('#antigravity [data-i18n="antigravity1"]')
    assert all(
        element["data-i18n"] in copy[lang] for element in soup.select("[data-i18n]")
    )
    assert "Cowork" in copy[lang]["connector.cowork"]
    assert "Antigravity" in copy[lang]["connector.antigravity"]
    assert soup.select("main > section")[-1].get("id") == "model-data"
