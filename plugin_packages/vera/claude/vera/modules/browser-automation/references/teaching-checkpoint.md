> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Resumable teaching checkpoint

The current model writes sanitized interpretations, never raw page capture,
private field values, account identifiers or credentials. Input references
replace observed values. This schema checks completeness of declarations; it
cannot determine whether an interpretation is true. Do not treat passing it as
proof of semantic understanding, accounting correctness or successful replay.

Create one fresh private directory outside the Git workspace. The parent must
already exist. The helper creates the final directory and each revision with
owner-only modes; it never changes an existing directory's permissions. If the
host rejects creation, report that exact limitation and do not claim progress
was saved. Keep the current in-chat resume summary until persistence is possible.

Before observing, save an initial payload with `steps: []`, status `paused`,
and a precise first step. After each step, the model supplies this shape:

```json
{
  "schema_version": "browser-teaching-checkpoint/v1",
  "objective": "Teach the purchase-invoice posting process",
  "start_state": "Authorized accounting console, before selecting an invoice",
  "end_condition": "Explicit posting result linked to the journal entry",
  "status": "needs_clarification",
  "resume_instruction": "Resume at account selection and explain the account choice",
  "steps": [{
    "id": "select-account",
    "intent": "Assign the purchase to an account",
    "action": "Account selection demonstrated; exact selection is unresolved",
    "decision_reason": "Not yet explained by the operator",
    "outcome": "Account-selection controls appeared",
    "postcondition": "Still need to establish how the assigned account is verified",
    "status": "unresolved",
    "evidence_basis": "observed",
    "uncertainties": ["What determines the account choice for this invoice?"],
    "capture": {
      "started_at": "2026-09-07T09:00:00.000Z",
      "ended_at": "2026-09-07T09:00:15.000Z",
      "stop_reason": "time_limit",
      "transition_count": 1,
      "before_sha256": "COPY_THE_ACTUAL_INITIAL_CONTROL_FINGERPRINT",
      "after_sha256": "COPY_THE_ACTUAL_FINAL_CONTROL_FINGERPRINT"
    }
  }]
}
```

The placeholders above are intentionally invalid: copy real capture hashes.
For evidence supplied only by the operator or an older summary, use
`evidence_basis: operator_report` or `unknown` and `capture: null`. Do not invent
timestamps or hashes when importing Francesco's older partial notes. Distinguish
imported assertions from freshly observed outcomes. Keep useful known steps;
resume only the uncertainties. All steps require an action, intent, decision
reason (including “no professional choice at this navigation step” when true),
outcome and postcondition. Unresolved fields must say what is missing.

`understood` means the model has accounted for the step, with no outstanding
questions. `ready_for_review` requires all steps understood and an observed
final result; it does not approve developer transfer or capability authoring.
The model must verify that the final result satisfies `end_condition`, rather
than merely observing a button change. Keep the current draft and linked
discovery evidence alongside progress as prescribed by the discovery playbook.

```bash
python scripts/teaching_checkpoint.py start <fresh-directory> \
  --input <sanitized-payload.json> --expected-revision 0
python scripts/teaching_checkpoint.py resume <directory> --summary
python scripts/teaching_checkpoint.py save <directory> \
  --input <updated-sanitized-payload.json> --expected-revision 1
```

Each immutable revision contains the full current payload and hashes its
predecessor. `resume` verifies the chain. A stale writer must resume again;
never delete or overwrite a revision. These local progress files are not the
sealed developer pack. Use `discovery_pack.py` for that separate reviewed
handoff and `capability_pipeline.py` for execution validation.

`resume --summary` verifies the same complete revision chain before returning
saved decisions, outcomes, evidence basis, open questions and the exact resume
instruction. It omits capture detail and always reports `execution_verified:
false`: a checkpoint cannot establish replay. The model chooses the relevant
next question from this evidence; the helper does not rank accounting decisions.
Use `resume` without `--summary` when full capture provenance is needed.

For a record-review process, maintain distinct steps for acquiring one record,
reviewing the populated entry with the operator, verifying an authorized posting
and checking replay. Put a learned rule in `decision_reason`, its observed or
reported basis in `evidence_basis`, what actually happened in `outcome`, and the
still-required verification in `postcondition` and `uncertainties`. Do not claim
acquisition from an empty workbook or replay from control changes. Business data
belongs in the authorized local review artifact, never in these fields. Reuse
an existing revision chain; do not replace it with a new tracker or fabricated
capture just to adopt the current teaching guidance.

## Automatic end-of-session report

`start` requires an empty step list and revision zero. `save` appends progress;
each successful write also creates `riepilogo-NNNN.md` beside that revision.
The report shows saved actions, reasons, declared outcomes, evidence labels,
open questions and the precise next step. It never certifies execution from a
checkpoint. Link the latest report at completion, pause or failure, not only
when the operator asks for it.

```bash
python scripts/teaching_checkpoint.py report <directory>
```

This verifies the revision chain and returns the report path. If interrupted
after saving a checkpoint but before writing its report, `resume --summary`
recovers the saved revision and `report` regenerates its missing report. Do not
retry the save with a stale revision or repeat the browser action. A modified
report is rejected rather than silently trusted or overwritten. The report is
local working material, not automatically approved for transfer; use the selected,
sanitized development request and its separate exact-content review for that.

The schema does not hard-code sites, professions or invoice fields. Capture
conditional decisions and exception paths explicitly, retaining unknowns rather
than inventing a rule from one example. Existing notes can be imported with
reported provenance, including explanations of manual steps; browser capture
hashes remain reserved for actual browser observations. A recorded manual step
does not acquire an executable implementation by being saved.

## Download steps during teaching

For each authorized exploratory download, use the shipped
`download_directory.mjs` observer in the supported persistent Node runtime:
`observeDownloadDirectory(actualDownloadsDirectory)` before the click, then
`observation.wait()` afterwards, with `observation.close()` in `finally`.
This reuses the same folder verification mechanics as capability execution.
Persist the returned path, byte length and SHA-256 only in the private run
artifact, not the sanitized checkpoint or chat. Record a sanitized outcome and
its provenance separately. Verify downloads sequentially, one observation per
click. Never invent a capability or promote a scaffold to invoke the runner.

The directory evidence establishes one new stable file and its bytes in that
window; it does not establish invoice identity or completeness of a batch.
Record any download event separately. Missing event evidence is not proof that
no file was saved, and an event alone is not proof of a saved file. Ambiguous or
unfinished arrivals remain unverified; leave existing files untouched. If the
host cannot run the local observer, record that gap instead of improvising a
profile inspection or bypassing a permission boundary. For an executable
capability, use `executeCapability` and its existing receipt contract, including
its event requirement; teaching evidence does not replace clean replay receipts.
