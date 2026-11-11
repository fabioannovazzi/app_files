> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Proposed entries in the existing reconciliation panel

Use this mode only for an explicitly requested accounting-proposal review. It
does not execute or attest the Journal-Bank or Open-item matcher. Preserve the
original bank population and every proposal independently of reviewer decisions.

Import the user's selected bank and ledger originals and one agent-authored
`Batch_proposte_139_UI.json`-style source with schema fields `company`,
`bank_account`, `notice`, `items` and source receipts. Each item has a stable
`id`, a human-readable `title`, `bank` (date, exact decimal amount, description,
source), `proposed_lines`, reason and evidence. Counterpart lines use `account`,
`side` (D/A), exact decimal `amount`, optional `partita`, `year`, `section`.
Movements have no saved decision initially. The editor preselects acceptance only
when there is no saved choice or recovered draft; this does not save or accept
anything. Empty counterpart lists retain unresolved movements.

Prepare and start one bound `journal-bank-reconciliation` Archive work labelled
as proposed accounting entries. Through `vera_execute`, component
`journal-bank-reconciliation`, run `scripts/prepare_posting_review.py` with
`--client-engagement <returned context.json> --batch-input-id <registered input>`.
This product-owned helper validates the unchanged portable source context and
creates the proposal review, not a reconciliation assurance receipt. An identical
retry reopens the same proposal batch. Never hand-write managed inputs or fabricate
a professional decision, assurance report or native binding.

Use `vera_open_review` with the actual client, engagement and run. In the same
panel the operator can edit counterpart accounts, D/A, amounts, invoice partita,
year and section; save pending, accepted or rejected decisions; add/remove lines;
and discuss a selected entry. Unsent drafts are distinct from saved decisions.
The proposal-type filters cover the complete retained population before paging.
They project the saved proposal labels (or the absence of original counterpart
lines), never infer confidence or recalculate matches. Saved pending decisions
are visibly distinct from never-saved movements. “Scarta modifiche” clears only
the operator's unfinished draft and restores the saved decision or original
proposal; an unchanged unresolved movement needs no save before navigation.
Accepted entries must balance against their fixed bank movement. Partita fields
must be supplied together in valid numeric formats or all left empty for an
account-only counterpart. There is no separate acknowledgement checkbox. Do not
treat an internal document number as a verified partita just because the draft
assumed equality.

The accounting comparison shows the fixed bank line, editable counterparts and
live Dare/Avere/difference totals using exact cents. Italian entry accepts
`1.030,46` and `1030,46`, and an ungrouped decimal point with at most two decimals;
dot grouping requires explicit comma cents to avoid ambiguity. Mixed, ambiguous
or overprecision inputs get a linked
field error. Stored accepted amounts use canonical exact decimal strings.

Search and the decision-state filter cover the complete retained population,
combined with the original proposal-type filter before paging. Navigation conserves
unfinished fields as actor/run/movement drafts without saving a domain decision.
Per-movement compare-and-set checkpoints reject stale tabs. Current drafts reopen
automatically; a draft from an older domain revision requires explicit recovery.
Old run-level drafts remain intact and are read for their original movement.
“Salva e successivo” and the save-in-place action alone register the chosen status.
“Conserva bozza” is separate. Removing even the sole counterpart makes the missing
row visible immediately and offers undo; it does not accept an empty entry.

An optional registered JSON chart source can be supplied at preparation with
`--chart-input-id`. Its `client_id` must match the portable client context; its
`accounts` contain unique seven-digit `code` and actual `name` values. The helper
retains its binding and byte hash separately from immutable original proposals.
Only this acquired chart supplies account denominations, search and membership
validation. Without it, retain manual account entry and state that format checking
does not establish chart membership. Do not fabricate names, infer a chart from
proposal codes, replace an existing client's chart, or create a new run merely to
upgrade an existing review.

“Genera TXT TeamSystem” consumes accepted saved corrections only,
withholds pending/rejected entries, and retains a receipt listing exclusions and
the exact decision digest. A subsequent correction invalidates the current export
while preserving earlier file bytes and decision history. “File del lavoro” lists
only the current byte-verified export and its receipt. Account-only entries request
no E/C update. Export does not import, post or prove installation compatibility.
For historical already-posted inputs, keep that exact warning visible.
With no accepted saved decisions the export button is disabled with an explicit
explanation. A filter does not restrict export: all accepted saved decisions in
the same run are included.

The native editor requires a running work and actual operator reviewer authority.
The actor label does not independently authenticate Francesco or attest a professional
signature. Do not accept entries on his behalf during preparation or testing.
Use a separately labelled fictional test to verify corrections and TXT writeback.

Input originals and review records remain local. Explicit selected-entry discussion
can send the selected bank description, date, amount, proposed counterpart lines,
saved decision, reasoning and evidence to the existing host model; not the whole
batch or unsent drafts. Do not claim that local storage anonymizes these values.
Keep any automatic model-data reporting gap visible separately from the useful
review result. A package build or UI-ready response is not visible host acceptance.


Export formats use the shared `vera.reviewed_journal_entry.v1` contract and a
versioned adapter registry. TeamSystem IMPPN is the available encoder. DATEV
Koinos / DATEV Italia and Zucchetti are registered targets requiring their
verified receiving-product import profile; they must not fall back to IMPPN,
German DATEV EXTF or an invented CSV. Unknown/unconfigured formats fail before
writing a file or modifying decisions. Add format-specific validation and
source-backed mapping to enable another encoder; never rerun reconciliation or
infer accounts, invoice closure or external partita keys in a formatter.
