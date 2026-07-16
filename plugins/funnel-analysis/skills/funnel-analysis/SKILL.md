---
name: funnel-analysis
description: Use when a user wants Codex to turn a CSV plus explicit ordered stages into a deterministic funnel-stage reporting table with start, pass, drop-off, stage conversion, cumulative conversion, context JSON, and artifact manifest.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or any GitHub Pages/static-site folder unless the task is
explicitly plugin packaging/release. For user-data runs, choose an output
directory outside the repo, preferably a sibling `output/funnel-analysis` folder
next to the user-provided input folder, and pass that path to every
`--output-dir` or `--out` argument. If a script has a safe default next to the
input folder, use that default instead of inventing `out/...` under the repo.

# Funnel Analysis

Use this skill when rows must be evaluated through an ordered funnel, readiness
pipeline, stage gate, or statement-like sequence. The plugin is deterministic:
Codex supplies explicit material choices, then the scripts evaluate predicates,
write a compact reporting table, and record the source artifact contract. The plugin
scripts must not make direct model API calls.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify only material
choices that cannot be inferred from the actual inputs: input file, output
folder, stage definitions, predicate columns, title/unit labels, and working
language. The funnel table, CSV, context JSON, manifest, used recipe, and
generated ZIPs during packaging are default behavior; they are not choices to
propose. Ask only those unresolved choices in chat and wait for the answer.
Generate choices from the actual inputs; do not offer chart modes, output
packages, or issue categories unless the facts cue them.

Default output policy: produce the normal deterministic package. CSV, HTML,
JSON context, manifest, and a concise Codex review note are not choices to
propose when they are natural outputs of this plugin. If required stage
definitions remain unresolved after inspection, ask only those unresolved
choices in chat.

Use Codex-native UI artifacts as part of the workflow:

1. Start with a visible checklist covering intake, dependency check, stage
   recipe, deterministic run, source review, and delivery.
2. Before helper scripts, show a Run Intake table with input path, output folder,
   working language, assumed stages, and expected artifacts.
3. After reading inputs, show a compact Decision Table for missing or ambiguous
   stage predicates and ask only unresolved decisions.
4. Before a long-running or write-heavy step, show an execution checkpoint or
   approval checkpoint with command intent, input, output folder, and expected
   artifacts. Ask for approval only when the step is external, destructive,
   approval-sensitive, or still depends on an unresolved material choice.
5. End with an Artifact Card listing output paths, review status, unresolved
   caveats, and next action.
6. If a run note is useful, write `codex_run_review.md`; do not edit plugin
   source or generated ZIPs during a user-data run.

## First Run Workflow

1. Ask for the input file and output folder only when not already clear.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the
environment allows it, or explain what dependency capability is missing.

3. Build or confirm a recipe with `stage_definitions`. Each stage has a
   `stage` label and a deterministic `predicate`; supported predicate types are
   `all`, `nonblank`, `any_nonblank`, `positive_number`, `equals`, and `in`.
4. Run the deterministic table:

```bash
python scripts/run_funnel_analysis.py <input-file> --output-dir <output-dir> --recipe <recipe.json>
```

5. Review `funnel_stage_table_chart_context.json`,
   `funnel_stage_table_chart_data.csv`, and `artifact_manifest.json` before
   looking at the rendered table.
6. Interpret where the funnel loses records, whether the sequence itself is
   defensible, and whether the table belongs in the report.

## Expected Outputs

- `used_recipe.json`;
- `funnel_stage_table.html`;
- `funnel_stage_table_chart_data.csv`;
- `funnel_stage_table_chart_context.json`;
- `final_artifacts.json`;
- `artifact_manifest.json`;
- optional `codex_run_review.md` for internal execution notes.

## Failure Modes

- If a predicate column is missing, stop and report the exact missing columns.
- If a predicate type is unsupported, stop and report the stage label and
  predicate type.
- If stage definitions are absent or not ordered, ask for the stage recipe
  before running.
- If the requested rows are ordinary sales entities, products, customers,
  regions, or time periods rather than sequential gates, use the period
  comparison table or chart plugins instead.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting
deliverables, briefly identify concrete improvements that would have made this
plugin run better. Base suggestions on the actual session, such as a missing
predicate helper, unclear recipe field, unsupported input type, output gap,
installation friction, or repeated manual step.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts.
