# Vera: delivered changes and remaining solutions

**Closed by user scope decision.** Mac-specific checks and Windows testing are
excluded. See [CLOSURE.md](CLOSURE.md) for the final state; the historical
requirements and evidence limits below are retained for traceability.

This is the short delivery handoff. CURRENT_REMAINING_WORK.md retains all20
original cards; no original requirement is waived. No merge or deployment occurred.

## Latest completed fix

Centrale Rischi 0.1.8 / Vera 0.1.211 now use the official Banca d’Italia corpus
by default. Direct downloads passed all 15 extraction/negative checks and 10
numerical analysis cases. Fixed an empty-corpus false pass; 32 CR tests pass.
All three Vera packages rebuilt and passed canonical-source parity, including
18 Cowork MCP startup/tool-list checks. Current source/package identities are
in `vera-0211-delivery-identities.json`. No deployment or publication occurred.
Repository inventory remains two local branches, two remote branches excluding
origin/HEAD, three worktrees and zero stashes; other task work is preserved.

## Previously completed communications fix

The synthetic no-publication result is now finalized. The user-approved decision
is retained; exact input/output integrity, six internal output kinds, accepted
reason text and semantic-review events are verified automatically. A second
human package approval is no longer required for an outcome with no communication
drafts. No human approval event is fabricated. Explicit package rejection still
blocks. Publishable communications still need exact-package approval, and only
final_ready can be externally delivered.

Communication0.1.10 / Vera0.1.210:41 workflow tests pass, including changed-record
rejection, explicit rejection preservation and the publishable-package approval
gate. Actual synthetic run status is no_publication_recommended with a validation
receipt. All three Vera packages rebuilt and pass parity;18MCP servers initialize
and list tools. Evidence:approval-loop-closure.json and vera-0210-package-checks.log
under /private/tmp/vera-remediation-01a07083.

## Remaining problems and concrete solutions

Scope clarification: this task audits and fixes Vera. Lucia and Clara checks
are relevant only where a Vera change affects a shared component or package
contract. Their independent workflow, page and publication defects are retained
as repository-wide findings, not additional Vera remediation requirements.
In particular, `apertura-pratica` is in Lucia's current component manifest and
absent from Vera's; its audit mismatch below is outside Vera's functional scope.
Repository-wide CI must still be reported honestly before any merge.

Current user scope: native Windows testing is excluded from this Astra/Vera
audit. Mac/browser checking has resumed; Chrome works. Local report file URLs
are refused by Browser Use policy, while public pages and the separate synthetic
browser workflow are accessible. No additional user approval is missing.

The interaction-audit failure has been narrowed to a detector limitation:
`apertura-pratica` uses `pending_review_decisions.json`, `review_decisions.json`
and digest-bound `review_receipts.json`, whereas the shared detector recognizes
`ui_decisions.json`. Its MCP panel explicitly renders read-only; the local
workbench saves pending decisions and `apply_review.py` applies confirmed ones.
Source inspection therefore supports persistence being implemented, but does
not establish runtime acceptance. The audit mismatch remains visible; do not
rename workflow artifacts or add documentation keywords merely to pass it.
Evidence: `current-interaction-audit.json`, `apertura_pratica_core.py`
`apply_decisions`, and `review_server.py`'s pending-decision write.

| Item | Observed state | Next solution |
| --- | --- | --- |
| Browser/report visual checks | Chrome is available; Browser Use explicitly refuses local report file URLs and alternate-route bypasses. | Report rendering remains unverified under this tool policy. Public-page review and direct synthetic browser workflow checks have completed separately. Do not rerun arithmetic or ask for another unlock. |
| Optional isolated accounting worker | Current Mac differs from the retained qualified profile; ordinary guarded launch stops. | Keep its explicit unsupported state until a new profile passes the existing complete canary and real-answer qualification. Do not replace hashes alone or claim Windows support from Mac tests. Windows testing is outside this task by explicit user instruction. |
| Centrale Rischi benchmark documents | Resolved using two public Banca d’Italia PDFs, downloaded directly on 6 September. All 15 extraction/negative checks and 10 numerical analysis cases pass. | New default `gold_official_cases.json` records URLs and the tested edition. Old third-party PDFs are optional and no longer prerequisites, as explicitly instructed by the user. |
| Cross-product integration | Latest selected run has8 failures; one newly stale Lucia communications fingerprint caused by this shared change has a reviewed correction and exact passing retry. The remaining failures concern Lucia matter-opening metadata/pages, shared interaction audit and Clara publication/package state. | Reconcile those owner changes against a stable source snapshot. Rebuild through canonical builders; preserve the publication gate rather than copying an unaccepted Clara ZIP or inventing a published version. |
| Repository-wide quality gates | Frozen full suite:9894 passed,29 failed,30 skipped; src coverage79.5029%. Subsequent fixes/retries are recorded individually. Global formatting includes unchanged baseline files. | The repository is not globally green. Before merge, resolve the remaining cross-product failures and add meaningful coverage where missing behavior is in scope; rerun the full gate once source integration is stable. Do not round79.50% up or weaken exclusions. Vera's separate four-kernel gate was84.52%. |

The original20-task goal is not certified complete. Technical fixes, local test
results, native-host acceptance and release approval are separate evidence.

## Latest user scope and Mac/browser result

Native Windows testing is removed from this Astra/Vera remediation scope by
explicit user instruction. It is not a remaining acceptance requirement.
Mac/browser work resumed immediately. Chrome completed the synthetic package
workflow, semantic-label recovery with a replaced DOM ID, visible login handoff,
and redirected-origin observation. No action followed the origin change.
These are direct browser observations, not a shipped executeCapability receipt.

The local Business HTML file URL was rejected by Browser Use URL policy, which
explicitly forbade alternate routes and browser surfaces to obtain the same
blocked result. Report rendering therefore remains unverified; user approval
is not missing. Evidence: current-mac-browser-observations.json.

## Public-browser review completed

Inspected live Italian Vera, Browser Automation, Management Control, Professional
Communications and Business Planning pages. The reviewed workflow boundaries and
model-data sections are visible and consistent with their reviewed contracts.
Business Planning switches to English and its breadcrumb returns to the English
Vera hub. The hub exposed an untranslated passive-invoice-audit heading: added
its missing translation binding and all five localized labels in
`static/shared/vera/index.html`. Website journey and architecture suites: 208
passed, one skipped. No deployment; the public page still has the old label.
Evidence: vera-public-browser-review.json and vera-public-browser-followup.xml.
This is public-page acceptance, not visual acceptance of the blocked local report.

## Final catalog reconciliation

The single-package Cowork check does not inspect the shared catalog. An explicit
check found Vera0.1.208 in that catalog against the current0.1.211 build. Regenerated
the catalog through `build_catalog` and verified it using `verify_catalog`; no
drift errors remain and Vera is0.1.211. Evidence: vera-0211-catalog-check.json.

The related task `migrate to GPT-6 Astra` reports PR525 merged/deployed with
server commit e0b98921 and successful AML/package checks. This historical
deployment is distinct from this task's uncommitted0.1.211 candidate and current
website localization correction; it supplies no authorization to deploy them.

## Catalog drift prevention implemented

The Cowork builder now regenerates the shared catalog after a selected-package
build and verifies the catalog during selected-package `--check`. Previously
both operations were skipped unless all configured packages were selected,
which reproduced the0.1.208/0.1.211 mismatch. Other package binaries are not
rebuilt by this change. Two CLI regressions verify catalog refresh and read-only
stale-catalog rejection; the existing Vera catalog contract also passes.
The actual `build_claude_plugin_zip.py vera --check` now passes both the Vera
package (18 MCP startups/tool lists) and the shared catalog. Black and Isort
pass for the edited builder and test file. Evidence: catalog-partial-build-final.xml
and vera-0211-integrated-catalog-check.log. No deployment or publication.
