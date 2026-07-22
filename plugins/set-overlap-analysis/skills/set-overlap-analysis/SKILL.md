---
name: set-overlap-analysis
description: Use when a user wants Codex to inspect a CSV/XLSX file and produce deterministic Venn or UpSet overlap source data for items across sets such as retailers, brands, regions, channels, cohorts, or periods.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Set Overlap Analysis

Use this skill for Venn and UpSet overlap work. The plugin is narrow: it
creates deterministic set-membership source data and chart artifacts. It is not a
presentation/reporting layer and must not invent charts outside this plugin.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify only material choices
that cannot be inferred from the actual inputs: input file, output folder, item
column, set column, optional period column, explicit filters, and selected sets
when automatic selection is not appropriate. Ask for the small-multiple facet
column only when the requested output is faceted, such as category-level UpSet
panels. Ask only those unresolved choices in chat.
Do not offer chart modes, output packages, issue categories, or report formats
unless the facts cue them.

Default output policy: inspection, CSV source tables, JSON context, audit,
source pack, Venn/UpSet chart artifacts, and archive files are normal plugin
outputs and are not choices to propose.

Use Codex-native UI artifacts as part of a substantive run:

1. Start with a visible checklist covering intake, dependency check,
   inspection, unresolved decisions, deterministic run, interpretation, and
   delivery.
2. Before helper scripts, show a Run Intake table with input path, output
   folder, working language, assumed mappings, filters, selected sets, and note
   that chart outputs, CSV source tables, audit and source pack run automatically.
3. After inspection, show a compact Decision Table for missing or low-confidence
   mappings and ask only unresolved decisions.
4. Before a long-running or write-heavy step, show an execution checkpoint or
   approval checkpoint with command intent, input, output folder, and expected
   artifacts. Ask for approval only when the step is external, destructive,
   approval-sensitive, or still depends on an unresolved material choice.
5. End with an Artifact Card listing output paths, review status, unresolved
   caveats, and next action.
6. If a run note is useful, write `codex_run_review.md`; it is not a client
   deliverable. Do not edit generated ZIPs during a run.

## Operating Rules

- The scripts own data preparation, filtering, membership tables, intersection
  counts, and chart rendering.
- Codex owns mapping clarification and interpretation of the structured
  source data.
- Read `set_overlap_context.json` and the CSV tables before inspecting PNG or
  HTML artifacts.
- Venn is only valid for exactly two or three selected sets. Use UpSet for
  larger overlap structures.
- For UpSet, when automatic set selection is used, lower-ranked sets are
  collapsed into `Other rank >N` by default so high-cardinality set columns stay
  readable. For UpSet small multiples, rank sets per panel unless the task
  explicitly asks for global ranking.
- Filters define source scope. Preserve explicit recipe filters and report them
  in the interpretation.
- Generated chart artifacts must follow the reporting typography rule: use one
  visible font size across the title, value labels, axis labels, legends, and
  set/category labels. Create emphasis with position, spacing, line weight, and
  marks instead of larger title text.
- Do not brand charts by style standard in titles or commentary.

## Workflow

1. Identify the input file and output folder. If either is missing, ask only for
   that missing input.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If dependencies are missing, install from this plugin's `requirements.txt`
only when the environment allows installation. Otherwise report the missing
requirement.

3. Run deterministic inspection:

```bash
python scripts/inspect_inputs.py <input-file> --output-dir <output-dir> --language <en|it|fr|de|es>
```

4. Read `inspection.json` and `suggested_recipe.json`. Ask only for unresolved
   or clearly wrong mappings:
   - `mappings.item_column`
   - `mappings.set_column`
   - `mappings.period_column`
   - selected period or explicit set values when needed
5. Edit the recipe in the work folder yourself when the user answers.
6. Run deterministic overlap analysis:

```bash
python scripts/run_set_overlap.py <input-file> --output-dir <output-dir>/set_overlap --recipe <output-dir>/suggested_recipe.json
```

When chart images are not needed, use structured data-only mode:

```bash
python scripts/run_set_overlap.py <input-file> --output-dir <output-dir>/set_overlap_data --recipe <output-dir>/suggested_recipe.json --artifact-mode data_only
```

7. Interpret the run from:
   - `set_overlap/set_overlap_context.json`
   - `set_overlap/set_overlap_intersections.csv`
   - `set_overlap/set_overlap_set_summary.csv`
   - `set_overlap/set_overlap_pairs.csv`
8. Inspect `upset.png`, `upset.html`, or `venn.png` only as final visual QA.

## Expected Outputs

- `inspection.json`
- `suggested_recipe.json`
- `set_overlap/used_recipe.json`
- `set_overlap/set_overlap_canonical.csv`
- `set_overlap/set_overlap_ranked_canonical.csv`
- `set_overlap/set_overlap_set_summary.csv`
- `set_overlap/set_overlap_item_sets.csv`
- `set_overlap/set_overlap_intersections.csv`
- `set_overlap/set_overlap_pairs.csv`
- `set_overlap/set_overlap_context.json`
- `set_overlap/set_overlap_audit.json`
- `set_overlap/upset.html`
- `set_overlap/upset.png` when PNG export is available
- `set_overlap/upset_small_multiples.html` when requested
- `set_overlap/set_overlap_small_multiples_set_summary.csv` when requested
- `set_overlap/set_overlap_small_multiples_intersections.csv` when requested
- `set_overlap/venn.png` for two or three selected sets
- `set_overlap/run_intake.json`
- `set_overlap/review_payload.json`
- `set_overlap/ui_decisions.json`
- `set_overlap/final_artifacts.json`

## MCP Review UI

Use MCP/HTML for the generated overlap source-data review. Do not build HTML for
simple intake, item/set/period mapping, selected-set choice, or a 2-3 option
business decision; those remain chat choices in Default mode and native
Plan-mode choices when this conversation is in Plan mode and
`request_user_input` is available.

After the deterministic run writes `set_overlap/review_payload.json`, prefer
the local MCP path when available:

1. Read `set_overlap/run_intake.json`, `set_overlap/review_payload.json`,
   `set_overlap/ui_decisions.json`, and `set_overlap/final_artifacts.json`.
2. Call `validate_set_overlap_review` with the review payload and optional
   handoff JSON objects before rendering.
3. If validation succeeds, call `render_set_overlap_review` with the same
   payload objects so Codex can show the local HTML widget
   `ui://widget/set-overlap-review.html`.
4. Use the widget to review selected sets, exact intersections, pairwise
   overlaps, chart audits, `set_overlap_context.json`, CSV source tables, the
   source-pack manifest, and generated chart artifacts.
5. Use `save_set_overlap_decisions` to persist accepted/edited/rejected
   decisions to `set_overlap/ui_decisions.json`, then
   `apply_set_overlap_decisions` to write `applied_decisions.json` and update
   `final_artifacts.json` status before treating the overlap package as
   reviewed. If MCP decision tools are unavailable, use a fallback review file
   in the output folder.

If MCP rendering is unavailable, fall back to a markdown review summary from
`review_payload.json`, `set_overlap_context.json`,
`set_overlap_intersections.csv`, `set_overlap_pairs.csv`,
`set_overlap_set_summary.csv`, and `set_overlap_audit.json`.

## Failure Modes

- If the item or set mapping is missing, stop and ask for that mapping.
- If filters remove all rows, report the filter audit and do not fabricate
  source data.
- If more than three sets are selected, do not force a Venn chart. The Venn
  audit should record that Venn was skipped.
- If PNG export fails but HTML succeeds, report the PNG export limitation and
  keep the structured source data.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, briefly identify concrete
improvements that would have made this plugin run better. Base suggestions on
the actual session, such as a missing column-mapping heuristic, unsupported file
type, unclear recipe field, output gap, installation friction, or repeated
manual step.

Keep the improvement note local to chat or run artifacts.
