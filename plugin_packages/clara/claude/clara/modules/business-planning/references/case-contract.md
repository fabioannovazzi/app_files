# Business Planning case contracts

The shared workflow has two explicit professional contracts. Both record the
company stage in reviewed plain language; deterministic code checks only that
the description is present and never classifies a startup or established
company.

- `business_plan_case.json` uses the `accounting_financial` lens for Vera.
- `strategic_business_plan_case.json` uses the `strategic_commercial` lens for
  Clara.

## Vera accounting-financial case

### Top-level fields

- `schema_version`: `mparanza.business_planning_financial_case.v1`.
- `case_id`: stable lowercase identifier.
- `entity_name`, `company_stage`, `planning_objective`, `audience`,
  `reporting_currency`.
- `professional_lens`: exactly `accounting_financial`.
- `periods`: 1–60 unique ordered labels.
- `reconciliation_tolerance`: non-negative canonical Decimal text.
- `review`: `status=reviewed`, reviewer and a timezone-aware ISO 8601 timestamp
  after the professional confirms the complete case.
- `evidence_register`: reviewed historical facts, opening facts, external
  evidence, management assumptions or model hypotheses.
- `opening_balance`: exact opening values and their evidence IDs.
- `assumptions`: confirmed numerical or structural assumptions.
- `scenarios`: up to eight user-meaningful scenarios with the same period set.

Evidence kinds are `historical_actual`, `opening_fact`,
`management_assumption`, `external_evidence` and `model_hypothesis`. Their
status is `reviewed`, `confirmed` or `unverified`. Every assumption has a
unique ID, description, category, evidence IDs, effective periods, rationale
and `status=confirmed`.

All monetary values are canonical Decimal strings. Opening values are
non-negative except that `equity` may be negative. The opening statement must
reconcile within the reviewed tolerance. A company may use zero values only
when those zero opening facts are explicitly confirmed; missing history is
never converted to zero.

Each scenario contains one row for every ordered period. Each row has revenue,
COGS, operating expenses, depreciation and amortization, interest, tax,
capital expenditure, ending working-capital balances, debt draws and
repayments, equity contributions and dividends. Every row lists the confirmed
assumption IDs effective in that period. Every confirmed assumption must be
applied by at least one scenario row.

The runner creates no balancing plug. It blocks on failed opening or period
reconciliation and on debt repayments or depreciation that would make debt or
net fixed assets negative. Negative cash is retained and reported as a funding
requirement. Break-even is the first period with non-negative EBITDA.

## Clara strategic-commercial case

`strategic_business_plan_case.json` uses schema
`mparanza.business_planning_strategic_case.v1` and
`professional_lens=strategic_commercial`. It carries the same entity, company
stage, planning objective, audience, reviewed evidence register and confirmed
assumptions, plus:

- `planning_horizon` in reviewed plain language;
- source-linked strategic findings across model-selected domains;
- strategic options with benefits, drawbacks, evidence and assumptions;
- one recommendation linked to reviewed options;
- initiatives with owners, milestones and KPIs;
- risks, responses and open questions.

Every confirmed assumption references evidence. Every finding, option,
recommendation, initiative and risk references at least one reviewed evidence
item or confirmed assumption. The finalizer must be given the Clara case
workspace, reads the strategic case from its root and writes only to its
`business-plan` directory.

The model and consultant decide the meaning, domains, options, recommendation,
initiatives, KPIs and risks. Deterministic code checks only shape, explicit
lens, review status, unique identifiers, reference closure and artifact hashes.
It does not score or select a strategy.

## Result and handoff boundary

Reconciliation does not approve Vera's assumptions or establish that a plan is
probable or financeable. Reference closure does not approve Clara's market
evidence, strategic interpretation, feasibility or recommendation.

Both runners create `business_planning_handoff.json` using schema
`mparanza.business_planning_handoff.v2`. It identifies the source and receiving
lens, carries the source plan and review statuses, carries shared assumptions
without source paths and includes only the results needed for counterpart
review. A ready, partial or blocked source is labelled explicitly. When a
handoff is supplied to the receiving runner, it creates
`counterpart_handoff_review.json`, compares exact case identity and shared
assumption IDs and descriptions, and stops on unresolved divergence or a source
that is not ready. The receiving product must expose any semantic divergence;
it may not silently overwrite the other lens.
