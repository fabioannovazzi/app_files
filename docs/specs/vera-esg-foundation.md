# Vera ESG: recovered brief and first implementation tranche

## Evidence and scope

Requested message: https://discord.com/channels/1550191335917625474/1554383339069378600/1554534695113592843

Recovered six messages and three attachments, with empty pagination before and
after the retrieved history. The original contribution is attributed in Discord
to Francesco Giraldo, 22 September 2026. The developer ZIP is a proposal, not an
installed product. The 29 September implementation reply specifies this first
tranche and retains later stages as a backlog. No contributor code was executed.

- Developer ZIP SHA-256: `36e501beee344e8e0e7c882f138c5f459b893d24b82b34cf7640b82d68783226`.
- 57 files; all 56 manifest entries matched bytes and hashes; no absolute paths,
  parent traversal or symlinks.
- Both reply attachments are retained separately by message ID, preserving their
  identical original filename `risposta-vera.md`.
- Local recovery: `outputs/vera-esg-discord-recovery` in the primary checkout;
  source messages, original attachments, inventory and readable documents remain
  there. Signed CDN links are recovery metadata, not permanent public links.

The supplied source research dates from 20 September. It has not been accepted
as current law, and the seed is not a complete catalogue. No compliance claim,
professional opinion, deployment or Marketplace publication follows from it.

## Requirement to implementation to verification

| Requirement | Implementation | Verification |
| --- | --- | --- |
| R01/R02 separate mandate and reporting basis, recover identity | Dedicated semantic skill; start/resume with Archive v2 context | Public start/retry/resume tests; synthetic demo |
| R04 versioned source packages | Separate unverified configuration plus versioned source records | Schema and source-gate tests; completeness/legal flags cannot be enabled |
| R07 selected immutable inputs and locators | Reuse Archive import/prepare; CSV data row/column and text line binding | Zero/missing values, bad locators, wrong IDs, changed bytes tests |
| R17 exact professional decisions | Reviewer-declared record and version/hash dependencies | Cross-engagement, nonexistent/stale ref and blank-reviewer tests |
| R17 supersession | Immutable entity versions, transitive current status, new Archive run with historical inputs | Synthetic input update invalidates decision and draft without rewriting old run |
| R20 partial deliverables | Immutable Markdown/JSON foundation drafts and state | Draft file integrity; unsupported conformity/assurance claim tests |
| R21 isolation and integrity | Existing Archive guard, closed output names, optimistic state check, write lock | Input/state/artifact tampering, symlink and stale-write tests |
| R22 replay | Idempotency key bound to complete request | Identical retry/no duplicates, conflicting-key rejection |

## Contract adaptations

The contributor's full schema covers eleven entities. The executable first-tranche
schema covers case, evidence, source, decision and artifact, plus strict request
contracts and references. Immutable envelopes carry version, hash and exact
dependencies, which the proposal did not fully specify. The Archive owns
client/engagement/run identities and selected immutable files. The ESG state
owns observations and professional decisions within the run, not another archive.

Evidence keeps the exact extracted string beside the interpreted decimal or null.
The helper validates representation and source identity, not semantic correctness.
Missing and non-applicable states are distinct. Optional metric/disclosure IDs are
unqualified links, not computed metrics or verified catalogue coverage. Reviewer
identity is declared, not authenticated or digitally signed. A hash detects
unexpected edits against recorded state; it is not a provider-signed attestation.

Updates require a new Archive run containing both historical and new input IDs.
The old run remains a historical view; the successor carries the current work.
The successor starts from an explicitly selected previous context and a distinct
run. Case-field changes stale dependent work; changing an evidence ID's version
stales only its dependency descendants. Missing historical sources stop recovery.
The current implementation supports a single local writer. A crash-held lock is
reported for inspection rather than silently removed.

## Ordered remaining phases

1. Import a complete official voluntary catalogue, reconcile datapoints and
   obtain competent professional review; build collection, calculations,
   disclosure review, report and action plan from one data register.
2. Version-qualified ESRS, materiality and taxonomy, with relevant source and
   denominator reconciliation. Do not turn this seed into an applicability engine.
3. Professional acceptance and independence, assurance program, workpapers,
   actual performed procedures, findings and professionally decided conclusions.
4. Comparable-period updates, final DOCX/PDF/XLSX renderers, visual review and
   representative professional acceptance. No phase is implied by this foundation.

## Verification evidence

See the task's test log and synthetic demo. The contributor's 34 reference tests
and 37 proposed product scenarios are not claimed as integration passes.
The user approved the correction of blank missing-data excerpts and the Archive
MCP workflow registration on 29 September 2026, together with the package integration.
The corrected ESG and Studio Archive regressions pass. The synthetic demonstration
passes all six recorded checks; its run folders preserve the exact evidence and drafts.


Local verification after the approved correction and integration:

- 48 ESG regressions pass; 88.58% coverage across the three new scripts.
- 439 package, update-notification and privacy checks pass; two conditional skips.
- Codex, ChatGPT-upload and Cowork archives all match the canonical source.
- The six synthetic acceptance checks also pass from each extracted Vera archive.
- Black, Isort, Mypy and Bandit pass on the new scripts; whitespace checks pass.
- Existing course content remains identical after excluding source bindings;
  `docs/releases/2026-09-29-vera-esg-course-source-review.json` records the two
  additive shared changes. Historical editorial reviews are not represented as
  new visual or learner acceptance.

Candidate versions: Vera 0.1.282, Clara 0.1.223, Lucia 0.1.63, Studio Archive
0.1.39, ESG component 0.1.0. Clara and Lucia rebuild because they embed the
shared contracts and course policy; ESG is only exposed by Vera. Versions were
selected above main and the inspected open PR candidates. Recheck the release
sequence and integrate intervening main changes before any publication.

These checks cover local code and packaged execution, not Marketplace Published
status, deployed public pages, enabled host installation or professional use.
The new CI matrix schedules the ESG tests on Linux and Windows; those results
remain separate from the observed local macOS run. No Discord reply is sent.

### CI integration follow-up

Both ESG CI matrix jobs passed on Linux and Windows. The initial broader CI
run identified omitted CLI classifications, older website inventory expectations,
a shared-archive privacy fingerprint in Lucia, and the Geneva catalogue snapshot.
These records are now reconciled: ESG requires its portable `--context`, the
developer demo is classified separately, and Geneva suitability remains explicitly
unresolved. The focused 370-test integration suite and 40-entry catalogue check
pass. Source fingerprints and all affected packages were rebuilt; no ESG behavior
or existing professional capability was changed to satisfy these checks.


### Integration with the merger foundation

Main advanced to `bbc94c37a` after the first complete 34-check CI pass on
`bb4e4773`. The task branch incorporates that main revision, preserves both
functions, regenerates the combined packages and keeps the unpublished candidate
versions above main. The combined catalogue has 37 function entries and four
helpers; both new foundations remain unresolved for Geneva professional use.

The merged source passes 48 ESG tests at 88.58% coverage and 411 merger,
Archive/filesystem, website, registry and routing tests. All three product
packages match canonical source. All six synthetic ESG checks pass from each
Vera archive format. CI must qualify the exact integration commit independently.

A broader local Cowork test invocation exposed a pre-existing assertion requiring
a projection note on every reference, including the unchanged source-preserved
`learn-with-vera/references/get-started.md`. It also omitted the parent test
fixture through `--confcutdir`; these are not evidence of an ESG runtime failure.
The version guard compares uncommitted work with HEAD, so the pending merge
reports the already reserved unpublished Vera candidate as unchanged. Its final
result and the required package suite are checked again on the committed source.

### Subsequent main integration

Main then advanced to `cf648f7c3` with the synthetic transformation prototype.
The ESG branch preserves that release as well as the merger foundation, combines
all three registrations and retains their separate scope boundaries. The full
Geneva catalogue now has 42 entries; all three additions remain unresolved for
professional Geneva use. The existing merger source citation is preserved.
The combined ESG, merger, transformation, filesystem, website and routing suite
passes all 505 tests. Candidate versions remain reserved and unpublished by this
task. Packages are rebuilt from this combined source; CI qualifies each commit
separately. No ESG runtime behavior changed during either merge.
