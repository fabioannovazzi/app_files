# Public usage dashboard

`/static/shared/utilizzo/index.html` is an Italian aggregate page linked from
Vera, Clara and Lucia. It refreshes `/api/usage-summary` once per minute while
visible. Only received activity from Codex, Cowork and Antigravity is included.
Each product's `instrumented_from_version` is the inclusive minimum start
version; versions are compared numerically. There is no rolling date window.

The agreed counting unit is the proven computer ID. Repeat tasks, reporting
instances and apps do not multiply one user. Each function, app and the global
total has its own sets of starters and completers. The global total is the union,
never the sum of the displayed rows. "Failed" means starters without any completed
task in that row's scope, regardless of whether their task events are failed,
cancelled or still unknown. This dashboard convention does not rewrite task
outcomes or incident records.

Explicit synthetic/agent samples and the registered test identities from the
latest product testing configurations are excluded. Test configuration dates do
not impose a counting cutoff. The exclusion applies across products. Missing
computer proof is never replaced by an installation UUID; an aggregate coverage
flag prevents presenting such a result as complete.

Only nonzero rows are published. The response contains aggregate counts, catalog
labels, minimum versions, supported apps, a coverage flag and the refresh time.
No computer, installation or run IDs, comments, ratings, documents, credentials,
individual histories or test-exclusion details leave the server. Displayed
function labels use the product language; the Lucia document check uses its
public name. A transport failure preserves the last successful display with an
availability message, never replacing it with zero.

Exact set membership and arithmetic are deterministic because their correctness
is mechanically verifiable. Regression coverage includes repeated attempts,
cross-product/app overlap, version boundaries, owner tests labelled as ordinary
use, missing identity, historical activity, empty inventories and public response
field boundaries.
