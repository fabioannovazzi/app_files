# Composizione negoziata: evidence and implementation

## Recovered source

Requested message: https://discord.com/channels/1550191335917625474/1552308080157655140/1554534895290683464

Contributor: Francesco Giraldo, original message 1552308465383514124.
Recovered all 11 channel messages and five attachments on 2026-09-29.
The original and reposted ZIP are identical, SHA-256
`0a9f18851c6a994f16df648d64e796f14ba2935aa8c073b64371c88f26d32daa`.
All 72 listed member hashes match; 73 entries have no absolute paths,
traversal or symlinks. Contributor code was inspected as text, not executed.
The integration note, two Vera replies and ZIP remain in the primary checkout's
ignored `outputs/discord-composizione-negoziata-20260929` recovery folder.
That folder includes a readable transcript, recovery index, all five attachments,
67 extracted text documents and the independent synthetic behavior-check outputs.

The integration note supersedes the proposed architecture: implement a light
professional orchestrator using actual Vera capabilities. The latest reply
defines a first executable increment, not evidence of a released full function.

## Reuse decisions

| Proposal | Decision | Repository destination and reason |
| --- | --- | --- |
| Advisor / independent expert distinction | KEEP | Separate role references; one fixed role per engagement history |
| Problems, evidence gaps, contrary evidence, next action | KEEP | Model-authored case record; no keyword classifier |
| Discovery sources and professional scenarios | ADAPT | Research reference and synthetic acceptance cases; sources require verification at use |
| Document inventory, versions and isolation | REUSE | `plugins/studio-archive/scripts/client_ledger.py` imports, receipts and managed runs |
| Revision conflicts and retries | ADAPT | Extend that ledger with sealed workflow snapshots under its existing engagement lock |
| Explicit dependencies and change impact | ADAPT | CNC module validates graph and marks transitive dependents stale; the model selects edges and semantic impact |
| Financial reconstruction / reconciliation | REUSE | `financial-analysis`, `journal-bank-reconciliation`, `open-item-reconciliation`, `centrale-rischi-review` |
| Cash forecasts and business plans | REUSE | `treasury-forecast`, `business-planning`; separate managed runs and recorded output references |
| Legal research and review | REUSE | Vera `quesito-legale-fiscale`, planner and answer review; no static legal rule engine |
| 24 templates and rigid workflow JSON | ADAPT | Progressive role/topic guides and evidence-linked Markdown drafts appropriate to the actual problem |
| Contributor JavaScript engine, A/B ratio, state machine | DROP | Duplicates existing calculations or imposes semantic transitions without demonstrated advantage |
| JSON production/approval flags | DROP | Editable flags cannot authenticate an actor or authorize external actions |
| Portal automation, signatures, background monitoring | DROP | Outside this function; no inferred execution or receipt |

## Requirement to component to proof

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Roles, start/resume, document provenance | Managed engagement + role-bound snapshots + archive input receipts | Fresh-process resume; foreign input and role-change rejection |
| Facts, assumptions, gaps, sources, professional questions | Typed evidence nodes, locators and model-authored priority brief | Missing evidence remains explicit; invalid references rejected |
| Existing capability invocation | Catalog routes, child run output bindings | Synthetic treasury run referenced in case evidence |
| Concrete draft and professional review | Versioned draft content with evidence references; review records bound to exact node digest | Changed draft or dependency cannot inherit review |
| New fact / source / assumption | Explicit dependency graph and transitive stale projection | November-to-January receipt change invalidates forecast, funding and creditor proposal |
| Concurrent work and retries | Ledger lock, expected revision and idempotency key | Stale write rejected; duplicate retry yields original snapshot |
| Juridical uncertainty / adverse outcome | Progressive guides and research routing | Behavioral cases with missing sources and unsupported optimism |
| Package availability and data handling | Component, router, privacy manifest, public process page, generated package | Registry, boundary and package parity checks |

The existing archive API is `client_ledger.py` (`prepare_run`, `start_run`,
`finalize_run`, `complete_run` and input/upstream receipts). The executable
financial handoff in the synthetic acceptance test calls
`plugins/treasury-forecast/scripts/run_treasury.py prepare`, closes its managed
run and binds the exact forecast artifact in a successor CNC run. Other routes
retain their own skills and reviews, including
`financial-analysis/scripts/run_pack.py`,
`open-item-reconciliation/scripts/reconciliation_workflow.py`,
`business-planning/scripts/planning_cli.py` and
`centrale-rischi-review/scripts/run_analysis.py`. Those routes are available
integration points, not additional executions demonstrated by the CNC test.

## Verification performed

- 23 CNC synthetic tests pass; helper coverage is 90.75%. They include an actual
  treasury CLI run, exact artifact binding, fresh-process resume across closed
  runs, stale review rejection, concurrent revision conflicts, idempotent retry,
  missing-memo repair, conflicting-memo preservation and snapshot tampering.
- Archive identity, registry, filesystem, icon and public-copy suites:
  202 passed, 22 skipped. Privacy and update-notification suites:
  58 passed, 2 skipped. Teaching and Cowork privacy suites: 89 passed.
  These suite results are not a count of professional acceptance cases.
- The final Codex/Cowork package, skill-identity and function-page architecture
  regression run passes all 490 tests. `build_product_release.py --check` verifies
  the exact canonical versions, source parity and matching public Cowork bytes
  for all three products; packaged MCP startup checks pass.
- Independent forward testing produced three synthetic chat/export responses:
  missing aging and unsupported growth; an expert with a prior professional
  relationship; and a delayed receipt with an old approval. The responses
  exposed gaps, preserved role boundaries and did not fabricate execution,
  legal-source verification or saved history. That exercise did not have a
  managed archive; persistence is covered by the separate executable tests.
- Black and Isort pass on changed Python; Mypy passes on all 28 registered
  plugin kernels and the two CNC scripts; Bandit reports no medium/high findings
  on the CNC helpers and archive ledger.
- The public page was inspected in the browser at desktop and 390-pixel width
  without horizontal overflow. IT/EN/FR/DE/ES controls, the localized final
  model-data section, the shared report note and product navigation were checked.
- The required course catalogue contains a five-language synthetic CNC lesson.
  It supplies initial facts and a changed receipt, not precomputed conclusions
  or forged learner confirmations.
- Codex, ChatGPT and Cowork packages were rebuilt. The CNC dependency checker
  loaded from each Vera ZIP. Source/package parity and host acceptance remain
  separate checks; no Marketplace publication is claimed here.

The generic package assertions were updated for the new component, public
page and compact specialist contract. Existing Cowork introduction wording and
cache-busting stylesheet URLs are checked for their actual contract rather than
outdated literal boilerplate. The shared archive change requires aligned
candidate bundles: Vera 0.1.282, Clara 0.1.223 and Lucia 0.1.63, with Studio
Archive 0.1.39. These candidates were moved above the manifest versions inspected
in open PRs #705–#708 to avoid publishing different source under the same version.
The candidate refresh passed source/package parity for all three products.
Its broad package and privacy regression run had 564 passes, two skips and
eight failures: seven lacked Node on the test command's PATH and one exposed
a stale Lucia intake privacy fingerprint for the shared ledger. After reviewing
the additive ledger methods, refreshing that fingerprint and using the bundled
Node runtime, the focused rerun passed all 46 checks, including all eight failures.

Live CLI inspection on 2026-09-29 identified enabled local installations
`vera@mp-vera` 0.1.275, `clara@mp-clara` 0.1.218 and `lucia@mp-lucia` 0.1.60.
The remote Marketplace catalogue lookup failed in that command. The candidate
versions' installed-host acceptance is therefore not established.

A subsequent repository-wide gate attempt did not pass. Black flagged 262 files
and Isort 202 files, all unchanged by this implementation. Full pytest stopped
during collection with 26 import errors; 24 report a SciPy native-library loader
failure, which also reproduces with an isolated import outside the repository.
Installed SciPy 1.15.2 matches the requirements pin and its native file matches
the installed distribution's RECORD hash. Repository-wide source coverage was
not established. Mypy passed on 132 source files; Bandit found 30 low-severity
issues and zero medium/high issues. Logs and the unchanged-file comparison are
in the recovery folder's `full-quality-gate` directory. These results do not
replace the passing scoped checks above or establish a green complete CI run.

## Evidence boundaries

Hashes and recorded reviewer references establish provenance and revision
binding, not professional identity, eligibility, truth, legal validity or a
signature. The local host and filesystem remain the access boundary. Separate
engagements prevent automatic role sharing within this workflow; this is not a
multi-tenant permission system. A different role requires a separate authorized
engagement and independence assessment. No external sends, filing or monitoring
are implemented.

The CNDCEC/FNC page published 2026-06-22 was inspected on 2026-09-29:
https://www.fondazionenazionalecommercialisti.it/node/1904 . It distinguishes
preliminary analysis, negotiation support/opinions, and final reporting for the
expert. CNDCEC Informativa 86/2026 confirms publication of the 23 April 2026
decree: https://commercialisti.it/wp-content/uploads/2026/06/Informativa-n.-86-2026.pdf .
The attempted Normattiva full-code URL returned an error. No complete current
legal corpus or automatic deadline engine is claimed. Per-case decisive legal
questions require current primary sources and professional review.

Synthetic verification is not field validation. Professional acceptance on an
authorized real case and fresh installed-host qualification remain distinct.
