> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Startup Business Plan case contract

`business_plan_case.json` is the reviewed bridge between model-led planning
judgment and deterministic calculation. It records a professionally reviewed
startup or new-venture stage in plain language; deterministic code checks only
that the description is present and does not classify the venture. Pilot or
early historical evidence is optional; confirmed opening balances and
assumptions are not.

## Top-level fields

- `schema_version`: `vera.startup_business_plan_case.v1`.
- `case_id`: stable lowercase identifier.
- `entity_name`, `venture_stage`, `audience`, `reporting_currency`.
- `periods`: 1–60 unique ordered labels.
- `reconciliation_tolerance`: non-negative canonical Decimal text.
- `review`: `status=reviewed`, reviewer, and a timezone-aware ISO 8601 timestamp
  after the professional confirms the complete case.
- `evidence_register`: reviewed historical facts, opening facts, external
  evidence, management assumptions, or model hypotheses.
- `opening_balance`: exact opening values and their evidence IDs.
- `assumptions`: confirmed numerical or structural assumptions.
- `scenarios`: up to eight user-meaningful scenarios with the same period set.

## Evidence and assumptions

Evidence kinds are `historical_actual`, `opening_fact`,
`management_assumption`, `external_evidence`, and `model_hypothesis`. Their
status is `reviewed`, `confirmed`, or `unverified`. The selected kind is a
model-led and professional decision; deterministic validation checks only the
reviewed record shape and reference closure.

Every assumption has a unique ID, description, category, evidence IDs,
effective periods, rationale, and `status=confirmed`. An assumption may use a
confirmed model hypothesis, but the workflow must not disguise it as a sourced
fact. Referencing unverified evidence keeps the result `partial`.

## Opening balance values

All monetary values are canonical Decimal strings. Values are non-negative
except that `equity` may be negative when the reviewed opening position
requires it:

- `cash`;
- `accounts_receivable`;
- `inventory`;
- `other_current_assets`;
- `net_fixed_assets`;
- `other_non_current_assets`;
- `accounts_payable`;
- `debt`;
- `other_liabilities`;
- `equity`.

The opening statement must reconcile within the reviewed tolerance. A startup
may use zero values only when those zero opening facts are explicitly
confirmed; the runner never supplies them.

## Scenario schedule

Each scenario contains one row for every ordered period. Each row has canonical
non-negative Decimal strings for:

- `revenue`, `cogs`, `operating_expenses`;
- `depreciation_amortization`, `interest_expense`, `tax_expense`;
- `capital_expenditure`;
- ending `accounts_receivable`, `inventory`, `other_current_assets`,
  `accounts_payable`, and `other_liabilities`;
- `debt_draws`, `debt_repayments`, `equity_contributions`, and `dividends`.

Each row also lists the confirmed `assumption_ids` effective in that period.
Every confirmed assumption must be applied by at least one scenario row; an
unused assumption blocks the case instead of disappearing silently.
The runner uses ending working-capital balances to calculate period movements.
Interest and tax expense are treated as paid in the same period in this initial
contract; deferred tax, tax payable, non-cash interest, asset disposals,
leases, and other specialist schedules are unsupported unless the contract is
extended and reviewed.

## Result boundary

The runner creates no balancing plug. It blocks on a failed opening or period
reconciliation and on debt repayments or depreciation that would make debt or
net fixed assets negative. Negative cash is retained and reported as a funding
requirement. The reported break-even period is the first period with
non-negative EBITDA, not a sales-volume or revenue threshold. Reconciliation
does not approve the assumptions or establish that
the business plan is probable, financeable, or suitable for its audience.
