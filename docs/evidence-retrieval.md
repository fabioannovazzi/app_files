# Indexed reconciliation evidence

The live entrypoints are `grouped_review.complete_grouped_review` and
`open-item-reconciliation/semantic_resolution.prepare_resolution`. Both call
`bank_first.run_bank_first`, now delegated to `retrieval_review.run_review`.
The shared bookkeeping/audit purposes use the same controller. Replay dispatches
by the retained retrieval protocol. Legacy receipt replay remains available;
legacy active runs are not silently migrated or recalculated.

The qualified population stays in a per-run SQLite B-tree/FTS index. Selection is
mechanical; interpretation belongs to the model. There is no universal date or
amount gate. Documented aliases require a canonical value, alias and source
reference. Group/reference/settlement searches provide paginated members and
exact totals; totals never establish an accounting identity.

Each worker returns either a decision or typed evidence requests, through the
existing isolated JSON capsule. Queries have no filesystem, SQL, shell or
network capability. Search results carry candidate counts, reasons, provenance,
cursors and explicit incomplete coverage. Known source IDs can be retrieved by
`field=transaction_id`; current B/J references are scoped to their exact packet.
`retain` names currently visible B/J references to keep across searches. A short
working note is explicitly fallible model memory, not source evidence. Sol uses
the same searches and receives the latest relevant first-stage conclusions,
a working note and the last eight query/coverage summaries. Search counts expose
any omitted history; full attempts stay in the local evidence log.

Defaults: 16 rows per page, four queries per turn, at most 16 evidence turns per
focus, and 98,304 bytes for the prompt plus schema. The unchanged native cap also
applies. These are technical budgets, not accounting thresholds. Changing a
budget requires a new bound execution; it cannot silently reinterpret an old
run. Large indivisible focus groups or excessive source text may still return a
technical deferral rather than a conclusion. Six scale samples measured roughly
12–14 KB; representative small-group tests retain headroom under 96 KiB. The
60,000-query scale experiment is not 60,000 model calls or production acceptance.

The global reserved-evidence register is validated after every decision, and a
per-run OS file lock prevents concurrent controllers. Doubtful candidates do not
reserve evidence. Source changes and native denials leave technical state;
completed decisions replay from retained native receipts without calling models.
Every evidence request is reconstructed against the same index on replay.
All original domain controls apply to deterministic and model allocations.
Source and implementation fingerprints bind the run. Preserve the original
execution source to replay historical evidence after an implementation change.

No saved human decisions/private drafts, real client runs, posting or export
approval semantics are changed. The previous candidate's Terra selection,
short references and portable isolation implementation are carried forward;
Windows device acceptance remains unverified. Only synthetic inputs are used
in this change's verification.

## Explicit recovery of a 0.1.625 checkpoint

Vera 0.1.627 closes the current packet over every source-row reference in its
retained prior conclusions, including accounting citations outside group
membership. This does not allocate those cited rows or relax global non-reuse.
Before a new investigation, the controller measures the exact prompt plus schema
size and reduces the focus to a prefix of whole groups when needed. Remaining
groups stay in the work queue; an indivisible group still exceeding the budget
remains an explicit technical deferral. Packet projection 2 is recorded on new packets. Existing packets without that
field replay with projection 1, with their original hashes, local B/J references,
source binding, prompt, response and native receipt. Historical code is evidence,
never imported or launched by this recovery path.

For a failed Archive run, use `start_studio_client_workflow` with the existing
client, engagement and run IDs (CLI: `studio_archive.py start-workflow`). This
supported transition retains the previous artifact manifest and reporting history.
Do not prepare another run, rewrite `execution-runtime.json`, remove a state
file, or edit any receipt. Keep the original indexed execution package available:
the assurance envelope still validates against its original bytes.

Then use the **new installed product's managed CLI** explicitly:

```sh
python "$VERA_PLUGIN/scripts/managed_python_runtime.py" \
  --module journal-bank-reconciliation run scripts/semantic_review.py \
  run-all "$RUN_ROOT/outputs/reconciliation" \
  --output-dir "$RUN_ROOT/outputs/semantic-review" \
  --client-engagement "$RUN_ROOT/context.json" --resume-checkpoint
```

Set the reconciliation directory to the existing run's actual `run_intake.json`
parent, not a newly created directory. Preserve the original purpose and worker
selection arguments when they were specified. The managed CLI verifies and
executes the currently selected installation. `vera_execute` retains a run's
original package and is therefore not the upgrade route for this recovery.

The explicit option accepts only the audited 0.1.625 implementation fingerprint
and matching source/admission/purpose/relationship/budget binding. It reconstructs
all saved decisions before writing a transition record into the state. Changed
sources, altered retained artifacts and an unfinished native worker reject
recovery without launching another worker. New calls continue only outstanding
work. The original attempt files remain byte-identical; no old receipt is resealed.
Use ordinary `run-all` for subsequent continuations on the recovered version.

Verify the final workbook, native review and privacy-report outcome separately.
A successful synthetic recovery or package installation does not establish that
a customer run has completed or that the host's already-open chat refreshed.
# Historical code retention

Runtime collection preserves indexed journal-bank implementation bytes in
`journal-bank-reconciliation-replay/<package-sha256>` before removing an idle
execution release. Historical receipt validation can read that archive when the
original execution directory is absent. It verifies the saved index and exact
implementation receipts; it never launches the archived release. If preservation
fails, collection retains the original directory and current work can continue.
