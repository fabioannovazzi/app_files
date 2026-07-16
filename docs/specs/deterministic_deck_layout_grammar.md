# Deterministic Deck Layout Grammar v1

## Goal

Introduce a layout-planning step between authored slide copy and PPTX rendering.

The planner should:

- read a semantic slide spec
- classify the slide into a deterministic layout family
- expose the decision in machine-readable form
- keep geometry decisions in code rather than in the LLM prompt

This is the missing layer between:

1. `what to say`
2. `how to render it`

## Input Shape

The grammar accepts slide payloads with existing authored-plan fields plus a few
optional richer content fields.

Current fields already used by the sales deck pipeline:

- `kind`
- `title`
- `subtitle`
- `bullets`
- `chart_id`

Optional richer fields supported by the grammar:

- `body`
- `cards`
- `metrics`
- `examples`
- `comparison`
- `visual`
- `density`

## Supported Layout Families

`v1` chooses among these deterministic slide families:

- `section_header`
- `hero_thesis`
- `summary_bullets`
- `chart_focus`
- `chart_sidebar`
- `cards_3up`
- `cards_2x2`
- `example_grid`
- `metrics_comparison`
- `comparison_two_column`
- `text_statement`

These are not final PPTX templates. They are stable layout intents that a
renderer can map to PowerPoint geometry.

## Selection Rules

The planner uses content shape, not wording style.

Representative rules:

- explicit `section_header` kind -> `section_header`
- hero-style visual plus light copy -> `hero_thesis`
- left/right comparison items present -> `comparison_two_column`
- exactly 3 cards -> `cards_3up`
- exactly 4 cards -> `cards_2x2`
- 3 or 4 examples -> `example_grid`
- 2 or more named metrics without a chart -> `metrics_comparison`
- chart with light copy and no subtitle -> `chart_focus`
- chart with heavier supporting copy -> `chart_sidebar`
- summary kind or high bullet count -> `summary_bullets`
- otherwise -> `text_statement`

The planner also derives:

- `layout_density`
- `layout_reasons`
- `split_recommended`

## Example

Input:

```json
{
  "title": "Hydrating launches over-index",
  "chart_id": "chart-01",
  "bullets": [
    "Hydrating launches over-index versus the older base."
  ]
}
```

Output annotation:

```json
{
  "title": "Hydrating launches over-index",
  "chart_id": "chart-01",
  "bullets": [
    "Hydrating launches over-index versus the older base."
  ],
  "layout_family": "chart_focus",
  "layout_density": "light",
  "layout_reasons": [
    "Chart is primary and supporting copy is light."
  ],
  "split_recommended": false
}
```

## Why This Helps

This keeps the system flexible without asking the LLM to invent pixel geometry.

The intended flow is:

1. LLM writes semantic slide spec
2. Layout grammar assigns layout families
3. Renderer maps families to deterministic PowerPoint geometry
4. Validation loop reviews overflow, density, cropping, and hierarchy
5. Only bounded fixes are allowed

## Current Integration

The grammar is implemented in:

- [deck_layout_grammar.py](../../modules/pdp/deck_layout_grammar.py)

It is currently applied to the authored sales deck payload in:

- [sales_authored_deck_plan.py](../../modules/pdp/sales_authored_deck_plan.py)

The raw deck-plan contract remains unchanged.
