#!/usr/bin/env python3
"""Compose editable Clara HTML slides from an explicit deck-plan contract."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

__all__ = [
    "CompositionResult",
    "ExtensionRenderer",
    "PLAN_SCHEMA_VERSION",
    "REGISTRY_SCHEMA_VERSION",
    "RenderContext",
    "compose_deck",
    "default_registry_path",
    "load_registry",
]


PLAN_SCHEMA_VERSION = "clara.html_deck_plan.v1"
REGISTRY_SCHEMA_VERSION = "clara.html_deck_layout_registry.v1"
GENERATED_CSS_START = "/* BEGIN CLARA GENERATED LAYOUT CSS — DO NOT EDIT */"
GENERATED_CSS_END = "/* END CLARA GENERATED LAYOUT CSS */"
AUTHOR_CSS_HEADER = (
    "/* Deck-specific semantic rules below are preserved across recomposition. */"
)
SAFE_SLIDE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TOKEN = re.compile(r"{{([a-z][a-z0-9_]*)}}")
URL_ATTRIBUTES = frozenset(
    {"action", "data", "formaction", "href", "poster", "src", "srcset", "xlink:href"}
)
WORD = re.compile(r"\b[\w'’.-]+\b", re.UNICODE)


@dataclass(frozen=True)
class RenderContext:
    """Immutable slide metadata supplied to an optional extension renderer."""

    slide_id: str
    layout_id: str
    title: str
    source_refs: tuple[str, ...]
    claim_refs: tuple[str, ...]


class ExtensionRenderer(Protocol):
    """Contract for data-bound or otherwise specialized slot renderers."""

    def __call__(
        self,
        *,
        slot_name: str,
        value: Mapping[str, Any],
        slot_schema: Mapping[str, Any],
        slide: RenderContext,
    ) -> str: ...


@dataclass(frozen=True)
class CompositionResult:
    """Editable outputs produced from one validated deck plan."""

    slides_html: str
    custom_css: str
    slide_count: int
    layout_ids: tuple[str, ...]


RendererDispatch = Mapping[str, ExtensionRenderer]


def default_registry_path() -> Path:
    """Return the bundled layout registry."""

    return (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "layout-library"
        / "registry.json"
    )


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be an array")
    return value


def _string(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    result = value.strip()
    if not allow_empty and not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _safe_asset_path(library_dir: Path, relative: object, label: str) -> Path:
    relative_text = _string(relative, label)
    candidate = (library_dir / relative_text).resolve()
    try:
        candidate.relative_to(library_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the layout library") from exc
    if not candidate.is_file():
        raise ValueError(f"{label} does not exist: {relative_text}")
    return candidate


def _template_tokens(path: Path) -> set[str]:
    return set(TOKEN.findall(path.read_text(encoding="utf-8")))


def _validate_slot_schema(
    slot_name: str,
    raw_schema: object,
    *,
    library_dir: Path,
    label: str,
) -> None:
    schema = _mapping(raw_schema, label)
    slot_type = _string(schema.get("type"), f"{label}.type")
    supported = {"text", "enum", "items", "data_uri", "extension"}
    if slot_type not in supported:
        raise ValueError(f"{label}.type is unsupported: {slot_type!r}")
    if not isinstance(schema.get("required", False), bool):
        raise ValueError(f"{label}.required must be a boolean")

    if slot_type == "text":
        max_chars = schema.get("max_chars")
        if (
            not isinstance(max_chars, int)
            or isinstance(max_chars, bool)
            or max_chars < 1
        ):
            raise ValueError(f"{label}.max_chars must be a positive integer")
    elif slot_type == "enum":
        values = _sequence(schema.get("values"), f"{label}.values")
        if not values or any(not isinstance(item, str) or not item for item in values):
            raise ValueError(f"{label}.values must contain non-empty strings")
    elif slot_type == "data_uri":
        if schema.get("media") != "image":
            raise ValueError(f"{label}.media must be 'image'")
    elif slot_type == "extension":
        _string(schema.get("renderer"), f"{label}.renderer")
    elif slot_type == "items":
        minimum = schema.get("min_items", 0)
        maximum = schema.get("max_items")
        if (
            not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or minimum < 0
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or maximum < max(minimum, 1)
        ):
            raise ValueError(f"{label} has an invalid item range")
        fields = _mapping(schema.get("item_fields"), f"{label}.item_fields")
        if not fields:
            raise ValueError(f"{label}.item_fields cannot be empty")
        for field_name, field_schema in fields.items():
            if not isinstance(field_name, str) or not re.fullmatch(
                r"[a-z][a-z0-9_]*", field_name
            ):
                raise ValueError(
                    f"{label} has an invalid item field name: {field_name!r}"
                )
            _validate_slot_schema(
                field_name,
                field_schema,
                library_dir=library_dir,
                label=f"{label}.item_fields.{field_name}",
            )
        item_template = _safe_asset_path(
            library_dir,
            schema.get("item_template"),
            f"{label}.item_template",
        )
        expected_tokens = set(fields) | {"fragment_attr"}
        actual_tokens = _template_tokens(item_template)
        if actual_tokens != expected_tokens:
            raise ValueError(
                f"{label}.item_template tokens must be {sorted(expected_tokens)}, "
                f"found {sorted(actual_tokens)}"
            )


def _validate_layout(raw_layout: object, *, library_dir: Path, index: int) -> str:
    label = f"registry.layouts[{index}]"
    layout = _mapping(raw_layout, label)
    layout_id = _string(layout.get("id"), f"{label}.id")
    if not SAFE_SLIDE_ID.fullmatch(layout_id):
        raise ValueError(f"{label}.id is not a stable lowercase identifier")
    _string(layout.get("name"), f"{label}.name")
    _string(layout.get("narrative_role"), f"{label}.narrative_role")
    _string(layout.get("description"), f"{label}.description")
    _string(layout.get("slide_class"), f"{label}.slide_class", allow_empty=True)

    tones = _sequence(layout.get("tone_options"), f"{label}.tone_options")
    if not tones or any(tone not in {"light", "dark"} for tone in tones):
        raise ValueError(f"{label}.tone_options may contain only 'light' and 'dark'")

    slots = _mapping(layout.get("slots"), f"{label}.slots")
    if not slots:
        raise ValueError(f"{label}.slots cannot be empty")
    for slot_name, slot_schema in slots.items():
        if not isinstance(slot_name, str) or not re.fullmatch(
            r"[a-z][a-z0-9_]*", slot_name
        ):
            raise ValueError(f"{label} has an invalid slot name: {slot_name!r}")
        _validate_slot_schema(
            slot_name,
            slot_schema,
            library_dir=library_dir,
            label=f"{label}.slots.{slot_name}",
        )

    headline_slot = _string(layout.get("headline_slot"), f"{label}.headline_slot")
    if (
        headline_slot not in slots
        or _mapping(slots[headline_slot], headline_slot).get("type") != "text"
    ):
        raise ValueError(f"{label}.headline_slot must name a text slot")

    density = _mapping(layout.get("density_budget"), f"{label}.density_budget")
    typography = _mapping(layout.get("typography_budget"), f"{label}.typography_budget")
    for field, minimum in (("max_total_words", 1), ("max_items", 0)):
        value = density.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"{label}.density_budget.{field} is invalid")
    for field in ("headline_max_chars", "headline_max_lines", "body_min_px"):
        value = typography.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{label}.typography_budget.{field} is invalid")

    fragments = _mapping(layout.get("fragment_support"), f"{label}.fragment_support")
    if fragments.get("mode") not in {"none", "items"}:
        raise ValueError(f"{label}.fragment_support.mode is invalid")
    max_fragments = fragments.get("max_fragments")
    if (
        not isinstance(max_fragments, int)
        or isinstance(max_fragments, bool)
        or max_fragments < 0
    ):
        raise ValueError(f"{label}.fragment_support.max_fragments is invalid")

    template = _safe_asset_path(
        library_dir,
        layout.get("template"),
        f"{label}.template",
    )
    actual_tokens = _template_tokens(template)
    if actual_tokens != set(slots):
        raise ValueError(
            f"{label}.template tokens must be {sorted(slots)}, found {sorted(actual_tokens)}"
        )
    return layout_id


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Load and mechanically validate the layout registry and its templates."""

    registry_path = (path or default_registry_path()).expanduser().resolve()
    payload = _mapping(
        json.loads(registry_path.read_text(encoding="utf-8")),
        "layout registry",
    )
    if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported layout registry schema: {payload.get('schema_version')!r}"
        )
    css_path = _safe_asset_path(
        registry_path.parent,
        payload.get("css"),
        "registry.css",
    )
    layouts = _sequence(payload.get("layouts"), "registry.layouts")
    if not 12 <= len(layouts) <= 16:
        raise ValueError("registry.layouts must contain 12 to 16 layouts")
    seen: set[str] = set()
    for index, layout in enumerate(layouts):
        layout_id = _validate_layout(
            layout, library_dir=registry_path.parent, index=index
        )
        if layout_id in seen:
            raise ValueError(f"Duplicate layout id: {layout_id}")
        seen.add(layout_id)
    return {
        "path": registry_path,
        "library_dir": registry_path.parent,
        "css_path": css_path,
        "layouts": {str(_mapping(item, "layout")["id"]): item for item in layouts},
    }


def _escape_text(value: str) -> str:
    # Braces are encoded because the downstream deck builder reserves {{...}} tokens.
    return html.escape(value, quote=True).replace("{", "&#123;").replace("}", "&#125;")


def _validate_refs(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    refs = _sequence(value, label)
    normalized: list[str] = []
    for index, ref in enumerate(refs):
        token = _string(ref, f"{label}[{index}]")
        if not SAFE_REF.fullmatch(token):
            raise ValueError(f"{label}[{index}] is not a safe reference token")
        if token in normalized:
            raise ValueError(f"{label} contains duplicate reference {token!r}")
        normalized.append(token)
    return tuple(normalized)


class TrustedMarkupParser(HTMLParser):
    """Reject executable or non-inline constructs after HTML entity decoding."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.issues: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._inspect(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._inspect(tag, attrs)

    def _inspect(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {
            "embed",
            "iframe",
            "link",
            "meta",
            "object",
            "script",
            "style",
        }:
            self.issues.append(f"forbidden element <{normalized_tag}>")
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = html.unescape(raw_value or "")
            if name.startswith("on"):
                self.issues.append(f"event attribute {name}")
                continue
            if name == "style" and re.search(
                r"(?:url\s*\(|expression\s*\(|behavior\s*:|-moz-binding)",
                value,
                flags=re.IGNORECASE,
            ):
                self.issues.append("executable or external inline style")
            if name not in URL_ATTRIBUTES or not value.strip():
                continue
            compact = re.sub(r"[\x00-\x20\x7f]+", "", value).lower()
            if compact.startswith("#"):
                continue
            if name in {"src", "xlink:href"} and re.fullmatch(
                r"data:image/(?:png|jpeg|gif|webp|svg\+xml);base64,[a-z0-9+/=]+",
                compact,
                flags=re.IGNORECASE,
            ):
                continue
            self.issues.append(f"non-inline or executable URL in {name}")


def _validate_trusted_markup(markup: object, label: str) -> str:
    text = _string(markup, label)
    parser = TrustedMarkupParser()
    parser.feed(text)
    parser.close()
    if parser.issues:
        raise ValueError(
            f"{label} contains unsafe markup: {sorted(set(parser.issues))}"
        )
    if TOKEN.search(text):
        raise ValueError(f"{label} contains a reserved template token")
    return text


def _render_template(template: str, values: Mapping[str, str], label: str) -> str:
    missing = sorted(set(TOKEN.findall(template)) - set(values))
    if missing:
        raise ValueError(f"{label} is missing template values: {missing}")
    return TOKEN.sub(lambda match: values[match.group(1)], template)


def _render_scalar(value: object, schema: Mapping[str, Any], label: str) -> str:
    slot_type = schema["type"]
    required = bool(schema.get("required", False))
    if value is None:
        if required:
            raise ValueError(f"{label} is required")
        return ""
    if slot_type == "text":
        text = _string(value, label, allow_empty=not required)
        if len(text) > int(schema["max_chars"]):
            raise ValueError(
                f"{label} exceeds its {schema['max_chars']}-character budget"
            )
        return _escape_text(text)
    if slot_type == "enum":
        text = _string(value, label, allow_empty=not required)
        if not text and not required:
            return ""
        if text not in schema["values"]:
            raise ValueError(f"{label} must be one of {schema['values']}")
        return _escape_text(text)
    if slot_type == "data_uri":
        text = _string(value, label, allow_empty=not required)
        if not text and not required:
            return ""
        if not re.fullmatch(
            r"data:image/(?:png|jpeg|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=\s]+",
            text,
            re.IGNORECASE,
        ):
            raise ValueError(f"{label} must be an inline base64 image data URI")
        return html.escape(text, quote=True)
    raise ValueError(f"{label} cannot be rendered as a scalar")


def _render_items(
    value: object,
    schema: Mapping[str, Any],
    *,
    label: str,
    library_dir: Path,
    fragment_mode: str,
    max_fragments: int,
    used_fragments: list[int],
) -> tuple[str, int, list[str]]:
    if value is None:
        if schema.get("required", False):
            raise ValueError(f"{label} is required")
        items: Sequence[Any] = ()
    else:
        items = _sequence(value, label)
    if not int(schema["min_items"]) <= len(items) <= int(schema["max_items"]):
        raise ValueError(
            f"{label} must contain {schema['min_items']} to {schema['max_items']} items"
        )

    item_template_path = _safe_asset_path(
        library_dir,
        schema["item_template"],
        f"{label}.item_template",
    )
    item_template = item_template_path.read_text(encoding="utf-8")
    field_schemas = _mapping(schema["item_fields"], f"{label}.item_fields")
    rendered: list[str] = []
    plain_text: list[str] = []
    for item_index, raw_item in enumerate(items):
        item_label = f"{label}[{item_index}]"
        item = _mapping(raw_item, item_label)
        unexpected = sorted(set(item) - set(field_schemas) - {"_fragment"})
        if unexpected:
            raise ValueError(f"{item_label} has unknown fields: {unexpected}")
        values: dict[str, str] = {}
        for field_name, raw_field_schema in field_schemas.items():
            field_schema = _mapping(raw_field_schema, f"{item_label}.{field_name}")
            raw_field = item.get(field_name)
            values[field_name] = _render_scalar(
                raw_field,
                field_schema,
                f"{item_label}.{field_name}",
            )
            if isinstance(raw_field, str):
                plain_text.append(raw_field)

        fragment = item.get("_fragment")
        if fragment is None:
            values["fragment_attr"] = ""
        else:
            if fragment_mode != "items":
                raise ValueError(f"{item_label} cannot use fragments in this layout")
            if (
                not isinstance(fragment, int)
                or isinstance(fragment, bool)
                or fragment < 1
                or fragment > max_fragments
            ):
                raise ValueError(f"{item_label} has an invalid _fragment")
            used_fragments.append(fragment)
            values["fragment_attr"] = f' data-fragment="{fragment}"'
        rendered.append(_render_template(item_template, values, item_label).rstrip())
    return "\n".join(rendered), len(items), plain_text


def _render_extension(
    value: object,
    schema: Mapping[str, Any],
    *,
    slot_name: str,
    label: str,
    slide: RenderContext,
    renderer_dispatch: RendererDispatch,
) -> str:
    if value is None:
        if schema.get("required", False):
            raise ValueError(f"{label} is required")
        return ""
    payload = _mapping(value, label)
    renderer_name = _string(payload.get("renderer"), f"{label}.renderer")
    expected_renderer = str(schema["renderer"])
    if renderer_name != expected_renderer:
        raise ValueError(f"{label}.renderer must be {expected_renderer!r}")
    _mapping(payload.get("spec"), f"{label}.spec")
    _validate_refs(payload.get("source_refs"), f"{label}.source_refs")
    _validate_refs(payload.get("claim_refs"), f"{label}.claim_refs")
    renderer = renderer_dispatch.get(renderer_name)
    if renderer is None:
        raise ValueError(f"No extension renderer registered for {renderer_name!r}")
    # Dispatch is deterministic only at the explicit renderer boundary. It does not
    # select a layout, interpret a claim, or make any semantic presentation choice.
    rendered = renderer(
        slot_name=slot_name,
        value=MappingProxyType(dict(payload)),
        slot_schema=MappingProxyType(dict(schema)),
        slide=slide,
    )
    if not isinstance(rendered, str):
        raise ValueError(f"Renderer {renderer_name!r} must return an HTML string")
    return _validate_trusted_markup(rendered, f"renderer {renderer_name!r} output")


def _plain_text_for_density(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [
            text
            for nested in value.values()
            for text in _plain_text_for_density(nested)
        ]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [text for nested in value for text in _plain_text_for_density(nested)]
    return []


def _section_attributes(
    *,
    slide_id: str,
    title: str,
    chapter: str,
    chapter_label: str,
    tone: str,
    layout_id: str,
    source_refs: tuple[str, ...],
    claim_refs: tuple[str, ...],
    slide_class: str,
    active: bool,
) -> str:
    classes = ["slide"]
    if slide_class:
        classes.extend(slide_class.split())
    if active:
        classes.append("is-active")
    attributes = [
        f'class="{html.escape(" ".join(classes), quote=True)}"',
        f'id="{html.escape(slide_id, quote=True)}"',
        f'data-slide-title="{_escape_text(title)}"',
        f'data-chapter="{html.escape(chapter, quote=True)}"',
        f'data-chapter-label="{_escape_text(chapter_label)}"',
        f'data-layout-id="{html.escape(layout_id, quote=True)}"',
        f'aria-hidden="{"false" if active else "true"}"',
    ]
    if tone == "dark":
        attributes.append('data-tone="dark"')
    if source_refs:
        attributes.append(
            f'data-source-ids="{html.escape(" ".join(source_refs), quote=True)}"'
        )
    if claim_refs:
        attributes.append(
            f'data-claim-ids="{html.escape(" ".join(claim_refs), quote=True)}"'
        )
    return " ".join(attributes)


def _validate_slide_common(
    slide: Mapping[str, Any],
    *,
    index: int,
    seen_ids: set[str],
) -> tuple[str, str, str, str, str, str, tuple[str, ...], tuple[str, ...]]:
    label = f"deck_plan.slides[{index}]"
    slide_id = _string(slide.get("id"), f"{label}.id")
    if not SAFE_SLIDE_ID.fullmatch(slide_id):
        raise ValueError(f"{label}.id must match {SAFE_SLIDE_ID.pattern}")
    if slide_id in seen_ids:
        raise ValueError(f"Duplicate slide id: {slide_id}")
    seen_ids.add(slide_id)
    layout_id = _string(slide.get("layout_id"), f"{label}.layout_id")
    title = _string(slide.get("title"), f"{label}.title")
    chapter = _string(slide.get("chapter"), f"{label}.chapter")
    if not SAFE_SLIDE_ID.fullmatch(chapter):
        raise ValueError(f"{label}.chapter must be a stable lowercase identifier")
    chapter_label = _string(slide.get("chapter_label"), f"{label}.chapter_label")
    notes = _string(slide.get("notes"), f"{label}.notes")
    source_refs = _validate_refs(slide.get("source_refs"), f"{label}.source_refs")
    claim_refs = _validate_refs(slide.get("claim_refs"), f"{label}.claim_refs")
    return (
        slide_id,
        layout_id,
        title,
        chapter,
        chapter_label,
        notes,
        source_refs,
        claim_refs,
    )


def _compose_registered_slide(
    slide: Mapping[str, Any],
    *,
    layout: Mapping[str, Any],
    library_dir: Path,
    index: int,
    common: tuple[str, str, str, str, str, str, tuple[str, ...], tuple[str, ...]],
    renderer_dispatch: RendererDispatch,
) -> str:
    (
        slide_id,
        layout_id,
        title,
        chapter,
        chapter_label,
        notes,
        source_refs,
        claim_refs,
    ) = common
    label = f"deck_plan.slides[{index}]"
    allowed = {
        "id",
        "layout_id",
        "title",
        "chapter",
        "chapter_label",
        "tone",
        "notes",
        "source_refs",
        "claim_refs",
        "slots",
    }
    unexpected_slide_fields = sorted(set(slide) - allowed)
    if unexpected_slide_fields:
        raise ValueError(f"{label} has unknown fields: {unexpected_slide_fields}")

    tone = _string(slide.get("tone", "light"), f"{label}.tone")
    if tone not in layout["tone_options"]:
        raise ValueError(f"{label}.tone is not supported by layout {layout_id!r}")
    slots = _mapping(slide.get("slots"), f"{label}.slots")
    slot_schemas = _mapping(layout["slots"], f"layout {layout_id}.slots")
    unexpected_slots = sorted(set(slots) - set(slot_schemas))
    if unexpected_slots:
        raise ValueError(f"{label}.slots has unknown slots: {unexpected_slots}")

    headline_slot = str(layout["headline_slot"])
    if slots.get(headline_slot) != title:
        raise ValueError(f"{label}.title must exactly match slots.{headline_slot}")
    headline_limit = int(
        _mapping(layout["typography_budget"], "typography")["headline_max_chars"]
    )
    if len(title) > headline_limit:
        raise ValueError(
            f"{label}.title exceeds the {headline_limit}-character headline budget"
        )

    fragment_policy = _mapping(layout["fragment_support"], "fragment policy")
    used_fragments: list[int] = []
    rendered_slots: dict[str, str] = {}
    item_count = 0
    density_text: list[str] = []
    context = RenderContext(
        slide_id=slide_id,
        layout_id=layout_id,
        title=title,
        source_refs=source_refs,
        claim_refs=claim_refs,
    )
    for slot_name, raw_slot_schema in slot_schemas.items():
        slot_schema = _mapping(raw_slot_schema, f"layout {layout_id}.slots.{slot_name}")
        value = slots.get(slot_name)
        slot_type = slot_schema["type"]
        slot_label = f"{label}.slots.{slot_name}"
        if slot_type == "items":
            rendered, count, text_values = _render_items(
                value,
                slot_schema,
                label=slot_label,
                library_dir=library_dir,
                fragment_mode=str(fragment_policy["mode"]),
                max_fragments=int(fragment_policy["max_fragments"]),
                used_fragments=used_fragments,
            )
            rendered_slots[slot_name] = rendered
            item_count += count
            density_text.extend(text_values)
        elif slot_type == "extension":
            rendered_slots[slot_name] = _render_extension(
                value,
                slot_schema,
                slot_name=slot_name,
                label=slot_label,
                slide=context,
                renderer_dispatch=renderer_dispatch,
            )
        else:
            rendered_slots[slot_name] = _render_scalar(value, slot_schema, slot_label)
            if isinstance(value, str):
                density_text.append(value)

    distinct_fragments = sorted(set(used_fragments))
    if distinct_fragments and distinct_fragments != list(
        range(1, max(distinct_fragments) + 1)
    ):
        raise ValueError(f"{label} fragment numbers must be contiguous from 1")

    density = _mapping(layout["density_budget"], "density budget")
    word_count = sum(len(WORD.findall(text)) for text in density_text)
    if word_count > int(density["max_total_words"]):
        raise ValueError(
            f"{label} uses {word_count} words; layout {layout_id!r} allows "
            f"{density['max_total_words']}"
        )
    if item_count > int(density["max_items"]):
        raise ValueError(
            f"{label} uses {item_count} items; layout {layout_id!r} allows "
            f"{density['max_items']}"
        )

    template_path = _safe_asset_path(
        library_dir,
        layout["template"],
        f"layout {layout_id}.template",
    )
    inner_html = _render_template(
        template_path.read_text(encoding="utf-8"),
        rendered_slots,
        f"layout {layout_id}",
    ).strip()
    attributes = _section_attributes(
        slide_id=slide_id,
        title=title,
        chapter=chapter,
        chapter_label=chapter_label,
        tone=tone,
        layout_id=layout_id,
        source_refs=source_refs,
        claim_refs=claim_refs,
        slide_class=str(layout["slide_class"]),
        active=index == 0,
    )
    typography = _mapping(layout["typography_budget"], "typography budget")
    headline_max_lines = int(typography["headline_max_lines"])
    body_min_px = int(typography["body_min_px"])
    body_min_cqw = body_min_px / 12.8
    attributes += (
        f' data-qa-headline-max-lines="{headline_max_lines}"'
        f' data-qa-body-min-px="{body_min_px}"'
        f' style="--clara-body-min: {body_min_cqw:.6g}cqw"'
    )
    return (
        f"    <section {attributes}>\n"
        f"{inner_html}\n"
        f'      <aside class="speaker-notes">{_escape_text(notes)}</aside>\n'
        "    </section>"
    )


def _compose_bespoke_slide(
    slide: Mapping[str, Any],
    *,
    index: int,
    common: tuple[str, str, str, str, str, str, tuple[str, ...], tuple[str, ...]],
    allow_bespoke_html: bool,
) -> str:
    (
        slide_id,
        layout_id,
        title,
        chapter,
        chapter_label,
        notes,
        source_refs,
        claim_refs,
    ) = common
    label = f"deck_plan.slides[{index}]"
    allowed = {
        "id",
        "layout_id",
        "title",
        "chapter",
        "chapter_label",
        "tone",
        "notes",
        "source_refs",
        "claim_refs",
        "bespoke_html",
    }
    unexpected = sorted(set(slide) - allowed)
    if unexpected:
        raise ValueError(f"{label} has unknown fields: {unexpected}")
    if not allow_bespoke_html:
        raise ValueError(
            f"{label} uses the bespoke HTML escape hatch without deck_plan.allow_bespoke_html"
        )
    raw_html = _validate_trusted_markup(
        slide.get("bespoke_html"), f"{label}.bespoke_html"
    )
    if re.search(r"<(?:section|aside)\b", raw_html, re.IGNORECASE):
        raise ValueError(f"{label}.bespoke_html must contain slide body markup only")
    tone = _string(slide.get("tone", "light"), f"{label}.tone")
    if tone not in {"light", "dark"}:
        raise ValueError(f"{label}.tone must be 'light' or 'dark'")
    attributes = _section_attributes(
        slide_id=slide_id,
        title=title,
        chapter=chapter,
        chapter_label=chapter_label,
        tone=tone,
        layout_id=layout_id,
        source_refs=source_refs,
        claim_refs=claim_refs,
        slide_class="slide--top",
        active=index == 0,
    )
    return (
        f"    <section {attributes}>\n"
        f"{raw_html.strip()}\n"
        f'      <aside class="speaker-notes">{_escape_text(notes)}</aside>\n'
        "    </section>"
    )


def compose_deck(
    plan: Mapping[str, Any],
    *,
    registry_path: Path | None = None,
    renderer_dispatch: RendererDispatch | None = None,
    existing_custom_css: str = "",
) -> CompositionResult:
    """Validate a deck plan and compose editable HTML/CSS without semantic choices."""

    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported deck plan schema: {plan.get('schema_version')!r}"
        )
    allowed_plan_fields = {"schema_version", "allow_bespoke_html", "slides"}
    unexpected_plan_fields = sorted(set(plan) - allowed_plan_fields)
    if unexpected_plan_fields:
        raise ValueError(f"deck_plan has unknown fields: {unexpected_plan_fields}")
    allow_bespoke_html = plan.get("allow_bespoke_html", False)
    if not isinstance(allow_bespoke_html, bool):
        raise ValueError("deck_plan.allow_bespoke_html must be a boolean")
    raw_slides = _sequence(plan.get("slides"), "deck_plan.slides")
    if not raw_slides:
        raise ValueError("deck_plan.slides cannot be empty")

    registry = load_registry(registry_path)
    layouts = _mapping(registry["layouts"], "registry layouts")
    library_dir = Path(registry["library_dir"])
    dispatch = (
        renderer_dispatch
        if renderer_dispatch is not None
        else _load_renderer_modules([Path(__file__).with_name("data_visuals.py")])
    )
    seen_ids: set[str] = set()
    rendered_slides: list[str] = []
    used_layouts: list[str] = []
    for index, raw_slide in enumerate(raw_slides):
        slide = _mapping(raw_slide, f"deck_plan.slides[{index}]")
        common = _validate_slide_common(slide, index=index, seen_ids=seen_ids)
        layout_id = common[1]
        if layout_id == "bespoke":
            rendered = _compose_bespoke_slide(
                slide,
                index=index,
                common=common,
                allow_bespoke_html=allow_bespoke_html,
            )
        else:
            raw_layout = layouts.get(layout_id)
            if raw_layout is None:
                raise ValueError(
                    f"deck_plan.slides[{index}].layout_id is unknown: {layout_id!r}"
                )
            rendered = _compose_registered_slide(
                slide,
                layout=_mapping(raw_layout, f"layout {layout_id}"),
                library_dir=library_dir,
                index=index,
                common=common,
                renderer_dispatch=dispatch,
            )
        rendered_slides.append(rendered)
        used_layouts.append(layout_id)

    css = Path(registry["css_path"]).read_text(encoding="utf-8").rstrip()
    if GENERATED_CSS_END in existing_custom_css:
        authored_css = existing_custom_css.split(GENERATED_CSS_END, 1)[1].lstrip("\n")
    else:
        authored_css = existing_custom_css.strip()
        if authored_css:
            authored_css += "\n"
    if not authored_css:
        authored_css = f"{AUTHOR_CSS_HEADER}\n"
    elif not authored_css.startswith(AUTHOR_CSS_HEADER):
        authored_css = f"{AUTHOR_CSS_HEADER}\n{authored_css}"
    return CompositionResult(
        slides_html="\n\n".join(rendered_slides) + "\n",
        custom_css=(
            f"{GENERATED_CSS_START}\n{css}\n{GENERATED_CSS_END}\n" f"{authored_css}"
        ),
        slide_count=len(rendered_slides),
        layout_ids=tuple(used_layouts),
    )


def _load_renderer_modules(paths: Sequence[Path]) -> dict[str, ExtensionRenderer]:
    dispatch: dict[str, ExtensionRenderer] = {}
    for index, path in enumerate(paths):
        resolved = path.expanduser().resolve()
        spec = importlib.util.spec_from_file_location(
            f"clara_deck_renderer_{index}", resolved
        )
        if not spec or not spec.loader:
            raise ValueError(f"Unable to load renderer module: {resolved}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        renderers = _mapping(
            getattr(module, "RENDERERS", None), f"{resolved}.RENDERERS"
        )
        for name, renderer in renderers.items():
            if not isinstance(name, str) or not name:
                raise ValueError(f"{resolved}.RENDERERS has an invalid name")
            if not callable(renderer):
                raise ValueError(f"{resolved}.RENDERERS[{name!r}] is not callable")
            if name in dispatch:
                raise ValueError(f"Duplicate renderer name: {name!r}")
            dispatch[name] = renderer
    return dispatch


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except (OSError, UnicodeError):
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck_plan", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--registry", type=Path, default=default_registry_path())
    parser.add_argument("--renderer-module", action="append", type=Path, default=[])
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan_path = args.deck_plan.expanduser().resolve()
        plan = _mapping(json.loads(plan_path.read_text(encoding="utf-8")), "deck plan")
        output_dir = args.output_dir.expanduser().resolve()
        slides_path = output_dir / "slides.html"
        css_path = output_dir / "custom.css"
        existing = [str(path) for path in (slides_path, css_path) if path.exists()]
        if existing and not args.force:
            raise ValueError(
                f"Refusing to replace existing files without --force: {existing}"
            )
        existing_custom_css = (
            css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
        )
        renderers = _load_renderer_modules(
            [Path(__file__).with_name("data_visuals.py"), *args.renderer_module]
        )
        result = compose_deck(
            plan,
            registry_path=args.registry,
            renderer_dispatch=renderers,
            existing_custom_css=existing_custom_css,
        )
        _atomic_write_text(slides_path, result.slides_html)
        _atomic_write_text(css_path, result.custom_css)
        payload = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "deck_plan": str(plan_path),
            "slides": str(slides_path),
            "custom_css": str(css_path),
            "slide_count": result.slide_count,
            "layout_ids": list(result.layout_ids),
        }
        sys.stdout.write(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
