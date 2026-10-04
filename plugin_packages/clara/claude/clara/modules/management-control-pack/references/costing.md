# Costing within Management Control Pack

Use this path for a question about costs and margins by job, product, customer,
channel, service or segment. It shares the public `management-control-pack`
workflow and Studio Archive lifecycle. A complete monthly reporting pack still
uses `run_pack.py`; its ledger requirement and calculations are unchanged.

## Establish the decision and evidence

Start with the decision, its horizon and the available records. Examples include
which jobs contribute after their specific fixed costs, whether shared support
changes product margins, or the incremental effect of an additional order.
Inspect the authorized source records and ask only unresolved material questions.
Do not ask the professional to author JSON or select a technical algorithm.

The model and professional establish the operating perimeter, period, one view
of non-overlapping objects, revenue, consumed costs, and independent source totals.
Classify fixed/variable separately from direct/indirect/entity. A direct fixed
cost is not automatically avoidable. Split mixed costs using reviewed evidence;
do not classify accounts with keywords or fabricate hours, drivers or consumption.
Record missing information and what it prevents. When sufficient source totals
or the variable cost basis are unavailable, produce an evidence-gap plan rather
than unsupported margins. Retain the registered run and its workpapers.

Select the methods justified by the question and data. Explain that choice in
the reviewed mapping note. Direct costing calculates contribution after variable
costs, including reviewed variable indirect allocations. Direct Evoluto then
subtracts specific fixed costs. Full costing uses a reviewed traditional driver;
ABC uses reviewed activity pools. Practical capacity retains unused fixed costs
separately. Common fixed costs are allocated on an actual basis or retained at
entity level according to the reviewed policy. An absent unrequested method
does not make the requested scope incomplete.

The implemented path supports EUR, one period of consumed operating costs and
up to 200 objects of one dimension. It does not capitalize inventory, provide
ERP/POS connectors, calculate food/recipe costs, or optimize production.
Existing variance analysis owns price-volume-mix; business planning owns
break-even and wider financial scenarios. Link the reviewed outputs when these
are needed instead of creating competing calculations here.

## Prepare the internal case

Run `python scripts/check_dependencies.py`. In Claude, select the client and
engagement, import the actual records (including recorded statements or approved
estimates), then prepare/start `management-control-pack`. Use the exact returned
context and output directory. In Cowork, use the existing product archive-session
adapter for the explicitly connected client folder; do not fabricate a context
or claim a portable Claude registration. If that binding is unavailable, preserve
the reviewed case and explain the blocked calculation.

Write `reviewed_costing_case.json` inside that run output. Its contract is:

```json
{
  "schema_version": "vera.costing_case.v1",
  "entity": "Reviewed company name",
  "language": "it",
  "audience": "internal",
  "decision_question": "Which jobs contribute after specific fixed costs?",
  "methods": ["direct_costing", "direct_costing_evoluto"],
  "case": {},
  "decisions": [],
  "accounting_bridge": null
}
```

`case` uses the documented reference field names:

- `meta`: `schemaVersion: "1.0.0"`, `caseId`, the exact archive `clientId` and
  `engagementId`, `currency: "EUR"`, ISO `periodStart`/`periodEnd`,
  `basis: "accrual_consumed"`, `perimeter: "operating"`, and a boolean
  `demonstration`. Only genuine synthetic examples set demonstration to true.
- `evidence`: records with unique `id`, `kind` (`document`, `client_statement`,
  `estimate`, `synthetic`), `status` (`documented`, `declared`,
  `approved_estimate`, `synthetic`), a concrete `locator` and `source_sha256`
  matching an actual selected, archive-bound source. Assertions and estimates
  need a recorded source too; a label is not evidence of approval.
- `objects`: `id`, `label`, one shared `dimension` (`job`, `product`, `client`,
  `channel`, `service`, `segment`), decimal-string `units`, `unit`, integer
  `revenueCents`, and nonempty `evidenceIds`.
- `costs`: `id`, `label`, integer `amountCents`, reviewed `behavior` (`fixed` or
  `variable`), `traceability` (`direct`, `indirect`, `entity`), `objectId`,
  `poolId`, and `evidenceIds`. A direct cost names one object and a null pool;
  an indirect cost names one pool and a null object. Entity costs are fixed
  with both references null. Signed corrections retain their sign.
- `pools`: `id`, `label`, `driver` or null. Each driver has `name`, `unit`,
  `weights` covering every object including zeros, `rationale`,
  `capacityPolicy` (`actual` or `practical`) and `capacity` (null for actual,
  a positive decimal string for practical). Quantities have at most six places.
- `traditionalDriver`, `commonPolicy` (`allocate` or `retain_entity`) and
  `commonDriver` (null when retained; actual basis when allocated).
- `sourceTotals`: independent reviewed `revenueCents`, `costsCents`, and
  `evidenceIds`. Do not manufacture an independent control by summing the same
  mapped rows and calling that sum the source total.
- `review`: `status: "reviewed"`, named `reviewer`, `reviewedAt`,
  `mappingVersion`, and explanatory `note`. Synthetic examples may instead
  use `status: "synthetic"`; that never proves professional acceptance.

Identifiers contain letters, digits, underscores or hyphens, begin with a letter
or digit, and have at most 80 characters. Monetary inputs are integer cents,
not binary floating-point EUR values. Normalize source conventions before review.

An optional `accounting_bridge` contains `sourceProfitCents`,
`sourceEvidenceId`, `basis`, `reviewer`, and `entries` with `id`, `reason`,
`evidenceId` and signed `profitEffectCents`. Its sum must equal the costing
operating result. Without it, the report explicitly limits reconciliation to
the reviewed costing source totals; it does not claim accounting reconciliation.

## Decision scenarios

Optional `decisions` records contain `id`, `type`, `label`, reviewed `basis`,
`evidenceIds` and `amounts`. Supply every amount as nonnegative integer cents,
including explicit zeros. Use separate evidence for avoidability and capacity
effects; never derive them from a Full or ABC allocation.

| Type | Required amount keys | Positive result means |
| --- | --- | --- |
| `incremental_order` | `revenueCents`, `variableCents`, `additionalFixedCents`, `opportunityCents`, `oneOffCents` | Incremental profit from the order under the stated assumptions |
| `make_or_buy` | `avoidableMakeCents`, `purchaseCents`, `transitionCents`, `releasedCapacityContributionCents`, `strandedFixedCents` | Profit improvement from buying rather than making |
| `discontinue` | `lostRevenueCents`, `avoidedVariableCents`, `avoidableFixedCents`, `exitCents`, `replacementContributionCents`, `strandedFixedCents` | Profit improvement from discontinuing |

Stranded fixed costs remain visible and are never treated as savings. These
comparisons require professional interpretation; they do not select an action.

## Calculate, interpret and deliver

```bash
python scripts/run_costing.py \
  --input <exact-bound-source> [--input <exact-bound-source> ...] \
  --case <run-output>/reviewed_costing_case.json \
  --client-engagement <exact-context.json> \
  --output-dir <run-output>/costing-01
```

Use a fresh calculation folder after a change. Existing outputs are not
overwritten. Read the execution receipt and hash-validated `model_context.json`
before interpretation. The complete JSON retains cost classifications, drivers,
evidence and calculation workpapers locally. The bounded context contains the
question, selected scope, results, controls, limitations and up to 60 calculated
rows per section; it excludes the raw costing workpapers and evidence locators.
All calculated metric IDs remain available for commentary.

The normal outputs use the existing pack filenames: JSON, Excel, Markdown,
HTML, execution receipt, model context/receipt and commentary template. Complete
`management_commentary.json` with metric-linked observations, separate hypotheses,
questions and limits, then use the normal `finalize_pack.py` and
`preview_report.py`. Inspect the HTML and workbook. Deliver both the calculated
schedules and the decision memo in the final report; unanswered decisions remain
explicit. Everything stays a professional-review draft.

A missing driver affects only requested methods that need it. A partial scope
may be reported with its missing methods explicitly disclosed. A wholly blocked
scope or failed accounting bridge cannot be finalized. Case changes alter the
pack identity and invalidate earlier commentary. Import changed source records
as new versions and preserve earlier runs and reviews.

Record the actual model-visible phases in the normal run-level model-data
report. Finalize all physical artifacts through the existing Studio Archive
ledger and complete the run only after its normal review. Do not implement the
contributor package's proposed host adapter or separate approval registry.

## Integration evidence

Source: Francesco's 29 September 2026 costing contribution in
https://discord.com/channels/1550191335917625474/1554556999939657888/1554589848302788729
(`skill.zip`, SHA-256
`c66eaee443bac63fd5f94ceeca7a0b3a64c84ecaba95a8e4f5e7db6b62ee2bca`).
The comparison baseline was repository commit
`bebefc9b5f187bbcc5619a1b603363581ec68158`.

The Python costing engine preserves the reference arithmetic on six synthetic
cases. Existing management reporting, variance, business planning, archive
binding, commentary validation and report delivery remain the reused components.
The selected-method completeness rule and real archive binding replace the
reference's all-method comparison and mocked adapter. Source, package and
synthetic lifecycle checks do not establish installed-host or real-client
professional acceptance.
