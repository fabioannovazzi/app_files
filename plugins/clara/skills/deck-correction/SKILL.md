---
name: deck-correction
description: "Correct, revise, or rebuild an existing PPTX or Clara HTML deck from spoken feedback, a call transcript, screen recording, review notes, or partner comments. Use when the user says record feedback on this deck or when the requested outcome is a changed deck rather than only a transcript: open Clara Voice Capture when needed, interpret every requested change, preserve untouched content, require a reviewable understanding and approval checkpoint for PPTX work, apply changes to a copy, render, verify, and inspect the final audience-facing deck. Do not use for transcription alone or for creating a new deck without revision feedback."
---

# Deck Correction

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or another static-site folder. Keep the corrected deck,
rendered slides, revision artifacts, and `codex_run_review.md` in the user's case
or adjacent project/output folder.

Use this skill when feedback must become a verified deck change. The analytical
meaning of the feedback is model-led work; deterministic helpers may prepare
evidence, validate contracts, apply explicit patches, and verify mechanics, but
must never decide what the speaker meant from keywords, slide numbers, or visual
matching alone.

Deck correction is always a goal-level workflow. Start or continue an explicit
goal before intake. The goal covers interpretation, user review, application,
rendering, verification, and final output review.

## Route by Target Format

- **PPTX:** use the Clara deck-revision harness below and the installed
  presentation-editing capability. Keep the original untouched and edit a copy.
- **Clara HTML deck:** use the `html-deck` preservation-aware revision workflow.
  Build a revision map from the approved change ledger, protect untouched
  slides/components/runtime, apply only mapped changes, and prove before/after
  fidelity through browser and render QA.
- **No existing deck:** this is creation, not correction. Route to the normal
  presentation or `html-deck` creation workflow after clarifying the target
  format.

If the feedback comes from audio or video, use `transcribe` first when no clean
reviewed transcript exists. A hosted external interview is not a deck-correction
input until its bundle has been retrieved and the user explicitly asks to use
that evidence.

Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

Install declared requirements only when the environment permits.

## One-Command Live Feedback Capture

When the user says **“Clara, record feedback on this deck”** or equivalent,
do not ask them to find a server URL, open a desktop shortcut, locate the
downloaded bundle, or run an import command. Resolve the current Clara case and
target deck from inspected context. Ask one short question only when either is
materially ambiguous, then run:

```bash
python scripts/start_deck_feedback.py <case-dir> \
  --deck <existing-deck.pptx-or-html> \
  --browser chrome
```

Run this as a continuing process and keep the user informed while they record.
The helper opens the authorized context-bearing Voice Capture page, ignores
older downloads, waits for the newly completed bundle, imports it into the
case, and writes `deck_feedback_capture.json` in the imported voice session.
For PPTX it also refreshes the deck-revision intake against the exact target
deck. For HTML, read the handoff and follow the preservation-aware HTML path
below. After import, complete speaker attribution when needed and continue the
normal interpretation and revision workflow; do not send the user back to the
Downloads folder.

If the capture process is interrupted, preserve the existing local case and
report whether the browser launch, new-bundle detection, or import failed. Fall
back to `import_latest_hosted_voice_bundle.py` only when a completed bundle is
already present but the continuing process was lost.

## Required Authorities

Before editing, establish:

- **case/evidence authority:** the relevant case context, transcript, notes,
  call/video provenance, and supporting materials;
- **visual authority:** the current deck plus its inherited or explicit style
  profile;
- **method authority:** evidence-aware, room-safe advisory wording and the
  distinction between source claims, user requests, and Clara interpretation.

Do not fabricate missing replacement wording, quotes, evidence, chart data, or
style rules. If a requested change lacks source material or a decision, keep it
visible as blocked or `needs_human_decision`.

## PPTX Intake and Interpretation

Prepare the intake after the transcript is attributed and the existing deck is
known:

```bash
python scripts/prepare_voice_deck_revision.py <case-dir> \
  --deck <current-deck.pptx>
```

Add `--deck-style` or `--company-profile` when style authority is not already
resolved. The intake snapshots the deck/style evidence and may attach
conservative rendered-slide match candidates. Those matches are navigation
evidence only.

Build the workbench and focused interpretation packets:

```bash
python scripts/build_deck_revision_workbench.py <case-dir>
python scripts/build_deck_revision_interpretation_packets.py <case-dir>
```

Codex inspects the packets and writes
`deck_revision_changes.json`. Every change must carry:

- the requested change and its transcript/review evidence;
- Clara's interpretation and uncertainty;
- scope and affected slides;
- execution strategy;
- concrete success criteria;
- packet/dependency metadata when relevant.

Use `packet_scope: "deck"` for global font, order, insertion, deletion, or other
deck-level changes. High/medium visual matches may ground location; low/no
matches are navigation hints only.

Finalize the consultant-readable understanding:

```bash
python scripts/finalize_deck_revision_plan.py <case-dir> \
  voice_sessions/<timestamp>/deck_revision_changes.json
```

The finalizer validates evidence and slide references, ignores model-authored
approval flags, and writes the normalized plan plus
`deck_revision_understanding.md`. Do not edit the PPTX yet.

## Execution Planning and Material Gaps

Build explicit execution routes and packets:

```bash
python scripts/build_deck_revision_execution_plan.py <case-dir>
python scripts/build_deck_revision_execution_packets.py <case-dir>
python scripts/analyze_deck_revision_materials.py <case-dir>
```

Strategies are `deterministic_patch`, `model_assisted_edit`, `slide_rebuild`,
`deck_restructure`, or `needs_human_decision`. Execute one focused packet at a
time. If a deck-level packet changes order or slide count, refresh later slide
references before continuing.

Supported automatic patches are intentionally narrow: `set_title_text`,
`set_shape_text`, `replace_text`, `add_textbox`, `delete_shape`, and
`move_shape`. Existing-object patches need concrete target identity and expected
pre-edit text. Route unsupported or judgement-heavy changes to the appropriate
model-assisted or human path.

When changes request better quotes or interview evidence, build and inspect the
candidate matrix before selecting copy:

```bash
python scripts/build_deck_revision_quote_candidate_matrix.py <case-dir>
```

The matrix finds candidates; Clara/Codex still judges relevance, source
diversity, sharpness, and room-safe wording.

## PPTX Approval and Application

Show `deck_revision_understanding.md` to the user. Only after that review write
the hash-bound approval artifact:

```bash
python scripts/approve_deck_revision_plan.py <case-dir> \
  --reviewer "<name>" --understanding-reviewed
```

If the normalized plan or understanding changes, approval is stale and must be
renewed. Apply supported patches only after approval:

```bash
python scripts/apply_deck_revision_plan.py <case-dir>
```

The applier writes a corrected copy, apply report, verification artifacts, and
an output-review checklist. A successful script exit is not proof that the deck
is ready; semantic/manual success criteria and the visible render still require
review.

Render and inspect every changed slide and enough surrounding slides to catch
sequence effects. Check audience-facing titles/copy, numbers, charts, footers,
clipping, overlap, stale artifacts, internal instructions, process language,
and semantic drift. Iterate until no material issue remains, then complete the
exact-output review:

```bash
python scripts/complete_deck_revision_output_review.py <case-dir> \
  --reviewer "<name>" \
  --audience-copy-reviewed \
  --process-language-reviewed \
  --requested-structure-reviewed \
  --semantic-evidence-fit-reviewed \
  --visual-render-reviewed
```

Do not present the corrected PPTX as final until the completion artifact exists
for the exact reviewed output.

## HTML Preservation Path

For an existing HTML deck, read and follow the full `html-deck` revision
workflow. The correction evidence becomes an explicit change ledger; it does
not authorize global cleanup. Inspect the existing deck, create a revision map,
protect untouched slide IDs/components/styles/runtime, apply only mapped edits,
run static and multi-viewport browser QA, render the result, and compare it with
the baseline. Report both intended changes and any unexplained drift.

There is no PPTX-style hash approval helper for HTML. Still show the interpreted
change ledger before a materially ambiguous or broad revision and keep the
goal-level checkpoint in chat.

## Codex-Native Run UX

Use a short checklist covering intake, transcript/evidence readiness,
interpretation packets, understanding, approval, execution packets, render QA,
and delivery.

Show a compact Run Intake table with source deck, target format, feedback
sources, transcript status, style authority, case/evidence folder, output copy,
and expected QA artifacts. Use a Decision Table only for unresolved material
choices such as ambiguous feedback, missing source material, an unresolvable
style authority, or a real execution strategy choice.

Default output policy: preserve the original, produce one corrected deck plus
its interpretation, approval, verification, and render-review evidence. These
are not choices to propose when the user asked for the normal deck-correction
run. For PPTX, the reviewed understanding and hash-bound approval checkpoint are
mandatory before application.

Before long or write-heavy work, show an execution checkpoint naming the source
deck, approved plan hash where applicable, output path, packet scope, and
expected verification. End with an Artifact Card listing original, corrected
deck, interpreted changes, approval state, verification, render-review state,
and residual manual items. Create `codex_run_review.md` when blocked or when a
repeatable correction gap should survive the chat. Never edit generated ZIPs
during a run.
