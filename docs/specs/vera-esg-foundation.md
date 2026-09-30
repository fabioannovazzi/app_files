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

The user approved the blank missing-data excerpt and Archive registration fixes
on 29 September, and the state-size correction on 30 September 2026. A public CLI
probe had accepted an 8,381,003-byte request but saved an unreadable 8,393,954-byte
state. The corrected helper measures exact UTF-8 state bytes before writing drafts
or state. The same request now fails without changing the 11,871-byte saved case,
and resume succeeds. ASCII and Unicode regressions verify unchanged state and
output files. No history is truncated or pruned.

Current local evidence after integration of main `8f662195f`:

- 50 ESG regressions pass; 88.72% coverage across the three new scripts.
- 601 combined ESG, merger, transformation, CNC, assetti, filesystem, website,
  registry and routing tests pass.
- Canonical Codex, ChatGPT-upload and Cowork archives match source for all three
  products. Each Vera archive passes all six synthetic demo checks.
- The 43-entry Geneva catalogue preserves the recorded scope judgments.
- All 46 courses retain identical authored JSON except source bindings relative
  to main. `docs/releases/2026-09-30-vera-esg-course-source-review.json` records
  the additive ESG registry and prepared-lesson exclusion review. Historical
  editorial evidence is not new visual or learner acceptance.

The required package/update/privacy suite and exact-commit CI must pass before
review readiness is reported. Evidence logs remain in the recovery folder.
The configured ESG Black, Isort, Mypy and Bandit commands pass. A supplementary
Mypy invocation using the stricter shared-runtime config reports five pre-existing
errors in the synthetic demo; that configuration is not the ESG CI gate and no
production change was made to satisfy it. An earlier broad Cowork invocation also
exposed an unchanged projection-note assertion on a source-preserved teaching
reference, separate from the required CI gates.

Candidate versions: Vera 0.1.286, Clara 0.1.225, Lucia 0.1.65, Studio Archive
0.1.41, ESG component 0.1.0. Clara and Lucia rebuild because they embed the shared
contracts and course policy; ESG is exposed only by Vera. Versions exceed main
and the inspected open candidates. Recheck the sequence before publication.

These checks cover source and packaged synthetic execution. No merge to main,
deployment, Marketplace publication, enabled-host acceptance, real-client work
or Discord reply is included. Complete reporting, assurance and renderers remain
the ordered backlog above, as required by the recovered first-tranche brief.
