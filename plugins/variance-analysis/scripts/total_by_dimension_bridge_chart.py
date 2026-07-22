"""Single-dimension total variance bridge rendering."""

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

__all__ = [
    "TotalByDimensionBridgeExport",
    "build_total_by_dimension_bridge_rows",
    "write_total_by_dimension_bridge_artifacts",
]

TOLERANCE = 0.000001
DEFAULT_TOP_N = 8
NULL_LABEL = "N/A"
OTHER_LABEL = "Other"
DIMENSION_VALUE_COLUMN = "__total_bridge_dimension_value"
COLORS = {
    "actual": "#1F1F1F",
    "baseline_period": "#A6A6A6",
    "grid": "#EDEDED",
    "negative": "#FF2F2F",
    "positive": "#67C40F",
    "text": "#1F2328",
    "muted": "#666666",
    "white": "#FFFFFF",
}


@dataclass(frozen=True)
class TotalByDimensionBridgeExport:
    """Exported total-by-dimension artifacts and audit metadata."""

    paths: list[str]
    audit: dict[str, Any]
    summary_markdown: str


def _sum_column(df: pl.DataFrame, column: str) -> float:
    """Return the numeric sum for ``column`` or zero when missing."""

    if column not in df.schema or df.is_empty():
        return 0.0
    value = df.select(pl.col(column).sum()).item()
    return float(value or 0.0)


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Return a finite float for chart calculations."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _format_number(value: float, *, signed: bool = True) -> str:
    """Return compact chart text with K/M/B suffixes."""

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


def _format_percent_marker(value: float | None) -> str:
    """Return compact percent text for the delta-percent side panel."""

    if value is None or not math.isfinite(value):
        return ""
    abs_value = abs(value)
    body = f"{abs_value:.0f}" if abs_value >= 10 else f"{abs_value:.1f}"
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{body}"


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    """Return a readable font while staying robust in headless runs."""

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
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_segmented_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    segments: tuple[tuple[str, bool], ...],
    *,
    fill: str,
    regular_font: ImageFont.ImageFont,
    bold_font: ImageFont.ImageFont,
) -> None:
    """Draw one title line with per-segment emphasis."""

    x, y = xy
    for text, emphasized in segments:
        if not text:
            continue
        font = bold_font if emphasized else regular_font
        draw.text((x, y), text, fill=fill, font=font)
        bbox = draw.textbbox((x, y), text, font=font)
        x += bbox[2] - bbox[0]


def _draw_ibcs_title(
    draw: ImageDraw.ImageDraw,
    recipe: dict[str, Any],
    *,
    dimension: str,
) -> list[str]:
    """Draw the standard three-row IBCS title and return its lines."""

    title = build_ibcs_title(
        recipe,
        chart_kind="total_by_dimension",
        dimension=dimension,
    )
    lines = title.lines()
    who_font = _font(18)
    title_font = _font(18)
    title_subject_font = _font(18, bold=True)
    subtitle_font = _font(17)
    if lines:
        draw.text((54, 26), lines[0], fill=COLORS["muted"], font=who_font)
    if len(lines) > 1:
        _draw_segmented_text(
            draw,
            (54, 51),
            measure_line_segments(lines[1]),
            fill=COLORS["text"],
            regular_font=title_font,
            bold_font=title_subject_font,
        )
    if len(lines) > 2:
        draw.text((54, 77), lines[2], fill=COLORS["muted"], font=subtitle_font)
    return lines


def _x_position(value: float, low: float, high: float, left: int, width: int) -> int:
    """Map a value to a horizontal pixel position."""

    if abs(high - low) < TOLERANCE:
        high = low + 1.0
    return int(left + ((value - low) / (high - low)) * width)


def _draw_bar(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str | None = None,
    width: int = 1,
) -> None:
    """Draw a rounded horizontal bar."""

    x0, y0, x1, y1 = box
    draw.rounded_rectangle(
        (min(x0, x1), y0, max(x0, x1, min(x0, x1) + 3), y1),
        radius=4,
        fill=fill,
        outline=outline,
        width=width,
    )


def _bar_box_from_zero(
    zero_x: int,
    value_x: int,
    y0: int,
    y1: int,
) -> tuple[int, int, int, int]:
    """Return a valid horizontal bar box from a zero axis."""

    x0 = min(zero_x, value_x)
    x1 = max(zero_x, value_x)
    return (x0, y0, max(x1, x0 + 3), y1)


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    """Return text truncated to fit a fixed pixel width."""

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


def _periods(recipe: dict[str, Any]) -> tuple[str, str]:
    """Return baseline and comparison labels from the recipe."""

    mappings = recipe["mappings"]
    return str(mappings["baseline_period"]), str(mappings["comparison_period"])


def _is_plan_label(label: str) -> bool:
    """Return whether ``label`` represents a plan-like scenario."""

    normalized = label.strip().upper()
    return normalized in {"PL", "PLAN", "BUDGET", "BDG", "FORECAST", "FC"}


def _is_period_comparison(recipe: dict[str, Any]) -> bool:
    """Return whether the recipe compares periods rather than scenarios."""

    return (recipe.get("options") or {}).get("comparison_basis") == "period"


def _json_safe(value: Any) -> Any:
    """Return a JSON-serializable value."""

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON with deterministic formatting."""

    path.write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _summary_markdown(context: dict[str, Any]) -> str:
    """Return a markdown source-data block for the run summary."""

    if context.get("status") != "written":
        return ""
    language = str(context.get("language") or "en").lower().replace("_", "-")
    spanish = language.split("-", 1)[0] == "es"
    lines = [
        "",
        (
            "## Variación total por dimensión"
            if spanish
            else "## Total Variance By Dimension"
        ),
        "",
        f"- {'Dimensión' if spanish else 'Dimension'}: `{context.get('dimension')}`",
        f"- {'Filas mostradas' if spanish else 'Displayed rows'}: `{context.get('displayed_row_count')}`",
        f"- {'Archivos fuente' if spanish else 'Source files'}: `total_by_dimension_bridge.png`, "
        "`total_by_dimension_bridge.csv`, "
        "`total_by_dimension_bridge_context.json`",
        "",
        (
            "Elementos principales por variación total absoluta:"
            if spanish
            else "Largest members by absolute total variance:"
        ),
    ]
    for row in context.get("rows", [])[:6]:
        lines.append(
            "- "
            f"{row.get('dimension_value')}: delta="
            f"{float(row.get('total_delta') or 0.0):,.2f}; "
            f"baseline={float(row.get('amount_baseline') or 0.0):,.2f}; "
            f"comparison={float(row.get('amount_comparison') or 0.0):,.2f}"
        )
    lines.extend(
        [
            "",
            (
                "Codex debe tratar estos datos como un desglose fijo de la variación total en una sola dimensión, no como una descomposición de precio/unidades/mix ni como datos de causas con dimensiones variables."
                if spanish
                else "Codex must treat this as a fixed single-dimension total variance split, not as price/units/mix decomposition and not as root-cause variable-dimension source data."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def build_total_by_dimension_bridge_rows(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    dimension: str,
    top_n: int = DEFAULT_TOP_N,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Aggregate standard variance results by one fixed dimension."""

    if result.is_empty():
        raise ValueError("Cannot build total-by-dimension bridge from empty results.")
    if dimension not in result.schema:
        raise ValueError(
            f"Dimension '{dimension}' is not present in the variance result frame."
        )
    required_columns = {"amount_baseline", "amount_comparison", "total_delta"}
    missing = sorted(required_columns - set(result.columns))
    if missing:
        raise ValueError(
            "Variance result frame is missing required columns: " + ", ".join(missing)
        )

    display_limit = max(1, int(top_n or DEFAULT_TOP_N))
    total_abs_delta = _sum_column(
        result.with_columns(pl.col("total_delta").abs().alias("_abs_delta")),
        "_abs_delta",
    )
    total_delta = _sum_column(result, "total_delta")
    grouped = (
        result.with_columns(
            pl.col(dimension)
            .cast(pl.Utf8)
            .fill_null(NULL_LABEL)
            .alias(DIMENSION_VALUE_COLUMN)
        )
        .group_by(DIMENSION_VALUE_COLUMN)
        .agg(
            [
                pl.col("amount_baseline").sum().alias("amount_baseline"),
                pl.col("amount_comparison").sum().alias("amount_comparison"),
                pl.col("total_delta").sum().alias("total_delta"),
                pl.len().alias("source_result_rows"),
            ]
        )
        .with_columns(pl.col("total_delta").abs().alias("_abs_delta"))
        .sort("_abs_delta", descending=True)
    )
    selected = grouped.head(display_limit)
    remaining = grouped.slice(display_limit)
    row_frames = [selected]
    has_other = not remaining.is_empty()
    if has_other:
        other = remaining.select(
            [
                pl.lit(OTHER_LABEL).alias(DIMENSION_VALUE_COLUMN),
                pl.col("amount_baseline").sum().alias("amount_baseline"),
                pl.col("amount_comparison").sum().alias("amount_comparison"),
                pl.col("total_delta").sum().alias("total_delta"),
                pl.col("source_result_rows").sum().alias("source_result_rows"),
                pl.col("_abs_delta").sum().alias("_abs_delta"),
            ]
        )
        row_frames.append(other)
    rows = pl.concat(row_frames, how="vertical").with_columns(
        [
            pl.when(pl.col("amount_baseline").abs() > TOLERANCE)
            .then((pl.col("total_delta") / pl.col("amount_baseline")) * 100.0)
            .otherwise(None)
            .alias("percent_delta"),
            pl.when(pl.col(DIMENSION_VALUE_COLUMN) == OTHER_LABEL)
            .then(pl.lit("other_members"))
            .otherwise(pl.lit("member"))
            .alias("row_type"),
            (
                pl.col("_abs_delta") / total_abs_delta
                if total_abs_delta > TOLERANCE
                else pl.lit(0.0)
            ).alias("share_of_total_abs_delta"),
            (
                pl.col("total_delta") / total_delta
                if abs(total_delta) > TOLERANCE
                else pl.lit(0.0)
            ).alias("share_of_total_delta"),
        ]
    )
    rows = rows.with_row_index("row_number", offset=1).with_columns(
        pl.col("row_number").cast(pl.Int64)
    )
    row_dicts = rows.to_dicts()
    percent_labels = [
        _format_percent_marker(
            _safe_float(row.get("percent_delta"))
            if row.get("percent_delta") is not None
            else None
        )
        for row in row_dicts
    ]
    rows = rows.with_columns(pl.Series("percent_label", percent_labels)).select(
        [
            "row_number",
            pl.lit(dimension).alias("dimension"),
            pl.col(DIMENSION_VALUE_COLUMN).alias("dimension_value"),
            "row_type",
            "amount_baseline",
            "amount_comparison",
            "total_delta",
            "percent_delta",
            "percent_label",
            "share_of_total_delta",
            "share_of_total_abs_delta",
            "source_result_rows",
        ]
    )
    audit = {
        "dimension": dimension,
        "source_result_rows": result.height,
        "candidate_member_count": grouped.height,
        "displayed_member_count": selected.height,
        "displayed_row_count": rows.height,
        "top_n": display_limit,
        "other_included": has_other,
        "total_delta": total_delta,
        "displayed_delta_sum": _sum_column(rows, "total_delta"),
        "chart_reconciliation_delta": _sum_column(rows, "total_delta") - total_delta,
        "selection_strategy": "single_fixed_dimension_ranked_by_abs_total_delta",
    }
    return rows, audit


def _draw_percent_pin(
    draw: ImageDraw.ImageDraw,
    *,
    row: dict[str, Any],
    center_y: int,
    pct_low: float,
    pct_high: float,
    pct_zero_x: int,
    pct_left: int,
    pct_width: int,
    value_font: ImageFont.ImageFont,
) -> None:
    """Draw one percent-change pin."""

    percent_label = str(row.get("percent_label") or "")
    percent_delta = row.get("percent_delta")
    if (
        not percent_label
        or percent_delta is None
        or not math.isfinite(float(percent_delta))
    ):
        return
    pct_x = _x_position(float(percent_delta), pct_low, pct_high, pct_left, pct_width)
    line_color = COLORS["positive"] if float(percent_delta) >= 0 else COLORS["negative"]
    draw.line(
        (min(pct_zero_x, pct_x), center_y, max(pct_zero_x, pct_x), center_y),
        fill=line_color,
        width=2,
    )
    draw.rectangle(
        (pct_x - 4, center_y - 4, pct_x + 4, center_y + 4), fill=COLORS["actual"]
    )
    label_box = draw.textbbox((0, 0), percent_label, font=value_font)
    label_width = label_box[2] - label_box[0]
    label_y = center_y - 11
    if pct_x >= pct_zero_x:
        draw.text(
            (pct_x + 8, label_y), percent_label, fill=COLORS["text"], font=value_font
        )
    else:
        draw.text(
            (pct_x - label_width - 8, label_y),
            percent_label,
            fill=COLORS["text"],
            font=value_font,
        )


def _write_png(
    rows: pl.DataFrame,
    recipe: dict[str, Any],
    output_path: Path,
    *,
    dimension: str,
) -> dict[str, Any]:
    """Render the total-by-dimension bridge PNG."""

    baseline_label, comparison_label = _periods(recipe)
    row_count = rows.height + 2
    width = 1280
    row_height = 70
    top = 142
    bottom = 52
    height = max(560, top + row_height * row_count + bottom)
    label_x = 54
    value_left = 360
    value_width = 310
    delta_left = 730
    delta_width = value_width
    pct_left = 1115
    pct_width = 112
    bar_height = 16
    row_overlay_offset = 8
    label_font = _font(18)
    value_font = _font(16, bold=True)
    small_font = _font(14)
    subtitle_font = _font(17)

    baseline_total = _sum_column(rows, "amount_baseline")
    comparison_total = _sum_column(rows, "amount_comparison")
    value_candidates = [baseline_total, comparison_total, 0.0]
    percent_values: list[float] = []
    for row in rows.to_dicts():
        value_candidates.extend(
            [
                _safe_float(row.get("amount_baseline")),
                _safe_float(row.get("amount_comparison")),
            ]
        )
        value_candidates.append(_safe_float(row.get("total_delta")))
        percent_delta = row.get("percent_delta")
        if percent_delta is not None and math.isfinite(float(percent_delta)):
            percent_values.append(float(percent_delta))

    scale_low = min(value_candidates)
    scale_high = max(value_candidates)
    scale_padding = max((scale_high - scale_low) * 0.04, 1.0)
    scale_low -= scale_padding
    scale_high += scale_padding
    if percent_values:
        pct_low = min(0.0, min(percent_values))
        pct_high = max(0.0, max(percent_values))
        pct_padding = max((pct_high - pct_low) * 0.18, 1.0)
        pct_low -= pct_padding
        pct_high += pct_padding
    else:
        pct_low = -1.0
        pct_high = 1.0

    image = Image.new("RGB", (width, height), COLORS["white"])
    draw = ImageDraw.Draw(image)
    title_lines = _draw_ibcs_title(draw, recipe, dimension=dimension)

    value_zero_x = _x_position(0.0, scale_low, scale_high, value_left, value_width)
    delta_zero_x = _x_position(0.0, scale_low, scale_high, delta_left, delta_width)
    pct_zero_x = _x_position(0.0, pct_low, pct_high, pct_left, pct_width)
    for axis_x, axis_top, axis_bottom in (
        (value_zero_x, top - 18, height - bottom + 12),
        (delta_zero_x, top - 18, height - bottom + 12),
        (pct_zero_x, top - 18, height - bottom + 12),
    ):
        draw.line((axis_x, axis_top, axis_x, axis_bottom), fill=COLORS["grid"], width=1)
    draw.text(
        (value_left, top - 54),
        f"{baseline_label} / {comparison_label}",
        fill=COLORS["muted"],
        font=small_font,
    )
    draw.text((delta_left, top - 54), "\u0394", fill=COLORS["text"], font=subtitle_font)
    draw.text((pct_left, top - 54), "\u0394%", fill=COLORS["text"], font=subtitle_font)

    all_rows = [
        {
            "row_type": "baseline_total",
            "dimension_value": baseline_label,
            "amount": baseline_total,
        },
        *rows.to_dicts(),
        {
            "row_type": "comparison_total",
            "dimension_value": comparison_label,
            "amount": comparison_total,
        },
    ]
    period_mode = _is_period_comparison(recipe)
    for index, row in enumerate(all_rows):
        y = top + index * row_height
        row_type = str(row.get("row_type") or "")
        if row_type in {"baseline_total", "comparison_total"}:
            value = _safe_float(row.get("amount"))
            x1 = _x_position(value, scale_low, scale_high, value_left, value_width)
            label = str(row["dimension_value"])
            draw.text((label_x, y + 9), label, fill=COLORS["text"], font=label_font)
            if row_type == "baseline_total":
                fill = COLORS["white"]
                outline = COLORS["actual"]
                if period_mode and not _is_plan_label(baseline_label):
                    fill = COLORS["baseline_period"]
                    outline = None
                _draw_bar(
                    draw,
                    _bar_box_from_zero(value_zero_x, x1, y + 10, y + 10 + bar_height),
                    fill=fill,
                    outline=outline,
                    width=2 if outline else 1,
                )
            else:
                _draw_bar(
                    draw,
                    _bar_box_from_zero(value_zero_x, x1, y + 10, y + 10 + bar_height),
                    fill=COLORS["actual"],
                )
            draw.text(
                (x1 + 10, y + 8),
                _format_number(value, signed=False),
                fill=COLORS["text"],
                font=value_font,
            )
            continue

        label = _fit_text(
            draw,
            str(row.get("dimension_value") or ""),
            label_font,
            max_width=value_left - label_x - 22,
        )
        draw.text((label_x, y + 11), label, fill=COLORS["text"], font=label_font)

        delta_value = _safe_float(row.get("total_delta"))
        delta_x = _x_position(
            delta_value, scale_low, scale_high, delta_left, delta_width
        )
        delta_color = COLORS["positive"] if delta_value >= 0 else COLORS["negative"]
        _draw_bar(
            draw,
            _bar_box_from_zero(delta_zero_x, delta_x, y + 11, y + 11 + bar_height),
            fill=delta_color,
        )
        delta_label = _format_number(delta_value)
        delta_box = draw.textbbox((0, 0), delta_label, font=value_font)
        if delta_value >= 0:
            draw.text(
                (delta_x + 8, y + 8),
                delta_label,
                fill=delta_color,
                font=value_font,
            )
        else:
            draw.text(
                (delta_x - (delta_box[2] - delta_box[0]) - 8, y + 8),
                delta_label,
                fill=delta_color,
                font=value_font,
            )

        baseline_value = _safe_float(row.get("amount_baseline"))
        comparison_value = _safe_float(row.get("amount_comparison"))
        baseline_x = _x_position(
            baseline_value,
            scale_low,
            scale_high,
            value_left,
            value_width,
        )
        comparison_x = _x_position(
            comparison_value,
            scale_low,
            scale_high,
            value_left,
            value_width,
        )
        baseline_top = y + 8
        comparison_top = baseline_top + row_overlay_offset
        _draw_bar(
            draw,
            _bar_box_from_zero(
                value_zero_x,
                baseline_x,
                baseline_top,
                baseline_top + bar_height,
            ),
            fill=COLORS["baseline_period"],
        )
        _draw_bar(
            draw,
            _bar_box_from_zero(
                value_zero_x,
                comparison_x,
                comparison_top,
                comparison_top + bar_height,
            ),
            fill=COLORS["actual"],
        )
        draw.text(
            (baseline_x + 8, baseline_top - 12),
            _format_number(baseline_value, signed=False),
            fill=COLORS["muted"],
            font=small_font,
        )
        draw.text(
            (comparison_x + 8, comparison_top + bar_height - 2),
            _format_number(comparison_value, signed=False),
            fill=COLORS["text"],
            font=small_font,
        )
        _draw_percent_pin(
            draw,
            row=row,
            center_y=y + 19,
            pct_low=pct_low,
            pct_high=pct_high,
            pct_zero_x=pct_zero_x,
            pct_left=pct_left,
            pct_width=pct_width,
            value_font=value_font,
        )

    image.save(output_path)
    return {
        "enabled": True,
        "status": "written",
        "artifact": output_path.name,
        "path": str(output_path),
        "bytes": output_path.stat().st_size,
        "format": "png",
        "renderer": "pillow_total_by_dimension_bridge",
        "pillow_renderer_version": "total_by_dimension_value_delta_pins_v3",
        "chart_title": " / ".join(title_lines),
        "chart_title_lines": title_lines,
        "dimension": dimension,
        "row_number_markers": False,
        "visual_order": [
            "labels",
            "initial_final_value_bars",
            "absolute_variance_bars",
            "percent_difference_pins",
        ],
        "initial_final_value_bars": True,
        "initial_final_value_bars_position": "after_labels",
        "delta_bar_panel": True,
        "delta_bar_scale": "same_absolute_scale_as_initial_final_value_bars",
        "delta_bar_panel_position": "right_of_initial_final_value_bars",
        "delta_percent_side_panel": True,
        "delta_percent_panel_position": "right_of_absolute_variance_bars",
        "delta_percent_basis": "dimension_member_total_delta_over_member_baseline",
        "legacy_chart_key": "verticalWaterfallChart",
        "legacy_variance_aggregation": "totalVarianceAggregation",
        "legacy_reference_function": (
            "modules.charting.plot_charts.plot_vertical_waterfall_chart"
        ),
        "legacy_reference_function_call_mode": (
            "not_executed_native_renderer_aggregated_standard_result"
        ),
        "source_functions": [
            "plugins.variance-analysis.scripts.variance_core.run_legacy_variance",
            (
                "plugins.variance-analysis.scripts."
                "total_by_dimension_bridge_chart."
                "build_total_by_dimension_bridge_rows"
            ),
            (
                "plugins.variance-analysis.scripts."
                "total_by_dimension_bridge_chart._write_png"
            ),
        ],
    }


def _context_payload(
    rows: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    dimension: str,
    table_path: Path,
    chart_path: Path,
    context_path: Path,
    row_audit: dict[str, Any],
    chart_audit: dict[str, Any],
) -> dict[str, Any]:
    """Return structured model context for the chart."""

    mappings = recipe.get("mappings") or {}
    baseline_period = mappings.get("baseline_period")
    comparison_period = mappings.get("comparison_period")

    return {
        "schema_version": "1.0",
        "analysis_type": "total_by_dimension_bridge",
        "status": "written",
        "language": str(recipe.get("language") or "en"),
        "capability_id": "variance.total_by_dimension_bridge",
        "chart_family": "variance_analysis",
        "chart_type": "total_by_dimension_bridge",
        "chart_artifact": chart_path.name,
        "table_csv": table_path.name,
        "context_json": context_path.name,
        "dimension": dimension,
        "dimensions": [dimension],
        "metric": mappings.get("amount_column"),
        "selected_periods": [
            period
            for period in [baseline_period, comparison_period]
            if period not in (None, "")
        ],
        "unit": (recipe.get("options") or {}).get("currency") or "EUR",
        "comparison": {
            "basis": (recipe.get("options") or {}).get("comparison_basis"),
            "baseline": baseline_period,
            "comparison": comparison_period,
            "period_mode": (recipe.get("options") or {}).get("period_comparison_mode"),
            "period_window": (recipe.get("options") or {}).get("period_window") or {},
        },
        "totals": {
            "amount_baseline": _sum_column(rows, "amount_baseline"),
            "amount_comparison": _sum_column(rows, "amount_comparison"),
            "total_delta": _sum_column(rows, "total_delta"),
        },
        "displayed_row_count": rows.height,
        "rows": rows.to_dicts(),
        "selection": row_audit,
        "chart_audit": chart_audit,
        "resolved_parameters": {
            "metric": mappings.get("amount_column"),
            "comparison_basis": (recipe.get("options") or {}).get("comparison_basis"),
            "baseline_period": baseline_period,
            "comparison_period": comparison_period,
            "period_column": mappings.get("period_column"),
            "date_column": mappings.get("date_column"),
            "dimension": dimension,
            "top_n": row_audit.get("top_n"),
        },
        "codex_interpretation_contract": {
            "must_review_when_written": True,
            "purpose": (
                "Show how the total metric movement is split across one fixed "
                "dimension, one row per dimension member."
            ),
            "required_points": [
                "Use row baseline and comparison values before interpreting the delta.",
                "Use percent pins only as row-level change markers.",
                "Call out the Other row when it is present.",
                "Do not describe this as price/units/mix decomposition.",
                "Do not describe this as variable-dimension root-cause analysis.",
            ],
        },
    }


def write_total_by_dimension_bridge_artifacts(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    dimension: str,
    top_n: int = DEFAULT_TOP_N,
    render: bool = True,
) -> TotalByDimensionBridgeExport:
    """Write CSV/context data and optionally render the PNG bridge."""

    rows, row_audit = build_total_by_dimension_bridge_rows(
        result,
        recipe,
        dimension=dimension,
        top_n=top_n,
    )
    table_path = output_dir / "total_by_dimension_bridge.csv"
    chart_path = output_dir / "total_by_dimension_bridge.png"
    context_path = output_dir / "total_by_dimension_bridge_context.json"
    rows.write_csv(table_path)
    if render:
        chart_audit = _write_png(rows, recipe, chart_path, dimension=dimension)
    else:
        chart_audit = {
            "status": "data_written",
            "artifact": chart_path.name,
            "path": str(chart_path),
            "rendered": False,
            "source_functions": [
                "total_by_dimension_bridge_chart.build_total_by_dimension_bridge_rows"
            ],
        }
    audit = {
        **row_audit,
        **chart_audit,
        "table_csv": table_path.name,
        "context_json": context_path.name,
    }
    context = _context_payload(
        rows,
        recipe,
        dimension=dimension,
        table_path=table_path,
        chart_path=chart_path,
        context_path=context_path,
        row_audit=row_audit,
        chart_audit=chart_audit,
    )
    _write_json(context_path, context)
    paths = [str(table_path), str(context_path)]
    if render:
        paths.insert(1, str(chart_path))
    return TotalByDimensionBridgeExport(
        paths=paths,
        audit=audit,
        summary_markdown=_summary_markdown(context),
    )
