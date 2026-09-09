# Business planning: iteration and financing

## Intended behavior

One durable case supports repeated business decisions. A report records the current
assessment; it does not end the planning exercise. A follow-up such as a pricing
question or competitor event resumes the latest case, investigates the evidence,
updates the assumptions and calculations, and records the resulting decision and
next test. Both Vera and Clara use the same implementation.

Financing is an explicit purpose, separate from permission to share source data.
Bank debt assessment connects business credibility and the proposed financing to
repayment, adverse scenarios, borrower context and the lender's actual conditions.
Venture equity assessment connects market opportunity, advantage, traction, team,
milestones, cash runway, ownership and prospective investor return. Internal-only
planning needs no invented financing request. Mixed funding can include both.

## Implementation

1. Extend the shared case with a planning cycle and financing mandate. Preserve
   source, assumption and narrative identities. Read a prior report only as an
   explicitly registered source, within the existing case boundary.
2. Derive changes against that snapshot and require carried conclusions to be
   reconsidered when their planning basis changes. Record the current question,
   evidence, assessment, decision, next test and reopening condition. Preserve
   earlier output folders; support deliberate branches from an identified parent.
3. Validate financing coverage and links to the same scenario calculations. Show
   missing evidence and horizons, including debt repayments outside the model.
   Keep suitability and financing conclusions model-authored. Do not create a
   credit score, universal DSCR threshold or automatic investability verdict.
4. Render the cycle and financing assessment in the shared HTML/PDF report. Update
   workflow guidance, internal authoring contract, marketplace instructions,
   public explanations and function-specific data paths.
5. Exercise successive pricing, competition and financing revisions through the
   registered entry points, source and packaged code. Test stale conclusions,
   foreign/tampered parents, missing cash/terms, audience restrictions, and Italian
   rendering. Run formatting, typing, security, coverage and release gates.
6. Rebuild shared-module, Vera and Clara artifacts from canonical source, merge
   only after required CI is green, deploy through Git, verify live artifacts,
   and remove this task's temporary branch/worktree. Marketplace publication and
   platform acceptance remain distinct evidence, not inferred from ZIP creation.

## Judgment and evidence

Exact arithmetic, snapshot hashes, ID closure, change comparisons and finite
forecast coverage are mechanical contracts with reproducible correctness. Code
does not judge whether customers accept a price, whether a competitor changes the
market, or whether a lender/investor should finance the proposal. The model must
research and explain these conclusions, propose tests and preserve uncertainty.

Design references consulted on 2026-09-09:

- [EBA loan origination and monitoring](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/credit-risk/guidelines-loan-origination-and-monitoring): repayment capacity and business-model assessment; not a claim of bank acceptance.
- [BDC lender and investor comparison](https://www.bdc.ca/en/articles-tools/blog/what-difference-between-lenders-and-investors): financing purpose, realistic cash forecasts and repayment structure.
- [Sequoia business-plan guidance](https://sequoiacap.com/article/writing-a-business-plan): customer problem, market, competition, business model, team and financials.

## Baseline

Clean worktree at origin/main `3be041ca`. The four existing business-planning
suites passed: 132 tests. The primary checkout contains unrelated modifications;
this task preserves them.

## Local implementation evidence

- Shared workflow tests: 161 passed; coverage 82.89%, including resumed Vera runs
  with exact parent-source receipts and Clara revision folders. Changed case
  approvals, stale narrative/financing conclusions, foreign or altered parents,
  missing repayment inputs and incomplete funding horizons have negative tests.
- Black, Isort, Mypy for the new decision modules, and Bandit for the planning
  scripts passed. Both complete privacy registers passed after source review.
- Codex, ChatGPT-upload and Cowork releases rebuilt from source for Vera 0.1.224
  and Clara 0.1.189, with shared Business Planning 0.3.0.
- A declared synthetic subscription exercise changes closing cash from -280 to
  320 after a conditional price revision, then -40 after a competitor scenario.
  Replacing debt with equity brings closing cash to 190 while leaving monthly
  operating loss at -20 and a model-authored conclusion that VC funding is not
  supported. This tests arithmetic and recorded reasoning, not market demand.
- Bank and equity discussion PDFs were produced with the real declared Chromium
  renderer, with network requests disabled. Visual review identified and corrected
  financing-heading pagination and print-only history controls. The reports keep
  pending professional review and synthetic evidence labels explicit.

The remaining release steps are PR/required CI, Git-based deployment, live artifact
verification and removal of this task's temporary branch/worktree. A real lender
or investor has not reviewed the output. No approval or acceptance is inferred
from structural coverage, tests or successful rendering.

The wider local package/privacy/website/icon checks passed: 657 tests, with two
optional checks skipped. Canonical source-to-package checks passed for both
products after the final report-print changes.
