"""The introductory guide must launch the right host and reuse real courses."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = "skills/learn-with-vera/references/"


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links = []
        self.requests = {}
        self.current = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"a", "link", "script"}:
            self.links.append(attrs.get("href", attrs.get("src")))
        if tag == "textarea":
            self.current = attrs["id"]
            self.requests[self.current] = ""

    def handle_endtag(self, tag):
        if tag == "textarea":
            self.current = None

    def handle_data(self, data):
        if self.current:
            self.requests[self.current] += data


def test_introduction_links_resolve_and_preserve_exact_host_requests(
    tmp_path, monkeypatch
):
    monkeypatch.syspath_prepend(str(ROOT / "scripts/course_materials"))
    from get_started import render_introduction

    section = render_introduction(ROOT, tmp_path)
    copy = json.loads(
        (ROOT / "plugins/vera" / REFERENCE / "get-started.json").read_text()
    )
    pages = [link for link in Page(section).links if not link.startswith("#")]
    assert len(pages) == 5
    for link in pages:
        target = tmp_path / link
        language = target.parent.name
        page = Page(target.read_text())
        assert page.requests == {
            "course-start-request": copy[language]["codex_prompt"],
            "cowork-start-request": copy[language]["cowork_prompt"],
        }
        for asset in page.links:
            if asset.endswith((".css", ".js")):
                assert (target.parent / asset).resolve().parent == tmp_path.resolve()
    # This orientation must not become a fabricated executable workflow.
    catalog = json.loads((ROOT / "plugins/vera/assets/courses/index.json").read_text())
    assert "get-started" not in catalog["courses"]
    assert "journal-bank-reconciliation" in catalog["courses"]


@pytest.mark.parametrize("surface", ["plugin", "chatgpt-upload", "claude-plugin"])
def test_installed_introduction_references_are_complete(surface):
    prefix = "vera-codex-plugin/plugins/vera/" if surface == "plugin" else ""
    with ZipFile(ROOT / f"plugin_packages/vera/vera-{surface}.zip") as archive:
        for name in ("get-started.md", "get-started.json"):
            assert (
                archive.read(prefix + REFERENCE + name)
                == (ROOT / "plugins/vera" / REFERENCE / name).read_bytes()
            )
        skill = archive.read(prefix + "skills/learn-with-vera/SKILL.md").decode()
        assert "references/get-started.md" in skill
        if surface == "claude-plugin":
            assert "written single-conversation contract" in skill
            assert prefix + "scripts/local_teaching.py" not in archive.namelist()


def test_catalogue_offers_introduction_before_workflow_selection():
    catalogue = (ROOT / "static/shared/courses/index.html").read_text()
    assert catalogue.index('id="inizia-con-vera"') < catalogue.index(
        'id="come-iniziare"'
    )
    assert catalogue.index('id="inizia-con-vera"') < catalogue.index('id="vera"')
    for link in Page(catalogue).links:
        if link and "get-started/" in link:
            assert (ROOT / "static/shared/courses" / link).is_file()
