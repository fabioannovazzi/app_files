# PCI 2018-11-04 taxonomy spike

Evidence recorded on 2026-08-05 for the deterministic Phase 0 path.

## Official package lock

- Official source page:
  `https://it.xbrl.org/materiali/tassonomie/tassonomia-principi-contabili-italiani-2018/`
- Official package URL:
  `https://it.xbrl.org/wp-content/uploads/sites/5/2018/11/PCI-2018-11-04.zip`
- Observed SHA-256:
  `c24b86375529469ca0be9a06b231fbb05da18df99fa36a1db2e587ab51e2f0f1`
- Ordinary entry point: `2018-11-04/itcc-ci-ese-2018-11-04.xsd`
- Abbreviated entry point: `2018-11-04/itcc-ci-abb-2018-11-04.xsd`
- Micro entry point: `2018-11-04/itcc-ci-micr-2018-11-04.xsd`

The repository stores the lock metadata, but does not bundle the official ZIP
or generated catalogue until redistribution rights are approved.

## Reproducible catalogue build

With the official ZIP available locally, run:

```bash
python scripts/build_taxonomy_catalogue.py \
  --package /controlled/path/PCI-2018-11-04.zip \
  --entry-point ORDINARY=2018-11-04/itcc-ci-ese-2018-11-04.xsd \
  --entry-point ABBREVIATED=2018-11-04/itcc-ci-abb-2018-11-04.xsd \
  --entry-point MICRO=2018-11-04/itcc-ci-micr-2018-11-04.xsd \
  --taxonomy-id PCI_2018-11-04 \
  --expected-sha256 c24b86375529469ca0be9a06b231fbb05da18df99fa36a1db2e587ab51e2f0f1 \
  --official-source https://it.xbrl.org/wp-content/uploads/sites/5/2018/11/PCI-2018-11-04.zip \
  --output /controlled/path/PCI_2018-11-04.catalogue.json
```

Observed result: all three entry-point DTSs loaded without Arelle errors. The
schema-2 unified catalogue contained 2,399 concepts: 2,292 items, 29 tuples,
and 78 schema/reference concepts that are neither items nor tuples. It also
preserved 6,708 concept references and the resolved presentation and
calculation networks. Only non-abstract reportable items may enter renderer or
schedule allowlists.

## Local validation evidence

The production renderer generated one minimal current/comparative instance per
form containing `itcc-ci:TotaleAttivo` and `itcc-ci:TotalePassivo`. Each was
validated offline with `arelle-release==2.42.1`, the checksum-pinned official
ZIP, and Arelle's bundled standard-schema cache.

| Form | Entry point | Local result |
| --- | --- | --- |
| Ordinary | `itcc-ci-ese-2018-11-04.xsd` | PASS |
| Abbreviated | `itcc-ci-abb-2018-11-04.xsd` | PASS |
| Micro | `itcc-ci-micr-2018-11-04.xsd` | PASS |

These are structural spike instances, not complete statutory golden cases.
The remaining Phase 0 gates are manual TEBENI comparison, renderer comparison,
copyright/licensing approval, and signed accounting-rule ownership.

## Complete primary-presentation coverage

The later controlled audit at `scripts/audit_statutory_presentation.py` derives
the selected-form monetary leaf and total inventories directly from the locked
catalogue's official presentation and calculation relationships. It refuses a
network count that differs from the versioned policy, requires explicit current
and comparative decisions for every absent leaf, and uses the official
calculation weights to derive or verify totals.

Observed on 2026-08-05 with the same package and catalogue:

| Form | Unique required leaves | Unique totals | Emitted facts | Local XBRL result |
| --- | ---: | ---: | ---: | --- |
| Abbreviated | 87 | 29 | 116 | PASS |
| Micro | 84 | 29 | 113 | PASS |
| Ordinary | 224 | 74 | 298 | PASS |

All three controlled cases explicitly confirmed every leaf as zero for both
periods, closed with zero missing decisions and zero arithmetic issues, emitted
the complete resolved primary inventory, and passed pinned offline Arelle in
XBRL 2.1 calculation mode. Exact catalogue, package, policy, inventory,
instance, validation-report, and audit checksums are recorded in
`docs/bilancio_statutory_presentation_audit.json` at the repository root.

This proves primary-network enumeration, explicit absence handling, official
rollups, rendering, and local processor acceptance. The controlled zeros are
not real-entity accounting judgments and do not prove semantic classification,
note/schedule-table completeness, official rendering equivalence, or TEBENI
compatibility.

## Controlled schedule-table boundaries

The schedule adapter at `scripts/schedule_taxonomy_adapter.py` uses a versioned
policy to select official presentation roots for fixed assets, receivables,
payables, equity, provisions, TFR, tax and guarantees/commitments. It derives
the permitted descendants from the locked catalogue, requires a reviewed
mapping or omission for every normalized schedule cell, derives fact values
without model arithmetic, and reconciles any concept already emitted by the
primary presentation.

The checked audit at `scripts/audit_schedule_taxonomy.py` observed:

| Form | Schedule families | Permitted unique monetary table concepts | Route |
| --- | ---: | ---: | --- |
| Ordinary | 8 | 623 | `TABLE_FACTS` |
| Abbreviated | 8 | 453 | `TABLE_FACTS` |
| Micro | 8 | 0 | `TEXT_ONLY` |

The ordinary inventory SHA-256 is
`ee0178b2e8fb35cbab1d3ecca5782de3c04f7abc02f9d964c78dbac06b8db376`;
the abbreviated inventory SHA-256 is
`eb59426cfc2bdc11e4fb2529fa90a070cb861dc0dea84e3ea9baedfefb61c598`;
the micro inventory SHA-256 is
`b86889e511bad1f958044f9cb0b3d72bf252a6db57c77f8b26a71b922e53d4a7`.
The adapter policy SHA-256 is
`3f90676d582862bcaa9a48a1f35b632c6b719198374bffb7e8220488bae590a5`,
and the checked audit report SHA-256 is
`f99572cfed076993070c80012122de5ef02d9daac50be64221ed3ffaf098ea5a`.

The corrected counts exclude tuple containers and non-item schema concepts.
Reportable descendants inside tuple tables remain available with exact
role/root/tuple-path bindings, so repeated rows can emit distinct tuple
occurrences without weakening duplicate-fact controls.

This proves the form-specific structural boundary and guarded fact-compilation
path. It does not prove that a professional binding chosen for one synthetic
schedule is correct for every real-company fact, or that every triggered note
table is completely populated.

The processor configuration is separately exercised against the complete
official XBRL 2.1 conformance suite in `conformance-evidence.md`. Vera enables
XBRL 2.1 calculation validation in addition to structural validation.

## Controlled 24-case run

The synthetic registry at `evals/golden_cases.json` represents every scenario
listed in specification section 23.3. The production runner at
`scripts/run_golden_cases.py` refuses a non-empty output directory, verifies the
official-package checksum against the generated catalogue, and drives each
XBRL fixture through the public case lifecycle from source ingestion through
professional approval and export. It checks rendered values, invokes offline
Arelle, and writes a checksum manifest.

Observed on 2026-08-05 with the package and catalogue above:

- suite status: `PASS`;
- cases passed: `24/24`;
- locally validated XBRL instances: `20/20`;
- boundary cases: taxonomy mismatch, unsupported IFRS, spreadsheet prompt
  injection, and inconsistent progressives, all `PASS`;
- every ordinary workflow includes one reviewed cash-flow schedule whose net
  change reconciles to the statutory XBRL cash-flow root;
- every XBRL workflow records complete selected-form presentation and
  disclosure coverage; the stale-prior case records a redline and does not
  silently reuse the prior text;
- generated catalogue SHA-256:
  `c30f5436979e4a9c39dccac6a2f9e556f5d54eba2cb6a4437eba060559698854`;
- statutory-presentation rule-pack SHA-256:
  `d3808f0be5190d652031faa7ef489fe4552521f41dec2e295ff58fc5583cfcbb`;
- schedule-taxonomy rule-pack SHA-256:
  `3f90676d582862bcaa9a48a1f35b632c6b719198374bffb7e8220488bae590a5`;
- golden-suite input SHA-256:
  `19e7c8e0d5d3a92207cf72283cf9f423c19a444ad3ebfc373370b7626f807e88`;
- eight non-cash schedule workflows record complete per-cell adapter
  dispositions and emit representative official schedule facts;
- final controlled run manifest SHA-256:
  `3462fed35175c98519d42b9d2ab4aeda2ee63e0b7034ab3156e03fd0c7187a1d`;
- external TEBENI status: `NOT_RUN_USER_CONTROLLED`.

This evidence proves the controlled renderer and boundary paths used by the
suite. Together with the separate complete-primary-presentation audit it still
does not prove full note/schedule filing-content coverage, real-entity
classification quality, official rendering equivalence, or TEBENI
compatibility. Those gates remain open.
