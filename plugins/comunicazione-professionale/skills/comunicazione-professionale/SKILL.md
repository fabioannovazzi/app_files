---
name: comunicazione-professionale
description: Use when a commercialista or professional studio wants Vera to monitor or explain a tax, legal, regulatory, accounting, social-security, corporate, grant, or other professional development; learn an approved studio voice from selected prior communications; decide whether communication is worthwhile; and prepare source-backed client emails, LinkedIn posts, newsletters, website articles, FAQs, client alerts, or branded graphical explainers for professional review and optional publication.
---

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
- Keep client identity and case facts out of public research queries. Use a
  client example only when the professional supplied and approved a lawful,
  appropriate public-use version.
- Keep a generic communication distinct from recipient selection and
  personalized advice. Never infer that one communication applies to every
  client.
- Never send an email, upload an asset, or publish a post unless the user has
  explicitly chosen that route and the exact final package is accepted.
- Reserve explicit approval for external, destructive, approval-sensitive, or
  material steps. Do not interrupt ordinary read-only intake, local analysis,
  or deterministic validation with ceremonial confirmation prompts.
- Never request credentials, cookies, session material, one-time codes, or
  passwords. Use only callable connectors or an already authenticated supported
  browser surface, and stop at account ambiguity or security checkpoints.

## Codex-Native Run UX

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
`codex_run_review.md` beside the package. Never edit plugin source or generated
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

3. Create `communication_intake.json` from actual user choices and selected
   material. Include the objective, audience, channels, selected source files,
   selected prior communications, and an optional brand profile. Prepare a run:

   ```bash
   python scripts/prepare_run.py \
     --workspace <private-workspace> \
     --intake <communication_intake.json>
   ```

4. Read the exact bound inputs. When public research was selected, research
   with generic topic-level queries and record exact official source snapshots
   or user-readable source files in a new prepared run before confirming
   claims. Do not treat a URL string as captured evidence.
5. Use model-led reasoning to write `model_contribution.json` according to the
   contract. A `publish` contribution contains a studio profile proposal when
   history is present, source assessments, atomic claims, a master brief,
   channel drafts, and a visual story. A `no_publish` contribution explains why
   communication is not useful and contains no promotional filler. Every
   contribution includes a model-led `editorial_value` judgment; a calendar,
   generic awareness, or available word count is never sufficient.
6. Record the exact provider, model, template version, and operator:

   ```bash
   python scripts/record_contribution.py \
     --run-dir <run-dir> \
     --contribution <model_contribution.json> \
     --provider <provider> --model <model> \
     --template-version professional-communication-v1 \
     --recorded-by <operator>
   ```

7. Review the visible `review_handoff.md`, claims, drafts, and visual story.
   Record each required scope with `accepted`, `returned`, or `rejected` and
   `--confirmed-by-user`. Required scopes are generated from the actual package;
   do not invent an approval:

   ```bash
   python scripts/record_review.py \
     --run-dir <run-dir> --scope <scope> \
     --decision accepted|returned|rejected \
     --reviewer <professional> --confirmed-by-user
   ```

8. A returned or rejected draft may be replaced with
   `record_contribution.py --supersede`; this creates a new immutable version and
   invalidates prior reviews. Never edit a reviewed version in place.
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
   digest separately:

   ```bash
   python scripts/record_review.py \
     --run-dir <run-dir> --scope rendered_output \
     --decision accepted|returned|rejected \
     --reviewer <professional> --confirmed-by-user
   ```

11. Package the accepted drafts, technical basis, exact accepted visuals, and a
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
- `content_workbench.json` preserves the model contribution and provenance.
- `review_payload.json` and `review_handoff.md` expose the review queue.
- `review_log.json` binds professional decisions to one exact contribution
  digest and binds `rendered_output` decisions to one exact visual-manifest
  digest and `packaged_output` decisions to one exact package digest.
- `visual_manifest.json` proves PNG dimensions, font assets, and byte hashes.
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

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
