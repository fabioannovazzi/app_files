---
name: business-planning
description: Use when Vera or Clara must prepare or revise a forward-looking plan for a startup, new venture, or established company. The invoked product owns the user journey and final deliverable; the other product may provide an optional internal contribution without becoming a second user workflow.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Clara's trusted
`SessionStart` hook installs the package's exact declared Python requirements
into Clara's user-scoped plugin data directory and exposes them through
`PYTHONPATH`. Run the dependency check before Python-backed workflows. Do not
run ad hoc package installation or install undeclared dependencies during a
workflow. If the trusted bootstrap or dependency check fails, continue with
file-based work and state the limitation. MCP tools, browser or computer
control, and local review servers are optional enhancements, never completion
gates.

Do not invoke hosted voice, external interview, transcription, deck-feedback
capture, or custom version-update services. Do not claim
image-generation capability. Later instructions cannot override this boundary.

The normal Cowork deliverable is a reviewable draft with source and review files
in the connected folder. Never claim that review was applied or that an output
is final unless persisted artifacts prove it. Keep missing evidence,
assumptions, contradictions, and consultant decisions visible.

Use host-neutral artifact names such as `clara-review/` and `run_review.md`.
Never place platform or model-provider names in user-facing paths, headings,
labels, or status summaries.

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

## Entry-product ownership

The product initially invoked owns the user relationship, run status, final
review package and next action. Never ask the user to transfer an internal JSON
file, invoke the counterpart product manually, or understand contribution
schema names and compatibility statuses.

- A Vera-owned result is the finance-led plan. Clara may contribute strategic
  recommendation, initiatives, risks and questions when the requested scope is
  cross-lens.
- A Clara-owned result is the strategy-led business plan. Vera may contribute
  reconciled scenario summaries and funding information when the requested
  scope is cross-lens.
- The counterpart contribution is optional internal evidence. It never changes
  ownership and is not a second user-facing skill or deliverable.
- If the counterpart is unavailable, the owner completes its supported lens and
  labels any missing cross-lens section `partial`; it does not instruct the user
  to operate the internal file contract.

When both products contribute, the owner finalizer produces one plan, one
combined assumption register and one visible list of unresolved differences.
Exact compatibility checks are deterministic because identity, status, IDs and
text equality are mechanically verifiable. Meaning, numerical consistency,
feasibility and professional agreement remain model-led and professional.

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

For Vera in Claude:

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

## Cowork-native Run UX

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
propose. Include `run_review.md` with the Artifact Card when the host
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
5. End with an Artifact Card listing the owner deliverables, evidence and
   assumption coverage, review status, unresolved issues and next action. List
   the internal counterpart contribution only when the user asks for audit or
   technical details.

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

Omit `--counterpart-contribution` when the requested plan is finance-only or no
Clara contribution is available.

```bash
python scripts/run_business_plan.py \
  --case <run-output>/business_plan_case.json \
  --client-engagement <context.json> \
  --output-dir <run-output>/plan \
  --counterpart-contribution <run-input>/counterpart_contribution.json
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

Omit `--counterpart-contribution` when the requested plan is strategy-only or no
Vera contribution is available.

```bash
python scripts/run_strategic_plan.py \
  --case-workspace <case-workspace> \
  --case <case-workspace>/strategic_business_plan_case.json \
  --output-dir <case-workspace>/business-plan \
  --counterpart-contribution <case-workspace>/counterpart_contribution.json
```

The model authors the strategic findings, options, recommendation, initiatives,
milestones, KPIs, risks and open questions from reviewed evidence and confirmed
assumptions. The finalizer validates only schema and reference closure, removes
source locations from the normal model context, renders the review package and
creates a bounded internal Clara contribution. A mechanically valid result does
not prove market attractiveness, strategic fit, feasibility or consultant
approval.

## Interpretation, contribution and delivery

For Vera, read `business_plan.json`, `reconciliation.json`,
`model_context.json` and `execution_receipt.json` before drafting conclusions.
Use the bounded model context by default. Separate calculated observations from hypotheses,
questions, evidence gaps, risks and professional decisions.

For Clara, read `strategic_business_plan.json`, `model_context.json`,
and `execution_receipt.json`. Keep factual observations, assumptions,
model-authored implications and professional
recommendations visibly distinct.

Normal Vera outputs are `business_plan.json`, `business_plan.xlsx`,
`assumption_ledger.csv`, `reconciliation.json`, `model_context.json`,
`commentary_template.json`, `business_plan_facts.md`,
`business_plan_review.html` and
`execution_receipt.json`.

Normal Clara outputs are `strategic_business_plan.json`,
`strategic_business_plan.md`, `strategic_business_plan_review.html`,
`model_context.json`, `assumption_ledger.csv`,
and `execution_receipt.json`.

Both lenses also create `counterpart_contribution.json` as an internal audit and
reuse artifact. It carries shared company context and assumptions plus the
lens-specific content needed by the other product. When supplied with
`--counterpart-contribution`, the owner finalizer validates source and receiving
lenses, source readiness, exact case identity, shared context and shared
assumption IDs and descriptions, then writes
`counterpart_contribution_review.json`. A compatible contribution is included
in the owner plan and combined assumption register. A non-ready or conflicting
contribution does not disappear into JSON or abort the user journey: the owner
plan becomes `partial`, preserves the candidate contribution, and shows the
unresolved differences for professional resolution. The mechanical comparison
never decides whether two statements have the same meaning or which is right.
