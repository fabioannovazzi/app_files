# Agent-led PDF reading and reconciliation recovery

The host agent diagnoses unfamiliar registration layouts and may write a local
adapter in the active run. Local code checks source ownership, exact arithmetic
and frozen replay independently. The adapter proposes references to original
PDF words; it does not provide accounting values or qualification decisions.

## Execution contract

1. Preserve the same registered case, immutable input and recovery history.
2. Inspect targeted pages or export the local word inventory. The host chooses
   evidence and interprets structure using its normal tools and model account.
3. Revise a layout or write a run-local Python adapter. Snapshot its exact bytes
   and retain the reason for each revision. There are four distinct trials and
   twelve inspections/inventories per session.
4. The independent checker reads the original PDF again, reconstructs proposed
   values from referenced tokens, checks column/account ownership, monetary
   coverage, duplicate use, registration balances and printed running totals.
5. Retain readable entries and all unresolved issues even if qualification fails.
   JSON preserves complete evidence; CSV labels each row as unqualified.
6. A successful trial permits a fresh freeze replay. The frozen code/layout/source
   binding does not approve a mapping. Normalization and reconciliation still
   require their normal source-bound decisions, completeness and replay gates.
7. The existing incident outbox records handled inspection failures, subsequent
   attempts and fresh replay evidence under the original report identity.
   Extraction recovery cannot close the original task. The host resumes that
   task and verifies its actual outputs before using the existing recovery outcome.

Discovery is model-led; a frozen input, adapter and recipe can be replayed locally.
Local execution does not make the host model's processing local. The adapter
subprocess is not an OS sandbox and retains ordinary host permission boundaries.
It uses the existing Python environment, without dynamic package installation.
Installed code and validators are never rewritten by this recovery route.

## Initial scope and limits

- Text PDFs with reviewed physical amount/account bands. The adapter can resolve
  unfamiliar header and posting associations beyond the built-in header parser.
- The adapter route requires independently printed running controls on every
  page. Missing controls, OCR-only pages or unsupported amount syntax preserve
  available evidence but cannot qualify a complete population through this route.
- Source-reference and arithmetic checks cannot establish semantic correctness
  of every account/header association. The existing exact mapping review remains
  necessary; balanced totals are not semantic approval.
- A partial population is available for reading and diagnosis, while sampling,
  population statistics and complete reconciliation remain blocked.
- Adapter path and digest are bound to the reviewed layout. Moving the adapter
  requires a new valid layout/mapping binding; stale paths are not silently repaired.
- Technical reporting sends fixed method/check identifiers, flags and counts.
  PDF content, values, paths, adapter source, private stderr and free-text reasons
  stay local. The host may supplement the same incident with reviewed technical
  diagnosis. Local-only delivery retains the existing queue.
- Product-wide improvement remains a separate reviewed change with a regression
  fixture. A local correction is not a new product release or installed-host proof.

## Executable acceptance

`tests/plugins/test_agentic_pdf_recovery.py` checks an unfamiliar header recovered
by a host-authored adapter, exact fresh replay, normal reconciliation after mapping
review, and readable partial inspection with zero qualified movements. Negative
cases include a balanced omitted pair, duplicate amount ownership, invented
values/references, wrong sides/accounts/headers, incorrect printed totals, changed
code, invalid JSON and failed execution.

`tests/plugins/test_pdf_recovery_incidents.py` checks original-episode linkage,
cross-process identity preservation, offline/local-only retention, handled
inspection failure despite a successful helper exit, and exclusion of private
source values/code/reasons from transmitted evidence. Existing source, negative
amount, normalization, reconciliation, material replay and incident closure tests
continue to govern those boundaries.

Synthetic acceptance proves these tested paths. A real customer PDF and a fresh
installed-host conversation remain separate acceptance evidence.
