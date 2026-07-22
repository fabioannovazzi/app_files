---
name: registro-imprese-sari
description: Use when Vera must understand and prepare an Italian Registro Imprese, REA, Comunicazione Unica, or DIRE position-opening practice from current official SARI/CCIAA guidance, including cases involving INPS, INAIL, SUAP, or IVASS/RUI; produces a source-backed draft for professional review and never logs in, signs, or files.
---

# Registro Imprese e SARI

Prepare a reviewable practice plan from explicit case facts and current official
sources. Keep SARI guidance, DIRE compilation, Registro Imprese/REA effects, and
other recipient positions separate. The output is a professional-review draft,
not a filing instruction or portal automation.

## Hard boundaries

- Never request, receive, store, replay, or export credentials, SPID/CIE/CNS
  material, signatures, tokens, cookies, one-time codes, or delegations.
- Never log in to DIRE, Telemaco, Registro Imprese, INPS, INAIL, SUAP, or IVASS.
- Never click, fill, sign, pay, book assistance, send a SARI question, or submit
  a practice. Draft the manual action and stop before it.
- Never treat the words "open the position" as a legal classification. Resolve
  separately RI, REA, Agenzia Entrate, INPS, INAIL, SUAP, IVASS/RUI, and any
  other recipient cued by the facts.
- Never infer legal form, ATECO, recipient, DIRE model/panel/field, deadline, or
  SARI-card applicability with deterministic keyword rules.
- Private case JSON and local professional-review artifacts may contain the
  client and case facts that are useful for the work. Never place credentials,
  cookies, tokens, signatures, or session material in them.
- Before an actual public SARI search, reduce the outgoing query to generic
  topical terms and run the direct-identifier guard. Do not put client
  identifiers into public SARI/search URLs or generated filenames.
- Every OCR-derived fact remains partial until a human visually confirms the
  source image.
- No status may mean ready to file. `ready_to_file` must remain false.

Reserve explicit approval for an external, destructive, approval-sensitive, or
material step. A confirmation to inspect or draft never authorizes a different
step such as downloading models, using the conditional connector, contacting a
service, changing a professional artifact, or filing.

Read `references/official-sources.md` before any SARI or current-source work.
Read `references/workflow-reference.md` before authoring the case intake or
practice plan.

## Codex-Native Run UX

1. Start with a visible checklist for dependency checks, Run Intake, local
   evidence, official-source selection, material decisions, validation,
   packaging, and professional review.
2. Show a Run Intake table with the stable case reference, private input
   and output folders, competent Camera, reference/effective dates, Codex-context
   and external-acquisition posture, and assumptions.
3. Show a compact Decision Table for every unresolved chamber, legal form,
   activity/classification, recipient position, DIRE step, source
   applicability, date, OCR limitation, or evidence conflict.
4. Before long or write-heavy work, show an execution checkpoint with the
   command intent, bounded inputs, private output directory, and expected
   artifacts. Ask for approval only at the explicit boundary described above.
5. End with an Artifact Card listing outputs, source count, validation status,
   blockers, OCR visual checks, review status, and the next professional action.

Default output policy: create the ordinary private review package without
unnecessary copies of source evidence. JSON, Markdown, audit, and review files
are not choices to propose when the tooling can produce them. Ask only about
material choices that change facts, legal scope, source applicability,
destination, or write scope. Generate alternatives from
the case facts; do not offer uncued legal classifications.

Ask only those unresolved choices in chat, and wait only when an answer would
materially change the case scope or authorized action.
Generate the Decision Table from the actual inputs. Do not propose named
classifications, authorities, recipients, or filing paths unless the facts cue them.

When useful, create `codex_run_review.md` beside the package to record the
checklist, Run Intake table, Decision Table, commands, limitations, and Artifact
Card. Never edit plugin source or generated ZIPs during a customer case run.

## 1. Dependencies and run location

Run from the plugin root:

```bash
python scripts/check_dependencies.py
```

If local screenshot OCR is needed, also check the optional requirements:

```bash
python scripts/check_dependencies.py --requirements requirements-ocr.txt
```

Do not install packages at runtime. Report missing requirements and let the user
decide how to update the environment.

Never write run outputs inside this Git workspace. Use an existing owner-only
customer/run directory outside the repository, or let the initializer create a
new one:

```bash
python scripts/initialize_case.py \
  --output-dir /absolute/private/run-dir \
  --run-id CASE-YYYYMMDD-001 \
  --reference-date YYYY-MM-DD \
  --client-reference CLIENT-OPAQUE-001
```

Do not overwrite or resume draft files for a different `run_id`.

## 2. Confirm the material intake

Before research, show a short decision table and confirm facts that materially
change the practice:

- stable client reference and any identity or contact facts useful to the
  professional task;
- competent chamber/tenant and territorial basis;
- subject and legal form;
- activity in neutral factual language;
- operation requested and effective date;
- current RI/REA and other known position states;
- which recipient positions are being investigated, not assumed applicable;
- the professional question.

Real case material may enter the Codex model context when it is useful for this
private professional review. Do not ask for a per-case processing declaration;
Vera cannot use that declaration to establish compliance.

Complete `case_intake_draft.json`. An unresolved chamber, form, activity, scope,
or date is a blocker, not a reason to guess.

## 3. Inventory local evidence

When the user provides exported documents or DIRE/SARI screenshots, inventory
them locally:

```bash
python scripts/inventory_case.py /absolute/input-folder \
  --output-dir /absolute/private/run-dir \
  --run-id CASE-YYYYMMDD-001 \
  --no-ocr
```

For image OCR, omit `--no-ocr`. Use existing local models by default. If the
user explicitly chooses the optional first model-download route, add:

```bash
--allow-ocr-model-download
```

The run records whether that route was selected and whether network access
actually occurred; it does not manufacture an approval ID. The shared
PaddleOCR adapter runs locally and never transfers case-image bytes.
Visually compare every OCR passage used in a proposal with its source image.

## 4. Consult current official sources

### Default: browser-assisted public SARI lookup

Use the current SARI public directory or the institutional link published by
the competent Camera. Operate in read-only public pages only:

1. choose the chamber explicitly and check the page title;
2. search with a generic topical query, never a name, tax code, VAT number,
   phone, email, PEC, address, or case narrative;
3. present candidates and let a human select the relevant content ID;
4. capture the metadata needed for provenance;
5. do not export session cookies or use login/contact/assistance forms.

Register a browser-selected source without fetching it from a script:

```bash
python scripts/register_official_source.py \
  --output-dir /absolute/private/run-dir \
  --run-id CASE-YYYYMMDD-001 \
  --source-id SARI-TENANT-CARD-ID \
  --source-type official_sari_selected_result \
  --title "Official card title" \
  --official-url "https://supportospecialisticori.infocamere.it/sariWeb/tenant?apriContenuto=ID" \
  --publisher "InfoCamere / selected Camera di commercio" \
  --territorial-applicability "Selected Camera / territory" \
  --authorization-basis browser_assisted_metadata \
  --authorization-reference PUBLIC-READ-ONLY-SELECTION \
  --selected-by human_reviewer
```

For an official page or source copy supplied by the user, select the matching
source type and `user_provided_copy`. A local `--snapshot` is allowed only for a
user-provided copy or recorded written reuse authorization.

Research current official Registro Imprese, DIRE, chamber, INPS, INAIL, SUAP,
and IVASS sources only when the facts make them relevant. Record each selected
source in `official_sources.json`; do not cite search-result pages as the
substantive authority.

### Conditional direct SARI JSON connector

The JSON routes used by SARI's frontend are undocumented and the legal notice
reserves reuse rights. Do not use `scripts/sari_connector.py` unless evidence of
written permission from the relevant rights holder has been checked separately.
User or studio approval alone is not that permission.

If written permission exists, record its stable reference. Invoking the command
is the explicit network-route choice; do not create a second network approval
identifier. Run a metadata search first, select one result manually, then fetch
at most that one card:

```bash
python scripts/sari_connector.py search \
  --output-dir /absolute/private/run-dir \
  --run-id CASE-YYYYMMDD-001 \
  --tenant exact-current-tenant \
  --expected-chamber "Official chamber title" \
  --query "generic topical terms" \
  --limit 10 \
  --written-use-authorization-id RIGHTS-HOLDER-AUTHORIZATION
```

```bash
python scripts/sari_connector.py detail \
  --output-dir /absolute/private/run-dir \
  --run-id CASE-YYYYMMDD-001 \
  --tenant exact-current-tenant \
  --expected-chamber "Official chamber title" \
  --card-id HUMAN-SELECTED-ID \
  --written-use-authorization-id RIGHTS-HOLDER-AUTHORIZATION
```

The direct connector keeps anonymous cookies in memory only, makes exactly two
requests per operation, caps results/bytes, rejects every redirect, and never
calls login, support, upload, or submission routes.

## 5. Author the plan with Codex

Codex reads the confirmed case facts and selected source artifacts, then writes
`practice_plan_draft.json` to `schemas/practice_plan.schema.json`. Scripts do
not write the semantic plan.

For every classification proposal, recipient-position row, DIRE step, required
document, application field, risk, and missing-information item:

- use a stable `id`;
- state the proposal and its applicability condition in `detail`;
- cite one or more `source_ids` (`CASE-INTAKE` is allowed for user-confirmed
  facts);
- list the exact `case_fact_ids` it depends on;
- set `review_status` to `proposed`, `blocked`, `confirmed`, or
  `not_applicable`;
- for `confirmed`, include a human professional confirmation object.

Do not turn broad SARI search matches into a classification. For cases involving
insurance subagents or legacy third/fourth producer groups, distinguish the
source's territorial/date scope, the RUI section/mandate evidence, the RI/REA
effect, and any INPS position. Leave disputed meaning as a named question.

Always draft a concise `sari_question_draft` for private professional review.
Record only case, source, or OCR limitations that actually apply. Before any
later manual transmission, the professional decides which facts the actual
question needs.

## 6. Validate and package

Run the mechanical validation:

```bash
python scripts/validate_practice_case.py \
  --case-intake /absolute/private/run-dir/case_intake_draft.json \
  --practice-plan /absolute/private/run-dir/practice_plan_draft.json \
  --official-sources /absolute/private/run-dir/official_sources.json \
  --output-dir /absolute/private/run-dir
```

Add `--local-inventory .../local_evidence_inventory.json` when local evidence
was inventoried. Resolve schema errors before packaging. It is valid to package
a structurally sound case with explicit blockers; the status remains draft.

```bash
python scripts/package_practice.py \
  --output-dir /absolute/private/run-dir
```

Confirm that `final_artifacts.json` binds the exact validated inputs and source
manifest, shows `ready_to_file: false`, and lists no portal/signature/submission
activity.

The package also writes `review_handoff.md` as the visible handoff card. It must
name the validate, render, save, and apply sequence and repeat that the handoff
does not authorize a portal action.

## 7. Professional review

Call the MCP review tools in this order:

1. `validate_registro_imprese_sari_review`
2. `render_registro_imprese_sari_review`
3. `save_registro_imprese_sari_decisions`
4. `apply_registro_imprese_sari_decisions`

Saved choices go to `ui_decisions.json`; applied choices go to
`applied_decisions.json` and update `final_artifacts.json`. Reject, edit,
unclear, document-request, skipped, and undecided items remain blockers. An edit
records a revision requirement and never silently rewrites the professional
artifact. Even all accepts do not authorize or perform filing.

End with an Artifact Card listing the private run folder, source count,
validation status, blockers, OCR visual checks, review status, and the explicit
statement that no portal action occurred.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
