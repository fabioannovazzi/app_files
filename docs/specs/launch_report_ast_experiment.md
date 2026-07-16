# Launch Report AST Experiment

## Goal

Experiment with a richer intermediate deck artifact for scraped-launch reports.

This path is intentionally separate from the discontinued `/sales` flow. The
target use case is:

1. scrape Ulta new-arrivals / launch evidence
2. derive findings with a strong model
3. have the model author a rich deck AST
4. compile that AST into the shared semantic PPTX format
5. render the final `.pptx`

## Why A Fat AST

A skinny JSON with only `title`, `bullets`, and `image` references is not enough
to make a strong deck. The AST needs to be expressive enough to describe:

- slide role
- composition intent
- native visual structures
- comparison groupings
- emphasis and hierarchy
- explicit layout overrides when needed

The model should still be free to make strong editorial decisions, but the
runtime execution should remain deterministic.

## Current Compiler Path

The shared semantic PPTX renderer now exposes:

- [build_slides_pptx_spec_from_report_payload](../../src/slides/semantic_pptx.py#L360)

This compiles a structured report payload directly into `SlidesPptxSpec`, which
the existing PPTX renderer can then render deterministically.

## Experiment CLI

Use:

```bash
python scripts/build_launch_report_pptx.py \
  docs/examples/launch_report_ast.sample.json \
  --output-dir /tmp/launch_report_experiment
```

Optional PNG rendering:

```bash
python scripts/build_launch_report_pptx.py \
  docs/examples/launch_report_ast.sample.json \
  --output-dir /tmp/launch_report_experiment \
  --render-pngs
```

The script writes:

- `report_payload.json`
- `slides_pptx_spec.json`
- `<deck-name>.pptx`

The compiler validates the AST before rendering. Invalid `layoutVariant`,
absolute/URL `visualPath` values, incomplete comparison columns, and malformed
native visuals fail fast with a clear error.

## AST Features In This Experiment

The sample AST demonstrates:

- cover-style slide with footer metadata
- explicit `layoutVariant` override when the slide should be bottom-weighted
- `nativeVisual.launch_product_tiles` for launch-specific product tiles instead of a flat screenshot
- comparison columns with a bottom callout block

These features are enough to test whether a strong model can author a deck that
still feels intentional once rendered deterministically.

## Next Likely Step

If this path works well, the next iteration should add a dedicated launch-report
builder that converts Ulta scrape outputs into this AST shape, and then let the
strong model revise the AST inside a render-review loop.
