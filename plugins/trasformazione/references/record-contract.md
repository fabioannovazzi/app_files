# Prototype record contract

The operator declares synthetic inputs; this is not a personal-data detector or
an authenticated multi-user case system. Storage is under one explicit local
case folder. Do not use the prototype for live mandates.

`CaseStore` in `scripts/transform_case.py` is the public Python API. The CLI uses
the same API. Each operation stores a complete new JSON snapshot under `history/`.
Snapshots bind the previous digest; reads reject edited histories or evidence.
Imported files are copied as inert bytes under `evidence/<sha256>`. No parser,
shell, model call, connector, deadline engine or filing adapter is invoked.

Create with `init --id DEMO --owner 'Synthetic operator' --purpose 'Synthetic
review' --synthetic-only`. `update-case --json <file> --actor <name>` sets case
attributes without changing its stable ID, jurisdiction or original owner.

`put <kind> --json <file> --actor <name>` accepts the exact fields declared in
`KINDS` plus `id` and `dependencies`. Unknown sensitive fields remain `null`.
Numeric values must be decimal or rational strings, such as `"0"` or `"1/3"`;
float and boolean numbers are rejected. Numeric strings are limited to 100
characters and exponent notation is rejected to bound arithmetic resources.
For a numeric field a reasoned
`{"not_applicable": "reason"}` is distinct from unknown and zero. It cannot be
used as an arithmetic operand. `version` is assigned by the store.

Supported objects: Case (case metadata), Evidence (import only), Finding,
ParticipantRight (`participant`), CreditorPosition (`creditor`), ReserveLayer
(`reserve`), AssetBridge (`asset`), Deadline, ReviewDecision (review only), and
ResearchIssue (`issue`). `source` and `calculation` are additional mechanical
support records. Case versions and historical review decisions are retained.

A dependency is `kind:id` or `kind:id#field`. Missing records and required null
fields block only branches whose transitive dependencies include them. Cycles
are invalid. Dependencies are explicit model/reviewer proposals; Python does
not infer semantic relevance. A `source` must include its `evidence:id` snapshot
in dependencies. Norm/interpretation findings require source references.

Example finding:

```json
{"id":"F1","category":"fact","statement":"Synthetic valuation reports assets of 700000.","rationale":"Selected synthetic valuation, row 1.","alternatives":[],"confidence":"synthetic_unverified","dependencies":["evidence:valuation"]}
```

Branches declare title, owner, next step and references. A branch without
findings is evidence_pending; populated unblocked proposals are analysis_ready.
`submit` binds the current proposal digest for review. `review` requires that
exact digest, a nonblank reviewer and reason, and approve/request_changes.
Approval means only synthetic preparation. Changed dependent data or source
snapshots mark the branch stale; unchanged independent reviews remain current.
`blockers` remain visible even when a stale branch also has missing evidence.
Any case-wide material metadata change invalidates all branch approvals.
Superseded object versions remain in history; there is no delete operation.

The prototype does not implement `ready_for_external_action`, `executed` or
`reconciled`. Deadline approved dates and receipts are rejected. No passage of
time supplies consent or resolves a creditor position. Legal/tax determinations,
calculation input extraction and correspondence to documents remain model and
professional work. Arithmetic results from a stale proposal are historical,
not automatically recomputed from new document text.

`export` writes a versioned `dossier.md`, full `case.json` and file hash manifest.
This is a local reviewable deliverable, not a signed legal file. The 46-scenario
matrix distinguishes implementation tests from professional acceptance.
