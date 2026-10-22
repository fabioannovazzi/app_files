# One import-to-delivery operation

For an explicitly selected client and engagement, the agent writes one JSON
request and invokes Studio Archive's `scripts/reconcile_open_items.py --request
<absolute-path>`. Vera uses `vera_execute`; the professional never authors this
JSON or runs a terminal. Inspect actual source headers and values first, using
the normal selected-source read path so data-usage reporting retains provenance.
When the host has no `vera_execute` tool, the agent invokes this same published
script from the verified execution root using the resolved Python environment.

The request contains:

- `client_id`, `engagement_id`: the selected Archive scope.
- `request_id`: a stable identifier for this request; reuse it for resumption.
- `sources`: a list of `{ "path": "<absolute source path>", "mapping": {...} }`.
  Each mapping is the explicit source decision described in
  `tabular-source-layout.md`: role, adapter, perimeter, money/date conventions,
  mapped columns and actual table bounds. Optional `sha256` pins supplied bytes.
  Technical `reviewer_ref` and `reviewed_on` may be omitted.
- `assumptions`: established scope, cut-off, treatment of later settlements and
  any other material choices. Preserve real invoice and payment dates.
- Optional `title`, `narrative`, `language`, `purpose`.

The operation imports immutable originals, prepares and starts one run, calls
the ordinary producer, replays its assurance, declares the files and completes
verified work. The accounting result, file paths and reporting warning are
returned separately. Repeating the same request reopens the saved result without
recalculation. A changed mapping or scope requires a new request identifier.

`accounting_status=verified` and `report_ready=true` permit direct delivery.
Exact source-verified matches require no review-server visit. Automatic checks
do not authorize posting, filing, signature or professional adoption.

`accounting_status=review_required` returns the saved draft and its review
handoff. Keep unresolved rows explicit and use the maintained review/apply and
regeneration path only for remaining decisions. Then invoke the same script with
`--request <path> --finish-run <run_id>` to finalize delivery. A producer error
retains the failed run and diagnostics; repeating the request does not retry it.
The operation retains the initial validated review checkpoint outside the review
package and forwards it automatically when finishing. For an older run without
that retained checkpoint, pass its separately saved original hash through
`--expected-predecessor-checkpoint <hash>`; never derive it from a successor.

For an explicitly isolated test session, `--state-dir <path>` selects that
session's Archive configuration. Never substitute another client's state or run.
