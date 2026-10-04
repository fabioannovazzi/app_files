---
name: fusione-guidata
description: "Prepare reviewed P1 domestic OIC incorporation workpapers for independent or directly wholly owned companies: evidence-bound valuation bridges, exact exchange allocations, accounting bridges, event calendars and review dossiers, with verified multi-company Studio Archive imports and revision history. Preserve P0 case preparation; later branches remain unsupported."
---

# Fusione guidata — P1

Use the existing authenticated Codex or Cowork session. No model API key is
required. Resolve this module root and run `python scripts/check_dependencies.py`
using Vera's shared managed Python runtime. Read `references/case-contract.md`
and `references/p1-contract.md` before writing requests. The component uses only
the standard library, as declared in `requirements.txt`; do not install packages at runtime.

Use the user's language. Explain the work in professional terms, without requiring
the user to choose a technical skill or edit JSON. You prepare requests from the
inspected evidence and review choices. Keep outputs in an explicitly selected case
or engagement output folder outside the plugin and repository source.

Never write run outputs inside this Git workspace or plugin source. Use the
selected engagement output directory, or a separate user-authorized demo directory.
Explicit approval is reserved for external, destructive, approval-sensitive or
material steps. Prior authorization covers reversible case preparation; actual
professional confirmation still belongs to the named reviewer.
Deterministic local scripts own exact arithmetic, calendar offsets, hashes and
structural validation. The model owns semantic interpretation, source relevance
and proposed dependency selection.

## Start from the actual case

Identify whom the professional assists, mandates/conflicts, the two companies,
ownership and rights, objectives, intended dates, accounting framework, acquisition
funding and exceptional conditions. Reuse available evidence. Ask only questions
that alter a material choice; explain why they matter. A missing fact remains
`unknown`, a contradiction `disputed`, both with null values. Never turn either
into zero, false, consent or an exemption. Independent work can continue.

The model proposes the branch and explains its evidence. P1 implements workpapers
for `ordinary_domestic_oic` and `wholly_owned_domestic_oic`: two Italian OIC
companies, incorporation, ordinary homogeneous rights and no cash adjustment,
reciprocal/own holdings, MLBO, crisis or regulated special case. The direct wholly
owned branch also requires its exact ownership edge. Record the declared scope
facts with evidence; code checks those declarations and arithmetic, not legal
classification. Foreign, IFRS, partial/90%, inverse, sister-company, MLBO,
new-company and other special combinations require later work and must remain
explicitly unsupported. Do not relabel a case to pass the P1 checks.

## Evidence and Studio Archive

Read the two selected Studio Archive client and engagement identities using its
actual ledger. Register each company with its authorized source roots, then
`bind_archive` with the exact client root, client ID and engagement ID. Import
only explicitly selected input IDs using `import_archive`; the adapter verifies
the receipt and stored bytes, retaining identity, path, hash and locator in the
new case Evidence. It does not scan other clients or copy a combined dossier back
into an individual client's archive. Ordinary selected-file `import_evidence`
remains available. Model-extracted facts refer to their actual page/row evidence.

Read the current company grants. Never change actor or invent an administrator to
bypass a denial. Actor IDs are declared local workflow identities, not authenticated
accounts; filesystem permissions and encryption remain outside this helper.
Archive bindings require a case administrator. The adapter reads existing archives
and writes the selected case only. It neither closes engagements nor changes runs.

## Sources and review

Read `references/p1-source-review.md`. Its public sources and candidate calendar
recipes are starting evidence, not an approved rulepack. Use the host's authorized
research workflow to check the current primary text for the actual dates and case.
Use generic public queries without client identifiers. Store the selected snapshot
as Evidence, then SourceVersion and RuleVersion with exact references, applicability,
exceptions and test references. A failed access is `failed`, never "no change".
The helper has no network client or automatic source monitor.

The model selects pertinent sources, interprets exceptions and proposes rules.
Code checks shapes, hashes, exact periods and calculations. Obtain the named
professional's actual confirmation of each rule and branch scope before treating
it as reviewed. Never record an approval on their behalf. Confirmations retain
exact content/version, role, author, time, scope and confirmation evidence; they
are not electronic signatures or proof of identity.

## Prepare and review the workpapers

Use `apply` action `workpaper`, selecting one kind at a time and its exact input
references. Read the persisted result and issues before moving to dependent work.

1. **BranchDecision:** record the proposed branch, both companies, explicit scope
   facts, rationale, source-backed rules and ownership evidence. Missing or
   conflicting inputs persist as a blocked workpaper, without an invented result.
2. **Valuation:** for the independent branch, record each reviewed equity value or
   enterprise-to-equity bridge, methodology and matching valuation date. The model
   and professional perform valuation; the code only executes the stated bridge.
3. **ExchangeModel:** supply totals, nominal value, share versus capital-unit
   convention, and every shareholder's evidenced holdings. The output retains the
   exact ratio, new units, capital increase, allocation and resulting fraction per
   shareholder. Fractional shares are exposed and require a dedicated allocation
   beyond P1; never round silently. The wholly owned branch issues zero new units
   and retains acquirer shareholder proportions.
4. **BookBridge:** map each reviewed balance-sheet account and signed debit amount
   for the same reference date. Close/adjust the source balances professionally
   first; code does not infer period-end entries. Explicitly select reciprocal
   balance pairs and their eligible treatment. Unequal amounts remain exceptions.
   Select the participation account for the wholly owned branch. The output
   cancels that account or records new capital, calculates annullamento/concambio
   separately, and reconciles opening balances. Supply source-backed difference
   allocations and accounting policy; no automatic goodwill or reserve treatment.
   Preserve accounting values, asset tax bases, shareholder tax costs, reserves
   and loss positions separately. Tax treatment, deferred-tax assumptions and
   advanced loss/group calculations are professional work, not inferred by P1.
5. **Deadline:** prepare the case's event schedule from exact rule versions and
   evidenced anchors, including all relevant companies. Distinguish project
   publication, document availability, decision registration, creditor interval,
   document age, act/deposit and legal/accounting/tax dates. Select each applicable
   period and exception from sources; never infer a waiver from ownership or a
   shareholder consent from a creditor consent. Month arithmetic uses actual
   calendar months. Record any professionally reviewed holiday adjustment with
   its rationale; the raw boundary remains visible. Missing execution evidence
   remains `not_evidenced`; a date calculation never authorizes execution.
6. **LegalDocument:** assemble the reviewed workpapers and evidence-bound prose
   into the review dossier. Complete mandate, objectives, due diligence findings,
   feasibility, articles/statutory changes, profit participation, accounting
   date, special rights, management advantages, tax review, execution checklist,
   cut-over responsibilities and post-merger checks. The project should account
   for each pertinent art. 2501-ter field. Any selected 2505 exemption needs its
   reviewed source and scope; it does not remove every document. Reuse existing
   legal research, financial analysis, treasury, reconciliation or SARI skills
   only for their inspected contracts and genuinely required subwork.

Review due diligence across corporate/shareholder rights, financial balances,
intercompany differences, debt/covenants, tax positions, contracts, workforce,
property, litigation, grants and operational continuity. Capture material findings,
source locators, open questions, responsible professional and affected outputs.
A narrative that simply says "reviewed" is not evidence that the work happened.

The professional reviews valuation/congruity, accounting policy and any fiscal
conclusions. A draft can exist before approval; its issues and pending confirmations
stay visible. LegalDocument approval requires reviewed upstream workpapers. Final
execution still belongs to the responsible organs, notary and professionals.
P1 neither signs nor files nor treats an act PDF as proof of registration/effect.

## Changes, handoff and demonstration

On an input or source revision, read ChangeImpact and current status. Re-read the
actual evidence, revise only affected workpapers with current exact references,
and obtain renewed confirmations when required. Never overwrite approved history.
Moving the planned date also reopens dependent work and checks declared rule periods.
Scope completeness and material dependencies remain model/professional judgments.

`export` writes the scoped case history, readable Markdown and HTML P1 workpapers,
and the canonical local model-data report. Open `p1-workpapers.html` for review and
show the readable privacy report. Explain the current stage, open issues and next
professional action. For a retained document snapshot, place the approved draft
under this case's `drafts/` and register it with `artifact`, citing its exact inputs.
Do not describe a generated dossier as an executed merger or an accepted client case.

Run `python scripts/run_fusione.py demo-p1 --output /absolute/new-directory` for
two entirely synthetic cases using the real archive and case APIs. It preserves
requests, before/after dossiers, receipt provenance and assertion results. The old
`demo` command still exercises P0. Demo reviewers and approvals are synthetic.
Never turn these fixtures into actual professional confirmations. Report passed,
failed and not-run work separately; the contributor's full 36-scenario proposal
is not certified by these tests.

## What data reaches the model

The selected host may read company/client and engagement identities, ownership,
paths, selected source documents, ledger balances, tax bases, valuations, shareholder
allocations, event dates, source passages, model-authored drafts and professional
confirmations needed for the assignment. Imports verify complete selected bytes
locally. Reports retain all declared company scopes; nothing is automatically
anonymized. Codex/Cowork use the selected provider account, so local helper execution
does not mean local-only model processing. No helper network calls, uploads or
model API calls occur. Real-case model exposure is `not_measurable` until the
orchestrator records observable phases through Vera's normal report workflow.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts. Do not send feedback
or receipts from these runs. For ordinary professional work, show the readable
model-data report and follow Vera's existing feedback instructions. This component
provides no separate authorization to transmit client material.
