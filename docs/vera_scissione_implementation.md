# Scissione guidata implementation

Status: release candidate integrated with main for the authorized Scissione deployment.
Server deployment and Marketplace publication must be verified separately.
Source: Discord message 1554534739514359879 in channel
1554383368270118973, recovered 2026-09-29. Contribution attributed to Francesco
Giraldo; ZIP SHA-256 `49d683ea9cfcce56f7f386356522e43a2d8304138571ac1ff4a2008ec3328676`.
The original ZIP has 15 entries. Its code was inspected as text, never executed.
Recovered files are in the primary checkout's `outputs/discord-scissione-2026-09-29`.

## Acceptance scope

Implement P0 (versioned evidence, decisions and dependency tracking) and the
first P1 path: Italian OIC partial proportional scission into a new beneficiary.
The host model proposes the route and case meaning; the professional confirms
them. No legal rule is shipped as professionally approved. Complex cases,
scorporo, existing beneficiaries, IFRS and cross-border operations remain
explicitly outside this first operational path. The simple existing-beneficiary
exchange calculation is a separate synthetic arithmetic check, not route support.

The implementation must persist through Studio Archive, preserve exact historical
versions, reject foreign inputs, keep unknown amounts distinct from zero, separate
book/tax/economic values and shareholder tax costs, require exact-version review,
invalidate only dependent records, and produce reviewable drafts and schedules.
Generated documents never establish signature or filing.

## Validation plan

- Synthetic proportional example B: 60/40 ownership and 1,000,000 = 700,000 + 300,000.
- T06-T08: separate arithmetic example A and rejection of unsupported assumptions.
- T25/T29: transitive selective invalidation and preserved historical approvals.
- T26: missing material contract keeps a balanced case incomplete.
- T28: drafts do not acquire filed status.
- T30: explicit rounding policy and visible residuals, with every owner retained.
- T31: exact Studio Archive input membership and entity authorization.
- Positive and negative portable-run integration, privacy validation and package parity.

Deterministic logic is used for mechanically verifiable arithmetic, schemas,
hashes, identity membership and dependency traversal. It does not decide legal
applicability, economic fairness, evidence sufficiency or the correct route.

## Release boundary

Technical tests do not establish legal validation or installed runtime acceptance.
No signature, filing or external communication forms part of this implementation.
Record the exact tests, remaining limitations and package state before review.

## Implemented behavior

- A single authoritative case holds entity declarations, evidence locators/hashes,
  facts, liabilities, allocations, valuations, tax positions, rules, decisions,
  deadlines and document drafts. Derived views do not create competing registries.
- Exact archive membership and input hashes are enforced through the real portable
  Studio Archive contract. MCP and Python registries both expose the new workflow.
- Each immutable revision contains its dossier, schedules, change impact and
  artifact inventory. Reviews bind exact revisions and declared identities;
  documents cannot be approved before schedules exist. Source/date/engine changes
  invalidate the corresponding approvals. Independent decisions survive revisions.
- Finalized prior revisions can continue in a new run only through a verified
  same-engagement upstream artifact. Ordinary imported JSON cannot claim that status.
- Decimal schedules retain every owner, explicit rounding residuals, analytical
  allocations and separate book/tax/economic totals. Unknown shareholder tax costs
  stay null. Unsupported routes produce an explicit result without calculations.
- Vera routing, host skill cards, privacy manifests and five-language public
  explanation are integrated. The function is Italy-scoped on the product page.
  It has no prepared voice lesson in this initial candidate.

## Historical candidate evidence and limits

Recovered six channel messages and three attachments. All fourteen hashes in the
contributor's original file manifest match the recovered ZIP. The supplied report
claims 55 checks; those are not presented as independently executed tests.

Independent scissione acceptance: **49 tests passed**, **84.84% line coverage**.
The tests exercise examples A/B; T06-T09, T25-T31 mechanical boundaries; unknown
and conflicting evidence; tampered outputs; concurrent/stale writers; finalization;
real archive continuation; and indirect dependency reviews. A required parent cannot
hide an unreviewed input or candidate rule. T01 is covered for its arithmetic and routing only.
No claim is made to pass all 32 proposed legal acceptance scenarios. Legal-source
currency, case-specific applicability and actual professional approval remain
outside these synthetic results. Entity authority and reviewer identity are
declarations, not independently verified credentials.

The combined archive, privacy, icon and original scissione suite passed 187 tests
before the additional engine-version regression was added. Black, Isort, Mypy
and Bandit passed for the changed Python implementation. A separate persisted
synthetic run reached `prepared_for_review`; its filing status remains
`not_performed` and legal validation `not_certified`.

Candidate packages: Vera **0.1.281**, Clara **0.1.222**, Lucia **0.1.62**;
Studio Archive component **0.1.38**. The latter products are rebuilt because they
bundle the changed shared archive registry. Their professional behavior is unchanged.
The full package/update-notification/release-alignment suite passed **458 tests**
with **2 skips because curated Marketplace installations are absent**. All Codex/ChatGPT-upload/Cowork packages pass
source parity and version alignment;
Vera's 18 and Lucia's 4 packaged MCP servers initialize and list tools.

The branch incorporates main `d728392e7`, preserving the independently merged
fusione P0 foundation and the synthetic-only trasformazione prototype. Both
upstream implementations and their tests are unchanged; the scissione engine is
also unchanged by the integration. The combined Geneva inventory contains all
42 skill identities and preserves their authored roles and dispositions. No Swiss
professional applicability is inferred from translation or structural tests.

The combined scissione, fusione, trasformazione, website, router, Geneva and icon
suite passed **372 tests**. The Cowork instruction check and 36 teaching-review
regressions passed **37 tests**. All three products' host packages pass source
parity; Vera's 18 and Lucia's 4 packaged MCP servers initialize and list tools.

The shared scissione workflow-ID addition changed source pins in 34 previously
reviewed teaching kits (32 Vera, one Clara, one Lucia). Every non-source course
field and input definition matches the accepted base. The pinned source delta
adds `scissione-guidata` to the archive workflow tuple. The bounded freshness
review records that comparison; original reviewers, dates, judgments and artifact
hashes remain intact. It does not claim a new independent professional or
teaching review. The complete fresh-JUnit gate passed in the earlier CI runs.

All 33 CI checks passed on `194ea571f`, and all 36 passed on `1dcf0da45` after
integrating fusione. Main then advanced with trasformazione. The latest combined
revision requires fresh CI; an earlier green rollup does not certify new source.
The local completion audit and PR record the final candidate's checks separately.

Vera package SHA-256:

| Distribution | SHA-256 |
|---|---|
| Codex | `fa0481b8a276eaf42857ae6634dc04eef3c832435c1c8d3437d486a1d22254ed` |
| ChatGPT upload | `aa0f9a666ee7cc59e83c032a13e819a9fb7818e5838bd3e534a87db996d2f436` |
| Cowork | `e8d79c972f913dc1f7a12277ceaa21b49b5af1ec2e3f0b118f70679fbb33795e` |

These are build candidates. No installed-session acceptance, Marketplace
publication, public deployment, signature, filing or Discord reply was performed.

## September 30 release integration

Integrated main `84f230804d295f1fe6cfdbc682cb0c1f5990447c`, retaining the
PMI valuation, Patent Box, ESG, Fusione P1 and CNC releases. The Scissione
implementation and its 49 acceptance tests are unchanged; the integrated run
passes all 49 with 84.84% coverage. No new legal route is enabled.

Release versions: Vera **0.1.297**, Clara **0.1.233**, Lucia **0.1.73**,
Studio Archive **0.1.42**. Shared archive registration requires rebuilding
all three products. Earlier candidate versions and hashes above are historical.

The 46-entry Geneva inventory preserves every current-main assessment and adds
the retained unresolved Scissione entry. This does not qualify Swiss use.
The public explanation states the minimum containing version and explicitly
retains the outstanding professional validation on a real case.

For 36 teaching kits, every non-source field and input record matches main.
The source delta adds Scissione to the archive's supported workflow IDs.
Existing reviewer attribution and output hashes are preserved; fresh native
execution and editorial binding remain enforced by CI.

The release also repairs the current-main archive registry mismatch: the MCP
workflow enum now includes the already-supported CNC and Patent Box IDs in
the same order as Python. The inventory test adds its missing Patent Box ID.
This correction was explicitly approved on September 30.
