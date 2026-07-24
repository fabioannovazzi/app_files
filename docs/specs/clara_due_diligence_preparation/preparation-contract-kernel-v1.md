# Clara preparation contract kernel v1

Status: M3 contract note
Scope: audit envelope and validation boundary only

## Evidence and permitted claim

M1 proves exact transport of a reviewed public-fact fixture, precision-aware
reconciliation, statement identities, and abstention from unsupported monthly
facts. M2 proves exact execution of one reviewed synthetic account mapping,
source-row conservation, statement identities, public tie-outs, deterministic
outputs, and a prepared-evidence manifest.

The common claim is deliberately narrow:

> Clara can bind reviewed inputs and decisions to a registered deterministic
> preparation, verify mechanical reconciliations, and emit a reproducible audit
> envelope without treating those checks as semantic or publication approval.

The fixtures do not prove remote-source authenticity, reviewer authorization,
semantic correctness, row-level lineage, real-data resilience, or report
readiness.

## Why the kernel is deterministic

The kernel is deterministic only where correctness is mechanically verifiable
or auditability requires exact reproduction. It may validate schemas, canonical
identifiers, byte hashes, exact Decimal values, references, status consistency,
lineage coverage claims, reconciliation arithmetic, and canonical output bytes.

It may not select authoritative sources, infer business meaning, approve a
mapping or relationship, choose a tolerance or perimeter, decide economic
validity, or overrule reviewed judgement. A model or person authors or reviews
those decisions. The registered producer executes the case-owned contract, the
adapter replays it, and the kernel validates the resulting receipts and
consistency.

## Canonical audit envelope

`clara.preparation_audit_envelope.v1` has these required top-level fields and no
undeclared fields:

| Field | Required content |
| --- | --- |
| `schema_version` | Exact schema identifier |
| `case` | Case ID, case-owned kind, source schema, and case-artifact reference |
| `adapter` | Adapter ID/version, implementation SHA-256, and `audit_only` scope |
| `local_artifacts` | Ordered local file receipts |
| `remote_sources` | Ordered declared remote-source receipts |
| `reviewed_decisions` | Ordered decision-presence receipts |
| `execution` | Explicit producer receipt and input/output artifact references |
| `numeric_policy` | Decimal-string and case-owned constraint receipt |
| `reconciliation` | Required checks and preserved errors |
| `lineage` | Separate artifact, aggregate, and row declarations |
| `statuses` | Independent gate statuses defined below |
| `report_ready` | Always `false` in this audit-only contract |
| `limitations` | Non-empty ordered statements of what the envelope does not prove |

Every `local_artifacts` record contains `artifact_id`, a case-owned `role`,
relative `path`, `byte_count`, lowercase `sha256`, and optionally `media_type`.
The adapter and preparation producer are each byte-bound. The kernel itself is
also an artifact reference. Exactly one `audit_schema` artifact binds the
versioned JSON Schema, so changes to either validation implementation remain
visible.

The kernel rejects duplicate IDs, absolute or escaping paths, symlink escapes,
missing files, digest or byte-count mismatches, malformed values, unknown
references, and non-canonical ordering. Artifacts, receipts, decisions,
checks, errors, lineage IDs, limitations, and every reference list are sorted
by stable identifier. The envelope contains no generated timestamp, so the
same files and declarations produce identical bytes.

## Status separation

`statuses` contains exactly `validation`, `preparation`, `reconciliation`,
`semantic`, `source`, `downstream`, and `publication`. Each contains `status`,
`basis`, and evidence references.

- Mechanical statuses may be `passed`, `failed`, `blocked`, or
  `not_assessed`.
- Semantic and downstream status remain `not_assessed` in v1 because M3 does
  not validate them.
- Source status may be `receipt_only`; v1 does not claim remote-byte
  authentication.
- Publication remains `withheld` for both benchmarks. `emitted` is rejected by
  the runtime validator because external publication is outside this envelope.

A status records one gate only. Preparation or reconciliation success never
implies semantic approval, downstream compatibility, report readiness, or
publication.

## Source receipts and authenticity

Each source receipt contains `source_id`, title, document type, HTTPS URL, byte
count, SHA-256, and `receipt_scope: declared_remote_receipt`. Publisher and
document date are included only when the source contract actually records them;
case-specific fields remain under optional `metadata`. An adapter may not
invent a publisher or reinterpret a filed date merely to fill a generic field.

The registered adapters copy declared receipt metadata from the hash-bound case
contract. Runtime validation checks canonical shape, ordering, and reference
closure; it does not independently compare each receipt field with the case
artifact. The remote bytes are not packaged by either fixture, so both adapters
record `source.status: receipt_only`. Neither the kernel nor the adapters infer
that a source is authentic, authoritative, relevant, complete, or correctly
interpreted.

## Reviewed decisions

Each reviewed-decision receipt contains `decision_id`, a case-owned decision
kind, source-preserved `status: reviewed`, basis, uninterpreted JSON `content`,
the canonical JSON content SHA-256, and evidence references. Review date,
version, and reviewer are optional because the source fixtures do not prove a
universal approval model.

The kernel validates presence, format, content identity, and reference closure.
The receipt builder rejects any source status other than `reviewed`; it never
upgrades a draft or missing status. The kernel does not determine whether the
decision is semantically correct or whether the recorded reviewer had
authority. That missing authorization remains part of the semantic and
publication limitations.

## Lineage levels

`lineage` contains separate `artifact`, `aggregate`, and `row` objects. Each
declares whether that level is available, lists typed records, and states its
limitations.

- Artifact records bind a whole artifact to input, source, decision, and other
  lineage references.
- Aggregate records bind case-owned group metadata without defining its
  business aggregation semantics. Each record must resolve a JSON Pointer in a
  hash-bound producer-output `aggregate_lineage_evidence` artifact, match the
  canonical hash of the located value, locate the declared aggregate ID, and
  locate the exact output artifact ID and digest. Assigning a role label or
  pointing at unrelated JSON is insufficient. These checks establish metadata
  identity, not the semantic validity of the declared provenance.
- Row lineage is always undeclared in v1. Neither benchmark proves a registered
  row-lineage evidence contract, so no artifact label can enable it.

An envelope may claim only the finest level its artifact actually contains.
M1 provides artifact lineage plus fact-to-source locators. Successful M2
provides content-bound aggregate account and dependency metadata and separately
retains hash-bound source-row conservation evidence. Neither currently proves
full row-level lineage.

Derivation references are separate from control evidence. M2 monthly values
derive from the trial balance, mapping, and registered engine; the five public
filings support reconciliation controls and are not represented as causes of
every monthly value.

## Reconciliation and fail-closed publication

`reconciliation` contains sorted required checks and preserved errors. A check
has a case-owned kind, status, references, optional canonical Decimal evidence,
and uninterpreted details. This is deliberately not a formula language.
Tolerance and materiality selection remain judgement inputs. M3 preserves any
source-declared review status but does not infer approval; deterministic code
only applies the supplied case policy.

The validator rejects a passed reconciliation status when any required check
failed, was not run, or an error exists. It also rejects stale hashes, unknown
references, binary floats, non-canonical Decimal evidence, `report_ready:
true`, row-lineage overstatement, and `publication.status: emitted`.

The shared numeric rule is finite, non-exponent, canonical Decimal-string
syntax. It does not impose M2's 38-digit or six-decimal-place limits on other
cases. A producer may apply explicit case-owned precision and scale bounds;
those constraints remain recorded and hash-bound in `numeric_policy`. Shared
arithmetic derives sufficient working precision from its operands unless a
case explicitly supplies a recorded calculation-precision policy.

## Explicit exclusions

M3 does not define:

- a universal crosswalk schema;
- a formula or transformation DSL;
- a generic dataset-relationship or join model;
- a dataset semantic layer;
- source selection, semantic classification, materiality, or approval logic;
- Reporting Engine or evidence-bundle integration;
- an analysis or report orchestrator.

Crosswalks, formulas, and relationships remain versioned, hashed,
recipe-specific assets executed by registered code. The semantic layer and
report/evidence handoff remain M4 work. Orchestration remains deferred.

## M1 and M2 adapter expectations

Adapters are offline, deterministic reshaping layers. They must preserve source
values, hashes, limitations, and failure states; they may not repair, enrich, or
approve evidence.

The M1 adapter:

- binds the benchmark, truth, expected, candidate, source receipts, assertions,
  and reviewed disclosure boundary;
- deterministically replays the registered validator and requires the complete
  supplied report to match, rather than trusting its pass status or receipts;
- records source verification as `receipt_only`;
- records preparation and downstream checks as `not_assessed`;
- preserves reconciliation and abstention results;
- records publication as `withheld`, regardless of benchmark success;
- claims no finer than artifact lineage.

The M2 adapter:

- binds the case, three input assets, reviewed mapping and scope relationship,
  registered engine, reconciliation, outputs, and disclosure boundary;
- deterministically replays the registered engine in a temporary directory and
  requires the complete producer-owned file set and every byte to match;
- preserves failed runs with only `reconciliation.json` and
  `unmapped_accounts.csv`; stale success artifacts make the envelope fail;
- preserves `synthetic_benchmark_only` by recording publication as `withheld`;
- preserves downstream checks as `not_assessed`;
- records source verification as `receipt_only`;
- claims aggregate, not row, lineage;
- does not promote WD-40 statement lines, SEC-only sources, twelve calendar
  months, zero tolerance, or one-to-one account mappings into kernel rules.

If required decision accountability or authorization is absent, semantic
status remains `not_assessed` and publication remains withheld.

## Definition of done

M3 is complete when:

1. the envelope schema and validator implement only the fields and boundaries
   above;
2. M1 and M2 adapters emit canonical byte-identical envelopes from frozen
   fixtures without changing those fixtures;
3. referenced local artifacts, producer and engine bytes, reviewed-decision
   content, numeric constraints, outputs, and located aggregate-evidence values
   are digest-bound; remote-source receipts remain declared metadata;
4. status contradictions and unsupported facts fail closed;
5. tests cover clean adapters, stale or internally resealed producer outputs,
   genuine failed runs, schema validity, duplicate IDs, path escape, digest
   drift, unknown references, decision-status promotion, content-drifted
   decision receipts, lineage-evidence drift, role-only lineage claims,
   reconciliation inconsistency, binary floats, non-canonical numeric
   evidence, report-readiness overstatement, and publication escalation; the
   retained M1 and M2 tests continue to cover unsupported facts and synthetic
   labelling;
6. the tests run offline and prove byte determinism;
7. both adapted fixtures remain withheld, with unknown review
   authorization, remote authenticity, row lineage, and downstream readiness
   visible rather than inferred;
8. no crosswalk model, formula DSL, relationship model, semantic layer,
   reporting handoff, or orchestrator is introduced.
