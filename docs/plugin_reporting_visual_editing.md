Plugin Reporting Visual Editing
===============================

This workflow supports two practical requests:

- review one generated chart/table, identify the requested fix and adjacent
  reporting-visual suggestions, then wait before editing;
- prepare an all-gallery review queue so generated visuals can be inspected one
  by one.

The generated PNG gallery remains the working surface:

```text
runs/png_examples/png-gallery/index.html
static/shared/png-gallery/index.html
```

External references are not gallery content. Reporting examples are cached and
classified separately under `docs/reporting_visual_references/` and used to
inspect our own generated artifacts.

Review Packet
-------------

Prepare a packet for one chart:

```bash
source .venv/bin/activate
python scripts/prepare_reporting_visual_review.py --only "column_total"
```

Prepare a queue for all gallery charts:

```bash
source .venv/bin/activate
python scripts/prepare_reporting_visual_review.py \
  --format json \
  --output runs/reporting_visual_review_queue.json
```

The packet includes:

- exact generated output path;
- source artifact path;
- context/data/recipe sidecars when present;
- inferred chart/table family;
- inferred structural variants;
- matching classified reference examples and local image paths from
  `docs/visual_reporting_references.json`;
- review focus for the family.

Operating Rule
--------------

When the user points to a concrete problem, address that problem first. If other
reporting issues are visible, list them as adjacent suggestions and do not include
them in the implementation scope unless the user approves.

The normal loop is:

```text
locate chart -> visually inspect output -> inspect context/data -> compare to
fixed references -> propose scoped edit plan -> wait -> implement -> regenerate
-> visually verify
```

Reference Manifest
------------------

`docs/visual_reporting_references.json` is the fixed classified reference
manifest. It maps families such as column/bar, stacked charts,
waterfall/variance, distribution, scatter/bubble, mosaic/mekko, and reporting
tables to local reporting reference images where available.

Validate it with:

```bash
source .venv/bin/activate
python scripts/validate_reporting_visual_references.py
```

If local reference images or PDFs are added, store them outside the generated
gallery and update the manifest with:

- source URL;
- usage/license note;
- local asset path;
- what to notice in the example.

Do not imply external certification, endorsement, or affiliation.
