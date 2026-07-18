"""Deterministic profit-and-loss statement table generation."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_STATEMENT_ROWS",
    "StatementRunResult",
    "default_recipe",
    "load_recipe",
    "run_statement_analysis",
    "resolve_statement_rows",
]

CAPABILITY_ID = "statement.pnl_table"
TABLE_KEY = "pnl_statement_table"
TABLE_SPEC_NAME = "pnl_statement_table"
DEFAULT_PERIODS = ("2012", "2013", "2014", "2015")
DEFAULT_SCENARIOS_BY_PERIOD = {
    "2012": ["PL", "AC"],
    "2013": ["PL", "AC"],
    "2014": ["PL", "AC"],
    "2015": ["PL", "FC"],
}
DEFAULT_STATEMENT_ROWS: tuple[dict[str, Any], ...] = (
    {
        "key": "software_revenue",
        "label": "Software revenue",
        "level": 0,
        "line_type": "detail",
        "prefix": "+",
        "source_key": "software_revenue",
    },
    {
        "key": "support_revenue",
        "label": "Support revenue",
        "level": 0,
        "line_type": "detail",
        "prefix": "+",
        "source_key": "support_revenue",
    },
    {
        "key": "consulting_revenue",
        "label": "Consulting revenue",
        "level": 0,
        "line_type": "detail",
        "prefix": "+",
        "source_key": "consulting_revenue",
    },
    {
        "key": "revenue",
        "label": "Revenue",
        "level": 0,
        "line_type": "subtotal",
        "prefix": "=",
        "formula": [
            {"row": "software_revenue", "factor": 1},
            {"row": "support_revenue", "factor": 1},
            {"row": "consulting_revenue", "factor": 1},
        ],
    },
    {
        "key": "cost_of_sales",
        "label": "Cost of sales",
        "level": 0,
        "line_type": "detail",
        "prefix": "-",
        "source_key": "cost_of_sales",
    },
    {
        "key": "gross_profit",
        "label": "Gross profit",
        "level": 0,
        "line_type": "subtotal",
        "prefix": "=",
        "formula": [
            {"row": "revenue", "factor": 1},
            {"row": "cost_of_sales", "factor": -1},
        ],
    },
    {
        "key": "research_development",
        "label": "Research and development expenses",
        "level": 1,
        "line_type": "detail",
        "prefix": "-",
        "source_key": "research_development",
    },
    {
        "key": "selling_admin",
        "label": "Selling and general administrative expenses",
        "level": 1,
        "line_type": "detail",
        "prefix": "-",
        "source_key": "selling_admin",
    },
    {
        "key": "other_operating_income",
        "label": "Other operating income",
        "level": 1,
        "line_type": "detail",
        "prefix": "+",
        "source_key": "other_operating_income",
    },
    {
        "key": "other_operating_expenses",
        "label": "Other operating expenses",
        "level": 1,
        "line_type": "detail",
        "prefix": "-",
        "source_key": "other_operating_expenses",
    },
    {
        "key": "other_financial_income_net",
        "label": "Other financial income, net",
        "level": 1,
        "line_type": "detail",
        "prefix": "+",
        "source_key": "other_financial_income_net",
    },
    {
        "key": "income_before_tax",
        "label": "Income from continuing operations before tax",
        "level": 0,
        "line_type": "subtotal",
        "prefix": "=",
        "formula": [
            {"row": "gross_profit", "factor": 1},
            {"row": "research_development", "factor": -1},
            {"row": "selling_admin", "factor": -1},
            {"row": "other_operating_income", "factor": 1},
            {"row": "other_operating_expenses", "factor": -1},
            {"row": "other_financial_income_net", "factor": 1},
        ],
    },
    {
        "key": "income_tax",
        "label": "Income tax expenses",
        "level": 1,
        "line_type": "detail",
        "prefix": "-",
        "source_key": "income_tax",
    },
    {
        "key": "income_continuing_operations",
        "label": "Income from continuing operations",
        "level": 0,
        "line_type": "subtotal",
        "prefix": "=",
        "formula": [
            {"row": "income_before_tax", "factor": 1},
            {"row": "income_tax", "factor": -1},
        ],
    },
    {
        "key": "income_discontinued_operations",
        "label": "Income from discontinued operations",
        "level": 0,
        "line_type": "detail",
        "prefix": "+",
        "source_key": "income_discontinued_operations",
    },
    {
        "key": "net_income",
        "label": "Net income",
        "level": 0,
        "line_type": "total",
        "prefix": "=",
        "formula": [
            {"row": "income_continuing_operations", "factor": 1},
            {"row": "income_discontinued_operations", "factor": 1},
        ],
    },
)


@dataclass(frozen=True)
class StatementRunResult:
    """Paths and payloads written by one statement table run."""

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
    """Return the default P&L statement recipe."""

    return {
        "schema_version": "1.0",
        "title": "SoftCons International Inc.",
        "statement_label": "Profit and loss statement",
        "unit": "mUSD",
        "scope_label": "2012..2015 PL and AC (FC)",
        "mappings": {
            "row_key_column": "row_key",
            "period_column": "period",
            "scenario_column": "scenario",
            "value_column": "value",
        },
        "periods": list(DEFAULT_PERIODS),
        "scenarios_by_period": dict(DEFAULT_SCENARIOS_BY_PERIOD),
        "statement_rows": [dict(item) for item in DEFAULT_STATEMENT_ROWS],
    }


def load_recipe(recipe_path: Path | None) -> dict[str, Any]:
    """Load a recipe JSON file or return the default recipe."""

    if recipe_path is None:
        return default_recipe()
    payload = json.loads(recipe_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Recipe must be a JSON object: {recipe_path}")
    merged = default_recipe()
    default_mappings = dict(merged["mappings"])
    payload_mappings = payload.get("mappings")
    if payload_mappings is not None and not isinstance(payload_mappings, dict):
        raise ValueError("Recipe mappings must be an object.")
    merged.update(payload)
    merged["mappings"] = {
        **default_mappings,
        **(payload_mappings or {}),
    }
    return merged


def _parse_number(value: Any) -> float:
    text = str(value or "").strip()
    cleaned = re.sub(r"[^0-9.+-]", "", text)
    if cleaned in {"", ".", "+", "-", "+.", "-."}:
        raise ValueError(f"Cannot parse numeric value: {value!r}")
    return float(cleaned)


def _source_columns(recipe: dict[str, Any]) -> dict[str, str]:
    mappings = recipe.get("mappings")
    if not isinstance(mappings, dict):
        raise ValueError("Recipe mappings must be an object.")
    columns: dict[str, str] = {}
    for role, default in {
        "row_key_column": "row_key",
        "period_column": "period",
        "scenario_column": "scenario",
        "value_column": "value",
    }.items():
        value = str(mappings.get(role) or default).strip()
        if not value:
            raise ValueError(f"Recipe mapping {role} must name a source column.")
        columns[role] = value
    return columns


def _read_values(
    source_file: Path, recipe: dict[str, Any]
) -> dict[tuple[str, str, str], float]:
    if not source_file.exists():
        raise FileNotFoundError(f"Source file does not exist: {source_file}")
    columns = _source_columns(recipe)
    with source_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        required = set(columns.values())
        missing = sorted(required - fieldnames)
        if missing:
            raise ValueError(
                "Statement value CSV missing columns: " + ", ".join(missing)
            )
        values: dict[tuple[str, str, str], float] = {}
        for line_number, row in enumerate(reader, start=2):
            row_key = str(row.get(columns["row_key_column"]) or "").strip()
            period = str(row.get(columns["period_column"]) or "").strip()
            scenario = str(row.get(columns["scenario_column"]) or "").strip()
            if not row_key or not period or not scenario:
                raise ValueError(
                    f"Blank row_key, period, or scenario at line {line_number}."
                )
            values[(row_key, period, scenario)] = _parse_number(
                row.get(columns["value_column"])
            )
    return values


def _period_scenario_pairs(recipe: dict[str, Any]) -> list[tuple[str, str]]:
    periods = [str(item) for item in recipe.get("periods") or []]
    scenarios_by_period = recipe.get("scenarios_by_period") or {}
    if not periods:
        raise ValueError("Recipe periods must not be empty.")
    if not isinstance(scenarios_by_period, dict):
        raise ValueError("Recipe scenarios_by_period must be an object.")
    pairs: list[tuple[str, str]] = []
    for period in periods:
        scenarios = scenarios_by_period.get(period)
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError(f"Missing scenarios for period {period}.")
        pairs.extend((period, str(scenario)) for scenario in scenarios)
    return pairs


def _validate_recipe(recipe: dict[str, Any]) -> None:
    rows = recipe.get("statement_rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Recipe statement_rows must be a non-empty list.")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Every statement row must be an object.")
        key = str(row.get("key") or "").strip()
        if not key:
            raise ValueError("Every statement row requires a key.")
        if key in seen:
            raise ValueError(f"Duplicate statement row key: {key}")
        seen.add(key)
        if not str(row.get("label") or "").strip():
            raise ValueError(f"Statement row {key} requires a label.")
        formula = row.get("formula")
        source_key = row.get("source_key")
        if formula is None and not source_key:
            raise ValueError(f"Statement row {key} requires source_key or formula.")
        if formula is not None:
            if not isinstance(formula, list) or not formula:
                raise ValueError(
                    f"Statement row {key} formula must be a non-empty list."
                )
            for term in formula:
                ref = str(term.get("row") if isinstance(term, dict) else "").strip()
                if ref not in seen:
                    raise ValueError(
                        f"Statement row {key} references unknown or later row {ref}."
                    )
    _period_scenario_pairs(recipe)


def resolve_statement_rows(
    values: dict[tuple[str, str, str], float],
    recipe: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return ordered statement rows with deterministic formulas resolved."""

    _validate_recipe(recipe)
    pairs = _period_scenario_pairs(recipe)
    resolved_by_key: dict[str, dict[tuple[str, str], float]] = {}
    output_rows: list[dict[str, Any]] = []
    for position, row in enumerate(recipe["statement_rows"], start=1):
        key = str(row["key"])
        row_values: dict[tuple[str, str], float] = {}
        formula = row.get("formula")
        for period, scenario in pairs:
            if formula is None:
                source_key = str(row.get("source_key") or key)
                source_value = values.get((source_key, period, scenario))
                if source_value is None:
                    raise ValueError(
                        f"Missing value for {source_key}, {period}, {scenario}."
                    )
                row_values[(period, scenario)] = source_value
                continue
            total = 0.0
            for term in formula:
                ref = str(term["row"])
                factor = float(term.get("factor", 1))
                total += factor * resolved_by_key[ref][(period, scenario)]
            row_values[(period, scenario)] = total
        resolved_by_key[key] = row_values
        output_rows.append(
            {
                "key": key,
                "label": str(row["label"]),
                "position": position,
                "level": int(row.get("level") or 0),
                "line_type": str(row.get("line_type") or "detail"),
                "prefix": str(row.get("prefix") or ""),
                "values": {
                    f"{period}_{scenario}": row_values[(period, scenario)]
                    for period, scenario in pairs
                },
            }
        )
    return output_rows


def _json_dump(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _format_value(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 0.05:
        return f"{int(rounded):,}".replace(",", " ")
    return f"{value:,.1f}".replace(",", " ")


def _write_table_csv(
    rows: list[dict[str, Any]],
    recipe: dict[str, Any],
    path: Path,
) -> None:
    pairs = _period_scenario_pairs(recipe)
    value_columns = [f"{period}_{scenario}" for period, scenario in pairs]
    fieldnames = [
        "key",
        "label",
        "position",
        "level",
        "line_type",
        "prefix",
        *value_columns,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "key": row["key"],
                    "label": row["label"],
                    "position": row["position"],
                    "level": row["level"],
                    "line_type": row["line_type"],
                    "prefix": row["prefix"],
                    **row["values"],
                }
            )


def _scenario_bar_class(scenario: str) -> str:
    compact = scenario.lower()
    if compact in {"ac", "act", "actual"}:
        return "actual"
    if compact in {"fc", "forecast"}:
        return "forecast"
    return "plan"


def _render_html(
    rows: list[dict[str, Any]], recipe: dict[str, Any], source_name: str
) -> str:
    periods = [str(item) for item in recipe["periods"]]
    scenarios_by_period = recipe["scenarios_by_period"]
    pairs = _period_scenario_pairs(recipe)
    period_header = "".join(
        f'<th class="period" colspan="{len(scenarios_by_period[period])}">{escape(period)}</th>'
        for period in periods
    )
    scenario_header = "".join(
        (
            f'<th class="scenario {escape(_scenario_bar_class(scenario))}">'
            f"<span>{escape(scenario)}</span></th>"
        )
        for _period, scenario in pairs
    )
    body_rows: list[str] = []
    for row in rows:
        classes = ["statement-row", row["line_type"]]
        if row["level"] > 0:
            classes.append("indented")
        label = f"{row['prefix']} {row['label']}".strip()
        value_cells = "".join(
            f'<td class="num">{escape(_format_value(float(row["values"][f"{period}_{scenario}"])))}</td>'
            for period, scenario in pairs
        )
        body_rows.append(
            f'<tr class="{" ".join(classes)}">'
            f'<td class="label">{escape(label)}</td>'
            f"{value_cells}</tr>"
        )
    statement_line = f"{recipe['statement_label']} in {recipe['unit']}"
    title_lines = _title_contract_lines(recipe)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(str(recipe['title']))} - {escape(str(recipe['statement_label']))}</title>
<style>
:root {{
  --ink: #111;
  --muted: #4b5563;
  --rule: #d3d3d3;
  --heavy: #111;
  --plan: #9a9a9a;
  --actual: #111;
  --forecast: #777;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: #fff;
  color: var(--ink);
  font-family: Arial, Helvetica, sans-serif;
}}
.page {{
  width: 1120px;
  padding: 30px 32px 24px;
  background: #fff;
}}
.title {{
  margin-bottom: 22px;
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
  font-size: 12px;
}}
thead th {{
  padding: 4px 5px;
  color: var(--ink);
  font-weight: 700;
  text-align: right;
}}
thead .blank {{
  width: 250px;
}}
thead .period {{
  border-bottom: 2px solid var(--heavy);
  font-size: 12px;
}}
thead .scenario {{
  border-bottom: 1px solid var(--heavy);
  font-weight: 400;
  position: relative;
}}
thead .scenario span::after {{
  content: "";
  display: block;
  height: 5px;
  margin-top: 3px;
}}
thead .scenario.plan span::after {{ background: var(--plan); }}
thead .scenario.actual span::after {{ background: var(--actual); }}
thead .scenario.forecast span::after {{
  background: repeating-linear-gradient(
    135deg,
    var(--forecast) 0,
    var(--forecast) 2px,
    transparent 2px,
    transparent 4px
  );
  border: 1px solid var(--forecast);
}}
tbody td {{
  padding: 4px 6px;
  border-bottom: 1px solid var(--rule);
  height: 24px;
  vertical-align: middle;
}}
tbody .label {{
  width: 250px;
  text-align: left;
}}
tbody .indented .label {{
  padding-left: 24px;
}}
tbody .num {{
  text-align: right;
  font-variant-numeric: tabular-nums;
}}
tbody .subtotal td,
tbody .total td {{
  border-top: 2px solid var(--heavy);
  font-weight: 700;
}}
tbody .total td {{
  border-bottom: 3px solid var(--heavy);
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
    <p>{escape(title_lines[0])}</p>
    <p class="metric">{escape(title_lines[1])}</p>
    <p>{escape(title_lines[2])}</p>
    <div class="title-rule"></div>
  </header>
  <table>
    <thead>
      <tr><th class="blank"></th>{period_header}</tr>
      <tr><th class="blank"></th>{scenario_header}</tr>
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


def _title_contract_lines(recipe: dict[str, Any]) -> list[str]:
    """Return the visible three-row title contract for the statement table."""

    return [
        str(recipe["title"]),
        f"{recipe['statement_label']} in {recipe['unit']}",
        str(recipe["scope_label"]),
    ]


def _build_context(
    rows: list[dict[str, Any]],
    recipe: dict[str, Any],
    source_file: Path,
) -> dict[str, Any]:
    title_lines = _title_contract_lines(recipe)
    return {
        "schema_version": "1.0",
        "analysis_type": "pnl_statement_table",
        "object_type": "table",
        "capability_id": CAPABILITY_ID,
        "table_key": TABLE_KEY,
        "table_spec_name": TABLE_SPEC_NAME,
        "statement_label": recipe["statement_label"],
        "unit": recipe["unit"],
        "title": recipe["title"],
        "scope_label": recipe["scope_label"],
        "source_file": source_file.name,
        "periods": recipe["periods"],
        "scenarios_by_period": recipe["scenarios_by_period"],
        "chart_title_lines": title_lines,
        "chart_title": " / ".join(title_lines),
        "title_contract": {
            "who": title_lines[0],
            "what": title_lines[1],
            "when": title_lines[2],
        },
        "row_grain": "One row per ordered P&L statement line; formula rows are computed from prior rows in the recipe.",
        "statement_rows": recipe["statement_rows"],
        "table_rows": rows,
    }


def _build_manifest(
    output_dir: Path,
    source_file: Path,
    recipe: dict[str, Any],
) -> dict[str, Any]:
    resolved_parameters = {
        "source_file": source_file.name,
        "statement_rows": recipe["statement_rows"],
        "periods": recipe["periods"],
        "scenarios_by_period": recipe["scenarios_by_period"],
        "statement_label": recipe["statement_label"],
        "unit": recipe["unit"],
        "scope_label": recipe["scope_label"],
    }
    return {
        "schema_version": "1.0",
        "producer": {"plugin": "statement-analysis", "capability_id": CAPABILITY_ID},
        "artifacts": [
            {
                "artifact_id": TABLE_KEY,
                "kind": "tables",
                "artifact_type": "table",
                "capability_id": CAPABILITY_ID,
                "table_key": TABLE_KEY,
                "table_spec_name": TABLE_SPEC_NAME,
                "path": "pnl_statement_table.html",
                "source_path": "pnl_statement_table.html",
                "data_path": "pnl_statement_table_chart_data.csv",
                "context_path": "pnl_statement_table_chart_context.json",
                "resolved_parameters": resolved_parameters,
            },
            {
                "artifact_id": "context",
                "kind": "contexts",
                "artifact_type": "context",
                "path": "pnl_statement_table_chart_context.json",
            },
        ],
        "output_dir": output_dir.name,
    }


def run_statement_analysis(
    source_file: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    language: str = "en",
) -> StatementRunResult:
    """Run a deterministic P&L statement table and write artifacts."""

    recipe = load_recipe(recipe_path)
    recipe["language"] = language
    values = _read_values(source_file, recipe)
    rows = resolve_statement_rows(values, recipe)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "pnl_statement_table.html"
    csv_path = output_dir / "pnl_statement_table_chart_data.csv"
    context_path = output_dir / "pnl_statement_table_chart_context.json"
    manifest_path = output_dir / "artifact_manifest.json"
    final_artifacts_path = output_dir / "final_artifacts.json"
    recipe_output_path = output_dir / "used_recipe.json"

    _write_table_csv(rows, recipe, csv_path)
    html_path.write_text(
        _render_html(rows, recipe, source_file.name),
        encoding="utf-8",
    )
    _json_dump(recipe, recipe_output_path)
    context = _build_context(rows, recipe, source_file)
    _json_dump(context, context_path)
    manifest = _build_manifest(output_dir, source_file, recipe)
    _json_dump(manifest, manifest_path)
    _json_dump(
        {
            "schema_version": "1.0",
            "plugin": "statement-analysis",
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
    return StatementRunResult(
        output_dir=output_dir,
        html_path=html_path,
        csv_path=csv_path,
        context_path=context_path,
        manifest_path=manifest_path,
        final_artifacts_path=final_artifacts_path,
        rows=rows,
        context=context,
        manifest=manifest,
    )
