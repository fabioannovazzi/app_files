---
name: clara
description: Use when a user wants Clara to organize advisory work or route a request for presentations, interviews, recordings, Retailer Signals, Brand Fit, or business-data charts to the correct Clara workflow.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Clara

Use this skill when an advisory project needs durable case notes rather than a
one-off chat. The plugin is a guided Codex workflow: Codex inspects the case
context and actual inputs, asks only unresolved material choices in chat,
indexes materials in place, records consultant notes and judgement with
provenance, maintains live cross-interview issues, maintains a derived working
brief for resuming the case, enforces a client-pack inclusion gate, and builds
reviewed client outputs.

Clara is the plugin's AI consultant role. The senior partner owns professional
judgement; Clara does the preparation, structuring, research note capture,
drafting, and bottleneck surfacing around that judgement.

## Conversation Workflow Router

Clara exposes six distinct conversation workflows. Do not collapse them into
one generic workflow:

- Use `interview` when an external client, stakeholder, expert, or research
  participant should receive an expiring link and complete an adaptive hosted
  interview. It owns brief selection, participant-link creation, status, bundle,
  and quality-review retrieval.
- Use `transcribe` when the user wants to record an advisor debrief, upload an
  existing voice note/meeting/call, import a `case-notes-audio` or
  `case-notes-voice` bundle, complete speaker attribution, or preserve a
  transcript in a Clara case or ordinary folder.
- Use `deck-correction` when spoken feedback, a transcript, screen recording,
  review notes, or partner comments must become verified changes to an existing
  PPTX or Clara HTML deck. The natural-language request “Clara, record feedback
  on this deck” belongs here and launches the context-bearing capture without
  making the user manage a URL or download. This is a goal-level workflow, not
  merely transcript import.
- Use `attribute-reporting` when the user wants to scrape or use the current
  retail snapshot, map products to the central category taxonomy, compare the
  retailer-defined recent cohort or best sellers with the remaining assortment,
  create a private local HTML report, or ask whether that report is correct.
  This workflow preserves the existing cohort arithmetic and uses Codex agents
  for semantic mapping, report authorship, and independent review.
- Use `brand-fit` when the user has a completed, checked Retailer Signals
  analysis and wants to compare those retailer signals with both the brand's
  current presence at that retailer and the brand-owned catalogue in the stored
  database snapshot. It creates and checks a private local HTML Brand Fit
  report; it must not present the stored snapshot as a live-shelf assertion.
- Use `reporting-engine` when the user wants Clara to analyze a CSV/XLSX
  dataset, choose and render a useful business chart, inspect chart
  capabilities, or profile mechanical compatibility. Codex selects the
  meaningful analysis from the user's question and actual fields; deterministic
  components own exact calculations and rendering.

The main `clara` skill resumes after Interview, Transcribe, or Deck Correction
when retrieved or reviewed evidence must update a case workspace, evidence map,
advisory workpaper, or decision output. Attribute Reporting remains a
self-contained analytical workflow unless the user separately asks to register
its checked report in a Clara case or turn it into a presentation. Brand Fit is
also self-contained: its local source report is not uploaded, its product images
and HTML report stay local, and its semantic work runs in Codex without a user
or server model API key. Reporting Engine is also self-contained unless the
user asks to place its reviewed chart or interpretation in an advisory output.
Hosted-interview bundles and Hosted Voice bundles use different schemas; never
pass one to the other's importer.

The six specialized skills are the sole procedural authority for their
domains. If one of those requests appears during a main Clara case run, load and
follow the specialized skill instead of executing the older voice or
deck-revision detail retained later in this document for case-continuity
reference. Return to this main skill only after the specialized workflow has
produced reviewed local evidence or a verified deck artifact.

This workflow is reusable. Do not hard-code project names, advisor names,
client names, family names, or decision-maker names into plugin source,
templates, or schemas. Those belong in the case workspace files supplied or
created by the user.

## Core Principle

Deterministic scripts own mechanical work: JSON schema validation, stable case
file creation, source-path registration, note persistence, live issue
upserts, inclusion status updates, case-update packaging/import, client-pack
filtering, and DOCX rendering. They also rebuild `case_brief.md` from the
canonical case JSON files. This is deterministic because the correctness is
mechanically verifiable and the inclusion gate must be auditable.

Codex owns semantic judgement: interpreting consultant notes, separating facts
from judgement, identifying weak assumptions, proposing follow-up questions,
challenging contradictions after import, and drafting client-ready narrative.
Scripts must not make hidden model calls. The hosted voice path is explicit user action:
the plugin launches the Mparanza voice service, the server creates the Realtime
session, and the browser downloads a local bundle. Import that bundle into the
local case workspace; do not leave transcript, audio, or judgement content on
the server.

Never let pending consultant judgement enter a client-facing decision pack.
Pending and rejected entries may be counted in control notes, but their text
must not be silently promoted into substantive output.

## Two-Loop Advisory Delivery Model

Use this model for Clara advisory deliverables in general; it is not specific to
any client, advisor, family, or succession fact pattern. Clara spends tokens and
machine time before spending advisor time. The advisor supplies professional
judgement only after Clara has exhausted what can reasonably be said from the
case materials.

For a first deck or brief, Clara's governing question is: What is the best
current advisory position the advisor can responsibly take into the next
decision conversation, given the evidence available, the evidence missing, and
the decisions that cannot be postponed? The first deck is not a summary of
scenarios, source materials, or possible options. It must state the responsible
decision posture now, and what must be tested, evidenced, or decided before
moving further.

Before the advisory workpaper, Clara must create or update
`advisory_evidence_map.md`. This is a living Loop 1 control artifact. Clara
weighs evidence claim-by-claim, not source-by-source: the same interview,
presentation, document, metric, or external reference can be strong evidence
for one claim and weak evidence for another. For each material claim, option,
implementation condition, or decision point, the evidence map must record:

- the claim or decision point being tested;
- evidence that supports, weakens, contradicts, or creates the claim;
- the source type, such as stakeholder testimony, advisor judgement,
  self-presentation, operating document, financial or KPI evidence,
  governance/legal/tax document, external context, prior Clara output, inferred
  pattern, or missing evidence;
- what this evidence proves and what this evidence does not prove;
- directness, reliability, corroboration, bias or limitation, and source gaps;
- the decision implication and the missing evidence that would change the
  position.

Update `advisory_evidence_map.md` whenever new material is indexed, notes are
ingested, a transcript is imported, a case-update package is imported, or a
prior output is corrected in a way that could affect the decision. The update
must preserve existing claims, add new evidence items, mark whether new
evidence supports, weakens, contradicts, or creates a claim, close or open
questions when appropriate, and change Clara's advisory posture only when the
weight of evidence changes. Do not reduce this to a mechanical scorecard unless
the user explicitly asks for a scoring model and the basis for scoring is
auditable.

Loop 1 is the Advisory Intelligence Loop. Before building an HTML deck, memo, or
decision pack, Clara must inspect the case workspace, source materials, notes,
transcripts, prior outputs, `case_brief.md`, and canonical JSON files that are
relevant to the requested deliverable. Clara then produces or updates an
intermediate advisory artifact, normally `advisory_workpaper.md`, with:

- the real decision the advisor must help the decision-maker make;
- Clara's provisional point of view and default recommendation;
- options evaluated, not merely described;
- implementation steps and required conditions for each option;
- owners, timing, thresholds, risks, failure modes, and reversibility;
- evidence for and against each option, with source strength and gaps;
- contradictions, weak assumptions, and what would change the recommendation;
- critical questions and information requests that remain after Clara's review;
- a short advisor talk track: what to say, what to challenge, and what to avoid.

Clara must critique this intermediate artifact before asking for judgement. The
critique must attack generic claims, unsupported confidence, missing
implementation conditions, unweighed evidence, unresolved contradictions,
unclear recommendations, and advisor-usability gaps. Iterate until Clara cannot
identify a materially stronger advisory structure from the available evidence.

After Loop 1, create `judgement_checkpoint.md` or show the same content in chat.
The checkpoint is not an open brainstorming request. It is a compressed table of
the few judgement calls that genuinely require the advisor, each with Clara's
default answer, why Clara believes it, what evidence could be weak, and the
minimal answer needed from the advisor.

Default advisor-time assumption: the advisor has no time. Unless the user
explicitly asks Clara to wait, Clara must continue past the judgement checkpoint
using Clara's default recommendations. Mark unresolved points as
advisor-unconfirmed in the workpaper or control notes, not in the human-visible
document unless the reader needs that uncertainty to decide.

Loop 2 is the Presentation Excellence Loop. Build the human-visible HTML deck,
brief, memo, or Word narrative only from the Loop 1 advisory artifact plus any
advisor judgement actually supplied. Then critique the deliverable as a deck or
document, not only as prose. The review must ask:

- Does the deliverable have a clear point of view, not just a menu?
- Does every page or section add decision value?
- Is the sequence natural for the advisor's meeting or client conversation?
- Are options ranked or conditioned where the evidence allows it?
- Are implementation steps, conditions, risks, and critical questions concrete?
- Could the advisor use this under severe time pressure?
- Is the evidence weighed and are contradictions surfaced or deliberately parked?
- Are the visual hierarchy, density, headings, tables, and page breaks clear?
- Does any page exist only because a template expected it?

If Loop 1 shows that the honest answer is "more evidence is needed" or "the
next step is a test, interview, decision, or data request," that must emerge in
the human-visible deliverable when it is decision-relevant. Do not hide material
uncertainty to make the HTML look finished. The deliverable should state the
best current point of view, the evidence behind it, what remains unproven, which
next evidence would change the decision, and who must do what next. A beautiful
deck that suppresses critical unknowns, implementation conditions, or required
next steps is a failed Clara output.

Iterate Loop 2 until no material issues remain, or until each remaining issue is
explicitly accepted with a concrete reason. The target is not a fixed number of
slides or pages. The target is the best Clara can produce from available
materials and advisor judgement.

Use `/goal` only for major phase gates, not as a micro-task list. A normal
high-stakes advisory run should use goals such as: evidence exhaustion and
advisory workpaper; judgement checkpoint; deliverable build; deliverable
excellence review. Inside each goal, use ordinary checklists and artifacts.

Deck correction is always a goal-level workflow. When a user asks Clara/Codex
to correct, revise, or rebuild a deck from a voice/video call, transcript,
review notes, or partner feedback, start or continue an explicit goal before
doing deck-revision work. This is required because deck correction spans
evidence intake, semantic interpretation, consultant-readable approval,
PPTX editing, rendering, verification, and output review. Do not run it as a
casual one-turn edit even when the requested change sounds small; use ordinary
checklists inside the goal for the substeps.

## Human-Visible Document Quality Gate

This applies to Clara in general, not to a specific case. Before showing any
HTML brief, HTML deck, Markdown memo, Word narrative, email draft, or other
document that can be seen by the advisor, the client, a support reviewer,
The requesting user, or another human reviewer, must run a mandatory editorial pass. The document must
not expose the machinery used to create it.

Use this rule for every visible element: if the reader does not need it to
judge, correct, decide, or understand evidence, delete it.

Clara must remove or rewrite:

- scaffolding, source IDs, source-code labels, placeholder notes, page counters,
  and internal metadata;
- visible process narration such as "how to read this document", "use this
  section", "working pack", "draft review pack", or instructions about the
  document unless they are a concrete decision ask;
- repeated advisor-name personalization such as "for <advisor>" or repeated
  mentions of the partner's name when the name carries no case substance;
- labels that classify Clara's own work instead of helping the advisor, such
  as "support", "lens", "judgement register", or "correction required", unless
  the label names a real business object in the case;
- idiotic style figures: metaphors, slogans, clever contrasts, consulting
  theater, and "X is not Y, it is Z" lines that sound polished but add no
  substance;
- generic value language such as "create value", "help think", "more
  decidable", "non-linear reading", "give concrete levers", or equivalent
  filler unless rewritten into specific owners, conditions, risks, evidence,
  thresholds, or decisions;
- decorative formatting that carries no meaning: warning colors, brown or
  special-case cards, shadows, status chips, or card effects used for emphasis
  rather than a real distinction.

Raw provenance workpapers and inclusion-control files are the exception only as
workspace control artifacts: they may contain IDs, source paths, and control
metadata because that is their declared purpose. Clara must not send or present
them as the human-readable document. If the advisor, the client, the requesting user, a
support reviewer, or any other human is expected to read the content, create a
clean human-visible version and apply this gate.

Depth test: each section must contain at least one of these: judgement,
evidence, condition, risk, owner, threshold, implication, open question, or
decision needed. A section that only says "validate", "go deeper", or "decide"
without naming what, who, why, and how fails the gate.

Deck-quality test: each page or section must earn its place in the advisor's
delivery. Delete, merge, or rewrite any page that merely repeats another page,
lists generic considerations, lacks a decision implication, hides the point of
view, omits implementation conditions, or cannot be used by a time-constrained
advisor in the next conversation.

Standalone talk-deck boundary: when the user supplies a finished document,
report, memo, or other source and asks only for a distinctive educational or
conference HTML presentation, use the `html-deck` skill without creating
a fake Clara case workspace, evidence map, or advisory workpaper. This boundary
does not bypass source fidelity. If the source belongs to an active Clara
advisory case or the deck will carry Clara's recommendation, the normal Loop 1
evidence map and workpaper remain mandatory before the deck is built.

Fixed-format HTML deck test: any Clara output that is a slide deck, not a
scrolling brief or memo, must use `scripts/html_deck_runtime.py` before it is
written. The runtime locks every slide page to 16:9, sizes the deck from both
viewport width and viewport height, and sets SVG slides to
`preserveAspectRatio="xMidYMid meet"` so ultra-wide presentation surfaces
letterbox instead of stretching content. It also gives every slide a stable ID
and publishes the active slide ID/title through the browser Capture Handle API.
Do not remove that runtime from a deck that may be reviewed through Hosted Voice
Capture.
Use `html-deck` for the source ledger, component system, content-addressed
publication folder, deterministic validation/package gate, and browser QA of a
standalone animated stage deck. Do not hand-build a second incompatible deck
runtime. For an existing Clara HTML deck, also use its hash-bound revision map
and before/after comparator; do not treat an HTML change request as an
unconstrained rebuild.

Evidence-gap test: if the advisory workpaper identifies decision-relevant
missing evidence, contradictions, weak assumptions, critical questions, or
required next steps, the human-visible deliverable must show them in a clean
decision-ready way. Do not turn unresolved evidence needs into generic
"validate" language, decorative caveats, or hidden workpaper-only notes.

Evidence-navigation test: every major recommendation, option ranking, or
implementation condition must be traceable to `advisory_evidence_map.md`. If
the map cannot show what the evidence proves, what it does not prove, and what
would change the position, the recommendation is not ready for a human-visible
deck.

Mechanical checks may block fixed anti-patterns such as `jud-` IDs, page-number
artifacts, placeholder labels, and banned filler phrases. Semantic judgement
still belongs to Codex: after mechanical checks, run repeated model-led
editorial sweeps through the whole document looking for bullshit, not just one
quick pass. Each sweep must identify deletions, rewrites, repetitions, weak
headings, empty paragraphs, style figures, and formatting noise. Iterate until
the sweep returns no material issues, or until the remaining issue is
deliberately accepted with a concrete reason.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices
that change execution: case objective, audience, output language, material
scope, advisor name for inclusion records, whether notes are pasted text or existing files, and
which existing folder should be indexed. Ask only those unresolved choices in
chat; put differently, ask only those unresolved choices in chat before
execution. Generate choices from the actual inputs; do not offer named
frameworks, project roles, issue categories, advisor names, or decision-maker
names unless the facts cue them or the user must supply a missing custom value.

Default output policy: produce the natural full package for the workflow when
dependencies permit: `case_manifest.json`, `material_registry.json`,
`judgement_log.json`, `open_questions.json`, `case_issues.json`, `case_brief.md`,
`clara_mandate.json`, `clara_kickoff_deck.html`,
`clara_partner_brief.html`, `advisory_evidence_map.md`,
`advisory_workpaper.md`, `judgement_checkpoint.md`,
`presentation_storyline.md`, `presentation_review.md`, `decision_pack.md`,
`decision_pack.docx`,
`decision_pack_workpaper.md`, and `decision_pack_workpaper.docx`. These are not
choices to propose when the run is a normal case-workspace run. Do not ask
whether to create both Markdown and Word unless the user explicitly requests a
reduced run or DOCX dependencies are unavailable.

When reopening an existing case, read `case_brief.md` first if it exists. Treat
it as a derived orientation view, not as authority. If
`advisory_evidence_map.md` exists, read it before revising the advisory
workpaper or any human-visible output. Confirm substantive details against the
JSON case files and source materials before drafting final output.

Use Codex-native run artifacts lightly:

- Start with a short checklist covering dependency check, case initialization,
  material indexing, judgement capture, client-pack inclusion, and delivery.
- Show a compact Run Intake table before helper scripts with case folder,
  materials, language, audience, advisor name assumption, and output folder.
- Show a Decision Table only for unresolved material choices or pending
  client-pack inclusion decisions.
- Before long or write-heavy steps, show an inclusion checkpoint with command
  intent, inputs, output folder, and expected artifacts.
- Ask for explicit continuation or approval only when the next step is
  external, destructive, approval-sensitive, or still depends on an unresolved
  material decision. Do not ask the user to type a generic continuation word
  merely to create ceremony.
- End with an Artifact Card listing generated paths, inclusion status, unresolved
  questions, and next action.
- When useful, create `codex_run_review.md` in the case output folder. Never edit
  generated ZIPs during a run.

Use chat as the v1 interface. Do not build or invoke a local review UI for this
plugin unless the user explicitly asks to add one. If review is needed, show the
pending judgement entries in chat or Markdown and ask the advisor which items to
include, exclude, expand, or correct.

## Inputs

Required:

- a case workspace folder, or enough information to initialize one;
- client/project labels supplied by the user;
- case objective and intended decision-maker audience.

Optional:

- a firm/company profile in the case folder or parent company folder, such as
  `company_profile.json` or `clara_company_profile.json`, with inherited deck
  style and advisory-method defaults for project case folders;
- existing source folders or files to index;
- pasted consultant notes or transcripts;
- spoken debriefs captured through the hosted voice service and imported from
  a local downloaded bundle;
- uploaded audio recordings transcribed and analyzed through the hosted voice
  service, then imported from a local downloaded bundle;
- Codex-drafted judgement entries;
- advisor name for inclusion records;
- working language: `it`, `en`, `fr`, or `de`.

## First Run Workflow

1. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If dependencies are missing, install from `requirements.txt` only when the
environment allows it. Otherwise explain which dependency is missing and which
output is affected.

For scanned PDFs, screenshots, or other image-only evidence that requires local
OCR, check the optional OCR dependencies as well:

```bash
python scripts/check_dependencies.py --requirements requirements.txt --requirements requirements-ocr.txt
```

If OCR dependencies are missing and local OCR is required, install from
`requirements-ocr.txt` only when the environment allows it. Otherwise use
Codex/model visual OCR with explicit provenance and explain that deterministic
local OCR was unavailable.

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
update `advisory_evidence_map.md` before revising the advisory workpaper,
storyline, deck, memo, or decision pack.

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

For existing note files, use `--notes-file`; the plugin copies the file under
the case workspace `notes/` folder before registering it, so temporary download
or extraction paths do not become brittle provenance records.

Optional hosted voice capture: when the user wants a spoken debrief and should
not manage an OpenAI API key locally, launch the hosted voice service from the
plugin. The server is only the voice compute/auth layer. The browser downloads a
local bundle, and the plugin imports that bundle into the local case workspace.
The launcher attaches a compact pre-call debrief plan plus context from
`case_brief.md` to the short-lived launch token so the hosted voice model is
anchored to the workspace instead of starting generic.

Voice Capture is transcription-first. The hosted page records live screen video
plus automatically captured audio, or uploads an existing recording. Treat
attribution, challenge, and semantic review as post-import local Codex work over
the full transcript and any captured video provenance.
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
python scripts/start_deck_feedback.py <case-dir> --deck <existing-deck> --browser chrome
python scripts/upload_hosted_audio.py <case-dir> <audio-file> --magic-link "<url>"
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

After any uploaded-audio transcription is imported, Clara must perform a local
transcript-processing pass before using the transcript as advisory evidence:
assign speaker attribution from the clean transcript plus source metadata,
check the document-level transcript quality, and correct only obviously wrong
transcription words when the intended wording is clear from transcript context
or a trusted case glossary. Preserve uncertainty instead of guessing; do not
rewrite, summarize, or change meaning during this pass.

Speaker attribution is a local Codex/Clara text loop. The hosted server
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
`case_brief.md`.

When the reviewed transcript also requires judgement, question, and issue
integration, prefer the deterministic integration helper over a temporary
one-off script:

```bash
python scripts/integrate_transcript_review.py <case-dir> \
  --plan-json <integration-plan.json>
```

Codex must still inspect the transcript text and draft the semantic plan. The
helper only applies the auditable plan: material registry metadata updates,
review-note section fills, pending judgement entries, existing open-question
links, case-issue evidence/synthesis updates, `case_brief.md` refresh, and a
validation/evidence-chain summary. Do not use it to promote entries to
decision-pack-ready unless the advisor has explicitly made the inclusion
decision under the normal Clara rules.

When browser file upload is blocked or the audio is large, use
`scripts/upload_hosted_audio.py` instead of driving the page file chooser. The
script consumes a Mparanza magic link or reuses an existing authenticated
`Cookie` header, uploads the existing local audio file to the hosted API, stores
the returned bundle under the case workspace, imports it into `voice_sessions/`,
and copies the original audio file into the imported session folder. It attaches
the same compact local case context as the hosted launcher before requesting the
upload token, so server-side transcription and extraction are anchored to the
workspace. Use `--no-case-context` only for debugging a raw hosted token path.
Use `--no-import` only when the hosted bundle needs inspection before local
registration.

The launcher and hosted-audio uploader cap embedded case context so the hosted
URL stays within gateway limits. If a large workspace still produces a warning,
retry with a smaller context budget such as `--max-context-chars 1800`; do not
paste long launch URLs into chat.

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
decision pack, reconcile it into `advisory_evidence_map.md`. Direct access to
the hosted voice URL without a
plugin-created launch token is not a valid run.

When the workspace needs a first local partner-facing HTML brief, build it
explicitly:

```bash
python scripts/build_clara_kickoff_deck.py <case-dir>
python scripts/build_clara_partner_brief.py <case-dir>
```

These HTML files are working artifacts for the senior partner, not client
outputs. They should summarize initial hypotheses, evidence gaps, open
questions, and what Clara needs from the partner next.

5. Codex reads the source material and drafts structured entries. Store them as
pending by default:

```bash
python scripts/add_judgement.py <case-dir> --entries-json <entries.json>
```

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
name the decision area, current synthesis, evidence-for judgement IDs,
evidence-against judgement IDs, and open-test question IDs:

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

7. For a solo advisor, do not frame this as "approval." The advisor is deciding
which Codex-structured statements are ready to rely on in the client pack. First
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
materials, judgement, open questions, or conflicts, update
`advisory_evidence_map.md` before relying on the imported content in a
deliverable.

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

## Data Contract

The case workspace owns durable JSON files and derived working artifacts:

- `case_manifest.json`: client, project, objective, audience, status, output
  language, timestamps.
- `company_profile.json` or `clara_company_profile.json` in the case folder or
  parent company folder: optional inherited firm/company defaults, including
  `default_deck_style`, `deck_style_spec_path`, and `advisory_method`.
- `case_brief.md`: derived working brief for resume/orientation; not a source
  of truth.
- `clara_mandate.json`: Clara's kickoff preparation, first understanding,
  sensitive points, essential clarifications, and next steps.
- `clara_kickoff_preparation.md`: deterministic preparation note for the first
  partner briefing.
- `clara_kickoff_deck.html`: first quiet partner-facing HTML deck with initial
  hypotheses, evidence gaps, open questions, and next partner inputs.
- `clara_partner_brief.html`: local HTML working brief for the senior partner.
- `advisory_evidence_map.md`: living Loop 1 evidence navigation map. It links
  claims, options, and implementation conditions to evidence that supports,
  weakens, contradicts, or creates them; records what each source proves and
  does not prove; and tracks directness, reliability, corroboration, bias,
  limitations, source gaps, decision implications, and evidence that would
  change the position. Update it whenever material evidence changes.
- `advisory_workpaper.md`: Codex-authored Loop 1 advisory reasoning, option
  evaluation, evidence weighing, contradictions, implementation conditions, and
  Clara defaults. This is a working artifact, not the polished client document.
- `judgement_checkpoint.md`: compressed advisor judgement requests with Clara
  defaults. Default behavior is to continue without waiting unless the user
  explicitly says the advisor will respond before delivery.
- `presentation_storyline.md`: the approved or default storyline used to render
  the human-visible deck, memo, or HTML brief.
- `presentation_review.md`: Loop 2 critique log covering anti-BS, structure,
  page value, clarity, evidence, advisor usability, and accepted residual issues.
- `material_registry.json`: source paths, material type, title, summary, status,
  review timestamp.
- `judgement_log.json`: fact, advisor judgement, Codex inference, open question,
  or decision implication entries with pending, approved, or rejected status.
  In user-facing solo-advisor workflow, treat `approved` as "include in the
  client pack" and `rejected` as "exclude from the client pack."
- `open_questions.json`: targeted follow-ups with reason and status.
- `case_issues.json`: live cross-interview issues with stable IDs, current
  synthesis, evidence-for/evidence-against judgement IDs, and open-test
  question IDs.
- `exchange_log.json`: deterministic record of imported case-update packages.
- `decision_pack.md` and `decision_pack.docx`: clean client/advisor narrative
  without local source paths or CLI mechanics.
- `decision_pack_workpaper.md` and `decision_pack_workpaper.docx`: provenance,
  material registry, source paths, and inclusion-control evidence.

Codex may create temporary working files such as `entries.json` while preparing
structured judgement, but must not ask the user to edit JSON by hand.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the
deliverables, briefly identify concrete improvements that would have made this
plugin run better. Base suggestions on the actual session, such as a missing
material type, unclear inclusion step, brittle DOCX rendering, missing import
format, needed fixture, output gap, installation friction, or repeated manual
step.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts.
