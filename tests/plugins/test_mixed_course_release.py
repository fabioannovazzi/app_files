"""Preserve published lessons and check public downloads without session data."""

from __future__ import annotations

import hashlib
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from tests.plugins.test_prepared_courses import ROOT, builder

sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))
from courseware.library import CourseLibrary

PLAN = json.loads((ROOT / "scripts/course_materials/release_plan.json").read_text())
RETAINED = [
    (product, workflow, language)
    for key in PLAN["retained"]
    for product, workflow in [key.split("/")]
    for language in json.loads(
        (ROOT / f"scripts/course_materials/published/{key}/course.json").read_text()
    )["supported_languages"]
]


@pytest.mark.parametrize("product,workflow,language", RETAINED)
def test_retained_published_lesson_preserves_content_and_renders(
    tmp_path, monkeypatch, product, workflow, language
):
    # The suite removes vendor paths between tests; restore for lazy imports.
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    key = f"{product}/{workflow}"
    original_path = ROOT / f"scripts/course_materials/published/{key}/course.json"
    original = json.loads(original_path.read_text())
    assert (
        hashlib.sha256(original_path.read_bytes()).hexdigest()
        == PLAN["retained"][key]["course_sha256"]
    )
    library = CourseLibrary(ROOT / "plugins" / product, builder._eligible(product))
    current = library.load(workflow, language)
    original.pop("sources")
    current.pop("sources")
    assert current.pop("retained_from") == PLAN["retained"][key]
    assert current == original
    destination = tmp_path / "lesson"
    library.render(workflow, language, destination)
    assert (destination / "course.html").is_file()
    assert (destination / "teacher.md").is_file()
    assert (destination / "input.csv").is_file()
    assert not (destination / "execution-request.json").exists()


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.ids.update([attributes["id"]] if "id" in attributes else [])
        self.targets.extend(
            attributes[key] for key in ("href", "src") if attributes.get(key)
        )


def test_public_catalogue_links_every_language_and_contains_no_local_requests():
    directory = ROOT / "static/shared/courses"
    assert len(list(directory.glob("*/*/*/course.html"))) == 205
    assert not list(directory.rglob("execution-request.json"))
    documents = {}
    for path in directory.rglob("*.html"):
        parser = Links()
        text = path.read_text()
        assert "/private/tmp/" not in text
        assert "/Users/" not in text
        assert "file://" not in text
        parser.feed(text)
        documents[path.resolve()] = parser
    for path, parser in documents.items():
        for target in parser.targets:
            link = urlsplit(target)
            if link.scheme or link.netloc:
                continue
            destination = (
                (path.parent / unquote(link.path)).resolve() if link.path else path
            )
            assert destination.is_relative_to(directory.resolve()), (path, target)
            assert destination.is_file(), (path, target)
            if link.fragment and destination in documents:
                assert unquote(link.fragment) in documents[destination].ids, (
                    path,
                    target,
                )
