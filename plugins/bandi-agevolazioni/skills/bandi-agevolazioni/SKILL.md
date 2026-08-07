---
name: bandi-agevolazioni
description: Use when Vera must prepare or review an Italian grant, subsidy, tax-credit, or subsidized-finance application from the official call, annexes, amendments, FAQs, forms, and client evidence; produces a traceable professional-review dossier and never authenticates, signs, or files.
---

# Bandi e agevolazioni

Prepare one source-bound application dossier inside a running Studio Archive
engagement. Treat every eligibility, exclusion, eligible-cost, document, form,
and narrative conclusion as a proposal until the responsible professional
reviews it.

## Output location

Never write run outputs inside this Git workspace or a published folder. Use
only the exact private Studio Archive run output described below.

## Hard boundaries

- Never invent eligibility, exclusion, eligible-cost, deadline, document, or
  form requirements.
- Never use deterministic keywords to select the governing framework or decide
  the meaning, applicability, or authority of a source.
- Never request, store, replay, or export credentials, SPID/CIE/CNS material,
  cookies, tokens, one-time codes, delegations, or signatures.
- Never log in, fill a live portal, accept a declaration, sign, pay, save a
  portal draft, or submit an application. Produce field-by-field guidance and
  stop before every portal action.
- Never use `ready` as a synonym for eligible or accepted. Keep documentary
  readiness separate from the assessment outcome. `ready_to_file` is always
  false.
- Treat an official FAQ as clarifying evidence whose effect requires review;
  never let it silently override a formal act.
- Keep OCR-derived facts at `verify` until the source image is visually checked.

Reserve explicit approval for an external, destructive, approval-sensitive, or
material step. Ordinary local evidence inspection and deterministic validation
inside the already selected run do not require a separate confirmation.

## Codex-Native Run UX

1. Show a checklist covering dependencies, Run Intake, source selection,
   workbench drafting, professional review, validation, and packaging.
2. Show a Run Intake table with the opaque client reference, call identifier,
   reference date, bound input and output paths, source-set revision, and
   external-research posture.
3. Use a Decision Table for unresolved source authority, applicability,
   requirement meaning, eligibility, exclusions, costs, missing evidence,
   conflicting facts, form fields, narrative claims, and portal guidance.
   Generate it from the actual inputs; do not offer named classifications,
   authorities, or legal conclusions unless the facts cue them.
4. Ask only about material choices that change the case, governing source,
   professional conclusion, destination, or authorized write scope.
   Ask only those unresolved choices in chat and wait only when an answer would
   materially change the scope or authorized action.
5. Before a long or write-heavy stage, show an execution checkpoint with the
   bounded inputs, private output path, intended command, and expected files.
6. End with an Artifact Card listing source count, disposition, validation,
   stale or missing reviews, blockers, outputs, and the next authorized-person
   action.

Default output policy: produce the ordinary private JSON, audit, and Markdown
review package when the tooling can do so. These are not choices to propose.
When useful, save the visible run summary as `codex_run_review.md` beside the
package. Never edit plugin source or generated ZIPs during a customer case run.

## Client engagement gate

Select one Studio Archive client and engagement, import the official sources
and client evidence as immutable receipts, then prepare and start workflow
`bandi-agevolazioni`. Pass the returned `client_engagement_path` to every
mutating command. Write only to the exact run output directory.

After the outputs are reviewed, finalize every file with a stable artifact ID,
purpose, audience, and media type; then complete the run. Record `failed` or
cancel an abandoned run instead of treating partial files as a result.

## Workflow

Read `references/product-thesis.md`, `references/workflow-method.md`, and
`references/implementation-status.md` completely before interpreting sources,
requesting a model contribution, or editing the workbench. Use
`references/acceptance-matrix.md` when reviewing or releasing the workflow.

1. Run `python scripts/check_dependencies.py` from the component root. The
   declared `jsonschema` dependency is required for exhaustive runtime contract
   validation; do not install it at runtime.
2. Initialize the bounded drafts:

```bash
python scripts/initialize_case.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  --reference-date YYYY-MM-DD \
  --client-reference CLIENT-OPAQUE-001
```

3. Register each exact selected input without copying or fetching it:

```bash
python scripts/register_source.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  --source <bound-input-file> \
  --source-id SOURCE-001 \
  --source-type call \
  --title "Official call title" \
  --issuer "Issuing authority" \
  --authority-role primary \
  --selected-by <reviewer>
```

   After professional source selection, record amendments, supersession,
   clarification, implementation, and incorporation links mechanically:

```bash
python scripts/link_sources.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  --source-id AMENDMENT-001 \
  --kind amends \
  --target-source-id CALL-001
```

4. Read the selected sources and client evidence. Request one bounded semantic
   contribution at a time. Create a bounded task packet without mutating the
   case. The intake applicant object and local paths are not copied by default,
   but professionally relevant facts and excerpts may still identify the
   applicant; there is no automatic anonymization:

```bash
python scripts/intelligence_workflow.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  packet
```

   Record the exact response and exact provider/model/template identity as a
   non-authoritative `MODEL_SUGGESTED` run:

```bash
python scripts/intelligence_workflow.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  record \
  --model-output <strict-output.json> \
  --provider <provider> \
  --model <exact-model> \
  --prompt-template-version bandi-intelligence-v1 \
  --recorded-by <operator> \
  --idempotency-key <stable-request-id>
```

   Codex/model reasoning may propose atomic requirements, facts, assessments,
   document checklist items, expenses, form fields, narratives, consistency
   checks, issues, and an adversarial authority-review simulation. It cannot
   update the workbench until a professional explicitly accepts that exact run:

```bash
python scripts/intelligence_workflow.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  decide \
  --intelligence-run-id INTEL-000001 \
  --decision accepted \
  --reviewer-id <reviewer> \
  --reviewer-role commercialista \
  --confirmed-by-user
```

   `rejected` and `returned` are also explicit terminal decisions. Accepted
   contributions enter `application_workbench.json` only as `proposed`; they
   never overwrite confirmed or blocked work. Any change to intake, sources, or
   workbench makes an undecided run stale. Deterministic scripts validate shape,
   identity, references, exact arithmetic, review hashes, status consistency,
   and prohibited portal controls; they do not interpret the call.
5. Record explicit professional decisions mechanically:

```bash
python scripts/record_review.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  --scope source_baseline \
  --decision accepted \
  --reviewer-id <reviewer> \
  --reviewer-role commercialista \
  --confirmed-by-user
```

   Review scopes are `source_baseline`, `requirements`, `assessments`, and
   `dossier`. A changed bound artifact invalidates the prior review hash.
   Use `--confirmed-by-user` only after the user explicitly confirms that exact
   scope and decision. The local reviewer ID and role are asserted metadata,
   not authenticated identity; the dossier states this boundary and remains
   for authorized professional review.
6. Validate and package the private review dossier:

```bash
python scripts/validate_application.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path>

python scripts/package_dossier.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path>
```

7. Show the professional the exact readiness/outcome matrix, missing evidence,
   unresolved interpretations, red flags, draft form fields, and narrative
   claims. Do not hide negative or uncertain findings in polished prose.
8. Provide portal assistance only as a manual field map. The authorized person
   owns authentication, declarations, signature, saving, and transmission.

## Status contract

Readiness is `ready`, `missing`, `verify`, or `not_applicable`. Assessment
outcome is separately `satisfied`, `not_satisfied`, `uncertain`,
`not_applicable`, or `not_assessed`. `not_applicable` requires a reviewed
rationale. A conclusive negative assessment may therefore be documentary
`ready` while making the dossier unsuitable for filing.

## Deterministic boundary

Use deterministic code only for mechanically verifiable work: exhaustive JSON
Schema and ID validation, exact hashes, path containment, source/reference
closure, the versioned `exact_decimal_compare` and `exact_date_compare` rule
families after their inputs and outcome mapping are professionally confirmed,
status invariants, review hash binding, and packaging. Keep source
authority, requirement meaning, eligibility, exclusions, cost classification,
narrative judgment, conflict significance, and simulated-authority review
model-led and professionally reviewed.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
