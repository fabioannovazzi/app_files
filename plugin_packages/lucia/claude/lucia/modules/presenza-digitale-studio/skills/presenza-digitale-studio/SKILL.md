---
name: presenza-digitale-studio
description: Use when a commercialista or professional studio wants Vera to assess and refresh an existing informational website, create a first professional website from verified studio materials, prepare an unlisted review preview, or package an approved site for publication. Covers content hierarchy, restrained visual identity, responsive implementation, browser review, mechanical validation, and approval-bound publishing; excludes transactional portals, e-commerce, custom business applications, invented claims, and autonomous publication.
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

# Presenza digitale dello studio

Create a credible, current and reviewable professional-studio website. Support
two modes:

- `refresh`: inspect and improve an existing website;
- `first_site`: create the studio's first website from verified materials and
  conservative proposed defaults.

Do not frame the result as a fashionable or spectacular website. Build a
decent professional presence that is clear, responsive, accessible, restrained
and appropriate to the studio.

 When this skill is
used independently, keep the improvement note local to chat or run artifacts.
Do not submit it to Mparanza automatically.

## Required reading

Read completely before execution:

- `references/product-thesis.md`;
- `references/workflow-method.md`;
- `references/website-quality-standard.md`;
- `references/skill-orchestration.md`;
- `references/sites-handoff.md` when supplied artifacts already name Sites, to preserve the Cowork-unavailable publication boundary.

## Output location

Never write run outputs inside this Git workspace or a published folder. Use
one explicitly authorized, owner-controlled studio workspace. A tokenized
preview or production destination is an external publication route, not the
working directory.

## Hard boundaries

- Never invent services, qualifications, memberships, results, testimonials,
  client names, team members, history, locations, contact details, legal text,
  privacy/cookie compliance, prices or availability.
- Never describe a proposed first-site identity as established studio history.
  Mark each brand or voice field `observed`, `user_supplied`, or
  `vera_default_proposal`.
- Do not promise SEO ranking, accessibility compliance, legal compliance,
  conversion results or compatibility that was not tested.
- Do not accept a visual mock-up as a working site. Inspect the actual rendered
  implementation at desktop and phone widths.
- Do not publish a preview or final site unless the intake selected that exact
  route. Final publication additionally requires acceptance of the exact
  identity, claims, responsive preview and package digest.
- Never request passwords, cookies, one-time codes or hosting credentials.
  Use a callable connector, a supported authenticated browser, or a user-run
  handoff without exposing credentials.
- Keep transactional portals, client areas, e-commerce, booking/payment flows,
  contact forms, third-party embeds, remote executable scripts, bespoke
  applications and regulatory legal drafting outside this workflow. Identify
  them as separate, explicitly reviewed integrations rather than hiding them
  inside an informational-site build.
- Reserve explicit approval for external, destructive, approval-sensitive, or
  materially unresolved steps. Do not add ceremonial pauses to reversible
  inspection, drafting, implementation or local validation.
- Keep selected source files and working outputs local in the owner-controlled
  workspace by default. Deterministic scripts own snapshots, hashes,
  mechanically verifiable HTML checks, review freshness and package binding;
  model-led skills own semantic and visual judgment.
- Select a file or confirmed fact only when the professional has approved it
  for website work. This confirms the purpose of the source; it does
  not accept every statement in the source as final website copy.
- During evidence mapping, the selected runtime may read the complete approved
  source when the brief requires it. After the brief is recorded, follow its
  `source_use_plan`: default to mapped facts, use only named excerpts or assets
  for targeted access, and reopen a complete source only when the model records
  a concrete professional reason. Do not use deterministic code to decide
  relevance or to classify personal data.

## Cowork-native Run UX

1. Show a checklist covering dependencies, Run Intake, evidence, brief,
   implementation, desktop and phone review, approval and packaging.
2. Show a Run Intake table with the studio, mode, objective, audience,
   requested pages, selected materials, private output path and each external
   route posture.
3. Use a Decision Table only for unresolved material choices that change
   identity, scope, claims, destination or authorization. Populate it from the
   actual inputs; do not offer page sets, style labels or platforms unless the
   facts cue them.
4. Before a write-heavy stage, show an execution checkpoint with the bound
   inputs, private output path, intended command and expected files. Pause only
   when an unresolved answer would materially change the site or an approval
   boundary.
5. End with the Artifact Card defined below.

Default output policy: create the private JSON, HTML, CSS, asset, screenshot and
package artifacts required by the selected mode. These are not choices to
propose. When useful, save the visible run summary as `run_review.md`
beside the package. Never edit plugin source or generated ZIPs during a studio
website run.

## Workflow

1. Run `python scripts/check_dependencies.py` from the resolved plugin root.
   Do not install missing requirements at runtime.
2. Determine `refresh` or `first_site` from the evidence. Do not ask when the
   presence or absence of an existing website is clear.
3. Show a compact Run Intake with studio, mode, objective, audiences, selected
   materials, requested pages, current platform when known, and five external
   route records: `public_site_inspection`, `studio_material_connector`,
   `creative_assistance`, `preview_publication`, and `final_publication`. Each
   route records its provider. Cowork must not select `sites` for a new route;
   use another provider only when the professional explicitly selects it.
4. Before helper scripts or write-heavy work, identify material choices that
   would change execution: public identity, audience, information scope,
   destination or review posture. Ask only those unresolved choices in chat.
   Generate choices from the actual inputs; do not offer named frameworks or
   style taxonomies unless the facts cue them or the user must supply a missing
   custom value. For `first_site`,
   default to a small informational site and label the initial visual system
   as a Vera proposal. Do not require a logo, slogan, testimonials or a brand
   manual.
5. Initialize the private workspace once and prepare the run:

   ```bash
   python scripts/initialize_workspace.py \
     --workspace <private-workspace> \
     --workspace-id <stable-id> \
     --owner <studio-or-professional> \
     --retention-owner <studio-or-professional> \
     --confirmed-by-user

   python scripts/prepare_run.py \
     --workspace <private-workspace> \
     --intake <website_intake.json>
   ```

   Preparation requires at least one selected evidence file or one exact fact
   explicitly confirmed by the professional. Every `selected_files` and
   `confirmed_facts` entry must record `approved_for_website_use: true`; do not
   prepare the run until the professional has selected that material for the
   website purpose. Put chat-confirmed first-site facts in
   `confirmed_facts`; preparation snapshots each fact as immutable evidence
   without asking the professional to manufacture a document. It snapshots every
   selected local file, records SHA-256 and creates `work/site/` plus the
   optional `work/sites-project/`. A URL is not a source snapshot. When public inspection was
   selected, capture the exact HTML, screenshots or extracted evidence used and
   add those local files to a new prepared run.
6. Inspect evidence and write `site_brief.json` against its schema. Include one
   `source_use_plan` entry for every selected evidence ID. The model assigns the
   professional purpose and chooses `mapped_brief_only`, `targeted_material`, or
   `full_source_required`; exact locators identify every targeted excerpt, page,
   section, asset or code path. Use `full_source_required` only with a concrete
   reason specific to the website work. Deterministic validation checks schema
   shape and exact source-ID coverage only; it does not decide which mode is
   professionally appropriate. In
   `refresh`, distinguish observations from proposed changes. In `first_site`,
   distinguish supplied facts from proposed information architecture, voice
   and visual defaults. Run:

   ```bash
   python scripts/record_site_brief.py \
     --run-dir <run-dir> --brief <site_brief.json> \
     --provider <provider> --model <model> --recorded-by <operator>
   ```

7. Use the host-skill sequence in `references/skill-orchestration.md`. After the
   brief is recorded, give downstream design, copy and implementation work the
   current brief plus only the material permitted by `source_use_plan`. Do not
   reopen `mapped_brief_only` sources. For `targeted_material`, use only the
   named material. Reopen a `full_source_required` source only for its recorded
   reason, then return to the mapped brief. When a
   named skill is callable, read and follow it rather than imitating it. Use
   the internal quality standard only for unavailable skills. Build the actual
   site in `work/site/`; keep primary content and navigation usable without
   JavaScript unless a requested feature requires it.
8. Validate mechanically:

   ```bash
   python scripts/validate_site.py --run-dir <run-dir>
   ```

   The validator checks only mechanically verifiable properties: file
   integrity, required HTML metadata, heading shape, alternative-text
   presence, duplicate IDs, local link/asset closure, unsafe schemes, out-of-scope
   forms and active embeds, placeholders and preview-indexing posture. It does not judge aesthetics,
   copy quality, accessibility conformance or professional truth.
9. Render the exact site in a browser at desktop and phone widths. Inspect the
   full page, interaction state, overflow, navigation, images, typography,
   hierarchy and console errors. Save the exact full-page PNG for each claimed
   viewport below `reviews/browser/`, record its run-relative path and SHA-256
   in `quality_assessment.json`, then record it:

   ```bash
   python scripts/record_quality_assessment.py \
     --run-dir <run-dir> --assessment <quality_assessment.json> \
     --provider <provider> --model <model> --recorded-by <operator>
   ```

   A `revise` or `blocked` verdict requires correction and a new validation and
   assessment. Do not mark the site ready from file existence or one viewport.
10. Package an unlisted preview only when `preview_publication` was selected:

    ```bash
    python scripts/package_website.py --run-dir <run-dir> --kind preview
    ```

    The preview package requires `noindex, nofollow, noarchive` on every page
    and binds exact bytes. Publish it only to the selected destination and
    verify the visible URL. Cowork cannot initiate a Sites publication. For
    another explicitly selected provider, use `record_external_delivery.py`;
    for supplied Sites artifacts, follow `references/sites-handoff.md` and
    keep any unproven publication pending.
11. Present one visible review matrix for `identity_and_claims`,
    `responsive_preview` and `publication_destination`. Record only explicit
    decisions against the current site digest:

    ```bash
    python scripts/record_review.py --run-dir <run-dir> \
      --scope <scope> --decision accepted|returned|rejected \
      --reviewer <professional> --confirmed-by-user
    ```

12. Remove every preview robots directive, then revalidate, repeat browser
    assessment and obtain current reviews for the changed release bytes.
    Package the release only after all three scopes are accepted:

    ```bash
    python scripts/package_website.py --run-dir <run-dir> --kind release
    python scripts/validate_run.py --run-dir <run-dir>
    ```

    Publish only through the exact selected route. Verify the live site and
    record the exact URL or receipt. A package is not evidence of publication.

    When supplied artifacts name Sites, follow `references/sites-handoff.md`,
    review the existing binding and receipt as evidence, and keep publication
    pending unless those artifacts already prove a succeeded deployment.

## Completion

End with an Artifact Card containing mode, evidence coverage, post-brief source
use modes, brief version,
skill routes used and unavailable, mechanical validation status, browser
viewports inspected, current site digest, reviews, preview URL, release
package, final URL, unresolved issues and the next authorized action.

Completion states are:

- `preview_ready`: exact preview package exists and is mechanically and
  visually ready;
- `release_ready`: exact release package and all required reviews are current;
- `published`: a visible final URL or provider receipt is bound to the exact
  release digest;
- `partial`: useful work exists but an optional capability or material input is
  missing;
- `blocked`: identity, evidence, validation or approval required for the next
  claimed state is absent.
