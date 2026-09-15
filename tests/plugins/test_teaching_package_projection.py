"""Preserve reviewed source identity across the existing upload projection."""

from __future__ import annotations

import hashlib
import json
from types import ModuleType
from typing import Any

import pytest

from tests.plugins.test_codex_plugin_packages import load_builder

__all__: list[str] = []


def _encoded(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _case(
    project: bool = True,
) -> tuple[ModuleType, dict[str, bytes], dict[str, bytes], str]:
    builder = load_builder()
    prefix = "package/plugins/clara/"
    runtime = (
        "## ChatGPT and Codex Runtime\n\nUse the available host tools.\n\n"
        if project
        else ""
    )
    source = (
        "---\nname: sample\ndescription: Prepare a report\n---\n\n"
        "# Prepare a report\n\n"
        + runtime
        + "## Workflow\n\nInspect the supplied data.\n"
    ).encode()
    course = _encoded(
        {
            "workflow": "sample",
            "lessons": {"en": {"request": "Prepare a report from these files."}},
            "sources": [
                {
                    "path": "skills/sample/SKILL.md",
                    "sha256": hashlib.sha256(source).hexdigest(),
                }
            ],
        }
    )
    files = {
        "skills/sample/SKILL.md": source,
        "assets/courses/sample/course.json": course,
        "assets/courses/index.json": _encoded(
            {"courses": {"sample": {"sha256": hashlib.sha256(course).hexdigest()}}}
        ),
    }
    native = {prefix + name: value for name, value in files.items()}
    entries = dict(files)
    entries["skills/sample/SKILL.md"] = builder.project_chatgpt_source_skill(source)
    return builder, native, entries, prefix


def test_upload_projection_binds_shipped_skill_and_preserves_reviewed_course() -> None:
    builder, native, entries, prefix = _case()
    original = dict(native)
    builder.project_chatgpt_course_sources(entries, native, prefix)
    course = json.loads(entries["assets/courses/sample/course.json"])
    before = json.loads(native[prefix + "assets/courses/sample/course.json"])
    assert native == original
    assert course["lessons"] == before["lessons"]
    assert course["sources"][0]["source_sha256"] == before["sources"][0]["sha256"]
    assert (
        course["sources"][0]["sha256"]
        == hashlib.sha256(entries["skills/sample/SKILL.md"]).hexdigest()
    )
    canonical = hashlib.sha256(
        native[prefix + "assets/courses/sample/course.json"]
    ).hexdigest()
    assert course["source_package"]["course_sha256"] == canonical
    index = json.loads(entries["assets/courses/index.json"])["courses"]["sample"]
    assert index["source_sha256"] == canonical
    assert (
        index["sha256"]
        == hashlib.sha256(entries["assets/courses/sample/course.json"]).hexdigest()
    )


def test_upload_preserves_course_bytes_when_no_source_projection_is_needed() -> None:
    builder, native, entries, prefix = _case(project=False)
    original = dict(entries)
    builder.project_chatgpt_course_sources(entries, native, prefix)
    assert entries == original


def test_upload_without_teaching_courses_needs_no_projection() -> None:
    builder = load_builder()
    entries = {"LICENSE": b"fixture"}
    builder.project_chatgpt_course_sources(entries, {}, "package/")
    assert entries == {"LICENSE": b"fixture"}


@pytest.mark.parametrize("missing_from", ["native", "upload"])
def test_upload_rejects_missing_pinned_workflow_source(missing_from: str) -> None:
    builder, native, entries, prefix = _case()
    if missing_from == "native":
        native.pop(prefix + "skills/sample/SKILL.md")
    else:
        entries.pop("skills/sample/SKILL.md")
    with pytest.raises(ValueError, match="Missing packaged teaching source"):
        builder.project_chatgpt_course_sources(entries, native, prefix)


@pytest.mark.parametrize("change", ["index", "course", "source"])
def test_upload_rejects_stale_canonical_review_inputs(change: str) -> None:
    builder, native, entries, prefix = _case()
    if change == "index":
        entries["assets/courses/index.json"] = _encoded(
            {"courses": {"sample": {"sha256": "0" * 64}}}
        )
    elif change == "course":
        entries["assets/courses/sample/course.json"] += b" "
    else:
        native[prefix + "skills/sample/SKILL.md"] += b"Changed workflow\n"
    with pytest.raises(ValueError, match="Rebuild and review the source course"):
        builder.project_chatgpt_course_sources(entries, native, prefix)


def test_upload_cannot_relabel_an_arbitrary_workflow_edit_as_projection() -> None:
    builder, native, entries, prefix = _case()
    entries[
        "skills/sample/SKILL.md"
    ] += b"Invent a result instead of running the workflow.\n"
    with pytest.raises(ValueError, match="Unsupported teaching source projection"):
        builder.project_chatgpt_course_sources(entries, native, prefix)
