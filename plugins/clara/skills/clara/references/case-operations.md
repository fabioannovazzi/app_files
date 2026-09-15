# Case operations reference

Read this reference when initializing, indexing, or updating an advisory case.
Commands run from the installed Clara plugin root. The router retains scope,
workflow selection, privacy, and review responsibilities.

## First Run Workflow

1. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

This command prepares the published shared core requirements for Vera, Clara and
Lucia in one user-scoped Python 3.12 environment. It reuses that environment
across modules and restarts, updating it only when the shared recipe changes. Run subsequent core helper commands through:

```bash
python scripts/managed_python_runtime.py run scripts/<helper>.py <arguments>
```

For a delegated component, use `python scripts/managed_python_runtime.py
--module <component> run scripts/<helper>.py <arguments>` to validate that component using the same shared environment. These managed forms supersede the shorter
standalone `python scripts/...` examples below. Do not run `pip install`
directly.

Whenever the user supplies a PDF, image, or folder that may contain either,
run the input-aware preflight:

```bash
python scripts/check_dependencies.py --input <file-or-folder>
```

The preflight mechanically distinguishes usable native PDF text from visual-only
pages. If it reports `OCR_SETUP_REQUIRED`, ask only:

> PaddleOCR is required to read this document. Shall Codex install it now? The
> download is about 500 MB.

Do not ask the user to run pip, Python, Terminal, or any technical installation
step. Wait for explicit approval. When approved, Codex must run the managed
one-time setup itself:

```bash
python scripts/managed_ocr_runtime.py install
```

After a successful setup, say `PaddleOCR is ready. Retrying the document now.`
and automatically rerun the input preflight and the interrupted PDF operation.
The runtime is persistent and shared with Vera; when the preflight finds it
ready, reuse it without prompting. If setup fails, show only `I couldn't install
PaddleOCR right now. Shall I try the installation again?` unless the user asks
for technical details. Never treat image-only evidence as read when setup is
declined or unsuccessful.

2. Initialize the case workspace when the four case files do not exist:

```bash
python scripts/init_case.py <case-dir> \
  --client "<client>" \
  --project "<project>" \
  --objective "<objective>" \
  --audience "<audience>" \
  --language it
```

3. Index existing materials without copying them:

```bash
python scripts/index_materials.py <case-dir> <file-or-folder> [...]
```

Supported source previews include Markdown/text, Word documents, PDFs as
registered references, and PowerPoint decks.

After indexing or importing any new material that could affect a decision,
return the bounded analysis to the case director before revising the advisory
workpaper, storyline, deck, memo, or decision pack. The common envelope carries
the evidence receipts, claims, judgement projections, answer effect, and
question changes that Clara actually uses:

```bash
python scripts/record_case_direction_return.py \
  <case-dir> <model-authored-case-direction-return.json>
python scripts/advisory_evidence_lineage.py validate <case-dir>
```

The model authors the question and answer, observations, support relationships,
what evidence proves and does not prove, dependencies, reasoning, uncertainty,
decision use, answer effect, question changes, and any judgement-log wording.
The return helper validates and commits the declared hand-off atomically; if
any binding fails it restores the prior registers and case files. Specialist
adapters may record their own authoritative claims first and reference those
claim IDs in the return. Use `record_analysis_contribution.py` and the lower-
level `add-evidence` and `add-claims` commands only for repair, migration, or a
specialist adapter where no case-direction return is being completed.
When a claim enters a final output, have the model declare its claim ID and
locator, then let the helper compute the output receipt:

```bash
python scripts/advisory_evidence_lineage.py bind-output \
  <case-dir> <completed-output> <model-authored-claim-locations.json>
```

`claim-locations.json` uses `{"appearances": [{"claim_id": "...",
"locator": "..."}]}`. The helper computes the exact path, SHA-256, byte count,
and timestamp; the model remains responsible for the semantic location. Use
`link-appearances` only to import an already complete receipt. Use
`capture_advisory_web_evidence.py` for an explicitly selected public page; do
not turn every URL into an automatic fetch.

After the contribution is committed, stage the model-authored workpaper outside
the canonical path and commit it against the model-selected current claims:

```bash
python scripts/commit_advisory_workpaper.py \
  <case-dir> <staged-advisory-workpaper.md> \
  --claim-id <claim-id> [--claim-id <claim-id> ...] \
  --change-summary "<what changed in the case direction>"
```

This writes `advisory_workpaper_checkpoint.json` and preserves a changed prior
workpaper under `history/`. It validates declared mechanics only; the model
remains responsible for the prose, the selected claim IDs, and completeness.

When a downloaded or local file must first be made durable inside the case
workspace, use the copy helper before indexing or handoff:

```bash
python scripts/add_case_file.py <case-dir> <downloaded-file>
python scripts/add_case_file.py <case-dir> <downloaded-file> --register
python scripts/add_case_file.py <case-dir> <downloaded-file> --kind deck
python scripts/add_case_file.py <case-dir> <downloaded-file> --kind audio
```

The helper routes audio files to `source_materials/interviews/audio/`, notes to
`notes/`, presentation drafts to `outputs/presentations/current/`, and ordinary
source documents to `source_materials/project_docs/`. It preserves the original
filename, reuses an identical existing copy, and avoids overwriting a different
file by adding a numeric suffix. Use `--register` only when the copied file
should be recorded in `material_registry.json`; registration refreshes
`case_brief.md`. If the registered material could affect a decision, update
the structured evidence and claim registers and rerender
`advisory_evidence_map.md` before relying on it in any workpaper, storyline,
deck, memo, or decision pack.

For `.pptx` presentation drafts, `add_case_file.py` automatically inspects
`ppt/media/` for `.wmf` and `.emf` parts. When legacy media are found, it also
creates a sibling `<name>_normalized_for_merge.pptx` plus a
`.normalization_report.json`; use that normalized file as the base for editable
slide merging. Use `--skip-legacy-pptx-normalization` only when the deck is
being archived or copied without any future editable merge.

When Clara must normalize an older PPTX already in the case folder or outside
the `add_case_file.py` flow, run:

```bash
python scripts/normalize_legacy_pptx.py <source.pptx>
python scripts/normalize_legacy_pptx.py <source.pptx> \
  --output <source_normalized_for_merge.pptx> --overwrite
```

The normalizer round-trips only legacy-heavy or `--force` decks through
LibreOffice, preserves Clara custom document properties such as transcript
links, validates the output PPTX, and writes a `.normalization_report.json`. If
the report still lists legacy media after normalization, avoid fragile editable
merging for those affected slides and use an image fallback only for the
affected slide content.

Before any Clara editable PPTX merge, run the merge-input guard:

```bash
python scripts/prepare_editable_pptx_merge_input.py <source.pptx>
python scripts/prepare_editable_pptx_merge_input.py <source.pptx> \
  --normalized-pptx <source_normalized_for_merge.pptx>
```

The guard writes an `.editable_merge_input_report.json` and returns the PPTX
base that merge code may use. It fails when a legacy WMF/EMF source has no
normalized merge base. If normalization is deliberately skipped because the
operation is image-only or otherwise safe, pass
`--skip-normalization-reason "<specific reason>"`; never bypass the guard
silently.

3a. When the user wants Clara to begin the engagement, prepare the first partner
kickoff before launching voice. Clara has read the case material summaries, the
controlled succession playbook, and any concise industry or external research
notes Codex supplies. The helper itself does not browse or make model calls:

```bash
python scripts/prepare_clara_kickoff.py <case-dir>
python scripts/prepare_clara_kickoff.py <case-dir> \
  --industry-context-json <industry-notes.json> \
  --external-research-json <source-takeaways.json>
```

Use public or authorized external sources only. Store source links and concise
takeaways; do not copy proprietary case material into the playbook or case
workspace. The kickoff posture is: the senior partner briefs Clara; Clara
listens and asks only essential clarifications when a missing point blocks
understanding.

4. Ingest pasted consultant notes when provided:

```bash
python scripts/ingest_notes.py <case-dir> --title "<note-title>" --text "<pasted notes>"
```

Each pasted-note invocation is a distinct capture, including an identical
replay. The helper preserves the supplied capture timestamp and allocates a
new immutable source path and material identity; it does not deduplicate by
title, timestamp or text. To refer to an existing capture, reuse its material
ID rather than ingesting it again. Interrupted registration is recovered under
the case transaction before the next case operation.

For existing note files, use `--notes-file`; the plugin copies the file under
the case workspace `notes/` folder before registering it, so temporary download
or extraction paths do not become brittle provenance records.

Optional hosted voice capture: when the user wants a spoken debrief and should
not manage an OpenAI API key locally, launch the hosted voice service from the
plugin. Mparanza handles authentication, short-lived launch and job state, and
voice processing through its configured transcription provider. The browser
downloads a local bundle, and the plugin imports that bundle into the local case
workspace; advisory interpretation remains Codex work through the user's
ChatGPT plan.
With an authenticated cookie or magic link, the launcher sends compact context
from `case_brief.md` in an HTTPS request body. The server stores it in
short-lived metadata and returns an opaque token, so case context never appears
in the launch URL. The token is bound to the authenticated user and does not
replace the Mparanza session. Without supplied authentication material, the
launcher uses an explicit browser-authenticated fallback without reading or
attaching the case brief.

Voice Capture is transcription-first. The hosted page records live screen video
plus automatically captured audio, or uploads an existing recording. Treat
attribution, challenge, and semantic review as post-import Codex work over the
locally stored transcript and any captured video provenance.
When the shared surface is a cooperating Clara HTML deck, the downloaded bundle
must also contain `active_slide_timeline` events on the capture-relative clock,
and each timed transcript segment should carry the active slide ID/title. Inspect
that metadata before manually matching screen-video frames. An empty timeline is
an explicit browser/surface limitation; use the recorded video as the fallback
and do not infer a slide identity from transcript wording alone.
When Codex imports a voice bundle and the importer emits a speaker attribution
task, Codex must complete that task in the same workflow before using the
transcript for advisory or deck-revision work. Do not hand this back to the
user as a manual step unless the transcript is genuinely ambiguous after Codex
has inspected the text and metadata.

```bash
python scripts/launch_hosted_voice.py <case-dir>
python scripts/launch_hosted_voice.py <case-dir> --browser chrome
python scripts/launch_hosted_voice.py <case-dir> --cookie-header-file /tmp/mparanza.cookie
python scripts/start_deck_feedback.py <case-dir> --deck <existing-deck> --browser chrome \
  --cookie-header-file /tmp/mparanza.cookie
python scripts/upload_hosted_audio.py <case-dir> <audio-file> --magic-link-file /tmp/mparanza.magic-link
python scripts/upload_hosted_audio.py <case-dir> <audio-file> --cookie-header-file /tmp/mparanza.cookie
python scripts/import_latest_hosted_voice_bundle.py <case-dir>
python scripts/import_hosted_voice_bundle.py <case-dir> <downloaded-bundle.zip>
```

Ordinary-folder import exception: when the user only asks to preserve a hosted
voice transcript in a normal document folder and that folder has no
`case_manifest.json`, do not initialize a case workspace merely to run the
case importer. Use the lightweight importer:

```bash
python scripts/import_hosted_voice_bundle_to_folder.py \
  <target-folder> <downloaded-bundle.zip>
```

It copies or adopts the source ZIP/JSON, writes or adopts a readable sibling
transcript, and records relative artifact paths plus bundle, payload,
transcript, and media fingerprints in `.clara/voice_imports.json`. Exact or
repackaged duplicates must reuse the existing artifacts; an existing manual
transcript containing the complete source text must be adopted without being
rewritten. Missing transcripts may be repaired. Never overwrite or delete an
ordinary-folder document. Use suffixes for unrelated filename collisions, and
require `--allow-variant` for a conflicting version of the same recording.
This helper does not create case JSON, register judgement, or promote the
transcript into advisory evidence. If the target has `case_manifest.json`, use
the normal case importer instead. Speaker attribution remains a separate local
Codex/Clara text pass that preserves the unattributed source transcript.

Use `import_latest_hosted_voice_bundle.py` as the normal path after a hosted
capture. It looks in the browser's default `~/Downloads` folder for the newest
valid `case-notes-voice-*.zip`, `case-notes-audio-*.zip`, or older loose JSON
bundle, skips bundles whose timestamped `voice_sessions/` folder already
exists, and then calls the explicit importer. Use
`import_hosted_voice_bundle.py` only when the advisor or Codex needs to point at
a specific bundle file.

The hosted voice page also accepts uploaded audio files for recordings that
already exist. Use it when the consultant has a voice note, meeting recording,
or call recording instead of a live debrief. The server transcribes the uploaded
audio, then the browser downloads the same local bundle shape used by live
voice. Import that bundle with `import_latest_hosted_voice_bundle.py`
unless you need to point at a specific file. The browser downloads a ZIP whose
contents include the transcript JSON plus the audio file. The importer copies
the audio into the same local `voice_sessions/<timestamp>/` folder as the
transcript. For older loose JSON downloads, the importer also copies a
companion audio file when the JSON names it and the file sits next to the JSON
bundle. The transcript is registered locally as source material, and the local
`clara_review.md` created during import is the workspace for Codex/Clara's
semantic review.

When the imported voice session includes screen video and may be used to revise
an existing deck, prepare the deck-revision intake before editing slides:

```bash
python scripts/prepare_voice_deck_revision.py <case-dir>
python scripts/prepare_voice_deck_revision.py <case-dir> \
  --deck <current-deck.pptx> --deck-style ag
python scripts/prepare_voice_deck_revision.py <case-dir> \
  --deck <current-deck.pptx> --company-profile <company_profile.json>
```

The intake is still deterministic. It does not decide what the partner meant
and does not edit the PPTX. It resolves the inherited company/deck style
authority, snapshots the selected style spec into
`voice_sessions/<timestamp>/deck_style_spec.md`, extracts the deck text/object
snapshot when a PPTX is attached, enriches feedback timeline frames with
conservative slide-match candidates when rendered slide images and extracted
video frames are available, and writes `deck_revision_gate.md`. Slide matching
is visual candidate evidence only; Clara/Codex still decides what the speaker
meant.

Do not implement semantic understanding of deck corrections as deterministic
code. No keyword rule, slide-number heuristic, visual matcher, or schema helper
is allowed to decide what the partner meant. Deterministic scripts may prepare
evidence, validate schemas, route execution strategies, apply concrete approved
patches, and verify mechanical criteria. The meaning of the requested change is
always Codex/Clara reasoning work using the attributed transcript, video/deck
context, case materials, style authority, and advisory-output-shaper behavior.

When the intake has an attributed transcript, attached PPTX, and resolved style
authority, build the local workbench before producing edit instructions:

```bash
python scripts/build_deck_revision_workbench.py <case-dir>
```

This writes `deck_revision_workbench.json`, `deck_revision_prompt.md`,
`deck_revision_changes.schema.json`, and an initial `deck_revision_changes.md`
review stub. The workbench is the evidence package and prompt contract for the
Codex/model semantic pass. It still does not call a model and does not edit the
PPTX.

Before Codex/model writes the final change list, build focused interpretation
packets:

```bash
python scripts/build_deck_revision_interpretation_packets.py <case-dir>
```

This writes `deck_revision_interpretation_packets.json`,
`deck_revision_interpretation_packets.md`, and per-packet JSON/Markdown files
under `deck_revision_interpretation_packets/`. The packet builder is
deterministic evidence routing only: it groups available feedback timeline,
slide-match, deck snapshot, and deck outline evidence into smaller slide or
deck/general inputs. It does not decide what the partner meant.

Codex/model then processes the packets, not the full workbench as one huge
semantic prompt, and writes
`voice_sessions/<timestamp>/deck_revision_changes.json` from the packet-level
interpretations plus the resolved style/advisory authorities. If
`feedback_timeline.json` contains `slide_match` fields, use high/medium matches
as slide-location grounding and treat low/no matches as navigation hints. This
is a semantic Codex/Clara interpretation step, not a deterministic
transformation. Every change must carry the requested change, Clara's
interpretation, scope, execution strategy, success criteria, and execution
packet metadata when useful: `packet_scope`, `affected_slide_numbers`,
`execution_group_id`, and `dependency_change_ids`. Use `packet_scope: "deck"`
for global changes such as all-slide font changes, deck sequence changes, or
slide insertions/deletions. After that, render and validate the
consultant-readable review:

```bash
python scripts/finalize_deck_revision_plan.py <case-dir> \
  voice_sessions/<timestamp>/deck_revision_changes.json
```

The finalizer validates slide numbers against the deck snapshot, requires both
transcript evidence and visual/deck evidence for each change, requires success
criteria, ignores any model-authored approval flag, writes
`deck_revision_changes.normalized.json`, renders `deck_revision_changes.md`,
writes the consultant checkpoint `deck_revision_understanding.md`, and writes
`deck_revision_handoff.md`. Do not edit the PPTX merely because the plan
exists. PPTX editing starts only after a separate approval artifact is written
for the exact normalized plan hash.

Next build the execution route:

```bash
python scripts/build_deck_revision_execution_plan.py <case-dir>
```

This writes `deck_revision_execution_plan.json` and
`deck_revision_execution_plan.md`. The execution strategy is explicit per
change: `deterministic_patch`, `model_assisted_edit`, `slide_rebuild`,
`deck_restructure`, or `needs_human_decision`. Use deterministic routing only
for mechanical readiness checks from that explicit strategy; do not use rules
to infer semantic meaning.

Then build focused execution packets:

```bash
python scripts/build_deck_revision_execution_packets.py <case-dir>
```

This writes `deck_revision_execution_packets.json`,
`deck_revision_execution_packets.md`, and per-packet JSON/Markdown files under
`deck_revision_execution_packets/`. Clara/Codex must execute one packet at a
time. A packet is one local slide, a related slide cluster, or a deck-level
change such as "make fonts bigger in all slides" or "move slide 5 after slide
8 and add a new slide after slide 4." Use the whole change list only as global
context and dependency awareness; do not feed all changes into one deck-editing
prompt. If a deck-level packet changes slide count or order, refresh slide
references before executing later slide-local packets.

Automatic PPTX application requires concrete `application_patches` when a
change's strategy is `deterministic_patch`. Supported deterministic patches are
intentionally narrow: `set_title_text`, `set_shape_text`, `replace_text`,
`add_textbox`, `delete_shape`, and `move_shape`. If a change needs judgement,
source material, replacement wording, visual redesign, structure changes, or an
unsupported operation, keep it in the plan and route it to model-assisted edit,
slide rebuild, deck restructure, or human decision instead of guessing.
Existing-object patches must include target identity from the pre-edit deck,
especially `target.expected_text`, and text replacement must name a specific
target shape.

Before applying a plan, run the material-needs analysis:

```bash
python scripts/analyze_deck_revision_materials.py <case-dir>
```

This writes `deck_revision_material_needs.json` and
`deck_revision_material_needs.md`, separating changes ready for automatic
deterministic application from changes that still need Codex/model editing,
slide rebuild, deck restructuring, concrete targets, replacement text, source
material, or a human decision.

When a change asks for better quotes, interview evidence, transcript excerpts,
or source-backed examples for a slide, build the quote candidate matrix before
selecting quotes or editing the PPTX:

```bash
python scripts/build_deck_revision_quote_candidate_matrix.py <case-dir>
```

This writes `deck_revision_quote_candidate_matrix.json` and
`deck_revision_quote_candidate_matrix.md`. The matrix is evidence preparation,
not semantic judgement: deterministic code finds candidate transcript passages,
then Clara/Codex reviews them for relevance, sharpness, source diversity, and
room-safe wording before choosing what goes on the slide. The material-needs
analysis must flag quote-backed changes as blocked until this matrix exists.

After consultant/user review of `deck_revision_understanding.md`, approve the
exact normalized plan:

```bash
python scripts/approve_deck_revision_plan.py <case-dir> \
  --reviewer "<name>" --understanding-reviewed
```

This writes `deck_revision_approval.json` and `deck_revision_approval.md`. The
approval stores the SHA-256 of the normalized plan and the SHA-256 of
`deck_revision_understanding.md`. Do not pass `--understanding-reviewed` until
the consultant/user-facing understanding has been shown in chat or otherwise
reviewed. If either the plan or the understanding changes after approval, Clara
must re-run approval before applying.

After approval, apply only supported patches to a copied PPTX:

```bash
python scripts/apply_deck_revision_plan.py <case-dir>
```

The applier writes `deck_revision_corrected.pptx`,
`deck_revision_apply_report.json`, and `deck_revision_apply_report.md`; it
keeps the original deck untouched. It also runs
`verify_deck_revision_output.py` automatically and writes
`deck_revision_verification.json` plus `deck_revision_verification.md`.
Verification mechanically checks supported patch assertions such as title text,
exact text replacement, added text, moved coordinates, and explicit absent-text
checks for deletions. It also checks every mechanical success criterion and
marks semantic/manual criteria for review. Failed or manual-review assertions
block the corrected deck from being treated as complete; the apply report
status is not final merely because verification passes.

After applying, Clara must run a final output review loop before delivery. The
applier writes `deck_revision_output_review.json` and
`deck_revision_output_review.md` with the rendered-deck review checklist. Codex
must render and inspect the corrected deck, read slide titles and visible copy
as audience-facing material, and catch internal instructions, workpaper
language, prompt/construction language, stale artifacts, wrong footers,
clipping, overlap, or semantic drift. If any issue is found, revise the deck,
rerender, rerun verification, and repeat the loop. Only after the deck passes
this review may Codex complete it:

```bash
python scripts/complete_deck_revision_output_review.py <case-dir> \
  --reviewer "<name>" \
  --audience-copy-reviewed \
  --process-language-reviewed \
  --requested-structure-reviewed \
  --semantic-evidence-fit-reviewed \
  --visual-render-reviewed
```

Do not present the corrected PPTX as final until
`deck_revision_output_review_completion.json` exists for the exact reviewed
output. This loop is where Clara catches mistakes such as slide titles that
describe the editing instruction instead of saying something useful to the
meeting audience.

For regression tests of this harness, use:

```bash
python scripts/run_deck_revision_fixture.py <fixture-dir>
```

The fixture runner executes workbench, finalization, execution planning,
material-needs analysis, optional approval, optional apply, and verification,
then writes `deck_revision_eval_report.json` and
`deck_revision_eval_report.md`.

Do not produce deck edit instructions, add slides, rebuild slides, or modify a
PPTX until the intake has all three authorities:

- case context: the existing case workspace and its `case_manifest.json`;
- visual authority: a resolved deck style spec from explicit arguments, the
  parent company profile, the case folder profile, or case manifest fields such
  as `deck_style`;
- advisory-method authority: `advisory-output-shaper` behavior for
  evidence-aware, room-safe wording in family/governance advisory work.

A firm/company profile belongs above project folders when multiple cases inherit
the same way of working. For example, a company folder can contain
`company_profile.json` with `default_deck_style: "ag"`, and each project case
folder below it inherits the A&G PPTX style unless the case explicitly
overrides it. Style specs such as `docs/specs/pptx_templates/ag-style-spec.md`
are visual authorities; they are not interchangeable with the advisory-output
shaping method.

After any uploaded-audio transcription is imported, Clara must perform a
post-import Codex transcript-processing pass before using it as advisory evidence:
assign speaker attribution from the clean transcript plus source metadata,
check the document-level transcript quality, and correct only obviously wrong
transcription words when the intended wording is clear from transcript context
or a trusted case glossary. Preserve uncertainty instead of guessing; do not
rewrite, summarize, or change meaning during this pass.

Speaker attribution is a text-only Codex/Clara loop after local import. The
transcript Codex reads may enter model context through the user's existing
ChatGPT plan. The hosted server
transcribes audio; it must not be treated as the speaker-naming authority for
Clara case work. Import creates and registers
`voice_sessions/<timestamp>/attributed_transcript.md` only when attribution is
actually trivial: a single known speaker. If more than one speaker is possible,
import writes `speaker_attribution_task.md` plus
`speaker_attribution_report.json`; that is not a stopping point for Codex. In
the same Codex/Clara workflow, Codex must read the task, raw transcript,
available call metadata, and any useful notes, then write
`voice_sessions/<timestamp>/attributed_transcript.md` itself. If real names are
unavailable, Codex may use stable labels such as `Speaker 1` and `Speaker 2`.
Preserve the original unattributed transcript, inspect the attributed
transcript for obvious merged turns or wrong labels, apply only clear
text-supported boundary corrections, and keep uncertainty visible with
confidence notes. Do not use an audio or voice diarization model for Clara
speaker attribution.

When Codex/Clara later creates or replaces the attributed transcript with a
reviewed one, finalize the registry with the deterministic helper instead of
hand-editing `material_registry.json`:

```bash
python scripts/finalize_hosted_transcript.py <case-dir> <transcript-material-id> \
  <voice_sessions/.../raw_transcript_rule_attributed.md> \
  --audio-pointer <source_materials/interviews/...-audio.md>
```

For hosted voice imports, the normal attributed transcript path is
`voice_sessions/<timestamp>/attributed_transcript.md`, and the material id is
printed by `import_hosted_voice_bundle.py` or recorded in
`codex_discussion_review.md`. The helper preserves
`raw_transcript_unattributed.md`, updates the transcript material to the
attributed working transcript, marks any raw-audio pointer as transcribed,
links it visibly to the transcript material/path, and refreshes
`case_brief.md`. It also records a hash-bound `interview_transcript` evidence
receipt automatically. That receipt proves the attributed transcript bytes and
speaker wording, not the truth of an underlying assertion.

When the reviewed transcript also requires judgement, question, and issue
integration, prefer the deterministic integration helper over a temporary
one-off script:

```bash
python scripts/integrate_transcript_review.py <case-dir> \
  --plan-json <integration-plan.json>
```

Codex must still inspect the transcript text and draft the semantic plan. The
plan carries `evidence_receipts`, `claims`, and judgement entries together. The
helper applies that auditable plan atomically with material registry metadata,
review-note section fills, existing open-question links, claim-linked
case-issue synthesis, `case_brief.md` refresh, and a validation/evidence-chain
summary. Do not use it to promote entries to
decision-pack-ready unless the advisor has explicitly made the inclusion
decision under the normal Clara rules.

When browser file upload is blocked or the audio is large, use
`scripts/upload_hosted_audio.py` instead of driving the page file chooser. The
script consumes a Mparanza magic link or reuses an existing authenticated
`Cookie` header, uploads the existing local audio file to the hosted API, stores
the returned bundle under the case workspace, imports it into `voice_sessions/`,
and copies the original audio file into the imported session folder. It sends
compact local case context in the authenticated upload body, so server-side
transcription is anchored to the workspace without placing context in a URL.
Use `--no-case-context` only when the hosted transcription should not receive
that context.
Use `--no-import` only when the hosted bundle needs inspection before local
registration.

The launcher and hosted-audio uploader cap body-supplied case context. Use a
smaller context budget such as `--max-context-chars 1800` only when the normal
compact context is still broader than useful for the transcription.

Use `--browser chrome` for local microphone capture when the embedded Codex
browser or a stale site permission blocks the microphone. It opens Voice Capture
in a dedicated Chrome profile with first-run screens disabled and the local
microphone prompt accepted for that session.

The imported transcript is registered as a `transcript` material. Extracted
judgement entries are added to `judgement_log.json` as `pending`; they must be
marked ready for client-pack use before they can feed the decision pack. Import
also creates `voice_sessions/<timestamp>/codex_discussion_review.md`. Use the local review
pack when Codex should perform the second-pass advisory review of the full
discussion: weak assumptions, contradictions, missed questions, and proposed
local Clara entries. Before any imported transcript changes the deck, memo, or
decision pack, create the transcript receipt and linked quote/assertion claims,
then rerender `advisory_evidence_map.md`. Direct access to
the hosted voice URL without a plugin-created launch token and authenticated
Mparanza session is not a valid run.

When the workspace needs a first local partner-facing HTML brief, build it
explicitly:

```bash
python scripts/build_clara_kickoff_deck.py <case-dir>
python scripts/build_clara_partner_brief.py <case-dir>
```

These HTML files are working artifacts for the senior partner, not client
outputs. They should summarize initial hypotheses, evidence gaps, open
questions, and what Clara needs from the partner next.

5. Codex reads the source material and drafts the first bounded case-direction
   return: structured evidence, active result claims, their judgement-log
   projections, the answer effect, and the resulting questions. Store entries
   as pending by default, but bind each one to its canonical
   `advisory_claim_id` and linked evidence receipt IDs:

```bash
python scripts/record_case_direction_return.py \
  <case-dir> <model-authored-case-direction-return.json>
```

`add_judgement.py` remains a low-level repair tool. It cannot make an unbound
entry decision-pack-ready. Approval of a pending legacy entry is blocked until
the model authors and records its evidence and claim binding.

When Codex drafts targeted follow-up questions separately from judgement
entries, store them with the same auditable JSON pattern:

```bash
python scripts/add_open_questions.py <case-dir> \
  --questions-json <questions.json>
```

The questions JSON may be a list or an object with a `questions` list. Each item
uses `question`, `why_it_matters`, optional `source_entry_ids`, and optional
`status`.

Judgement entry kinds are:

- `fact`
- `advisor_judgement`
- `codex_inference`
- `open_question`
- `decision_implication`

6. When a case has multiple interviews or source rounds, maintain live
cross-interview issues. Use issues only for questions that matter to the client
decision; do not turn every judgement entry into an issue. Each issue should
name the decision area, current synthesis, supporting and contradicting
advisory claim IDs, related judgement IDs, and open-test question IDs:

```bash
python scripts/upsert_case_issues.py <case-dir> --issues-json <issues.json>
python scripts/upsert_case_issues.py <case-dir> \
  --id production_quality_transition \
  --title "Production and quality transition" \
  --decision-area "Operating transition" \
  --current-synthesis "Quality ownership is unresolved." \
  --claim-for cl-quality-001 \
  --evidence-for jud-0017 \
  --open-test q-0012
```

7. For a solo advisor, do not frame this as "approval." The advisor is deciding
which Codex-structured statements are ready to rely on in the client pack. An
entry can be included only when it is already bound to an active canonical
claim whose statement matches and whose evidence IDs are declared on that
claim. First
build the deterministic inclusion checklist and show its pending entries in
chat. The checklist is read-only and does not change judgement status:

```bash
python scripts/build_inclusion_review.py <case-dir>
```

When the pending list is long, Codex/Clara should group entries into
advisor-readable inclusion bundles before showing the checklist. Bundle themes
are semantic judgement: Codex/Clara chooses labels such as decision area,
interview, delegation topic, or scenario from the case evidence; deterministic
code must not infer those themes from keywords. Apply the reviewed bundle plan
mechanically, then rebuild the checklist:

```bash
python scripts/apply_inclusion_bundles.py <case-dir> \
  --bundles-json <inclusion-bundles.json>
python scripts/build_inclusion_review.py <case-dir>
```

The bundle JSON may be a list or an object with `bundles`. Each bundle has
`title`, optional `id`, optional `description`, and `entry_ids`. The helper
writes `inclusion_bundles.json`, validates entry IDs, and rejects duplicate
entry assignments. It does not change judgement status.

The advisor can say "include all", "exclude item 7", "correct item 4", or
"include bundle 2", "exclude bundle deleghe", or "show me more on item 3." Do
not show the advisor CLI commands as the normal workflow. Codex records the
inclusion decision mechanically after confirmation:

```bash
python scripts/approve_judgements.py <case-dir>
```

If the advisor confirms all candidate entries shown in the summary:

```bash
python scripts/approve_judgements.py <case-dir> \
  --all-pending \
  --recorded-by "<advisor>"
```

If only one numbered item from the summary is included, excluded, corrected, or
needs expansion:

```bash
python scripts/approve_judgements.py <case-dir> --item <number> \
  --include \
  --recorded-by "<advisor>"
```

If one thematic bundle from the summary is included or excluded:

```bash
python scripts/approve_judgements.py <case-dir> --bundle <number-or-id> \
  --include \
  --recorded-by "<advisor>"
```

8. When Clara is not enough and the user wants another person or tool to help,
treat this as a support escalation, not collaboration. The advisor should not
use CLI, choose JSON files, or manage hidden OCR/runtime folders. If the
problem is unclear, ask only for the missing support request, such as "what
should the support reviewer fix or produce?" Then prepare a clean local
package:

```bash
python scripts/prepare_support_package.py <case-dir> \
  --request "<what is not working or what the support reviewer should produce>" \
  --requested-by "<advisor>"
```

Natural-language triggers include "prepare a support package", "Clara is not
enough", "these slides are not good enough", and "send the case for support".
The package contains a clean case workspace plus `support_request.md`; it
excludes `.codex_*_py`, hidden OCR/runtime dependency folders, virtual
environments, caches, macOS metadata, and prior exchange exports. Report one
clear package path in chat and explain that the local case folder remains
authoritative.

9. When another local user needs the whole case folder, export a clean
workspace ZIP rather than zipping the folder manually. This excludes local
runtime libraries, hidden dependency folders such as `.codex_*_py`, virtual
environments, caches, `.DS_Store`, and prior exchange exports while keeping case
files, notes, transcripts, materials, and outputs:

```bash
python scripts/export_case_workspace.py <case-dir>
```

For ongoing collaboration between separate local workspaces, export an
append-only case update package. When receiving one, import it into the local
workspace:

```bash
python scripts/export_case_update.py <case-dir> --exporter "<name>"
python scripts/import_case_update.py <case-dir> <case-update.zip>
```

The import is deterministic: it appends new records, maps imported source IDs
to local IDs, extracts packaged case-owned files under `exchange_imports/`, and
does not overwrite local records. If an already imported record arrives with
changed fields, the script logs an open conflict question for manual review.
Do not use Codex to merge conflicting judgement silently. After importing new
materials, judgement, open questions, or conflicts, update the structured
evidence and claim registers and rerender `advisory_evidence_map.md` before
relying on the imported content in a deliverable.

10. Refresh the derived working brief when the case files were edited manually or
when the user asks "where are we?":

```bash
python scripts/build_case_brief.py <case-dir>
```

Validate the canonical case JSON files directly when checking workspace health
without changing derived artifacts:

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

When a material import or registration was wrong, remove it with the
deterministic deletion helper instead of hand-editing `material_registry.json`:

```bash
python scripts/delete_material.py <case-dir> mat-0055 mat-0056
python scripts/delete_material.py <case-dir> mat-0055 --ignore-missing
python scripts/delete_material.py <case-dir> mat-0055 --remove-empty-orphan-dirs
```

The helper removes material records, scrubs canonical material references from
`judgement_log.json` and `clara_mandate.json`, refreshes `case_brief.md`,
validates the workspace, and reports orphan candidate paths. It never deletes
files or non-empty folders; `--remove-empty-orphan-dirs` only removes empty
case-owned directories.

The helper scripts refresh `case_brief.md` automatically after normal
mutations. The brief is not the source of truth; it is a readable view over the
case JSON files. Pending items may be visible there only under pending review,
not as decision-pack-ready understanding.

11. Build the decision pack:

```bash
python scripts/build_decision_pack.py <case-dir>
```

This produces a clean client/advisor narrative in `decision_pack.md` and
`decision_pack.docx`, plus provenance workpapers in
`decision_pack_workpaper.md` and `decision_pack_workpaper.docx`. Before final
delivery, read `decision_pack.md` and verify that pending/rejected judgement,
local filesystem paths, and internal workpaper mechanics are not present.


The executive lead must be authored from the current case answer, including
material contradictions and decision consequences. Do not select it from the
first register entries. After committing the current advisory workpaper, stage
JSON with `review.status` (`model_reviewed` or `human_reviewed`),
`review.reviewed_by`, and a nonempty `paragraphs` array. Each paragraph contains
`text` and the approved `claim_ids` that support it. Review meaning, completeness,
and uncertainty before recording the review; the script only checks identities
and declared references.

```bash
python scripts/commit_decision_narrative.py <case-dir> <staged-narrative.json>
python scripts/build_decision_pack.py <case-dir>
```

Markdown and Word use these same paragraphs. Changed workpaper or evidence/claim
identity requires a refreshed narrative. Without it the factual exports remain
available, but `decision_pack_readiness.json` reports
`missing_reviewed_narrative`. With current prose it reports
`requires_final_deliverable_review`; neither state authorizes delivery. Run the
advisory deliverable validator and inspect both formats before presenting a
finished pack. The receipt binds the current output bytes; it does not evaluate
the recommendation or establish HTML/deck readiness.

Before final review or reuse, run
`python scripts/verify_decision_pack.py <case-dir> <output-dir>` to recheck the
workpaper, registers, narrative, and all four output hashes. A saved receipt
alone is historical evidence. This check rejects changed inputs or outputs and
still requires semantic and visual review.

After individual semantic reviews, run `verify_advisory_delivery.py` for each
final Markdown/Word artifact and its validator audit. This shares the HTML
current-case contract. Markdown needs no browser check; Word requires the
recorded visual review described in the advisory deliverable validator skill.
