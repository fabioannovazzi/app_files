#!/usr/bin/env python3
"""Validate a self-contained Clara HTML stage deck and emit a deterministic report."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from content_ledger import extract_embedded_ledger, validate_content_ledger

SCHEMA_VERSION = "clara.html_deck_validation.v1"
VALIDATION_PROFILES = {"stage", "static"}
SLIDE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PUBLICATION_ID_RE = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_RE = re.compile(
    r"\{\{[^{}]+\}\}|\bLOREM\s+IPSUM\b|\bREPLACE\s+THIS\b",
    flags=re.IGNORECASE,
)
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
CONTENT_SPEC_TEXT_FIELDS = (
    "eyebrow",
    "brand",
    "title",
    "chart_caption_left",
    "chart_caption_right",
    "narrative_headline",
)
CONTENT_SPEC_TRAILING_FIELDS = ("note", "footer", "number")


@dataclass
class Check:
    code: str
    severity: str
    status: str
    message: str
    location: str | None = None


@dataclass
class Slide:
    index: int
    id: str
    title: str
    chapter: str
    active: bool
    has_notes: bool = False
    note_text: str = ""
    fragment_values: list[str] = field(default_factory=list)
    heading_text: str = ""
    source_refs: list[str] = field(default_factory=list)
    claim_refs: list[str] = field(default_factory=list)


class DeckParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.doctype = False
        self.html_count = 0
        self.head_count = 0
        self.body_count = 0
        self.main_count = 0
        self.deck_roots: list[dict[str, str]] = []
        self.language = ""
        self.title_parts: list[str] = []
        self._in_title = False
        self.meta: list[dict[str, str]] = []
        self.ids: list[str] = []
        self.href_fragments: list[str] = []
        self.resource_refs: list[tuple[str, str, str]] = []
        self.anchor_refs: list[str] = []
        self.executable_attribute_issues: list[tuple[str, str, str]] = []
        self.style_attrs: list[str] = []
        self.style_bodies: list[str] = []
        self.script_bodies: list[str] = []
        self.class_names: set[str] = set()
        self._in_style = False
        self._style_parts: list[str] = []
        self._in_executable_script = False
        self._script_parts: list[str] = []
        self.slides: list[Slide] = []
        self._slide: Slide | None = None
        self._slide_section_depth: int | None = None
        self._section_depth = 0
        self._in_heading = False
        self._heading_parts: list[str] = []
        self._in_notes = False
        self._note_parts: list[str] = []
        self.svg_total = 0
        self.svg_accessible = 0

    @staticmethod
    def attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.lower(): value or "" for key, value in attrs}

    @staticmethod
    def reference_tokens(value: str) -> list[str]:
        """Parse provenance IDs from the whitespace-delimited token contract."""

        # Accept commas for compatibility with early composer work files while
        # emitting whitespace-delimited values in all current authoring tools.
        return [token for token in re.split(r"[\s,]+", value.strip()) if token]

    def handle_decl(self, decl: str) -> None:
        if decl.lower().strip() == "doctype html":
            self.doctype = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = self.attrs_dict(attrs)
        if tag not in VOID_TAGS:
            self.stack.append(tag)
        if tag == "section":
            self._section_depth += 1
        if "id" in values:
            self.ids.append(values["id"])
        if tag == "html":
            self.html_count += 1
            self.language = values.get("lang", self.language)
        elif tag == "head":
            self.head_count += 1
        elif tag == "body":
            self.body_count += 1
        elif tag == "title" and "head" in self.stack[:-1]:
            self._in_title = True
        elif tag == "meta":
            self.meta.append(values)
        elif tag == "main":
            self.main_count += 1
            classes = set(values.get("class", "").split())
            if "deck-stage" in classes or "clara-fixed-16-9-deck" in classes:
                self.deck_roots.append(values)

        classes = set(values.get("class", "").split())
        self.class_names.update(classes)
        if values.get("style"):
            self.style_attrs.append(values["style"])
        for name, value in values.items():
            if name.startswith("on"):
                self.executable_attribute_issues.append((tag, name, value))
            if name in {
                "action",
                "data",
                "formaction",
                "href",
                "poster",
                "src",
                "srcset",
                "xlink:href",
            }:
                compact = re.sub(r"[\x00-\x20\x7f]+", "", value).lower()
                if compact.startswith(("javascript:", "vbscript:", "data:text/html")):
                    self.executable_attribute_issues.append((tag, name, value))
        if tag == "style":
            self._in_style = True
            self._style_parts = []
        if tag == "script" and values.get("type", "").lower() != "application/json":
            self._in_executable_script = True
            self._script_parts = []
        if tag == "section" and "slide" in classes:
            slide = Slide(
                index=len(self.slides) + 1,
                id=values.get("id", ""),
                title=values.get("data-slide-title", ""),
                chapter=values.get("data-chapter", ""),
                active=(
                    "is-active" in classes
                    or values.get("data-active", "").lower() == "true"
                    or values.get("aria-hidden", "").lower() == "false"
                ),
                source_refs=self.reference_tokens(values.get("data-source-ids", "")),
                claim_refs=self.reference_tokens(values.get("data-claim-ids", "")),
            )
            self.slides.append(slide)
            self._slide = slide
            self._slide_section_depth = self._section_depth
        elif self._slide is not None:
            self._slide.source_refs.extend(
                self.reference_tokens(values.get("data-source-ids", ""))
            )
            self._slide.claim_refs.extend(
                self.reference_tokens(values.get("data-claim-ids", ""))
            )
            if "speaker-notes" in classes:
                self._slide.has_notes = True
                self._in_notes = True
                self._note_parts = []
            if tag in {"h1", "h2", "h3"} and not self._slide.heading_text:
                self._in_heading = True
                self._heading_parts = []
            if "data-fragment" in values:
                self._slide.fragment_values.append(values["data-fragment"])

        if tag == "a" and "href" in values:
            href = values["href"].strip()
            if href.startswith("#"):
                self.href_fragments.append(href[1:])
            elif href:
                self.anchor_refs.append(href)

        resource_attrs: list[str] = []
        if tag in {
            "script",
            "img",
            "audio",
            "video",
            "source",
            "iframe",
            "embed",
            "input",
        }:
            resource_attrs.extend(["src", "srcset"])
        elif tag == "link":
            resource_attrs.append("href")
        elif tag == "object":
            resource_attrs.append("data")
        for attr in resource_attrs:
            if values.get(attr):
                self.resource_refs.append((tag, attr, values[attr].strip()))

        if tag == "svg":
            self.svg_total += 1
            if values.get("role") == "img" and (
                values.get("aria-label") or values.get("aria-labelledby")
            ):
                self.svg_accessible += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag == "style" and self._in_style:
            self.style_bodies.append("".join(self._style_parts))
            self._in_style = False
            self._style_parts = []
        if tag == "script" and self._in_executable_script:
            self.script_bodies.append("".join(self._script_parts))
            self._in_executable_script = False
            self._script_parts = []
        if self._slide is not None and tag in {"h1", "h2", "h3"} and self._in_heading:
            self._slide.heading_text = " ".join("".join(self._heading_parts).split())
            self._in_heading = False
            self._heading_parts = []
        if self._slide is not None and self._in_notes and tag in {"aside", "div"}:
            self._slide.note_text = " ".join("".join(self._note_parts).split())
            self._in_notes = False
            self._note_parts = []
        if (
            tag == "section"
            and self._slide is not None
            and self._slide_section_depth == self._section_depth
        ):
            self._slide = None
            self._slide_section_depth = None
            self._in_heading = False
            self._in_notes = False
        if tag == "section" and self._section_depth:
            self._section_depth -= 1
        if tag in self.stack:
            matching_index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[matching_index:]

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_heading:
            self._heading_parts.append(data)
        if self._in_notes:
            self._note_parts.append(data)
        if self._in_style:
            self._style_parts.append(data)
        if self._in_executable_script:
            self._script_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())


class VisibleSlideParser(HTMLParser):
    """Collect visible text nodes using the controlled benchmark contract."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.slides: list[list[str]] = []
        self._slide_depth = 0
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        if tag == "section" and "slide" in classes and self._slide_depth == 0:
            self.slides.append([])
            self._slide_depth = 1
            return
        if self._slide_depth:
            if tag not in VOID_TAGS:
                self._slide_depth += 1
            if tag in {"script", "style"} or "speaker-notes" in classes:
                self._ignored_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if not self._slide_depth:
            return
        if self._ignored_depth and tag in {"script", "style", "aside", "div"}:
            self._ignored_depth -= 1
        self._slide_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._slide_depth and not self._ignored_depth:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.slides[-1].append(value)


def copy_tokens(nodes: Sequence[str]) -> Counter[str]:
    """Return the benchmark-compatible, case-insensitive visible token multiset."""

    return Counter(
        token.casefold()
        for token in re.findall(r"[\w$%+.-]+", " ".join(nodes), flags=re.UNICODE)
    )


def expected_content_spec_slides(
    content_spec: Mapping[str, Any],
) -> tuple[list[list[str]] | None, str | None]:
    """Extract mechanically controlled per-slide copy from a benchmark deck spec."""

    raw_slides = content_spec.get("slides")
    if not isinstance(raw_slides, list):
        return None, "root field 'slides' must be a JSON array"

    expected: list[list[str]] = []
    for slide_index, raw_slide in enumerate(raw_slides, start=1):
        if not isinstance(raw_slide, Mapping):
            return None, f"slides[{slide_index - 1}] must be a JSON object"
        missing_fields = [
            field
            for field in (*CONTENT_SPEC_TEXT_FIELDS, *CONTENT_SPEC_TRAILING_FIELDS)
            if field not in raw_slide
        ]
        if "kpis" not in raw_slide:
            missing_fields.append("kpis")
        if missing_fields:
            return (
                None,
                f"slides[{slide_index - 1}] is missing required fields: "
                f"{sorted(missing_fields)}",
            )

        raw_kpis = raw_slide["kpis"]
        if not isinstance(raw_kpis, list):
            return None, f"slides[{slide_index - 1}].kpis must be a JSON array"

        nodes = [str(raw_slide[field]) for field in CONTENT_SPEC_TEXT_FIELDS]
        for kpi_index, raw_kpi in enumerate(raw_kpis):
            if not isinstance(raw_kpi, Mapping):
                return (
                    None,
                    f"slides[{slide_index - 1}].kpis[{kpi_index}] must be a JSON object",
                )
            missing_kpi_fields = [
                field for field in ("label", "value") if field not in raw_kpi
            ]
            if missing_kpi_fields:
                return (
                    None,
                    f"slides[{slide_index - 1}].kpis[{kpi_index}] is missing "
                    f"required fields: {missing_kpi_fields}",
                )
            nodes.extend((str(raw_kpi["label"]), str(raw_kpi["value"])))
        nodes.extend(str(raw_slide[field]) for field in CONTENT_SPEC_TRAILING_FIELDS)
        expected.append(nodes)
    return expected, None


def exact_content_spec_copy(
    html_text: str, content_spec: Mapping[str, Any]
) -> tuple[bool, str]:
    """Compare each slide's visible-token multiset with the controlling spec."""

    expected_slides, spec_error = expected_content_spec_slides(content_spec)
    if expected_slides is None:
        return False, f"Invalid controlling content spec: {spec_error}."

    visible_parser = VisibleSlideParser()
    visible_parser.feed(html_text)
    visible_parser.close()
    observed_slides = visible_parser.slides
    differences: list[dict[str, Any]] = []
    for slide_index in range(max(len(expected_slides), len(observed_slides))):
        expected_tokens = copy_tokens(
            expected_slides[slide_index] if slide_index < len(expected_slides) else []
        )
        observed_tokens = copy_tokens(
            observed_slides[slide_index] if slide_index < len(observed_slides) else []
        )
        missing = expected_tokens - observed_tokens
        extra = observed_tokens - expected_tokens
        if missing or extra:
            differences.append(
                {
                    "slide": slide_index + 1,
                    "missing": {token: missing[token] for token in sorted(missing)},
                    "extra": {token: extra[token] for token in sorted(extra)},
                }
            )

    if len(expected_slides) != len(observed_slides) or differences:
        details = {
            "expected_slide_count": len(expected_slides),
            "observed_slide_count": len(observed_slides),
            "slide_differences": differences,
        }
        return (
            False,
            "Visible copy differs from the controlling content spec: "
            f"{json.dumps(details, ensure_ascii=False, sort_keys=True)}.",
        )
    return (
        True,
        f"Visible copy exactly matches the controlling content spec on "
        f"{len(expected_slides)} slides.",
    )


def load_runtime(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("clara_html_deck_runtime", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load Clara runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def default_runtime_path() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts" / "html_deck_runtime.py"


def classify_resource(value: str) -> str:
    lowered = value.lower()
    if lowered.startswith(("data:", "blob:", "#")):
        return "embedded"
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} or value.startswith("//"):
        return "remote"
    return "local"


def load_static_local_resources(
    parser: DeckParser, resource_root: Path | None
) -> tuple[list[str], list[str], list[str]]:
    """Read only referenced local CSS/JS and report missing or escaping resources."""

    issues: list[str] = []
    css_bodies: list[str] = []
    script_bodies: list[str] = []
    if resource_root is None:
        local_refs = [
            value
            for _, _, value in parser.resource_refs
            if classify_resource(value) == "local"
        ]
        return (
            (["resource_root is required for local resources"] if local_refs else []),
            [],
            [],
        )
    root = resource_root.expanduser().resolve()
    for tag, attribute, value in parser.resource_refs:
        if classify_resource(value) != "local":
            continue
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc:
            issues.append(f"unsupported local URL in {tag}[{attribute}]: {value}")
            continue
        relative = Path(unquote(parsed.path))
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            issues.append(f"resource escapes deck root: {value}")
            continue
        if not candidate.is_file():
            issues.append(f"missing local resource: {value}")
            continue
        try:
            if candidate.suffix.lower() == ".css":
                css_bodies.append(candidate.read_text(encoding="utf-8"))
            elif candidate.suffix.lower() in {".js", ".mjs"}:
                script_bodies.append(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            issues.append(f"unreadable local resource {value}: {exc}")
    return issues, css_bodies, script_bodies


def validate_html_text(
    html_text: str,
    *,
    label: str,
    runtime_path: Path,
    publication_id: str | None = None,
    allow_template_examples: bool = False,
    max_bytes: int = 1_500_000,
    profile: str = "stage",
    resource_root: Path | None = None,
    content_spec: Mapping[str, Any] | None = None,
    content_spec_error: str | None = None,
    content_spec_label: str | None = None,
) -> dict[str, Any]:
    if profile not in VALIDATION_PROFILES:
        raise ValueError(f"Unsupported validation profile: {profile}")
    parser = DeckParser()
    parser.feed(html_text)
    parser.close()
    checks: list[Check] = []

    def add(
        code: str,
        condition: bool,
        ok: str,
        failure: str,
        *,
        severity: str = "error",
        location: str | None = None,
    ) -> None:
        checks.append(
            Check(
                code,
                severity,
                "pass" if condition else "fail",
                ok if condition else failure,
                location,
            )
        )

    add(
        "document.doctype",
        parser.doctype,
        "HTML5 doctype is present.",
        "Missing HTML5 doctype.",
    )
    add(
        "document.structure",
        (parser.html_count, parser.head_count, parser.body_count) == (1, 1, 1),
        "Document has one html, head, and body element.",
        "Document must have exactly one html, head, and body element.",
    )
    add(
        "document.title",
        bool(parser.title),
        "Document title is present.",
        "Document title is empty or missing.",
    )
    add(
        "document.language",
        bool(parser.language),
        f"Document language is {parser.language!r}.",
        "Document language is missing.",
        severity="warning",
    )
    viewport_ok = any(
        item.get("name", "").lower() == "viewport"
        and "width=device-width" in item.get("content", "").lower()
        for item in parser.meta
    )
    add(
        "document.viewport",
        viewport_ok,
        "Viewport metadata is present.",
        "Viewport metadata is missing or incomplete.",
    )
    robots = next(
        (
            item.get("content", "")
            for item in parser.meta
            if item.get("name", "").lower() == "robots"
        ),
        "",
    )
    add(
        "publication.noindex",
        "noindex" in robots.lower(),
        "Publication defaults to noindex.",
        "Missing noindex robots directive.",
        severity="warning",
    )

    root_ok = len(parser.deck_roots) == 1 and parser.main_count == 1
    add(
        "deck.root",
        root_ok,
        "Exactly one Clara deck root is present.",
        "Expected exactly one main Clara deck root.",
    )
    stage_ok = root_ok and parser.deck_roots[0].get("data-clara-deck-mode") == "stage"
    add(
        "deck.profile",
        stage_ok,
        "Deck declares the stage profile.",
        'Deck root must declare data-clara-deck-mode="stage".',
    )
    add(
        "slides.present",
        bool(parser.slides),
        f"Found {len(parser.slides)} slides.",
        "Deck has no .slide sections.",
    )

    slide_ids = [slide.id for slide in parser.slides]
    missing_slide_ids = [slide.index for slide in parser.slides if not slide.id]
    add(
        "slides.ids_present",
        not missing_slide_ids,
        "Every slide has an ID.",
        f"Slides missing IDs: {missing_slide_ids}.",
    )
    invalid_slide_ids = [
        slide.id
        for slide in parser.slides
        if slide.id and not SLIDE_ID_RE.fullmatch(slide.id)
    ]
    add(
        "slides.ids_safe",
        not invalid_slide_ids,
        "All slide IDs are URL-safe.",
        f"Invalid slide IDs: {invalid_slide_ids}.",
    )
    duplicate_slide_ids = sorted(
        {value for value in slide_ids if value and slide_ids.count(value) > 1}
    )
    add(
        "slides.ids_unique",
        not duplicate_slide_ids,
        "All slide IDs are unique.",
        f"Duplicate slide IDs: {duplicate_slide_ids}.",
    )
    missing_titles = [
        slide.id or str(slide.index)
        for slide in parser.slides
        if not slide.title.strip()
    ]
    add(
        "slides.titles",
        not missing_titles,
        "Every slide has data-slide-title.",
        f"Slides missing data-slide-title: {missing_titles}.",
    )
    missing_chapters = [
        slide.id or str(slide.index)
        for slide in parser.slides
        if not slide.chapter.strip()
    ]
    add(
        "slides.chapters",
        not missing_chapters,
        "Every slide belongs to a chapter.",
        f"Slides missing data-chapter: {missing_chapters}.",
    )
    active_count = sum(1 for slide in parser.slides if slide.active)
    add(
        "slides.initial_active",
        active_count == 1,
        "Exactly one initial active slide is declared.",
        f"Expected one initial active slide; found {active_count}.",
    )
    missing_notes = [
        slide.id or str(slide.index)
        for slide in parser.slides
        if not slide.has_notes or not slide.note_text
    ]
    add(
        "slides.notes",
        not missing_notes,
        "Every slide has non-empty speaker notes.",
        f"Slides missing speaker notes: {missing_notes}.",
    )

    bad_fragments: list[str] = []
    gapped_fragments: list[str] = []
    for slide in parser.slides:
        if not slide.fragment_values:
            continue
        try:
            values = [int(value) for value in slide.fragment_values]
        except ValueError:
            bad_fragments.append(slide.id)
            continue
        if any(value <= 0 for value in values):
            bad_fragments.append(slide.id)
            continue
        distinct = sorted(set(values))
        if distinct != list(range(1, max(distinct) + 1)):
            gapped_fragments.append(slide.id)
    add(
        "fragments.positive",
        not bad_fragments,
        "Fragment steps are positive integers.",
        f"Slides with invalid fragment steps: {bad_fragments}.",
    )
    add(
        "fragments.contiguous",
        not gapped_fragments,
        "Fragment steps are contiguous within each slide.",
        f"Slides with gapped fragment steps: {gapped_fragments}.",
    )

    duplicate_ids = sorted(
        {value for value in parser.ids if value and parser.ids.count(value) > 1}
    )
    add(
        "document.ids_unique",
        not duplicate_ids,
        "All document IDs are unique.",
        f"Duplicate document IDs: {duplicate_ids}.",
    )
    broken_hashes = sorted(
        {value for value in parser.href_fragments if value and value not in parser.ids}
    )
    add(
        "navigation.hash_targets",
        not broken_hashes,
        "All internal hash targets exist.",
        f"Broken hash targets: {broken_hashes}.",
    )

    resource_issues = [
        (tag, attr, value, classify_resource(value))
        for tag, attr, value in parser.resource_refs
        if classify_resource(value) != "embedded"
    ]
    add(
        "resources.self_contained",
        not resource_issues,
        "No external or local runtime resources are required.",
        f"Non-embedded resources: {resource_issues}.",
    )
    add(
        "security.executable_attributes",
        not parser.executable_attribute_issues,
        "No executable event handlers or URL attributes are present.",
        "Executable attributes found: " f"{parser.executable_attribute_issues[:12]}.",
    )
    local_issues, local_css, local_scripts = load_static_local_resources(
        parser, resource_root if profile == "static" else None
    )
    css_text = "\n".join(parser.style_bodies + parser.style_attrs + local_css)
    script_text = "\n".join(parser.script_bodies + local_scripts)
    remote_resources = [
        (tag, attribute, value)
        for tag, attribute, value in parser.resource_refs
        if classify_resource(value) == "remote"
    ]
    add(
        "resources.no_remote",
        not remote_resources,
        "No remote runtime resources are referenced.",
        f"Remote runtime resources found: {remote_resources}.",
    )
    add(
        "resources.local_available",
        not local_issues,
        "Every referenced local resource is available inside the deck root.",
        f"Local resource issues: {local_issues}.",
    )
    css_remote = re.findall(
        r"@import\s+[^;]+|url\(\s*['\"]?(?!data:|#)([^)'\"]+)",
        css_text,
        flags=re.IGNORECASE,
    )
    add(
        "resources.css_embedded",
        not css_remote,
        "CSS contains no external imports or URLs.",
        f"CSS external references found: {css_remote}.",
    )
    css_network_references = re.findall(
        r"(?:@import\s+[^;]*(?:https?:)?//|url\(\s*['\"]?(?:https?:)?//)",
        css_text,
        flags=re.IGNORECASE,
    )
    add(
        "resources.css_no_remote",
        not css_network_references,
        "CSS contains no remote imports or URLs.",
        f"Remote CSS references found: {css_network_references}.",
    )
    network_tokens = sorted(
        set(
            re.findall(r"\b(fetch|WebSocket|EventSource|XMLHttpRequest)\b", script_text)
        )
    )
    add(
        "resources.no_network_api",
        not network_tokens,
        "No dynamic network APIs are used.",
        f"Dynamic network APIs found: {network_tokens}.",
    )
    dangerous_js = bool(re.search(r"\beval\s*\(|\bnew\s+Function\s*\(", script_text))
    add(
        "script.no_dynamic_eval",
        not dangerous_js,
        "No dynamic JavaScript evaluation is used.",
        "Found eval() or new Function().",
    )
    static_navigation_tokens = ["keydown", "ArrowRight", "ArrowLeft"]
    missing_static_navigation = [
        token for token in static_navigation_tokens if token not in script_text
    ]
    add(
        "interaction.static_navigation",
        not missing_static_navigation,
        "The static deck provides the keyboard navigation allowed by its brief.",
        f"Static keyboard navigation tokens missing: {missing_static_navigation}.",
    )

    non_executable_html = re.sub(
        r"<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>",
        "",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    placeholders = sorted(
        set(match.group(0) for match in PLACEHOLDER_RE.finditer(non_executable_html))
    )
    add(
        "content.placeholders",
        allow_template_examples or not placeholders,
        (
            "No unresolved placeholders remain."
            if not placeholders
            else "Template placeholders allowed for this preview."
        ),
        f"Unresolved placeholders: {placeholders[:12]}.",
    )
    has_template_examples = "data-template-example" in html_text
    add(
        "content.template_examples",
        allow_template_examples or not has_template_examples,
        (
            "No template example markers remain."
            if not has_template_examples
            else "Template examples allowed for this preview."
        ),
        "Template example markers remain in the deck.",
    )
    add(
        "content.no_box_shadow",
        "box-shadow" not in css_text.lower(),
        "No decorative box-shadow declarations are present.",
        "Decorative box-shadow declarations are not allowed in Clara human-visible decks.",
    )
    add(
        "content.no_visible_counter",
        "slideCounter" not in parser.ids and "slideCounter" not in parser.class_names,
        "No persistent visible slide counter is present.",
        "Persistent visible slide counters are not allowed.",
    )
    if content_spec is not None or content_spec_error is not None:
        if content_spec_error is not None:
            exact_copy_ok = False
            exact_copy_message = (
                f"Unable to load controlling content spec: {content_spec_error}."
            )
        elif content_spec is None:
            exact_copy_ok = False
            exact_copy_message = "Controlling content spec is missing."
        else:
            exact_copy_ok, exact_copy_message = exact_content_spec_copy(
                html_text, content_spec
            )
        add(
            "content.exact_spec_copy",
            exact_copy_ok,
            exact_copy_message,
            exact_copy_message,
            location=content_spec_label,
        )

    required_ids = {
        "prevBtn",
        "nextBtn",
        "overviewBtn",
        "helpBtn",
        "fullscreenBtn",
        "notesPanel",
        "overviewOverlay",
        "helpOverlay",
    }
    missing_controls = sorted(required_ids - set(parser.ids))
    add(
        "interaction.controls",
        not missing_controls,
        "Required controls and overlays are present.",
        f"Missing controls or overlays: {missing_controls}.",
    )
    interaction_tokens = [
        "keydown",
        "hashchange",
        "requestFullscreen",
        "touchstart",
        "wheel",
        "beforeprint",
        "afterprint",
        "clara:slidechange",
    ]
    missing_tokens = [token for token in interaction_tokens if token not in html_text]
    add(
        "interaction.contract",
        not missing_tokens,
        "Keyboard, hash, touch, wheel, print, and slide-change hooks are present.",
        f"Missing interaction hooks: {missing_tokens}.",
    )
    add(
        "accessibility.reduced_motion",
        "prefers-reduced-motion" in html_text,
        "Reduced-motion treatment is present.",
        "Missing prefers-reduced-motion treatment.",
    )
    add(
        "publication.print",
        "@media print" in html_text and "@page" in html_text,
        "Print treatment is present.",
        "Missing print treatment.",
    )
    add(
        "accessibility.svg",
        parser.svg_total == parser.svg_accessible,
        f"All {parser.svg_total} SVG visuals are labelled.",
        f"Only {parser.svg_accessible} of {parser.svg_total} SVG visuals are labelled.",
        severity="warning",
    )

    ledger: dict[str, Any] | None = None
    ledger_error = ""
    try:
        embedded = extract_embedded_ledger(html_text)
        if embedded is None:
            ledger_error = "Standalone deck has no embedded Clara content ledger."
        else:
            ledger = validate_content_ledger(
                embedded,
                slide_ids=[slide.id for slide in parser.slides],
            )
    except (json.JSONDecodeError, ValueError) as exc:
        ledger_error = str(exc)
    add(
        "provenance.ledger",
        ledger is not None,
        "Embedded content ledger covers every slide.",
        f"Invalid or missing content ledger: {ledger_error}",
    )
    if ledger is not None:
        source_ids = {source["id"] for source in ledger["sources"]}
        slide_claim_ids = {
            slide["slide_id"]: {claim["id"] for claim in slide["claims"]}
            for slide in ledger["slides"]
        }
        referenced_sources = {
            source_id for slide in parser.slides for source_id in slide.source_refs
        }
        missing_sources = sorted(referenced_sources - source_ids)
        missing_claims = sorted(
            {
                f"{slide.id}:{claim_id}"
                for slide in parser.slides
                for claim_id in slide.claim_refs
                if claim_id not in slide_claim_ids.get(slide.id, set())
            }
        )
        add(
            "provenance.source_refs",
            not missing_sources,
            "All rendered source references resolve to the content ledger.",
            f"Unknown rendered source references: {missing_sources}.",
        )
        add(
            "provenance.claim_refs",
            not missing_claims,
            "All rendered claim references resolve to their slide ledger entries.",
            f"Unknown or cross-slide rendered claim references: {missing_claims}.",
        )
    else:
        add(
            "provenance.source_refs",
            False,
            "All rendered source references resolve to the content ledger.",
            "Source references cannot be checked without a valid ledger.",
        )
        add(
            "provenance.claim_refs",
            False,
            "All rendered claim references resolve to the content ledger.",
            "Claim references cannot be checked without a valid ledger.",
        )

    runtime_ok = False
    runtime_message = ""
    try:
        runtime = load_runtime(runtime_path)
        runtime.assert_html_deck_runtime(html_text, label=label, profile="stage")
        runtime_ok = True
        runtime_message = "Clara stage runtime is present and profile-compatible."
    except Exception as exc:  # noqa: BLE001 - report runtime failures deterministically
        runtime_message = str(exc)
    add(
        "runtime.stage",
        runtime_ok,
        runtime_message,
        f"Invalid or missing Clara stage runtime: {runtime_message}",
    )

    if publication_id is not None:
        add(
            "publication.id",
            bool(PUBLICATION_ID_RE.fullmatch(publication_id)),
            "Publication ID is a 64-character lowercase hexadecimal value.",
            f"Invalid publication ID: {publication_id!r}.",
        )

    byte_count = len(html_text.encode("utf-8"))
    add(
        "document.size",
        byte_count <= max_bytes,
        f"Standalone HTML is {byte_count} bytes.",
        f"Standalone HTML exceeds {max_bytes} bytes ({byte_count}).",
        severity="warning",
    )

    if profile == "static":
        strict_only_codes = {
            "document.viewport",
            "publication.noindex",
            "deck.root",
            "deck.profile",
            "slides.ids_present",
            "slides.ids_safe",
            "slides.titles",
            "slides.chapters",
            "slides.initial_active",
            "slides.notes",
            "resources.self_contained",
            "resources.css_embedded",
            "interaction.controls",
            "interaction.contract",
            "accessibility.reduced_motion",
            "publication.print",
            "provenance.ledger",
            "provenance.source_refs",
            "provenance.claim_refs",
            "runtime.stage",
            "publication.id",
        }
        checks = [
            (
                replace(
                    check,
                    severity="info",
                    status="skip",
                    message="Not required by the static-deck compatibility profile.",
                )
                if check.code in strict_only_codes
                else check
            )
            for check in checks
        ]
    else:
        checks = [
            (
                replace(
                    check,
                    severity="info",
                    status="skip",
                    message="Only applicable to the static-deck compatibility profile.",
                )
                if check.code == "interaction.static_navigation"
                else check
            )
            for check in checks
        ]

    error_count = sum(
        1 for check in checks if check.status == "fail" and check.severity == "error"
    )
    warning_count = sum(
        1 for check in checks if check.status == "fail" and check.severity == "warning"
    )
    passed_count = sum(1 for check in checks if check.status == "pass")
    report = {
        "schema_version": SCHEMA_VERSION,
        "result": "pass" if error_count == 0 else "fail",
        "profile": profile,
        "input": {
            "label": label,
            "bytes": byte_count,
            "sha256": hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
        },
        "deck": {
            "title": parser.title,
            "language": parser.language,
            "slide_count": len(parser.slides),
            "note_count": sum(
                1 for slide in parser.slides if slide.has_notes and slide.note_text
            ),
            "fragment_element_count": sum(
                len(slide.fragment_values) for slide in parser.slides
            ),
            "slides": [
                {
                    "index": slide.index,
                    "id": slide.id,
                    "title": slide.title,
                    "chapter": slide.chapter,
                    "fragment_steps": sorted(
                        {
                            int(value)
                            for value in slide.fragment_values
                            if value.isdigit()
                        }
                    ),
                    "has_notes": slide.has_notes and bool(slide.note_text),
                }
                for slide in parser.slides
            ],
        },
        "resources": {
            "embedded": sum(
                1
                for _, _, value in parser.resource_refs
                if classify_resource(value) == "embedded"
            ),
            "local": sum(
                1
                for _, _, value in parser.resource_refs
                if classify_resource(value) == "local"
            ),
            "remote": sum(
                1
                for _, _, value in parser.resource_refs
                if classify_resource(value) == "remote"
            ),
        },
        "provenance": {
            "ledger_present": ledger is not None,
            "source_count": len(ledger["sources"]) if ledger is not None else 0,
            "claim_count": (
                sum(len(slide["claims"]) for slide in ledger["slides"])
                if ledger is not None
                else 0
            ),
        },
        "checks": [asdict(check) for check in checks],
        "summary": {
            "passed": passed_count,
            "warnings": warning_count,
            "errors": error_count,
        },
        "manual_review": [
            "Confirm source-document fidelity and factual correctness.",
            "Inspect every slide for rendered overflow, clipping, contrast, and editorial quality.",
            "Exercise JavaScript navigation, fragments, overlays, notes, fullscreen, touch, and hashes.",
            "Check browser console output and the Capture Handle slide ID/title transition.",
        ],
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--runtime", type=Path, default=default_runtime_path())
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--content-spec",
        type=Path,
        help="Controlling deck_spec.json for exact per-slide visible-copy validation.",
    )
    parser.add_argument("--allow-readable-path", action="store_true")
    parser.add_argument("--allow-template-examples", action="store_true")
    parser.add_argument("--warnings-as-errors", action="store_true")
    parser.add_argument("--max-bytes", type=int, default=1_500_000)
    parser.add_argument(
        "--profile", choices=sorted(VALIDATION_PROFILES), default="stage"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        input_path = args.input.expanduser().resolve()
        html_text = input_path.read_text(encoding="utf-8")
        publication_id = None if args.allow_readable_path else input_path.parent.name
        content_spec: Mapping[str, Any] | None = None
        content_spec_error: str | None = None
        content_spec_label: str | None = None
        if args.content_spec is not None:
            content_spec_path = args.content_spec.expanduser().resolve()
            content_spec_label = str(content_spec_path)
            try:
                parsed_content_spec = json.loads(
                    content_spec_path.read_text(encoding="utf-8")
                )
                if isinstance(parsed_content_spec, Mapping):
                    content_spec = parsed_content_spec
                else:
                    content_spec_error = "JSON root must be an object"
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                content_spec_error = str(exc)
        report = validate_html_text(
            html_text,
            label=str(input_path),
            runtime_path=args.runtime.expanduser().resolve(),
            publication_id=publication_id,
            allow_template_examples=args.allow_template_examples,
            max_bytes=args.max_bytes,
            profile=args.profile,
            resource_root=input_path.parent,
            content_spec=content_spec,
            content_spec_error=content_spec_error,
            content_spec_label=content_spec_label,
        )
        rendered = (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        if args.report:
            report_path = args.report.expanduser().resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        failed = report["result"] != "pass"
        if args.warnings_as_errors and report["summary"]["warnings"]:
            failed = True
        return 1 if failed else 0
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
