---
name: business-planning
description: Prepare one business plan for a startup, new venture or established company: assess customers, market, operations, economics, cash needs, options and next actions. Vera and Clara use the same workflow and report.
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
uses the exact Studio Archive run output for workflow ID `business-planning`.
Clara uses the selected advisory case workspace and its `business-plan` folder.
Synthetic developer evaluations may write to a temporary test directory.

# Business Planning

Use one workflow and report in both Vera and Clara. There is no product-specific
angle, division of analytical responsibilities, or contribution from another
product. The user's business question determines the work.

Assess the proposition and customer need, credible demand, pricing and channels,
operations and capacity, full costs and margins, cash timing and financing,
credible alternatives, and the recommendation with practical next actions.
Use one source register, accepted assumptions and financial calculation register.
Changing entry point must not change scope, required sections, numbers or report.
Company stage changes the evidence and questions; missing history is not zero.
Do not infer stage using keyword rules.

## Intake and review

Read [the case contract](../../references/case-contract.md). Both entry points
require `mparanza.business_planning_case.v3`. Legacy v1/v2 case and counterpart files
are inspection inputs only; they cannot finalize reports. Migrate by inspecting
actual files and obtaining real assumption/audience decisions, never by inventing
review metadata. Do not assume an earlier report used this registered pipeline.

Establish entity, mandate, audience, currency, monthly horizon, source selection,
opening position, scenarios and material unknowns from the actual evidence. Ask
only material unresolved questions. Keep the user informed about intake, evidence
review, financial calculation, strategic interpretation, validation and delivery.

For every selected file record its relative path, actual SHA-256, version, role,
review status, intended audience and explicit confidentiality restrictions. Roles
distinguish client documents, professional reviews, existing financial models,
external evidence and model-created hypotheses. Hashes establish file identity,
not truth. Existing spreadsheets must be reconciled as evidence.

The model and professional must extract and align material source figures into
`observations` with period, scenario, metric, units and source IDs. Include
contradictory values, not only values supporting the preferred conclusion.
Deterministic grouping exposes differences in these reviewed alignments; it
cannot discover omitted claims or interpret raw documents. Review source coverage
and completeness explicitly before marking the case reviewed.

Keep facts, assumptions, hypotheses, calculated results, conflicts and professional
decisions distinct. Confirm every material assumption, including financing timing,
debt service, working capital and the variable/fixed cost split, with a named
professional and timestamp. Explicit confirmed zero differs from missing `null`.
Each input needs evidence/assumption references effective for its period.

An accepted conflict resolution names an observation and a reviewed professional
decision. Never silently select a conflicting number. Unresolved material conflicts
produce partial results; disagreement with accepted figures blocks readiness.

## Financial and strategic work

The shared financial engine calculates monthly scenarios and linked statements, margins,
EBITDA/EBIT/net income, cash flow, working capital, minimum cash, pre-financing
funding need and residual gap, runway, revenue break-even, margin of safety,
debt service/DSCR and sources-and-uses reconciliation. Read their formula and
limitation fields. Do not treat mechanical reconciliation as viability.

The model interprets reviewed market evidence, positioning, options, initiatives,
commercial implications and risks. All financial amounts in narrative use typed
`{{claim}}` placeholders with exact calculation IDs and expected values. Narrative
must never independently calculate or rewrite a canonical amount. Correct the accepted
inputs and rerun the shared engine if figures need changing.

Do not invent scores, benchmarks or KPI thresholds. They require a reviewed rubric,
source, or explicitly labelled and confirmed professional hypothesis. A reference
to a number does not support the meaning of a score: professional review must check
both numerical and semantic claims, including numbers written as words and implied
recommendations. The compiler checks exact bindings, not prose meaning.

A precise capital recommendation requires the complete accepted cash-flow model,
all material reviews/conflicts resolved, and the full-horizon `funding_requirement`
calculation ID. It is not permission to recommend a financing instrument, valuation,
buffer or round size unsupported by that model. Report missing inputs and questions
instead. Financing timing and unpaid/missing debt cannot be hidden in prose.

## Registered execution

The commands below are storage adapters to the same execution path. They do not
select financial or strategic modes. The model handles this binding internally.

Run `python scripts/check_dependencies.py` first. `requirements.txt` is the core
published dependency declaration; do not install arbitrary packages at runtime.

Vera imports the shared case and **every selected source** as exact same-engagement
Studio Archive receipts, then prepares and starts workflow `business-planning`.
Use source paths relative to the run's `input_dir` (`imports` / receipt ID / stored filename),
and pass the returned context unchanged. Inputs are checked against exact receipts.

```bash
python scripts/run_business_plan.py --case <receipted-case.json> \
  --client-engagement <context.json> --source-root <run-input-dir> \
  --output-dir <run-output>/plan
```

Clara keeps its case JSON at the advisory case workspace root and all selected
sources below that workspace:

```bash
python scripts/run_strategic_plan.py --case <case-workspace>/business_plan_case.json \
  --case-workspace <case-workspace> --source-root <case-workspace> \
  --output-dir <case-workspace>/business-plan
```

Use a fresh output folder. Exit code 2 means partial/blocked or rejected input;
inspect the report/validation file if written. Do not overwrite a previous report.

## Controlled delivery

Only the shared compiler produces the deliverable. Do not draft an independent
final HTML, Markdown, spreadsheet or PDF with copied figures. Edit the reviewed
structured case and rerun. Normal outputs are `business_plan.json`,
`report_structure.json`, `business_plan_review.html`, `calculations.json`,
`calculations.csv`, `input_manifest.json`, `reconciliation.json`,
`validation.json` and `execution_receipt.json`.

The compiler replays arithmetic, source hashes, reference closure, narrative
bindings and chart data before rendering. It includes complete provenance,
comparisons, professional decisions, unresolved matters, limitations and audience
restrictions. Audience release requires an explicit reviewed decision bound to the
source's hash; internal-only material cannot be exported to a different audience
merely because a new audience name was entered.

HTML comes first. Visually inspect it, including chart axes, negative results,
zero lines, legends, source comparisons and provenance tables. PDF is optional via
`--pdf`, solely from that validated structure. Check `requirements-pdf.txt` before
using the optional renderer; no PDF is permitted for a partial or blocked result.

Charts use canonical calculation IDs only: reported versus adjusted EBITDA when
available, EBITDA scenarios, monthly cash before/after financing and cumulative
funding gaps. Reported values are labelled source projections, not accepted EBITDA.
Do not add decorative progress bars, unsupported scorecards or channel unit
economics when channel-specific inputs are absent.

For model interpretation provide only the reviewed, audience-permitted excerpts,
assumptions and calculation records needed for the assignment. Full local source
files and paths are not automatically model context. The full report structure is
an audience-controlled local audit artifact; do not send it wholesale to a model
or external service without the relevant data-use authorization.

Deliver one business plan report with its status, supported conclusions, open matters and
next professional action. Finalize Vera's physical output artifacts with stable
IDs, purpose, audience and media type and complete the Studio Archive run. Record
failure/cancellation honestly. Clara records results in the selected case workspace.

## Cowork-native Run UX

Show a compact checklist for intake, evidence/assumption review, calculation,
interpretation, validation, visual inspection and delivery. Use a Run Intake table
for the actual entity, mandate, audience, horizon, sources and output folder, and
a Decision Table only for unresolved material choices. Confirmed facts and
accepted assumptions are not choices to propose.

Default output policy: use only the selected run/case folder. End with an Artifact
Card giving the report path, status, unresolved matters and next professional
action. Include `run_review.md` when the host needs a review note. Build
generated ZIPs from canonical source; never edit their extracted copies.

Ask only those unresolved choices in chat, grounded in the actual inputs. Do not
introduce hypothetical alternatives unless the facts cue them. Before execution,
show an execution checkpoint with the selected inputs, command intent, output
folder and expected artifacts.
