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
