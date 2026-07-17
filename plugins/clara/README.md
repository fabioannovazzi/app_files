# Clara

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/clara) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Clara is a Codex plugin for advisory and succession projects where the
core asset is consultant judgement. It keeps a durable case map, indexes source
materials in place, stores Codex-structured judgement as draft candidates, and
maintains cross-interview case issues that accumulate evidence for and against
the live hypotheses. It renders only decision-pack-ready items into Markdown and
Word client outputs. It also maintains `case_brief.md`, a derived working brief
for resuming the case without relying on chat history. Clara also embeds the
Attribute Reporting specialist workflow for centrally governed retail taxonomy
mapping, preserved cohort comparisons, private local HTML reports, and direct
correctness verdicts. It also embeds Reporting Engine and eight chart-family
components for local business-data analysis and rendering.

Clara is the plugin's AI consultant role. The senior partner keeps judgement;
Clara prepares the intelligence layer, asks only for judgement bottlenecks, and
turns validated understanding into working artifacts.

## Conversation Workflows

Clara keeps five related capabilities separate:

- `interview` prepares an expiring browser link for an adaptive external
  participant interview, then retrieves the completed bundle and quality review;
- `transcribe` records or uploads advisor voice notes, meetings, and calls,
  preserves the local bundle, and completes transcript attribution and review;
- `deck-correction` turns spoken or written feedback into reviewed, approved,
  rendered, and verified changes to an existing PPTX or Clara HTML deck.
- `attribute-reporting` maps retailer products to the central category
  taxonomy, preserves the established new-versus-rest and
  best-seller-versus-other comparisons, creates a private local HTML report,
  and answers whether the report is correct.
- `reporting-engine` profiles a CSV/XLSX dataset, lets Codex select the useful
  analysis from the business question and actual fields, and runs the embedded
  distribution, funnel, mix, period, scatter, overlap, statement, or variance
  component.

Hosted interviews and Hosted Voice are different systems and bundle schemas.
The first conducts an external interview; the second captures or transcribes an
advisor discussion or existing recording. Neither automatically promotes its
output into advisory conclusions.

Attribute Reporting is also independent of the advisory case workflow. Its
structured scrape records, canonical taxonomy, accepted mappings, and image
URLs remain server-authoritative; product images and report artifacts remain
local. Do not add its report to a case or convert it into a 16:9 deck unless the
user explicitly asks for that follow-on work.

The editable Attribute Reporting, Reporting Engine, and chart-family
implementations remain in their `plugins/<component>` source folders. Clara's
package builder embeds them under `modules/`, while the thin Clara skills own
discovery and routing. This keeps one implementation for standalone development
tests and the installed Clara workflow.

The scripts are intentionally mechanical. They validate JSON shape, preserve
source provenance, enforce the client-pack inclusion gate, and render outputs. Codex handles
the semantic work: interpreting advisor judgement, challenging assumptions after
import, asking follow-up questions, and drafting client-facing narrative.

For Attribute Reporting, delegate its dependency check before component helper
scripts:

```bash
python scripts/check_dependencies.py --module attribute-reporting
```

For data analysis and charts:

```bash
python scripts/check_dependencies.py --module reporting-engine
```

## Two-Loop Advisory Delivery

Clara's default delivery model has two loops. The first loop is advisory
intelligence; the second loop is presentation excellence.

For a first deck or brief, Clara's governing question is the best current
advisory position the advisor can responsibly take into the next decision
conversation, given the evidence available, the evidence missing, and the
decisions that cannot be postponed. The first deck is not a summary of scenarios
or materials; it states the responsible decision posture now and what must be
tested, evidenced, or decided before moving further.

Before the advisory workpaper, Clara maintains
`advisory_evidence_map.md`: a living claim-by-claim evidence map. It records
which evidence supports, weakens, contradicts, or creates each claim or option;
the source type; what the evidence proves and does not prove; directness,
reliability, corroboration, bias or limitation, decision implication, and
missing evidence that would change the position. New indexed materials, notes,
transcripts, case-update imports, or corrected prior outputs must update this
map before Clara revises the workpaper, storyline, deck, memo, or decision pack.

In Loop 1, Codex/Clara inspects the case folder and relevant source materials,
then produces an `advisory_workpaper.md` before building a deck, memo, or HTML
brief. The workpaper should define the real decision, Clara's default point of
view, evaluated options, implementation steps and conditions, owners, timing,
risks, failure modes, evidence for and against, contradictions, weak
assumptions, critical questions, and an advisor talk track. Clara critiques this
artifact until it cannot identify a materially stronger advisory structure from
the available evidence.

The Loop 1 output also includes `judgement_checkpoint.md`: a compressed set of
advisor judgement calls with Clara's default answers. The default assumption is
that the advisor has no time. Unless the user explicitly asks Clara to wait,
Clara proceeds using its defaults and marks unresolved points as
advisor-unconfirmed in the workpaper or control notes.

In Loop 2, Clara builds the human-visible deliverable from the Loop 1 workpaper
and any supplied advisor judgement, then critiques the deck or document for
structure, page value, insight, clarity, evidence weight, advisor usability,
anti-BS quality, and visual readability. The objective is not a fixed number of
slides or pages. The objective is the best Clara can produce from the available
materials and judgement.

If Loop 1 shows that the honest answer is that further evidence, a test,
interview, decision, or data request is needed, the deliverable should say that
cleanly when it matters to the decision. Clara should not produce polished HTML
that hides material uncertainty, missing implementation conditions, or required
next steps. The deck or memo should carry the best current point of view and the
specific evidence gaps or actions that govern the next decision.

Use `/goal` for major phase gates only: evidence exhaustion and advisory
workpaper, judgement checkpoint, deliverable build, and deliverable excellence
review. Use ordinary checklists inside each goal.

Deck correction is always a goal-level workflow. When Clara/Codex corrects,
revises, or rebuilds a PPTX from a call, transcript, screen video, review notes,
or partner feedback, start or continue an explicit goal before the
deck-revision work begins. The goal covers intake, interpretation, approval,
PPTX application, rendering, verification, and final output review; use ordinary
checklists for the internal substeps.

## Animated HTML Decks

The `html-deck` skill turns approved Word, PDF, Markdown, report, or case
materials into a source-faithful standalone 16:9 browser presentation. Its
structured deck plan selects from a 15-layout editorial registry, while a
claim-level content ledger and source-bound chart/table components preserve
provenance. The shared stage engine provides semantic motion, fragments,
keyboard/touch navigation, notes, overview, fullscreen, print behavior, and
Voice Capture metadata. The builder creates one dependency-free,
content-addressed HTML file and canonical ZIP. Automated multi-viewport browser
QA checks geometry, collisions, interactions, console output, reduced motion,
and print; model-led review still judges fidelity, hierarchy, and usefulness.
Preservation-aware revision maps protect untouched slides, components, global
styles/runtime, IDs, order, and slide-local provenance. A difficult URL is
convenient obscurity, not access control.

Standalone educational or conference talks do not require a fabricated Clara
case workspace. Decks that carry an active Clara case recommendation still
inherit the evidence-map and advisory-workpaper gates before presentation work.

Strict HTML deck browser QA also requires a runnable Chrome or Chromium. The
dependency checker verifies the Python Playwright binding; it does not install
or verify a browser executable. On a fresh environment, provide Chrome/Chromium
or run `playwright install chromium` before browser QA.

## Typical Flow

1. Run `scripts/check_dependencies.py`. When scanned PDFs, screenshots, or other
   image-only evidence require local OCR, also run
   `scripts/check_dependencies.py --requirements requirements.txt --requirements requirements-ocr.txt`
   and install from `requirements-ocr.txt` if the environment allows it.
2. Initialize a case workspace with `scripts/init_case.py`.
3. Index source files with `scripts/index_materials.py`. Supported previews
   include Markdown/text, Word, PDF placeholders, and PowerPoint decks.
4. Copy downloaded/local files into the case with `scripts/add_case_file.py`
   when Codex needs to make a file durable before indexing or handoff. The
   helper routes presentation drafts to `outputs/presentations/current`, notes
   to `notes/`, audio to `source_materials/interviews/audio/`, and ordinary
   source documents to `source_materials/project_docs/`. Add `--register` when
   the copied file should be recorded in `material_registry.json`.
5. Prepare Clara's first kickoff with `scripts/prepare_clara_kickoff.py`.
6. Ingest pasted notes with `scripts/ingest_notes.py`, or launch hosted Voice
   Capture with `scripts/launch_hosted_voice.py`.
7. Let Codex draft structured judgement entries, then store them with
   `scripts/add_judgement.py`. Store separately drafted follow-up questions
   with `scripts/add_open_questions.py`.
8. For a reviewed transcript integration that needs several mechanical updates
   at once, let Codex prepare a JSON plan and apply it with
   `scripts/integrate_transcript_review.py`. The helper can correct a transcript
   material path, fill review-note sections, append pending judgement, link
   existing open questions, update issue evidence/synthesis, refresh
   `case_brief.md`, and print a validation/evidence-chain summary. It does not
   interpret transcript content; Codex supplies the semantic plan from inspected
   text evidence.
9. Let Codex update cross-interview issues with `scripts/upsert_case_issues.py`
   when an interview confirms, weakens, contradicts, or opens a live hypothesis.
10. For high-stakes advisory deliverables, let Codex create
   `advisory_evidence_map.md`, `advisory_workpaper.md`,
   `judgement_checkpoint.md`, `presentation_storyline.md`, and
   `presentation_review.md` as the two-loop reasoning and deck-quality
   artifacts. These are Codex-authored working
   artifacts, not deterministic script outputs.
11. Let Codex show a short numbered inclusion summary in chat. The advisor says
   what should go into the client pack, and Codex records that decision with
   `scripts/approve_judgements.py`. When the pending list is long, Codex first
   groups entries semantically into advisor-readable bundles, applies the
   bundle plan with `scripts/apply_inclusion_bundles.py`, rebuilds
   `inclusion_review.md`, and lets the advisor include or exclude whole bundles
   while preserving item-level traceability.
12. When Clara is not enough, ask Codex to prepare a support package;
   Codex runs `scripts/prepare_support_package.py` and creates a clean ZIP plus
   a `support_request.md` note.
13. Share a clean full workspace ZIP with `scripts/export_case_workspace.py`
   when a coworker needs the whole folder. Exchange append-only updates with
   another local workspace using `scripts/export_case_update.py` and
   `scripts/import_case_update.py` when collaborating over time.
14. Refresh or inspect `case_brief.md` with `scripts/build_case_brief.py` when
   the JSON files were edited outside the helper scripts.
15. Generate clean `decision_pack.md` / `decision_pack.docx` and separate
   provenance workpapers with `scripts/build_decision_pack.py`.

## Adding Downloaded Files

Use `scripts/add_case_file.py` when a downloaded or local file should be copied
into the case workspace before further work. It preserves the original filename,
reuses an identical existing copy, and adds `-2`, `-3`, and so on when a
different file with the same name is already present.

```bash
python scripts/add_case_file.py <case-dir> ~/Downloads/example.pptx
python scripts/add_case_file.py <case-dir> ~/Downloads/source.pdf --register
python scripts/add_case_file.py <case-dir> ~/Downloads/interview.m4a --kind audio
python scripts/add_case_file.py <case-dir> ~/Downloads/notes.md --kind note --register
```

`--kind auto` routes audio files to `source_materials/interviews/audio/`, note
files and note-like names to `notes/`, presentation draft names such as
`incontro`, `deck`, `slides`, or `draft` to `outputs/presentations/current/`,
and other files to `source_materials/project_docs/`. Use `--kind source`,
`--kind note`, `--kind audio`, or `--kind deck` when the filename is ambiguous.
When `--register` is used, the helper registers the copied path and refreshes
`case_brief.md`. If the new registered material could affect the advisory
position, Codex updates `advisory_evidence_map.md` before using it in a
workpaper, storyline, deck, memo, or decision pack. For `.pptx` presentation
drafts, `add_case_file.py` automatically inspects the deck for WMF/EMF media
and writes a `<name>_normalized_for_merge.pptx` sibling plus a
`.normalization_report.json` when legacy media are found. Use
`--skip-legacy-pptx-normalization` only when the copied deck will not feed an
editable merge.

## Importing Hosted Voice Bundles Into Ordinary Folders

When the user only needs a hosted call transcript preserved in a normal
document folder, do not initialize a Clara case workspace. Use the lightweight
plain-folder importer instead:

```bash
python scripts/import_hosted_voice_bundle_to_folder.py \
  <target-folder> <case-notes-audio-or-voice.zip>
```

The helper keeps the original ZIP or JSON bundle in the target folder, writes a
readable sibling `<bundle-stem>-transcript.md`, and maintains the hidden control
registry `.clara/voice_imports.json`. It uses bundle, canonical payload,
transcript, and available media SHA-256 fingerprints to make repeated imports
idempotent. On its first run against a folder that already contains an identical
bundle and a transcript containing the same source text, it adopts those files
without rewriting the transcript. A missing transcript is repaired.

The helper never deletes or overwrites documents. Unrelated filename collisions
receive `-2`, `-3`, and so on. A suspicious alternate version of the same
recording is rejected unless the user deliberately passes `--allow-variant`;
the registry then links the variant to the earlier import. Use `--dry-run` to
inspect the intended paths and `--json` for a machine-readable result.

This path only preserves source material. It does not create case JSON files,
register judgement, infer speakers, or make the transcript advisory evidence.
If `case_manifest.json` is present, use `import_hosted_voice_bundle.py` instead.
Speaker attribution remains a separate local Codex/Clara text review that keeps
the original transcript unchanged.

## Normalizing Legacy PowerPoint Decks

Use `scripts/normalize_legacy_pptx.py` before editable slide merging when a
source deck already sits outside the `add_case_file.py` flow and contains
legacy WMF/EMF media or was produced by an older PowerPoint/export pipeline.

```bash
python scripts/normalize_legacy_pptx.py ~/Downloads/example.pptx
python scripts/normalize_legacy_pptx.py ~/Downloads/example.pptx \
  --output ~/Downloads/example_normalized_for_merge.pptx --overwrite
```

The helper inspects `ppt/media/` for `.wmf` and `.emf` parts, runs a
LibreOffice PPTX round-trip only when needed or when `--force` is passed,
preserves Clara custom properties such as transcript links, validates the output
package, and writes a `.normalization_report.json`. Use the normalized deck as
the base for editable merge operations. If legacy media remain after
normalization, use an image fallback only for affected slide content.

Before any editable PPTX merge, run the merge-input guard:

```bash
python scripts/prepare_editable_pptx_merge_input.py ~/Downloads/example.pptx
python scripts/prepare_editable_pptx_merge_input.py ~/Downloads/example.pptx \
  --normalized-pptx ~/Downloads/example_normalized_for_merge.pptx
```

The guard writes an `.editable_merge_input_report.json` and returns the PPTX
base that merge code may use. It fails when a legacy WMF/EMF source has no
normalized merge base. If normalization is deliberately skipped because the
operation is image-only or otherwise safe, pass
`--skip-normalization-reason "<specific reason>"`; do not let merge code bypass
this check silently.

## Clara Kickoff

Clara's first useful loop is preparation plus kickoff. Codex may browse public
or authorized sources before calling the helper, then pass concise source
takeaways as JSON. The helper itself is deterministic: it records source links,
industry implications, material anchors, succession lenses, and red flags.

```bash
python scripts/prepare_clara_kickoff.py <case-dir>
python scripts/build_clara_kickoff_deck.py <case-dir>
python scripts/launch_hosted_voice.py <case-dir>
python scripts/import_hosted_voice_bundle.py <case-dir> <downloaded-bundle.json>
python scripts/build_clara_partner_brief.py <case-dir>
```

The kickoff posture is that the senior partner briefs Clara. Clara listens and
asks only essential clarifications when a missing point blocks understanding.
The kickoff deck is the first working readout when the partner has not yet
imported a voice kickoff. Kickoff imports update `clara_mandate.json`; the HTML
brief and deck are local working artifacts for the partner, not client
deliverables.

## Case Brief

`case_brief.md` is a readable working view generated from the canonical case
JSON files. It is useful when reopening a case after a break: Codex can read the
brief first, then inspect the underlying JSON and source materials as needed.

The brief is not a source of truth. It is rebuilt from `case_manifest.json`,
`material_registry.json`, `judgement_log.json`, `open_questions.json`, and
`case_issues.json`, and `clara_mandate.json`. Draft judgement appears only in a
pending-review section and cannot feed the client decision pack until the
advisor marks it ready for client-pack use.

```bash
python scripts/build_case_brief.py <case-dir>
```

Validate the canonical JSON files without rebuilding derived artifacts:

```bash
python scripts/validate_workspace.py <case-dir>
```

Validation also checks linked raw-audio pointers. If a transcript material
references `raw_audio_pointer_material_id`, the pointer must be marked
transcribed, link back to the transcript material/path, and must not still say
"not yet transcribed" in the pointer Markdown.

If validation is already failing only because linked raw-audio pointer metadata
or pointer Markdown is stale, repair that narrow pointer linkage before running
full validation again:

```bash
python scripts/repair_audio_pointer_links.py <case-dir>
python scripts/repair_audio_pointer_links.py <case-dir> \
  --transcript-material-id <transcript-material-id>
```

This helper runs without a pre-validation gate. It only repairs existing
transcript records that already reference an existing raw-audio pointer; it
does not recreate missing pointer records or change transcript content.

## Removing Wrong Materials

If a material was imported or registered by mistake, remove it through the
deterministic helper instead of hand-editing `material_registry.json`.

```bash
python scripts/delete_material.py <case-dir> mat-0055 mat-0056
python scripts/delete_material.py <case-dir> mat-0055 --ignore-missing
python scripts/delete_material.py <case-dir> mat-0055 --remove-empty-orphan-dirs
```

The helper removes the registry records, scrubs canonical material references
from `judgement_log.json` and `clara_mandate.json`, refreshes `case_brief.md`,
validates the workspace, and reports orphan candidate paths. It never deletes
files or non-empty folders; `--remove-empty-orphan-dirs` only removes empty
case-owned directories.

## Cross-Interview Issues

`case_issues.json` is the lightweight issue model Clara uses when a case has
multiple interviews or source rounds. Each issue has a stable ID, title,
decision area, current synthesis, status, evidence-for judgement IDs,
evidence-against judgement IDs, and open-test question IDs.

Use it only for live questions that matter to the client decision. It is not a
taxonomy exercise and should not duplicate every judgement entry.

```bash
python scripts/upsert_case_issues.py <case-dir> --issues-json <issues.json>
python scripts/upsert_case_issues.py <case-dir> \
  --id production_quality_transition \
  --title "Production and quality transition" \
  --decision-area "Operating transition" \
  --current-synthesis "Quality ownership is unresolved." \
  --evidence-for jud-0017 \
  --open-test q-0012
```

## Client-Pack Inclusion

For solo-advisor work there is no separate approval ceremony. The advisor is
not approving themselves; they are deciding which Codex-structured statements
are ready to rely on in a client-facing pack.

In normal Codex use, Codex shows a short numbered summary in chat and the
advisor replies naturally, such as "include all", "include bundle 1",
"exclude item 7", or "show me more on item 3". Codex then runs the mechanical
helper and records the advisor name in the audit log.

For long reviews, Codex/Clara should create thematic inclusion bundles before
asking the advisor to decide. Bundle themes are semantic judgement from the
case evidence, not deterministic keyword classification. The bundle JSON may be
a list or an object with `bundles`; each bundle has `title`, optional `id`,
optional `description`, and `entry_ids`.

```bash
python scripts/apply_inclusion_bundles.py <case-dir> \
  --bundles-json <inclusion-bundles.json>
python scripts/build_inclusion_review.py <case-dir>
```

The helper can also print the candidate summary directly:

```bash
python scripts/approve_judgements.py <case-dir>
```

After the advisor confirms that all candidate entries are ready for the client
pack, mark them in one audited update:

```bash
python scripts/approve_judgements.py <case-dir> \
  --all-pending \
  --recorded-by "<advisor>"
```

For a single numbered item that needs a different decision:

```bash
python scripts/approve_judgements.py <case-dir> --item <number> \
  --include \
  --recorded-by "<advisor>"
```

For a whole thematic bundle:

```bash
python scripts/approve_judgements.py <case-dir> --bundle <number-or-id> \
  --include \
  --recorded-by "<advisor>"
```

## Hosted Voice Debrief

The hosted voice path lets the Clara plugin use the Mparanza server for
Realtime voice without requiring a local OpenAI API key. The server issues a
short-lived launch token with compact context from the local `case_brief.md`.
That context is kept only in the launch-token metadata while the token is
valid. The hosted page records live audio or uploads an existing recording; for
browser tab audio it can also capture tab video as provenance. The server
transcribes audio and returns a downloadable bundle. Attribution, challenge,
and semantic review happen after import, when local Codex reviews the full
transcript in the case workspace.

```bash
python scripts/launch_hosted_voice.py <case-dir>
python scripts/import_hosted_voice_bundle.py <case-dir> <downloaded-bundle.json>
python scripts/upload_hosted_audio.py <case-dir> <audio-file> --magic-link "<url>"
python scripts/upload_hosted_audio.py <case-dir> <audio-file> --cookie-header-file /tmp/mparanza.cookie
```

For deck feedback, the normal Codex-facing entry point is the natural-language
request **“Clara, record feedback on this deck.”** Clara resolves the current
case and target deck, then runs the single continuing helper:

```bash
python scripts/start_deck_feedback.py <case-dir> \
  --deck <existing-deck.pptx-or-html> \
  --browser chrome
```

The helper opens the context-bearing hosted capture, watches for a new bundle,
imports it automatically, and records the exact deck target in the imported
voice session. Users do not need the server URL or a manual Downloads-folder
handoff.

Imported sessions are written under `voice_sessions/`, registered as transcript
materials, and added to `judgement_log.json` as pending entries only. They are
not used in the decision pack unless later marked ready for client-pack use.
The import also writes `voice_sessions/<timestamp>/codex_discussion_review.md`,
a local-only Codex review pack for the second-pass advisory read of the full
discussion: weak assumptions, contradictions, missed questions, and candidate
Clara entries. Before an imported transcript changes the advisory position or
deck, Codex updates `advisory_evidence_map.md`.

For screen-video sessions that may revise an existing deck, Clara prepares a
local deck-revision intake before slide editing. The intake is evidence
plumbing, not semantic judgement: it links transcript/video/deck evidence,
extracts a PPTX snapshot when a deck is attached, resolves the inherited
company/deck style authority, snapshots that style spec into the voice session,
enriches feedback timeline frames with conservative slide-match candidates when
rendered slide images and extracted video frames are available, and writes
`deck_revision_gate.md` for Codex/Clara review. Slide matching is visual
candidate evidence only; Clara/Codex still decides what the speaker meant.

After the intake has an attributed transcript, attached PPTX, and resolved
style authority, build the local revision workbench:

```bash
python scripts/build_deck_revision_workbench.py <case-dir>
```

This writes:

- `voice_sessions/<timestamp>/deck_revision_workbench.json`
- `voice_sessions/<timestamp>/deck_revision_prompt.md`
- `voice_sessions/<timestamp>/deck_revision_changes.schema.json`
- `voice_sessions/<timestamp>/deck_revision_changes.md`

The workbench still does not call a model and does not edit the PPTX. It gives
Codex the exact local prompt, evidence paths, deck snapshot, style spec, and
  schema for producing focused interpretation packets and then
  `deck_revision_changes.json`: the list of changes Clara understood from the
  attributed transcript and visual context.

  Before writing that change list, build focused interpretation packets:

  ```bash
  python scripts/build_deck_revision_interpretation_packets.py <case-dir>
  ```

  This writes `deck_revision_interpretation_packets.json`,
  `deck_revision_interpretation_packets.md`, and per-packet JSON/Markdown files
  under `deck_revision_interpretation_packets/`. The workbench remains the
  evidence index; Codex/Clara should interpret the smaller packets rather than
  using the full workbench as one huge semantic prompt. If
  `feedback_timeline.json` contains `slide_match` fields, use high/medium
  matches as slide-location grounding and treat low/no matches as navigation
  hints. Each change must include a scope, Clara's interpretation of the
  requested correction, an execution strategy, success criteria, and packet
  metadata such as `packet_scope`, `affected_slide_numbers`, group id, or
  dependencies when the edit is global or cross-slide.

After Codex writes `deck_revision_changes.json`, render the consultant-facing
review and the controlled PPTX handoff:

```bash
python scripts/finalize_deck_revision_plan.py <case-dir> \
  voice_sessions/<timestamp>/deck_revision_changes.json
```

The finalizer validates slide numbers against the deck snapshot, requires
transcript and visual/deck evidence for each change, requires success criteria,
ignores any model-authored approval flag, writes
`deck_revision_changes.normalized.json`, renders the readable
`deck_revision_changes.md`, writes the simpler consultant checkpoint
`deck_revision_understanding.md`, and writes `deck_revision_handoff.md`. PPTX
editing is a separate step: Clara/Codex applies the deck only after a separate
approval artifact is written for the exact normalized plan hash.

Then build the execution route:

```bash
python scripts/build_deck_revision_execution_plan.py <case-dir>
```

  This writes `deck_revision_execution_plan.json` and
  `deck_revision_execution_plan.md`. The execution strategy is explicit per
  change: `deterministic_patch`, `model_assisted_edit`, `slide_rebuild`,
  `deck_restructure`, or `needs_human_decision`. Deterministic routing is used
  only for mechanical readiness checks from the explicit strategy; semantic
  judgement stays with Clara/Codex.

  Then build focused execution packets:

  ```bash
  python scripts/build_deck_revision_execution_packets.py <case-dir>
  ```

  This writes `deck_revision_execution_packets.json`,
  `deck_revision_execution_packets.md`, and per-packet JSON/Markdown files under
  `deck_revision_execution_packets/`. Clara/Codex should execute one packet at a
  time: a local slide packet, a related slide-cluster packet, or a deck-level
  packet for global changes such as "make the font bigger in all slides" or
  deck sequence edits. The whole change list is global context, not one giant
  deck-editing prompt.

For automatic PPTX application, a change with strategy `deterministic_patch`
must include concrete `application_patches`. Supported deterministic patches
are deliberately narrow: `set_title_text`, `set_shape_text`, `replace_text`,
`add_textbox`, `delete_shape`, and `move_shape`. Semantic, structural, visual,
or content changes still belong in the plan; route them to model-assisted edit,
slide rebuild, deck restructure, or human decision instead of forcing a fragile
patch. Existing-object patches must include target identity from the pre-edit
deck, especially `target.expected_text`, and text replacement must name a
specific target shape.

Before applying, write the material-needs review:

```bash
python scripts/analyze_deck_revision_materials.py <case-dir>
```

This writes `deck_revision_material_needs.json` and
`deck_revision_material_needs.md`, separating changes that are ready for
automatic deterministic application from changes that require Codex/model
editing, slide rebuild, deck restructuring, source material, or a human
decision.

When a change asks for better quotes, interview evidence, transcript excerpts,
or source-backed examples for a slide, build the quote candidate matrix before
selecting quotes or editing the PPTX:

```bash
python scripts/build_deck_revision_quote_candidate_matrix.py <case-dir>
```

This writes `deck_revision_quote_candidate_matrix.json` and
`deck_revision_quote_candidate_matrix.md`. The matrix is evidence preparation:
deterministic code finds candidate transcript passages, while Clara/Codex still
selects quotes by relevance, sharpness, source diversity, and room-safe wording.
`analyze_deck_revision_materials.py` flags quote-backed changes as blocked
until this matrix exists.

After the consultant/user reviews `deck_revision_changes.md`, approve the exact
normalized plan:

```bash
python scripts/approve_deck_revision_plan.py <case-dir> --reviewer "<name>"
```

This writes `deck_revision_approval.json` and `deck_revision_approval.md`. The
approval stores the SHA-256 of the normalized plan. If the plan changes after
approval, Clara must re-run approval before applying.

After approval, apply only the supported patches to a copied PPTX:

```bash
python scripts/apply_deck_revision_plan.py <case-dir>
```

The applier writes `deck_revision_corrected.pptx`,
`deck_revision_apply_report.json`, and `deck_revision_apply_report.md`; it
keeps the original deck untouched. It also runs verification automatically and
writes `deck_revision_verification.json` plus `deck_revision_verification.md`.
Verification mechanically checks supported patch assertions, such as title
text, exact text replacement, added text, moved coordinates, and explicit
absent-text checks for deletions. It also checks every normalized success
criterion where the criterion is mechanical, and marks semantic/manual criteria
for review. Failed or manual-review assertions block the deck from being
treated as correct; the apply report status is successful only when
verification also passes.

For regression tests of the full harness, create a fixture with a case folder,
voice session, change JSON, and expected statuses, then run:

```bash
python scripts/run_deck_revision_fixture.py <fixture-dir>
```

The runner executes the local harness from workbench through finalization,
execution planning, material-needs analysis, optional approval, optional apply,
and verification. It writes `deck_revision_eval_report.json` and
`deck_revision_eval_report.md`.

Deck revision requires three authorities before edits are produced:

- the case workspace, including `case_manifest.json`;
- a visual style authority, normally inherited from a firm/company profile in
  the case folder or parent company folder;
- the advisory method authority, currently `advisory-output-shaper`, so
  family/governance feedback becomes useful, evidence-aware, room-safe slide
  changes rather than raw transcript paste.

A company folder can hold `company_profile.json` or
`clara_company_profile.json` above its project folders. Supported profile
fields include `default_deck_style`, `deck_style`, `deck_style_spec_path`, and
`advisory_method`. For example, `default_deck_style: "ag"` resolves to
`docs/specs/pptx_templates/ag-style-spec.md`; `default_deck_style: "bain"`
resolves to `docs/specs/pptx_templates/bain-style-spec.md`. A project case can
override this by passing `--deck-style`, `--style-spec`, or by adding a style
field to `case_manifest.json`.

Speaker attribution is local and text-only. The hosted server transcribes
audio and may provide clean text, but it is not the authority for naming
speakers in Clara case work. Import creates and registers
`voice_sessions/<timestamp>/attributed_transcript.md` only when attribution is
actually trivial: a single known speaker. If more than one speaker is possible,
import writes `speaker_attribution_task.md` plus
`speaker_attribution_report.json` and leaves the raw transcript registered until
Clara/Codex completes attribution. If real names are unavailable, Clara/Codex
may use stable labels such as `Speaker 1` and `Speaker 2`. Codex/Clara
attributes from transcript text plus source metadata: preserve the unattributed
transcript, inspect for obvious merged turns or wrong labels, correct only clear
text-supported boundary errors, and leave uncertainty visible. Do not use an
audio or voice diarization model for Clara speaker attribution.

When Codex/Clara later creates or replaces the attributed transcript with a
reviewed one, finalize the registry mechanically instead of editing JSON by hand:

```bash
python scripts/finalize_hosted_transcript.py <case-dir> <transcript-material-id> \
  <voice_sessions/.../raw_transcript_rule_attributed.md> \
  --audio-pointer <source_materials/interviews/...-audio.md>
```

This command preserves `raw_transcript_unattributed.md`, updates the transcript
material to point at the attributed working transcript, marks the raw-audio
pointer as transcribed, links it visibly to the transcript material/path, and
refreshes `case_brief.md`.

For existing local recordings, prefer `scripts/upload_hosted_audio.py` when the
browser or Chrome extension cannot attach local files. The script can consume a
Mparanza magic link or reuse an existing authenticated `Cookie` header, uploads
the audio through the hosted API, saves the bundle under the case workspace,
imports it into `voice_sessions/`, and copies the original audio file into the
imported session folder. By default it attaches the same compact local case
context used by `launch_hosted_voice.py` before requesting the upload token; use
`--no-case-context` only for debugging a raw hosted token path. Use `--no-import`
only when you need to inspect the hosted bundle before registering it locally.

## Support Package

If Clara is not enough for delivery, the advisor should not handle CLI,
manually zip folders, or decide which hidden folders to exclude. Codex should
treat natural-language requests such as "prepare a support package" or "these
slides are not good enough" as a support escalation. The live case remains
local and authoritative; the package is only a clean diagnostic and delivery
handoff.

```bash
python scripts/prepare_support_package.py <case-dir> \
  --request "The slides are not good enough; the support reviewer should improve the output." \
  --requested-by "<advisor>"
```

The package is written by default to `../case_support_exports/`. It contains the
clean case workspace plus `support_request.md`, and excludes hidden OCR/runtime
dependency folders such as `.codex_*_py`, virtual environments, caches,
`.DS_Store`, and prior exchange exports.

## Case Exchange

For a first handoff, export a clean workspace ZIP instead of zipping the folder
manually. The clean archive keeps case files, notes, transcripts, materials, and
outputs, but excludes local runtime libraries, hidden dependency folders such as
`.codex_*_py`, virtual environments, caches, `.DS_Store`, and prior exchange
exports.

```bash
python scripts/export_case_workspace.py <case-dir>
```

For ongoing collaboration, case exchange is local-first and deterministic. One
user exports a ZIP update
package; another imports it into their own case workspace. Import appends new
materials, judgement entries, and open questions. It does not overwrite local
records. If the same imported origin has changed, the import logs an open
conflict question for manual review.

```bash
python scripts/export_case_update.py <case-dir> --exporter "<name>"
python scripts/import_case_update.py <case-dir> <case-update.zip>
```

Case-owned note and transcript files are included in the package and extracted
under `exchange_imports/`. External source paths are retained as provenance
references rather than copied. After importing new material, judgement, open
questions, or conflicts, Codex updates `advisory_evidence_map.md` before using
the imported content in a deliverable.

## Case Files

- `case_manifest.json`
- `case_brief.md`
- `clara_mandate.json`
- `clara_kickoff_preparation.md`
- `clara_kickoff_deck.html`
- `clara_partner_brief.html`
- `advisory_evidence_map.md`
- `advisory_workpaper.md`
- `judgement_checkpoint.md`
- `presentation_storyline.md`
- `presentation_review.md`
- `material_registry.json`
- `judgement_log.json`
- `open_questions.json`
- `case_issues.json`
- `exchange_log.json`
- `company_profile.json` or `clara_company_profile.json` in a case folder or
  parent company folder when project folders inherit firm defaults
- `voice_sessions/<timestamp>/raw_transcript.md`
- `voice_sessions/<timestamp>/judgement_candidates.json`
- `voice_sessions/<timestamp>/codex_discussion_review.md`
- `voice_sessions/<timestamp>/deck_revision_intake.json`
- `voice_sessions/<timestamp>/deck_revision_gate.md`
- `voice_sessions/<timestamp>/deck_style_spec.md`
- `voice_sessions/<timestamp>/deck_revision_workbench.json`
- `voice_sessions/<timestamp>/deck_revision_prompt.md`
- `voice_sessions/<timestamp>/deck_revision_changes.schema.json`
- `voice_sessions/<timestamp>/deck_revision_interpretation_packets.json`
- `voice_sessions/<timestamp>/deck_revision_interpretation_packets.md`
- `voice_sessions/<timestamp>/deck_revision_changes.json`
- `voice_sessions/<timestamp>/deck_revision_changes.md`
- `voice_sessions/<timestamp>/deck_revision_understanding.md`
- `voice_sessions/<timestamp>/deck_revision_handoff.md`
- `voice_sessions/<timestamp>/deck_revision_execution_plan.json`
- `voice_sessions/<timestamp>/deck_revision_execution_plan.md`
- `voice_sessions/<timestamp>/deck_revision_execution_packets.json`
- `voice_sessions/<timestamp>/deck_revision_execution_packets.md`
- `voice_sessions/<timestamp>/deck_revision_material_needs.json`
- `voice_sessions/<timestamp>/deck_revision_material_needs.md`
- `voice_sessions/<timestamp>/deck_revision_quote_candidate_matrix.json`
- `voice_sessions/<timestamp>/deck_revision_quote_candidate_matrix.md`
- `voice_sessions/<timestamp>/deck_revision_approval.json`
- `voice_sessions/<timestamp>/deck_revision_approval.md`
- `voice_sessions/<timestamp>/deck_revision_corrected.pptx`
- `voice_sessions/<timestamp>/deck_revision_apply_report.json`
- `voice_sessions/<timestamp>/deck_revision_apply_report.md`
- `voice_sessions/<timestamp>/deck_revision_verification.json`
- `voice_sessions/<timestamp>/deck_revision_verification.md`
- `../case_support_exports/<case-support>.zip`
- `../case_share_exports/<case-workspace>.zip`
- `exchange_exports/<case-update>.zip`
- `exchange_imports/<exchange-id>/...`
- `outputs/decision_pack.md`
- `outputs/decision_pack.docx`
- `outputs/decision_pack_workpaper.md`
- `outputs/decision_pack_workpaper.docx`

## Public Explainer

The public plugin explainer is maintained at
`static/shared/clara/index.html`.
