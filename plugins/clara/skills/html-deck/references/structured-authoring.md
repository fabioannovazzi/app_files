# Structured authoring contract

Use `deck-plan.json` as the editable narrative/layout contract and
`content-ledger.json` as the source/claim contract. The model chooses the
storyline, layout, claim classification, and visual type. The composer only
checks and renders the supplied choices.

## Deck plan

The top-level schema is `clara.html_deck_plan.v1`:

```json
{
  "schema_version": "clara.html_deck_plan.v1",
  "allow_bespoke_html": false,
  "slides": [
    {
      "id": "decision-gap",
      "layout_id": "visual-takeaway",
      "title": "The decision gap is concentrated in one measure",
      "chapter": "evidence",
      "chapter_label": "Evidence",
      "tone": "light",
      "notes": "Explain the comparison basis before the implication.",
      "source_refs": ["source-workpaper"],
      "claim_refs": ["claim-gap"],
      "slots": {
        "eyebrow": "Observed difference",
        "title": "The decision gap is concentrated in one measure",
        "visual": {
          "renderer": "data_visual",
          "source_refs": ["source-workpaper"],
          "claim_refs": ["claim-gap"],
          "spec": {
            "schema_version": "clara.html_deck_visual.v1",
            "type": "bar",
            "id": "decision-gap-chart",
            "title": "Observed value by option",
            "data": [
              {"label": "Option A", "value": 72},
              {"label": "Option B", "value": 48}
            ],
            "source_ids": ["source-workpaper"],
            "source_note": "Same period and basis."
          }
        },
        "takeaway_label": "Implication",
        "takeaway": "The difference changes the governed next move.",
        "source_note": "Approved workpaper."
      }
    }
  ]
}
```

Read `assets/layout-library/registry.json` before selecting layouts. Each entry
defines narrative role, slots, density, typography, fragment limits, and tone.
Do not choose a layout by mechanically matching keywords; choose it for the
argument the slide must make.

The bundled data renderer supports `bar`, `line`, `scatter`, `bubble`,
`waterfall`, `timeline`, and `table`. Supply the already-selected period,
filters, records, labels, and visual type. The renderer deliberately does not
filter data or combine/split periods. Analytical preparation remains upstream.

Every visual needs a safe stable `id`, at least one safe `source_ids` entry,
an audience-facing title, and an accessible label. Scatter and bubble specs
also require visible `x_axis_label` and `y_axis_label`; bubble specs require a
visible `size_axis_label`, positive sizes, and no more than a 25:1 size range.
Bubble radius is square-root scaled so circle area, rather than diameter,
represents the supplied size.

Mechanical legibility limits are enforced before rendering: bar/scatter/bubble/
waterfall data is capped at eight items, line at ten, timeline at six, and
tables at six columns by eight rows. Bar labels are capped at 16 characters;
line and waterfall label limits tighten as item count rises. Browser QA then
measures every SVG text bounding box and fails labels that leave the canvas or
overlap. These checks do not decide whether the selected data, period, visual,
or analytical interpretation is correct.

Set `allow_bespoke_html` to `true` only when no registered layout can express
the required mechanism. Bespoke markup is body markup only; scripts, event
handlers, remote/local resources, and executable URLs are rejected.

## Content ledger

The top-level schema is `clara.html_deck_ledger.v1`. Every deck slide appears
exactly once. Every claim has an explicit classification and basis.

```json
{
  "schema_version": "clara.html_deck_ledger.v1",
  "sources": [
    {
      "id": "source-workpaper",
      "label": "Approved advisory workpaper",
      "kind": "workpaper",
      "locator": "/private/case/advisory_workpaper.md",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "publish_locator": false
    }
  ],
  "slides": [
    {
      "slide_id": "decision-gap",
      "basis_status": "source-backed",
      "basis_note": "",
      "claims": [
        {
          "id": "claim-gap",
          "statement": "The observed difference is 24 on the agreed basis.",
          "classification": "fact",
          "basis_status": "source-backed",
          "basis_note": "",
          "source_ids": ["source-workpaper"],
          "qualification": "Illustrative labels replaced with approved values."
        }
      ]
    }
  ]
}
```

Classifications are `fact`, `assumption`, `target`, `forecast`, `probability`,
`illustrative`, `judgement`, and `open-question`. Basis statuses are
`source-backed`, `speaker-judgement`, and `not-applicable`. Facts must be
source-backed. A non-source-backed claim needs a basis note. Private locators
are stripped from the published HTML unless `publish_locator` is the JSON
boolean `true`.

## Compose

After editing both files:

```bash
python skills/html-deck/scripts/compose_html_deck.py \
  <work-dir>/deck-plan.json \
  --output-dir <work-dir> \
  --force
```

The bundled `data_visual` renderer is registered automatically. The command
replaces only `slides.html` and `custom.css`; it does not invent or rewrite the
content ledger. Reconcile slide/source/claim IDs before building.
