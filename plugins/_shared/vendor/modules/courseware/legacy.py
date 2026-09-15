"""Load reviewed course content and render it without model or network calls.

The checks here concern exact product membership, file identity and language
coverage. They do not judge professional relevance, correctness or understanding.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import shutil
from pathlib import Path
from typing import Any

__all__ = ["CourseError", "CourseLibrary"]


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


def _table(columns: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th scope='col'>{_esc(value)}</th>" for value in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<div class='table-scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _markdown_table(columns: list[str], rows: list[list[str]]) -> str:
    lines = [columns, ["---"] * len(columns), *rows]
    return "\n".join(
        "| "
        + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row)
        + " |"
        for row in lines
    )


def _visual(course: dict[str, Any], content: dict[str, Any]) -> str:
    """Draw the case's explicitly authored values from a common zero baseline."""
    if "visual" not in course:
        return ""
    visual = course["visual"]
    maximum = visual.get("maximum", max(value for _, value in visual["bars"]))
    rows = []
    for index, value in visual["bars"]:
        label = content["output_rows"][index][0]
        display = content["output_rows"][index][visual["column"]]
        width = value / maximum * 1000
        rows.append(
            f"<div class='chart-row'><div><span>{_esc(label)}</span><strong>{_esc(display)}</strong></div>"
            f"<svg viewBox='0 0 1000 22' aria-hidden='true' focusable='false'>"
            f"<rect class='chart-track' width='1000' height='22'/><rect class='chart-bar' width='{width:.3f}' height='22'/></svg></div>"
        )
    return (
        "<figure class='case-chart'>"
        f"<figcaption>{_esc(content['output_columns'][visual['column']])}</figcaption>"
        + "".join(rows)
        + "</figure>"
    )


class CourseLibrary:
    """Read only courses belonging to the caller's current eligible catalog."""

    def __init__(self, plugin_root: Path, eligible: set[str]) -> None:
        self.root = plugin_root.resolve()
        self.product = _read(self.root / ".codex-plugin/plugin.json")["name"]
        self.assets = self.root / "assets/courses"
        self.index = _read(self.assets / "index.json")
        self.eligible = eligible
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
        if (
            course.get("schema") != "mparanza.course.v1"
            or course.get("product") != self.product
            or course.get("workflow") != workflow
            or sorted(course["locales"]) != sorted(entry["languages"])
            or not 300 <= sum(course["seconds"]) <= 480
        ):
            raise CourseError("Invalid course identity, language coverage or duration")
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
        for asset in course.get("files", []):
            path = _inside(manifest.parent, asset["path"])
            if _digest(path) != asset["sha256"]:
                raise CourseError("Prepared example changed; rebuild its course")
        return course

    def render(self, workflow: str, language: str, destination: Path) -> dict[str, Any]:
        """Materialize prepared content in a fresh local directory; record no lesson."""
        course = self.load(workflow, language)
        destination = destination.expanduser().absolute()
        if any(path.is_symlink() for path in (destination, *destination.parents)):
            raise CourseError("Use an ordinary local destination, not a symlink")
        if destination.exists():
            raise CourseError("Use a fresh course directory; preserve existing work")
        destination.mkdir(parents=True)
        copy = course["locales"][language]
        shared_assets = Path(__file__).parent / "assets"
        ui = _read(shared_assets / "legacy-languages.json")[language]
        for asset in (
            "course.css",
            "InstrumentSans-Regular.ttf",
            "InstrumentSans-SemiBold.ttf",
            "OFL.txt",
        ):
            shutil.copyfile(
                _inside(
                    shared_assets,
                    "legacy-course.css" if asset == "course.css" else asset,
                ),
                destination / asset,
            )
        source_dir = (self.assets / self.index["courses"][workflow]["path"]).parent
        files = []
        for asset in course.get("files", []):
            target = destination / asset["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_inside(source_dir, asset["path"]), target)
            files.append(asset["path"])
        specimen = self._specimen(course, copy, ui, language)
        (destination / "example.html").write_text(specimen, encoding="utf-8")
        (destination / "course.html").write_text(
            self._page(course, copy, ui, language, files), encoding="utf-8"
        )
        (destination / "teacher.md").write_text(
            self._teacher(course, copy, ui), encoding="utf-8"
        )
        # A ready-to-inspect synthetic input, not an invented execution recipe.
        (destination / "case.json").write_text(
            json.dumps(
                {
                    "kind": "authored_synthetic_teaching_case",
                    "workflow": workflow,
                    "scenario": copy["scenario"],
                    "columns": copy["input_columns"],
                    "rows": copy["input_rows"],
                    "scope": copy["scope"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        with (destination / "input.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(copy["input_columns"])
            writer.writerows(copy["input_rows"])
        (destination / "source.md").write_text(
            f"# {copy['title']}\n\n{ui['synthetic']}\n\n{copy['scenario']}\n\n"
            + _markdown_table(copy["input_columns"], copy["input_rows"])
            + f"\n\n{copy['basis']}\n\n{copy['scope']}\n",
            encoding="utf-8",
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
            "example": str(destination / "example.html"),
            "teacher": str(destination / "teacher.md"),
            "sources": course["sources"],
            "prepared_artifacts": [
                {
                    "path": path.relative_to(destination).as_posix(),
                    "sha256": _digest(path),
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

    def _specimen(
        self,
        course: dict[str, Any],
        copy: dict[str, Any],
        ui: dict[str, Any],
        language: str,
    ) -> str:
        rows = _table(copy["output_columns"], copy["output_rows"])
        return self._shell(
            copy["title"],
            language,
            f"<header class='masthead'><b>{_esc(self.product.title())}</b><span>{_esc(ui['example'])}</span></header>"
            f"<main class='report'><p class='eyebrow'>{_esc(ui['prepared'])}</p><h1>{_esc(copy['result_title'])}</h1>"
            f"<p class='lead'>{_esc(copy['conclusion'])}</p><p class='caption'>{_esc(ui['synthetic'])}</p>"
            f"{_visual(course, copy)}{rows}<section><h2>{_esc(ui['source'])}</h2><p>{_esc(copy['basis'])}</p></section>"
            f"<section class='review'><h2>{_esc(ui['check'])}</h2><p>{_esc(copy['check'])}</p>"
            f"<p>{_esc(copy['scope'])}</p></section><footer>{_esc(ui['specimen_notice'])}</footer></main>",
        )

    def _page(
        self,
        course: dict[str, Any],
        copy: dict[str, Any],
        ui: dict[str, Any],
        language: str,
        files: list[str],
    ) -> str:
        labels = ui["stages"]
        nav = "".join(
            f"<a href='#step-{i}'><span>0{i+1}</span>{_esc(label)}</a>"
            for i, label in enumerate(labels)
        )
        methods = "".join(f"<li>{_esc(step)}</li>" for step in copy["method"])
        downloads = "".join(
            f"<li><a href='{_esc(file)}'>{_esc(file)}</a></li>" for file in files
        )
        supplement = (
            f"<h3>{_esc(ui['supplement_title'])}</h3><p>{_esc(ui['supplement_text'])}</p><ul>{downloads}</ul>"
            if files
            else ""
        )
        parts = [
            f"<p class='lead'>{_esc(copy['scenario'])}</p><blockquote>{_esc(copy['request'])}</blockquote><p>{_esc(copy['scope'])}</p>",
            _table(copy["input_columns"], copy["input_rows"])
            + f"<p>{_esc(copy['basis'])}</p><a href='source.md' download>{_esc(ui['case_download'])}</a> · <a href='input.csv' download>CSV</a>",
            f"<ol class='method'>{methods}</ol>",
            f"<div class='result-preview'><p class='eyebrow'>{_esc(ui['prepared'])}</p><h3>{_esc(copy['result_title'])}</h3><p>{_esc(copy['conclusion'])}</p>"
            + _visual(course, copy)
            + _table(copy["output_columns"], copy["output_rows"])
            + f"<a class='button' href='example.html' target='_blank' rel='noopener'>{_esc(ui['open_example'])} ↗</a></div>{supplement}",
            f"<p class='lead'>{_esc(copy['check'])}</p><p>{_esc(copy['question'])}</p><details><summary>{_esc(ui['answer'])}</summary><p>{_esc(copy['answer'])}</p></details>",
            f"<blockquote>{_esc(copy['practice'])}</blockquote><p>{_esc(ui['optional_practice'])}</p><p>{_esc(copy['next'])}</p>",
        ]
        sections = "".join(
            f"<section id='step-{i}' class='lesson-step'><div class='section-label'><span>0{i+1} / {course['seconds'][i]} s</span><h2>{_esc(labels[i])}</h2></div>"
            f"<div class='section-body'><p class='voice-cue'>{_esc(ui['cues'][i])}</p>{part}</div></section>"
            for i, part in enumerate(parts)
        )
        body = (
            f"<header class='masthead'><b>{_esc(self.product.title())}</b><span>{_esc(ui['series'])}</span><span>5–8 min · {_esc(language.upper())}</span></header>"
            f"<main><div class='hero'><p class='eyebrow'>{_esc(ui['prepared'])}</p><h1>{_esc(copy['title'])}</h1>"
            f"<p class='lead'>{_esc(copy['goal'])}</p><p class='caption'>{_esc(ui['timing'])}</p></div>"
            f"<aside class='paired'><b>{_esc(ui['two_threads'])}</b><p>{_esc(ui['pair_explanation'])}</p></aside>"
            f"<nav aria-label='{_esc(ui['contents'])}'>{nav}</nav>{sections}"
            f"<footer><p>{_esc(ui['specimen_notice'])}</p><p>{_esc(ui['privacy'])}</p>"
            f"<a href='course-provenance.json'>{_esc(ui['provenance'])}</a> · {_esc(course['revision'])}</footer></main>"
        )
        return self._shell(copy["title"], language, body)

    def _teacher(
        self, course: dict[str, Any], copy: dict[str, Any], ui: dict[str, Any]
    ) -> str:
        blocks = [
            copy["scenario"] + "\n\n" + copy["request"],
            copy["basis"] + "\n\n" + json.dumps(copy["input_rows"], ensure_ascii=False),
            "\n".join(copy["method"]),
            copy["conclusion"]
            + "\n\n"
            + json.dumps(copy["output_rows"], ensure_ascii=False),
            copy["check"]
            + "\n\n"
            + copy["question"]
            + "\n\n"
            + ui["answer"]
            + ": "
            + copy["answer"],
            copy["practice"] + "\n\n" + copy["next"],
        ]
        text = f"# {copy['title']}\n\n{ui['timing']}\n\n{ui['pair_explanation']}\n\n{ui['teacher_rule']}\n\n"
        for i, block in enumerate(blocks):
            text += f"## {i+1}. {ui['stages'][i]} · {course['seconds'][i]} s\n\n{ui['cues'][i]}\n\n{block}\n\n"
        return text + ui["specimen_notice"] + "\n\n" + ui["privacy"] + "\n"
