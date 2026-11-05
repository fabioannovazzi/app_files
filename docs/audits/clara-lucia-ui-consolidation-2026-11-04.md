# Clara and Lucia UI consolidation — 4 November 2026

Base: `90fee768e20d4e40c3f55509ffbfdedb05c92780`.
Candidates: Vera 0.1.565, Clara 0.1.378, Lucia 0.1.204.
These are implementation candidates, not Desktop acceptance or Marketplace publication.

## Individual dispositions

| Product / entry point | Inspected use and decision | Resulting route |
|---|---|---|
| Clara distribution review | Unregistered metadata inspector; raw JSON/source-record panes duplicate delivered charts and report. Remove Clara's embedded shell. | Professional chart/report and explicit decisions in chat; calculation/validation engines retained. |
| Clara mix/contribution review | Same duplicate inspector pattern, with contribution results already delivered by the analysis. Remove embedded shell. | Existing professional outputs and decision engines. |
| Clara period comparison review | Duplicate inspector around delivered comparisons, including raw JSON panes. Remove embedded shell. | Existing professional outputs and decision engines. |
| Clara scatter/bubble review | Generated a second standalone run UI. Keep graphs; replace duplicate review HTML with a short Markdown handoff and update output receipts. | Existing graphs/report and explicit decisions. |
| Clara set overlap review | Unregistered duplicate inspector with JSON/source panes. Remove embedded shell. | Existing outputs and decision engines. |
| Clara variance review | Unregistered duplicate inspector with raw JSON/source panes. Remove embedded shell. | Existing outputs and decision engines. |
| Clara budget dashboard loopback preview | Useful month/cumulative controls and verified calculation output. Port; retain receipt and exact bundled-script checks. | `clara_report_open`, `ui://clara/budget-report-v1.html`; app-only HTML, isolated frame, guarded refresh. |
| Clara management-control loopback preview | Duplicates the report preview and requires a Vera engagement. Remove only the Clara embedded launcher. | Clara's own report app; canonical component and Vera's native report route retained. |
| Clara course chat | Useful paired-chat control. Keep; no tutorial is started by this audit. | Existing local course MCP app. |
| Lucia firm-method editor | Useful editable fields, saved versions, copies, imports and reuse. Port; retire standalone editor generation and download-as-save behavior. | `lucia_method_open`, `ui://lucia/firm-method-v1.html`; visible selected folder, immutable owner-private versions, app-only save/import, and an explicit current-chat handoff of the rechecked saved version. |
| Lucia matter-opening browser editor | Useful persistent professional review, duplicated by a read-only widget. Consolidate into one native editor; remove embedded browser launcher/shell. | `lucia_matter_open`, `ui://lucia/matter-opening-v1.html`; exact-version pending decisions, mutation lock, retries; apply remains separate. |
| Lucia matter-opening read-only widget | Reuse its professional content and translations for the one native review above. Remove internal identifier panels; retain useful matter/register references. | Native app-only evidence and restored decisions. |
| Lucia legal/tax model selector | Simple model-policy check/confirmation needs no separate screen. Retire UI; preserve checks and explicit confirmation tools. | Existing review engine through the local MCP adapter, without a renderer. |
| Lucia answer-planning inspector | Technical helper inspector duplicates professional contract/chat review. Retire renderer/resource; preserve validation, save/apply and exact-version references. | Local review-engine MCP tools plus professional documents/chat. |
| Lucia answer-validation inspector | Technical helper inspector includes Copy JSON and fallback controls. Retire UI; preserve validation and explicit decisions. | Local review-engine MCP tools plus professional documents/chat. |
| Lucia course chat | Useful paired-chat control. Keep; no tutorial is started by this audit. | Existing local course MCP app. |

The six independent chart plugins retain their canonical assets. Product packaging removes only Clara's copies. Removing a product UI must not silently delete an independently used plugin or a business calculation.

## Useful documents and external surfaces

All 27 Clara deck-engine/layout HTML templates remain. `build_html_deck.py`, `init_html_deck.py`, `compose_html_deck.py` and the layout gallery consume them as output templates; they are not duplicate plugin editors.

Course outlines/document previews remain read-only learning/document delivery. The external interview participant, hosted voice, narration upload and completed interview reader have a legitimate external audience/service boundary; substituting a local app would prevent that use. They are not alternate local professional editors.

The interview results reader now uses the shared workflow theme and bundled local fonts. Raw campaign identifiers, audio chunk counts and event counts are removed from its visible metadata; raw JSON/quality-data links are replaced by a local print/save-PDF control. Known technical status values are displayed as plain language, provider/model details are removed, and raw review errors remain outside the professional reader. Other shared voice templates use the same local fonts. The incident-recovery console retains its structured arguments/response because it is an agent-operated recovery route when the normal host helper is unavailable. Its shared theme preserves monospace for actual structured input.

## Boundaries and evidence

New native tools expose the selected full report, method or review only through app metadata; ordinary opener results contain ready/error status. Form values cannot choose a different save directory or run. Selected professional/model-context reads remain subject to their existing account boundary; app-only delivery is not a guarantee that an entire conversation is local-only. No new external recipient is introduced by these ports. Schema/OS errors do not echo private field contents through opener messages.

Source tests separately cover durable reopening, immutable versions, copy/import lineage, exclusive file creation, stale source and pending-decision rejection, duplicate-request recovery, current receipts/scripts, sandboxed period controls and the MCP protocol. Browser tests exercise real resource bytes and local stdio servers at 400 and 1080 pixels. They are isolated browser checks, not Codex Desktop acceptance.

The canonical matter asset builder now reproduces the native resource exactly from its own JavaScript source. Regeneration cannot restore the retired widget. The independent component browser template remains outside the Lucia package. Package/discovery assertions and local reviewer notes follow the retained engines and native apps.

Selecting an existing Vera work item now requests its detailed fullscreen view after the user’s click; it does not add another mode button and keeps the view usable inline if the host declines. This avoids requiring the surrounding chat expansion control.

Vera's shared typography fix addresses an observed host `body` font override. The app content owns its font without overriding the host body. No professional skill entrypoint changed; the localization snapshot refresh preserves the exact previous function IDs/hashes and jurisdiction judgments.

## Release and acceptance gates

- Source verification: 50 focused tests passed with 94.65% coverage; 20 browser checks passed at narrow and wide widths. Shared theme/typography: 122 passed; hosted output: 8 passed.
- All package formats built and passed release consistency/startup checks. The six native app browser checks also passed through both Codex and Cowork packages and their MCP brokers (six checks per format).
- CI caught an unnecessary eager Word/PDF dependency in the firm-method service. Imports now load only when document commands run; a startup regression verifies that opening the editor does not import document processors. Nine package document/reference checks passed after updating the retired editor expectation.
- Earlier `d9328a368` packages were compared member-for-member with exact CI artifacts and installed as Vera 0.1.561 / Clara 0.1.373 / Lucia 0.1.199. That head had 115 successful checks; the teaching workflow ran 1,734 passing tests with three skips, then failed on stale editorial binding records. It was not merged or deployed.
- Fresh Desktop inspection exercised Clara’s period selector and Lucia’s saved method version 2. Lucia’s matter facts and sources were read; its save click timed out before dispatch/persistence could be confirmed. No pending-decision file was created. Vera’s management detail exposed technical metadata. Further panel reads timed out; screenshots and repeated reopen loops are not used as substitutes for acceptance.
- Confirmed presentation defects are included in the new candidates: plain budget scenario headers, display-only cleanup of verified older report headers, translated registered matter headings without changing stored payloads, simpler firm-method hints, and a readable management results/coverage/control view. Exact decimal strings and original saved files are preserved; technical receipts remain available on request. New source browser checks cover reporting/costing at 400 and 1080 pixels, read-only authority, complete bounded metric counts, exact values and unchanged output files.
- Twenty compiled courses differ from their reviewed baseline only in source bindings. The bounded source review preserves historical localized editorial/output judgments. New current-digest execution must independently pass the unmodified teaching release verifier; older JUnit digests are not relabelled.
- Exact CI artifacts, installation and production deployment for the new candidate versions: pending.
- Actual fresh Desktop inspection of every retained UI, Vera’s remaining individual cases, and the complete second pass: pending. Expanded app tabs were available after restart, but inspection repeatedly stalled on later reads. No source/package check or reopened panel is counted as Desktop acceptance.
- No Marketplace upload, submission or publication is authorized or performed.
- Other active task branches/worktrees are preserved; the temporary task branch/worktree is removed only after the tested change is integrated and deployed.

A retained-run comparison identified that even a wording change in the shared
budget producer changes its saved exact implementation scope. The final change
therefore keeps that producer and its copy dictionary byte-identical to the
previous candidate. Scenario abbreviation cleanup, localized forecast headings
and the explanatory forecast prefix are display-only operations inside the
receipt-verified native report frame. The original reports and receipts remain
unchanged. Existing scope checks stay intact; no saved case is recalculated or
replaced merely to display it.

The release integrates main `acb88b4c5` (PR946 and PR948), retaining Vera’s
developer-skill exclusion and Lucia’s single Archive service restricted to its
three registered workflows. The native report/method/matter apps remain separate
owners; the retired metadata renderers remain absent. Main’s 54 public Vera
function identities and jurisdiction judgments are preserved. Generated package
and privacy conflicts are rebuilt from the combined source.

The retained recording/transcription and narration-upload pages also received an
individual content pass. User-facing link errors no longer print raw token
diagnostics; recording details replace “Call metadata”, and narration instructions
refer to the approved request and downloaded audio rather than JSON/hash internals.
The Italian recording view keeps its labels after JavaScript initialization.
Actors, selected data, deletion boundaries, validation and media processing are
unchanged. The four retained hosted templates were rendered individually at 400
and 1080 pixels with fictional context and local assets: Instrument Sans, no page
overflow and no browser errors. No recording, upload or interview was started.
These eight source-browser views are not Codex Desktop capture or service acceptance.


## Expanded Desktop pass and final display fixes

The audit chat was hidden in Desktop. Bringing this same chat into view through
Codex's navigation tool restored 571px panels; no repeated close/reopen request,
new chat, authorization change or screenshot capture was needed. The actual
running audit packages were Vera 0.1.563, Clara 0.1.375 and Lucia 0.1.202.

All 28 bound client-work pages were individually opened in Desktop, plus the
seven specialist pages (Bilancio, Bandi, Patent Box, merger, transformation,
website and communication), the three auxiliary panels, the work directory,
agenda, browser automation and practice/document-format views. These are 42
Vera entry surfaces. Clara's budget and course panels and Lucia's method, matter
and course panels were also individually read. These 47 interactive surfaces
are a different count from the 47 classified Clara/Lucia source surfaces above,
which include removed editors, generated-document templates and hosted pages.

Clara's February control changed the visible comparison to February values;
Budget/Consuntivo labels replaced PL/AC. Lucia restored the exact pending
return decision and synthetic note without applying them or accepting the
engagement. Every Lucia intake section was expanded, exposing remaining owned
English defaults. Bilancio's six review tabs opened individually: this incomplete
fixture has no area plan/catalogue rows, so populated financial-statement output
is not inferred. Agenda history, new commitment and meeting forms were read;
no appointment, meeting, calendar event or message was submitted.

Observed fixes for candidates Vera 0.1.565 and Lucia 0.1.204:

- Translate the twelve additional registered intake default explanations and
  folder purposes in all five supported languages. Unknown authored text stays
  verbatim. Original intake/review/pending-decision bytes and hashes are intact.
- Translate the remaining owned cash, customer-concentration and service-margin
  labels and source roles in management results. Saved calculations, the shared
  budget producer and the bounded payload remain untouched.
- Use the source basename, not the archive's opaque storage path, as Registro
  Imprese headings. Source IDs, original file paths and excerpt retrieval stay
  intact. Add an explanatory empty state for an unprepared read-only invoice
  comparison instead of leaving only the heading and introduction.
- Replace visible Italian implementation terms in the inspected specialist
  panels with ordinary professional wording. Privacy descriptions retain the
  same recipients, app-only/model distinction, original-reading limits,
  account/retention limits and separate external-action boundaries.
- Clarify agenda time-zone labels and translate known history action names.

This source review covers display substitutions and the empty-state addition.
No workflow authority, backend receipt, provider call, semantic/legal decision,
model-context scope, persistence rule or host permission has changed. Refreshing
source fingerprints records these reviewed bytes; it is not fresh professional,
learner, external-service or installed-host acceptance. Final-package Desktop
rechecks and exact-head CI/deployment are separate remaining gates.

Clara is bumped to 0.1.378 because its onboarding source-review binding changes with the compiled source catalogue, even though its native report and course UI code are unchanged.


## Current-package Desktop inspection, 5 November

All remaining 46 entry panels were individually read in the actual Codex MCP
Apps surface, using Vera 0.1.565, Clara 0.1.378 and Lucia 0.1.204. Together with
the corrected Lucia intake inspected on 4 November this covers all 47 entries.
The inspection timeout was avoided by foregrounding this chat and using
accessibility snapshots and ordinary controls after each host request completed.
No font/computed-style probes, screenshot capture, repeated restart request,
authorization changes, or alternate host-control route were used.

The course invitations for all three products, the optional subscriptions panel
and the acquisition plan were visibly present. No course worker was started,
subscription connected, acquisition launched, appointment saved, filing sent,
professional acceptance recorded or other external action performed. Prepared,
empty and read-only fixtures demonstrate those selected views only.

Two actual visible defects were found and corrected: known INPS output labels
are now readable Italian document names, while authored fact labels remain
verbatim; and variance preparation disables save/calculation for read-only
users, requiring a complete choice and renewed confirmation before calculation.
These are presentation/affordance changes. Backend authorization, immutable
source identities, receipt checks, calculations, source/model boundaries and
all saved professional decisions remain unchanged. Focused real-MCP browser
regressions cover the two defects and preserve all original output bytes.

Main 383bb4f was integrated, preserving its bank CSV acquisition workflow,
course-completion reporting, Archive/dependency incident fixes and Windows
snapshot/startup repair. The bank skill operates through the existing browser
and chat and adds no duplicate native editor. Historical privacy and course
reviews retain their original evidence scope; refreshed hashes require fresh
exact-head release CI. Final packages, deployment and corrected-view Desktop
verification are recorded as separate gates rather than inferred here.


Both corrected views were re-opened in actual Desktop: INPS owned output names
are readable and the read-only variance actions are disabled. Every shipped UI
asset in candidates Vera 0.1.573, Clara 0.1.382 and Lucia 0.1.208 is byte-identical
to the assets inspected in Desktop (including the explicitly recorded Vera audit
asset refresh). All 12 finished-package MCP browser checks passed. The audit
backend process for the last two Desktop views was still 0.1.565; final backend
package tests, installation and production deployment retain separate evidence.
All three products built successfully for Codex, Cowork and Antigravity.
