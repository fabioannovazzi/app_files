> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Check Entries Workflow Reference

## Deterministic Boundary

Journal Sampling owns raw journal parsing, reviewed mappings, source
qualification, and canonical monetary normalization. Check Entries validates
that sealed v2 output by replaying its complete assurance envelope, gates,
mapping decisions, source and implementation receipts, extracts PDF/XML facts,
performs exact comparisons, and binds results to receipts and lineage. The
normalized bytes are captured once. Before parsing them, Check Entries closes
the exact 24-file Journal Sampling/shared implementation tree and invokes the
isolated normalization replay CLI. Raw source plus the exact retained reviewed
recipe must reproduce the CSV byte-for-byte, the material diagnostics
projection, reviewed decisions, gates, envelope, and qualification-review
payload. Current receipts are checked again after support extraction before
commit.
Every support file is also captured exactly once; its receipt, parser, source
qualification, comparisons, and final assurance replay use that same capture.
For a directory selection, every nested file's canonical membership and
receipt are sealed in `support_manifest.json` and re-enumerated at final
validation. Unsupported file types fail qualification. Added, deleted,
replaced, Unicode/casefold-aliased, or duplicate support paths fail the run.
Temporary-prefixed files remain part of membership; symlinks, hardlink aliases,
and special filesystem entries are rejected.
Claude can inspect outputs and explain professional conclusions, but it must not
rewrite extracted evidence.

## Prepared Input

- `normalized_journal.csv` must use the ordered
  17-column `journal_sampling.normalization.v2` contract, including
  `currency`, `unit`, and `reported_increment`.
- Adjacent `normalization_diagnostics.json` must have a valid content hash,
  complete population status, qualified sources, closing row counts, and a
  valid CSV receipt.
- Exact debit, credit, signed amount, and absolute amount closure is rechecked.
- Source file/sheet/page/row, qualification ID, and stable prepared-entry ID
  are preserved. Movement numbers are never synthesized.

## Support Identity

- FatturaPA requires a distinctive invoice number in labelled invoice syntax
  plus a confirming amount or date signal. Generic numeric, year, and
  single-letter tokens remain review.
- PDF identity requires a distinctive labelled movement identifier in text
  extracted from the captured PDF. Filename occurrences never establish
  identity.
- An exact reviewed relationship can replace mechanical identity only when its
  receipt binds the prepared entry, support-artifact receipt, exact support
  locator, and non-empty recording exception.
- ZIP-member locators always include the captured archive path, for example
  `batch-a.zip!/invoice.xml`. A member name is never a global locator by itself,
  and the invoice-to-artifact map must bind that locator to the archive receipt.

## Currency And Direction

- Structured FatturaPA currency comes only from exact `Divisa`. PDF currency
  requires the expected three-letter ISO code or an exact reviewed currency
  decision. Symbols such as `$` are ambiguous, and an explicit conflicting ISO
  4217 code forces mismatch even when a reviewed symbol decision exists.
- FatturaPA preserves `TipoDocumento` and bounded positive/negative document
  polarity as diagnostic facts. Neither fact identifies the journal account
  line or debit/credit side being tested.
- PDF invoice/credit-note labels likewise preserve document polarity only; they
  do not determine the journal side.
- Direction closes only through an exact reviewed `check_entries_direction`
  receipt bound to the normalized journal, prepared entry, captured support
  receipt, and exact locator. A stale or opposite-side decision is rejected.
  Without a valid receipt, signed support values and differences are withheld
  and the row remains manual review.
- Magnitude still uses exact Decimal tolerance, but magnitude alone can never
  pass: `amount_signed` direction closes independently.

## Party Perimeter

- Mechanical `ok` requires an exact reviewed party perimeter in addition to
  identity, amount, date, and currency.
- Prefer reviewed tax IDs. Exact names are supported only for structured XML
  under the explicit reviewed `casefold_alnum_v1` normalization contract.
- A PDF tax ID must be coupled to the reviewed supplier/customer role label.
  A generic tax label is role-unresolved and the opposite role is a mismatch.
- Free-text PDF name or beneficiary containment is diagnostic and never
  promotes a result.
- When the journal genuinely lacks party evidence, an exact reviewed support
  relationship and its recording exception can close the relationship without
  pretending a free-text party match occurred.

The recipe stores these judgments as shared
`vera.reviewed_decision_receipt.v1` objects:

- `reviewed_party_perimeters` uses decision type
  `check_entries_party_perimeter`, adapter
  `check_entries.party_perimeter@1`, and the exact
  `source.normalized_journal` binding. Its content binds one
  `prepared_entry_id`, expected role, reviewed tax IDs/names, and any explicit
  name-normalization contract.
- `reviewed_support_relationships` uses decision type
  `check_entries_support_relationship`, adapter
  `check_entries.relationship@1`, and exact normalized-journal plus support
  artifact bindings. Its content binds one prepared entry, artifact ID,
  support locator, confirmed status, and recording exception.
- `reviewed_currency_decisions` uses decision type
  `check_entries_currency`, adapter `check_entries.currency@1`, and exact
  normalized-journal, PDF artifact, prepared-entry, and PDF-locator bindings.
  Its content records the entry currency, confirmed status, and non-empty
  recording exception.
- `reviewed_direction_decisions` uses decision type
  `check_entries_direction`, adapter `check_entries.direction@1`, and the same
  exact source/entry/support bindings. Its expected direction must equal the
  sealed journal `amount_signed` direction.

Claude may prepare these objects after a reviewer makes the judgment, but must
not invent reviewer identity, review date, party perimeter, relationship, or
recording exception. Without a valid source-bound receipt, the row remains
manual review.

## Source Qualification And Replay

- Every PDF, XML, ZIP, and P7M support artifact has a separate source
  qualification. PDF readability is qualified separately from identity.
- FatturaPA parsing is byte-, member-, compression-, path-, and structure-
  bounded. A parse error withholds all invoices from that artifact.
- P7M is unsupported until a bounded decoder and signature-validation policy
  is implemented.
- A failed qualification, parse error, or missing support prevents a passed
  global source gate.
- `amount_signed`, `amount_abs`, exact signed support amount, signed and
  absolute differences, and any passing `amount_found` are bound through exact
  source, prepared CSV, result CSV, and XLSX locators in
  `numeric_evidence_ledger.json`. Difference arithmetic is replayed with
  Decimal.
- XLSX is generated and canonicalized twice; only byte-identical OOXML is
  receipted. The assurance envelope is also rebuilt twice for equality.
- Successful runs are fresh-directory builds: stale review decisions and
  revision trees are removed. Any early or late failure restores the exact
  prior run tree.

## Review Statuses

- `ok`: unique explicit or reviewed support, exact party perimeter (or reviewed
  recording exception), and required amount, date, currency, and direction
  checks passed.
- `mismatch`: one or more deterministic checks failed.
- `missing_support`: no explicit unique PDF/XML support was found.
- `manual_review`: support is ambiguous, reused, or required checks are absent.

Every status is a mechanical fact. `professional_conclusion` remains
`pending_review`, and reconciliation/semantic-review/reporting/publication
gates remain independent.

## Review UI Contract

After the deterministic run, use `checks/review_payload.json` as the
structured review contract for the MCP widget or Markdown fallback. The payload
is bounded and selected for review; it does not replace `check_results.csv`,
`check_results.xlsx`, `pdf_inventory.json`, `check_audit.json`, or
`review_notes.md` as the full evidence set.

The payload's canonical digest binds `ui_decisions.json` and
`applied_decisions.json` to exact review bytes. The MCP rejects stale bindings.
Before any save or apply write, the immutable caller run-intake projection must
equal persisted `run_intake.json`; only the append-only local execution trace is
excluded. Before apply, the MCP also replays persisted local assurance; caller
summaries cannot grant final readiness. A structured edit is accepted only when
the receipted original proves that exactly the authorized `review_notes` cells
changed. Native outputs and affected receipts are then regenerated and
`assurance_envelope.json` is resealed. Accept-only decisions are also receipted
and resealed. Review completion never overrides independent assurance gates.
All MCP-controlled save/apply writes run in a private staged tree. The prior
tree remains rollback material until the staged tree passes filesystem safety
validation and commits. Internal symlinks, hardlink aliases, special entries,
and post-preflight path swaps fail closed. Revision, CSV, XLSX, envelope,
manifest, or final trace failure restores the exact prior tree.

For an assured run, validation is not limited to replaying local hashes.
`execution_recipe.json` preserves and receipts the exact recipe bytes used by
the run. Each Python preflight reconstructs a fresh baseline from the original
normalized journal, current support source, and original recipe in a private
directory. The persisted support facts, immutable result projection, result
CSV/XLSX, numeric evidence ledger, material audit/review/intake fields, gates,
professional conclusion, and final status must agree with that reconstruction.
A reviewed successor may contain only the receipted decision extension and the
authorized `review_notes` delta. Missing or changed source/recipe material is a
closed failure. Validate, render, save, and apply all perform this replay.

Supported Python launchers must be invoked with `python -I -B`. Their first
local action snapshots the bootstrap without following aliases and validates
the exact 26-file Check Entries/shared-assurance implementation tree before any
local implementation import. Unowned entries, bytecode caches, symlinks,
hardlinks, FIFOs, and other special entries are rejected. The validated
assurance package is loaded by exact path, without adding its broader vendor
parent to the executable import search path. The same physical closure is
applied to the owned Journal Sampling implementation tree before upstream
receipt replay and before its isolated normalization re-performance process.

This boundary does not authenticate the mutable package or the reviewer. Local
receipts and self-hashes remain consistency evidence rather than an external
trust root. Re-performance rejects stale self-resealed preparation but cannot
distinguish a fully regenerated internally consistent package from one approved
by an authorized reviewer. Publication remains withheld pending separately
established package attestation and reviewer authority.

## Improvement Policy

When a run exposes a missing parser, brittle matching rule, or repetitive manual step, Claude should offer to draft a concise GitHub issue for the repository. Creating the issue still requires the user's confirmation.
