# Source-bound evidence contract

Use this contract for every production deck that contains a number, date,
percentage, count, currency amount, chart mark, or numeric table cell. The
contract guarantees that published quantitative content was transported from
exact evidence bytes and rendered deterministically. It does not guarantee
that the upstream calculation, evidence choice, or interpretation is correct.

## Boundary

The model or advisor chooses:

- the evidence that is relevant;
- metric and entity meaning;
- period, population, and comparison basis;
- which deterministic calculation or prepared view to request;
- chart type, narrative, materiality, and interpretation.

Deterministic code owns:

- exact file hashing and contained paths;
- stable table-key and JSON-object addressing;
- type, uniqueness, and finite-number checks;
- Decimal scaling, rounding, grouping, signs, prefixes, and suffixes;
- insertion into prose, claims, metric cards, tables, and visual specs;
- composition, rendering, provenance, and build-time equality checks.

Do not put a filter, join, aggregation, formula, row position, or semantic
selector in a deck binding. Materialize the required fact or plot view upstream
as a separate evidence artifact. This keeps the deck compiler generic across
sales, financial, customer, operational, contract, and other due-diligence
evidence.

## Prepare and seal evidence

An evidence bundle may contain any number of JSON or CSV artifacts:

```json
{
  "schema_version": "clara.evidence_bundle.v1",
  "bundle_id": "target-company-diligence",
  "description": "Prepared financial and customer evidence.",
  "artifacts": [
    {
      "id": "financial-facts",
      "source_id": "source-financial-facts",
      "path": "evidence/financial-facts.csv",
      "media_type": "text/csv",
      "sha256": "",
      "size_bytes": 0,
      "snapshot_id": "closing-snapshot",
      "table": {
        "key_fields": ["fact_id"],
        "order_by": ["display_order"]
      }
    },
    {
      "id": "customer-concentration",
      "source_id": "source-customer-concentration",
      "path": "evidence/customer-concentration.csv",
      "media_type": "text/csv",
      "sha256": "",
      "size_bytes": 0,
      "snapshot_id": "closing-snapshot",
      "table": {
        "key_fields": ["row_id"],
        "order_by": ["display_order"]
      }
    }
  ]
}
```

Paths are relative to the bundle, must remain inside its folder, and may not be
symbolic links. Table keys must be unique. `order_by` establishes deterministic
series order. Seal the draft after every evidence change:

```bash
python skills/html-deck/scripts/evidence_bindings.py seal \
  <work-dir>/evidence-bundle.json
```

The command writes each artifact's exact SHA-256 and byte count, then reports
the bundle SHA-256. Copy that bundle digest into the deck plan. Never edit a
sealed artifact without resealing and recomposing.

JSON artifacts can expose a scalar or complete prepared object through a JSON
Pointer. A pointer may traverse object keys but may not select an array
position. Use a keyed object or a prepared table instead of positional rows.

## Bind values in a v2 plan

Use `clara.html_deck_plan.v2`, `numeric_policy: require_bindings`, and a central
binding registry:

```json
{
  "schema_version": "clara.html_deck_plan.v2",
  "allow_bespoke_html": false,
  "evidence": {
    "bundle": {
      "path": "evidence-bundle.json",
      "sha256": "<bundle-sha256>"
    },
    "numeric_policy": "require_bindings",
    "bindings": {
      "revenue": {
        "kind": "table_cell",
        "artifact_id": "financial-facts",
        "row_key": {"fact_id": "revenue"},
        "field": "value",
        "value_type": "decimal",
        "display": {
          "decimals": 1,
          "scale": "0.000001",
          "rounding": "half_up",
          "prefix": "$",
          "suffix": "m"
        }
      },
      "customer-series": {
        "kind": "table_rows",
        "artifact_id": "customer-concentration",
        "fields": {"label": "label", "value": "share"},
        "value_type": "records"
      }
    }
  },
  "slides": []
}
```

Supported binding kinds:

- `table_cell`: exact row key plus one field; exactly one row must resolve;
- `table_rows`: every row of an already-prepared table, deterministically
  ordered and projected through an explicit output-to-source field map;
- `json_pointer`: one stable object-key path in a JSON artifact.

Supported value types are `decimal`, `integer`, `string`, `boolean`, `records`,
and `json`. Nulls, non-finite decimals, fractional integers, duplicate keys,
missing fields, missing files, changed bytes, and unsupported types fail closed.

Use a binding directly:

```json
{"$binding": {"id": "revenue", "mode": "display"}}
```

`display` uses the binding's explicit formatting contract. `raw` returns the
typed evidence value and is required for prepared visual data:

```json
{
  "renderer": "data_visual",
  "spec": {
    "type": "bar",
    "title": "Customer concentration",
    "data": {"$binding": {"id": "customer-series", "mode": "raw"}}
  }
}
```

For prose, use exact placeholder/reference parity:

```json
{
  "$template": {
    "text": "Revenue is {revenue}",
    "bindings": {
      "revenue": {"id": "revenue", "mode": "display"}
    }
  }
}
```

Every placeholder must resolve exactly once and every declared binding must be
used. A v2 plan rejects numeric-looking literal content in titles, prose,
notes, metric values, visual data, labels, source notes, claim statements, and
qualifications. Structural IDs, source references, schema versions, and
fragment indices are excluded from that scan.

## Bind claims and sources

Use `clara.html_deck_ledger.v2` with the same binding objects and templates.
Every used artifact has one `source_id`. The matching content-ledger source
must carry the artifact's exact SHA-256. A slide using the artifact must include
that ID in `source_refs`; a bound claim must include it in `source_ids`.

Source-bound plans do not permit bespoke HTML or custom renderers because their
quantitative content cannot yet be traced structurally.

Visible `deck.json` metadata must also be non-quantitative. Authored
`custom.css` may style verified content, but it may not generate text with the
`content` property or introduce images/resources with `url()`. Put any
quantitative image through a sealed evidence artifact and a structurally bound
deck slot instead.

## Compose and build

Run the normal composer:

```bash
python skills/html-deck/scripts/compose_html_deck.py \
  <work-dir>/deck-plan.json \
  --output-dir <work-dir> \
  --force
```

In addition to `slides.html` and `custom.css`, a v2 composition writes:

- `resolved-deck-plan.json`;
- `resolved-content-ledger.json`;
- `evidence-ledger.json`.

The evidence ledger records the bundle and artifact hashes, stable address,
display-format contract, raw value, recomputable formatted or raw consumer
value, value digest, source ID, and every consumer JSON path.

The builder resolves and composes again. It requires byte equality for
`slides.html`, generated/shared CSS, the resolved documents, and the evidence
ledger. A changed source, bundle, plan, value, HTML fragment, CSS block, or
ledger stops the build. The sanitized evidence ledger is embedded in the
content-addressed publication, and the build report declares
`evidence.status: verified`.

Legacy v1 decks are `not_verified`. The builder rejects quantitative v1
content by default. `--allow-unverified-quantitative-content` exists only for
explicit layout galleries or illustrative legacy material; it never upgrades
the evidence status and must not be used for source-backed reporting.

## Reporting Engine handoff

`modules/reporting-engine/scripts/render_capability.py` records exact input,
request, effective-recipe, and current-run output evidence in
`render_manifest.json`. Its output records include SHA-256 and byte counts, so
a prepared chart-data CSV can be sealed into this bundle without copying its
values into the deck plan.

The Reporting Engine remains a one-input render boundary today. A future
due-diligence orchestrator should create multiple source assets, reviewed
relationship contracts, and deterministic prepared tables before this deck
contract. It must not infer that similarly named fields across financial,
customer, operational, and contract sources identify the same concept.
