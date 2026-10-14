#!/usr/bin/env python3
"""Render deterministic, accessible Clara HTML data components.

The renderers handle only mechanically verifiable transformations of supplied
data. They deliberately do not choose analytical filters, periods, claims, or
chart types; those remain model/advisor decisions recorded in the deck plan.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import math
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "RENDERERS",
    "SUPPORTED_VISUALS",
    "render_data_visual_slot",
    "render_visual",
    "validate_visual_spec",
]

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = "clara.html_deck_visual.v1"
SUPPORTED_VISUALS = frozenset(
    {"bar", "line", "scatter", "bubble", "waterfall", "timeline", "table"}
)
SVG_WIDTH = 600.0
SVG_HEIGHT = 300.0
PLOT_LEFT = 56.0
PLOT_RIGHT = 574.0
PLOT_TOP = 24.0
PLOT_BOTTOM = 250.0
MAX_TITLE_CHARS = 100
MAX_DESCRIPTION_CHARS = 240
MAX_SOURCE_NOTE_CHARS = 180
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a list")
    return list(value)


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _required_text(spec: Mapping[str, Any], key: str) -> str:
    raw_value = spec.get(key)
    if not isinstance(raw_value, str):
        raise ValueError(f"visual.{key} must be text")
    value = raw_value.strip()
    if not value:
        raise ValueError(f"visual.{key} is required")
    return value


def _bounded_text(
    value: Any,
    *,
    label: str,
    max_chars: int,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if not text:
        raise ValueError(f"{label} is required")
    if len(text) > max_chars:
        raise ValueError(f"{label} exceeds the {max_chars}-character budget")
    return text


def _optional_text(
    spec: Mapping[str, Any],
    key: str,
    *,
    max_chars: int,
) -> str:
    raw_value = spec.get(key)
    if raw_value is None:
        return ""
    if not isinstance(raw_value, str):
        raise ValueError(f"visual.{key} must be text")
    value = raw_value.strip()
    if len(value) > max_chars:
        raise ValueError(f"visual.{key} exceeds the {max_chars}-character budget")
    return value


def _item_budget(items: Sequence[Any], *, label: str, maximum: int) -> None:
    if not items:
        raise ValueError(f"{label} cannot be empty")
    if len(items) > maximum:
        raise ValueError(f"{label} exceeds the {maximum}-item budget")


def _dynamic_label_budget(*, spacing: float, maximum: int, minimum: int = 4) -> int:
    """Return a conservative 12px-monospace label budget for a chart interval."""

    return max(minimum, min(maximum, math.floor((spacing - 8.0) / 7.2)))


def _fmt(value: float) -> str:
    if value and (abs(value) >= 1_000_000 or abs(value) < 0.001):
        return f"{value:.3g}"
    if math.isclose(value, round(value), abs_tol=1e-9):
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _extent(
    values: Sequence[float], *, include_zero: bool = False
) -> tuple[float, float]:
    if not values:
        raise ValueError("visual data cannot be empty")
    low = min(values)
    high = max(values)
    if include_zero:
        low = min(low, 0.0)
        high = max(high, 0.0)
    if math.isclose(low, high):
        pad = abs(low) * 0.1 or 1.0
        low -= pad
        high += pad
    return low, high


def _scale(
    value: float, low: float, high: float, out_low: float, out_high: float
) -> float:
    return out_low + ((value - low) / (high - low)) * (out_high - out_low)


def _source_attrs(spec: Mapping[str, Any]) -> str:
    component_id = _required_text(spec, "id")
    if not SAFE_REF.fullmatch(component_id):
        raise ValueError("visual.id must be a safe identifier")
    raw_source_ids = _sequence(spec.get("source_ids", []), label="visual.source_ids")
    if any(not isinstance(item, str) for item in raw_source_ids):
        raise ValueError("visual.source_ids must contain only text identifiers")
    source_ids = [item.strip() for item in raw_source_ids]
    if (
        not source_ids
        or any(not item for item in source_ids)
        or any(not SAFE_REF.fullmatch(item) for item in source_ids)
    ):
        raise ValueError(
            "visual.source_ids must contain at least one safe non-empty source ID"
        )
    source_value = " ".join(sorted(set(source_ids)))
    return (
        f'data-component-id="{_text(component_id)}" '
        f'data-source-ids="{_text(source_value)}" '
        'data-qa-role="data-visual"'
    )


def _svg_open(spec: Mapping[str, Any], visual_type: str) -> str:
    title = _bounded_text(
        spec.get("title"), label="visual.title", max_chars=MAX_TITLE_CHARS
    )
    aria_label = (
        _optional_text(
            spec,
            "aria_label",
            max_chars=MAX_DESCRIPTION_CHARS,
        )
        or title
    )
    description = _optional_text(
        spec,
        "description",
        max_chars=MAX_DESCRIPTION_CHARS,
    )
    description_markup = f"<desc>{_text(description)}</desc>" if description else ""
    return (
        f'<figure class="data-visual data-visual--{visual_type}" {_source_attrs(spec)}>'
        f"<figcaption>{_text(title)}</figcaption>"
        f'<svg viewBox="0 0 {int(SVG_WIDTH)} {int(SVG_HEIGHT)}" role="img" '
        f'aria-label="{_text(aria_label)}"><title>{_text(title)}</title>{description_markup}'
    )


def _svg_close(spec: Mapping[str, Any]) -> str:
    note = _optional_text(
        spec,
        "source_note",
        max_chars=MAX_SOURCE_NOTE_CHARS,
    )
    note_markup = f'<p class="data-source-note">{_text(note)}</p>' if note else ""
    return f"</svg>{note_markup}</figure>"


def _render_bar(spec: Mapping[str, Any]) -> str:
    rows = [
        _mapping(item, label="visual.data[]")
        for item in _sequence(spec.get("data"), label="visual.data")
    ]
    _item_budget(rows, label="visual.data", maximum=8)
    values = [_number(row.get("value"), label="visual.data[].value") for row in rows]
    low, high = _extent(values, include_zero=True)
    row_height = min(42.0, 198.0 / max(1, len(rows)))
    baseline = _scale(0.0, low, high, PLOT_LEFT + 130.0, PLOT_RIGHT)
    parts = [_svg_open(spec, "bar")]
    for index, (row, value) in enumerate(zip(rows, values, strict=True)):
        label = _bounded_text(
            row.get("label"), label="visual.data[].label", max_chars=16
        )
        y = PLOT_TOP + 22.0 + index * row_height
        x_value = _scale(value, low, high, PLOT_LEFT + 130.0, PLOT_RIGHT)
        x = min(baseline, x_value)
        width = max(1.0, abs(x_value - baseline))
        parts.append(
            f'<text class="data-axis-label" x="{PLOT_LEFT:.1f}" y="{y + 4:.1f}">{_text(label)}</text>'
            f'<rect class="data-mark data-mark--bar" x="{x:.2f}" y="{y - 10:.2f}" '
            f'width="{width:.2f}" height="18" rx="3" data-value="{_text(_fmt(value))}" />'
            f'<text class="data-value-label" x="{x_value + (8 if value >= 0 else -8):.2f}" '
            f'y="{y + 4:.1f}" text-anchor="{"start" if value >= 0 else "end"}">{_text(_fmt(value))}</text>'
        )
    parts.append(_svg_close(spec))
    return "".join(parts)


def _line_points(
    spec: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], list[float]]:
    points = [
        _mapping(item, label="visual.data[]")
        for item in _sequence(spec.get("data"), label="visual.data")
    ]
    _item_budget(points, label="visual.data", maximum=10)
    values = [
        _number(point.get("value"), label="visual.data[].value") for point in points
    ]
    if len(points) < 2:
        raise ValueError("line visual requires at least two data points")
    return points, values


def _render_line(spec: Mapping[str, Any]) -> str:
    points, values = _line_points(spec)
    low, high = _extent(values)
    coords: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        x = _scale(index, 0.0, float(len(values) - 1), PLOT_LEFT, PLOT_RIGHT)
        y = _scale(value, low, high, PLOT_BOTTOM, PLOT_TOP)
        coords.append((x, y))
    path = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in coords)
    parts = [_svg_open(spec, "line"), '<path class="data-grid-line" d="M56 250H574" />']
    label_budget = _dynamic_label_budget(
        spacing=(PLOT_RIGHT - PLOT_LEFT) / (len(points) - 1), maximum=18
    )
    parts.append(f'<path class="data-line anim-draw" pathLength="1" d="{path}" />')
    for point, value, (x, y) in zip(points, values, coords, strict=True):
        label = _bounded_text(
            point.get("label"),
            label="visual.data[].label",
            max_chars=label_budget,
        )
        parts.append(
            f'<circle class="data-mark data-mark--point" cx="{x:.2f}" cy="{y:.2f}" r="4" />'
            f'<text class="data-axis-label" x="{x:.2f}" y="274" text-anchor="middle">{_text(label)}</text>'
        )
    end_x, end_y = coords[-1]
    parts.append(
        f'<text class="data-value-label" x="{end_x - 4:.2f}" y="{max(15, end_y - 10):.2f}" '
        f'text-anchor="end">{_text(_fmt(values[-1]))}</text>'
    )
    parts.append(_svg_close(spec))
    return "".join(parts)


def _render_scatter(spec: Mapping[str, Any], *, bubble: bool) -> str:
    points = [
        _mapping(item, label="visual.data[]")
        for item in _sequence(spec.get("data"), label="visual.data")
    ]
    _item_budget(points, label="visual.data", maximum=8)
    x_axis_label = _bounded_text(
        spec.get("x_axis_label"), label="visual.x_axis_label", max_chars=40
    )
    y_axis_label = _bounded_text(
        spec.get("y_axis_label"), label="visual.y_axis_label", max_chars=40
    )
    size_axis_label = (
        _bounded_text(
            spec.get("size_axis_label"),
            label="visual.size_axis_label",
            max_chars=40,
        )
        if bubble
        else ""
    )
    x_values = [_number(point.get("x"), label="visual.data[].x") for point in points]
    y_values = [_number(point.get("y"), label="visual.data[].y") for point in points]
    sizes = [
        _number(point.get("size", 1.0), label="visual.data[].size") if bubble else 1.0
        for point in points
    ]
    if bubble and any(size <= 0 for size in sizes):
        raise ValueError("visual.data[].size must be positive")
    x_low, x_high = _extent(x_values)
    y_low, y_high = _extent(y_values)
    size_low, size_high = min(sizes), max(sizes)
    if bubble and size_high / size_low > 25:
        raise ValueError("visual.data[].size range exceeds the 25:1 legibility budget")
    visual_type = "bubble" if bubble else "scatter"
    plot_left = 76.0
    plot_right = 486.0 if bubble else 566.0
    plot_top = 34.0
    plot_bottom = 232.0
    parts = [
        _svg_open(spec, visual_type),
        f'<path class="data-grid-line" d="M{plot_left:.0f} {plot_bottom:.0f}H{plot_right:.0f}'
        f'M{plot_left:.0f} {plot_top:.0f}V{plot_bottom:.0f}" />',
    ]
    for tick_index, value in enumerate((x_low, (x_low + x_high) / 2, x_high)):
        x = _scale(float(tick_index), 0.0, 2.0, plot_left, plot_right)
        parts.append(
            f'<path class="data-grid-tick" d="M{x:.2f} {plot_bottom:.0f}v5" />'
            f'<text class="data-axis-tick" x="{x:.2f}" y="249" text-anchor="middle">{_text(_fmt(value))}</text>'
        )
    for tick_index, value in enumerate((y_low, (y_low + y_high) / 2, y_high)):
        y = _scale(float(tick_index), 0.0, 2.0, plot_bottom, plot_top)
        parts.append(
            f'<path class="data-grid-tick" d="M{plot_left - 5:.0f} {y:.2f}h5" />'
            f'<text class="data-axis-tick" x="{plot_left - 9:.0f}" y="{y + 3:.2f}" text-anchor="end">{_text(_fmt(value))}</text>'
        )
    parts.append(
        f'<text class="data-axis-title" x="{(plot_left + plot_right) / 2:.2f}" y="284" text-anchor="middle">{_text(x_axis_label)}</text>'
        f'<text class="data-axis-title" x="14" y="{(plot_top + plot_bottom) / 2:.2f}" '
        f'text-anchor="middle" transform="rotate(-90 14 {(plot_top + plot_bottom) / 2:.2f})">{_text(y_axis_label)}</text>'
    )
    if bubble:
        small_radius = math.sqrt(size_low / size_high) * 20.0
        parts.append(
            '<g class="data-size-legend" aria-label="Bubble size legend">'
            f'<text class="data-axis-title" x="505" y="35">{_text(size_axis_label)}</text>'
            f'<circle class="data-mark data-mark--bubble" cx="525" cy="71" r="{small_radius:.2f}" />'
            f'<text class="data-axis-tick" x="551" y="75">{_text(_fmt(size_low))}</text>'
            '<circle class="data-mark data-mark--bubble" cx="525" cy="122" r="20" />'
            f'<text class="data-axis-tick" x="551" y="126">{_text(_fmt(size_high))}</text>'
            "</g>"
        )
    for point, x_value, y_value, size in zip(
        points, x_values, y_values, sizes, strict=True
    ):
        label = _bounded_text(
            point.get("label"), label="visual.data[].label", max_chars=20
        )
        x = _scale(x_value, x_low, x_high, plot_left + 8, plot_right - 8)
        y = _scale(y_value, y_low, y_high, plot_bottom - 8, plot_top + 8)
        radius = math.sqrt(size / size_high) * 20.0 if bubble else 6.0
        size_attribute = f' data-size="{_text(_fmt(size))}"' if bubble else ""
        parts.append(
            f'<circle class="data-mark data-mark--bubble" cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" '
            f'data-x="{_text(_fmt(x_value))}" data-y="{_text(_fmt(y_value))}"{size_attribute} />'
            f'<text class="data-value-label" x="{x + radius + 4:.2f}" y="{y + 4:.2f}">{_text(label)}</text>'
        )
    parts.append(_svg_close(spec))
    return "".join(parts)


def _render_waterfall(spec: Mapping[str, Any]) -> str:
    rows = [
        _mapping(item, label="visual.data[]")
        for item in _sequence(spec.get("data"), label="visual.data")
    ]
    _item_budget(rows, label="visual.data", maximum=8)
    deltas = [_number(row.get("value"), label="visual.data[].value") for row in rows]
    cumulative = [0.0]
    for delta in deltas:
        cumulative.append(cumulative[-1] + delta)
    low, high = _extent(cumulative, include_zero=True)
    bar_width = min(56.0, 430.0 / max(1, len(rows)))
    gap = (PLOT_RIGHT - PLOT_LEFT) / max(1, len(rows))
    label_budget = _dynamic_label_budget(spacing=gap, maximum=18)
    parts = [
        _svg_open(spec, "waterfall"),
        '<path class="data-grid-line" d="M56 250H574" />',
    ]
    for index, (row, delta) in enumerate(zip(rows, deltas, strict=True)):
        label = _bounded_text(
            row.get("label"),
            label="visual.data[].label",
            max_chars=label_budget,
        )
        start = cumulative[index]
        end = cumulative[index + 1]
        y_start = _scale(start, low, high, PLOT_BOTTOM, PLOT_TOP)
        y_end = _scale(end, low, high, PLOT_BOTTOM, PLOT_TOP)
        x = PLOT_LEFT + index * gap + (gap - bar_width) / 2
        y = min(y_start, y_end)
        height = max(1.0, abs(y_end - y_start))
        polarity = "positive" if delta >= 0 else "negative"
        parts.append(
            f'<rect class="data-mark data-mark--waterfall data-mark--{polarity}" x="{x:.2f}" y="{y:.2f}" '
            f'width="{bar_width:.2f}" height="{height:.2f}" />'
            f'<text class="data-value-label" x="{x + bar_width / 2:.2f}" y="{max(14, y - 7):.2f}" '
            f'text-anchor="middle">{_text(_fmt(delta))}</text>'
            f'<text class="data-axis-label" x="{x + bar_width / 2:.2f}" y="274" '
            f'text-anchor="middle">{_text(label)}</text>'
        )
    parts.append(_svg_close(spec))
    return "".join(parts)


def _render_timeline(spec: Mapping[str, Any]) -> str:
    events = [
        _mapping(item, label="visual.data[]")
        for item in _sequence(spec.get("data"), label="visual.data")
    ]
    _item_budget(events, label="visual.data", maximum=6)
    parts = [
        _svg_open(spec, "timeline"),
        '<path class="data-timeline-line" d="M70 142H560" />',
    ]
    for index, event in enumerate(events):
        label = _bounded_text(
            event.get("label"), label="visual.data[].label", max_chars=24
        )
        date = _bounded_text(
            event.get("date"), label="visual.data[].date", max_chars=16
        )
        x = _scale(index, 0.0, float(max(1, len(events) - 1)), 82.0, 548.0)
        above = index % 2 == 0
        label_y = 96.0 if above else 198.0
        text_anchor = (
            "start" if index == 0 else "end" if index == len(events) - 1 else "middle"
        )
        parts.append(
            f'<path class="data-timeline-stem" d="M{x:.2f} 142V{label_y + (9 if above else -18):.2f}" />'
            f'<circle class="data-mark data-mark--point" cx="{x:.2f}" cy="142" r="6" />'
            f'<text class="data-date-label" x="{x:.2f}" y="{label_y:.2f}" text-anchor="{text_anchor}">{_text(date)}</text>'
            f'<text class="data-axis-label" x="{x:.2f}" y="{label_y + 17:.2f}" text-anchor="{text_anchor}">{_text(label)}</text>'
        )
    parts.append(_svg_close(spec))
    return "".join(parts)


def _render_table(spec: Mapping[str, Any]) -> str:
    columns = [
        str(item).strip()
        for item in _sequence(spec.get("columns"), label="visual.columns")
    ]
    if not columns or any(not item for item in columns):
        raise ValueError("visual.columns must contain non-empty labels")
    _item_budget(columns, label="visual.columns", maximum=6)
    if any(len(column) > 28 for column in columns):
        raise ValueError("visual.columns labels exceed the 28-character budget")
    rows = [
        _sequence(item, label="visual.rows[]")
        for item in _sequence(spec.get("rows"), label="visual.rows")
    ]
    _item_budget(rows, label="visual.rows", maximum=8)
    if any(len(row) != len(columns) for row in rows):
        raise ValueError("every visual.rows item must match visual.columns length")
    if any(len(str(value)) > 60 for row in rows for value in row):
        raise ValueError("visual.rows cells exceed the 60-character budget")
    title = _required_text(spec, "title")
    aria_label = (
        _optional_text(
            spec,
            "aria_label",
            max_chars=MAX_DESCRIPTION_CHARS,
        )
        or title
    )
    parts = [
        f'<figure class="data-visual data-visual--table" {_source_attrs(spec)}>',
        f"<figcaption>{_text(title)}</figcaption>",
        f'<table aria-label="{_text(aria_label)}"><thead><tr>',
    ]
    parts.extend(f'<th scope="col">{_text(column)}</th>' for column in columns)
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        for index, value in enumerate(row):
            tag = "th" if index == 0 else "td"
            scope = ' scope="row"' if index == 0 else ""
            parts.append(f"<{tag}{scope}>{_text(value)}</{tag}>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    note = _optional_text(
        spec,
        "source_note",
        max_chars=MAX_SOURCE_NOTE_CHARS,
    )
    if note:
        parts.append(f'<p class="data-source-note">{_text(note)}</p>')
    parts.append("</figure>")
    return "".join(parts)


def validate_visual_spec(spec: Mapping[str, Any]) -> None:
    """Validate the explicit component contract without making semantic choices."""

    if spec.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError(f"unsupported visual schema: {spec.get('schema_version')!r}")
    visual_type = _required_text(spec, "type")
    if visual_type not in SUPPORTED_VISUALS:
        raise ValueError(f"unsupported visual type: {visual_type!r}")
    _required_text(spec, "id")
    _bounded_text(spec.get("title"), label="visual.title", max_chars=MAX_TITLE_CHARS)
    _optional_text(spec, "aria_label", max_chars=MAX_DESCRIPTION_CHARS)
    _optional_text(spec, "description", max_chars=MAX_DESCRIPTION_CHARS)
    _optional_text(spec, "source_note", max_chars=MAX_SOURCE_NOTE_CHARS)
    _source_attrs(spec)


def render_visual(spec: Mapping[str, Any]) -> str:
    """Return safe standalone markup for one explicitly selected visual type."""

    validate_visual_spec(spec)
    visual_type = str(spec["type"])
    if visual_type == "bar":
        return _render_bar(spec)
    if visual_type == "line":
        return _render_line(spec)
    if visual_type == "scatter":
        return _render_scatter(spec, bubble=False)
    if visual_type == "bubble":
        return _render_scatter(spec, bubble=True)
    if visual_type == "waterfall":
        return _render_waterfall(spec)
    if visual_type == "timeline":
        return _render_timeline(spec)
    return _render_table(spec)


def render_data_visual_slot(
    *,
    slot_name: str,
    value: Mapping[str, Any],
    slot_schema: Mapping[str, Any],
    slide: Any,
) -> str:
    """Adapt a composer extension value to the explicit visual renderer.

    Stable IDs and source references are mechanical composition concerns. The
    visual type, data, labels, periods, and analytical meaning must remain
    explicit in ``value['spec']`` and are never selected here.
    """

    del slot_schema
    extension = _mapping(value, label=f"slot {slot_name}")
    spec = dict(_mapping(extension.get("spec"), label=f"slot {slot_name}.spec"))
    if isinstance(slide, Mapping):
        raw_slide_id = slide.get("slide_id", slide.get("id", "slide"))
    else:
        raw_slide_id = getattr(slide, "slide_id", "slide")
    if not isinstance(raw_slide_id, str) or not raw_slide_id.strip():
        raise ValueError(f"slot {slot_name} requires a stable slide ID")
    slide_id = raw_slide_id.strip()
    spec.setdefault("id", f"{slide_id}-{slot_name}")
    if isinstance(slide, Mapping):
        slide_source_refs = slide.get("source_refs", [])
    else:
        slide_source_refs = getattr(slide, "source_refs", ())
    source_refs = extension.get(
        "source_refs",
        spec.get("source_ids", slide_source_refs),
    )
    spec["source_ids"] = _sequence(
        source_refs,
        label=f"slot {slot_name}.source_refs",
    )
    return render_visual(spec)


RENDERERS = {"data_visual": render_data_visual_slot}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="JSON visual specification")
    parser.add_argument("--output", type=Path, help="Write markup to this file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        payload = json.loads(
            args.spec.expanduser().resolve().read_text(encoding="utf-8")
        )
        spec = _mapping(payload, label="visual")
        rendered = render_visual(spec) + "\n"
        if args.output:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
            LOGGER.info("Wrote Clara data visual to %s", output)
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        LOGGER.error("error: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
