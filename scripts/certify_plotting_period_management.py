from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Sequence

__all__ = [
    "CERTIFICATION_CASES",
    "PLOTTING_PLUGINS",
    "CertificationCase",
    "CertificationResult",
    "main",
    "render_html",
    "run_case",
]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "runs" / "plotting_period_management_certificate.html"
DEFAULT_JSON_OUTPUT = ROOT / "runs" / "plotting_period_management_certificate.json"

PLOTTING_PLUGINS = (
    "variance-analysis",
    "period-comparison",
    "mix-contribution-analysis",
    "scatter-bubble-analysis",
    "distribution-analysis",
    "set-overlap-analysis",
)


@dataclass(frozen=True)
class CertificationCase:
    """One mechanically verifiable period-management requirement."""

    plugin: str
    capability: str
    requirement: str
    nodeids: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class CertificationResult:
    """Executed evidence for one certification case."""

    case: CertificationCase
    passed: bool
    command: tuple[str, ...]
    returncode: int
    duration_seconds: float
    stdout: str
    stderr: str


CERTIFICATION_CASES: tuple[CertificationCase, ...] = (
    CertificationCase(
        plugin="shared-period-contract",
        capability="Scenario roles and period contract",
        requirement=(
            "Shared harness exposes AC/PY/PL/FC roles and normalizes "
            "calendar, to-date, rolling, fiscal period types with "
            "year/quarter/month/week grains."
        ),
        nodeids=(
            "tests/plugins/test_chart_harness.py::test_available_analysis_context_exposes_time_and_scenario_choices",
            "tests/plugins/test_chart_harness.py::test_period_contract_detects_forecast_and_period_grains",
        ),
    ),
    CertificationCase(
        plugin="variance-analysis",
        capability="Scenario column semantics",
        requirement=(
            "Actual-vs-plan/forecast scenarios are treated as scenarios, "
            "while AC/PY labels remain period comparison labels."
        ),
        nodeids=(
            "tests/plugins/test_variance_analysis_plugin.py::test_variance_plugin_inspects_xlsx_dates_and_plan_actual_scenario",
            "tests/plugins/test_variance_analysis_plugin.py::test_variance_plugin_uses_forecast_as_scenario_baseline",
            "tests/plugins/test_variance_analysis_plugin.py::test_variance_plugin_does_not_treat_actual_prior_year_as_scenario",
        ),
    ),
    CertificationCase(
        plugin="variance-analysis",
        capability="To-date and fiscal windows",
        requirement=(
            "Variance period buckets support calendar YTD and fiscal "
            "year-to-date windows with auditable AC/PY labels."
        ),
        nodeids=(
            "tests/plugins/test_variance_analysis_plugin.py::test_variance_plugin_prepares_legacy_ytd_window_buckets",
            "tests/plugins/test_variance_analysis_plugin.py::test_variance_plugin_prepares_fiscal_ytd_window_buckets",
        ),
    ),
    CertificationCase(
        plugin="variance-analysis",
        capability="Rolling windows and grains",
        requirement=(
            "Rolling period requests accept period_type aliases and derive "
            "month/week window lengths from period_grain."
        ),
        nodeids=(
            "tests/plugins/test_variance_analysis_plugin.py::test_variance_plugin_prepares_legacy_rolling_window_buckets",
            "tests/plugins/test_variance_analysis_plugin.py::test_variance_plugin_accepts_period_type_rolling_alias",
            "tests/plugins/test_variance_analysis_plugin.py::test_variance_plugin_derives_rolling_week_window_from_period_grain",
        ),
    ),
    CertificationCase(
        plugin="period-comparison",
        capability="Calendar, rolling, fiscal windows",
        requirement=(
            "Period comparison prepares fiscal to-date, calendar month, "
            "and rolling quarter windows with correct AC/PY totals."
        ),
        nodeids=(
            "tests/plugins/test_period_comparison_plugin.py::test_prepare_canonical_frame_uses_fiscal_to_date_window",
            "tests/plugins/test_period_comparison_plugin.py::test_prepare_canonical_frame_uses_calendar_month_window",
            "tests/plugins/test_period_comparison_plugin.py::test_prepare_canonical_frame_derives_rolling_quarter_window",
        ),
    ),
    CertificationCase(
        plugin="period-comparison",
        capability="Full chart package period reuse",
        requirement=(
            "The complete period-comparison chart package uses one prepared "
            "period frame across standard and small-multiple charts."
        ),
        nodeids=(
            "tests/plugins/test_plotting_plugin_boundaries.py::test_period_comparison_prepares_once_and_reuses_canonical_frame",
        ),
    ),
    CertificationCase(
        plugin="mix-contribution-analysis",
        capability="Date-derived period windows",
        requirement=(
            "Mix/contribution handles YTD, calendar, rolling, quarter, "
            "week, and year-grain period selections for legacy chart adapters."
        ),
        nodeids=(
            "tests/plugins/test_mix_contribution_plugin.py::test_legacy_adapter_uses_ytd_for_incomplete_latest_year",
            "tests/plugins/test_mix_contribution_plugin.py::test_legacy_adapter_calendar_mode_excludes_partial_latest_year",
            "tests/plugins/test_mix_contribution_plugin.py::test_legacy_adapter_rolling_mode_uses_labelled_equal_windows",
            "tests/plugins/test_mix_contribution_plugin.py::test_legacy_adapter_keeps_quarter_grain_out_of_year_window",
            "tests/plugins/test_mix_contribution_plugin.py::test_legacy_adapter_uses_latest_date_for_current_week_grain",
            "tests/plugins/test_mix_contribution_plugin.py::test_prepare_canonical_frame_can_use_yearly_period_grain",
        ),
    ),
    CertificationCase(
        plugin="mix-contribution-analysis",
        capability="Scenario and forecast periods",
        requirement=(
            "Mix/contribution detects Scenario as the period axis and uses "
            "Forecast (FC) as a comparison period when available."
        ),
        nodeids=(
            "tests/plugins/test_mix_contribution_plugin.py::test_prepare_canonical_frame_derives_price_and_margin_percent",
            "tests/plugins/test_mix_contribution_plugin.py::test_stacked_column_spec_uses_forecast_comparison_period",
        ),
    ),
    CertificationCase(
        plugin="scatter-bubble-analysis",
        capability="Date-derived period types",
        requirement=(
            "Scatter/bubble derives rolling, to-date, calendar, and fiscal "
            "period labels from date-only inputs."
        ),
        nodeids=(
            "tests/plugins/test_scatter_bubble_plugin.py::test_legacy_derived_metrics_keep_derivation_in_legacy_inputs",
            "tests/plugins/test_scatter_bubble_plugin.py::test_prepare_canonical_frame_can_derive_fiscal_quarter_periods",
            "tests/plugins/test_scatter_bubble_plugin.py::test_prepare_canonical_frame_can_derive_calendar_month_periods",
            "tests/plugins/test_scatter_bubble_plugin.py::test_prepare_canonical_frame_can_derive_to_date_periods",
            "tests/plugins/test_scatter_bubble_plugin.py::test_prepare_canonical_frame_can_derive_rolling_week_periods",
        ),
    ),
    CertificationCase(
        plugin="distribution-analysis",
        capability="Date-derived period types",
        requirement=(
            "Distribution derives rolling, fiscal quarter, calendar month, "
            "and to-date period selections from date-only inputs."
        ),
        nodeids=(
            "tests/plugins/test_distribution_analysis_plugin.py::test_build_recipe_derives_two_rolling_periods_from_dates_without_period_column",
            "tests/plugins/test_distribution_analysis_plugin.py::test_build_recipe_can_derive_fiscal_quarters_from_dates_without_period_column",
            "tests/plugins/test_distribution_analysis_plugin.py::test_build_recipe_can_derive_calendar_months_from_dates_without_period_column",
            "tests/plugins/test_distribution_analysis_plugin.py::test_build_recipe_can_derive_to_date_periods_from_dates_without_period_column",
        ),
    ),
    CertificationCase(
        plugin="distribution-analysis",
        capability="Explicit period labels and chart specs",
        requirement=(
            "Distribution preserves explicit selected periods through chart "
            "spec generation and rendered source paths."
        ),
        nodeids=(
            "tests/plugins/test_distribution_analysis_plugin.py::test_build_chart_specs_includes_standard_and_small_multiples",
        ),
    ),
    CertificationCase(
        plugin="set-overlap-analysis",
        capability="Explicit period filtering",
        requirement=(
            "Set overlap applies selected_period when a period column exists "
            "and also supports no-period overlap analysis."
        ),
        nodeids=(
            "tests/plugins/test_set_overlap_analysis_plugin.py::test_build_overlap_tables_returns_exact_intersections",
            "tests/plugins/test_set_overlap_analysis_plugin.py::test_build_overlap_tables_aggregates_lower_ranked_sets_as_other",
            "tests/plugins/test_set_overlap_analysis_plugin.py::test_run_set_overlap_applies_filters_and_records_title_scope",
        ),
        notes=(
            "Set overlap is an explicit-label plugin; date-to-period derivation "
            "is not part of its current plotting contract."
        ),
    ),
)


def run_case(case: CertificationCase) -> CertificationResult:
    """Run one explicit pytest evidence group.

    This certification is deterministic because each case is a fixed pytest
    node-id list and pass/fail is taken directly from the pytest exit status.
    """

    command = (sys.executable, "-m", "pytest", "-q", *case.nodeids)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    duration = time.perf_counter() - started
    return CertificationResult(
        case=case,
        passed=completed.returncode == 0,
        command=command,
        returncode=completed.returncode,
        duration_seconds=duration,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _command_text(command: Sequence[str]) -> str:
    return " ".join(command)


def _summarize_output(text: str, *, max_lines: int = 20) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    head = lines[: max_lines // 2]
    tail = lines[-(max_lines // 2) :]
    return "\n".join([*head, "...", *tail])


def _result_payload(result: CertificationResult) -> dict[str, object]:
    payload = asdict(result)
    payload["command"] = list(result.command)
    payload["case"]["nodeids"] = list(result.case.nodeids)
    return payload


def render_html(
    results: Sequence[CertificationResult],
    *,
    generated_at: str | None = None,
) -> str:
    """Return a standalone HTML certification report."""

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    passed = all(result.passed for result in results)
    status_label = "PASSED" if passed else "FAILED"
    status_class = "pass" if passed else "fail"
    total_duration = sum(result.duration_seconds for result in results)
    plugin_names = list(PLOTTING_PLUGINS)
    covered_plugins = {
        result.case.plugin for result in results if result.case.plugin in plugin_names
    }
    missing_plugins = [
        plugin for plugin in plugin_names if plugin not in covered_plugins
    ]
    rows = []
    detail_sections = []
    for result in results:
        case = result.case
        row_class = "pass" if result.passed else "fail"
        nodeid_list = "<br>".join(escape(nodeid) for nodeid in case.nodeids)
        rows.append(
            "<tr>"
            f"<td>{escape(case.plugin)}</td>"
            f"<td>{escape(case.capability)}</td>"
            f"<td>{escape(case.requirement)}</td>"
            f"<td>{nodeid_list}</td>"
            f"<td class=\"{row_class}\">{'PASS' if result.passed else 'FAIL'}</td>"
            f"<td>{result.duration_seconds:.2f}s</td>"
            "</tr>"
        )
        output = _summarize_output(result.stdout + "\n" + result.stderr)
        notes_markup = (
            f"<p><strong>Note:</strong> {escape(case.notes)}</p>" if case.notes else ""
        )
        detail_sections.append(
            f'<section class="case-detail {row_class}">'
            f"<h3>{escape(case.plugin)} - {escape(case.capability)}</h3>"
            f"<p>{escape(case.requirement)}</p>"
            f"{notes_markup}"
            f"<p><strong>Status:</strong> {'PASS' if result.passed else 'FAIL'} "
            f"(exit {result.returncode}, {result.duration_seconds:.2f}s)</p>"
            f"<pre>{escape(_command_text(result.command))}</pre>"
            f"<pre>{escape(output)}</pre>"
            "</section>"
        )
    missing_markup = (
        '<p class="fail">Missing configured plotting plugins: '
        + ", ".join(escape(plugin) for plugin in missing_plugins)
        + "</p>"
        if missing_plugins
        else '<p class="pass">All configured plotting plugins have certification cases.</p>'
    )
    rows_markup = "\n".join(rows)
    details_markup = "\n".join(detail_sections)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Plotting Plugin Period Management Certificate</title>
  <style>
    :root {{
      --text: #1f2933;
      --muted: #5b6775;
      --line: #d8dee8;
      --pass: #0f766e;
      --pass-bg: #e7f7f4;
      --fail: #b42318;
      --fail-bg: #fff1f0;
      --panel: #ffffff;
      --page: #f6f8fb;
    }}
    body {{
      margin: 0;
      background: var(--page);
      color: var(--text);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header, main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }}
    header {{
      padding-top: 32px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.2;
    }}
    h2 {{
      margin-top: 28px;
      font-size: 18px;
    }}
    h3 {{
      margin: 0 0 8px;
      font-size: 15px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .metric, .case-detail {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .metric strong {{
      display: block;
      font-size: 24px;
    }}
    .muted {{
      color: var(--muted);
    }}
    .pass {{
      color: var(--pass);
      font-weight: 700;
    }}
    .fail {{
      color: var(--fail);
      font-weight: 700;
    }}
    .badge {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      font-weight: 800;
      letter-spacing: 0;
    }}
    .badge.pass {{
      background: var(--pass-bg);
    }}
    .badge.fail {{
      background: var(--fail-bg);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      text-align: left;
      vertical-align: top;
      padding: 10px;
      border-bottom: 1px solid var(--line);
    }}
    th {{
      background: #edf1f6;
      font-size: 12px;
      text-transform: uppercase;
      color: #3c4653;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: #111827;
      color: #f9fafb;
      border-radius: 6px;
      padding: 10px;
      overflow-x: auto;
      font-size: 12px;
    }}
    .case-detail {{
      margin-bottom: 12px;
    }}
    @media (max-width: 900px) {{
      .summary {{
        grid-template-columns: 1fr 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <p><span class="badge {status_class}">Certification {status_label}</span></p>
    <h1>Plotting Plugin Period Management Certificate</h1>
    <p class="muted">Generated at {escape(generated_at)} from explicit pytest evidence groups.</p>
    <div class="summary">
      <div class="metric"><span class="muted">Cases</span><strong>{len(results)}</strong></div>
      <div class="metric"><span class="muted">Passed</span><strong>{sum(1 for result in results if result.passed)}</strong></div>
      <div class="metric"><span class="muted">Plugins</span><strong>{len(covered_plugins)}/{len(plugin_names)}</strong></div>
      <div class="metric"><span class="muted">Runtime</span><strong>{total_duration:.1f}s</strong></div>
    </div>
  </header>
  <main>
    <h2>Scope</h2>
    <p>This certificate covers period management for the configured plotting plugins: {escape(", ".join(plugin_names))}. The shared period contract is included because these plugins rely on it for scenario roles and period type/grain normalization.</p>
    {missing_markup}
    <h2>Certification Matrix</h2>
    <table>
      <thead>
        <tr>
          <th>Plugin</th>
          <th>Capability</th>
          <th>Requirement</th>
          <th>Evidence tests</th>
          <th>Status</th>
          <th>Runtime</th>
        </tr>
      </thead>
      <tbody>
        {rows_markup}
      </tbody>
    </table>
    <h2>Command Evidence</h2>
    {details_markup}
  </main>
</body>
</html>
"""


def write_outputs(
    results: Sequence[CertificationResult],
    *,
    html_output: Path,
    json_output: Path,
) -> None:
    html_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    html_output.write_text(render_html(results), encoding="utf-8")
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": all(result.passed for result in results),
        "plotting_plugins": list(PLOTTING_PLUGINS),
        "results": [_result_payload(result) for result in results],
    }
    json_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Certify plotting plugin period-management coverage."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="HTML certificate output path.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help="JSON evidence output path.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    results = [run_case(case) for case in CERTIFICATION_CASES]
    write_outputs(results, html_output=args.output, json_output=args.json_output)
    html_path = args.output.resolve()
    json_path = args.json_output.resolve()
    if all(result.passed for result in results):
        print(f"[OK] Period management certificate written: {html_path}")
        print(f"[OK] JSON evidence written: {json_path}")
        return 0
    print(f"[FAIL] Period management certificate written: {html_path}")
    print(f"[FAIL] JSON evidence written: {json_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
