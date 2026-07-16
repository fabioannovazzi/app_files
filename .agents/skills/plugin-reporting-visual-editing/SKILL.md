---
name: plugin-reporting-visual-editing
description: Use when the user asks to inspect, improve, edit, or create plugin charts, tables, PNG gallery artifacts, reporting visuals, IBCS-style visuals, UniformChart-informed visuals, or any one-chart/all-chart visual quality workflow for generated plugin outputs.
---

# Plugin Reporting Visual Editing

Use this skill for generated plugin charts and reporting tables. The target is
always the user's generated artifact, not a generic template and not our "best"
existing example.

## Ground Rules

- The gallery contains only our generated outputs. Do not add IBCS or
  UniformChart examples to the gallery.
- IBCS and UniformChart are fixed visual references used during review. They are
  directional evidence, not automatic styling engines.
- For a chart-edit request, focus on the user's complaint first. Surface adjacent
  IBCS/reporting issues separately as suggestions.
- For IBCS-style reporting chart artifacts, enforce one visible font size across
  the whole chart: title, axis titles, tick labels, value labels, legends,
  captions, and category/set labels. Create hierarchy with position, spacing,
  weight, and marks instead of mixed font sizes.
- Unless the user has already asked to implement, stop after diagnosis and a
  scoped edit plan. Wait for approval before changing code.
- Do not imply IBCS certification, endorsement, or affiliation.

## Locate The Artifact

Use the review packet helper from the repo root:

```bash
source .venv/bin/activate
python scripts/prepare_reporting_visual_review.py --only "<gallery label or chart id>"
```

For an all-chart queue:

```bash
source .venv/bin/activate
python scripts/prepare_reporting_visual_review.py --format json --output runs/reporting_visual_review_queue.json
```

The packet resolves the gallery PNG, source artifact, context/data sidecars,
inferred visual family/variants, quality flags, and matching classified
reference examples from `docs/visual_reporting_references.json`.

## One-Chart Review Loop

1. Open the exact PNG output from the packet with visual inspection.
2. Read the chart context/data sidecars needed to understand the visible marks.
3. Inspect the relevant reference examples listed by the packet. View each
   cached `local_asset` image that matches the chart family/variant before
   proposing changes. Use source URLs only for attribution or when refreshing the
   reference pack; do not web-search unless refreshing the reference pack is the
   task.
4. Respond in four separated parts:
   - requested change: what the user pointed to and how to address it;
   - adjacent suggestions: nearby IBCS/reporting issues, explicitly outside the
     requested scope unless approved;
   - edit plan: renderer/data/context changes and sibling charts likely affected;
   - verification: exact examples/tests/gallery regeneration needed, including
     a check that the chart uses one visible font size.
5. Implement only after approval or when the user explicitly asked to implement.

## All-Chart Review Loop

For an all-chart pass, create the packet first, then work item by item. Keep a
simple queue status:

- acceptable as-is;
- needs a specific edit;
- needs user decision;
- should remain screenshot-only;
- needs a table companion.

Do not batch unrelated visual changes into one renderer edit unless the same
visible defect and same code path are proven across sibling charts.

## New Chart Or Table Loop

For new visuals, define the reporting purpose before choosing the renderer:

- intended message;
- measure, unit, period, and denominator;
- chart/table family;
- required labels, totals, variance notation, and color semantics;
- single-font-size contract for chart text;
- export mode and gallery output;
- tests and visual verification.

Tables are first-class reporting visuals. Prefer structured reporting tables
over raw data dumps: business rows, comparison columns, absolute/percent deltas,
clear units, aligned numbers, restrained separators, and emphasized totals.

## Reference Pack

Use `docs/visual_reporting_references.json` as the fixed classified reference
manifest. Cached images live under `docs/reporting_visual_references/assets/`.
If new local reference assets are added later, update the manifest with source
URL, usage note, license note, family/variant classification, `look_at`,
`avoid_using_for`, and `local_asset`. Keep external examples out of published
generated galleries.

Validate the reference corpus before relying on it:

```bash
source .venv/bin/activate
python scripts/validate_reporting_visual_references.py
```

## After Approved Code Changes

- Run focused tests for data/label decisions.
- Regenerate the relevant artifact or gallery.
- Inspect the before/after PNGs visually.
- If plugin source under `plugins/` changed, follow the `plugin-release` skill
  before finishing.
