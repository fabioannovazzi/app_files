---
name: concordato-plan-review
description: Use when a user wants Claude to organize and review an Italian concordato preventivo case across procedure, proposal, plan, attestation, creditors and treatment, liquidation alternative, sources and uses, liquidity, feasibility evidence, and accounting consistency. Numerical tie-out is an optional appendix.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Use a local script only
when it is callable and every declared dependency it needs is already available;
never install packages at runtime. MCP tools, browser or computer control, and
local review servers are optional enhancements, never completion gates. When an
optional capability is unavailable, continue with Markdown and file-based review
and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

## Output Location Rule

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

## Client boundary in Cowork

Cowork does not package Studio Archive, so it cannot select or register its
local clients, import controlled snapshots, prepare or start customer-folder
runs, or finalize their artifact manifests. Use a product CLI only when a
compatible local Vera installation supplied a digest-valid, running
`vera.client_workflow_context.v2` for this exact workflow and its complete
customer-folder ledger paths are available. Otherwise work from the exact
connected files, preserve a reviewable file-based handoff, and state that the
sealed customer-folder run remains pending. Never invent an ID, receipt,
lifecycle state, or completed artifact declaration.

# Revisione del Concordato Preventivo

Use this skill for the Italian legal and professional object **concordato
preventivo**. Do not interpret “concordato” as an arbitrary workflow name or as
synonym for a numerical tie-out.

The review covers the procedure, proposal, plan, professional attestation,
document perimeter, creditor population and treatment, liquidation
alternative, sources and uses, liquidity, milestones, assumptions,
consistency, and open issues.

This is not a general report builder, a legal-opinion engine, or a plan
attestation. Claude proposes the semantic analysis; a qualified professional
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

Use Claude and professional judgment for:

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

## Cowork-native Run UX

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

Use native Claude artifacts:

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
   `run_review.md` in the output folder from the persisted review
   artifacts. Never edit plugin source or generated ZIPs during a case run.

Ask for explicit approval only when a step is external, destructive,
approval-sensitive, or depends on an unresolved material choice. Ordinary
local inspection, deterministic calculation, and artifact generation within
the agreed output folder do not require ceremonial approval.

The user should not have to operate helper CLIs. Claude runs them, reads the
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
professional. Do not label Claude's unconfirmed draft as reviewed.

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

### 8. Cowork review handoff

The normal Cowork completion point is delivery
of the reviewable draft, artifact card, and source/review files in the connected
folder. When `concordatoPlanReviewWidgets` and a compatible local Vera customer-
run context are callable, prefer the reference-bound review route: read
`review_reference` from `final_artifacts.json`, validate and render with only
that reference and the customer-run context, then request no more than 25
purpose-selected review items at a time through
`read_concordato_plan_review_items`. The complete review payload stays in
component-only metadata; paths, hashes, sizes, and technical references are
removed from selected model items and source filenames are replaced by stable
aliases. Exact source files may still be opened for a specific evidence
question; do not reopen the entire case by default.

If the optional interface or compatible context is unavailable, continue with
the file-based handoff. Begin with the delivered semantic review and open only
the exact review or source files needed for the unresolved professional
question. The 25-item tool limit does not apply to that connected-folder
fallback, so do not describe it as tool-bounded. Report the package as
`ready_for_professional_review` where that status exists, otherwise as
`pending_review`.

The optional interface may persist or apply reviewer actions. Its absence never
blocks delivery. Never claim `applied` or `final_ready` unless corresponding
persisted artifacts prove it. A file or chat review without those artifacts
remains pending professional review.

This is transport minimization, not anonymization or pseudonymization. Debtor,
creditor, claim, priority, class, vote, treatment, amount, and evidence details
remain when the professional question requires them.

Review actions cannot waive a failed deterministic check. Keep failed checks,
missing evidence, unresolved decisions, and applicable blockers visible in the
artifact card and final response.

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
