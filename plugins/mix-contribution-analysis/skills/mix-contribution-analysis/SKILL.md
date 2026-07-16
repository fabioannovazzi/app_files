---
name: mix-contribution-analysis
description: Use when a user wants Codex to inspect a sales CSV/XLSX file, generate mix, composition, contribution, Mekko, Pareto, stacked, multitier and small-multiple charts, and interpret the patterns.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Mix & Contribution Analysis

Use this skill when a sales or revenue dataset needs composition, contribution
or mix charting: Mekko, BarMekko, stacked bar/column, share views, Pareto,
stacked Pareto, related-metrics bar charts with marker overlays, multitier
charts, and small multiples where the legacy chart supports them.

## Codex-Native Run UX

Ask only material choices that cannot be inferred from the actual input:
ambiguous amount column, date/period column, dimensions, output folder, and
working language. Chart families, small multiples, audit files, diagnostics,
source packs, and Word reports are default behavior; do not ask whether to
enable them. Ask only those unresolved choices in chat.
Base every inferred default on the actual inputs; do not introduce optional
questions unless the facts cue them.

Default currency policy: use Euro (`EUR`) unless the user or source file
explicitly states another currency.

Use a compact checklist while working: intake, dependency check, inspection,
unresolved mapping decisions, deterministic run, Codex interpretation, and
delivery.

Start with a short Run Intake table when the user has not already provided the
file, language, output folder, amount/date/period fields, or key dimensions.
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
The adapter owns file parsing, mapping user columns into legacy canonical names,
headless capture/export of vendored legacy Plotly figures, CSV/XLSX/JSON/
Markdown/DOCX outputs, and source-pack generation.

Do not silently redraw failed legacy charts with new code. If a legacy chart
fails because of compatibility or unsupported input shape, write the failure to
the audit and report the affected chart. This is intentional: the plugin is a
wrapper around the legacy charting library, not a new chart implementation.

Codex owns judgment: deciding ambiguous mappings with the user, interpreting
the largest contribution patterns, explaining caveats, and writing
business-language commentary. The plugin scripts must not make direct model API
calls.

Legacy includes both the composition/mix analysis-preparation path and the
Plotly rendering path. Codex should interpret the prepared numbers, context
JSON, tables, audits, and briefs first; chart PNG/HTML artifacts are selected
later for human communication and visual QA.

## Structured Outputs

Every run writes structured context and audit files in the run directory.
Interpretation must use those numbers first, before looking at PNG/HTML chart
artifacts. For synthesis-style stacked columns, this means exposing the
total and each dimension decomposition with item labels, values, shares, ranks,
and `Other` bucket metadata. For related-metrics bar charts, this means
exposing the primary metric, marker metric, rank, share of panel total,
aggregated `Other` rows, and notable combinations such as large declining
contributors or small fast-growing contributors.

Every successful run also writes the local UI handoff files
`mix_contribution/run_intake.json`, `mix_contribution/review_payload.json`,
`mix_contribution/ui_decisions.json`, and
`mix_contribution/final_artifacts.json`. Treat `review_payload.json` as the
bounded OpenAI-style payload for the local MCP widget. It contains contribution
driver rows, chart artifacts, context artifacts, follow-up requests, and
generated report artifacts for review.

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

4. Read `inspection.json` and `suggested_recipe.json`. Summarize mappings,
warnings, and only unresolved required choices.
5. If a mapping decision is needed, ask in business terms and update the recipe
JSON yourself.
6. Run deterministic mix/contribution analysis:

```bash
python scripts/run_mix_contribution.py <input-file> --output-dir <output-dir>/mix_contribution --recipe <output-dir>/suggested_recipe.json
```

When chart images are not needed, use the structured data-only mode:

```bash
python scripts/run_mix_contribution.py <input-file> --output-dir <output-dir>/mix_contribution_data --recipe <output-dir>/suggested_recipe.json --artifact-mode data_only
```

7. Review `mix_contribution_context.json`, tables,
   audit, and briefs before looking at chart images. Interpret the dominant contribution, share, Pareto
   and mix patterns from structured source data. Inspect chart PNG/HTML artifacts
   afterward to confirm visual fit for the final report.
8. If a separate run note is useful, write `codex_run_review.md`; it is not a
client deliverable.

## MCP Review Handoff

After the deterministic run writes `mix_contribution/review_payload.json`,
prefer the local MCP widget when the `mixContributionWidgets` server is
available:

1. Read `mix_contribution/run_intake.json`,
   `mix_contribution/review_payload.json`,
   `mix_contribution/ui_decisions.json`, and
   `mix_contribution/final_artifacts.json`.
2. Call `validate_mix_contribution_review` with the review payload and optional
   intake/decision/final-artifact objects.
3. If validation succeeds, call `render_mix_contribution_review` with the same
   payload so Codex can show the HTML review widget.
4. Use `save_mix_contribution_decisions` to persist reviewer actions to
   `ui_decisions.json`, then `apply_mix_contribution_decisions` to write
   `applied_decisions.json` and update `final_artifacts.json` status.
5. If MCP rendering is unavailable, fall back to a concise Markdown/chat review
   based on `review_payload.json`; do not block the deterministic run.

Use the UI handoff to review the generated chart/report package. Continue to
write the client interpretation from structured source data and reviewed facts.

## Recipe Rules

Codex can edit `suggested_recipe.json` in the work folder. Use these fields:

- `language`: working/output language;
- `mappings.amount_column`: sales, revenue or amount column;
- `mappings.date_column`: optional date column for trend-capable charts;
- `mappings.period_column`: optional scenario/period column;
- `mappings.dimensions`: reporting columns for composition and small multiples;
- `options.currency`: defaults to `EUR`;
- `options.charts`: complete supported chart list by default;
- `options.small_multiples`: on when a useful dimension can be inferred;
- `options.max_chart_items`: top items before legacy Other aggregation.

Do not ask the user to edit JSON.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `mix_contribution/used_recipe.json`;
- `mix_contribution/mix_contribution_canonical.csv`;
- `mix_contribution/mix_contribution_summary.csv`;
- `mix_contribution/mix_contribution_results.xlsx`;
- `mix_contribution/mix_contribution_context.json`;
- `mix_contribution/mix_contribution_audit.json`;
- `mix_contribution/mix_contribution_summary.md`;
- `mix_contribution/run_intake.json`;
- `mix_contribution/review_payload.json`;
- `mix_contribution/ui_decisions.json`;
- `mix_contribution/final_artifacts.json`;
- legacy chart PNGs where legacy rendering succeeds;
- `mix_contribution/mix_contribution_client_report.md`;
- `mix_contribution/mix_contribution_client_report.docx`.

## Failure Modes

- If the amount column is missing or non-numeric, stop and ask for the correct
  amount field.
- If no useful dimension exists, report the blocker; composition charts need at
  least one business dimension.
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
