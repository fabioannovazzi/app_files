# Public usage dashboard

`/static/shared/utilizzo/index.html` is an Italian aggregate page linked from
Vera, Clara and Lucia. It refreshes `/api/usage-summary` once per minute while
visible. Only received activity from Codex, Cowork and Antigravity is included.
The inclusive minimum start version is the first deployed package without remote
reporting MCP, defined in `public_usage.py`. Versions are compared numerically;
there is no rolling date window. The release date is displayed beside the version
and does not filter task timestamps. Earlier `instrumented_from_version` catalogue
metadata records the introduction of collection and is not the dashboard cutoff.

| Product | Minimum version | Release date | Evidence |
| --- | --- | --- | --- |
| Vera | 0.1.492 | 2026-10-25 | [PR 910](https://github.com/fabioannovazzi/app_files/pull/910), merge `a37a4f9c6` at 20:44:14 UTC; production `main` fast-forward at 20:44:25 UTC |
| Clara | 0.1.347 | 2026-10-25 | Same release and production fast-forward as Vera |
| Lucia | 0.1.176 | 2026-10-25 | Same release; final merged canonical manifest and PR body specify 0.1.176, superseding the preparation document's 0.1.175 |

These package-release dates were verified against manifests, merged PRs and the
production Git reflog on 2026-11-07. They do not claim Marketplace publication
dates or the date an individual installed or first used a version.

The original dashboard mistakenly selected the older collection-introduction
versions (Vera 0.1.404, Clara 0.1.298, Lucia 0.1.121). PR 910 removes each
product's HTTP MCP registration while preserving local MCP and ordinary HTTPS
reporting. Its parent still declares all three remote reporting registrations.
PR 916 retires the server's legacy endpoints the next day; that is not the
client-package cutoff. Legacy completion events cannot turn a newer start into
a completed user in this dashboard.

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
labels, minimum versions and their release dates, supported apps, a coverage flag
and the refresh time.
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

The corrected cutoff was recalculated against retained production records on
2026-11-07 without changing records: 3 distinct starters, 2 completers, 1 failed;
the activity and app rows are unchanged. The boundary regressions explicitly
exclude the old collection releases and the immediate predecessors of each
HTTPS release, include the first HTTPS release, and ignore legacy completions.

During this correction, the canonical version/catalogue updates made the owned
privacy fingerprints stale, blocking package generation. Those exact metadata
changes were inspected and the affected reviews refreshed; all 55 Vera skill
entrypoint bytes remain unchanged. A reporting test run made before contract
regeneration had 190 passes and 3 stale-contract failures. After regeneration,
all 193 reporting/receipt tests pass; no validation was weakened.

- Reporting/receipt regression suite: 193 passed, 94.85% workflow-usage coverage;
  the aggregate module has 100% coverage. The 29 dashboard regressions pass.
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
