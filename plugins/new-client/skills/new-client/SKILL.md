---
name: new-client
description: Use when a commercialista or studio wants Vera to prepare an owner-only, reviewable new-client relationship dossier covering identity, representatives and beneficial owners, engagement scope, mandate/privacy/AI applicability, assisted AML assessment, missing evidence, document planning, and ongoing monitoring; it verifies a final-ready client-file-preparation binding or records explicit standalone evidence, but never renders client documents, signs, sends, screens externally, or activates the relationship.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or another published folder. Use a dedicated owner-only
directory outside the repository, preferably a sibling
`output/new-client-<run-id>` folder next to the user's private source
folder. Pass that exact path to every `--output-dir` option.

# New Client

Run one New Client journey. Phase one prepares incoming documents through the
subordinate `client-file-preparation` engine; later phases prepare the
professional relationship for review. Generated files never mean the
professional relationship is complete or active. The strongest workflow state
is `ready_for_professional_export`. Signature, client communication, external
screening, filing, and relationship activation are never performed by this
component.

Read `../../references/workflow-reference.md` and
`../../references/source-policy.md` completely before a substantive run. Here,
the component root is the directory two levels above this skill file:
`plugins/new-client`.

## Product boundary

Use sibling `client-file-preparation` for recursive inventory, OCR, extraction, and
document classification. When a reviewed Client File Preparation run exists, bind to its
run ID and final-artifact byte hash and verify its final-ready state instead of
repeating extraction. If there is no prior run, use the explicit
`standalone_evidence` mode with a recorded reason. Never label standalone facts
as reviewed Client File Preparation evidence.

New Client owns:

- party, representative, executor, and beneficial-owner facts;
- engagement purpose, nature, services, duration, and studio-entered terms;
- applicability proposals for mandate, privacy notice, informativa AI, art. 28,
  and AML documents;
- structured privacy purpose, role, legal-basis, and retention decisions, with
  a separate marketing-consent record whose marketing-only limits never decide
  whether the professional relationship may be exported for review;
- assisted AML inputs, exact arithmetic, blockers, and professional outcome;
- complete PEP, sanctions, and country-screening coverage for every relevant
  subject, while outcomes and resolutions remain professional findings;
- missing evidence, verified template-reference planning, and monitoring;
- persistent professional review and a source/hash-bound handoff.

Do not add an ANC price list, relationship-sentiment coefficient, or another
fee recommendation engine. Fee and payment terms are captured only when the
studio explicitly supplies them. Do not copy or redistribute third-party legal
templates unless reuse rights and version are known.

## Core judgment boundary

Deterministic local scripts own only mechanically verifiable work: schema and
enum checks, exact identifiers, hashes, path and permission safety, Decimal
arithmetic, the confirmed AML formula and bands, allowed review intervals,
date clamping, subject-by-subject coverage, template-reference integrity,
artifact QA, export gates, and decision persistence.

Codex may use model-led reasoning to propose the meaning of services, risk
scores, source relevance, Table 1 or Section B treatment, privacy roles,
art. 28 applicability, AI-transparency scope, missing evidence, and draft
language. Every material proposal must cite source IDs and case-fact IDs and
remain visibly proposed.

The professional owns identity verification, client declarations, screening
outcomes, legal applicability, every AML score and trigger, controller/processor
roles, purposes and legal bases, retention, clauses, final documents, cadence,
client acceptance, and all external actions. The model is never the approving
actor and professional review never impersonates a client's declaration or
signature.

## Codex-Native Run UX

1. Start with a visible checklist for evidence binding, dependencies, facts,
   material decisions, AML inputs, applicability, document plan, monitoring,
   packaging, and professional review.
2. Show a Run Intake table with the case reference, verified Client
   File Preparation binding or explicit standalone-evidence mode, output directory,
   jurisdiction, reference date, language, any selected route beyond Codex, and
   assumptions. Do not create a per-case model-processing approval field.
3. Show a compact Decision Table for unresolved identity, service, per-subject
   screening, Table 1, Section B, AML trigger, privacy-role, marketing-record,
   document-applicability, source, and template-reference choices.
4. Before long or write-heavy work, show an execution checkpoint with command
   intent, inputs, private output directory, and expected artifacts. Explicit
   approval is reserved for external, destructive, approval-sensitive, or
   material steps.
5. End with an Artifact Card listing each output, current state, blockers,
   source/version posture, and next professional action.

Default output policy: create the ordinary owner-only review package whenever
the inputs and dependencies permit. JSON, Markdown, audit, review, and handoff
files are not choices to propose. Ask only about material choices that change
facts, professional scope, source applicability, client-relationship privacy
role or processing basis, destination, or write scope.

Ask only those unresolved choices in chat when the answer materially changes
the case or authorized action. Generate the Decision Table from the actual inputs.
Do not offer legal classifications, document types, regulatory
conclusions, or screening outcomes unless the facts cue them or the user must
supply a custom value. Never ask for performative continuation text.

When useful, create `codex_run_review.md` beside the package to record the
checklist, Run Intake table, Decision Table, commands, limitations, and Artifact
Card. Never edit plugin source or generated ZIPs during a customer case run.

## Private review and external boundaries

Ordinary Codex analysis and the owner-only MCP review may include names, codice
fiscale, partita IVA, addresses, emails, identity-document numbers, descriptions,
source excerpts, and rationales when they are professionally useful. Do not add a
separate per-run model-approval or minimization form merely to permit that work,
and do not describe data removed after Codex read it as anonymized.

Keep credentials, authentication codes, cookies, private or tokenized session
URLs, and screening-provider tokens out of every artifact and review surface.
Keep raw local paths behind the owner-only persistence boundary. Authorization
for a real external action remains a separate gate at the point of that action.

## Workflow

### 1. Dependencies and starter contract

From the component root run:

```bash
python scripts/check_dependencies.py
python scripts/initialize_case.py \
  --case-dir /private/path/new-client-run \
  --client-reference CLIENT-001 \
  --assessment-date YYYY-MM-DD
```

Do not install missing packages at runtime. Report the declared missing
dependency and let the user decide how to update the environment. Treat
`requirements.txt` as the controlled requirements declaration and use
`check_dependencies.py --requirements <repo-relative-file>` when a different
declared requirements file must be checked.

The starter file is deliberately incomplete. Codex fills the draft from
evidence and explicit instructions while preserving acquisition method,
confidence, evidence references, and confirmation state. Code fiscale and
partita IVA remain separate facts. Blank values never overwrite verified
facts. Multiple representatives and beneficial owners remain separate stable
records.

### 2. Bind evidence and current sources

Prefer a reviewed `client-file-preparation` run. Verify the supplied run ID, exact
`final_artifacts.json` byte hash, plugin/workflow identity, final-ready states,
every listed output's byte hash and size, and the canonical upstream package
hash before relying on it. Do not duplicate its OCR or
classification. A malformed or hash-mismatched binding is a hard failure; a
valid but non-final binding blocks relationship export. When no prior run
exists, select `standalone_evidence`, state why, and use stable evidence IDs and
existing local paths. The package records hashes without copying source
documents.

For the normal handoff, create the phase-two starter deterministically:

```bash
python scripts/promote_client_file_preparation.py \
  --final-artifacts /private/path/file-preparation-run/final_artifacts.json \
  --case-dir /private/path/new-client-run \
  --client-reference CLIENT-001
```

The command inherits the sealed phase-one language. Do not pass a different
`--language`; an explicit mismatch is rejected.

Promotion may carry forward only accepted or edited, semantically unambiguous
fields as `reported`, never as verified. Ambiguous identifiers, amounts, years,
classification guesses, and unreviewed extractions remain bound upstream but
are not promoted as relationship facts.

The shipped professional-setup country pack is `IT`. Languages `it`, `en`,
`fr`, `de`, and `es` localize review and generated studio drafts for that pack; they
do not imply that Swiss or UK professional-setup packs exist.

Treat `references/source-registry.json` as a maintained seed, not as proof that
law is current or applicable. For a real case, model-led research should verify
the relevant current primary and professional sources and record retrieval,
version, temporal scope, and reuse status. Public mirrors are distribution
paths, not automatically primary authority. A template with unknown reuse
rights can be referenced for provenance but must not be bundled or reproduced.

### 3. Propose applicability and AML inputs

Codex may prepare proposed records but may not confirm them. Each applicability
record must identify a deliverable, proposed value, rationale, source IDs, case
fact IDs, and review state. Marketing consent is separate from the core privacy
notice and must not block the professional relationship when marketing is not
requested.

For each client, representative, and beneficial owner, record one PEP, one
sanctions, and one country-screening result. Duplicate or missing subject/type
pairs are invalid. A confirmed result needs evidence; a non-clear result remains
blocked until a professional records a supported resolution. The component
does not call screening providers or decide that a hit is a false positive.

For AML, preserve exactly four client factors and six service factors when
Section B is included. Section B exclusion is permitted only when a professional
explicitly confirms the corresponding official case; never infer it from service
keywords. Record Table 1 applicability as a separate `yes`, `no`, or `unknown`
assessment with a non-empty basis. Only a professional may confirm `yes` or `no`,
and the confirmation must identify the professional role and timestamp; an
unknown or merely proposed Table 1 assessment blocks the treatment outcome. The
exact mechanical calculation is:

- `RS = (totale A + totale B) / 10`, or `RS = totale A / 4` only after a
  confirmed Section B exclusion;
- `RE = RI × 30% + RS × 70%`;
- bands: `[1, 1.6)`, `[1.6, 2.6)`, `[2.6, 3.6)`, `[3.6, 4]`.

After Table 1 is professionally resolved, map the bands mechanically: a
non-significant Table 1 case uses the applicable conduct rule; a non-significant
non-Table-1 case and a little-significant case use simplified verification; a
fairly significant case uses ordinary verification; and a very significant case
uses enhanced verification. Do not infer Table 1 applicability from a service
label or description.

A confirmed mandatory trigger forces enhanced verification. An unknown trigger
blocks the final outcome. Do not infer the PEP public-administration exception;
it needs explicit professional confirmation. Mandatory enhanced verification
can never be declassified. Correct upstream facts and scores instead of using
an arbitrary downward override; a stronger professional escalation is allowed
only with rationale.

Monitoring cadence applies only to ongoing relationships. Simplified and
ordinary map mechanically to 36 and 24 months after professional confirmation.
Enhanced requires the professional to choose 6 or 12 months; never default it.
An unresolved Table 1 assessment blocks scheduling. A Table 1 conduct rule does
not receive one of these automatic cadences; follow the confirmed service-specific
rule and professional review instead.

### 4. Package drafts

Run:

```bash
python scripts/package_new_client.py \
  --input /private/path/new-client-run/new_client_input.json \
  --output-dir /private/path/new-client-run
```

Record a studio template only as a reference. Verify its exact local content
hash, approval, reuse scope, jurisdiction, language, review date, and source
basis before marking that reference current. Pending, withdrawn, prohibited,
unknown, stale, mismatched, or hash-drifted references block the affected
document plan. Never copy, merge, render, or substitute placeholders in a
template. New Client emits an internal document plan, not client-ready
legal wording.

Changing a material input, source, template, or upstream binding invalidates
the current hash binding. Validation must fail until the package is regenerated
and reviewed at a new revision. Preserve review history and use a new run
directory for regenerated domain artifacts.

### 5. Professional review

The normal session contains `run_intake.json`, `review_payload.json`,
`ui_decisions.json`, `review_handoff.md`, and `final_artifacts.json`.
The workbench groups party posture, engagement, subject screening, AML factor
sections, and mandatory triggers. Mechanically verified bindings, source rows,
and duplicate summaries remain in local artifacts rather than creating dozens
of mandatory accept decisions. Missing information is represented by one
grouped request decision when present.

When MCP is available:

1. call `validate_new_client_review`;
2. call `render_new_client_review`;
3. persist actions with `save_new_client_decisions`;
4. apply them with `apply_new_client_decisions`, producing
   `applied_decisions.json` and updating only the review portion of the export
   gate in `final_artifacts.json`.

At Apply, the service re-derives the package's inclusive temporal horizon from
the authoritative-source `review_by`, every recorded evidence and identity
document expiry, and every template `valid_until` and `review_due_on`. It uses
the system UTC date and fails without writing when that date is later than the
earliest bound deadline. Refresh the affected material and generate a new run;
an earlier professional acceptance does not extend the deadline.

Pass a stable studio reviewer reference in the `reviewer` field when applying
the completed review. It may be the reviewer's real name or professional account
reference. A complete set of acceptances without this reviewer reference must
remain blocked from export.

`accept` confirms only the displayed proposal. It cannot erase upstream,
domain, template, privacy, screening, or artifact blockers. `reject`, `mark_unclear`,
`request_more_documents`, and `skip` do not approve it and remain visible in
the final state. `edit` records an explicit proposed revision; a material edit
invalidates dependent acceptances and requires regeneration. Never silently
mutate source facts or legal/AML conclusions in place.

If the host MCP tools are unavailable, start the packaged local workbench from
the resolved module root:

```bash
python scripts/review_server.py <new-client-output-directory>
```

It renders the same widget on loopback and persists the same save/apply tool
calls. In repository source, the equivalent developer command from this
component root is
`python ../../scripts/serve_review_workbench.py <output-directory> --plugin-dir .`.
Only if neither service can run, review the Markdown artifacts and leave
`ui_decisions.json` pending; a conversational approval is not an applied
professional review.

## Expected artifacts

- `new_client_input.json` (private source intake, retained beside the package);
- `case_facts_validated.json` and `source_registry.json`;
- `applicability_plan_validated.json` and `document_plan.json`;
- `aml_assessment_draft.json` and `aml_calculation_audit.json`;
- `missing_evidence.json` and `client_missing_information_draft.md`;
- `monitoring_plan.json` and `studio_new_client_memo.md`;
- `run_intake.json`, `review_payload.json`, `ui_decisions.json`,
  `applied_decisions.json` after application, `review_handoff.md`, and
  `final_artifacts.json`.

The review contract binds each persisted domain artifact and the verified
upstream intake mode to its current hash. The final manifest exposes separate
domain, review, and artifact blockers and always keeps
`professional_review_required: true`,
`signature_performed: false`, `client_communication_sent: false`, and
`relationship_activation_performed: false`.

## Failure states

- Missing or unreadable evidence: `blocked_input` or `partial_evidence`.
- Unresolved jurisdiction, client-relationship privacy role or processing basis,
  service meaning, AML input, trigger, source, or template applicability:
  `blocked_decision`.
- Invalid schema, identifier, range, path, permission, or hash binding:
  `schema_error` or a hard validation failure.
- Stale source, template, upstream run, or changed material dependency: a hard
  binding failure until the package is verified, regenerated, and reviewed.
- Review with rejected, unclear, skipped, or document-request actions:
  `partial_review_applied` or `blocked`.
- All current proposals professionally accepted, with every relationship-scope
  domain and artifact gate clear: at most `ready_for_professional_export` for
  an internal professional dossier; never `compliant`, `complete`, `signed`,
  `active`, or a client-ready document state.

Never replace missing evidence with model inference. Retention, encryption,
access control, deletion, signature, and final communication remain the
studio's responsibility unless a separately approved system of record governs
them.

## Plugin Improvement Feedback

At the end of every completed or blocked run, briefly identify concrete
improvements that would have made this workflow better, based on the actual
case: a missing parser, weak evidence locator, source-version gap, ambiguous
review gate, template friction, repeated manual step, or missing integration.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
