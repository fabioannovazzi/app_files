"""Project prepared courses onto the exact supported Cowork workflow bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["add_written_teaching"]


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _written_copy(value: Any, replacements: list[list[str]]) -> Any:
    """Apply authored host wording only; preserve each workflow's method and data."""
    if isinstance(value, str):
        for native, written in replacements:
            value = value.replace(native, written)
        return value
    if isinstance(value, list):
        return [_written_copy(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _written_copy(item, replacements) for key, item in value.items()}
    return value


def add_written_teaching(
    root: Path, product: str, source: dict[str, bytes], entries: dict[str, bytes]
) -> None:
    """Reuse reviewed materials, excluding workflows absent from this host."""
    assets = "assets/courses/"
    source_index = json.loads(source[assets + "index.json"])
    if source_index["product"] != product:
        raise ValueError("Foreign course catalogue")
    wording = json.loads(
        (root / "scripts/cowork_teaching/written-copy.json").read_text(encoding="utf-8")
    )
    courses = {}
    for workflow, original in source_index["courses"].items():
        skill = f"skills/{workflow}/SKILL.md"
        if skill not in entries or (
            product == "clara"
            and workflow in {"brand-fit", "hosted-interview", "research-video"}
        ):
            continue
        manifest = assets + original["path"]
        data = source[manifest]
        if hashlib.sha256(data).hexdigest() != original["sha256"]:
            raise ValueError(f"Unreviewed course: {manifest}")
        course = json.loads(data)
        projected_sources = []
        for item in course["sources"]:
            path = item["path"]
            if (
                path not in source
                or hashlib.sha256(source[path]).hexdigest() != item["sha256"]
            ):
                raise ValueError(
                    f"Course needs source review: {product}/{workflow}: {path}"
                )
            if path in entries:
                projected_sources.append(
                    {"path": path, "sha256": hashlib.sha256(entries[path]).hexdigest()}
                )
        if not any(item["path"] == skill for item in projected_sources):
            projected_sources.append(
                {"path": skill, "sha256": hashlib.sha256(entries[skill]).hexdigest()}
            )
        for language, locale in course.get("locales", {}).items():
            course["locales"][language] = _written_copy(locale, wording[language])
        course["sources"] = projected_sources
        course["host"] = "cowork-written-single-conversation"
        course["canonical_course_sha256"] = original["sha256"]
        entries[manifest] = _json(course)
        for item in course["files"]:
            relative = Path(item["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Invalid course attachment path")
            path = (Path(manifest).parent / relative).as_posix()
            content = source[path]
            if hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise ValueError(f"Unreviewed course attachment: {path}")
            entries[path] = content
        courses[workflow] = {
            **original,
            "sha256": hashlib.sha256(entries[manifest]).hexdigest(),
        }
    entries[assets + "index.json"] = _json({**source_index, "courses": courses})
    overrides = json.loads(
        (root / "scripts/cowork_teaching/languages.json").read_text(encoding="utf-8")
    )
    for path, content in source.items():
        if not path.startswith("vendor/modules/courseware/"):
            continue
        if path.endswith(("library.py", "legacy.py")):
            content = content.replace(
                b".codex-plugin/plugin.json", b".claude-plugin/plugin.json"
            )
        if path.endswith(("/languages.json", "/legacy-languages.json")):
            locales = json.loads(content)
            for language, copy in locales.items():
                copy.update(overrides[language])
            content = _json(locales)
        entries[path] = content
    template = root / "scripts/cowork_teaching"
    entries["scripts/local_courses.py"] = (template / "runtime.py").read_bytes()
    entries[f"skills/learn-with-{product}/SKILL.md"] = (
        (template / "SKILL.md")
        .read_text(encoding="utf-8")
        .replace("__PRODUCT__", product)
        .replace("__NAME__", product.title())
        .encode()
    )
    catalog_path = f"skills/{product}/references/workflow-catalog.md"
    if catalog_path in entries:
        entries[catalog_path] += (
            f"\n- `learn-with-{product}`: learn an installed function in writing using prepared files, actual execution and practice in one conversation.\n"
        ).encode()
    router = f"skills/{product}/SKILL.md"
    text = entries[router].decode()
    route = (
        f"\n## Written lessons\n\nFor a request to learn or practise a supported {product.title()} function, read "
        f"`../learn-with-{product}/SKILL.md`. Teach in writing in this conversation "
        "using the prepared kit and actual workflow results. Start only when requested.\n"
    )
    # Put teaching routing before normal professional execution rules.
    end = text.find("\n---", 3) + len("\n---") if text.startswith("---") else 0
    entries[router] = (text[:end] + route + text[end:]).encode()
