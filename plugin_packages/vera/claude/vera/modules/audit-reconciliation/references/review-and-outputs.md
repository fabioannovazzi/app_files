> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Review And Outputs

Load this reference when producing delivery workpapers, reviewing deterministic classifications, or preparing operational follow-up requests.

## Claude Review Layer

After every deterministic run intended for delivery, build and review a reproducible sample containing at minimum:

- 10 highest-value in-scope rows;
- all rows with bank, factoring/operator, compensation, or other mandatory closure evidence;
- a stable random sample of at least 20 remaining in-scope rows;
- any user-challenged rows.

The reviewable population must have exactly one review row per `record_id`,
with no missing, unknown, or duplicate IDs. Record `PASS`, `FAIL`, or
`UNRESOLVED`, a canonical `reviewer_ref`, and ISO `reviewed_on` no later than
the sealed run date; status text alone is not a completed professional review.
`reviewer_ref` is only an unsigned, unauthenticated label. Treat it as untrusted
metadata, never as proof of the reviewer's identity or authorization.

If any `FAIL` exists, stop, patch deterministic logic or extraction, rerun reconciliation, rebuild the review packet, and repeat review before delivery. Do not deliver final Excel/Word as audit-ready while required review rows are still `PENDING`.

The assurance gate register keeps source, preparation, reconciliation,
semantic review, reporting, and publication independent. A click cannot waive
a failed deterministic check. A pending, skipped, unresolved, reviewer-unbound,
or failed required review keeps semantic review withheld/failed and reporting
blocked until native outputs are regenerated and all receipts replay.
Even a previously passing gate file cannot authorize a later review
application: every new applied decision requires native regeneration and a new
assurance seal. On the first apply, the same copy-on-write transaction retains
an exact predecessor transition under
`assurance_transition_history/<predecessor-seal-content-sha256>/`. Replay
requires the exact predecessor seal, professional review, final reconciliation,
and review payload bytes; the ordered review-item-to-record mapping; the exact
applied decisions and effects; the rederived successor professional review; and
the deterministic transition receipt. It also retains `predecessor_run/`, a
complete predecessor run snapshot, and freshly executes the full assurance
replay against that snapshot. The selected transition evidence must match its
snapshot counterpart exactly, including the seal whose run date must agree
with the receipted prepared assumptions. Missing, changed, expanded, reordered,
contradictory, or path-forged history blocks the successor and rolls back the
whole candidate.

Before any first apply, the caller must retain the predecessor seal
`content_sha256` through a separate review channel and pass it as
`expected_predecessor_checkpoint`. Pass the same external checkpoint into the
successor rebuild and every successor replay. The candidate tree is not an
authority for this value. Missing or unequal checkpoints block without writes;
the separate channel's trust and authorization remain outside this mechanical
control. Replay rederives predecessor reconciliation rows, allocation ledgers,
and core checks from the retained prepared population.

## Operational Review Sample

When the user wants a few rows to inspect with a client or reviewer, run `scripts/build_review_sample.py` after the reconciliation workbook exists. This is a post-run review aid, not a replacement for deterministic classification.

Example:

```bash
python scripts/build_review_sample.py <output-dir>/riconciliazione_audit.xlsx --count 2
```

The script creates `campione_movimenti_da_controllare.xlsx` and `testo_richiesta_controllo.md`.

Keep technical rule codes in the audit workbook, but avoid exposing them in emails or reviewer requests. Use operational wording such as "risulta ancora aperta, ma trova riscontro nei mastrini", "il riscontro e stato trovato sommando piu righe dello stesso documento", and "serve verificare se esistono pagamenti, incassi, compensazioni, storni o giroconti".

## Outputs

For audit workpapers, create Excel and Word outputs when useful:

```text
<output-dir>/
  riconciliazione_audit.xlsx
  relazione_riconciliazione_audit.docx
  source_pages.json
  prepared_records.json
  reconciliation_results.json
  assurance_receipts.json
  assurance_gates.json
  numeric_evidence_ledger.json
  final_output_inventory.json
  assurance_final_outputs/
    reconciliation_results.json
```

The workbook should preserve assumptions, source inventory, extracted source pages, normalized records, reconciliation detail, summary, checks, professional review rows, bank allocation candidates, external evidence details, and ledger/journal controls where relevant.

The sealed `assurance_final_outputs/reconciliation_results.json` is the
versioned canonical machine-readable record. It contains source-processing
diagnostics and analysis schedules in named sections built from the same rows
as the workbook. Do not write a standalone JSON projection for each workbook
sheet. Extraction failures must also appear in the review payload and the
workbook's source-processing-issues sheet.

Every row-level conclusion must show source reference, document number/date/amount, evidence type, deterministic rule, matched evidence reference, and missing evidence or next step when unresolved.

`assurance_final_outputs/` is the promoted delivery boundary. Its declared path
set must equal its physical ordinary single-link file set exactly; symlinks,
hardlinks, and special files fail. Every file must pass a fresh byte receipt
replay. Allocation and residual addresses refer to the
sealed `reconciliation_results.json`; material row values link source,
`prepared_records.json`, reconciliation output, and every declared
Excel/Word/JSON location with record identity. Missing workbook sheets or
columns cannot fall back to JSON-only coverage. Build and replay this tree in
staging before transactional promotion.

## Missing Evidence Wording

When evidence is missing, state the operational next step, such as:

- official bank statement, bank receipt, or bank accounting detail for the cited movement;
- allocation schedule tying a batch payment to specific rows;
- factoring/operator statement tying document number and amount to settlement;
- compensation agreement or accounting support tied to the specific rows;
- readable export/OCR for files that could not be extracted.

Avoid saying that no evidence is missing for rows that are not proven closed.
