---
name: concordato-plan-review
description: Use when a user wants Codex to organize and review an Italian concordato preventivo case across procedure, proposal, plan, attestation, creditors and treatment, liquidation alternative, sources and uses, liquidity, feasibility evidence, and accounting consistency. Numerical tie-out is an optional appendix.
---

## Output Location Rule

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

## Client engagement gate

Select one Studio Archive client and engagement, import the case sources, then
call `prepare_studio_client_workflow` with workflow ID
`concordato-plan-review`. Pass the returned `client_engagement_path` as
`--client-engagement` to the review runner, reviewer-confirmation helpers,
assurance replay, and every review writer. Include the same path in MCP review
calls. Cross-engagement inputs and arbitrary outputs are rejected.

Start the prepared run before execution. After the last output write, call
`finalize_studio_client_workflow` and declare every physical file with a stable
artifact ID, relative path, concrete purpose, audience, and media type. Review
the closed declaration, then call `complete_studio_client_workflow`; record
`failed` or explicitly cancel an abandoned run instead of treating a partial
directory as a result.

# Revisione del Concordato Preventivo

Use this skill for the Italian legal and professional object **concordato
preventivo**. Do not interpret “concordato” as an arbitrary workflow name or as
synonym for a numerical tie-out.

The review covers the procedure, proposal, plan, professional attestation,
document perimeter, creditor population and treatment, liquidation
alternative, sources and uses, liquidity, milestones, assumptions,
consistency, and open issues.

This is not a general report builder, a legal-opinion engine, or a plan
attestation. Codex proposes the semantic analysis; a qualified professional
confirms or corrects it. The scripts validate and calculate only mechanically
verifiable facts.

## Core Boundary

Use deterministic code for:

- source capture, hashes, receipts, and closed output paths;
- PDF/workbook extraction and precise evidence locators;
- schema and evidence-reference validation;
- exact decimal arithmetic;
- creditor/class totals and recovery percentages;
- plan-versus-liquidation differences;
- sources-and-uses totals and funding gap;
- period cash bridges and minimum liquidity;
- exact amount matching as an optional appendix;
- reproducible JSON, CSV, XLSX, DOCX, and review-session artifacts.

Use Codex and professional judgment for:

- governing law and its application;
- document meaning and authoritative version;
- creditor perimeter, priority, class, vote, and treatment;
- whether evidence supports an assertion;
- feasibility, materiality, sustainability, and going concern;
- legal, tax, social-security, and accounting conclusions;
- issue severity, follow-up, and professional conclusion.

Never infer a semantic role from a file name. Never convert a passed arithmetic
check into a legal or feasibility conclusion. If evidence is incomplete, keep
`missing`, `partial`, `unclear`, `gap`, or an open issue visible.

## Codex-Native Run UX

Before write-heavy execution, identify the material choices that would change
the review and establish only those not recoverable from the sources:

- input folder and intended procedure/case;
- review cut-off or reference date;
- working language and document language;
- accountable professional/reviewer for confirmation;
- any user-requested scope exclusion;
- numerical tolerance only if a numerical appendix is needed.

Ask only those unresolved choices in chat and wait for the answer. Generate
choices from the actual inputs; do not offer named frameworks, regulators,
document types, issue categories, or output packages unless the facts cue them
or the user must supply a missing custom value.

Do not ask the user to choose output files. Produce the complete normal package
when dependencies and evidence permit.

Default output policy: the semantic case model, creditor and class schedules,
sources and uses, liquidity, review workbook, Markdown, Word summary, audit
records, and numerical appendix are not choices to propose when they are
natural outputs of the case. Generate them whenever the evidence and declared
dependencies permit.

Use native Codex artifacts:

1. Show a short checklist: intake, dependency check, inspection, semantic
   modeling, reviewer confirmation, deterministic schedules, review, delivery.
2. Show a Run Intake table with source folder, output folder, cut-off,
   languages, and explicit assumptions.
3. After inspection, show a Decision Table only for material semantic
   uncertainties or missing evidence.
4. Before sealing the model, show an execution checkpoint with the procedure
   identity, plan type, authoritative documents, creditor perimeter status, key
   assumptions, open gaps, source folder, and output folder.
5. Update the checklist during execution.
6. End with an Artifact Card separating primary semantic outputs, numerical
   appendix, unresolved issues, and next action. When useful, create
   `codex_run_review.md` in the output folder from the persisted review
   artifacts. Never edit plugin source or generated ZIPs during a case run.

Ask for explicit approval only when a step is external, destructive,
approval-sensitive, or depends on an unresolved material choice. Ordinary
local inspection, deterministic calculation, and artifact generation within
the agreed output folder do not require ceremonial approval.

The user should not have to operate helper CLIs. Codex runs them, reads the
results, prepares the model, and explains the boundary.

## Inputs

Required:

- one folder containing the material supplied for the case.

The plugin does not require fixed file names or one fixed checklist. Depending
on the case, useful material may include a proposal, plan, attestations,
creditor schedules, liquidation analysis, cash-flow model, disposals,
contributions, accounting records, tax/social-security schedules, court
documents, or professional reports. Treat this as evidence discovered from the
actual case, not a filename taxonomy.

Default currency is EUR unless a source or user states otherwise. The semantic
model requires one consistent currency for its mechanical schedules.

## Workflow

### 1. Check dependencies

From the plugin directory:

```bash
python scripts/check_dependencies.py
```

Install only declared `requirements.txt` dependencies when permitted. Stop
before unreliable output if a required capability is unavailable.

### 2. Inspect in abstention

```bash
python scripts/run_concordato_review.py <managed-input-folder> \
  --client-engagement <client_engagement_path> \
  --output-dir <client-run-output>/inspection \
  --reference-date 2026-03-31 \
  --language it \
  --document-language it \
  --tolerance 1
```

This captures sources and writes an unreviewed semantic template. It does not
make filename-based roles operative and it does not grant reporting authority.

Read at least:

- `inventory.json`;
- `source_pages.json`;
- `suggested_concordato_case_model.json`;
- extraction diagnostics;
- `raw_amount_candidates.csv` only if a numerical appendix may be useful.

### 3. Build the semantic case model

Copy `suggested_concordato_case_model.json` to a working JSON file and fill it
from inspected evidence. Preserve its exact schema:

- `legal_framework`;
- `procedure`;
- `document_perimeter`;
- `creditor_population`;
- `sources_and_uses`;
- `liquidity`;
- `milestones`;
- `review_questions`;
- `assumptions`;
- `issues`.

For every semantic entry:

- use captured `source_artifact_ref` values;
- add precise locators when the schema provides them;
- explain `judgment_basis`;
- distinguish observed evidence from professional inference;
- keep missing evidence and contradictions explicit.

The required review areas are procedure identity, proposal/plan consistency,
document perimeter, creditor perimeter/treatment, voting and homologation,
liquidation alternative, feasibility/liquidity, attestation, accounting
consistency, and tax/social-security matters.

### 4. Obtain reviewer confirmation

Present the completed model and unresolved issues to the accountable
professional. Do not label Codex's unconfirmed draft as reviewed.

After confirmation, seal the model:

```bash
python scripts/review_case_model.py <client-run-output>/inspection \
  <client-run-output>/reviewer-confirmed-case-model.json \
  --client-engagement <client_engagement_path> \
  --output <client-run-output>/reviewed-semantic-recipe.json \
  --reviewer-ref qualified-reviewer \
  --reviewed-on 2026-07-26 \
  --reference-date 2026-03-31
```

The helper normalizes the model and binds it to current source receipts. If the
source perimeter or bytes change, repeat inspection and confirmation.

### 5. Add a numerical appendix only when useful

If the review requires a plan-to-accounting amount tie-out, prepare the
separate source/token decision file and seal it with:

```bash
python scripts/review_source_roles.py <client-run-output>/inspection \
  <client-run-output>/numeric-decisions.json \
  --client-engagement <client_engagement_path> \
  --output <client-run-output>/reviewed-numeric-recipe.json
```

This path requires an explicit disposition for every extracted numeric token
and authorizes only the fixed amount-difference calculation. Do not run it
merely because the capability once centered on a tie-out.

### 6. Run the reviewed case

Semantic review without the numerical appendix:

```bash
python scripts/run_concordato_review.py <managed-input-folder> \
  --client-engagement <client_engagement_path> \
  --output-dir <client-run-output>/reviewed-output \
  --reference-date 2026-03-31 \
  --language it \
  --document-language it \
  --tolerance 1 \
  --semantic-recipe <client-run-output>/reviewed-semantic-recipe.json
```

When the numerical appendix is also authorized, add:

```text
--recipe /path/to/reviewed-numeric-recipe.json
```

### 7. Review primary outputs

Read:

- `concordato_case_model.json`;
- `concordato_semantic_checks.json`;
- `creditor_treatment.csv`;
- `creditor_class_summary.csv`;
- `sources_and_uses.csv`;
- `liquidity_schedule.csv`;
- `concordato_review_workpaper.xlsx`;
- `concordato_semantic_review.md`;
- `concordato_preventivo_review_summary.docx`;
- `assurance_envelope.json`;
- `workflow_output_closure.json`;
- `final_artifacts.json`.

Keep `review_payload.json` as the complete local review/UI authority. Do not
reopen or resend it merely to render, save, or apply review state after the
semantic model has been confirmed.

Treat `concordato_tie_out_workpaper.xlsx` and
`concordato_review_summary.docx` as numerical appendices.

### 8. Use the review surface

When `concordatoPlanReviewWidgets` is available:

1. read `review_reference` from `final_artifacts.json`;
2. call `validate_concordato_plan_review` with only `client_engagement` and that reference;
3. call `render_concordato_plan_review` with the same two fields;
4. collect decisions in the component;
5. call `save_concordato_plan_decisions` with the same reference and the decisions;
6. call `apply_concordato_plan_decisions` with the same reference after reviewer completion.

The model-visible validate/render result contains only run status, total and
per-type counts, the small review reference, and the name and bound of the
on-demand read tool. The complete `review_payload.json`, run intake, current
decisions, final-artifact index, source labels, paths, hashes, and review rows
are hydrated from the persisted run and delivered to the review component in
tool-result metadata rather than model-visible `content` or
`structuredContent`. The same component-only payload contract applies in
Codex/ChatGPT and, when that optional interface is callable and used,
Cowork/MCP Apps. Cowork's normal connected-folder fallback remains file-based:
begin with the delivered semantic review and open only the exact review or
source files needed for the professional question. The 25-item tool limit does
not apply to that fallback.

If a specific professional question still needs model analysis after semantic
confirmation, call `read_concordato_plan_review_items` by exact item id or item
type. Each call returns at most 25 selected items, removes technical paths,
hashes, sizes, and artifact references, and replaces source filenames with
stable source aliases while preserving the substantive procedure, creditor,
treatment, amount, evidence locator, issue, and reviewer context. Use multiple
bounded calls only when the professional question requires them. Exact source
files remain available for a specific evidence question; do not reopen the
entire case by default.

This is transport minimization, not anonymization of the professional case.
Debtor and creditor identities remain when needed to establish procedure,
claim, priority, class, voting, treatment, or evidence. The workflow does not
automatically anonymize or pseudonymize those substantive identities.

Before any write, the MCP path replays the trusted payload, assurance envelope,
and whole-output closure. If MCP is unavailable, review the same payload in
Markdown/chat and keep decisions pending until recorded.

`ui_decisions.json` records the reviewer's pending or saved decisions.
`applied_decisions.json` records only decisions actually applied to downstream
artifacts. `final_artifacts.json` indexes the resulting output state and must
remain consistent with both. Never describe an edit as applied merely because
it appears in the review widget.

The review queue must lead with procedure, review questions, issues, creditor
class treatment, and mechanical checks. Numerical amount rows follow as
supporting evidence.

### 9. Replay

```bash
python scripts/replay_assurance.py \
  --client-engagement <client_engagement_path> \
  --output-dir <client-run-output>/reviewed-output
```

Use `references/workflow-reference.md` for the normative authority and replay
contract and `references/review-methodology.md` for professional review
sequence.

## Completion Standard

A useful delivery states:

- what was observed in the supplied evidence;
- which semantic judgments were confirmed and by whom;
- procedure and plan type;
- document and creditor perimeter status;
- treatment and liquidation-comparator results;
- sources-and-uses and liquidity observations;
- open questions, evidence gaps, assumptions, and limitations;
- whether the optional numerical appendix ran;
- why publication or professional conclusion remains withheld, if applicable.

Do not claim that synthetic tests prove real-case generality. Field validation
requires a previously unseen real case and an independent qualified review.

## Plugin Improvement Feedback

At the end of a completed or blocked run, mention concrete improvements
revealed by the actual case—such as unsupported source formats, weak locators,
missing semantic fields, difficult creditor schedules, or review friction.
Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
