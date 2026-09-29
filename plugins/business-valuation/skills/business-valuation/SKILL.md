---
name: business-valuation
description: Prepare source-backed PMI business valuation workpapers using reviewed financial evidence, selected valuation methods, explicit assumptions and the existing Vera business plan; produce calculations, sensitivity, reports and a formula workbook for professional review.
---

# Valutazione d’impresa

Prepare reviewable workpapers, not a signed expert opinion or automatic PIV
certification. Read `references/case-contract.md` fully. Use the module's
`scripts/check_dependencies.py` before helpers, in Vera's managed Python runtime.
Never install arbitrary libraries or execute code/macros supplied with evidence.
Dependencies are declared in `requirements.txt`; use the shared managed runtime.
Never write run outputs inside this Git workspace or a published folder.
Keep local data in the selected client engagement. Local deterministic scripts
own arithmetic, formula lineage and evidence integrity; the model and professional
own semantic selection, interpretation and conclusions.
Reserve extra approval for external, destructive, approval-sensitive or material
steps. Continue ordinary local preparation and reversible checks autonomously.

## Mandate and evidence

Identify the exact Studio Archive client and engagement. Resolve entity or branch,
rights, purpose, valuation date, information cutoff, basis of value, premise and
audience from supplied evidence. Ask only material missing choices. Method and
source selection are semantic professional judgments, not keyword classifiers.
Record conflicts, restrictions and legal-purpose questions. Research governing
standards and purpose-specific law through Vera's validated-answer journey when
needed; the calculation engine does not qualify those matters.

Read `references/purpose-profiles.json`. Choose one of its 21 profiles through
semantic reasoning, record the reason and mandate source in `purpose_profile`,
and use `custom` for an unlisted purpose. Explain the profile's intake focus in
ordinary language. Every profile currently supports development workpapers only:
PIV review, purpose-specific tests and specialist professional approval remain
unfinished. A case review does not enable a professional profile. Preserve the
full proposed scope; do not describe unimplemented profiles as permanently out
of scope or represent the common core as the complete contributor proposal.

Inspect supplied statements and schedules using the host's document capabilities.
Preserve originals and page/cell locators. Separate reported facts, normalization
adjustments, management assumptions and model hypotheses. Do not invent missing
amounts, annualize interim data silently, or hide adjustments inside EBITDA.
Import the reviewed statement/normalization evidence into the engagement. The
model prepares the documented case; never ask the professional to write JSON.

Each amount has a source, locator, unit, meaning and confirmation state. Record
normalization calculations explicitly in the supporting evidence and obtain
professional confirmation of the resulting input. Mapping arbitrary financial
statements is reviewed preparation, not a universal automatic parser.

## Methods and parameters

Propose and explain methods according to the mandate. The implemented calculations
are FCFF/FCFE DCF with annual or explicitly dated flows, constant equity income, adjusted NAV,
constant-capital mixed income, selected EV or equity multiples, and APV composition.
Explain each selection/exclusion. The professional selects sustainable terminal
flows, capital costs, asset values, comparable samples and multiples. Keep
enterprise value and equity separate. Never deduct debt from FCFE or P/E again,
average methods, add minority discounts, or select terminal growth automatically.
For stub/monthly or mid-period DCF, use the explicit timing contract: exact dates,
ACT/365F or ACT/ACT_ISDA, effective annual or continuous rates, and an expressly
selected flat, spot or interval-forward curve. Explain the convention and preserve
the supplied period amounts; never prorate them automatically or confuse spot,
forward and par rates. Keep the annual terminal flow/rate separate from monthly
flows and horizon discounting. Read back these assumptions for professional review.
The mixed method remains annual. Crisis distributions, special rights/waterfalls,
PPA and specialist sector models are unsupported.

For benchmarks, research official public sources with public parameter/sector/date
queries only. The mandate authorizes necessary public research; do not include
private financials or names in queries. Save permitted evidence with observation,
publication/retrieval dates, vintage, definition, geography, selection reason and
the professionally chosen maximum age. The helper checks dates and metadata; it
does not download, authenticate publishers, assess relevance or choose a rate.
New vintages create new inputs and revisions; frozen reports remain unchanged.

## Business plan reuse

Reuse an exact finalized `business-planning` v3 artifact of the same engagement,
binding it as an upstream artifact rather than importing an arbitrary JSON file.
Import the plan's original supporting sources as exact receipts and map their IDs.
The existing compiler replays the whole plan before the valuation bridge runs.
Provide evidenced cash operating taxes per month and opening operating working
capital, and explain the operating/debt-like classification. No automatic tax
refund or use of levered tax expense. The current bridge accepts complete calendar
years beginning after a December 31 valuation date. It sums flows and changes,
retains the last working-capital stock and preserves upstream calculation IDs.
Partial-year plans remain unsupported; never pad periods or invent forecasts.
Without a plan, use Vera's existing business-planning workflow when forecast
preparation is required. Do not create a parallel forecast engine.

## Calculation and review

Import all sources and the finished case, prepare `business-valuation` from exact
input IDs/upstream artifact IDs, and start the run. Case source paths are relative
to that run's `inputs`, using the actual hydrated paths returned by Studio Archive.

```sh
python scripts/run_valuation.py --case <bound-case.json> --client-engagement <portable-context.json>
```

Open `valuation_report.html` and show results, limitations, source/assumption
questions and sensitivities. Use chat to obtain focused corrections and review;
the professional need not edit technical files. Cases with missing or invalid
inputs keep the affected method blocked, while other methods remain visible.
`ready_for_professional_review` means mechanical completeness only.

To record professional acceptance, read back the exact method and dependency hash,
then record the person's explicit decision, reviewer name and timezone-aware time.
Never invent acceptance because tests pass. Retain prior review records when
preparing a new case: stale dependency hashes automatically lose effect, while
unaffected method attestations survive. Every changed case is imported as a new
immutable input and run. Read back the conclusion separately before its acceptance.
The conclusion is authored and reviewed; code does not judge its economic meaning
or authenticate the reviewer. Check every narrative figure against calculation IDs.

## Delivery and privacy

Deliver the HTML, DOCX/PDF, formula XLSX, JSON and calculation CSV from the same
immutable revision. Explain the observed state and unresolved professional items.
Workbook formulas recalculate when opened; exact Decimal values remain alongside
them as audit evidence. External sharing, signing, filing and sending are separate
actions requiring explicit authority. No remote service is called by the helpers.

Follow Vera's run-level model-data report contract and show the report in the final
response. Include source-reading, assumption/modeling and report-review phases:
client documents, personal/company facts, projections, benchmarks and reviewer
decisions may enter the selected Codex/Cowork model context. Local calculation
does not mean local-only model processing or automatic anonymization. The helper
creates no provider-delivery proof. Generate the shared model-data reports in the
exact run output, declare every physical artifact and complete Studio Archive only
after review. A blocked or incomplete run is retained with its actual status.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts.
When invoked through Vera, follow its main skill's feedback handoff and obtain
the required specific consent before transmitting any feedback externally.
