# Sales Brief JSON Contract for Direct PPTX Generation

## Goal

Replace the current `PDF brief + charts/` package as the machine input to deck
generation with a canonical JSON artifact plus PNG chart assets.

The JSON should be:

- rich enough to generate a deck without parsing a PDF
- close to the current review-brief outputs
- simple enough to map into the existing slides deck payload

This is the proposed minimal contract for `v1`.

## Canonical Artifacts

Required:

- `brief.json`
- `charts/*.png`

Optional:

- `chart-map.md`
- `chart-serials.json`
- `brief.pdf`

For the new pipeline, `brief.json` is the source of truth. The PDF is optional.

## Top-Level Shape

```json
{
  "version": "sales_deck_brief/v1",
  "brief_id": "blush-ulta-sephora-20260218-201018",
  "deck_id": "sales-blush-ulta-sephora-20260218-201018",
  "language": "it",
  "dataset": "us_cosmetics",
  "template_key": "bain",
  "prompt_style": "bain",
  "chart_palette": "bain",
  "scope": {},
  "narrative": {},
  "charts": [],
  "slides": []
}
```

## Required Fields

### 1. Deck metadata

```json
{
  "version": "sales_deck_brief/v1",
  "brief_id": "string",
  "deck_id": "string",
  "language": "string",
  "template_key": "string",
  "prompt_style": "string"
}
```

Notes:

- `prompt_style` matches the existing slides style key resolved by
  `resolve_prompt_style_key` in
  [notebooklm_style.py](../../src/slides/notebooklm_style.py#L98).
- `template_key` is included explicitly even if it initially equals
  `prompt_style`. This avoids coupling template choice to typography forever.

### 2. Scope

```json
{
  "scope": {
    "category_key": "blush",
    "category_label": "blush",
    "retailers": ["ulta", "sephora"],
    "brands": [],
    "period_start": "2022-01-01",
    "period_end": "2025-09-01",
    "price_bands": [],
    "pareto": [],
    "attribute_filters": {},
    "focus_attributes": [
      {
        "id": "form",
        "label": "Form"
      }
    ]
  }
}
```

This is the business context for both the LLM and auditability.

### 3. Narrative

```json
{
  "narrative": {
    "executive_summary": "string",
    "key_takeaways": ["string"],
    "title": "optional deck title",
    "subtitle": "optional deck subtitle"
  }
}
```

Minimal requirement:

- `executive_summary`
- `key_takeaways`

### 4. Chart catalog

Each chart entry should identify the asset and preserve the current chart
metadata already available in the brief pipeline.

```json
{
  "charts": [
    {
      "chart_id": "us-cosmetics_stacked_form_blush_6336a274fdd8",
      "definition_id": "stacked_form_blush_b997d32b5d83",
      "filename": "charts/us-cosmetics_stacked_form_blush_6336a274fdd8.png",
      "title": "US Cosmetics / ulta, sephora / Category: blush | Sales in % by form | Monthly values (2022-01-01 -> 2025-09-01)",
      "title_lines": [
        "US Cosmetics / ulta, sephora / Category: blush",
        "Sales in % by form",
        "Monthly values (2022-01-01 -> 2025-09-01)"
      ],
      "chart_type": "stacked_share",
      "normalization": "share_of_category_total",
      "interpretation": {
        "headline": "Cream becomes the clear category leader",
        "bullets": [
          "Cream climbs 39.1% -> 56.5%, up 17 pp.",
          "Liquid declines 37.4% -> 18.9%, down 19 pp."
        ]
      }
    }
  ]
}
```

Required chart fields for `v1`:

- `chart_id`
- `filename`
- `title_lines`
- `interpretation.headline`
- `interpretation.bullets`

Useful but optional in `v1`:

- `definition_id`
- `chart_type`
- `normalization`

### 5. Slide plan

This is the real replacement for parsing the PDF.

```json
{
  "slides": [
    {
      "slide_id": "s01",
      "kind": "text",
      "title": "Blush category reset",
      "bullets": [
        "Category value and price point reset higher.",
        "Cream, buildable and satin now define the winning archetype."
      ],
      "speaker_notes": "optional"
    },
    {
      "slide_id": "s02",
      "kind": "chart",
      "title": "Category-level form mix shift",
      "chart_id": "us-cosmetics_stacked_form_blush_6336a274fdd8",
      "bullets": [
        "Cream climbs 39.1% -> 56.5%, up 17 pp.",
        "Liquid declines 37.4% -> 18.9%, down 19 pp."
      ],
      "source_refs": [
        "us-cosmetics_stacked_form_blush_6336a274fdd8"
      ],
      "section": "category-mix"
    }
  ]
}
```

Required slide fields for `v1`:

- `slide_id`
- `kind`
- `title`

Rules:

- `kind` is one of: `section_header`, `text`, `chart`
- `chart` slides require exactly one `chart_id`
- `text` slides must not include `chart_id`
- `section_header` slides may include neither bullets nor chart

Recommended:

- `bullets`
- `source_refs`
- `section`

## Minimal `v1` Example

```json
{
  "version": "sales_deck_brief/v1",
  "brief_id": "blush-ulta-sephora-20260218-201018",
  "deck_id": "sales-blush-20260218-201018",
  "language": "it",
  "dataset": "us_cosmetics",
  "template_key": "bain",
  "prompt_style": "bain",
  "chart_palette": "bain",
  "scope": {
    "category_key": "blush",
    "category_label": "blush",
    "retailers": ["ulta", "sephora"],
    "brands": [],
    "period_start": "2022-01-01",
    "period_end": "2025-09-01",
    "price_bands": [],
    "pareto": [],
    "attribute_filters": {},
    "focus_attributes": []
  },
  "narrative": {
    "executive_summary": "Blush is structurally different in 2025 vs 2022, with stronger economics and a new winning product mix.",
    "key_takeaways": [
      "Cream is now the dominant form.",
      "Buildable coverage is now the majority.",
      "Rhode is the defining winner."
    ],
    "title": "US Cosmetics blush review",
    "subtitle": "Ulta + Sephora"
  },
  "charts": [
    {
      "chart_id": "us-cosmetics_stacked_form_blush_6336a274fdd8",
      "filename": "charts/us-cosmetics_stacked_form_blush_6336a274fdd8.png",
      "title_lines": [
        "US Cosmetics / ulta, sephora / Category: blush",
        "Sales in % by form",
        "Monthly values (2022-01-01 -> 2025-09-01)"
      ],
      "interpretation": {
        "headline": "Cream becomes the clear category leader",
        "bullets": [
          "Cream climbs 39.1% -> 56.5%, up 17 pp.",
          "Liquid declines 37.4% -> 18.9%, down 19 pp."
        ]
      }
    }
  ],
  "slides": [
    {
      "slide_id": "s01",
      "kind": "text",
      "title": "Executive summary",
      "bullets": [
        "Value growth and price realization both improved.",
        "The category has pivoted to cream, buildable and satin."
      ]
    },
    {
      "slide_id": "s02",
      "kind": "chart",
      "title": "Category-level form mix shift",
      "chart_id": "us-cosmetics_stacked_form_blush_6336a274fdd8",
      "bullets": [
        "Cream becomes the clear leader.",
        "Liquid is the main structural loser."
      ],
      "source_refs": [
        "us-cosmetics_stacked_form_blush_6336a274fdd8"
      ]
    }
  ]
}
```

## Mapping to the Existing Slides Stack

The existing deck save path expects:

- `promptStyle`
- `slides[]`
- optional `sections[]`

See:

- [DeckSaveRequest](../../modules/slides/api.py#L449)
- [SlidePayload](../../modules/slides/api.py#L361)
- [deck_from_payload](../../src/slides/service.py#L16)

The bridge from `brief.json` to the current deck payload should be:

1. Resolve `prompt_style` -> `promptStyle`
2. Convert each structured slide into HTML:
   - `title` -> `titleHtml`
   - `bullets` -> `bodyHtml`
   - `chart_id` -> `<img>` tag using the packaged PNG asset
3. Save the resulting deck through the existing deck save flow
4. Export to PPTX using the current slides export pipeline

## Why This Is Enough

This contract removes the need to:

- parse chart IDs back out of a PDF
- infer slide order from prose
- reverse-map PNG filenames from the rendered brief

It preserves the parts that matter:

- deck style/template selection
- business scope
- slide order
- slide titles and bullets
- deterministic chart asset references

## Deliberately Out of Scope for `v1`

Not required for the first direct-to-PPTX version:

- multiple charts on one slide
- arbitrary placeholder geometry
- chart cropping or chart restyling
- per-slide custom fonts/colors beyond `prompt_style` / `template_key`
- editable native chart reconstruction inside PPTX

Those can be added later once the direct deck path is stable.
