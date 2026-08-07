---
name: bandi-agevolazioni
description: Use when Vera must prepare or review an Italian grant, subsidy, tax-credit, or subsidized-finance application from the official call, annexes, amendments, FAQs, forms, and client evidence; produces a traceable professional-review dossier and never authenticates, signs, or files.
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

## Cowork-native Run UX

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
When useful, save the visible run summary as `run_review.md` beside the
package. Never edit plugin source or generated ZIPs during a customer case run.

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

## Workflow

Read `references/workflow-method.md` completely before interpreting sources or
editing the workbench.

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

4. Read the selected sources and client evidence. Claude/model reasoning drafts
   atomic requirements, facts, assessments, document checklist items, expenses,
   form fields, narratives, consistency checks, issues, and an adversarial
   authority-review simulation in `application_workbench.json`.
   Deterministic scripts validate shape, identity, references, exact arithmetic,
   review hashes, status consistency, and prohibited portal controls; they do
   not interpret the call.
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
