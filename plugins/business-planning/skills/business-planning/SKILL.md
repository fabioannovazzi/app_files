---
name: business-planning
description: Use when Vera or Clara must prepare or revise a forward-looking business plan for a startup, new venture, or established company. Vera owns the accounting-financial lens; Clara owns the strategic-commercial lens. Use one reviewed assumption and handoff contract without treating the two professional outputs as interchangeable.
---

## Output location

Never write run outputs inside this Git workspace or a published folder. Vera
uses only the exact Studio Archive run output for workflow ID
`business-planning`. Clara uses the selected advisory case workspace and keeps
the plan with the case materials and deliverables.

# Business Planning

Use this one workflow for startups, new ventures, and established companies.
Record `company_stage` in reviewed plain language. The model and professional
interpret the stage; deterministic code checks only that the description is
present. Do not create separate startup and established-company modes or route
from a keyword classifier.

The invoking product fixes the professional lens:

- Vera uses `accounting_financial` and owns the opening position, historical
  base when available, assumptions, linked profit and loss, cash flow, balance
  sheet, working capital, debt and equity, funding requirement and
  reconciliation.
- Clara uses `strategic_commercial` and owns market and customer evidence,
  business model, positioning, strategic findings and options, recommendation,
  initiatives, milestones, KPIs, risks and decision implications.

Do not ask the user to choose a lens after they have invoked Vera or Clara.
Neither product may silently rewrite the other product's reviewed assumptions,
figures, recommendation, or professional conclusions.

For Vera, route a request limited to sales volumes, prices, revenue, discounts,
COGS, or FX to `sales-plan`; historical analysis to `financial-analysis`;
recurring reporting to `management-control-pack`; and insolvency-plan review to
`concordato-plan-review`. For Clara, route a generic assignment-framing request
to `advisory-brief-planner`; use this workflow when the requested professional
output is the business plan itself.

## Judgment boundary

Model-led and professional judgment own the planning objective, company-stage
description, evidence meaning, source selection, assumption selection,
scenario or option design, market interpretation, risks, narrative and
approval. Do not infer numerical values from qualitative statements. Read back
every material assumption and obtain confirmation before finalization.

Deterministic code owns reviewed case shape, reference closure, hashes and
receipt integrity. In Vera's lens it also owns canonical Decimal parsing,
period order, exact statement arithmetic, working-capital, debt and equity
roll-forwards, reconciliation and funding-gap calculation. In Clara's lens it
checks only the declared evidence, assumption, option, initiative and risk
references and renders the reviewed model-authored strategic case. It never
selects a strategy, scores a market or infers whether the company is a startup.

## Workspace boundary

For Vera in Codex:

1. Select one Studio Archive client and engagement.
2. Import the exact reviewed evidence as immutable `source` receipts. A startup
   may have no historical accounts; an established company normally has an
   historical base. Neither absence nor availability decides the route.
3. Prepare and start workflow ID `business-planning` from the exact selected
   inputs and any finalized same-engagement upstream artifacts used.
4. Pass the returned `client_engagement_path` unchanged to the helper and write
   only below its `output_dir`.
5. Finalize every physical output with a stable artifact ID, relative path,
   purpose, audience and media type. Review the declaration and complete the
   run. Record failure or cancellation instead of treating partial files as a
   result.

For Clara, use the current advisory case workspace, follow the Clara case
director when one exists, and keep selected sources, the strategic case and
outputs together. In Cowork, use only explicitly connected files and folders
and state that no portable Studio Archive run was created.

## Codex-Native Run UX

Before helper scripts, identify the material choices that can change the plan:
entity, company stage, objective, audience, horizon, evidence, assumptions and
output folder. Vera also resolves currency, periods, opening position,
scenarios and tolerance. Clara also resolves the decision, strategic options,
initiatives, milestones and KPIs. Ask only about choices whose answer would
materially change the result.

Ask only those unresolved choices in chat. Ground the choice in the actual
inputs. Do not introduce hypothetical alternatives unless the facts cue them.

Default output policy: write only to the reviewed run or case output folder.
Input facts and confirmed assumptions are evidence to preserve, not choices to
propose. Include `codex_run_review.md` with the Artifact Card when the host
supports a review note; generated ZIPs are release artifacts and must be built
from canonical source rather than edited directly.

1. Start with a visible checklist for intake, dependency check, evidence and
   assumption review, lens-specific preparation, validation, visual inspection
   and delivery.
2. Show a Run Intake table with entity, company stage, product lens, objective,
   audience, horizon, evidence, assumptions, output folder and unresolved
   choices. Add the lens-specific inputs above.
3. Show a compact Decision Table only for material unresolved choices grounded
   in the actual inputs. Keep evidence, assumptions, hypotheses, unknowns and
   professional decisions separate.
4. Before a long or write-heavy step, show an execution checkpoint with command
   intent, inputs, output folder and expected artifacts.
5. End with an Artifact Card listing output paths, evidence and assumption
   coverage, review status, unresolved issues, counterpart handoff and next
   action.

Explicit approval is reserved for external, destructive, approval-sensitive,
or material steps. Local inspection, deterministic validation, calculation,
rendering and authorized run-output writes do not add an approval ceremony.

## Intake and assumption review

Keep these classes separate:

- source-supported historical or opening facts;
- external evidence;
- management assumptions;
- model-proposed hypotheses;
- calculated results or model-authored strategic findings;
- missing information and professional judgments.

For every material assumption, show its ID, description, evidence or hypothesis
basis, horizon or effective periods, rationale and status. The professional
must confirm the complete assumption read-back before the case receives
`review.status=reviewed`; Vera also requires confirmation of the opening
position. A model-proposed hypothesis may enter the case only after it is
clearly labelled and explicitly confirmed.

Read [the case contract](../../references/case-contract.md) before writing or
reviewing a case JSON. `requirements.txt` is the complete core dependency
declaration. Run `python scripts/check_dependencies.py` before either finalizer.
Do not install arbitrary packages at runtime.

## Vera financial calculation

From the module root:

```bash
python scripts/run_business_plan.py \
  --case <run-output>/business_plan_case.json \
  --client-engagement <context.json> \
  --output-dir <run-output>/plan
```

The reviewed case uses canonical Decimal strings. Each scenario supplies the
same ordered periods and references confirmed assumptions effective for those
periods. The runner calculates linked P&L, cash flow, balance sheet, break-even
period, minimum cash and funding requirement. It does not forecast demand,
select assumptions, search the market or create a balancing plug.

Stop on an invalid case, missing confirmation, unknown evidence or assumption
reference, impossible fixed-asset or debt roll-forward, changed run context or
failed statement reconciliation. Negative cash remains visible as a funding
requirement.

## Clara strategic finalization

From the module root:

```bash
python scripts/run_strategic_plan.py \
  --case <case-workspace>/strategic_business_plan_case.json \
  --output-dir <case-workspace>/business-plan
```

The model authors the strategic findings, options, recommendation, initiatives,
milestones, KPIs, risks and open questions from reviewed evidence and confirmed
assumptions. The finalizer validates only schema and reference closure, removes
source locations from the normal model context, renders the review package and
creates the Clara-to-Vera handoff. A mechanically valid result does not prove
market attractiveness, strategic fit, feasibility or consultant approval.

## Interpretation, handoff and delivery

For Vera, read `business_plan.json`, `reconciliation.json`,
`model_context.json`, `business_planning_handoff.json` and
`execution_receipt.json` before drafting conclusions. Use the bounded model
context by default. Separate calculated observations from hypotheses,
questions, evidence gaps, risks and professional decisions.

For Clara, read `strategic_business_plan.json`, `model_context.json`,
`business_planning_handoff.json` and `execution_receipt.json`. Keep factual
observations, assumptions, model-authored implications and professional
recommendations visibly distinct.

Normal Vera outputs are `business_plan.json`, `business_plan.xlsx`,
`assumption_ledger.csv`, `reconciliation.json`, `model_context.json`,
`commentary_template.json`, `business_plan_facts.md`,
`business_plan_review.html`, `business_planning_handoff.json` and
`execution_receipt.json`.

Normal Clara outputs are `strategic_business_plan.json`,
`strategic_business_plan.md`, `strategic_business_plan_review.html`,
`model_context.json`, `assumption_ledger.csv`,
`business_planning_handoff.json` and `execution_receipt.json`.

Both lenses produce `business_planning_handoff.json` with shared company
context and assumptions plus the lens-specific results needed by the
counterpart. The receiving product reviews it as evidence. It must surface
inconsistent assumptions or conclusions and return them for professional
resolution; deterministic code does not merge or choose between them.

## Plugin Improvement Feedback

After substantive use, read and follow the `Plugin Improvement Feedback`
section in the invoking product's router. Keep client data and source details
out of any technical improvement note.

Keep the improvement note local to chat or run artifacts.
