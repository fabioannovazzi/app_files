# Launch Brief Schema

`launch_brief.json` is the model-authored input contract for launch decks.

The intent is:

- the model writes only the brief
- code compiles the brief into the richer report payload
- the shared PPTX renderer builds the deck
- a review model checks rendered slides afterward

## Minimal shape

```json
{
  "version": "launch_brief/1",
  "deckName": "Ulta Lipstick Launch Brief Experiment",
  "templateKey": "uniform",
  "promptStyle": "uniform",
  "slides": [
    {
      "role": "cover",
      "title": "Testing whether launch attributes are signal, not noise",
      "body": ["Paragraph one", "Paragraph two"],
      "footerText": "Ulta new arrivals | April 2026"
    },
    {
      "role": "launch_tiles",
      "title": "Included launches",
      "body": "The cohort still skews comfort-led rather than novelty-led.",
      "implication": "Implication: care language matters more than novelty language.",
      "products": [
        {
          "brand": "Example Brand",
          "product": "Hydrating Lip Stick",
          "body": "Hydrating stick form with high brand familiarity.",
          "tags": ["Hydrating", "Stick"],
          "badge": "Core signal"
        }
      ]
    },
    {
      "role": "comparison",
      "title": "What survived vs what failed",
      "body": "Audit keeps one modest signal and removes the false positive.",
      "left": {
        "heading": "Survived",
        "items": ["Hydrating over-indexes"]
      },
      "right": {
        "heading": "Failed",
        "items": ["Refillable does not survive audit"]
      },
      "calloutTitle": "Bottom line",
      "calloutBody": "The signal is real, but smaller than the first read implied."
    }
  ]
}
```

## Supported slide roles

- `cover`
  - requires `title`
  - requires `body`
  - optional `footerText`
- `launch_tiles`
  - requires `title`
  - requires `body`
  - requires at least two `products`
  - optional `implication`
- `comparison`
  - requires `title`
  - requires `body`
  - requires populated `left` and `right` blocks with `heading` and `items`
  - optional `calloutTitle`
  - optional `calloutBody`

## Product object

Each `launch_tiles` product can include:

- `brand`
- `product`
- `body`
- `tags`
- `badge`

The brief should focus on content and emphasis, not decorative color choices. The renderer now defaults to white slides with restrained neutral cards and uses accent color only for meaningful emphasis, such as a badge.

## Compilation path

`launch_brief.json`
-> `report_payload.json`
-> `slides_pptx_spec.json`
-> `.pptx`

The current compiler lives in [launch_brief.py](../../src/slides/launch_brief.py), and the CLI entry point is [build_launch_report_pptx.py](../../scripts/build_launch_report_pptx.py).
