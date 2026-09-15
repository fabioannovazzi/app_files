"""Load reviewed course content and render it without model or network calls.

The checks here concern exact product membership, file identity and language
coverage. They do not judge professional relevance, correctness or understanding.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path
from typing import Any

from .policy import local_unavailability, unavailable_local_workflows

__all__ = ["CourseError", "CourseLibrary", "main"]


class CourseError(ValueError):
    """A course cannot be safely reused with the current installed workflow."""


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(root: Path, relative: str) -> Path:
    path = root / relative
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise CourseError("Course paths must be relative and contained")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise CourseError(f"Missing or foreign course file: {relative}")
    return path


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _list(values: list[str]) -> str:
    return (
        "<ol class='method'>"
        + "".join(f"<li>{_esc(value)}</li>" for value in values)
        + "</ol>"
    )


class CourseLibrary:
    """Read only courses belonging to the caller's current eligible catalog."""

    def __init__(self, plugin_root: Path, eligible: set[str]) -> None:
        self.root = plugin_root.resolve()
        self.product = _read(self.root / ".codex-plugin/plugin.json")["name"]
        self.assets = self.root / "assets/courses"
        self.index = _read(self.assets / "index.json")
        self.eligible = eligible - unavailable_local_workflows(self.product)
        if self.index.get("product") != self.product:
            raise CourseError("The course catalog belongs to another product")

    def catalog(self) -> list[dict[str, Any]]:
        """Return only installed courses, including their explicit locales."""
        return [
            {"workflow": key, **value}
            for key, value in sorted(self.index["courses"].items())
            if key in self.eligible
        ]

    def load(self, workflow: str, language: str) -> dict[str, Any]:
        """Fail closed on foreign, unavailable, altered or stale course content."""
        if reason := local_unavailability(self.product, workflow):
            raise CourseError(reason)
        if workflow not in self.eligible or workflow not in self.index["courses"]:
            raise CourseError("Choose a course from this product's installed catalog")
        entry = self.index["courses"][workflow]
        if language not in entry["languages"]:
            raise CourseError(
                "This course supports: "
                + ", ".join(entry["languages"])
                + "; ask the user to select one, without silently translating"
            )
        manifest = _inside(self.assets, entry["path"])
        if _digest(manifest) != entry["sha256"]:
            raise CourseError("Course content changed; rebuild the reviewed catalog")
        course = _read(manifest)
        if course.get("schema") == "mparanza.course.v1":
            from . import legacy

            try:
                return legacy.CourseLibrary(self.root, self.eligible).load(
                    workflow, language
                )
            except legacy.CourseError as exc:
                raise CourseError(str(exc)) from exc
        if (
            course.get("schema") != "mparanza.teaching_kit.v2"
            or course.get("product") != self.product
            or course.get("workflow") != workflow
            or sorted(course["locales"]) != sorted(entry["languages"])
            or len(course["seconds"]) != 6
            or any(
                type(seconds) is not int or seconds <= 0
                for seconds in course["seconds"]
            )
            or not 300 <= sum(course["seconds"]) <= 480
        ):
            raise CourseError("Invalid course identity, language coverage or duration")
        if course["group"] not in {"workflow", "supporting_task"}:
            raise CourseError("Invalid teaching-kit catalogue group")
        content = course["locales"][language]
        for field in (
            "title",
            "goal",
            "scenario",
            "scope",
            "inputs",
            "request",
            "review",
            "practice",
            "success",
            "repeat",
        ):
            if not isinstance(content.get(field), str) or not content[field].strip():
                raise CourseError(f"Teaching kit is missing its {field}")
        for field in ("steps", "deliverables", "checkpoints"):
            if (
                not isinstance(content.get(field), list)
                or not content[field]
                or any(
                    not isinstance(value, str) or not value.strip()
                    for value in content[field]
                )
            ):
                raise CourseError(f"Teaching kit is missing its {field}")
        for source in course["sources"]:
            # The package contains its own component; source checkouts use the
            # explicitly pinned sibling component, never an installed plugin.
            relative = source["path"]
            candidate = self.root / relative
            if (
                not candidate.is_file()
                and "repository_path" in source
                and (self.root.parent.parent / ".git").exists()
            ):
                candidate = _inside(self.root.parent.parent, source["repository_path"])
            else:
                candidate = _inside(self.root, relative)
            if _digest(candidate) != source["sha256"]:
                raise CourseError(
                    f"Course needs editorial refresh after a workflow change: {relative}"
                )
        selected_roles = set()
        seen_paths = set()
        for asset in course.get("files", []):
            path = _inside(manifest.parent, asset["path"])
            if _digest(path) != asset["sha256"]:
                raise CourseError("Teaching input changed; review and rebuild its kit")
            if (
                asset["path"] in seen_paths
                or asset["role"] not in {"source", "practice"}
                or not set(asset["languages"]) <= set(entry["languages"])
            ):
                raise CourseError(
                    "Teaching kits may contain only uniquely identified source and practice files"
                )
            seen_paths.add(asset["path"])
            if language in asset["languages"]:
                selected_roles.add(asset["role"])
        if selected_roles != {"source", "practice"}:
            raise CourseError(
                "Teaching kit needs source and practice files in the selected language"
            )
        return course

    def render(self, workflow: str, language: str, destination: Path) -> dict[str, Any]:
        """Materialize prepared content in a fresh local directory; record no lesson."""
        course = self.load(workflow, language)
        if course["schema"] == "mparanza.course.v1":
            from . import legacy

            try:
                return legacy.CourseLibrary(self.root, self.eligible).render(
                    workflow, language, destination
                )
            except legacy.CourseError as exc:
                raise CourseError(str(exc)) from exc
        destination = destination.expanduser().absolute()
        if any(path.is_symlink() for path in (destination, *destination.parents)):
            raise CourseError("Use an ordinary local destination, not a symlink")
        if destination.exists():
            raise CourseError("Use a fresh course directory; preserve existing work")
        destination.mkdir(parents=True)
        copy = course["locales"][language]
        shared_assets = Path(__file__).parent / "assets"
        ui = _read(shared_assets / "languages.json")[language]
        for asset in (
            "course.css",
            "InstrumentSans-Regular.ttf",
            "InstrumentSans-SemiBold.ttf",
            "OFL.txt",
        ):
            shutil.copyfile(_inside(shared_assets, asset), destination / asset)
        source_dir = (self.assets / self.index["courses"][workflow]["path"]).parent
        files = []
        for asset in course.get("files", []):
            if language not in asset["languages"]:
                continue
            target = destination / asset["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_inside(source_dir, asset["path"]), target)
            files.append(asset)
        (destination / "course.html").write_text(
            self._page(course, copy, ui, language, files), encoding="utf-8"
        )
        (destination / "teacher.md").write_text(
            self._teacher(course, copy, ui), encoding="utf-8"
        )
        # This is an instruction handoff, never an execution or review receipt.
        execution = {
            "schema": "mparanza.teaching_execution_request.v1",
            "product": self.product,
            "workflow": workflow,
            "language": language,
            "skill": str(self.root / "skills" / workflow / "SKILL.md"),
            "request": copy["request"],
            "source_files": [
                str(destination / f["path"]) for f in files if f["role"] == "source"
            ],
            "practice_files": [
                str(destination / f["path"]) for f in files if f["role"] == "practice"
            ],
            "execution": course["execution"],
            "steps": copy["steps"],
            "checkpoints": copy["checkpoints"],
            "deliverables": copy["deliverables"],
            "practice": copy["practice"],
            "success": copy["success"],
            "sources": course["sources"],
            "execution_receipt": False,
            "rule": "Read the current own-product skill and delegated procedure completely. Prepare the real bound tutorial case from source_files. Execute one authorized working-thread step at a time. Open and explain the actual outputs. Rendering this kit completes no demo, practice or understanding checkpoint. Never replace a missing or blocked pipeline with authored output. Keep the tutorial local; a hosted step needs the user's separate explicit choice and normal workflow authority.",
        }
        (destination / "execution-request.json").write_text(
            json.dumps(execution, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        receipt = {
            "product": self.product,
            "workflow": workflow,
            "language": language,
            "course_revision": course["revision"],
            "prepared_material_only": True,
            "execution_receipt": False,
            "understanding_confirmed": False,
            "course": str(destination / "course.html"),
            "execution_request": str(destination / "execution-request.json"),
            "source_files": execution["source_files"],
            "practice_files": execution["practice_files"],
            "teacher": str(destination / "teacher.md"),
            "sources": course["sources"],
            "prepared_artifacts": [
                {
                    "path": path.relative_to(destination).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in sorted(destination.rglob("*"))
                if path.is_file()
            ],
        }
        (destination / "course-provenance.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return receipt

    def _shell(self, title: str, language: str, body: str) -> str:
        return (
            "<!doctype html>\n" + f"<html lang='{_esc(language)}'><head>"
            "<meta charset='utf-8'><meta name='google' content='notranslate'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'self'; font-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'\">"
            f"<title>{_esc(title)}</title><link rel='stylesheet' href='course.css'></head>"
            f"<body>{body}</body></html>\n"
        )

    def _page(
        self,
        course: dict[str, Any],
        copy: dict[str, Any],
        ui: dict[str, Any],
        language: str,
        files: list[dict[str, Any]],
    ) -> str:
        labels = ui["stages"]
        nav = "".join(
            f"<a href='#step-{i}'><span>0{i+1}</span>{_esc(label)}</a>"
            for i, label in enumerate(labels)
        )
        downloads = "".join(
            f"<li><a href='{_esc(file['path'])}'>{_esc(Path(file['path']).name)}</a></li>"
            for file in files
            if file["role"] == "source"
        )
        practice_files = "".join(
            f"<li><a href='{_esc(file['path'])}'>{_esc(Path(file['path']).name)}</a></li>"
            for file in files
            if file["role"] == "practice"
        )
        parts = [
            f"<p class='lead'>{_esc(copy['scenario'])}</p><p>{_esc(copy['scope'])}</p>",
            f"<p>{_esc(copy['inputs'])}</p><ul>{downloads}</ul><blockquote>{_esc(copy['request'])}</blockquote>",
            _list(copy["steps"])
            + f"<aside class='paired'>{_esc(ui['live_rule'])}</aside>",
            _list(copy["deliverables"]) + f"<p>{_esc(copy['review'])}</p>",
            _list(copy["checkpoints"]) + f"<p>{_esc(ui['checkpoint_rule'])}</p>",
            f"<blockquote>{_esc(copy['practice'])}</blockquote><ul>{practice_files}</ul><p>{_esc(copy['success'])}</p><p>{_esc(copy['repeat'])}</p>",
        ]
        sections = "".join(
            f"<section id='step-{i}' class='lesson-step'><div class='section-label'><span>0{i+1}</span><h2>{_esc(labels[i])}</h2></div>"
            f"<div class='section-body'>{part}</div></section>"
            for i, part in enumerate(parts)
        )
        body = (
            f"<header class='masthead'><b>{_esc(self.product.title())}</b><span>{_esc(ui['series'])}</span><span>5–8 min · {_esc(language.upper())}</span></header>"
            f"<main><div class='hero'><p class='eyebrow'>{_esc(ui['prepared'])}</p><h1>{_esc(copy['title'])}</h1>"
            f"<p class='lead'>{_esc(copy['goal'])}</p><p class='caption'>{_esc(ui['timing'])}</p></div>"
            f"<aside class='paired'><b>{_esc(ui['two_threads'])}</b><p>{_esc(ui['pair_explanation'])}</p></aside>"
            f"<nav aria-label='{_esc(ui['contents'])}'>{nav}</nav>{sections}"
            f"<footer><p>{_esc(ui['kit_notice'])}</p><p>{_esc(ui['privacy'])}</p>"
            f"<a href='course-provenance.json'>{_esc(ui['provenance'])}</a> · {_esc(course['revision'])}</footer></main>"
        )
        return self._shell(copy["title"], language, body)

    def _teacher(
        self, course: dict[str, Any], copy: dict[str, Any], ui: dict[str, Any]
    ) -> str:
        blocks = [
            copy["goal"] + "\n\n" + copy["scenario"] + "\n\n" + copy["scope"],
            copy["inputs"] + "\n\n" + copy["request"],
            "\n\n".join(copy["steps"]) + "\n\n" + ui["live_rule"],
            "\n\n".join(copy["deliverables"]) + "\n\n" + copy["review"],
            "\n\n".join(copy["checkpoints"]) + "\n\n" + ui["checkpoint_rule"],
            copy["practice"] + "\n\n" + copy["success"] + "\n\n" + copy["repeat"],
        ]
        text = f"# {copy['title']}\n\n{ui['timing']}\n\n{ui['pair_explanation']}\n\n{ui['teacher_rule']}\n\n"
        for i, block in enumerate(blocks):
            text += f"## {i+1}. {ui['stages'][i]} · {course['seconds'][i]} s\n\n{ui['cues'][i]}\n\n{block}\n\n"
        return text + ui["kit_notice"] + "\n\n" + ui["privacy"] + "\n"


def main(plugin_root: Path, eligible: set[str], argv: list[str] | None = None) -> int:
    """Local CLI: catalog, inspect or render packaged content without user telemetry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "show", "render"))
    parser.add_argument("--workflow")
    parser.add_argument("--language")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        library = CourseLibrary(plugin_root, eligible)
        if args.action == "list":
            result: Any = library.catalog()
        else:
            if not args.workflow or not args.language:
                parser.error("--workflow and --language are required")
            if args.action == "render":
                if not args.output_dir:
                    parser.error("render requires --output-dir")
                result = library.render(args.workflow, args.language, args.output_dir)
            else:
                course = library.load(args.workflow, args.language)
                result = {
                    "product": course["product"],
                    "workflow": course["workflow"],
                    "language": args.language,
                    "revision": course["revision"],
                    "seconds": course["seconds"],
                    "sources_current": True,
                    "source_count": len(course["sources"]),
                    "execution": course["execution"],
                    "group": course["group"],
                    "content": course["locales"][args.language],
                    "files": [asset["path"] for asset in course.get("files", [])],
                }
        # JSON escapes preserve all localized text on legacy Windows consoles.
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (CourseError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Course unavailable: {exc}\n")
    return 0
