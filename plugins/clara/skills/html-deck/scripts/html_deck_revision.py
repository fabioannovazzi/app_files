#!/usr/bin/env python3
"""Shared inspection and preservation contracts for Clara HTML deck revisions.

The deterministic rules in this module are limited to mechanically verifiable
facts: JSON shape, stable ID matching, normalized DOM equality, and declared
add/remove/rename operations. They do not judge whether an edit is meaningful,
factually correct, or visually successful.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "COMPARISON_SCHEMA_VERSION",
    "INSPECTION_SCHEMA_VERSION",
    "REVISION_MAP_SCHEMA_VERSION",
    "DeckInspection",
    "compare_deck_revision",
    "inspect_deck",
    "load_json_object",
    "render_json",
    "validate_revision_map",
    "write_json_report",
]


INSPECTION_SCHEMA_VERSION = "clara.html_deck_inventory.v1"
REVISION_MAP_SCHEMA_VERSION = "clara.html_deck_revision_map.v1"
REVISION_MAP_VALIDATION_SCHEMA_VERSION = "clara.html_deck_revision_map_validation.v1"
COMPARISON_SCHEMA_VERSION = "clara.html_deck_revision_comparison.v1"
WORK_SCHEMA_VERSION = "clara.html_deck_work.v1"
SLIDE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
GLOBAL_EDIT_SCOPES = frozenset(
    {
        "content-ledger",
        "custom-css",
        "deck-plan",
        "metadata",
        "runtime",
        "shell",
        "styles",
    }
)
TRUE_VALUES = {"", "1", "on", "true", "yes"}
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


@dataclass
class Issue:
    code: str
    message: str
    location: str | None = None
    severity: str = "error"

    def as_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "location": self.location,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class DomNode:
    tag: str
    attrs: dict[str, str]
    children: list[DomNode | str] = field(default_factory=list)
    parent: DomNode | None = None


@dataclass
class ComponentRecord:
    node: DomNode
    path: str
    component_id: str | None
    dom_id: str | None
    protected: bool
    protection_reason: str | None
    fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "addressable": self.component_id is not None,
            "classes": sorted(class_tokens(self.node)),
            "component_id": self.component_id,
            "dom_id": self.dom_id,
            "normalized_dom_fingerprint": self.fingerprint,
            "path": self.path,
            "protection": {
                "declared_by": "data-revision-protected" if self.protected else None,
                "protected": self.protected,
                "reason": self.protection_reason,
            },
            "tag": self.node.tag,
        }


@dataclass
class SlideRecord:
    node: DomNode
    index: int
    slide_id: str
    title: str
    chapter: str
    protected: bool
    protection_reason: str | None
    fingerprint: str
    ledger_fingerprint: str | None
    components: list[ComponentRecord]

    @property
    def component_by_id(self) -> dict[str, ComponentRecord]:
        return {
            component.component_id: component
            for component in self.components
            if component.component_id is not None
        }

    def as_dict(self) -> dict[str, Any]:
        protected_components = [
            component.component_id
            for component in self.components
            if component.protected and component.component_id is not None
        ]
        return {
            "chapter": self.chapter,
            "component_count": len(self.components),
            "components": [component.as_dict() for component in self.components],
            "id": self.slide_id,
            "index": self.index,
            "normalized_dom_fingerprint": self.fingerprint,
            "ledger_fingerprint": self.ledger_fingerprint,
            "protection": {
                "declared_by": "data-revision-protected" if self.protected else None,
                "protected": self.protected,
                "reason": self.protection_reason,
            },
            "protected_component_ids": protected_components,
            "title": self.title,
        }


@dataclass
class DeckInspection:
    input_path: Path
    input_kind: str
    content_sha256: str
    deck_fingerprint: str
    global_fingerprints: dict[str, str]
    title: str
    slides: list[SlideRecord]
    issues: list[Issue]

    @property
    def slide_by_id(self) -> dict[str, SlideRecord]:
        return {slide.slide_id: slide for slide in self.slides if slide.slide_id}

    @property
    def result(self) -> str:
        return (
            "fail"
            if any(issue.severity == "error" for issue in self.issues)
            else "pass"
        )

    def as_report(self) -> dict[str, Any]:
        return {
            "schema_version": INSPECTION_SCHEMA_VERSION,
            "result": self.result,
            "input": {
                "content_sha256": self.content_sha256,
                "kind": self.input_kind,
                "path": str(self.input_path),
            },
            "deck": {
                "global_fingerprints": self.global_fingerprints,
                "normalized_dom_fingerprint": self.deck_fingerprint,
                "slide_count": len(self.slides),
                "slides": [slide.as_dict() for slide in self.slides],
                "title": self.title,
            },
            "issues": [issue.as_dict() for issue in self.issues],
            "summary": issue_summary(self.issues),
        }


class DomParser(HTMLParser):
    """Build the small DOM subset needed for deterministic deck inspection."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = DomNode("#document", {})
        self.stack = [self.root]
        self.issues: list[Issue] = []

    @staticmethod
    def attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {name.lower(): value or "" for name, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        node = DomNode(normalized_tag, self.attrs_dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if normalized_tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = DomNode(tag.lower(), self.attrs_dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        matching_index = next(
            (
                index
                for index in range(len(self.stack) - 1, 0, -1)
                if self.stack[index].tag == normalized_tag
            ),
            None,
        )
        if matching_index is None:
            self.issues.append(
                Issue(
                    "dom.unmatched_end_tag",
                    f"Ignoring unmatched closing tag </{normalized_tag}>.",
                )
            )
            return
        if matching_index != len(self.stack) - 1:
            unclosed = [node.tag for node in self.stack[matching_index + 1 :]]
            self.issues.append(
                Issue(
                    "dom.implicitly_closed_tags",
                    f"Closing </{normalized_tag}> implicitly closes {unclosed}.",
                )
            )
        del self.stack[matching_index:]

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)

    def finish(self) -> None:
        unclosed = [node.tag for node in self.stack[1:]]
        if unclosed:
            self.issues.append(
                Issue(
                    "dom.unclosed_tags", f"Unclosed tags at end of input: {unclosed}."
                )
            )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    report_path = path.expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_json(payload), encoding="utf-8")


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Revision map must be a JSON object")
    return payload


def issue_summary(issues: Iterable[Issue]) -> dict[str, int]:
    materialized = list(issues)
    return {
        "errors": sum(issue.severity == "error" for issue in materialized),
        "warnings": sum(issue.severity == "warning" for issue in materialized),
    }


def class_tokens(node: DomNode) -> set[str]:
    return {token for token in node.attrs.get("class", "").split() if token}


def is_slide(node: DomNode) -> bool:
    return node.tag == "section" and "slide" in class_tokens(node)


def is_protected(node: DomNode) -> bool:
    if "data-revision-protected" not in node.attrs:
        return False
    return node.attrs["data-revision-protected"].strip().lower() in TRUE_VALUES


def protection_reason(node: DomNode) -> str | None:
    value = " ".join(node.attrs.get("data-revision-protection-reason", "").split())
    return value or None


def stable_component_id(node: DomNode) -> str | None:
    component_id = node.attrs.get("data-component-id", "").strip()
    dom_id = node.attrs.get("id", "").strip()
    return component_id or dom_id or None


def descendant_nodes(node: DomNode) -> Iterable[DomNode]:
    for child in node.children:
        if isinstance(child, DomNode):
            yield child
            yield from descendant_nodes(child)


def normalized_attrs(
    node: DomNode,
    *,
    override_slide_id: bool = False,
) -> list[tuple[str, str]]:
    attrs = dict(node.attrs)
    if override_slide_id:
        attrs["id"] = "__slide_id__"
    normalized: list[tuple[str, str]] = []
    for name, raw_value in attrs.items():
        value = raw_value
        if name == "class":
            value = " ".join(sorted(value.split()))
        elif name == "style":
            value = re.sub(r"\s+", " ", value).strip()
            value = re.sub(r"\s*([:;,])\s*", r"\1", value)
        else:
            value = " ".join(value.split())
        normalized.append((name, value))
    return sorted(normalized)


def canonical_dom(
    node: DomNode,
    *,
    masked_component_ids: frozenset[str] = frozenset(),
    override_slide_id: bool = False,
    root: bool = True,
) -> str:
    component_id = None if root else stable_component_id(node)
    if component_id is not None and component_id in masked_component_ids:
        return f'<revision-target component-id="{json.dumps(component_id)[1:-1]}"/>'
    attrs = normalized_attrs(node, override_slide_id=override_slide_id and root)
    rendered_attrs = "".join(
        f" {name}={json.dumps(value, ensure_ascii=False)}" for name, value in attrs
    )
    rendered_children: list[str] = []
    preserves_text_whitespace = (
        node.tag in {"pre", "script", "style", "textarea"}
        or node.attrs.get("xml:space", "").lower() == "preserve"
    )
    for child in node.children:
        if isinstance(child, DomNode):
            rendered_children.append(
                canonical_dom(
                    child,
                    masked_component_ids=masked_component_ids,
                    override_slide_id=False,
                    root=False,
                )
            )
        else:
            normalized_text = (
                child.replace("\r\n", "\n").replace("\r", "\n")
                if preserves_text_whitespace
                else " ".join(child.split())
            )
            if normalized_text:
                rendered_children.append(
                    json.dumps(normalized_text, ensure_ascii=False)
                )
    return f"<{node.tag}{rendered_attrs}>{''.join(rendered_children)}</{node.tag}>"


def node_fingerprint(
    node: DomNode,
    *,
    masked_component_ids: frozenset[str] = frozenset(),
    override_slide_id: bool = False,
) -> str:
    return sha256_text(
        canonical_dom(
            node,
            masked_component_ids=masked_component_ids,
            override_slide_id=override_slide_id,
        )
    )


def relative_component_paths(slide: DomNode) -> list[tuple[DomNode, str]]:
    result: list[tuple[DomNode, str]] = []

    def walk(parent: DomNode, parent_path: str) -> None:
        element_index = 0
        for child in parent.children:
            if not isinstance(child, DomNode):
                continue
            element_index += 1
            path = f"{parent_path}/{child.tag}[{element_index}]"
            result.append((child, path))
            walk(child, path)

    walk(slide, "")
    return result


def json_file_fingerprint(path: Path) -> str:
    """Fingerprint JSON by value so formatting-only changes remain irrelevant."""

    if not path.is_file():
        return sha256_text("__missing__")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return sha256_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )


def text_file_fingerprint(path: Path) -> str:
    """Fingerprint an authored text resource exactly."""

    if not path.is_file():
        return sha256_text("__missing__")
    return sha256_text(path.read_text(encoding="utf-8"))


def ledger_fingerprints(payload: Any) -> tuple[str, dict[str, str]]:
    """Separate global source metadata from slide-local ledger entries."""

    if not isinstance(payload, dict):
        return sha256_text("__invalid__"), {}
    slides = payload.get("slides", [])
    global_payload = {key: value for key, value in payload.items() if key != "slides"}
    global_fingerprint = sha256_text(
        json.dumps(
            global_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    slide_fingerprints: dict[str, str] = {}
    if isinstance(slides, list):
        for entry in slides:
            if not isinstance(entry, dict):
                continue
            slide_id = str(entry.get("slide_id", "")).strip()
            if not slide_id:
                continue
            normalized_entry = {
                key: value for key, value in entry.items() if key != "slide_id"
            }
            slide_fingerprints[slide_id] = sha256_text(
                json.dumps(
                    normalized_entry,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
    return global_fingerprint, slide_fingerprints


def read_deck_source(
    path: Path,
) -> tuple[Path, str, str, str, dict[str, str], dict[str, str]]:
    input_path = path.expanduser().resolve()
    if input_path.is_dir():
        slides_path = input_path / "slides.html"
        index_path = input_path / "index.html"
        if slides_path.is_file():
            metadata_path = input_path / "deck.json"
            if not metadata_path.is_file():
                raise ValueError(
                    f"Clara work folder is missing deck.json: {input_path}"
                )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if (
                not isinstance(metadata, dict)
                or metadata.get("schema_version") != WORK_SCHEMA_VERSION
            ):
                raise ValueError(
                    f"Unsupported Clara work folder metadata: {metadata_path}"
                )
            title = str(metadata.get("title", "")).strip()
            ledger_path = input_path / "content-ledger.json"
            if ledger_path.is_file():
                ledger_payload = json.loads(ledger_path.read_text(encoding="utf-8"))
                ledger_global, slide_ledger_fingerprints = ledger_fingerprints(
                    ledger_payload
                )
            else:
                ledger_global = sha256_text("__missing__")
                slide_ledger_fingerprints = {}
            global_fingerprints = {
                "metadata": json_file_fingerprint(metadata_path),
                "custom-css": text_file_fingerprint(input_path / "custom.css"),
                "content-ledger": ledger_global,
            }
            deck_plan_path = input_path / "deck-plan.json"
            if deck_plan_path.is_file():
                global_fingerprints["deck-plan"] = json_file_fingerprint(deck_plan_path)
            return (
                slides_path,
                "work_folder",
                slides_path.read_text(encoding="utf-8"),
                title,
                global_fingerprints,
                slide_ledger_fingerprints,
            )
        if index_path.is_file():
            return (
                index_path,
                "standalone_html",
                index_path.read_text(encoding="utf-8"),
                "",
                {},
                {},
            )
        raise ValueError(
            f"Expected a Clara work folder with slides.html or a publication folder with index.html: {input_path}"
        )
    if not input_path.is_file():
        raise ValueError(f"Deck input does not exist: {input_path}")
    return (
        input_path,
        "standalone_html",
        input_path.read_text(encoding="utf-8"),
        "",
        {},
        {},
    )


def first_text(node: DomNode, tag_names: set[str]) -> str:
    for descendant in descendant_nodes(node):
        if descendant.tag not in tag_names:
            continue
        text_parts: list[str] = []
        for nested in descendant_nodes_and_text(descendant):
            if isinstance(nested, str):
                text_parts.append(nested)
        return " ".join("".join(text_parts).split())
    return ""


def descendant_nodes_and_text(node: DomNode) -> Iterable[DomNode | str]:
    for child in node.children:
        yield child
        if isinstance(child, DomNode):
            yield from descendant_nodes_and_text(child)


def canonical_shell_dom(node: DomNode) -> str:
    """Canonicalize document chrome while masking slides and global resources."""

    if is_slide(node):
        slide_id = json.dumps(node.attrs.get("id", ""), ensure_ascii=False)
        return f"<slide-ref id={slide_id}/>"
    if node.tag == "style":
        return "<style-ref/>"
    if node.tag == "script":
        script_id = json.dumps(node.attrs.get("id", ""), ensure_ascii=False)
        script_type = json.dumps(node.attrs.get("type", ""), ensure_ascii=False)
        return f"<script-ref id={script_id} type={script_type}/>"
    attrs = normalized_attrs(node)
    rendered_attrs = "".join(
        f" {name}={json.dumps(value, ensure_ascii=False)}" for name, value in attrs
    )
    rendered_children: list[str] = []
    for child in node.children:
        if isinstance(child, DomNode):
            rendered_children.append(canonical_shell_dom(child))
        else:
            normalized_text = " ".join(child.split())
            if normalized_text:
                rendered_children.append(
                    json.dumps(normalized_text, ensure_ascii=False)
                )
    return f"<{node.tag}{rendered_attrs}>{''.join(rendered_children)}</{node.tag}>"


def nodes_fingerprint(nodes: Iterable[DomNode]) -> str:
    """Fingerprint a stable sequence of DOM nodes."""

    return sha256_text("".join(canonical_dom(node) for node in nodes))


def node_text(node: DomNode) -> str:
    """Return all textual descendants without presentation whitespace changes."""

    return "".join(
        nested for nested in descendant_nodes_and_text(node) if isinstance(nested, str)
    )


def standalone_global_fingerprints(
    parser: DomParser,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return narrow fingerprints for standalone metadata, CSS, runtime and chrome."""

    nodes = list(descendant_nodes(parser.root))
    style_nodes = [node for node in nodes if node.tag == "style"]
    script_nodes = [node for node in nodes if node.tag == "script"]
    ledger_nodes = [
        node
        for node in script_nodes
        if node.attrs.get("id") == "claraContentLedger"
        or node.attrs.get("type", "").lower() == "application/json"
    ]
    ledger_node_ids = {id(node) for node in ledger_nodes}
    runtime_nodes = [node for node in script_nodes if id(node) not in ledger_node_ids]
    head_nodes = [node for node in nodes if node.tag == "head"]
    body_nodes = [node for node in nodes if node.tag == "body"]
    slide_ledger_fingerprints: dict[str, str] = {}
    if ledger_nodes:
        try:
            ledger_payload = json.loads(node_text(ledger_nodes[0]))
        except json.JSONDecodeError:
            ledger_global = nodes_fingerprint(ledger_nodes)
        else:
            ledger_global, slide_ledger_fingerprints = ledger_fingerprints(
                ledger_payload
            )
    else:
        ledger_global = sha256_text("__missing__")
    return {
        "metadata": sha256_text(
            "".join(canonical_shell_dom(node) for node in head_nodes)
        ),
        "styles": nodes_fingerprint(style_nodes),
        "runtime": nodes_fingerprint(runtime_nodes),
        "content-ledger": ledger_global,
        "shell": sha256_text("".join(canonical_shell_dom(node) for node in body_nodes)),
    }, slide_ledger_fingerprints


def inspect_deck(path: Path) -> DeckInspection:
    (
        source_path,
        input_kind,
        html_text,
        metadata_title,
        global_fingerprints,
        slide_ledger_fingerprints,
    ) = read_deck_source(path)
    parser = DomParser()
    parser.feed(html_text)
    parser.close()
    parser.finish()
    issues = list(parser.issues)

    if input_kind == "standalone_html":
        (
            global_fingerprints,
            slide_ledger_fingerprints,
        ) = standalone_global_fingerprints(parser)
        stage_roots = [
            node
            for node in descendant_nodes(parser.root)
            if node.tag == "main"
            and "deck-stage" in class_tokens(node)
            and node.attrs.get("data-clara-deck-mode") == "stage"
        ]
        if len(stage_roots) != 1:
            issues.append(
                Issue(
                    "deck.clara_stage_root",
                    f"Expected exactly one Clara stage root; found {len(stage_roots)}.",
                )
            )
        slide_nodes = [
            node
            for root in stage_roots
            for node in descendant_nodes(root)
            if is_slide(node)
        ]
        title_nodes = [
            node for node in descendant_nodes(parser.root) if node.tag == "title"
        ]
        title = ""
        if title_nodes:
            title = " ".join(
                nested
                for nested in descendant_nodes_and_text(title_nodes[0])
                if isinstance(nested, str)
            ).strip()
    else:
        slide_nodes = [node for node in descendant_nodes(parser.root) if is_slide(node)]
        title = metadata_title

    if not slide_nodes:
        issues.append(Issue("slides.present", "No Clara .slide sections were found."))

    slides: list[SlideRecord] = []
    seen_slide_ids: set[str] = set()
    for index, slide_node in enumerate(slide_nodes, start=1):
        slide_id = slide_node.attrs.get("id", "").strip()
        location = f"slide[{index}]"
        if not slide_id:
            issues.append(
                Issue("slides.id_required", "Slide ID is required.", location)
            )
        elif not SLIDE_ID_RE.fullmatch(slide_id):
            issues.append(
                Issue(
                    "slides.id_invalid",
                    f"Invalid Clara slide ID: {slide_id!r}.",
                    location,
                )
            )
        elif slide_id in seen_slide_ids:
            issues.append(
                Issue(
                    "slides.id_duplicate",
                    f"Duplicate slide ID: {slide_id!r}.",
                    location,
                )
            )
        seen_slide_ids.add(slide_id)

        components: list[ComponentRecord] = []
        seen_component_ids: set[str] = set()
        for node, component_path in relative_component_paths(slide_node):
            component_id = stable_component_id(node)
            protected = is_protected(node)
            component_location = f"{slide_id or location}{component_path}"
            if component_id is not None:
                if component_id in seen_component_ids:
                    issues.append(
                        Issue(
                            "components.id_duplicate",
                            f"Duplicate component identity {component_id!r} within slide {slide_id!r}.",
                            component_location,
                        )
                    )
                seen_component_ids.add(component_id)
            if protected and component_id is None:
                issues.append(
                    Issue(
                        "components.protected_id_required",
                        "Protected components require data-component-id or id for stable matching.",
                        component_location,
                    )
                )
            components.append(
                ComponentRecord(
                    node=node,
                    path=component_path,
                    component_id=component_id,
                    dom_id=node.attrs.get("id") or None,
                    protected=protected,
                    protection_reason=protection_reason(node),
                    fingerprint=node_fingerprint(node),
                )
            )

        slides.append(
            SlideRecord(
                node=slide_node,
                index=index,
                slide_id=slide_id,
                title=slide_node.attrs.get("data-slide-title", "").strip()
                or first_text(slide_node, {"h1", "h2", "h3"}),
                chapter=slide_node.attrs.get("data-chapter", "").strip(),
                protected=is_protected(slide_node),
                protection_reason=protection_reason(slide_node),
                fingerprint=node_fingerprint(slide_node),
                ledger_fingerprint=slide_ledger_fingerprints.get(slide_id),
                components=components,
            )
        )

    deck_fingerprint = sha256_text(
        json.dumps(
            {
                "global_fingerprints": global_fingerprints,
                "slides": [
                    {"id": slide.slide_id, "fingerprint": slide.fingerprint}
                    for slide in slides
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return DeckInspection(
        input_path=source_path,
        input_kind=input_kind,
        content_sha256=sha256_text(html_text),
        deck_fingerprint=deck_fingerprint,
        global_fingerprints=global_fingerprints,
        title=title,
        slides=slides,
        issues=issues,
    )


def add_issue(
    issues: list[Issue],
    code: str,
    message: str,
    location: str | None = None,
    *,
    severity: str = "error",
) -> None:
    issues.append(Issue(code, message, location, severity))


def ensure_string_list(
    value: Any,
    *,
    location: str,
    issues: list[Issue],
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        add_issue(issues, "map.schema", "Expected a list of strings.", location)
        return []
    values = [item.strip() for item in value]
    invalid = [item for item in values if not SLIDE_ID_RE.fullmatch(item)]
    if invalid:
        add_issue(
            issues, "map.slide_id_invalid", f"Invalid slide IDs: {invalid}.", location
        )
    duplicates = sorted({item for item in values if values.count(item) > 1})
    if duplicates:
        add_issue(
            issues, "map.duplicate_value", f"Duplicate values: {duplicates}.", location
        )
    return values


def ensure_global_edit_list(value: Any, *, issues: list[Issue]) -> list[str]:
    """Validate explicitly declared document-level revision scopes."""

    location = "global_edits"
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        add_issue(issues, "map.schema", "Expected a list of strings.", location)
        return []
    values = [item.strip() for item in value]
    invalid = sorted(set(values) - GLOBAL_EDIT_SCOPES)
    if invalid:
        add_issue(
            issues,
            "map.global_edit_invalid",
            f"Unsupported global edit scopes: {invalid}.",
            location,
        )
    duplicates = sorted({item for item in values if values.count(item) > 1})
    if duplicates:
        add_issue(
            issues,
            "map.duplicate_value",
            f"Duplicate values: {duplicates}.",
            location,
        )
    return values


def validate_revision_map(
    payload: dict[str, Any],
    baseline: DeckInspection,
) -> dict[str, Any]:
    issues: list[Issue] = []
    required_keys = {
        "baseline_fingerprint",
        "edit_targets",
        "global_edits",
        "protected_slides",
        "schema_version",
        "untouched_slides",
    }
    optional_keys = {"protected_components", "slide_changes"}
    missing_keys = sorted(required_keys - set(payload))
    unknown_keys = sorted(set(payload) - required_keys - optional_keys)
    if missing_keys:
        add_issue(issues, "map.schema", f"Missing required keys: {missing_keys}.")
    if unknown_keys:
        add_issue(issues, "map.schema", f"Unknown top-level keys: {unknown_keys}.")
    if payload.get("schema_version") != REVISION_MAP_SCHEMA_VERSION:
        add_issue(
            issues,
            "map.schema_version",
            f"Expected {REVISION_MAP_SCHEMA_VERSION!r}.",
            "schema_version",
        )
    baseline_fingerprint = payload.get("baseline_fingerprint")
    if not isinstance(baseline_fingerprint, str) or not FINGERPRINT_RE.fullmatch(
        baseline_fingerprint
    ):
        add_issue(
            issues,
            "map.baseline_fingerprint_invalid",
            "baseline_fingerprint must be a 64-character lowercase SHA-256 value.",
            "baseline_fingerprint",
        )
    elif baseline_fingerprint != baseline.deck_fingerprint:
        add_issue(
            issues,
            "map.baseline_mismatch",
            "Revision map does not match the inspected baseline deck fingerprint.",
            "baseline_fingerprint",
        )
    if baseline.result != "pass":
        add_issue(
            issues,
            "map.baseline_invalid",
            "Baseline inspection must pass before a revision map can be validated.",
        )

    untouched = ensure_string_list(
        payload.get("untouched_slides"),
        location="untouched_slides",
        issues=issues,
    )
    protected_slides = ensure_string_list(
        payload.get("protected_slides"),
        location="protected_slides",
        issues=issues,
    )
    global_edits = ensure_global_edit_list(payload.get("global_edits"), issues=issues)
    unavailable_global_edits = sorted(
        set(global_edits) - set(baseline.global_fingerprints)
    )
    if unavailable_global_edits:
        add_issue(
            issues,
            "map.global_edit_unavailable",
            "Global edit scopes are unavailable for this source kind: "
            f"{unavailable_global_edits}.",
            "global_edits",
        )

    raw_targets = payload.get("edit_targets")
    targets: list[dict[str, Any]] = []
    if not isinstance(raw_targets, list):
        add_issue(issues, "map.schema", "edit_targets must be a list.", "edit_targets")
    else:
        for index, raw_target in enumerate(raw_targets):
            location = f"edit_targets[{index}]"
            if not isinstance(raw_target, dict):
                add_issue(
                    issues, "map.schema", "Edit target must be an object.", location
                )
                continue
            allowed = {"component_ids", "reason", "scope", "slide_id"}
            unknown = sorted(set(raw_target) - allowed)
            if unknown:
                add_issue(
                    issues,
                    "map.schema",
                    f"Unknown edit-target keys: {unknown}.",
                    location,
                )
            slide_id = raw_target.get("slide_id")
            scope = raw_target.get("scope")
            reason = raw_target.get("reason", "")
            if not isinstance(reason, str):
                add_issue(issues, "map.schema", "reason must be a string.", location)
                reason = ""
            elif not reason.strip():
                add_issue(
                    issues,
                    "map.target_reason_required",
                    "Every edit target needs a non-empty reason.",
                    location,
                )
            if not isinstance(slide_id, str) or not SLIDE_ID_RE.fullmatch(slide_id):
                add_issue(issues, "map.slide_id_invalid", "Invalid slide_id.", location)
                continue
            if scope not in {"slide", "components"}:
                add_issue(
                    issues,
                    "map.target_scope_invalid",
                    "scope must be 'slide' or 'components'.",
                    location,
                )
                continue
            component_ids = raw_target.get("component_ids", [])
            if not isinstance(component_ids, list) or any(
                not isinstance(item, str) or not item.strip() for item in component_ids
            ):
                add_issue(
                    issues,
                    "map.schema",
                    "component_ids must be a list of non-empty strings.",
                    location,
                )
                continue
            component_ids = [item.strip() for item in component_ids]
            if len(component_ids) != len(set(component_ids)):
                add_issue(
                    issues,
                    "map.duplicate_value",
                    "component_ids contains duplicates.",
                    location,
                )
            if scope == "components" and not component_ids:
                add_issue(
                    issues,
                    "map.target_components_required",
                    "Component-scoped targets require at least one component_id.",
                    location,
                )
            if scope == "slide" and component_ids:
                add_issue(
                    issues,
                    "map.target_components_forbidden",
                    "Slide-scoped targets must not declare component_ids.",
                    location,
                )
            targets.append(
                {
                    "component_ids": component_ids,
                    "reason": reason.strip(),
                    "scope": scope,
                    "slide_id": slide_id,
                }
            )

    target_ids = [target["slide_id"] for target in targets]
    duplicate_target_ids = sorted(
        {slide_id for slide_id in target_ids if target_ids.count(slide_id) > 1}
    )
    if duplicate_target_ids:
        add_issue(
            issues,
            "map.target_duplicate",
            f"Slides have multiple edit targets: {duplicate_target_ids}.",
            "edit_targets",
        )

    raw_protected_components = payload.get("protected_components", [])
    protected_components: list[dict[str, str]] = []
    if not isinstance(raw_protected_components, list):
        add_issue(
            issues,
            "map.schema",
            "protected_components must be a list.",
            "protected_components",
        )
    else:
        for index, raw_protected in enumerate(raw_protected_components):
            location = f"protected_components[{index}]"
            if not isinstance(raw_protected, dict):
                add_issue(
                    issues,
                    "map.schema",
                    "Protected component must be an object.",
                    location,
                )
                continue
            allowed = {"component_id", "reason", "slide_id"}
            unknown = sorted(set(raw_protected) - allowed)
            if unknown:
                add_issue(
                    issues,
                    "map.schema",
                    f"Unknown protected-component keys: {unknown}.",
                    location,
                )
            slide_id = raw_protected.get("slide_id")
            component_id = raw_protected.get("component_id")
            reason = raw_protected.get("reason", "")
            if not isinstance(reason, str):
                add_issue(issues, "map.schema", "reason must be a string.", location)
                reason = ""
            if not isinstance(slide_id, str) or not SLIDE_ID_RE.fullmatch(slide_id):
                add_issue(issues, "map.slide_id_invalid", "Invalid slide_id.", location)
                continue
            if not isinstance(component_id, str) or not component_id.strip():
                add_issue(
                    issues,
                    "map.component_id_invalid",
                    "Invalid component_id.",
                    location,
                )
                continue
            protected_components.append(
                {
                    "component_id": component_id.strip(),
                    "reason": reason.strip(),
                    "slide_id": slide_id,
                }
            )

    changes = payload.get("slide_changes", {})
    if not isinstance(changes, dict):
        add_issue(
            issues, "map.schema", "slide_changes must be an object.", "slide_changes"
        )
        changes = {}
    unknown_change_keys = sorted(
        set(changes) - {"add", "after_order", "remove", "rename"}
    )
    if unknown_change_keys:
        add_issue(
            issues,
            "map.schema",
            f"Unknown slide_changes keys: {unknown_change_keys}.",
            "slide_changes",
        )
    added = ensure_string_list(
        changes.get("add", []), location="slide_changes.add", issues=issues
    )
    removed = ensure_string_list(
        changes.get("remove", []),
        location="slide_changes.remove",
        issues=issues,
    )
    raw_after_order = changes.get("after_order")
    after_order = (
        None
        if raw_after_order is None
        else ensure_string_list(
            raw_after_order,
            location="slide_changes.after_order",
            issues=issues,
        )
    )
    raw_renames = changes.get("rename", [])
    renames: list[dict[str, str]] = []
    if not isinstance(raw_renames, list):
        add_issue(
            issues, "map.schema", "rename must be a list.", "slide_changes.rename"
        )
    else:
        for index, raw_rename in enumerate(raw_renames):
            location = f"slide_changes.rename[{index}]"
            if not isinstance(raw_rename, dict) or set(raw_rename) != {"from", "to"}:
                add_issue(
                    issues,
                    "map.schema",
                    "Rename must contain exactly 'from' and 'to'.",
                    location,
                )
                continue
            old_id = raw_rename["from"]
            new_id = raw_rename["to"]
            if (
                not isinstance(old_id, str)
                or not isinstance(new_id, str)
                or not SLIDE_ID_RE.fullmatch(old_id)
                or not SLIDE_ID_RE.fullmatch(new_id)
            ):
                add_issue(
                    issues, "map.slide_id_invalid", "Invalid rename slide ID.", location
                )
                continue
            renames.append({"from": old_id, "to": new_id})

    baseline_ids = [slide.slide_id for slide in baseline.slides]
    baseline_id_set = set(baseline_ids)
    rename_from = [rename["from"] for rename in renames]
    rename_to = [rename["to"] for rename in renames]
    duplicate_operations = sorted(
        {
            slide_id
            for slide_id in removed + rename_from
            if (removed + rename_from).count(slide_id) > 1
        }
    )
    if duplicate_operations:
        add_issue(
            issues,
            "map.slide_operation_conflict",
            f"Baseline slides have conflicting operations: {duplicate_operations}.",
            "slide_changes",
        )
    new_ids = added + rename_to
    duplicate_new_ids = sorted(
        {slide_id for slide_id in new_ids if new_ids.count(slide_id) > 1}
    )
    if duplicate_new_ids:
        add_issue(
            issues,
            "map.slide_operation_conflict",
            f"New slide IDs are duplicated: {duplicate_new_ids}.",
            "slide_changes",
        )
    replaced_same_ids = sorted(set(added) & set(removed))
    if replaced_same_ids:
        add_issue(
            issues,
            "map.slide_operation_conflict",
            "Use an edit target instead of removing and adding the same slide "
            f"IDs: {replaced_same_ids}.",
            "slide_changes",
        )
    identity_renames = sorted(
        rename["from"] for rename in renames if rename["from"] == rename["to"]
    )
    if identity_renames:
        add_issue(
            issues,
            "map.slide_operation_conflict",
            f"Rename operations must change the slide ID: {identity_renames}.",
            "slide_changes.rename",
        )

    referenced_baseline = set(
        untouched + protected_slides + target_ids + removed + rename_from
    )
    unknown_baseline = sorted(referenced_baseline - baseline_id_set)
    if unknown_baseline:
        add_issue(
            issues,
            "map.slide_unknown",
            f"Revision map references unknown baseline slides: {unknown_baseline}.",
        )
    colliding_new = sorted(
        set(new_ids) & (baseline_id_set - set(removed) - set(rename_from))
    )
    if colliding_new:
        add_issue(
            issues,
            "map.slide_id_collision",
            f"New slide IDs collide with retained baseline slides: {colliding_new}.",
            "slide_changes",
        )

    classifications = untouched + protected_slides + target_ids + removed + rename_from
    multiply_classified = sorted(
        {
            slide_id
            for slide_id in classifications
            if classifications.count(slide_id) > 1
        }
    )
    if multiply_classified:
        add_issue(
            issues,
            "map.slide_classification_conflict",
            f"Slides have multiple revision classifications: {multiply_classified}.",
        )
    unclassified = sorted(baseline_id_set - set(classifications))
    if unclassified:
        add_issue(
            issues,
            "map.slide_unclassified",
            f"Every baseline slide must be classified; missing: {unclassified}.",
        )

    target_by_id = {target["slide_id"]: target for target in targets}
    protected_by_slide: dict[str, set[str]] = {}
    for slide in baseline.slides:
        inline_ids = {
            component.component_id
            for component in slide.components
            if component.protected and component.component_id is not None
        }
        protected_by_slide[slide.slide_id] = set(inline_ids)
        if slide.protected and slide.slide_id in set(
            target_ids + removed + rename_from
        ):
            add_issue(
                issues,
                "map.inline_protection_conflict",
                f"Inline-protected slide {slide.slide_id!r} cannot be edited, removed, or renamed.",
            )
    for item in protected_components:
        protected_by_slide.setdefault(item["slide_id"], set()).add(item["component_id"])

    protected_keys = [
        (item["slide_id"], item["component_id"]) for item in protected_components
    ]
    duplicate_protected_components = sorted(
        {key for key in protected_keys if protected_keys.count(key) > 1}
    )
    if duplicate_protected_components:
        add_issue(
            issues,
            "map.duplicate_value",
            f"Duplicate protected components: {duplicate_protected_components}.",
            "protected_components",
        )

    for slide_id, component_ids in protected_by_slide.items():
        slide = baseline.slide_by_id.get(slide_id)
        if slide is None:
            continue
        for component_id in sorted(component_ids):
            if component_id not in slide.component_by_id:
                add_issue(
                    issues,
                    "map.component_unknown",
                    f"Unknown protected component {component_id!r} on slide {slide_id!r}.",
                )
        if component_ids and slide_id in removed:
            add_issue(
                issues,
                "map.protected_component_removal",
                f"Slide {slide_id!r} cannot be removed because it contains protected components.",
            )

    for slide_id, target in target_by_id.items():
        slide = baseline.slide_by_id.get(slide_id)
        if slide is None or target["scope"] != "components":
            continue
        for component_id in target["component_ids"]:
            component = slide.component_by_id.get(component_id)
            if component is None:
                add_issue(
                    issues,
                    "map.component_unknown",
                    f"Unknown edit component {component_id!r} on slide {slide_id!r}.",
                )
                continue
            for protected_id in protected_by_slide.get(slide_id, set()):
                protected_component = slide.component_by_id.get(protected_id)
                if protected_component is None:
                    continue
                protected_is_ancestor = (
                    component.path == protected_component.path
                    or component.path.startswith(protected_component.path + "/")
                )
                if protected_is_ancestor:
                    add_issue(
                        issues,
                        "map.protected_component_targeted",
                        f"Edit target {component_id!r} is protected or nested inside protected component {protected_id!r} on slide {slide_id!r}.",
                    )

    expected_after_ids = (
        (baseline_id_set - set(removed) - set(rename_from))
        | set(rename_to)
        | set(added)
    )
    if after_order is not None and (
        len(after_order) != len(expected_after_ids)
        or set(after_order) != expected_after_ids
    ):
        add_issue(
            issues,
            "map.after_order_invalid",
            "after_order must contain every expected post-revision slide ID exactly once.",
            "slide_changes.after_order",
        )

    normalized = {
        "baseline_fingerprint": baseline_fingerprint,
        "edit_targets": targets,
        "global_edits": global_edits,
        "protected_components": protected_components,
        "protected_slides": protected_slides,
        "schema_version": REVISION_MAP_SCHEMA_VERSION,
        "slide_changes": {
            "add": added,
            "after_order": after_order,
            "remove": removed,
            "rename": renames,
        },
        "untouched_slides": untouched,
    }
    map_fingerprint = sha256_text(
        json.dumps(
            normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
    )
    return {
        "schema_version": REVISION_MAP_VALIDATION_SCHEMA_VERSION,
        "result": (
            "fail" if any(issue.severity == "error" for issue in issues) else "pass"
        ),
        "baseline": {
            "global_fingerprints": baseline.global_fingerprints,
            "normalized_dom_fingerprint": baseline.deck_fingerprint,
            "path": str(baseline.input_path),
            "slide_count": len(baseline.slides),
        },
        "issues": [issue.as_dict() for issue in issues],
        "normalized_map": normalized,
        "revision_map_fingerprint": map_fingerprint,
        "summary": issue_summary(issues),
    }


def compare_deck_revision(
    before: DeckInspection,
    after: DeckInspection,
    payload: dict[str, Any],
) -> dict[str, Any]:
    map_report = validate_revision_map(payload, before)
    issues: list[Issue] = []
    if after.result != "pass":
        add_issue(
            issues,
            "comparison.after_invalid",
            "Post-revision deck inspection must pass before fidelity comparison.",
        )
        issues.extend(after.issues)
    if map_report["result"] != "pass":
        add_issue(
            issues,
            "comparison.map_invalid",
            "Revision map validation failed against the baseline deck.",
        )
        issues.extend(
            Issue(
                item["code"],
                item["message"],
                item["location"],
                item["severity"],
            )
            for item in map_report["issues"]
        )
        return comparison_report(before, after, map_report, issues, [])

    normalized = map_report["normalized_map"]
    declared_global_edits = set(normalized["global_edits"])
    if before.input_kind != after.input_kind:
        add_issue(
            issues,
            "document.input_kind_changed",
            "Revision fidelity must compare the same Clara source kind before and after.",
        )
    global_keys = set(before.global_fingerprints) | set(after.global_fingerprints)
    changed_global_edits = {
        key
        for key in global_keys
        if before.global_fingerprints.get(key) != after.global_fingerprints.get(key)
    }
    undeclared_global_edits = sorted(changed_global_edits - declared_global_edits)
    if undeclared_global_edits:
        add_issue(
            issues,
            "document.unplanned_global_change",
            "Document-level resources changed without declaration: "
            f"{undeclared_global_edits}.",
        )
    unchanged_declared_globals = sorted(declared_global_edits - changed_global_edits)
    if unchanged_declared_globals:
        add_issue(
            issues,
            "targets.no_change",
            "Declared document-level targets did not change: "
            f"{unchanged_declared_globals}.",
        )
    changes = normalized["slide_changes"]
    removed = set(changes["remove"])
    added = set(changes["add"])
    rename_by_old = {item["from"]: item["to"] for item in changes["rename"]}
    rename_from = set(rename_by_old)
    rename_to = set(rename_by_old.values())
    expected_after = (
        (set(before.slide_by_id) - removed - rename_from) | added | rename_to
    )
    actual_after = set(after.slide_by_id)
    ledger_is_in_use = any(
        slide.ledger_fingerprint is not None
        for slide in [*before.slides, *after.slides]
    )
    if ledger_is_in_use:
        missing_ledger_entries = sorted(
            slide.slide_id for slide in after.slides if slide.ledger_fingerprint is None
        )
        if missing_ledger_entries:
            add_issue(
                issues,
                "provenance.slide_entry_missing",
                "Post-revision slides are missing content-ledger entries: "
                f"{missing_ledger_entries}.",
            )
    missing = sorted(expected_after - actual_after)
    unexpected = sorted(actual_after - expected_after)
    if missing:
        add_issue(
            issues,
            "slides.expected_missing",
            f"Expected post-revision slide IDs are missing: {missing}.",
        )
    if unexpected:
        add_issue(
            issues,
            "slides.unplanned_addition_or_id_change",
            f"Unplanned slide IDs appeared: {unexpected}.",
        )
    unplanned_removed = sorted(
        slide_id
        for slide_id in before.slide_by_id
        if slide_id not in after.slide_by_id
        and slide_id not in removed
        and slide_id not in rename_from
    )
    if unplanned_removed:
        add_issue(
            issues,
            "slides.unplanned_removal_or_id_change",
            f"Baseline slide IDs disappeared without a declared removal or rename: {unplanned_removed}.",
        )
    stale_renames = sorted(rename_from & actual_after)
    if stale_renames:
        add_issue(
            issues,
            "slides.rename_not_applied",
            f"Renamed baseline IDs still exist after revision: {stale_renames}.",
        )
    stale_removals = sorted(removed & actual_after)
    if stale_removals:
        add_issue(
            issues,
            "slides.removal_not_applied",
            f"Slides declared for removal still exist: {stale_removals}.",
        )

    expected_order = changes["after_order"]
    actual_order = [slide.slide_id for slide in after.slides]
    if expected_order is not None:
        if actual_order != expected_order:
            add_issue(
                issues,
                "slides.order_changed",
                "Post-revision slide order does not match declared after_order.",
            )
    else:
        retained_expected = [
            rename_by_old.get(slide.slide_id, slide.slide_id)
            for slide in before.slides
            if slide.slide_id not in removed
        ]
        retained_actual = [
            slide_id for slide_id in actual_order if slide_id not in added
        ]
        if retained_actual != retained_expected:
            add_issue(
                issues,
                "slides.order_changed",
                "Relative order of retained slides changed without a declared after_order.",
            )

    target_by_id = {target["slide_id"]: target for target in normalized["edit_targets"]}
    untouched = set(normalized["untouched_slides"])
    protected_slides = set(normalized["protected_slides"])
    planned_changes: list[dict[str, Any]] = []

    protected_by_slide: dict[str, set[str]] = {}
    for slide in before.slides:
        protected_by_slide[slide.slide_id] = {
            component.component_id
            for component in slide.components
            if component.protected and component.component_id is not None
        }
    for item in normalized["protected_components"]:
        protected_by_slide.setdefault(item["slide_id"], set()).add(item["component_id"])

    for before_slide in before.slides:
        old_id = before_slide.slide_id
        if old_id in removed:
            continue
        new_id = rename_by_old.get(old_id, old_id)
        after_slide = after.slide_by_id.get(new_id)
        if after_slide is None:
            continue

        ledger_changed = (
            before_slide.ledger_fingerprint != after_slide.ledger_fingerprint
        )
        if (
            ledger_changed
            and old_id not in target_by_id
            and old_id not in rename_by_old
        ):
            add_issue(
                issues,
                "provenance.unplanned_slide_change",
                f"Content-ledger entry changed for non-target slide {old_id!r}.",
            )

        if old_id in rename_by_old:
            if ledger_changed:
                add_issue(
                    issues,
                    "provenance.rename_changed_ledger",
                    f"Content-ledger entry changed while slide {old_id!r} was renamed to {new_id!r}.",
                )
            before_renamed = node_fingerprint(before_slide.node, override_slide_id=True)
            after_renamed = node_fingerprint(after_slide.node, override_slide_id=True)
            if before_renamed != after_renamed:
                add_issue(
                    issues,
                    "slides.rename_changed_content",
                    f"Slide {old_id!r} -> {new_id!r} changed beyond its declared ID rename.",
                )
        elif (
            old_id in untouched or old_id in protected_slides or before_slide.protected
        ):
            if before_slide.fingerprint != after_slide.fingerprint:
                code = (
                    "slides.protected_changed"
                    if old_id in protected_slides or before_slide.protected
                    else "slides.untouched_changed"
                )
                add_issue(
                    issues,
                    code,
                    f"Slide {old_id!r} changed despite its preservation classification.",
                )
        else:
            target = target_by_id.get(old_id)
            if target is not None:
                if target["scope"] == "components":
                    component_ids = frozenset(target["component_ids"])
                    missing_targets = sorted(
                        component_id
                        for component_id in component_ids
                        if component_id not in after_slide.component_by_id
                    )
                    if missing_targets:
                        add_issue(
                            issues,
                            "components.edit_target_missing",
                            f"Edit-target components disappeared from slide {old_id!r}: {missing_targets}.",
                        )
                    before_masked = node_fingerprint(
                        before_slide.node,
                        masked_component_ids=component_ids,
                    )
                    after_masked = node_fingerprint(
                        after_slide.node,
                        masked_component_ids=component_ids,
                    )
                    if before_masked != after_masked:
                        add_issue(
                            issues,
                            "components.unplanned_change",
                            f"Slide {old_id!r} changed outside its declared component edit targets.",
                        )
                    component_changes = []
                    for component_id in sorted(component_ids):
                        before_component = before_slide.component_by_id.get(
                            component_id
                        )
                        after_component = after_slide.component_by_id.get(component_id)
                        if before_component is None or after_component is None:
                            continue
                        component_changes.append(
                            {
                                "changed": before_component.fingerprint
                                != after_component.fingerprint,
                                "component_id": component_id,
                            }
                        )
                    planned_changes.append(
                        {
                            "component_changes": component_changes,
                            "scope": "components",
                            "slide_id": old_id,
                        }
                    )
                else:
                    planned_changes.append(
                        {
                            "changed": before_slide.fingerprint
                            != after_slide.fingerprint,
                            "scope": "slide",
                            "slide_id": old_id,
                        }
                    )

        for component_id in sorted(protected_by_slide.get(old_id, set())):
            before_component = before_slide.component_by_id.get(component_id)
            after_component = after_slide.component_by_id.get(component_id)
            if before_component is None:
                continue
            if after_component is None:
                add_issue(
                    issues,
                    "components.protected_missing",
                    f"Protected component {component_id!r} disappeared from slide {new_id!r}.",
                )
            elif before_component.path != after_component.path:
                add_issue(
                    issues,
                    "components.protected_moved",
                    f"Protected component {component_id!r} moved on slide {new_id!r}.",
                )
            elif before_component.fingerprint != after_component.fingerprint:
                add_issue(
                    issues,
                    "components.protected_changed",
                    f"Protected component {component_id!r} changed on slide {new_id!r}.",
                )

    for change in planned_changes:
        if change["scope"] == "slide" and not change["changed"]:
            add_issue(
                issues,
                "targets.no_change",
                f"Declared slide target {change['slide_id']!r} did not change.",
            )
        if change["scope"] == "components":
            unchanged = [
                item["component_id"]
                for item in change["component_changes"]
                if not item["changed"]
            ]
            if unchanged:
                add_issue(
                    issues,
                    "targets.no_change",
                    f"Declared component targets did not change on slide {change['slide_id']!r}: {unchanged}.",
                )

    return comparison_report(before, after, map_report, issues, planned_changes)


def comparison_report(
    before: DeckInspection,
    after: DeckInspection,
    map_report: dict[str, Any],
    issues: list[Issue],
    planned_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "result": (
            "fail" if any(issue.severity == "error" for issue in issues) else "pass"
        ),
        "before": {
            "global_fingerprints": before.global_fingerprints,
            "normalized_dom_fingerprint": before.deck_fingerprint,
            "path": str(before.input_path),
            "slide_count": len(before.slides),
        },
        "after": {
            "global_fingerprints": after.global_fingerprints,
            "normalized_dom_fingerprint": after.deck_fingerprint,
            "path": str(after.input_path),
            "slide_count": len(after.slides),
        },
        "issues": [issue.as_dict() for issue in issues],
        "planned_changes": planned_changes,
        "revision_map": {
            "result": map_report["result"],
            "revision_map_fingerprint": map_report["revision_map_fingerprint"],
        },
        "summary": issue_summary(issues),
    }
