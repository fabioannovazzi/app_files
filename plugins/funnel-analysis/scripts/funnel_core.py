"""Deterministic funnel-stage table generation."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_STAGE_DEFINITIONS",
    "FunnelRunResult",
    "compute_funnel_rows",
    "default_recipe",
    "load_recipe",
    "run_funnel_analysis",
]

CAPABILITY_ID = "funnel.stage_table"
TABLE_KEY = "funnel_stage_table"
TABLE_SPEC_NAME = "funnel_stage_table"
EMPTY_STRINGS = {"", "-", "na", "n/a", "nan", "none", "null"}
DEFAULT_STAGE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "stage": "Created records",
        "predicate": {"type": "all"},
        "note": "All source records.",
    },
    {
        "stage": "Owner assigned",
        "predicate": {"type": "nonblank", "column": "Company owner"},
    },
    {
        "stage": "Source classified",
        "predicate": {"type": "nonblank", "column": "Original Source Type"},
    },
    {
        "stage": "Activity logged",
        "predicate": {"type": "nonblank", "column": "Last Activity Date"},
    },
    {
        "stage": "Country identified",
        "predicate": {"type": "nonblank", "column": "Country/Region"},
    },
    {
        "stage": "Industry identified",
        "predicate": {"type": "nonblank", "column": "Industry"},
    },
    {
        "stage": "Positive revenue captured",
        "predicate": {"type": "positive_number", "column": "Annual Revenue"},
    },
    {
        "stage": "Sales accepted",
        "predicate": {
            "type": "equals",
            "column": "Lifecycle Stage",
            "value": "Sales Accepted Lead",
            "case_sensitive": False,
        },
    },
)


@dataclass(frozen=True)
class FunnelRunResult:
    """Paths and payloads written by one funnel table run."""

    output_dir: Path
    html_path: Path
    csv_path: Path
    context_path: Path
    manifest_path: Path
    final_artifacts_path: Path
    rows: list[dict[str, Any]]
    context: dict[str, Any]
    manifest: dict[str, Any]


def default_recipe() -> dict[str, Any]:
    """Return a generic CRM lead-readiness recipe."""

    return {
        "schema_version": "1.0",
        "title": "Baby CRM extract",
        "metric_label": "Lead readiness funnel",
        "unit": "records",
        "scope_label": "Sequential gates",
        "stage_definitions": [dict(item) for item in DEFAULT_STAGE_DEFINITIONS],
    }


def load_recipe(recipe_path: Path | None) -> dict[str, Any]:
    """Load a recipe JSON file or return the default recipe."""

    if recipe_path is None:
        return default_recipe()
    payload = json.loads(recipe_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Recipe must be a JSON object: {recipe_path}")
    return {**default_recipe(), **payload}


def _read_rows(source_file: Path) -> list[dict[str, str]]:
    if not source_file.exists():
        raise FileNotFoundError(f"Source file does not exist: {source_file}")
    with source_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header row: {source_file}")
        return [dict(row) for row in reader]


def _is_nonblank(value: Any) -> bool:
    return str(value or "").strip().lower() not in EMPTY_STRINGS


def _parse_number(value: Any) -> float | None:
    text = str(value or "").strip()
    if text.lower() in EMPTY_STRINGS:
        return None
    cleaned = re.sub(r"[^0-9.+-]", "", text)
    if cleaned in {"", ".", "+", "-", "+.", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _required_columns(stage_definitions: list[dict[str, Any]]) -> set[str]:
    columns: set[str] = set()
    for stage in stage_definitions:
        predicate = stage.get("predicate") or {}
        if not isinstance(predicate, dict):
            raise ValueError(f"Stage predicate must be an object: {stage!r}")
        column = predicate.get("column")
        if isinstance(column, str) and column:
            columns.add(column)
        predicate_columns = predicate.get("columns")
        if isinstance(predicate_columns, list):
            columns.update(str(item) for item in predicate_columns if str(item))
    return columns


def _predicate_note(predicate: dict[str, Any]) -> str:
    predicate_type = str(predicate.get("type") or "")
    if predicate_type == "all":
        return "All source records."
    if predicate_type == "nonblank":
        return f"Nonblank {predicate['column']}."
    if predicate_type == "any_nonblank":
        return "Any of " + ", ".join(str(item) for item in predicate["columns"]) + "."
    if predicate_type == "positive_number":
        return f"{predicate['column']} > 0."
    if predicate_type == "equals":
        return f"{predicate['column']} = {predicate['value']}."
    if predicate_type == "in":
        values = ", ".join(str(item) for item in predicate["values"])
        return f"{predicate['column']} in {values}."
    return predicate_type or "Custom predicate."


def _matches_predicate(row: dict[str, str], predicate: dict[str, Any]) -> bool:
    predicate_type = str(predicate.get("type") or "")
    if predicate_type == "all":
        return True
    if predicate_type == "nonblank":
        return _is_nonblank(row.get(str(predicate["column"])))
    if predicate_type == "any_nonblank":
        return any(
            _is_nonblank(row.get(str(column))) for column in predicate["columns"]
        )
    if predicate_type == "positive_number":
        value = _parse_number(row.get(str(predicate["column"])))
        return value is not None and value > 0
    if predicate_type == "equals":
        left = str(row.get(str(predicate["column"])) or "").strip()
        right = str(predicate.get("value") or "").strip()
        if predicate.get("case_sensitive"):
            return left == right
        return left.lower() == right.lower()
    if predicate_type == "in":
        left = str(row.get(str(predicate["column"])) or "").strip()
        values = [str(item).strip() for item in predicate.get("values") or []]
        if predicate.get("case_sensitive"):
            return left in values
        return left.lower() in {value.lower() for value in values}
    raise ValueError(f"Unsupported stage predicate type: {predicate_type}")


def _stage_id(stage: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "_", stage.lower()).strip("_")
    return compact or "stage"


def _validate_stage_definitions(
    rows: list[dict[str, str]], stage_definitions: list[dict[str, Any]]
) -> None:
    if not stage_definitions:
        raise ValueError("At least one stage definition is required.")
    available_columns = set(rows[0]) if rows else set()
    missing_columns = sorted(_required_columns(stage_definitions) - available_columns)
    if missing_columns:
        raise ValueError(
            "Missing stage predicate columns: " + ", ".join(missing_columns)
        )
    for stage in stage_definitions:
        if not str(stage.get("stage") or "").strip():
            raise ValueError("Every stage definition requires a non-empty stage label.")
        predicate = stage.get("predicate")
        if not isinstance(predicate, dict):
            raise ValueError(f"Stage {stage['stage']} requires a predicate object.")


def compute_funnel_rows(
    rows: list[dict[str, str]], stage_definitions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return sequential funnel rows from source rows and explicit stages."""

    _validate_stage_definitions(rows, stage_definitions)
    total_count = len(rows)
    remaining = rows
    output_rows: list[dict[str, Any]] = []
    for position, stage in enumerate(stage_definitions, start=1):
        stage_label = str(stage["stage"]).strip()
        predicate = dict(stage["predicate"])
        start_count = len(remaining)
        passed = [row for row in remaining if _matches_predicate(row, predicate)]
        pass_count = len(passed)
        drop_off = pass_count - start_count
        stage_conversion = pass_count / start_count if start_count else None
        cumulative_conversion = pass_count / total_count if total_count else None
        note = str(stage.get("note") or _predicate_note(predicate))
        output_rows.append(
            {
                "stage_id": _stage_id(stage_label),
                "stage": stage_label,
                "position": position,
                "start_count": start_count,
                "pass_count": pass_count,
                "drop_off": drop_off,
                "stage_conversion": stage_conversion,
                "cumulative_conversion": cumulative_conversion,
                "note": note,
            }
        )
        remaining = passed
    return output_rows


def _json_dump(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _write_table_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "stage_id",
        "stage",
        "position",
        "start_count",
        "pass_count",
        "drop_off",
        "stage_conversion",
        "cumulative_conversion",
        "note",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _format_count(value: int | float | None) -> str:
    if value is None:
        return ""
    return f"{int(value):,}"


def _format_signed_count(value: int | float | None) -> str:
    if value is None:
        return ""
    numeric = int(value)
    if numeric > 0:
        return f"+{numeric:,}"
    return f"{numeric:,}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


def _bar_class(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value >= 0.8:
        return "strong"
    if value >= 0.5:
        return "mid"
    return "weak"


def _render_drop_cell(row: dict[str, Any], max_drop: int) -> str:
    drop = int(row["drop_off"])
    width = 0.0 if max_drop == 0 else min(abs(drop) / max_drop * 100, 100)
    cls = "zero" if drop == 0 else "negative"
    return (
        f'<td class="num drop {cls}">'
        f'<span class="drop-track"><span class="drop-bar" style="width:{width:.1f}%"></span></span>'
        f'<span class="drop-label">{escape(_format_signed_count(drop))}</span>'
        "</td>"
    )


def _render_conversion_cell(value: float | None) -> str:
    width = 0.0 if value is None else max(0.0, min(value * 100, 100))
    cls = _bar_class(value)
    return (
        f'<td class="num conversion {cls}">'
        f'<span class="conversion-track"><span class="conversion-bar" style="width:{width:.1f}%"></span></span>'
        f'<span class="conversion-label">{escape(_format_percent(value))}</span>'
        "</td>"
    )


def _render_cumulative_cell(value: float | None) -> str:
    left = 0.0 if value is None else max(0.0, min(value * 100, 100))
    return (
        '<td class="num cumulative">'
        f'<span class="pin-track"><span class="pin-line" style="left:{left:.1f}%"></span>'
        f'<span class="pin-dot" style="left:{left:.1f}%"></span></span>'
        f'<span class="pin-label">{escape(_format_percent(value))}</span>'
        "</td>"
    )


def _render_html(
    rows: list[dict[str, Any]], recipe: dict[str, Any], source_name: str
) -> str:
    max_drop = max((abs(int(row["drop_off"])) for row in rows), default=0)
    body_rows: list[str] = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f'<td class="stage">{escape(str(row["stage"]))}</td>'
            f'<td class="num">{escape(_format_count(row["start_count"]))}</td>'
            f'<td class="num">{escape(_format_count(row["pass_count"]))}</td>'
            f"{_render_drop_cell(row, max_drop)}"
            f"{_render_conversion_cell(row['stage_conversion'])}"
            f"{_render_cumulative_cell(row['cumulative_conversion'])}"
            f'<td class="note">{escape(str(row["note"]))}</td>'
            "</tr>"
        )
    metric_line = f"{recipe['metric_label']} in {recipe['unit']}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(str(recipe['title']))} - {escape(str(recipe['metric_label']))}</title>
<style>
:root {{
  --ink: #111;
  --muted: #4b5563;
  --rule: #c9c9c9;
  --heavy: #111;
  --green: #7faa00;
  --amber: #c99700;
  --red: #ef2a1d;
  --black-pin: #222;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: #fff;
  color: var(--ink);
  font-family: Arial, Helvetica, sans-serif;
}}
.page {{
  width: 980px;
  padding: 34px 36px 28px;
  background: #fff;
}}
.title {{
  margin-bottom: 26px;
  line-height: 1.12;
}}
.title p {{
  margin: 0;
  font-size: 15px;
}}
.title .metric {{
  font-weight: 700;
}}
.title-rule {{
  height: 1px;
  margin-top: 16px;
  background: #888;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 13px;
}}
thead th {{
  padding: 6px 7px 7px;
  border-bottom: 2px solid var(--heavy);
  color: var(--ink);
  font-weight: 700;
  text-align: right;
}}
thead th.stage, thead th.note {{
  text-align: left;
}}
tbody td {{
  padding: 5px 7px;
  border-bottom: 1px solid var(--rule);
  height: 30px;
  vertical-align: middle;
}}
tbody tr:first-child td,
tbody tr:last-child td {{
  border-bottom: 2px solid var(--heavy);
  font-weight: 700;
}}
.stage {{ width: 170px; text-align: left; }}
.note {{ width: 205px; text-align: left; color: var(--muted); font-size: 12px; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.drop,
.conversion,
.cumulative {{
  position: relative;
  white-space: nowrap;
}}
.drop-track,
.conversion-track,
.pin-track {{
  position: absolute;
  left: 8px;
  right: 58px;
  top: 50%;
  height: 10px;
  transform: translateY(-50%);
}}
.drop-track {{
  border-right: 2px solid var(--black-pin);
}}
.drop-bar {{
  position: absolute;
  right: 0;
  top: 1px;
  height: 8px;
  background: var(--red);
}}
.drop.zero .drop-bar {{
  width: 0 !important;
}}
.drop-label,
.conversion-label,
.pin-label {{
  position: relative;
  z-index: 2;
}}
.drop.negative .drop-label {{ color: var(--red); }}
.conversion-track {{
  background: #f3f3f3;
  border-right: 2px solid var(--black-pin);
}}
.conversion-bar {{
  display: block;
  height: 10px;
}}
.conversion.strong .conversion-bar {{ background: var(--green); }}
.conversion.mid .conversion-bar {{ background: var(--amber); }}
.conversion.weak .conversion-bar {{ background: var(--red); }}
.conversion.neutral .conversion-bar {{ background: #aaa; }}
.pin-track {{
  height: 14px;
  border-bottom: 1px solid #9d9d9d;
}}
.pin-line {{
  position: absolute;
  bottom: -4px;
  width: 2px;
  height: 14px;
  background: var(--red);
}}
.pin-dot {{
  position: absolute;
  bottom: -5px;
  width: 7px;
  height: 7px;
  margin-left: -2px;
  background: var(--black-pin);
}}
.source {{
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--rule);
  color: var(--muted);
  font-size: 12px;
}}
</style>
</head>
<body>
<main class="page" data-gallery-screenshot>
  <header class="title">
    <p>{escape(str(recipe['title']))}</p>
    <p class="metric">{escape(metric_line)}</p>
    <p>{escape(str(recipe['scope_label']))}</p>
    <div class="title-rule"></div>
  </header>
  <table>
    <thead>
      <tr>
        <th class="stage">Stage</th>
        <th>Start</th>
        <th>Pass</th>
        <th>Drop-off</th>
        <th>Stage %</th>
        <th>Cumulative %</th>
        <th class="note">Note</th>
      </tr>
    </thead>
    <tbody>
      {''.join(body_rows)}
    </tbody>
  </table>
  <p class="source">Source: {escape(source_name)}</p>
</main>
</body>
</html>
"""


def _build_context(
    rows: list[dict[str, Any]],
    recipe: dict[str, Any],
    source_file: Path,
) -> dict[str, Any]:
    chart_title_lines = [
        str(recipe["title"]),
        f"{recipe['metric_label']} in {recipe['unit']}",
        str(recipe["scope_label"]),
    ]
    return {
        "schema_version": "1.0",
        "analysis_type": "funnel_stage_table",
        "object_type": "table",
        "capability_id": CAPABILITY_ID,
        "table_key": TABLE_KEY,
        "table_spec_name": TABLE_SPEC_NAME,
        "metric_label": recipe["metric_label"],
        "unit": recipe["unit"],
        "title": recipe["title"],
        "scope_label": recipe["scope_label"],
        "chart_title_lines": chart_title_lines,
        "title_contract": {
            "who": chart_title_lines[0],
            "what": chart_title_lines[1],
            "when": chart_title_lines[2],
        },
        "source_file": source_file.name,
        "row_grain": "One row per ordered stage definition; each row filters the rows that passed the prior stage.",
        "stage_definitions": recipe["stage_definitions"],
        "table_rows": rows,
    }


def _build_manifest(
    output_dir: Path,
    source_file: Path,
    recipe: dict[str, Any],
) -> dict[str, Any]:
    resolved_parameters = {
        "source_file": source_file.name,
        "stage_definitions": recipe["stage_definitions"],
        "metric_label": recipe["metric_label"],
        "unit": recipe["unit"],
        "scope_label": recipe["scope_label"],
    }
    return {
        "schema_version": "1.0",
        "producer": {"plugin": "funnel-analysis", "capability_id": CAPABILITY_ID},
        "artifacts": [
            {
                "artifact_id": TABLE_KEY,
                "kind": "tables",
                "artifact_type": "table",
                "capability_id": CAPABILITY_ID,
                "table_key": TABLE_KEY,
                "table_spec_name": TABLE_SPEC_NAME,
                "path": "funnel_stage_table.html",
                "source_path": "funnel_stage_table.html",
                "data_path": "funnel_stage_table_chart_data.csv",
                "context_path": "funnel_stage_table_chart_context.json",
                "resolved_parameters": resolved_parameters,
            },
            {
                "artifact_id": "context",
                "kind": "contexts",
                "artifact_type": "context",
                "path": "funnel_stage_table_chart_context.json",
            },
        ],
        "output_dir": output_dir.name,
    }


def run_funnel_analysis(
    source_file: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    language: str = "en",
) -> FunnelRunResult:
    """Run a deterministic funnel-stage table and write artifacts."""

    recipe = load_recipe(recipe_path)
    recipe["language"] = language
    stage_definitions = recipe.get("stage_definitions")
    if not isinstance(stage_definitions, list):
        raise ValueError("Recipe stage_definitions must be a list.")
    rows = _read_rows(source_file)
    funnel_rows = compute_funnel_rows(rows, stage_definitions)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "funnel_stage_table.html"
    csv_path = output_dir / "funnel_stage_table_chart_data.csv"
    context_path = output_dir / "funnel_stage_table_chart_context.json"
    manifest_path = output_dir / "artifact_manifest.json"
    final_artifacts_path = output_dir / "final_artifacts.json"
    recipe_output_path = output_dir / "used_recipe.json"

    _write_table_csv(funnel_rows, csv_path)
    html_path.write_text(
        _render_html(funnel_rows, recipe, source_file.name),
        encoding="utf-8",
    )
    _json_dump(recipe, recipe_output_path)
    context = _build_context(funnel_rows, recipe, source_file)
    _json_dump(context, context_path)
    manifest = _build_manifest(output_dir, source_file, recipe)
    _json_dump(manifest, manifest_path)
    _json_dump(
        {
            "schema_version": "1.0",
            "plugin": "funnel-analysis",
            "outputs": [
                {"path": html_path.name, "kind": "html", "status": "written"},
                {"path": csv_path.name, "kind": "csv", "status": "written"},
                {"path": context_path.name, "kind": "json", "status": "written"},
                {
                    "path": manifest_path.name,
                    "kind": "json",
                    "status": "written",
                },
            ],
        },
        final_artifacts_path,
    )
    return FunnelRunResult(
        output_dir=output_dir,
        html_path=html_path,
        csv_path=csv_path,
        context_path=context_path,
        manifest_path=manifest_path,
        final_artifacts_path=final_artifacts_path,
        rows=funnel_rows,
        context=context,
        manifest=manifest,
    )
