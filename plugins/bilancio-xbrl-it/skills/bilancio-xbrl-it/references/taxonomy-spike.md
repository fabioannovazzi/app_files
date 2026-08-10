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

Observed on 2026-08-10 with the same package and catalogue after adding the
inventory-balance schedule trigger:

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
policy to select official presentation roots for fixed assets, inventories,
receivables, payables, equity, provisions, TFR, tax and
guarantees/commitments. It derives
the permitted descendants from the locked catalogue, requires a reviewed
mapping or omission for every normalized schedule cell, derives fact values
without model arithmetic, and reconciles any concept already emitted by the
primary presentation.

The checked audit at `scripts/audit_schedule_taxonomy.py` observed:

| Form | Schedule families | Permitted unique monetary table concepts | Route |
| --- | ---: | ---: | --- |
| Ordinary | 9 | 635 | `TABLE_FACTS` |
| Abbreviated | 9 | 465 | `TABLE_FACTS` |
| Micro | 9 | 0 | `TEXT_ONLY` |

The ordinary inventory SHA-256 is
`1a2a7faa9e444f3359f14f7ef8ab9c199c84a2abd882e5cff608b6334280baec`;
the abbreviated inventory SHA-256 is
`99efd0f104da6bfc6b699f37418766a22eca67fcf01e2b1cfc8cbb37574f2b4b`;
the micro inventory SHA-256 is
`4b967f4ee316a3aa2b31f28bab4cf77b8d7bc55a1b8d8d5844497b63e2a9ee0b`.
The adapter policy SHA-256 is
`030f62d38592dc7cd4a497c2695bed271246bc3aa149806c24ce1361397aa599`,
and the checked audit report SHA-256 is
`9ede099209c7bf9e4a2dd577ae1371e7a4251399294178a270637f9a28ecb020`.

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

Re-executed on 2026-08-10 with the package and catalogue above:

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
- the first-financial-year workflow ingests no comparative column, retains no
  comparative facts, and renders only current instant and duration contexts;
- generated catalogue SHA-256:
  `0699148330d4d905b85649a558efe94d1c0e40fcaea5c16d988f1699b9ffc30f`;
- statutory-presentation rule-pack SHA-256:
  `d7d8b189b36a5177c24954a1956253b89f9b14d2d39fbd0174b9a5df4a73b857`;
- schedule-taxonomy rule-pack SHA-256:
  `030f62d38592dc7cd4a497c2695bed271246bc3aa149806c24ce1361397aa599`;
- golden-suite input SHA-256:
  `2d7930aecbd42867b34260a5449702f755c86f61d33612111378e3d39aeef5a6`;
- all nine non-cash schedule families record complete per-cell adapter
  dispositions and emit representative official schedule facts; inventory is
  exercised by golden case 6 and emits the official total inventory-movement
  concept;
- final controlled run manifest SHA-256:
  `d3e2d8edb97bf7115971272cd745e89b313046e3d60a2d0858645197d71c28b2`;
- external TEBENI status: `NOT_RUN_USER_CONTROLLED`.

This evidence proves the controlled renderer and boundary paths used by the
suite. Together with the separate complete-primary-presentation audit it still
does not prove full note/schedule filing-content coverage, real-entity
classification quality, official rendering equivalence, or TEBENI
compatibility. Those gates remain open.
