---
name: comunicazione-professionale
description: Use when a commercialista or professional studio wants Vera to monitor or explain a tax, legal, regulatory, accounting, social-security, corporate, grant, or other professional development; learn an approved studio voice from selected prior communications; decide whether communication is worthwhile; and prepare source-backed client emails, LinkedIn posts, newsletters, website articles, FAQs, client alerts, or branded graphical explainers for professional review and optional publication.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launchers provision and reuse an isolated environment containing only the
module's published requirements. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

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

# Comunicazione professionale

Prepare one source-backed professional communication package. Treat topic
selection, source authority, legal or tax meaning, audience relevance, the
`publish` versus `no_publish` recommendation, voice, claims, and editorial angle
as model-led professional proposals. Preserve the commercialista's approval of
the technical position and every external send or publication.

## Required reading

Before preparing a contribution, read completely:

- `references/product-thesis.md`;
- `references/workflow-method.md`;
- `references/model-contribution-contract.md`;
- `references/professional-circular-pattern.md` when a client circular or
  circular cover email is requested;
- `references/visual-system.md` when a visual output is requested or useful.

## Output location

Never write run outputs inside this Git workspace or a published folder. Use
one explicitly authorized, owner-controlled communications workspace bound to
its exact local path. It is studio-wide and must not be placed in one client's
Studio Archive engagement. The professional owns its retention.

## Hard boundaries

- Never invent a norm, effective date, affected audience, exception, client
  outcome, quotation, professional position, engagement result, or urgency.
- Never use keywords or fixed rules to select the governing framework, source
  authority, topic relevance, meaning, applicability, or editorial angle.
- Prefer current primary and official sources. Treat commentary as context, not
  silent authority for a legal or tax claim.
- Preserve `no_publish` as a successful outcome. A schedule never creates a
  reason to communicate.
- Learn voice only from material the professional selected for that purpose.
  Do not copy distinctive passages, preserve errors, or infer private beliefs.
- Never scan the Studio workspace, archive, mailbox, or connected account for
  prior communications. The professional selects every exact history item;
  a later profile revision may add only newly selected items in a new run.
- Local code strips explicit-format emails, phone numbers, tax identifiers,
  account identifiers and case numbers before any model sees selected history.
  One isolated model session receives only those stripped documents and
  creates complete pseudonymized derivatives. A second fresh model session
  sees only those candidate derivatives and must clear residual contextual
  identification before generation can start. Identity mappings remain local.
  Generation receives the accepted derivatives; claim, editorial, and visual
  review receive separate task-specific packets with no prior communications.
  Contextual identities may still reach the first selected Claude or Cowork
  model pass.
- Keep client identity and case facts out of public research queries. Use a
  client example only when the professional supplied and approved a lawful,
  appropriate public-use version.
- Keep a generic communication distinct from recipient selection and
  personalized advice. Never infer that one communication applies to every
  client.
- Never send an email, upload an asset, or publish a post unless the user has
  explicitly chosen that route and the exact final package is accepted.
- Creative Production is an optional art-direction collaborator, not a legal,
  tax, editorial, copywriting, source, or publishing authority. Its board
  output is never a final deliverable. Do not let it rewrite exact copy,
  numbers, dates, sources, Studio identity, or the approved logo.
- Reserve explicit approval for external, destructive, approval-sensitive, or
  material steps. Do not interrupt ordinary read-only intake, local analysis,
  or deterministic validation with ceremonial confirmation prompts.
- Never request credentials, cookies, session material, one-time codes, or
  passwords. Use only callable connectors or an already authenticated supported
  browser surface, and stop at account ambiguity or security checkpoints.

## Cowork-native Run UX

1. Show a checklist covering dependencies, Run Intake, selected evidence,
   editorial judgment, studio-profile proposal, professional review, rendering,
   validation, and packaging.
2. Show a Run Intake table with the studio, reference date, objective, audience,
   requested channels, selected source and history counts, private output path,
   existing profile version, and external-route posture.
3. Use a Decision Table for unresolved authority, meaning, applicability,
   audience value, repetition, professional position, studio format, claim,
   copy, visual, recipient, account, or publication issues. Use actual inputs
   and populate it from that evidence; do not offer legal conclusions,
   channels, or stylistic preferences unless the facts cue them.
4. Ask only about material choices that change source selection, professional
   meaning, audience, studio profile, output scope, exact destination, or an
   authorized external action. Ask only those unresolved choices in chat and
   wait only when the answer would materially change the package or
   authorization boundary.
5. Before rendering or another write-heavy stage, show an execution checkpoint
   with bound inputs, private output path, intended command, and expected files.
6. End with an Artifact Card listing the recommendation, sources, accepted and
   missing reviews, studio-profile version, drafts, visuals, blockers, and the
   next professional or authorized-person action.

Default output policy: create the ordinary private JSON, Markdown, text, HTML,
PNG, and PDF review package implied by the requested channels. These are not
choices to propose. When useful, save the visible run summary as
`run_review.md` beside the package. Never edit plugin source or generated
ZIPs during a professional communication run.

## Workflow execution

1. From the resolved plugin root, run `python scripts/check_dependencies.py`.
   Do not install missing requirements at runtime.
2. Initialize the private workspace once:

   ```bash
   python scripts/initialize_workspace.py \
     --workspace <private-workspace> \
     --workspace-id <stable-id> \
     --owner <professional-or-studio> \
     --retention-owner <professional-or-studio> \
     --confirmed-by-user
   ```

   Before the first contribution from a new editorial-assessor model, or after
   its template or benchmark changes, qualify that assessor. Use the exact
   bundled `prompts/editorial-assessment-v4.md` and record its SHA-256 in the
   benchmark result. Give the assessor
   only `evals/editorial_quality_cases.json`; never read or expose
   `evals/editorial_quality_expected.json` while producing its judgments.
   Write the model result against
   `schemas/editorial_benchmark_results.schema.json`, then run:

   ```bash
   python scripts/qualify_editorial_assessor.py \
     --workspace <private-workspace> \
     --results <editorial_benchmark_results.json> \
     --recorded-by <operator>
   ```

   The deterministic scorer only compares model judgments with fixed
   product-reviewed high-bar outcomes. A false `ready` on a critical generic or
   redundant case prevents that exact provider/model/template combination from
   assessing live work.

3. Create `communication_intake.json` from actual user choices and selected
   material. Include the objective, audience, channels, selected source files,
   selected prior communications, an optional `studio_format_brief`, an
   optional brand profile, and the four
   external-route records `public_research`, `history_connector`,
   `creative_production`, and `send_or_publish`. Set `creative_production` to
   selected only when the user explicitly chose that route and record its
   visible destination. Prepare a run:

   Direct connector intake is not supported for selected history because the
   connector response would enter the calling model before local stripping.
   The professional must select and export each desired message or document to
   a supported local file first. Set `history_connector.selected` to `false`;
   preparation fails closed if it is selected.

   ```bash
   python scripts/prepare_run.py \
     --workspace <private-workspace> \
     --intake <communication_intake.json>
   ```

   A new Studio may start without prior communications. Vera then proposes the
   complete first format from explicit instructions, supplied brand assets,
   and clearly labelled Vera defaults. No field may use `observed_history`
   unless its cited history was selected and snapshotted in this run.

   If history was selected, `prepare_run.py` extracts complete readable text,
   mechanically replaces explicit-format emails, phone numbers, tax IDs,
   account IDs and case numbers, writes the reversible mapping to the local-only
   `history_identity_map.json`, and creates
   `history_pseudonymization_packet.json` containing only stripped documents.
   The downstream `model_task_packet.json` remains blocked. Open the exact
   bundled `prompts/history-pseudonymization-v1.md` in a fresh host session and
   give it only that packet and its stripped document paths. Write
   `history_pseudonymization.json` against its schema. Preserve each complete
   useful document while pseudonymizing contextual names, organizations,
   addresses, locations, roles and identifying fact combinations. Return the
   semantic identity mapping separately; the recorder merges it into the local-
   only mapping rather than exposing it downstream. Record the result:

   ```bash
   python scripts/record_history_pseudonymization.py \
     --run-dir <run-dir> \
     --pseudonymization <history_pseudonymization.json> \
     --provider <provider> --model <model> \
     --session-id <fresh-history-session-id> \
     --recorded-by <operator>
   ```

   Recording requires every selected item once, a ready model assessment, exact
   input binding, preservation of locally inserted placeholders and the bundled
   prompt digest. It stages one complete candidate derivative per selected
   document and keeps downstream generation blocked. In a second fresh host
   session, open only `history_privacy_assessment_packet.json`, its candidate
   derivative paths, and `prompts/history-privacy-assessment-v1.md`. Do not open
   raw history, stripped intermediates, either identity map, or the first
   session transcript. Write the result against
   `schemas/history_privacy_assessment.schema.json`, then finalize it:

   ```bash
   python scripts/record_history_privacy_assessment.py \
     --run-dir <run-dir> \
     --assessment <history_privacy_assessment.json> \
     --provider <provider> --model <model> \
     --recorded-by <operator>
   ```

   A `revise` verdict does not unlock generation: rerun pseudonymization with
   the required generalizations. A `ready` verdict promotes the derivatives,
   moves both mapping layers into the owner-only identity map, deletes the
   transient stripped inputs and both dedicated model packets, writes a
   digest-bound cleanup receipt, and exposes only derivative paths and hashes
   to generation. Raw selected snapshots and the local mapping remain for the
   Studio's audit and possible re-identification. If safe pseudonymization
   cannot preserve the style-learning purpose, proceed without history.

4. Read the exact current-source inputs and, when history was selected, only
   the recorded pseudonymized derivatives. When public research was selected, research
   with generic topic-level queries and record exact official source snapshots
   or user-readable source files in a new prepared run before confirming
   claims. Do not treat a URL string as captured evidence.
5. Before drafting, write `answer_contract.json` against its schema. Bind the
   purpose, audience, language, jurisdiction, source hierarchy, preservation
   rules, evidence display, full-claim validation scope, correction policy, and
   professional-judgment boundary. Compute `contract_digest` over the exact
   object before that field is added.

   Then open the exact bundled `prompts/generation-v3.md` in a fresh host
   session and use model-led reasoning to write `model_contribution.json`
   according to the contract. A `publish` contribution contains a studio
   profile proposal whenever the run says `profile_revision_required`, source
   assessments, atomic claims, a master brief,
   channel drafts, and a model-led `render` or `omit` visual decision. A
   `no_publish` contribution explains why communication is not useful and
   contains no promotional filler. Every Studio-profile field must have one
   `field_provenance` record with basis `observed_history`, `user_supplied`, or
   `vera_default_proposal`. Never describe an unsupported cross-channel
   convention as observed. Every contribution includes a model-led
   `editorial_value` judgment; a calendar, generic awareness, available word
   count, or generic business advice is never sufficient.

   Every channel draft also carries its exact reviewed `public_source_notes`.
   The note identifies the real authority and instrument, plus the material
   date, number, version, or public URL when available. Packaging may escape
   text for HTML but must not replace these notes with a generic Studio phrase.

   Before claim assurance, create its exact minimized packet:

   ```bash
   python scripts/prepare_model_phase.py \
     --run-dir <run-dir> --phase claim_assurance \
     --contribution <model_contribution.json> \
     --answer-contract <answer_contract.json>
   ```

   Open only that packet's allowed inputs and
   `prompts/claim-assurance-v2.md` in a separate fresh host session and write
   `claim_assurance.json`. Bind it to the exact contribution and answer-contract
   digests; cover every material claim once; and keep source identity, semantic
   support, reasoning, and professional judgment separate. Correct or remove an
   unsupported, contradicted, overbroad, temporally distorted, or unsound claim
   before continuing. This is the communication-specific equivalent of Vera's
   deep-research validation record; do not start a separate client-bound
   validator run for the same studio-wide contribution.

   Then create the editorial packet:

   ```bash
   python scripts/prepare_model_phase.py \
     --run-dir <run-dir> --phase editorial_assessment \
     --contribution <model_contribution.json> \
     --claim-assurance <claim_assurance.json>
   ```

   Open only that packet's contribution and completed assurance with
   `prompts/editorial-assessment-v4.md` in a third fresh host
   session and write `editorial_assessment.json` according to its schema. Bind it to the exact
   canonical contribution and claim-assurance digests. Use a fresh assessor
   session that has not seen the generation transcript and does not reuse the
   generator prompt; record this in `assessment_protocol`. The verdict may be
   `ready`, `revise`, or `no_publish`. Do not record a
   contribution until this second pass is `ready`; regenerate when it is not.
   The assessment is adversarial, not ceremonial: compare the work against a
   strong practitioner-authored publication, identify its weakest element, test
   whether it expresses expertise beyond source summary, and give a separate
   semantic verdict for every channel and proposed slide. Judge public evidence
   readability explicitly: where a public source note is warranted, it must let
   the intended reader identify the actual authority and instrument (and the
   relevant date, number, version, or link when material). Labels such as
   `Fonte`, `fonte ufficiale`, or an internal source ID are not useful evidence
   by themselves. A `weak` or `redundant` slide, or a non-identifiable public
   evidence note when exact evidence is available, requires revision or
   omission.
6. Record the exact history-pseudonymization model when used, generator and editorial-assessor provider/model provenance,
   template versions, template digests, distinct host session IDs, and
   operator. These are operator-attested host records, not
   provider-authenticated API receipts; never describe them otherwise:

   ```bash
   python scripts/record_contribution.py \
     --run-dir <run-dir> \
     --contribution <model_contribution.json> \
     --answer-contract <answer_contract.json> \
     --claim-assurance <claim_assurance.json> \
     --editorial-assessment <editorial_assessment.json> \
     --provider <provider> --model <model> \
     --claim-assessment-provider <provider> \
     --claim-assessment-model <model> \
     --assessment-provider <provider> --assessment-model <model> \
     --template-version professional-communication-v3 \
     --generation-session-id <fresh-generator-session-id> \
     --recorded-by <operator>
   ```

   If and only if the intake selected Creative Production and the reviewed
   contribution contains a `render` visual story, prepare its locked handoff:

   ```bash
   python scripts/prepare_creative_direction_handoff.py \
     --run-dir <run-dir> --directions 4
   ```

   Then read the exact JSON and Markdown handoff completely and invoke
   `creative-production:produce` when that skill and its
   `creative_production_board` tool are callable. Use the board tools directly,
   keep one board for the workflow, and generate four to six materially
   different art-direction references. Send only the locked visual copy and
   minimal Studio visual context in the handoff; do not send source bytes,
   selected history, client facts, recipient data, or internal source IDs.
   Treat the references as non-publishable: they may explore composition,
   hierarchy, spacing, rules, shapes, brand-constrained color balance, and
   non-factual texture, but they may not add information or rasterize final
   copy. Show the directions and let the professional select one.

   After the board returns four to six completed items, write
   `creative_direction_selection_input.json` against its schema with the exact
   board ID, revision, item IDs, image paths, selected item, selection rationale,
   and a translation into Vera's supported renderer tokens. Record it only
   after the professional selects the direction:

   ```bash
   python scripts/record_creative_direction_decision.py \
     --run-dir <run-dir> \
     --decision <creative_direction_selection_input.json> \
     --recorded-by <operator> --confirmed-by-user
   ```

   If the tool is unavailable, generation fails, or the professional chooses
   Vera's internal system, record the corresponding `fallback` outcome with the
   same command. A selected Creative Production route must have one current
   selected decision or fallback before any preview or release render. The
   renderer snapshots every direction reference, binds the selected board item
   and translation digest, applies the supported tokens, and records that
   binding in the visual manifest. It must never silently render the unchanged
   internal style while claiming a Creative Production selection.

   Translate the selected direction back into Vera's supported visual system
   and deterministic renderer. If that translation changes the contribution,
   record the affected scope as `returned`, create a superseding contribution,
   and repeat the independent editorial assessment. Never edit reviewed JSON in
   place. When the Creative Production skill or board is unavailable, say so
   briefly, record the fallback, and continue with Vera's internal visual
   system; the workflow must not fail and no plugin installation is a
   precondition for a valid run.

7. Review the visible `review_handoff.md`, editorial assessment, claims, drafts,
   and visual decision or story.
   When the exact visual is needed to perform that review, first render an
   isolated QA preview:

   ```bash
   python scripts/render_visuals.py --run-dir <run-dir> --qa-preview
   ```

   The QA preview writes `visual_preview_manifest.json` and
   `visuals-preview/`. It is deliberately non-packageable and is not evidence
   of professional approval. Never copy or rename it into the release path.
   Prepare the exact preview-only packet:

   ```bash
   python scripts/prepare_model_phase.py \
     --run-dir <run-dir> --phase visual_assessment --qa-preview
   ```

   Open only its allowed inputs with `prompts/visual-assessment-v2.md` in
   another fresh host session, then open every exact PNG and every PDF page,
   compare them with the channel draft,
   and write a model-led `visual_assessment.json` against
   `schemas/visual_assessment.schema.json`. Record it with:

   ```bash
   python scripts/record_visual_assessment.py \
     --run-dir <run-dir> --assessment <visual_assessment.json> \
     --provider <provider> --model <model> --qa-preview
   ```

   A `revise`/`omit` verdict or any `weak`/`redundant` slide requires a new
   contribution and preview. Do not let a clean layout overrule the semantic
   visual assessment. A selected Creative Production direction also cannot
   overrule it: inspect only Vera's exact deterministic QA preview and release
   render when deciding whether the output is accurate, useful, on-brand, and
   ready.

   Present every current semantic scope in one visible review matrix. After one
   explicit professional confirmation, write `review_bundle.json` against its
   schema and record the matrix atomically. This creates separate digest-bound
   events under one review session, so auditability does not create ceremonial
   prompts:

   ```bash
   python scripts/record_review.py \
     --run-dir <run-dir> --bundle <review_bundle.json> \
     --reviewer <professional> --confirmed-by-user
   ```

   A later isolated decision may still use the single-scope form below.
   Required scopes are generated from the actual package; do not invent an approval:

   ```bash
   python scripts/record_review.py \
     --run-dir <run-dir> --scope <scope> \
     --decision accepted|returned|rejected \
     --reviewer <professional> --confirmed-by-user
   ```

8. A returned or rejected draft may be replaced with
   `record_contribution.py --supersede`; this creates a new immutable version and
   invalidates prior reviews. It also archives the earlier derived render,
   package, and assessment artifacts under `versions/artifacts-vNNN/`, so a
   revised contribution can be rendered and packaged without overwriting
   history. Never edit a reviewed version in place.
9. When the reviewed contribution contains an accepted studio profile proposal,
   promote it so later runs reuse the approved brand colors, persisted logo,
   document geometry, font family, voice, email, website, and social formats.
   On later runs that have no selected history for a profile revision, the
   stored brand and asset hashes are authoritative and conflicting intake
   values are rejected:

   ```bash
   python scripts/promote_studio_profile.py --run-dir <run-dir>
   ```

10. After the required semantic scopes are accepted, render the graphical story
    and any circular PDF:

   ```bash
   python scripts/render_visuals.py --run-dir <run-dir>
   ```

   Rendering deterministically owns exact dimensions, approved profile
   geometry and font selection, colors, wrapping, file hashes, source footers,
   and the preview gallery. It rejects content that cannot fit without
   clipping. It never decides what a norm means or whether a claim is
   supported. Inspect every rendered PNG and PDF, then accept the exact render
   digest separately. Before professional acceptance, repeat the model-led
   inspection against the exact release manifest and record a `ready`
   assessment without `--qa-preview`:

   ```bash
   python scripts/prepare_model_phase.py \
     --run-dir <run-dir> --phase visual_assessment
   python scripts/record_visual_assessment.py \
     --run-dir <run-dir> --assessment <visual_assessment.json> \
     --provider <provider> --model <model>
   ```

   The professional acceptance requires both that assessment and explicit
   confirmation of the visible checklist:

   ```bash
   python scripts/record_review.py \
     --run-dir <run-dir> --scope rendered_output \
     --decision accepted|returned|rejected \
     --reviewer <professional> --confirmed-by-user \
     --quality-checklist-confirmed
   ```

11. Package the accepted drafts, technical basis, complete editorial and visual
    model-assessment records, exact accepted visuals, and a
    `validation_pending` final manifest. Inspect the exact packaged email,
    Markdown, HTML, graphics, PDF, technical basis, and artifact card, then
    accept that package digest. Only after this exact-package review may
    validation write the receipt and change the status to `final_ready` or
    `no_publication_recommended`:

   ```bash
   python scripts/package_communications.py --run-dir <run-dir>
   python scripts/record_review.py \
     --run-dir <run-dir> --scope packaged_output \
     --decision accepted|returned|rejected \
     --reviewer <professional> --confirmed-by-user
   python scripts/validate_run.py --run-dir <run-dir>
   ```

12. Show the Artifact Card, every unresolved issue, and the exact next action.
    If the user selected a send or publish route, verify the exact visible copy,
    recipients or account, and attached assets immediately before the external
    action. Record the resulting external receipt or URL; never mark sent or
    published without visible confirmation. After the connector or supported
    browser reports success, record that exact evidence:

    ```bash
    python scripts/record_external_delivery.py \
      --run-dir <run-dir> --action <action> \
      --destination <exact-destination> \
      --visible-receipt <receipt-or-url> \
      --confirmed-by <operator> --confirmed-by-user
    ```

## Review and completion contract

- `run_intake.json` records selected files, requested channels, local data
  posture, and optional external routes.
- `source_register.json` proves exact immutable input snapshots.
- `history_pseudonymization_record.json`, when history is selected, binds one
  isolated model session to the exact locally stripped inputs and one complete
  pseudonymized derivative per selected item. `history_identity_map.json`
  remains local and is excluded from every model packet.
  `history_privacy_assessment_record.json` binds a second independent,
  derivative-only privacy review. `history_cleanup_receipt.json` proves that
  the stripped model inputs and dedicated history packets were removed after
  acceptance, while raw snapshots and the identity mapping were retained.
  Generation receives derivative paths and hashes; claim, editorial, and
  visual review packets exclude all selected history. This is pseudonymization, not
  anonymization: contextual identities can reach the isolated first pass and
  re-identification remains possible where the local mapping is retained.
- Direct connector retrieval of selected history is blocked because it cannot
  currently guarantee local stripping before model access. The professional
  exports and selects exact local messages or documents instead.
- `editorial_assessor_qualification.json` in the workspace proves that the
  exact editorial provider/model/template passed the current blinded anti-slop
  benchmark without a false-ready critical case.
- `content_workbench.json` preserves the model contribution and provenance.
- `model-phase-packets/` binds the exact minimum allowed inputs for claim,
  editorial, and visual model sessions; their recorders fail if a packet is
  missing, changed, stale, or contains selected-history artifacts.
- The workbench and package preserve `answer_contract` and `claim_assurance`,
  binding the professional objective to full material-claim support, reasoning,
  and judgment review.
- `review_payload.json` and `review_handoff.md` expose the review queue.
- `review_log.json` binds professional decisions to one exact contribution
  digest and binds `rendered_output` decisions to one exact visual-manifest
  digest and `packaged_output` decisions to one exact package digest.
- `visual_manifest.json` proves PNG dimensions, font assets, and byte hashes.
- `creative-direction/handoff-vNNN.json`, when the route was explicitly
  selected, binds only the reviewed visual story and minimal Studio visual
  context to a non-publishable Creative Production request. It is an internal
  direction artifact and is never a packaged communication.
- `creative-direction/decision-vNNN.json` records either the exact board result,
  selected item, user-confirmed translation and snapshotted references, or the
  explicit internal fallback. Its digest is bound into every visual manifest.
- An accepted `studio_profile_proposal` may be promoted to the private
  workspace with an authoritative format digest and a versioned logo asset.
  Later runs snapshot that exact approved profile and reject unreviewed brand
  drift.
- `final_artifacts.json` lists the technical basis, drafts, graphics, caveats,
  blockers, and next actions.
- Every integrity gate recomputes the prepared-input and contribution digests;
  editing the workbench, source register, snapshots, stored profile snapshot,
  or visual manifest invalidates reviews.
- `final_ready` requires fresh accepted reviews for all generated semantic
  scopes, separate acceptance of exact rendered bytes when present, successful
  acceptance of the exact packaged channel files, successful deterministic
  validation, and a digest-bound validation receipt.
  `no_publication_recommended` becomes complete only after the same package
  validation step.
- External delivery receipt recording rechecks all current output hashes and
  binds the visible receipt to the accepted package and validation-receipt
  digests.
- Run preparation commits from a private staging directory and removes or
  recovers incomplete staging state. Mutating commands use an operating-system
  writer lock and atomic file replacement.
