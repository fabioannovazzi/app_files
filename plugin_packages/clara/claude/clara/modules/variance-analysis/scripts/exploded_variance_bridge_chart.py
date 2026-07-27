"""Exploded parent/child variance bridge rendering."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
from ibcs_titles import build_ibcs_title, measure_line_segments
from PIL import Image, ImageDraw, ImageFont
from total_by_dimension_bridge_chart import DEFAULT_TOP_N as DEFAULT_PARENT_TOP_N
from total_by_dimension_bridge_chart import (
    NULL_LABEL,
    OTHER_LABEL,
    build_total_by_dimension_bridge_rows,
)

__all__ = [
    "DEFAULT_CHILD_TOP_N",
    "DEFAULT_MAX_DRILLDOWNS",
    "ExplodedVarianceBridgeExport",
    "build_exploded_variance_bridge_spec",
    "validate_exploded_variance_bridge_visual_quality",
    "write_exploded_variance_bridge_artifacts",
]

TOLERANCE = 0.000001
DEFAULT_MAX_DRILLDOWNS = 2
DEFAULT_CHILD_TOP_N = 5
MAX_PARENT_TOP_N = 18
MAX_CHILD_TOP_N = 5
CHART_WIDTH = 1600
CHART_HEIGHT = 900
VISIBLE_FONT_SIZE = 18
MIN_READABLE_ROW_HEIGHT = 30
MIN_NON_WHITE_RATIO = 0.02
MAX_CROP_RISK_INK_RATIO = 0.01
COLORS = {
    "actual": "#1F1F1F",
    "baseline_period": "#A6A6A6",
    "connector": "#2D5BB8",
    "grid": "#E7E7E7",
    "negative": "#D62728",
    "positive": "#65B80F",
    "text": "#1F2328",
    "muted": "#666666",
    "white": "#FFFFFF",
}


@dataclass(frozen=True)
class ExplodedVarianceBridgeExport:
    """Exported exploded bridge artifacts and audit metadata."""

    paths: list[str]
    audit: dict[str, Any]
    summary_markdown: str


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write compact JSON with stable default conversions."""

    path.write_text(
        json.dumps(payload, indent=2, default=_json_default), encoding="utf-8"
    )


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _font(*, bold: bool = False) -> ImageFont.ImageFont:
    """Return one visible font size, with regular or bold face."""

    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=VISIBLE_FONT_SIZE)
        except OSError:
            continue
    return ImageFont.load_default()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _sum_column(df: pl.DataFrame, column: str) -> float:
    if column not in df.schema or df.is_empty():
        return 0.0
    value = df.select(pl.col(column).sum()).item()
    return float(value or 0.0)


def _format_number(value: float, *, signed: bool = True) -> str:
    if not math.isfinite(value):
        return ""
    sign = "+" if signed and value > 0 else "-" if value < 0 else ""
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        text = f"{abs_value / 1_000_000_000:,.1f}B"
    elif abs_value >= 1_000_000:
        text = f"{abs_value / 1_000_000:,.1f}M"
    elif abs_value >= 1_000:
        text = f"{abs_value / 1_000:,.1f}K"
    else:
        text = f"{abs_value:,.0f}"
    return f"{sign}{text}"


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    ellipsis = "..."
    low = 0
    high = len(text)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = f"{text[:mid].rstrip()}{ellipsis}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            low = mid
        else:
            high = mid - 1
    return f"{text[:low].rstrip()}{ellipsis}"


def _draw_segmented_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    segments: tuple[tuple[str, bool], ...],
    *,
    regular_font: ImageFont.ImageFont,
    bold_font: ImageFont.ImageFont,
) -> None:
    x, y = xy
    for text, emphasized in segments:
        if not text:
            continue
        font = bold_font if emphasized else regular_font
        draw.text((x, y), text, fill=COLORS["text"], font=font)
        bbox = draw.textbbox((x, y), text, font=font)
        x += bbox[2] - bbox[0]


def _x_position(value: float, low: float, high: float, left: int, width: int) -> int:
    if abs(high - low) < TOLERANCE:
        high = low + 1.0
    return int(left + ((value - low) / (high - low)) * width)


def _bar_box_from_zero(
    zero_x: int,
    value_x: int,
    y0: int,
    y1: int,
) -> tuple[int, int, int, int]:
    x0 = min(zero_x, value_x)
    x1 = max(zero_x, value_x)
    return (x0, y0, max(x1, x0 + 3), y1)


def _draw_bar(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str | None = None,
    width: int = 1,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(
        (min(x0, x1), y0, max(x0, x1, min(x0, x1) + 3), y1),
        radius=3,
        fill=fill,
        outline=outline,
        width=width,
    )


def _period_labels(recipe: dict[str, Any]) -> tuple[str, str]:
    mappings = recipe.get("mappings") or {}
    return str(mappings.get("baseline_period") or "Baseline"), str(
        mappings.get("comparison_period") or "Comparison"
    )


def _mapped_dimensions(recipe: dict[str, Any], result: pl.DataFrame) -> list[str]:
    return [
        str(dimension)
        for dimension in (recipe.get("mappings") or {}).get("dimensions") or []
        if str(dimension) in result.schema
    ]


def _select_child_dimension(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    parent_dimension: str,
) -> str | None:
    options = recipe.get("options") or {}
    explicit = options.get("exploded_variance_bridge_child_dimension")
    if explicit:
        candidate = str(explicit)
        if candidate in result.schema and candidate != parent_dimension:
            return candidate
        return None
    for dimension in _mapped_dimensions(recipe, result):
        if dimension != parent_dimension:
            return dimension
    return None


def _bounded_positive_int(value: Any, default: int, *, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))


def _row_dicts(rows: pl.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in row.items()
            if value is not None and value != "" and value != []
        }
        for row in rows.to_dicts()
    ]


def _filter_parent_member(
    result: pl.DataFrame,
    parent_dimension: str,
    parent_value: str,
) -> pl.DataFrame:
    value_expr = pl.col(parent_dimension).cast(pl.Utf8).fill_null(NULL_LABEL)
    return result.filter(value_expr == parent_value)


def _select_drilldown_parent_rows(
    parent_rows: pl.DataFrame,
    *,
    max_drilldowns: int,
) -> pl.DataFrame:
    if parent_rows.is_empty():
        return parent_rows
    return (
        parent_rows.filter(
            (pl.col("row_type") == "member") & (pl.col("total_delta").abs() > TOLERANCE)
        )
        .head(max_drilldowns)
        .select(parent_rows.columns)
    )


def _comparison_payload(recipe: dict[str, Any]) -> dict[str, Any]:
    mappings = recipe.get("mappings") or {}
    options = recipe.get("options") or {}
    return {
        "basis": options.get("comparison_basis"),
        "baseline": mappings.get("baseline_period"),
        "comparison": mappings.get("comparison_period"),
        "period_mode": options.get("period_comparison_mode"),
        "period_window": options.get("period_window") or {},
    }


def _build_artifact_contract() -> dict[str, Any]:
    return {
        "native_payload": "exploded_variance_bridge_spec.json",
        "chart_data": "exploded_variance_bridge_chart_data.json",
        "editable_slide_target": "pptx",
        "can_insert_in_ppt": True,
        "requires_image_interpretation": False,
        "one_page": True,
        "max_drilldowns": DEFAULT_MAX_DRILLDOWNS,
        "ppt_composition": {
            "insert_mode": "single_slide",
            "fallback_render": "exploded_variance_bridge.png",
            "recommended_slide_aspect_ratio": "16:9",
        },
    }


def _quality_check(
    checks: list[dict[str, Any]],
    *,
    name: str,
    passed: bool,
    detail: str,
    severity: str = "fail",
    metrics: dict[str, Any] | None = None,
) -> None:
    checks.append(
        {
            "name": name,
            "status": "pass" if passed else severity,
            "detail": detail,
            "metrics": metrics or {},
        }
    )


def _panel_row_fit(panel: dict[str, int], row_count: int) -> dict[str, Any]:
    available_height = max(0, int(panel["height"]) - 92)
    row_height = available_height // max(1, row_count)
    return {
        "row_count": row_count,
        "available_height": available_height,
        "computed_row_height": row_height,
        "minimum_readable_row_height": MIN_READABLE_ROW_HEIGHT,
        "fits": row_height >= MIN_READABLE_ROW_HEIGHT,
    }


def _panel_bounds_check(panel: dict[str, int]) -> bool:
    x = int(panel["x"])
    y = int(panel["y"])
    width = int(panel["width"])
    height = int(panel["height"])
    return x >= 0 and y >= 0 and x + width <= CHART_WIDTH and y + height <= CHART_HEIGHT


def _image_quality_metrics(image_path: Path) -> dict[str, Any]:
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        pixels = list(rgb.getdata())
    total_pixels = max(1, width * height)

    def is_ink(pixel: tuple[int, int, int]) -> bool:
        return any(channel < 245 for channel in pixel)

    non_white_pixels = sum(1 for pixel in pixels if is_ink(pixel))
    edge_width = 8
    edge_pixels = []
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        for y in range(height):
            for x in range(width):
                if (
                    x < edge_width
                    or x >= width - edge_width
                    or y < edge_width
                    or y >= height - edge_width
                ):
                    edge_pixels.append(rgb.getpixel((x, y)))
    edge_count = max(1, len(edge_pixels))
    edge_ink_pixels = sum(1 for pixel in edge_pixels if is_ink(pixel))
    return {
        "width": width,
        "height": height,
        "non_white_ratio": non_white_pixels / total_pixels,
        "crop_risk_ink_ratio": edge_ink_pixels / edge_count,
    }


def validate_exploded_variance_bridge_visual_quality(
    spec: dict[str, Any],
    *,
    image_path: Path | None = None,
) -> dict[str, Any]:
    """Return deterministic readability checks for the one-page exploded bridge."""

    checks: list[dict[str, Any]] = []
    layout = spec.get("layout") or {}
    children = spec.get("children") or []
    parent = spec.get("parent") or {}
    child_panels = layout.get("child_panels") or []

    _quality_check(
        checks,
        name="one_page_contract",
        passed=bool(layout.get("one_page")) is True,
        detail="Visual must fit on one page for PPT insertion.",
    )
    _quality_check(
        checks,
        name="max_two_drilldowns",
        passed=len(children) <= DEFAULT_MAX_DRILLDOWNS,
        detail="At most two parent rows may be expanded on the same slide.",
        metrics={"selected_drilldown_count": len(children)},
    )
    _quality_check(
        checks,
        name="child_panel_count_matches_drilldowns",
        passed=len(child_panels) == len(children),
        detail="Every expanded parent row needs exactly one visible child panel.",
        metrics={
            "child_panel_count": len(child_panels),
            "drilldown_count": len(children),
        },
    )
    _quality_check(
        checks,
        name="connector_count_matches_drilldowns",
        passed=int(layout.get("connector_count") or 0) == len(children),
        detail="Every child panel needs one connector from the parent bridge.",
        metrics={"connector_count": int(layout.get("connector_count") or 0)},
    )
    panels = [layout.get("parent_panel") or {}, *child_panels]
    _quality_check(
        checks,
        name="panels_within_page_bounds",
        passed=all(_panel_bounds_check(panel) for panel in panels if panel),
        detail="Panels must stay inside the 16:9 slide canvas.",
    )
    _quality_check(
        checks,
        name="single_visible_font_size",
        passed=VISIBLE_FONT_SIZE == 18,
        detail="The visual uses one visible font size and bold weight for emphasis.",
        metrics={"visible_font_size": VISIBLE_FONT_SIZE},
    )

    parent_rows = parent.get("rows") or []
    parent_fit = _panel_row_fit(layout["parent_panel"], len(parent_rows) + 2)
    _quality_check(
        checks,
        name="parent_rows_readable",
        passed=bool(parent_fit["fits"]),
        detail="Parent bridge rows must have enough vertical space to read labels.",
        metrics=parent_fit,
    )
    for child, panel in zip(children, child_panels, strict=False):
        child_fit = _panel_row_fit(panel, len(child.get("rows") or []) + 2)
        _quality_check(
            checks,
            name=f"child_rows_readable_{child.get('drilldown_id')}",
            passed=bool(child_fit["fits"]),
            detail="Child bridge rows must have enough vertical space to read labels.",
            metrics=child_fit,
        )

    if image_path is None:
        _quality_check(
            checks,
            name="rendered_png_quality",
            passed=True,
            detail="PNG pixel checks skipped in data-only mode.",
            severity="warn",
        )
    else:
        image_metrics = _image_quality_metrics(image_path)
        _quality_check(
            checks,
            name="rendered_png_size",
            passed=(
                image_metrics["width"] == CHART_WIDTH
                and image_metrics["height"] == CHART_HEIGHT
            ),
            detail="Rendered PNG must match the native slide canvas.",
            metrics=image_metrics,
        )
        _quality_check(
            checks,
            name="rendered_png_not_blank",
            passed=image_metrics["non_white_ratio"] >= MIN_NON_WHITE_RATIO,
            detail="Rendered PNG must contain enough ink to rule out blank output.",
            metrics={
                **image_metrics,
                "minimum_non_white_ratio": MIN_NON_WHITE_RATIO,
            },
        )
        _quality_check(
            checks,
            name="rendered_png_not_cropped",
            passed=image_metrics["crop_risk_ink_ratio"] <= MAX_CROP_RISK_INK_RATIO,
            detail="Ink near image edges should stay low to avoid crop-risk.",
            metrics={
                **image_metrics,
                "maximum_crop_risk_ink_ratio": MAX_CROP_RISK_INK_RATIO,
            },
        )

    failing = [check for check in checks if check["status"] == "fail"]
    warnings = [check for check in checks if check["status"] == "warn"]
    score = max(0, 100 - len(failing) * 25 - len(warnings) * 5)
    return {
        "status": "pass" if not failing else "fail",
        "score": score,
        "flags": [check["name"] for check in failing],
        "warnings": [check["name"] for check in warnings],
        "checks": checks,
    }


def build_exploded_variance_bridge_spec(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    parent_dimension: str,
    child_dimension: str | None = None,
    parent_top_n: int = DEFAULT_PARENT_TOP_N,
    child_top_n: int = DEFAULT_CHILD_TOP_N,
    max_drilldowns: int = DEFAULT_MAX_DRILLDOWNS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the native parent/child exploded bridge spec."""

    if result.is_empty():
        raise ValueError("Cannot build exploded variance bridge from empty results.")
    if parent_dimension not in result.schema:
        raise ValueError(
            f"Parent dimension '{parent_dimension}' is not present in the result frame."
        )
    selected_child_dimension = child_dimension or _select_child_dimension(
        result,
        recipe,
        parent_dimension=parent_dimension,
    )
    if not selected_child_dimension:
        raise ValueError("Exploded variance bridge requires a child dimension.")
    if selected_child_dimension not in result.schema:
        raise ValueError(
            f"Child dimension '{selected_child_dimension}' is not present in the result frame."
        )
    if selected_child_dimension == parent_dimension:
        raise ValueError(
            "Exploded variance bridge parent and child dimensions must differ."
        )

    parent_limit = _bounded_positive_int(
        parent_top_n, DEFAULT_PARENT_TOP_N, maximum=MAX_PARENT_TOP_N
    )
    child_limit = _bounded_positive_int(
        child_top_n, DEFAULT_CHILD_TOP_N, maximum=MAX_CHILD_TOP_N
    )
    drilldown_limit = _bounded_positive_int(
        max_drilldowns, DEFAULT_MAX_DRILLDOWNS, maximum=DEFAULT_MAX_DRILLDOWNS
    )
    parent_rows, parent_audit = build_total_by_dimension_bridge_rows(
        result,
        recipe,
        dimension=parent_dimension,
        top_n=parent_limit,
    )
    selected_parent_rows = _select_drilldown_parent_rows(
        parent_rows,
        max_drilldowns=drilldown_limit,
    )
    children: list[dict[str, Any]] = []
    for index, parent_row in enumerate(selected_parent_rows.to_dicts(), start=1):
        parent_value = str(parent_row.get("dimension_value") or NULL_LABEL)
        if parent_value == OTHER_LABEL:
            continue
        child_source = _filter_parent_member(result, parent_dimension, parent_value)
        if child_source.is_empty():
            continue
        child_rows, child_audit = build_total_by_dimension_bridge_rows(
            child_source,
            recipe,
            dimension=selected_child_dimension,
            top_n=child_limit,
        )
        children.append(
            {
                "drilldown_id": f"drilldown_{index}",
                "panel_index": len(children) + 1,
                "parent_row_number": parent_row.get("row_number"),
                "parent_dimension": parent_dimension,
                "parent_dimension_value": parent_value,
                "parent_total_delta": _safe_float(parent_row.get("total_delta")),
                "child_dimension": selected_child_dimension,
                "rows": _row_dicts(child_rows),
                "selection": child_audit,
                "totals": {
                    "amount_baseline": _sum_column(child_rows, "amount_baseline"),
                    "amount_comparison": _sum_column(child_rows, "amount_comparison"),
                    "total_delta": _sum_column(child_rows, "total_delta"),
                },
            }
        )

    mappings = recipe.get("mappings") or {}
    options = recipe.get("options") or {}
    selected_parent_row_numbers = {
        child["parent_row_number"]
        for child in children
        if child.get("parent_row_number")
    }
    parent_payload_rows = []
    for row in parent_rows.to_dicts():
        row_number = row.get("row_number")
        payload = {
            **row,
            "selected_for_drilldown": row_number in selected_parent_row_numbers,
        }
        for child in children:
            if child.get("parent_row_number") == row_number:
                payload["drilldown_id"] = child["drilldown_id"]
                break
        parent_payload_rows.append(payload)

    spec = {
        "schema_version": "1.0",
        "analysis_type": "exploded_variance_bridge",
        "status": "written",
        "language": str(recipe.get("language") or "en"),
        "capability_id": "variance.exploded_variance_bridge",
        "chart_family": "variance_analysis",
        "chart_type": "exploded_variance_bridge",
        "chart_artifact": "exploded_variance_bridge.png",
        "spec_json": "exploded_variance_bridge_spec.json",
        "chart_data_json": "exploded_variance_bridge_chart_data.json",
        "context_json": "exploded_variance_bridge_context.json",
        "metric": mappings.get("amount_column"),
        "unit": options.get("currency") or "EUR",
        "comparison": _comparison_payload(recipe),
        "parent": {
            "dimension": parent_dimension,
            "top_n": parent_limit,
            "rows": parent_payload_rows,
            "selection": parent_audit,
        },
        "children": children,
        "layout": {
            "page_size": {"width": CHART_WIDTH, "height": CHART_HEIGHT, "unit": "px"},
            "one_page": True,
            "max_drilldowns": DEFAULT_MAX_DRILLDOWNS,
            "parent_panel": {"x": 48, "y": 122, "width": 660, "height": 712},
            "child_panels": [
                (
                    {"x": 886, "y": 122, "width": 666, "height": 326}
                    if len(children) > 1
                    else {"x": 886, "y": 214, "width": 666, "height": 438}
                ),
                {"x": 886, "y": 508, "width": 666, "height": 326},
            ][: len(children)],
            "connector_count": len(children),
        },
        "artifact_contract": _build_artifact_contract(),
        "codex_interpretation_contract": {
            "must_review_when_written": True,
            "must_use_native_payload_before_pixels": True,
            "purpose": (
                "Show one parent total-variance bridge and up to two child drilldowns "
                "for the largest parent rows by absolute total delta."
            ),
            "required_points": [
                "State the parent dimension and the child drilldown dimension.",
                "Mention that only the selected parent rows are expanded.",
                "Use the child rows to explain the selected parent row, not the full total.",
                "Call out Other rows when they are present.",
                "Do not infer unshown drilldowns for non-expanded parent rows.",
            ],
        },
        "selection": {
            "strategy": (
                "parent rows ranked by absolute total delta; child rows ranked by "
                "absolute total delta within each selected parent member"
            ),
            "parent_dimension": parent_dimension,
            "child_dimension": selected_child_dimension,
            "max_drilldowns": DEFAULT_MAX_DRILLDOWNS,
            "selected_drilldown_count": len(children),
            "one_page": True,
        },
        "totals": {
            "amount_baseline": _sum_column(parent_rows, "amount_baseline"),
            "amount_comparison": _sum_column(parent_rows, "amount_comparison"),
            "total_delta": _sum_column(parent_rows, "total_delta"),
        },
    }
    spec["visual_quality"] = validate_exploded_variance_bridge_visual_quality(spec)
    audit = {
        "enabled": True,
        "status": "data_written",
        "parent_dimension": parent_dimension,
        "child_dimension": selected_child_dimension,
        "requested_parent_top_n": parent_top_n,
        "requested_child_top_n": child_top_n,
        "parent_top_n": parent_limit,
        "child_top_n": child_limit,
        "max_drilldowns": DEFAULT_MAX_DRILLDOWNS,
        "selected_drilldown_count": len(children),
        "parent_displayed_row_count": parent_rows.height,
        "visual_quality_status": spec["visual_quality"]["status"],
        "visual_quality_flags": spec["visual_quality"]["flags"],
        "one_page": True,
        "selection_strategy": spec["selection"]["strategy"],
        "source_functions": [
            (
                "plugins.variance-analysis.scripts.total_by_dimension_bridge_chart."
                "build_total_by_dimension_bridge_rows"
            ),
            (
                "plugins.variance-analysis.scripts.exploded_variance_bridge_chart."
                "build_exploded_variance_bridge_spec"
            ),
        ],
    }
    return spec, audit


def _draw_title(
    draw: ImageDraw.ImageDraw,
    recipe: dict[str, Any],
    *,
    parent_dimension: str,
    child_dimension: str,
) -> None:
    regular_font = _font()
    bold_font = _font(bold=True)
    title = build_ibcs_title(
        recipe,
        chart_kind="total_by_dimension",
        dimension=f"{parent_dimension} > {child_dimension}",
    )
    lines = title.lines()
    if lines:
        draw.text((48, 34), lines[0], fill=COLORS["muted"], font=regular_font)
    if len(lines) > 1:
        _draw_segmented_text(
            draw,
            (48, 58),
            measure_line_segments(lines[1]),
            regular_font=regular_font,
            bold_font=bold_font,
        )
    if len(lines) > 2:
        draw.text((48, 82), lines[2], fill=COLORS["muted"], font=regular_font)


def _scale_bounds(rows: list[dict[str, Any]]) -> tuple[float, float]:
    candidates = [0.0]
    for row in rows:
        candidates.extend(
            [
                _safe_float(row.get("amount_baseline")),
                _safe_float(row.get("amount_comparison")),
                _safe_float(row.get("total_delta")),
                _safe_float(row.get("amount")),
            ]
        )
    low = min(candidates)
    high = max(candidates)
    padding = max((high - low) * 0.08, 1.0)
    return low - padding, high + padding


def _draw_bridge_panel(
    draw: ImageDraw.ImageDraw,
    *,
    box: dict[str, int],
    title: str,
    dimension: str,
    rows: list[dict[str, Any]],
    baseline_label: str,
    comparison_label: str,
    selected_parent_row_numbers: set[int] | None = None,
) -> dict[int, tuple[int, int]]:
    font = _font()
    bold_font = _font(bold=True)
    x = int(box["x"])
    y = int(box["y"])
    width = int(box["width"])
    height = int(box["height"])
    draw.rectangle((x, y, x + width, y + height), outline=COLORS["grid"], width=1)
    draw.text((x + 16, y + 14), title, fill=COLORS["text"], font=bold_font)
    draw.text((x + 16, y + 38), dimension, fill=COLORS["muted"], font=font)

    header_y = y + 72
    label_x = x + 16
    value_left = x + int(width * 0.39)
    value_width = int(width * 0.25)
    delta_left = value_left + value_width + 34
    delta_width = max(80, x + width - delta_left - 24)
    draw.text((value_left, header_y - 28), "Value", fill=COLORS["muted"], font=font)
    draw.text((delta_left, header_y - 28), "Delta", fill=COLORS["muted"], font=font)

    baseline_total = sum(_safe_float(row.get("amount_baseline")) for row in rows)
    comparison_total = sum(_safe_float(row.get("amount_comparison")) for row in rows)
    all_rows = [
        {
            "row_type": "baseline_total",
            "dimension_value": baseline_label,
            "amount": baseline_total,
        },
        *rows,
        {
            "row_type": "comparison_total",
            "dimension_value": comparison_label,
            "amount": comparison_total,
        },
    ]
    low, high = _scale_bounds(all_rows)
    value_zero_x = _x_position(0.0, low, high, value_left, value_width)
    delta_zero_x = _x_position(0.0, low, high, delta_left, delta_width)
    draw.line(
        (value_zero_x, header_y, value_zero_x, y + height - 16), fill=COLORS["grid"]
    )
    draw.line(
        (delta_zero_x, header_y, delta_zero_x, y + height - 16), fill=COLORS["grid"]
    )

    available_height = max(1, y + height - 20 - header_y)
    row_height = max(30, min(54, available_height // max(1, len(all_rows))))
    bar_height = 10
    anchors: dict[int, tuple[int, int]] = {}
    selected_parent_row_numbers = selected_parent_row_numbers or set()

    for index, row in enumerate(all_rows):
        row_y = header_y + index * row_height
        center_y = row_y + row_height // 2
        row_type = str(row.get("row_type") or "")
        label = _fit_text(
            draw,
            str(row.get("dimension_value") or ""),
            font,
            max(40, value_left - label_x - 18),
        )
        row_number = row.get("row_number")
        is_selected = (
            isinstance(row_number, int) and row_number in selected_parent_row_numbers
        )
        if is_selected:
            draw.rectangle(
                (
                    x + 6,
                    row_y + 4,
                    x + 10,
                    min(row_y + row_height - 4, y + height - 10),
                ),
                fill=COLORS["connector"],
            )
        draw.text((label_x, row_y + 8), label, fill=COLORS["text"], font=font)

        if row_type in {"baseline_total", "comparison_total"}:
            value = _safe_float(row.get("amount"))
            value_x = _x_position(value, low, high, value_left, value_width)
            fill = (
                COLORS["baseline_period"]
                if row_type == "baseline_total"
                else COLORS["actual"]
            )
            _draw_bar(
                draw,
                _bar_box_from_zero(value_zero_x, value_x, center_y - 5, center_y + 5),
                fill=fill,
            )
            draw.text(
                (min(value_x + 8, value_left + value_width + 4), center_y - 12),
                _format_number(value, signed=False),
                fill=COLORS["text"],
                font=bold_font,
            )
            continue

        baseline_value = _safe_float(row.get("amount_baseline"))
        comparison_value = _safe_float(row.get("amount_comparison"))
        baseline_x = _x_position(baseline_value, low, high, value_left, value_width)
        comparison_x = _x_position(comparison_value, low, high, value_left, value_width)
        _draw_bar(
            draw,
            _bar_box_from_zero(
                value_zero_x, baseline_x, center_y - bar_height, center_y
            ),
            fill=COLORS["baseline_period"],
        )
        _draw_bar(
            draw,
            _bar_box_from_zero(
                value_zero_x, comparison_x, center_y, center_y + bar_height
            ),
            fill=COLORS["actual"],
        )
        delta_value = _safe_float(row.get("total_delta"))
        delta_x = _x_position(delta_value, low, high, delta_left, delta_width)
        delta_color = COLORS["positive"] if delta_value >= 0 else COLORS["negative"]
        _draw_bar(
            draw,
            _bar_box_from_zero(delta_zero_x, delta_x, center_y - 5, center_y + 5),
            fill=delta_color,
        )
        delta_label = _format_number(delta_value)
        label_width = draw.textbbox((0, 0), delta_label, font=bold_font)[2]
        if delta_value >= 0:
            label_x_pos = min(delta_x + 8, x + width - label_width - 8)
        else:
            label_x_pos = delta_x - label_width - 8
        draw.text(
            (label_x_pos, center_y - 12), delta_label, fill=delta_color, font=bold_font
        )
        percent_label = str(row.get("percent_label") or "")
        if percent_label:
            draw.text(
                (x + width - 72, center_y - 12),
                f"{percent_label}%",
                fill=COLORS["muted"],
                font=font,
            )
        if isinstance(row_number, int):
            anchors[row_number] = (x + width, center_y)
    return anchors


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
) -> None:
    sx, sy = start
    ex, ey = end
    mid_x = sx + max(70, (ex - sx) // 2)
    draw.line((sx, sy, mid_x, sy, mid_x, ey, ex, ey), fill=COLORS["connector"], width=2)
    draw.polygon(
        [(ex, ey), (ex - 10, ey - 6), (ex - 10, ey + 6)],
        fill=COLORS["connector"],
    )


def _write_png(
    spec: dict[str, Any], recipe: dict[str, Any], output_path: Path
) -> dict[str, Any]:
    image = Image.new("RGB", (CHART_WIDTH, CHART_HEIGHT), COLORS["white"])
    draw = ImageDraw.Draw(image)
    parent = spec["parent"]
    children = spec["children"]
    parent_dimension = str(parent["dimension"])
    child_dimension = str(spec["selection"]["child_dimension"])
    baseline_label, comparison_label = _period_labels(recipe)
    _draw_title(
        draw,
        recipe,
        parent_dimension=parent_dimension,
        child_dimension=child_dimension,
    )
    font = _font()
    draw.rectangle((48, 850, 62, 862), fill=COLORS["baseline_period"])
    draw.text((70, 844), baseline_label, fill=COLORS["muted"], font=font)
    draw.rectangle((210, 850, 224, 862), fill=COLORS["actual"])
    draw.text((232, 844), comparison_label, fill=COLORS["muted"], font=font)
    draw.rectangle((412, 850, 426, 862), fill=COLORS["positive"])
    draw.text((434, 844), "Positive delta", fill=COLORS["muted"], font=font)
    draw.rectangle((604, 850, 618, 862), fill=COLORS["negative"])
    draw.text((626, 844), "Negative delta", fill=COLORS["muted"], font=font)

    selected_parent_rows = {
        int(child["parent_row_number"])
        for child in children
        if child.get("parent_row_number") is not None
    }
    layout = spec["layout"]
    parent_anchors = _draw_bridge_panel(
        draw,
        box=layout["parent_panel"],
        title="Parent bridge",
        dimension=parent_dimension,
        rows=parent["rows"],
        baseline_label=baseline_label,
        comparison_label=comparison_label,
        selected_parent_row_numbers=selected_parent_rows,
    )
    connector_specs: list[dict[str, Any]] = []
    for child, child_box in zip(children, layout["child_panels"], strict=False):
        parent_value = str(child.get("parent_dimension_value") or "")
        child_title = f"{child['panel_index']}. {parent_value}"
        _draw_bridge_panel(
            draw,
            box=child_box,
            title=child_title,
            dimension=child_dimension,
            rows=child["rows"],
            baseline_label=baseline_label,
            comparison_label=comparison_label,
        )
        parent_row_number = int(child["parent_row_number"])
        start = parent_anchors.get(parent_row_number)
        if start:
            end = (int(child_box["x"]), int(child_box["y"] + child_box["height"] / 2))
            _draw_arrow(draw, start, end)
            connector_specs.append(
                {
                    "drilldown_id": child["drilldown_id"],
                    "parent_row_number": parent_row_number,
                    "from_anchor": {"x": start[0], "y": start[1]},
                    "to_anchor": {"x": end[0], "y": end[1]},
                }
            )

    spec["layout"]["connectors"] = connector_specs
    image.save(output_path)
    spec["visual_quality"] = validate_exploded_variance_bridge_visual_quality(
        spec,
        image_path=output_path,
    )
    return {
        "status": "written",
        "artifact": output_path.name,
        "path": str(output_path),
        "bytes": output_path.stat().st_size,
        "format": "png",
        "renderer": "pillow_exploded_variance_bridge",
        "pillow_renderer_version": "exploded_parent_child_bridge_v1",
        "row_number_markers": True,
        "one_page": True,
        "max_drilldowns": DEFAULT_MAX_DRILLDOWNS,
        "connector_count": len(connector_specs),
        "visible_font_size": VISIBLE_FONT_SIZE,
        "visual_quality_status": spec["visual_quality"]["status"],
        "visual_quality_score": spec["visual_quality"]["score"],
        "visual_quality_flags": spec["visual_quality"]["flags"],
        "source_functions": [
            (
                "plugins.variance-analysis.scripts.exploded_variance_bridge_chart."
                "build_exploded_variance_bridge_spec"
            ),
            (
                "plugins.variance-analysis.scripts.exploded_variance_bridge_chart."
                "_write_png"
            ),
        ],
    }


def _context_payload(
    spec: dict[str, Any],
    *,
    chart_path: Path,
    spec_path: Path,
    chart_data_path: Path,
    context_path: Path,
    chart_audit: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "analysis_type": "exploded_variance_bridge",
        "status": "written",
        "language": spec.get("language") or "en",
        "capability_id": "variance.exploded_variance_bridge",
        "chart_family": "variance_analysis",
        "chart_type": "exploded_variance_bridge",
        "chart_artifact": chart_path.name,
        "spec_json": spec_path.name,
        "chart_data_json": chart_data_path.name,
        "context_json": context_path.name,
        "parent_dimension": spec["selection"]["parent_dimension"],
        "child_dimension": spec["selection"]["child_dimension"],
        "max_drilldowns": DEFAULT_MAX_DRILLDOWNS,
        "selected_drilldown_count": spec["selection"]["selected_drilldown_count"],
        "one_page": True,
        "metric": spec.get("metric"),
        "unit": spec.get("unit"),
        "comparison": spec.get("comparison") or {},
        "totals": spec.get("totals") or {},
        "parent_rows": spec["parent"]["rows"],
        "drilldowns": spec["children"],
        "selection": spec["selection"],
        "layout": spec["layout"],
        "visual_quality": spec["visual_quality"],
        "artifact_contract": spec["artifact_contract"],
        "codex_interpretation_contract": spec["codex_interpretation_contract"],
        "chart_audit": chart_audit,
    }


def _chart_data_payload(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "chart_type": "exploded_variance_bridge",
        "capability_id": "variance.exploded_variance_bridge",
        "parent": spec["parent"],
        "children": spec["children"],
        "layout": spec["layout"],
        "visual_quality": spec["visual_quality"],
        "selection": spec["selection"],
        "totals": spec["totals"],
        "artifact_contract": spec["artifact_contract"],
    }


def _summary_markdown(context: dict[str, Any]) -> str:
    children = context.get("drilldowns") or []
    expanded = ", ".join(str(child.get("parent_dimension_value")) for child in children)
    language = str(context.get("language") or "en").lower().replace("_", "-")
    spanish = language.split("-", 1)[0] == "es"
    expanded_text = expanded if expanded else ("ninguna" if spanish else "none")
    return (
        (
            "\n\n## Puente ampliado de variaciones\n\n"
            if spanish
            else "\n\n## Exploded Variance Bridge\n\n"
        )
        + ("- Archivos fuente: " if spanish else "- Source files: ")
        + "`exploded_variance_bridge.png`, "
        "`exploded_variance_bridge_spec.json`, "
        "`exploded_variance_bridge_chart_data.json`, "
        "`exploded_variance_bridge_context.json`\n"
        + f"- {'Dimensión principal' if spanish else 'Parent dimension'}: `{context.get('parent_dimension')}`\n"
        + f"- {'Dimensión secundaria' if spanish else 'Child dimension'}: `{context.get('child_dimension')}`\n"
        + f"- {'Filas principales ampliadas' if spanish else 'Expanded parent rows'}: {expanded_text}\n"
    )


def write_exploded_variance_bridge_artifacts(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    parent_dimension: str,
    child_dimension: str | None = None,
    parent_top_n: int = DEFAULT_PARENT_TOP_N,
    child_top_n: int = DEFAULT_CHILD_TOP_N,
    max_drilldowns: int = DEFAULT_MAX_DRILLDOWNS,
    render: bool = True,
) -> ExplodedVarianceBridgeExport:
    """Write native spec/context data and optionally render the exploded bridge PNG."""

    spec, spec_audit = build_exploded_variance_bridge_spec(
        result,
        recipe,
        parent_dimension=parent_dimension,
        child_dimension=child_dimension,
        parent_top_n=parent_top_n,
        child_top_n=child_top_n,
        max_drilldowns=max_drilldowns,
    )
    chart_path = output_dir / "exploded_variance_bridge.png"
    spec_path = output_dir / "exploded_variance_bridge_spec.json"
    chart_data_path = output_dir / "exploded_variance_bridge_chart_data.json"
    context_path = output_dir / "exploded_variance_bridge_context.json"
    if render:
        chart_audit = _write_png(spec, recipe, chart_path)
    else:
        chart_audit = {
            "status": "data_written",
            "artifact": chart_path.name,
            "path": str(chart_path),
            "rendered": False,
            "one_page": True,
            "max_drilldowns": DEFAULT_MAX_DRILLDOWNS,
            "visual_quality_status": spec["visual_quality"]["status"],
            "visual_quality_score": spec["visual_quality"]["score"],
            "visual_quality_flags": spec["visual_quality"]["flags"],
            "source_functions": spec_audit["source_functions"],
        }
    _write_json(spec_path, spec)
    _write_json(chart_data_path, _chart_data_payload(spec))
    context = _context_payload(
        spec,
        chart_path=chart_path,
        spec_path=spec_path,
        chart_data_path=chart_data_path,
        context_path=context_path,
        chart_audit=chart_audit,
    )
    _write_json(context_path, context)
    audit = {
        **spec_audit,
        **chart_audit,
        "spec_json": spec_path.name,
        "chart_data_json": chart_data_path.name,
        "context_json": context_path.name,
    }
    paths = [str(spec_path), str(chart_data_path), str(context_path)]
    if render:
        paths.insert(0, str(chart_path))
    return ExplodedVarianceBridgeExport(
        paths=paths,
        audit=audit,
        summary_markdown=_summary_markdown(context),
    )
