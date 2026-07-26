# Assurance Workflow Reference

Load this reference for the mechanical assurance sequence. It deliberately does
not decide source meaning, materiality, evidence sufficiency, or an accounting
conclusion.

## 1. Intake boundary

Inventory the visible regular files in the input folder and capture a full-byte
artifact receipt for each. The source set is exact: a missing, additional, or
changed file makes the prior boundary stale.

For every source, record a `reviewed_source_decisions` entry with exactly:

- `role` and `adapter_family`;
- `reviewer_ref` and `reviewed_on`;
- `perimeter`: `entity_ref`, `party_ref`, `currency`, `unit`,
  `direction_policy`, and `allocation_policy`;
- `money`: `decimal_separator`, `thousands_separator`, `reported_unit`, and
  `reported_increment`, which is currently supported only when it is exactly
  `0.01`;
- `date.order`: exactly `day_first` or `month_first`.

The v2 reviewed decision receipt cites exactly one byte-bound source artifact,
uses its expected decision ID/path/adapter, and has canonical reviewer identity
and ISO review date no later than the sealed `assurance_run_date`. Filename or
text suggestions do not authorize extraction. Each source also requires one
qualification with the reviewed mapping reference before preparation.
Unsupported, unreviewed, or invalid-date sources emit no prepared or
reconciliation rows and cannot produce final artifacts.

Canonical syntax does not authenticate a person: every `reviewer_ref` is an
unsigned, unauthenticated, untrusted label. The seal proves only which label
and review claim were recorded in the replayed bytes.

## 2. Preparation boundary

Parse money with exact `Decimal` arithmetic. Reject binary floats, ambiguous
punctuation, and amounts that are not exact cent multiples. A source declaring
another increment is rejected before any prepared row; no downstream renderer
may round a more precise source value to cents.
Attach the reviewed perimeter to every emitted row.

Immediately before preparation, replay source, decision, and implementation
receipts and the exact qualification set. Bind every prepared record ID and
value to one current source locator. Write `prepared_records.json` atomically,
receipt it, and replay the complete set. A stale or unaddressable source stops
before reconciliation or final promotion.

The implementation boundary is one code-owned, ordered 25-file contract:
3 assets, 1 MCP server, 8 executable workflow scripts (including the
pre-import bootstrap), 5 retained internal source units, and 8 shared assurance
files. Every public Python entrypoint first executes that bootstrap source,
disables local bytecode, and validates the exact implementation tree before
importing plugin or shared modules. The five internal units are deliberately
stored under `scripts/retained_sources/` with a non-`.py` suffix. Ordinary
Python import cannot resolve them; only the bootstrap opens their stable
single-link bytes and loads their internal module names after tree closure.
Direct import of those internals is unsupported. No cache namespace is
ignored. Missing, additional, reordered, changed, linked, or special entries
fail, including regular files and empty directories beneath `__pycache__`; a
run cannot expand the list by editing its own receipts. The MCP server performs
the same tree check before reading its manifest and again before every public
RPC surface.

The launcher descriptors `.codex-plugin/plugin.json`, `.mcp.json`, and
`.app.json` are outside this in-process 25-file boundary. The Codex host reads
them before the validated process starts, so this replay does not attest the
host's initial executable selection. Arbitrary code already executing as the
same operating-system user is likewise outside this in-process boundary.

## 3. Reconciliation boundary

Match only compatible entity, party, currency, and unit perimeters. A row-level
closure requires row-level evidence. Allocation ledgers declare the reviewed
relationship shape, prevent prohibited reuse, and conserve exact source and
target amounts. Record all allocation and residual values; a material residual
is never rounded or forced to zero.

## 4. Reporting boundary

Write native Excel/Word and JSON outputs, then copy only declared delivery files
into `assurance_final_outputs/`. The expected basenames are closed in a sealed
workflow output contract before the boundary is inspected; current-tree
discovery never expands that contract. `final_output_inventory.json` lists
every regular file and its full-byte receipt. Declared and physical path sets
must be identical, so an injected regular file is a replay failure.

`numeric_evidence_ledger.json` addresses each material amount from a source
artifact through `prepared_records.json` to `reconciliation_results.json` and
every declared workbook/Word/JSON location that contains it. Each locator
replays record identity and value together. A missing or wrong sheet/column
cannot degrade to JSON-only coverage; an output that cannot be addressed is
withheld. Allocation/residual addresses point to the sealed reconciliation
result artifact.

Expected output files must be ordinary single-link regular files. Symlinks,
hardlinks, special files, missing paths, injected paths, and empty injected
directories fail replay. The seal records the exact physical file-and-directory
closure at the run root and final-output boundary. Finalization runs under the
whole-run transaction; a late failure restores the exact prior tree. Browser
save/apply writes use a sibling working copy and promote only a validated
whole-tree result.

## 5. Gates and promotion

`assurance_gates.json` contains six independent gates:

- `source`: every input is current and qualified;
- `preparation`: current implementation and prepared-population receipts pass;
- `reconciliation`: mechanical checks and allocation conservation pass;
- `semantic_review`: required review is complete, all rows are `PASS`, and each
  reviewable record ID appears exactly once, with no unknown/missing/duplicate
  IDs and canonical reviewer identity/ISO date no later than the sealed run
  date;
- `reporting`: all upstream reporting dependencies pass;
- `publication`: always `withheld` until a separate authorized publication.

Use `failed` for a failed control, `withheld` for a required judgment/action not
yet completed, and `blocked` for a downstream gate whose dependency did not
pass. Never describe a pending required review as success.

`assurance_receipts.json` seals the output contract and embedded controls.
Before review/application status can advance, replay that seal, the independent
gate file, source/implementation/prepared receipts, numeric/allocation ledgers,
the exact root/final physical closure, and the exact final-output inventory.
The MCP terminal path invokes this same complete Python replay; it has no
shorter terminal-ready validator. Applying a new review decision is itself new
run state: native outputs and the assurance seal must be regenerated before the
application can become `final_ready`.

The first review application also retains its predecessor transition within
the same copy-on-write candidate. The content-addressed directory
`assurance_transition_history/<predecessor-seal-content-sha256>/` has an exact
nine-entry contract: the prior eight transition files plus
`predecessor_run/`, a complete physical snapshot of the validated predecessor
run. Successor validation runs `validate_assurance_run` against that snapshot,
requires the replayed seal to equal the selected archived seal, and requires
the selected professional review, final reconciliation, and review payload
bytes to equal their snapshot counterparts. This freshly replays the
predecessor run date, prepared assumptions and receipts, material values,
gates, final inventory, and exact run-tree closure before rederiving the
mapping, decision fingerprint, professional-review records, and successor
authority. Missing, changed, expanded, reordered, contradictory, or
path-forged history fails. Capture, retention, replay, and promotion share the
existing whole-tree rollback boundary.

A successor additionally requires
`expected_predecessor_checkpoint`, the prior seal's 64-hex
`content_sha256`, supplied by the caller from a separate review channel. It is
required on the first apply, successor rebuild, and successor validation; it is
never inferred from the candidate output tree, transition history, or current
assumptions. Missing or unequal checkpoints fail before mutation and preserve
the prior tree. The checkpoint makes a fully resealed replacement detectable
even when an attacker consistently replaces amounts, currency, cut-off, run
date, run identity, scope year, or tolerance. The replay also deterministically
reruns predecessor reconciliation rows, allocation ledgers, and core checks
from the retained prepared population. `run_id` is an explicit assurance-seal
field, so changing run identity changes the seal digest.

For isolated replay, use:

```bash
python -I -B scripts/audit_assurance.py validate-run-json <output-folder> \
  --expected-predecessor-checkpoint <retained-64-hex-sha256>
```

The checkpoint proves byte-digest equality only. Its authority depends on the
separate channel used to retain and supply it; this workflow neither
authenticates that channel nor upgrades `reviewer_ref` beyond an unsigned,
unauthenticated, untrusted label.

## Professional judgment boundary

The controls verify identity, exact arithmetic, conservation, replay, and
declared file sets. A qualified professional remains responsible for source
meaning, accounting perimeter, materiality, evidence sufficiency, review
findings, and the final accounting/audit conclusion.
