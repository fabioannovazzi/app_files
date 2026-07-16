---
name: variance-analysis
description: Use when a user wants Codex to inspect a sales CSV/XLSX file, map periods and metrics, run sales variance, price-volume-mix, net sales and margin analysis, and interpret the resulting source data.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Variance Analysis

Use this skill when a sales or revenue dataset needs period-over-period variance analysis. The plugin is a guided Codex workflow: Codex inspects the file, confirms unresolved mappings, runs deterministic helper scripts, reviews diagnostics, and explains the largest business drivers.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify only material choices that cannot be inferred from the file: ambiguous comparison basis, baseline and comparison periods, period column, amount column, units column, reporting dimensions, calculation grain, output folder, and working language. Root-cause variance, the alternative sweep, automatic drilldowns, standard waterfall output, charts, audit files, diagnostics, model-context files, and client-ready Word report outputs are default behavior; do not ask the user whether to enable them. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named variance modes, business dimensions, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of this plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

The plugin has two host-mode behaviors:

- Default mode is the normal starting point. Inspect the file, state the inferred defaults, and continue only when material assumptions are either obvious or confirmed. If a material choice is unresolved, state the proposed default and say that the user can switch this chat to Plan mode to change it with structured choices. The user may also answer in chat; if they do, use that answer and continue.
- Plan mode is the structured-intake lane. When `request_user_input` is available and a material discrete choice is unresolved, use the native widget instead of a textual multiple-choice list. Put the recommended option first, mark it as the default, and show only the most relevant 2-3 options; the host-provided custom or free-form path covers anything outside the listed choices.

The plugin must never claim that it switched modes itself. Mode transitions are host/user controlled. Codex may ask the user to switch to Plan mode for structured intake, but it cannot programmatically enter or leave that mode.

Good Plan-mode widget choices for this plugin are:

- comparison basis: scenario comparison, period comparison, or custom comparison;
- period comparison style when the basis is period: calendar period, year-to-date, or rolling period;
- reporting view: the most relevant dimensional rollups detected in the file;
- PVM calculation grain: product/customer-level grain, product-level grain, or reporting-level grain.

Do not use Plan mode to ask whether to produce DOCX, audit, diagnostics, charts,
root-cause outputs, sweep outputs, or drilldowns. Those are normal outputs of
the run when the mapped data and dependencies support them.

Use Codex-native UI artifacts as part of the workflow:

1. Start with a visible markdown checklist covering intake, dependency check, inspection, user decisions, deterministic run, Codex interpretation, and delivery.
2. Before helper scripts, show a Run Intake table with input path, output folder, working language, assumed mappings, and note that root-cause sweep and client report outputs run automatically.
3. After inspection, show a compact Decision Table for missing or low-confidence mappings and ask only unresolved decisions.
4. Before a long-running or write-heavy step, show an execution checkpoint or approval checkpoint with command intent, input, output folder, and expected artifacts. Ask for approval only when the step is external, destructive, approval-sensitive, or still depends on an unresolved material choice.
5. End with an Artifact Card listing output paths, review status, unresolved caveats, and next action.
6. For every completed run, create a Codex narrative review in the output folder from generated JSON/CSV/Markdown outputs; never edit plugin source or generated ZIPs during a run.

## Core Principle

The vendored legacy Mparanza code owns period splitting, aggregation, bottom-up price/volume/mix arithmetic, net-of-discount and margin period totals, and Plotly waterfall draw/title/layout rendering. The plugin adapter owns file parsing, schema inspection, mapping user columns into legacy canonical names, and CSV/XLSX/JSON/Markdown/PNG exports.

Codex owns judgment: deciding ambiguous mappings with the user, interpreting the largest drivers, explaining caveats, and writing business-language commentary. The plugin scripts must not make direct OpenAI API calls. The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

Deterministic logic is appropriate here because variance arithmetic and component reconciliation are mechanically verifiable and auditable. Do not reimplement the legacy period split, variance formula, or mix calculation when the vendored legacy module can be called. Do not use deterministic rules to infer semantic business causes beyond the measured columns; Codex should make those interpretations explicitly from the source data.

## Legacy Chart Plugin Pattern

Use the same architecture when extending this plugin or creating related chart-family plugins from the legacy code:

1. Reuse the legacy data-preparation/calculation layer as the source of truth. Keep period splitting, period comparison windows, pivots, aggregation, top/Other logic, variance arithmetic, and chart-family-specific preparation in the vendored modules unless a narrow Polars port is required.
2. Reuse the legacy chart-generation layer for each chart family where it works. The plugin may adapt titles, colors, export paths, audit metadata, and headless rendering, but it must not recode chart semantics such as period comparison, hierarchy handling, pinheads, scale sharing, or small-multiple panel construction.
3. Add a modern Codex interpretation/report layer on top of the deterministic artifacts. Codex should review generated chart context, CSV/JSON source data, sweep outputs, and audit files before looking at chart images, then decide which findings are business-relevant and write the client-facing narrative.
4. Treat small multiples as a normal output for chart families that support them. Do not ask whether to run small multiples when a useful dimension can be inferred; generate the main chart and supporting small-multiple chart(s), keep scale comparable where the legacy chart requires it, include their context files in the source package, and have Codex comment on them when they materially support or challenge the main read.
5. Split future chart plugins by business chart family, not by old file names. For example, legacy `multitierColumnChart` belongs with period-comparison/year-over-year charts because it is the legacy "year-over-year column" chart and shares period comparison prep. Legacy `multitierBarChart` belongs with composition/hierarchy charts because it pivots one business dimension by another and applies top/Other composition logic.

The default stance for these chart-family plugins is the same as Variance Analysis: infer what can be inferred, ask only for material missing mappings, generate the richest normal chart/report package, and use Codex to interpret the source data rather than making users inspect every technical chart variant manually.

Legacy includes both the analysis/calculation path and the Plotly rendering path.
The model-facing source of truth is the prepared numbers and contexts, not the
PNG. Use rendered charts for client communication and visual QA after the
structured source data has been interpreted.

## Codex Analysis Requirement

Do not finish a successful run with only deterministic tables and audit files. Write `codex_business_analysis.md` or a clearly named equivalent in the output folder. The analysis should state the business conclusion, quantify the largest drivers, explain whether the result is a price, volume, mix, discount, COGS, or margin story, and call out why surprising outputs such as zero volume/mix are or are not supported by the source data. When `waterfall_small_multiples_context.json` exists, the analysis must use it to explain whether the standard variance story is concentrated in a few members of the selected dimension or spread across several panels, and which variance type dominates the largest panels.

Every successful variance run writes structured source-data files directly in
the run directory. Codex should read `standard_variance_context.json`,
`pvm_decomposition_ladder_context.json`, root-cause context files, CSV/XLSX
tables, and audits before writing a client-facing report.

Every successful variance run also writes the local UI handoff files
`variance/run_intake.json`, `variance/review_payload.json`,
`variance/ui_decisions.json`, and `variance/final_artifacts.json`. Treat
`review_payload.json` as the bounded OpenAI-style payload for the local MCP
widget. It contains variance-driver rows, chart artifacts, context artifacts,
follow-up requests, and generated report artifacts for review.

The narrative must distinguish deterministic facts from interpretation. Use the file's known labels and units only; if the workbook does not provide currency, use `EUR` as the default assumption. If unit of measure, customer segment definitions, or product hierarchy meaning are missing, say so rather than inventing context.

## Root-Cause Alternative Sweep

Root-cause variance is a sequential residual bridge, not a normal pivot-table decomposition. There can be several valid bridges for the same file because `options.root_cause_bridge_alternative_result` changes the starting ranked candidate. Treat these as alternative explanations, not as one single automatic truth.

Every variance run enables root-cause variance when the mapped data has enough dimensions. The alternative sweep is not optional: run `alternativeResult` values `1..10` in one deterministic plugin run. For large files this may take time; that is acceptable because the plugin is expected to produce the most complete analysis rather than ask the user to choose technical modes. Use `--no-waterfall-chart` only for explicit debug runs where the normal waterfall is not useful.

The sweep writes `root_cause_bridge_alt_<n>.csv`, `root_cause_bridge_alt_<n>.png`, `root_cause_sweep_summary.csv`, `root_cause_sweep_summary.json`, `root_cause_sweep_model_context.json`, `root_cause_sweep_interpretation_brief.md`, and a client-ready Word package: `root_cause_client_report.md` and `root_cause_client_report.docx`. Review the model context, interpretation brief, generated charts, and client report before writing any extra business interpretation.

For each alternative, review the sweep context and build a commentary with:

- alternative number;
- selected row count;
- selected row labels and amounts;
- selected `bridge_dimensions` sequence;
- whether `selected_sequence_has_mixed_dimensions` is true;
- residual/Other size and reconciliation status;
- a short Codex interpretation of whether the bridge is business-readable.

Interpret every selected row as a residual after previous selected rows. If row 1 is `Product A` and row 2 is `Australia`, row 2 does not mean total Australia variance; it means the remaining Australia-related residual after the variance already attributed to `Product A` has been removed. Say this explicitly when mixed-dimension rows could be misunderstood.

A bridge is genuinely variable-dimension only when the selected sequence contains more than one distinct `bridge_dimensions` value. Same-dimension alternatives and drilldowns can still be useful, but do not describe them as mixed variable-dimension bridges.

The model/Codex role is to compare the deterministic alternatives, identify which are interesting or misleading, explain the residual logic in business language, and recommend which alternatives deserve drilldown. Do not change the calculated sequence or fabricate rows that are not present in the generated CSV/audit outputs.

After every successful sweep, write `codex_root_cause_sweep_analysis.md` in the variance output folder. It must include: executive read, deterministic facts, useful alternatives, misleading/noisy alternatives, residual logic explanation, recommended drilldowns, and caveats. Use the generated interpretation brief as the checklist.

Automatic sweep drilldown defaults to every selected row (`all_selected`) so the report has the detail needed to support the conclusion. The deterministic output still comes from the legacy detail/snapshot frames.

## Inputs

Required:

- a `.csv`, `.tsv`, `.psv`, `.xlsx`, or `.xlsm` sales dataset.

Optional:

- mapping hints for period, baseline period, comparison period, amount/sales, units, discount, COGS, and dimensions;
- calculation grain hints when mix should be calculated bottom-up below the reporting dimensions;
- working language: `it`, `en`, `fr`, or `de`;
- root-cause variance analysis runs by default when dimensions support it.

## Known Scenario Codes

When an input has a `Scenario` column with exactly `PL` and `AC`, treat `PL` as Plan and `AC` as Actual. The default comparison is Actual vs Plan, so keep `PL` as the baseline period and `AC` as the comparison period unless the user chooses otherwise. This is a deterministic project convention, not a semantic inference about arbitrary scenario labels.

## Comparison Basis And Period Styles

Do not collapse all comparisons into a generic "period" choice. First distinguish whether the run compares scenarios or periods:

- Scenario comparison: Plan vs Actual, Forecast vs Actual, Budget vs Actual, or similar scenario labels. For `PL`/`AC`, default to `PL` baseline and `AC` comparison.
- Calendar period comparison: complete comparable calendar or fiscal buckets, such as 2024 vs 2025, Q1 vs Q2, or January 2025 vs January 2026.
- Year-to-date comparison: cumulative windows from the start of a fiscal/calendar year to an explicit cutoff date. Confirm the cutoff and the prior-year comparable window before running.
- Rolling period comparison: trailing windows such as last 13 weeks, rolling 3 months, or last 12 months. Confirm window length and whether the comparison is previous rolling window or prior-year equivalent.
- Custom comparison: any user-specified baseline and comparison filters.

For year-to-date and rolling periods, the plugin prepares a synthetic two-bucket period column before running variance. It uses the vendored legacy helpers to identify the most recent date and preserve legacy YTD/rolling labels, then records exact date boundaries in `used_recipe.json`, `variance_audit.json`, and `variance_summary.md`. If the date column is missing or cannot be parsed, stop and ask for the date mapping or prepared buckets.

## First Run Workflow

1. Ask for the input file and output folder only when not already clear.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it, or explain what dependency capability is missing.
If `check_dependencies.py` reports `OPTIONAL_EXPORT_FALLBACK` for Plotly/Kaleido,
continue: the plugin has a supported Pillow PNG renderer and records the
fallback in chart audit metadata.

3. Run deterministic inspection:

```bash
python scripts/inspect_inputs.py <input-file> --output-dir <output-dir> --language <it|en|fr|de>
```

4. Read `inspection.json` and `suggested_recipe.json`. Summarize columns, periods, suggested mappings, warnings, comparison basis, period comparison style, and missing required choices.
5. If a mapping or comparison decision is needed, ask the smallest business question and update the recipe JSON in the work folder yourself.
6. Run deterministic variance:

```bash
python scripts/run_variance.py <input-file> --output-dir <output-dir>/variance --recipe <output-dir>/suggested_recipe.json
```

When chart images are not needed, use the structured data-only mode:

```bash
python scripts/run_variance.py <input-file> --output-dir <output-dir>/variance_data --recipe <output-dir>/suggested_recipe.json --artifact-mode data_only
```

The run writes `waterfall.png`, `pvm_decomposition_ladder.png`, root-cause outputs, and `waterfall_small_multiples.png` by default when the standard variance has a useful reporting dimension. When at least two dimensions are mapped it can also write `exploded_variance_bridge.png` plus `exploded_variance_bridge_spec.json`, `exploded_variance_bridge_chart_data.json`, and `exploded_variance_bridge_context.json`; use the JSON spec/context as the native artifact payload and the PNG as the slide fallback. It also writes `pvm_decomposition_ladder.csv`, `pvm_decomposition_ladder_context.json`, `waterfall_small_multiples_summary.csv`, and `waterfall_small_multiples_context.json` so Codex can interpret the analysis from data rather than chart pixels. The PVM ladder uses the legacy different-calculations waterfall pattern: the same total movement is shown as combined Price & Units & Mix, then Price plus Units & Mix, then Price / Units / Mix separately, with the legacy `Δ%` total movement label retained. The small-multiples chart uses the legacy fixed-dimension variance pattern: each panel repeats the compact Price / Units & Mix / Balance bridge for one selected member of the chosen dimension. The dimension is only the panel split, never the row structure inside a standard-variance small multiple. Add `--waterfall-small-multiples` only to force small multiples for a non-default reporting dimension. Add `--no-waterfall-chart` only for explicit debug/table-only runs.

Chart colors follow the project role-color convention: Plan/Budget/Forecast opening totals are white with a dark outline, prior-period opening totals are grey, Actual/current closing totals are black, positive drivers are green, and negative drivers are red. Reject or regenerate charts that show `PL` as a grey total bar.

7. Review `variance_results.csv`, `variance_audit.json`, `variance_summary.md`, `standard_variance_context.json`, `pvm_decomposition_ladder_context.json`, `exploded_variance_bridge_context.json`, root-cause context files, and small-multiple context/summary files before looking at chart images. Interpret the largest absolute drivers, explain which components reconcile to total delta, explain what changes across PVM calculation depths, explain concentration/spread across small-multiple panels when available, and call out missing mappings or zero-denominator caveats from structured source data. Inspect `waterfall.png`, `pvm_decomposition_ladder.png`, `exploded_variance_bridge.png`, root-cause PNGs, and `waterfall_small_multiples.png` afterward for visual fit; show only the charts that materially support the explanation.
8. Write `codex_business_analysis.md` in the run output folder. Include an executive read, driver narrative, small-multiples takeaways when available, caveats, and recommended follow-ups. Link it from `codex_run_review.md` when that file exists.

## MCP Review Handoff

After the deterministic run writes `variance/review_payload.json`, prefer the
local MCP widget when the `varianceAnalysisWidgets` server is available:

1. Read `variance/run_intake.json`, `variance/review_payload.json`,
   `variance/ui_decisions.json`, and `variance/final_artifacts.json`.
2. Call `validate_variance_analysis_review` with the review payload and optional
   intake/decision/final-artifact objects.
3. If validation succeeds, call `render_variance_analysis_review` with the same
   payload so Codex can show the HTML review widget.
4. Use `save_variance_analysis_decisions` to persist reviewer actions to
   `ui_decisions.json`, then `apply_variance_analysis_decisions` to write
   `applied_decisions.json` and update `final_artifacts.json` status.
5. If MCP rendering is unavailable, fall back to a concise Markdown/chat review
   based on `review_payload.json`; do not block the deterministic run.

Use the UI handoff to review the generated chart/report package. Continue to
write `codex_business_analysis.md` from the structured source pack and the
reviewed facts.

## Recipe Rules

Codex can edit `suggested_recipe.json` in the work folder. Use these fields:

- `language`: working/output language;
- `mappings.period_column`: column containing periods;
- `mappings.baseline_period`: first period in the comparison;
- `mappings.comparison_period`: second period in the comparison;
- `mappings.amount_column`: sales, revenue, or amount column;
- `mappings.units_column`: optional units/quantity/volume column for price-volume-mix analysis;
- `mappings.discount_column`: optional discount column for net variance;
- `mappings.cogs_column`: optional COGS/cost column for margin variance;
- `mappings.date_column`: date column used to prepare year-to-date or rolling comparison buckets;
- `mappings.dimensions`: reporting columns to group by;
- `mappings.calculation_grain`: lowest stable business grain passed into the legacy bottom-up price-volume-mix path; keep this at SKU/customer/SKU-customer level when those columns exist, and let `mappings.dimensions` be coarser when the user wants the legacy aggregation path used at category/customer/total level;
- `options.root_cause_bridge`: root-cause variance analysis, forced `true`;
- `options.root_cause_bridge_alternative_result`: legacy `alternativeResult`
  value from `1` to `10`, default `1`;
- `options.root_cause_bridge_drilldown_rows`: 1-based main bridge rows to
  drill down with legacy detail outputs, default `[]`;
- `options.root_cause_bridge_drilldown_all`: run legacy drilldown for every
  selected main bridge row, default `false`;
- `options.root_cause_bridge_move_rows`: mapping such as `{"1": [1, 2]}` to
  move selected drilldown rows back into the main bridge through legacy
  `insertAtRowDict`, default `{}`;
- `options.root_cause_bridge_alternative_sweep`: run alternatives in one
  deterministic root-cause sweep, forced `true`;
- `options.root_cause_bridge_alternative_sweep_start`: first sweep
  `alternativeResult`, default `1`;
- `options.root_cause_bridge_alternative_sweep_end`: final sweep
  `alternativeResult`, default `10`;
- `options.root_cause_bridge_auto_drilldown`: automatic drilldown mode for
  sweep alternatives: `none`, `single_row`, `dominant_row`, or `all_selected`,
  default `all_selected`;
- `options.root_cause_bridge_auto_drilldown_min_share`: minimum absolute
  variance share for `dominant_row`, default `0.75`;
- `options.waterfall_chart`: vendored legacy waterfall PNG output, default `true`.
- `options.pvm_decomposition_ladder`: legacy different-calculations Price /
  Units / Mix ladder, default `true` when units are mapped.
- `options.waterfall_small_multiples`: write `waterfall_small_multiples.png`
  as an additional standard component bridge repeated by dimension member,
  default `true` when a useful reporting dimension can be selected.
- `options.waterfall_small_multiples_dimension`: dimension column for the
  small-multiples waterfall, defaulting to an automatically selected reporting
  dimension when available.
- `options.exploded_variance_bridge`: one-page parent/child bridge with at
  most two drilldowns, default `true` when at least two dimensions are mapped.
- `options.exploded_variance_bridge_parent_dimension`: parent row dimension;
  defaults to the selected total-by-dimension bridge dimension.
- `options.exploded_variance_bridge_child_dimension`: child drilldown
  dimension; defaults to the first other mapped dimension.
- `options.exploded_variance_bridge_parent_top_n`: parent rows shown before
  aggregating remaining members as Other, default `8`.
- `options.exploded_variance_bridge_child_top_n`: child rows shown per
  drilldown before Other, default `5`.
- `options.exploded_variance_bridge_max_drilldowns`: maximum expanded parent
  rows, capped at `2`.
- `options.comparison_basis`: advisory comparison metadata, usually `scenario` or `period`;
- `options.period_comparison_mode`: advisory comparison metadata, usually `not_applicable`, `calendar_period`, `year_to_date`, `rolling_period`, or `custom`.
- `options.rolling_window_months`: rolling window length in months, default `12`;
- `options.rolling_comparison`: `prior_year` by default, or `previous_window` when the user asks for the immediately preceding window;
- `options.fiscal_start_month`: fiscal/calendar year start month for YTD, default `1`;
- `options.period_window`: generated audit metadata for prepared YTD/rolling windows. Codex should review it but not hand-edit it unless rerunning with explicit user choices.

Do not ask the user to edit JSON. Ask in business terms, then Codex updates the recipe and reruns deterministic scripts.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `variance/used_recipe.json`;
- `variance/variance_results.csv`;
- `variance/variance_results.xlsx` when XLSX dependencies are available;
- `variance/variance_audit.json`;
- `variance/variance_summary.md`;
- `variance/run_intake.json`;
- `variance/review_payload.json`;
- `variance/ui_decisions.json`;
- `variance/final_artifacts.json`;
- `variance/standard_variance_context.json`;
- `variance/pvm_decomposition_ladder_context.json` when units are mapped;
- `variance/waterfall.png`;
- `variance/pvm_decomposition_ladder.png`,
  `variance/pvm_decomposition_ladder.csv`, and
  `variance/pvm_decomposition_ladder_context.json` when units are mapped;
- `variance/waterfall_small_multiples.png` when the standard variance has a
  useful reporting dimension or small multiples are explicitly enabled;
- `variance/waterfall_small_multiples_summary.csv` and
  `variance/waterfall_small_multiples_context.json` when small multiples are
  enabled, including panel-level variance type amounts and Other handling;
- `variance/exploded_variance_bridge.png`,
  `variance/exploded_variance_bridge_spec.json`,
  `variance/exploded_variance_bridge_chart_data.json`, and
  `variance/exploded_variance_bridge_context.json` when at least two mapped
  dimensions support a parent/child drilldown;
- `codex_business_analysis.md` or equivalent Codex-written business interpretation;
- `variance/root_cause_bridge.csv` containing the selected legacy
  `process_node_combinations` sequence;
- `variance/root_cause_bridge_candidates.csv` containing the full
  legacy candidate universe;
- `variance/root_cause_bridge.png`;
- `variance_audit.json` records
  `legacy_runtime.variable_dimension_bridge.selected_sequence_bridge_dimensions`,
  `selected_sequence_unique_bridge_dimensions`, and
  `selected_sequence_has_mixed_dimensions`. Do not present a bridge as a
  variable-dimension example unless the selected sequence has more than one
  distinct `bridge_dimensions` value;
- `variance/root_cause_bridge_details.csv` and
  `variance/root_cause_bridge_snapshot.csv` when automatic or explicit legacy
  drilldown runs and details/snapshots are available;
- `variance/root_cause_bridge_drilldown_row_<n>.csv` and PNG files for
  requested legacy drilldown rows;
- `variance/root_cause_bridge_moved_rows.csv` and PNG when selected
  drilldown rows are moved back into the main bridge.
- `variance/root_cause_bridge_alt_<n>.csv` and PNG files,
  `variance/root_cause_sweep_summary.csv`,
  `variance/root_cause_sweep_summary.json`, and
  `variance/root_cause_sweep_model_context.json`,
  `variance/root_cause_sweep_interpretation_brief.md`,
  `variance/root_cause_client_report.md`,
  `variance/root_cause_client_report.docx`, and Codex-written
  `variance/codex_root_cause_sweep_analysis.md` when the mapped data supports
  root-cause analysis.

## Failure Modes

- If required mappings are missing after inspection, ask for those mappings before running variance.
- If a mapped metric column is non-numeric, stop and report the exact column and dtype.
- If one selected period has no rows, stop and ask the user to choose valid periods.
- If units are missing, run basic delta, net, and margin where possible, but do not claim price-volume-mix was computed.
- If deterministic results look surprising, do not override them silently; explain the caveat and suggest a follow-up inspection.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a missing column-mapping heuristic, unsupported file type, brittle period inference, unclear recipe field, needed fixture, output gap, installation friction, or repeated manual step.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts.
