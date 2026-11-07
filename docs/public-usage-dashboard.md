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

## Validation and recovered blocks

- Reporting/receipt regression suite: 186 passed, 94.84% workflow-usage coverage;
  the new aggregate module has 100% coverage. The 22 dashboard regressions pass.
- The rendered page was inspected at 1440px and 390px using representative
  aggregate fixtures. Both tables fit the mobile viewport, totals and labels
  agree with the response, and no JavaScript errors were observed. This local
  preview is separate from production verification after deployment.
- The service privacy review records the exact public payload and the unchanged
  private lifecycle/receipt paths. Privacy-contract tests passed (31 tests).
  This is a developer review; no professional task or customer document was
  executed to generate dashboard acceptance evidence.

| Encountered block | Effect and recovery |
| --- | --- |
| Antigravity test fixture used an unsupported native-identity app value | Three tests failed before counting. Corrected the fixture to use an existing verified computer identity with an Antigravity task event; no identity contract was relaxed. |
| Static typing found a generic string product key | Narrowed the aggregate key annotation to the existing product type; Mypy then passed. |
| Sandbox denied the local HTTP listener and Chromium process bootstrap | Preview could not start. Retried the explicitly scoped localhost server and installed browser with approved execution permissions. |
| GitHub connector returned 403 for PR creation | Used the configured GitHub CLI to open the authorized PR. |
| CI rejected stale shared-service privacy fingerprints | Reviewed the new public boundary, refreshed the affected services and regenerated source contracts and packaged declarations. The rejected checks were archive generation and the bandi package-contract test. |
| Canonical version update invalidated the localization catalogue snapshot | Verified that all 55 skill entrypoints were byte-identical, then rebound the existing assessment to the new manifest. No jurisdiction judgment or professional acceptance claim changed. |
| A privacy regression expected every usage boundary to have only Codex and Cowork profiles | Updated the test to require all three requested apps for the new public aggregate boundary while retaining the exact existing profiles for private boundaries. Production declarations were not weakened. |
