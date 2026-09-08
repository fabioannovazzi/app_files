> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Saved batch review

For an authorized invoice-processing batch, Francesco normally reviews the
results after processing. He need not watch live commentary. Maintain one
private batch review throughout acquisition and execution; link its latest saved
HTML at the end, on interruption, and after each subsequent human review.
Read this reference before running `scripts/batch_review.py`.

The model interprets the evidence and chooses professional treatment. No colour,
supplier match, confidence percentage or deterministic classifier constitutes
certainty. Continue supported decisions within the operator's existing explicit
scope and authorization. Set aside uncertain items and proceed with independent
items where possible. Existing browser action-time approval requirements still
apply; this report grants no posting authority and does not bypass host approvals.
Reuse valid authorization instead of asking again merely to create the report.

Acquire one real entry as required by the discovery playbook. Then use a fresh
owner-only batch directory outside the repository, public folders, sanitized
teaching checkpoint and developer pack. JSON and HTML may contain authorized
invoice details, amounts, account/tax treatment, source evidence and posting
references. They remain local files, but anything the model reads or writes is
in the selected model context. No new API, upload, external asset or server is
used. Never put credentials, session URLs or raw browser captures in a review.

## During the batch

1. Record the actual selection boundary in `scope` and its observed item count
   in `expected_items`, or null when still unknown. Keep pending items visible;
   an unfinished or interrupted run is `paused`, never successful by implication.
2. For each entry preserve the source document identity, intended action,
   proposed treatment and brief evidence-based reason. Save before a consequential
   attempt. In TeamSystem, include invoice/line descriptions, proposed account,
   VAT and other applicable treatment, amounts and the relevant client guidance,
   with exact source labels. Unknown fields stay explicit; do not invent values.
3. Record what actually happened separately from the proposal. `completed`
   requires observed confirmation and captured actual result, with a journal
   reference when available. Explain the supporting observation in `evidence`;
   a successful click, the proposal itself or a return to the list is insufficient.
   Missing journal reference must be stated, not fabricated. If the result cannot
   be established, use `unverified` and specify how to check it before any retry.
4. Use `set_aside` for unresolved professional questions, `failed` for an observed
   unsuccessful action, `unverified` for ambiguous outcomes, and `pending` for
   work not attempted. Record one concrete question or next action for exceptions.
   Do not retry a possibly completed posting until its actual state is reconciled.
5. Save a new revision after every item and before pause. `finished` means the
   declared selection is fully accounted for, including exceptions; it does not
   mean everything succeeded or that Francesco has checked it. Unknown population
   or unprocessed items require a partial status and an explicit scope gap.
6. At the end give the latest HTML link, counts and material exceptions. Do not
   replace the saved report with a chat-only summary or an empty workbook.

## Commands and payload

Run the module installation/dependency checks first, using the managed Python.
The operator never writes JSON. Vera supplies the full current snapshot using
this shape (the illustrative entry below is not live evidence):

```json
{
  "schema_version": "browser-batch-review/v1",
  "batch_id": "purchase-batch-1",
  "title": "Revisione fatture passive",
  "scope": "The exact client, period and invoice selection authorized by the operator",
  "status": "paused",
  "expected_items": 1,
  "entries": [{
    "id": "invoice-1",
    "document": "The observed invoice identity",
    "action": "Prepare accounting treatment",
    "reason": "Explain the decision using this invoice and applicable client guidance",
    "status": "set_aside",
    "proposed": [{"label": "Account", "value": "The actual proposed value", "source": "Observed proposal or explicit model proposal"}],
    "actual": [],
    "evidence": [{"label": "Invoice line", "value": "The actual acquired description", "source": "Invoice identity and exact line/field"}],
    "outcome": "Not posted",
    "question": "The specific remaining professional question",
    "posting_reference": "",
    "correction_of": ""
  }],
  "reviews": []
}
```

All proposed/actual/evidence details have `label`, `value`, `source`. Use these
arrays for row-level treatment and evidence; the helper does not select accounts
or verify semantic correctness. `expected_items` counts original items, not
subsequent linked correction actions. IDs remain stable across revisions.

```bash
python scripts/batch_review.py save <new-private-batch-directory> \
  --input <private-snapshot.json> --expected-revision 0
python scripts/batch_review.py resume <private-batch-directory>
python scripts/batch_review.py save <private-batch-directory> \
  --input <updated-private-snapshot.json> --expected-revision 1
```

`resume` verifies the JSON revision chain and renders/reopens the latest report.
Read the latest JSON when resuming work, not an old HTML snapshot. A hash chain
checks integrity, not accounting correctness or browser execution. The HTML is
an offline read-only view with search, status filter, expandable evidence and
print support; it requires no running server. Do not claim its controls post
corrections or save decisions. Dates/revision labels identify older snapshots.

## Francesco reviews afterwards

He can tell Vera which invoice he checked and any correction in ordinary language.
Resolve that statement to the exact entry; ask only if the identity or correction
is ambiguous. Never mark a record checked without his actual instruction.
Persist the supplied decision immediately through:

```bash
python scripts/batch_review.py review <private-batch-directory> \
  --entry invoice-1 --decision checked --note 'Operator’s actual check' \
  --expected-revision 2
python scripts/batch_review.py review <private-batch-directory> \
  --entry invoice-1 --decision correction_requested \
  --note 'Operator’s actual requested correction' --expected-revision 3
```

Show the resulting latest report link. Earlier reviews remain in history.
A correction request is not an executed accounting correction. Completed entries
cannot be rewritten: add a separate entry with `correction_of` referencing the
original ID, explicit intended rectification and its own outcome/evidence.
Use the existing authority boundary before changing the external accounting
system. Preserve both the original posting and verified rectification. An open
correction request stays visible until Francesco explicitly checks/resolves it;
do not silently mark it reviewed because a correction was attempted.
