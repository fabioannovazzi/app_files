---
name: scatter-bubble-analysis
description: Use when a user wants Codex to inspect a CSV/XLSX file, generate legacy scatter and bubble charts, small multiples, and relationship/outlier source data.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Scatter & Bubble Analysis

Use this skill when a dataset needs scatter or bubble charting: x/y metric
relationships, dot labels, optional color dimensions, bubble-size metrics, and
small multiples where the legacy chart supports them.

## Codex-Native Run UX

Ask only material choices that cannot be inferred from the actual input:
ambiguous x metric, y metric, bubble-size metric, dot dimension, color
dimension, period/date column, output folder, and working language. Chart
families, small multiples, audit files, diagnostics, source packs, and Word
reports are default behavior; do not ask whether to enable them. Ask only those unresolved choices in chat. Base every inferred default on the actual inputs;
do not introduce optional questions unless the facts cue them.

Default currency policy: use Euro (`EUR`) unless the user or source file
explicitly states another currency.

Use a compact checklist while working: intake, dependency check, inspection,
unresolved mapping decisions, deterministic run, Codex interpretation, and
delivery.

Start with a short Run Intake table when the user has not already provided the
file, language, output folder, metrics, date/period fields, or key dimensions.
When a required mapping is ambiguous, use a Decision Table with the inferred
choice, source basis, and any material approval-sensitive step. Before a long or
write-heavy deterministic step, show an execution checkpoint with command
intent, input, output folder, and expected artifacts. The Default output policy
is: produce the rich package by default. DOCX reports, audit files,
diagnostics, source packs, chart PNGs, and generated ZIPs are not choices to propose
when they are natural outputs. End with an Artifact Card that links the main
report, source pack, audit, and any `codex_run_review.md` note.
Ask for explicit continuation or approval only when the next step is external,
destructive, approval-sensitive, or still depends on an unresolved material
decision. Do not ask the user to type a generic continuation word merely to
create ceremony.

## Core Principle

The vendored legacy Mparanza code owns chart preparation and chart semantics.
The adapter owns file parsing, mapping user columns into legacy chart
configuration, reusable prepared-data caching, headless capture/export of
vendored legacy Plotly figures, CSV/XLSX/JSON/Markdown/DOCX outputs, and
source-pack generation.

Do not silently redraw failed legacy charts with new code. If a legacy chart
fails because of compatibility or unsupported input shape, write the failure to
the audit and report the affected chart. This is intentional: the plugin is a
wrapper around the legacy charting library, not a new chart implementation.

Codex owns judgment: deciding ambiguous mappings with the user, interpreting
relationship and outlier patterns, explaining caveats, and writing
business-language commentary. The plugin scripts must not make direct model API
calls.

Legacy includes both the scatter/bubble preparation path and the Plotly
rendering path. Codex should interpret the prepared numbers, context JSON,
tables, audits, and briefs first; chart PNG/HTML artifacts are selected later
for human communication and visual QA.

## Bubble Semantics

The red total bubble is valid only when both plotted axis metrics are
non-additive, such as price, rate, ratio, percent, share, index, CWD,
distribution, coverage, or growth. Its bubble area represents the additive
bubble-size metric total, but its x/y coordinates are averages of the plotted
point coordinates. If either axis is summable, such as Units, Sales, Value,
Volume, Quantity, or Count, suppress the total bubble in normal and
small-multiple bubble charts.

Prefer bubble x/y axes that explain a relationship through non-additive metrics.
When a requested additive axis duplicates the bubble-size metric's business
scale, flag that caveat in the interpretation and consider a scatter or a
different axis metric.

## Structured Outputs

Every run writes structured context and audit files in the run directory.
Interpretation must use those numbers first, before looking at PNG/HTML chart
artifacts. For scatter and bubble charts, this means exposing x metric, y
metric, bubble-size metric, dot dimension, color dimension, panel dimension,
captured legacy chart data, draw-function invocations, and cache activity.

Every successful run also writes the local UI handoff files
`scatter_bubble/run_intake.json`, `scatter_bubble/review_payload.json`,
`scatter_bubble/ui_decisions.json`, and `scatter_bubble/final_artifacts.json`.
Treat `review_payload.json` as the bounded OpenAI-style payload for the local
MCP widget. It contains relationship driver rows, chart artifacts, context
artifacts, follow-up requests, and generated report artifacts for review.

## First Run Workflow

1. Ask for the input file and output folder only when not already clear.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the
environment allows it, or explain which dependency capability is missing.

3. Run deterministic inspection:

```bash
python scripts/inspect_inputs.py <input-file> --output-dir <output-dir> --language <it|en|fr|de>
```

4. Read `suggested_recipe.json`. Summarize mappings, warnings, and only
   unresolved required choices.
5. If a mapping decision is needed, ask in business terms and update the recipe
   JSON yourself.
6. Run deterministic scatter/bubble analysis:

```bash
python scripts/run_scatter_bubble.py <input-file> --output-dir <output-dir>/scatter_bubble --recipe <output-dir>/suggested_recipe.json
```

When chart images are not needed, use the structured data-only mode:

```bash
python scripts/run_scatter_bubble.py <input-file> --output-dir <output-dir>/scatter_bubble_data --recipe <output-dir>/suggested_recipe.json --artifact-mode data_only
```

7. Review `scatter_bubble_context.json`, tables, audit,
   and briefs before looking at chart images. Interpret the strongest relationships, outliers,
   bubble-size patterns and small-multiple differences from structured
   source data. Inspect chart PNG/HTML artifacts afterward to confirm
   visual fit for the final report.
8. If a separate run note is useful, write `codex_run_review.md`; it is not a
   client deliverable.

## MCP Review Handoff

After the deterministic run writes `scatter_bubble/review_payload.json`, prefer
the local MCP widget when the `scatterBubbleWidgets` server is available:

1. Read `scatter_bubble/run_intake.json`,
   `scatter_bubble/review_payload.json`,
   `scatter_bubble/ui_decisions.json`, and
   `scatter_bubble/final_artifacts.json`.
2. Call `validate_scatter_bubble_review` with the review payload and optional
   intake/decision/final-artifact objects.
3. If validation succeeds, call `render_scatter_bubble_review` with the same
   payload so Codex can show the HTML review widget.
4. Use `save_scatter_bubble_decisions` to persist reviewer actions to
   `ui_decisions.json`, then `apply_scatter_bubble_decisions` to write
   `applied_decisions.json` and update `final_artifacts.json` status.
5. If MCP rendering is unavailable, fall back to a concise Markdown/chat review
   based on `review_payload.json`; do not block the deterministic run.

Use the UI handoff to review the generated chart/report package. Continue to
write the client interpretation from structured source data and reviewed facts.

## Recipe Rules

Codex can edit `suggested_recipe.json` in the work folder. Use these fields:

- `language`: working/output language;
- `mappings.x_metric_column`: metric for the x-axis;
- `mappings.y_metric_column`: metric for the y-axis;
- `mappings.bubble_size_metric_column`: metric for bubble area;
- `mappings.dot_dimension`: item labels/dots;
- `mappings.color_dimension`: optional color grouping;
- `mappings.small_multiples_dimension`: optional panel grouping;
- `mappings.date_column`: optional date column for audit/title context;
- `mappings.period_column`: optional scenario/period column;
- `mappings.dimensions`: reporting columns for dots, color and panels;
- `options.currency`: defaults to `EUR`;
- `options.charts`: complete supported chart list by default;
- `options.small_multiples`: on when a useful dimension can be inferred;
- `options.max_chart_items`: top items before legacy Other aggregation.

Do not ask the user to edit JSON.

## Expected Outputs

- `suggested_recipe.json`;
- `scatter_bubble/used_recipe.json`;
- `scatter_bubble/scatter_bubble_canonical.csv`;
- `scatter_bubble/scatter_bubble_summary.csv`;
- `scatter_bubble/scatter_bubble_results.xlsx`;
- `scatter_bubble/scatter_bubble_context.json`;
- `scatter_bubble/scatter_bubble_audit.json`;
- `scatter_bubble/scatter_bubble_summary.md`;
- `scatter_bubble/run_intake.json`;
- `scatter_bubble/review_payload.json`;
- `scatter_bubble/ui_decisions.json`;
- `scatter_bubble/final_artifacts.json`;
- legacy chart PNGs or Plotly HTML where legacy rendering succeeds;
- `scatter_bubble/scatter_bubble_client_report.md`;
- `scatter_bubble/scatter_bubble_client_report.docx`;

## Failure Modes

- If fewer than two numeric metrics exist, stop and ask for the correct metric
  fields.
- If no useful dimension exists, report the blocker; scatter and bubble charts
  need at least one business dimension for labels.
- If a legacy chart fails, keep going with the remaining charts and record the
  failed chart, source function and error in the audit. Do not fabricate a
  replacement chart.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, briefly identify concrete
improvements that would have made this plugin run better. Base suggestions on
the actual session.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts.
