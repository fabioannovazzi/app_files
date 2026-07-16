# Launch Pipeline Contracts

The deck pipeline is split into explicit layers:

1. `launch_facts.json`
2. `category_insights.json`
3. `launch_brief.json`
4. `report_payload.json`
5. `slides_pptx_spec.json`
6. `.pptx`

The operating model is:

- strongest model reasons over facts and writes insights or a final brief
- deterministic code owns deck structure and rendering
- rendered output stays visually consistent across categories

## `launch_facts.json`

`launch_facts.json` is the upstream evidence packet prepared by code from scrape outputs and derived analysis. It should stay factual and auditable.

Required fields:

- `retailer`
- `category`
- `question`
- at least one of:
  - `summaryMetrics`
  - `attributeSignals`
  - `launchExamples`

Sample: [launch_facts.sample.json](../../docs/examples/launch_facts.sample.json)

## `category_insights.json`

`category_insights.json` is the preferred model-authored intermediate step for one category. It captures analytical conclusions without forcing the model to design the actual slides.

Required fields:

- `thesis`
- `summary`
- at least two `evidenceExamples`
- at least one `survivingSignals`
- at least one `droppedSignals` or `caveats`

Sample: [category_insights.sample.json](../../docs/examples/category_insights.sample.json)

## `launch_brief.json`

`launch_brief.json` is the renderer-facing narrative brief. It is the last model-authored stage before deterministic compilation into PowerPoint.

Sample: [launch_brief.sample.json](../../docs/examples/launch_brief.sample.json)

## Deterministic compilation

Current code paths:

- facts validation: [launch_facts.py](../../src/slides/launch_facts.py)
- insights validation and compilation: [category_insights.py](../../src/slides/category_insights.py)
- brief validation and compilation: [launch_brief.py](../../src/slides/launch_brief.py)
- PPTX build entry point: [build_launch_report_pptx.py](../../scripts/build_launch_report_pptx.py)

The PPTX build script now accepts either:

- `category_insights.json`
- `launch_brief.json`
- compiled `report_payload.json`

So the current experimental paths are:

- `category_insights -> launch_brief -> report_payload -> pptx`
- `launch_brief -> report_payload -> pptx`
- `report_payload -> pptx`
