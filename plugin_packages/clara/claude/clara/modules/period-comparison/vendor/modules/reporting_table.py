"""Shared IBCS-style reporting table, extracted from Period Comparison.

Render supplied comparison rows only. Source selection and favorable/adverse
meaning remain with the caller; bar geometry and number formatting are mechanical.
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path
from typing import Any

__all__ = ["render_reporting_table", "write_reporting_table"]
TOLERANCE = 0.000001


def _table_value_scale(rows: list[dict[str, Any]]) -> tuple[float, str]:
    """Return a compact display scale and label for table values."""

    values = [
        abs(float(row.get(key) or 0.0))
        for row in rows
        for key in ("baseline_value", "comparison_value", "absolute_variance")
    ]
    max_value = max(values or [0.0])
    if max_value >= 1_000_000:
        return 1_000_000.0, "m"
    if max_value >= 1_000:
        return 1_000.0, "k"
    return 1.0, "units"


def _format_scaled_value(
    value: float, scale: float, *, signed: bool = False, language: str = "en"
) -> str:
    """Format table values with tabular, compact notation."""

    scaled = value / scale
    if scaled == 0:
        scaled = 0.0
    prefix = "+" if signed and scaled > 0 else ""
    text = f"{prefix}{scaled:,.0f}" if scale == 1.0 else f"{prefix}{scaled:,.1f}"
    return (
        text.translate(str.maketrans({",": ".", ".": ","}))
        if language == "it"
        else text
    )


def _format_relative_percent(value: float | None, language: str = "en") -> str:
    """Format a signed relative variance."""

    if value is None or math.isnan(value):
        return "n/d" if language == "it" else "n/a"
    text = f"{value:+.1f}%" if value else "0.0%"
    return text.replace(".", ",") if language == "it" else text


def _variance_marker_html(
    *,
    value: float | None,
    label: str,
    max_abs_value: float,
    marker_style: str = "bar",
) -> str:
    """Return centered positive/negative variance marker markup."""

    if value is None or math.isnan(float(value)):
        return (
            '<span class="variance-marker">'
            '<span class="variance-lane negative-lane"></span>'
            '<span class="variance-axis"></span>'
            '<span class="variance-lane positive-lane"></span>'
            f'<span class="variance-label muted">{escape(label)}</span>'
            "</span>"
        )
    value = float(value)
    width = 0.0
    if max_abs_value > TOLERANCE:
        width = min(100.0, abs(value) / max_abs_value * 100)
    sign_class = (
        "positive"
        if value > TOLERANCE
        else "negative" if value < -TOLERANCE else "neutral"
    )
    negative_width = width if sign_class == "negative" else 0.0
    positive_width = width if sign_class == "positive" else 0.0
    if marker_style == "pin":
        negative_pin = (
            f'<span class="variance-pin-line negative" style="width:{negative_width:.1f}%">'
            '<span class="variance-pin"></span></span>'
            if sign_class == "negative"
            else ""
        )
        positive_pin = (
            f'<span class="variance-pin-line positive" style="width:{positive_width:.1f}%">'
            '<span class="variance-pin"></span></span>'
            if sign_class == "positive"
            else ""
        )
        neutral_pin = (
            '<span class="variance-zero-pin"><span class="variance-pin"></span></span>'
            if sign_class == "neutral"
            else ""
        )
        return (
            '<span class="variance-marker">'
            f'<span class="variance-lane negative-lane">{negative_pin}</span>'
            f'<span class="variance-axis">{neutral_pin}</span>'
            f'<span class="variance-lane positive-lane">{positive_pin}</span>'
            f'<span class="variance-label {sign_class}">{escape(label)}</span>'
            "</span>"
        )
    return (
        '<span class="variance-marker">'
        '<span class="variance-lane negative-lane">'
        f'<span class="variance-bar negative" style="width:{negative_width:.1f}%"></span>'
        "</span>"
        '<span class="variance-axis"></span>'
        '<span class="variance-lane positive-lane">'
        f'<span class="variance-bar positive" style="width:{positive_width:.1f}%"></span>'
        "</span>"
        f'<span class="variance-label {sign_class}">{escape(label)}</span>'
        "</span>"
    )


def render_reporting_table(
    *,
    row_header: str,
    rows: list[dict[str, Any]],
    baseline_label: str,
    comparison_label: str,
    entity_label: str,
    comparison_caption: str,
    metric: str,
    source_label: str,
    language: str = "en",
    fragment: bool = False,
    row_label_width: int | None = None,
    scale_rows: list[dict[str, Any]] | None = None,
    value_scale: int | None = None,
    value_width: int = 88,
) -> str:
    """Write a compact scenario and variance table artifact."""

    # An interactive group shares its unit and variance scales across views.
    scale_basis = rows if scale_rows is None else [*rows, *scale_rows]
    scale, scale_label = _table_value_scale(scale_basis)
    if value_scale is not None:
        if value_scale not in {1, 1000, 1000000}:
            raise ValueError("value_scale must be 1, 1000 or 1000000")
        scale, scale_label = (
            float(value_scale),
            {1: "units", 1000: "k", 1000000: "m"}[value_scale],
        )
    measure_suffix = (
        ""
        if scale_label == "units"
        else (
            (" × 1.000" if scale_label == "k" else " × 1.000.000")
            if language == "it"
            else f" en {scale_label}" if language == "es" else f" in {scale_label}"
        )
    )
    max_abs_absolute = max(
        (abs(float(row["absolute_variance"])) for row in scale_basis),
        default=0.0,
    )
    max_abs_relative = max(
        (
            abs(float(row["relative_variance"]))
            for row in scale_basis
            if row.get("relative_variance") is not None
        ),
        default=0.0,
    )
    row_label_width = row_label_width or (
        92 if row_header in {"Period", "Periodo"} else 124
    )
    variance_width = 172
    table_width = row_label_width + (value_width * 2) + (variance_width * 2)
    page_width = table_width + 56
    table_rows: list[str] = []
    for index, row in enumerate(rows):
        absolute_variance = float(row["absolute_variance"])
        sign_class = (
            "positive"
            if absolute_variance > TOLERANCE
            else "negative" if absolute_variance < -TOLERANCE else "neutral"
        )
        relative_variance = row.get("relative_variance")
        relative_value = None if relative_variance is None else float(relative_variance)
        table_rows.append(
            '<tr class="'
            + (
                "summary-row"
                if row.get("row_type") in {"subtotal", "total"}
                or (index == 0 and row_header == "Window")
                else "detail-row"
            )
            + (
                " lower"
                if row.get("favorable_direction") == "lower"
                else (
                    " neutral-direction"
                    if row.get("favorable_direction") == "neutral"
                    else ""
                )
            )
            + f'" data-absolute-variance="{escape(str(row["absolute_variance"]), quote=True)}">'
            f"<th>{escape(str(row['row_label']))}</th>"
            f"<td>{escape(_format_scaled_value(float(row['baseline_value']), scale, language=language))}</td>"
            f"<td>{escape(_format_scaled_value(float(row['comparison_value']), scale, language=language))}</td>"
            f'<td class="variance-cell group-start {sign_class}">'
            f"{_variance_marker_html(value=absolute_variance, label=_format_scaled_value(absolute_variance, scale, signed=True, language=language), max_abs_value=max_abs_absolute)}</td>"
            f'<td class="variance-cell">'
            f"{_variance_marker_html(value=relative_value, label=_format_relative_percent(relative_value, language), max_abs_value=max_abs_relative, marker_style='pin')}</td>"
            "</tr>"
        )
    html = f"""<!doctype html>
<html lang="{escape(language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(entity_label)} - {escape(metric)}</title>
  <style>
    .reporting-comparison {{
      --ink: #0f1114;
      --muted: #5d6670;
      --rule: #c9cdd1;
      --heavy: #111;
      --pin: #222;
      --soft: #f3f4f5;
      --negative: #e22a1d;
      --positive: #86ad00;
      --neutral: #444;
    }}
    .reporting-comparison * {{
      box-sizing: border-box;
    }}
    .reporting-comparison {{
      margin: 0;
      background: #fff;
      color: var(--ink);
      font: 14px/1.2 Arial, Helvetica, sans-serif;
      font-variant-numeric: tabular-nums;
    }}
    .reporting-comparison .page {{
      width: {page_width}px;
      padding: 24px 28px 20px;
      background: #fff;
    }}
    .reporting-comparison .title-block {{
      border-bottom: 2px solid #858585;
      padding-bottom: 24px;
      width: {table_width}px;
    }}
    .reporting-comparison .title-line {{
      margin: 0;
      color: var(--ink);
      font-size: 14px;
      line-height: 1.18;
    }}
    .reporting-comparison .title-metric strong {{
      font-weight: 700;
    }}
    .reporting-comparison table {{
      border-collapse: collapse;
      margin-top: 14px;
      table-layout: fixed;
      width: {table_width}px;
    }}
    col.row-label {{ width: {row_label_width}px; }}
    col.value {{ width: {value_width}px; }}
    col.variance {{ width: {variance_width}px; }}
    .reporting-comparison thead tr.group th {{
      border-bottom: 0;
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
      padding: 0 8px 4px;
      text-align: center;
    }}
    .reporting-comparison thead tr.labels th {{
      border-bottom: 2px solid var(--heavy);
      font-size: 14px;
      font-weight: 700;
      padding: 5px 8px 7px;
      text-align: right;
    }}
    .reporting-comparison thead tr.labels th:first-child,
    .reporting-comparison tbody th {{
      text-align: left;
    }}
    .reporting-comparison tbody th,
    .reporting-comparison tbody td {{
      border-bottom: 1px solid var(--rule);
      font-size: 14px;
      height: 31px;
      padding: 5px 7px;
      text-align: right;
      vertical-align: middle;
      white-space: nowrap;
      min-width: 0;
    }}
    .reporting-comparison tbody th {{
      font-weight: 500;
      text-align: left;
    }}
    .reporting-comparison tbody tr.summary-row th,
    .reporting-comparison tbody tr.summary-row td {{
      border-bottom: 2px solid var(--heavy);
      font-weight: 700;
    }}
    .reporting-comparison .group-start {{
      border-left: 2px solid var(--heavy);
    }}
    .reporting-comparison .negative {{
      color: var(--negative);
    }}
    .reporting-comparison .positive {{
      color: var(--positive);
    }}
    .reporting-comparison .neutral {{
      color: var(--neutral);
    }}
    .reporting-comparison .muted {{
      color: var(--muted);
    }}
    .reporting-comparison .variance-cell {{
      padding-left: 8px;
    }}
    .reporting-comparison .variance-marker {{
      display: grid;
      gap: 0;
      grid-template-columns: 50px 2px 50px 56px;
    }}
    .reporting-comparison .variance-lane {{
      align-items: center;
      display: flex;
      height: 18px;
    }}
    .reporting-comparison .negative-lane {{
      justify-content: flex-end;
    }}
    .reporting-comparison .positive-lane {{
      justify-content: flex-start;
    }}
    .reporting-comparison .variance-axis {{
      background: var(--heavy);
      display: block;
      height: 22px;
      margin-top: -2px;
      width: 2px;
    }}
    .reporting-comparison .variance-bar {{
      display: block;
      height: 11px;
      min-width: 0;
    }}
    .reporting-comparison .variance-bar.negative {{
      background: var(--negative);
    }}
    .reporting-comparison .variance-bar.positive {{
      background: var(--positive);
    }}
    .reporting-comparison .variance-pin-line {{
      align-items: center;
      display: flex;
      height: 2px;
      min-width: 0;
    }}
    .reporting-comparison .variance-pin-line.negative {{
      background: var(--negative);
      justify-content: flex-start;
    }}
    .reporting-comparison .variance-pin-line.positive {{
      background: var(--positive);
      justify-content: flex-end;
    }}
    .reporting-comparison .variance-pin {{
      background: var(--pin);
      display: block;
      flex: 0 0 auto;
      height: 7px;
      width: 7px;
    }}
    .reporting-comparison .variance-zero-pin {{
      align-items: center;
      display: flex;
      height: 22px;
      justify-content: center;
      left: -3px;
      position: relative;
      width: 7px;
    }}
    .reporting-comparison .variance-label {{
      font-size: 14px;
      line-height: 18px;
      padding-left: 8px;
      text-align: right;
    }}
    .reporting-comparison .source {{
      border-top: 1px solid var(--rule);
      color: var(--muted);
      font-size: 14px;
      margin-top: 14px;
      padding-top: 8px;
    }}
    .reporting-comparison {{ max-width: 100%; overflow-x: auto; }}
    .reporting-comparison .page {{ padding: 20px 0; margin: 0; }}
    .reporting-comparison .title-block {{ border-top: 0; padding-top: 0; }}
    .reporting-comparison th {{ background: #fff; color: var(--ink); }}
    .reporting-comparison tbody th {{ white-space: normal; overflow-wrap: break-word; }}
    .reporting-comparison .lower .variance-bar.positive,
    .reporting-comparison .lower .variance-pin-line.positive {{ background: var(--negative); }}
    .reporting-comparison .lower .variance-bar.negative,
    .reporting-comparison .lower .variance-pin-line.negative {{ background: var(--positive); }}
    .reporting-comparison .lower .positive {{ color: var(--negative); }}
    .reporting-comparison .lower .negative {{ color: var(--positive); }}
    .reporting-comparison .neutral-direction .positive,
    .reporting-comparison .neutral-direction .negative {{ color: var(--neutral); }}
    .reporting-comparison .neutral-direction .variance-bar,
    .reporting-comparison .neutral-direction .variance-pin-line {{ background: var(--neutral); }}
    @media print {{
      .reporting-comparison {{ overflow: visible; break-inside: avoid-page; }}
      .reporting-comparison .page,
      .reporting-comparison .title-block,
      .reporting-comparison table {{ width: 100%; }}
      .reporting-comparison col.row-label {{ width: 24%; }}
      .reporting-comparison col.value {{ width: 12%; }}
      .reporting-comparison col.variance {{ width: 26%; }}
    }}
  </style>
</head>
<body>
<div class="reporting-comparison">
  <main class="page" data-gallery-screenshot>
    <header class="title-block">
      <p class="title-line">{escape(entity_label)}</p>
      <p class="title-line title-metric"><strong>{escape(metric)}</strong>{escape(measure_suffix)}</p>
      <p class="title-line">{escape(comparison_caption)}</p>
    </header>
    <table>
      <colgroup>
        <col class="row-label">
        <col class="value">
        <col class="value">
        <col class="variance">
        <col class="variance">
      </colgroup>
      <thead>
        <tr class="group">
          <th></th>
          <th colspan="2">{'Confronto' if language == 'it' else 'Escenario' if language == 'es' else 'Scenario'}</th>
          <th class="group-start" colspan="2">{'Scostamento' if language == 'it' else 'Variación' if language == 'es' else 'Change'}</th>
        </tr>
        <tr class="labels">
          <th>{escape(row_header)}</th>
          <th>{escape(baseline_label)}</th>
          <th>{escape(comparison_label)}</th>
          <th class="group-start">Δ</th>
          <th>{'Δ %' if language == 'it' else '% variación' if language == 'es' else '% change'}</th>
        </tr>
      </thead>
      <tbody>
        {''.join(table_rows)}
      </tbody>
    </table>
    <div class="source">{escape(source_label)}</div>
  </main>
</div>
</body>
</html>
"""
    if fragment:
        style = html.split("<style>", 1)[1].split("</style>", 1)[0]
        body = html.split("<body>", 1)[1].split("</body>", 1)[0]
        return "<style>" + style + "</style>" + body
    return html


def write_reporting_table(*, output_path: Path, **kwargs: Any) -> None:
    """Write the same reporting component as a standalone HTML artifact."""
    output_path.write_text(render_reporting_table(**kwargs), encoding="utf-8")
