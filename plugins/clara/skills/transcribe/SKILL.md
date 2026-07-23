---
name: transcribe
description: Capture, transcribe, import, attribute, and review advisor voice notes, consultant debriefs, meetings, calls, and existing audio recordings with Clara Hosted Voice. Use when the user asks to start Voice Capture, transcribe an audio file, import a case-notes-audio or case-notes-voice ZIP/JSON bundle, preserve a transcript in an ordinary folder with deduplication, or add a reviewed transcript to a Clara case. Do not use to create an adaptive external-participant interview link or to revise a deck from spoken feedback.
---

# Transcribe

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or another static-site folder. Preserve bundles, audio,
transcripts, review files, and `codex_run_review.md` in the user's target case,
ordinary folder, or adjacent project/output folder.

Use this skill for transcription-first evidence capture. The hosted service is
the authorized audio/transcription layer. Durable source and output files remain
local after import; Codex performs speaker review and advisory interpretation
through the user's existing ChatGPT plan. This is separate from `interview`,
which conducts an adaptive conversation with an external participant.

## Choose the Path

- **Live consultant debrief:** launch Voice Capture from an existing Clara case.
- **Existing audio:** upload the voice note, meeting, or call recording through
  the hosted service, then import the downloaded bundle.
- **Downloaded bundle into a Clara case:** import into `voice_sessions/`, finish
  speaker attribution, register the reviewed transcript, and update the case
  evidence map before downstream advisory output.
- **Downloaded bundle into an ordinary folder:** preserve the original bundle
  and readable transcript with deduplication; do not initialize a case merely
  to store the transcript.
- **Spoken feedback that should change a deck:** complete transcription and
  attribution here, then route the reviewed evidence to `deck-correction`.

Run dependency checks from the plugin directory before substantive work:

```bash
python scripts/check_dependencies.py
```

Install declared requirements only when the environment permits. Do not install
packages at runtime from within a plugin script.

## Live Capture

For an initialized Clara case:

```bash
python scripts/launch_hosted_voice.py <case-dir>
python scripts/launch_hosted_voice.py <case-dir> --browser chrome
python scripts/launch_hosted_voice.py <case-dir> \
  --cookie-header-file <private-cookie.txt>
```

With an authenticated cookie or magic link, the launcher refreshes
`case_brief.md`, sends compact transcription context in an authenticated HTTPS
request body, and opens the hosted page with an opaque short-lived token. The
context is not placed in the URL. The user-bound token is an additional session
control and does not replace Mparanza authentication. Without supplied
authentication material, the launcher opens an explicit browser-authenticated
fallback without reading or attaching `case_brief.md`. Use Chrome when the
embedded browser or stale permissions block the microphone. The browser
downloads a local bundle when the session ends. Directly opening the hosted
voice URL without a plugin-created launch token and authenticated session is not
a valid run.

Voice Capture is transcription-first. Sparse follow-ups may help the advisor
finish a debrief, but the hosted model is not the final speaker-attribution or
advisory authority.

## Existing Audio

The hosted page accepts an existing audio recording. When browser upload is
blocked or the file is large, use the authenticated uploader:

```bash
python scripts/upload_hosted_audio.py <case-dir> <audio-file> \
  --magic-link-file <private-magic-link.txt>

python scripts/upload_hosted_audio.py <case-dir> <audio-file> \
  --cookie-header-file <private-cookie.txt>
```

Add source metadata such as `--title`, `--interview-date`, `--participants`, and
`--interviewer` when known. Do not place authentication secrets in chat or run
artifacts. The uploader stores the returned bundle under the case workspace and
normally imports it immediately. Use `--no-import` only when the bundle must be
inspected before registration.

For an ordinary folder that is not a Clara case, disable both case-dependent
behaviors and choose the transcription language explicitly when it is not
Italian:

```bash
python scripts/upload_hosted_audio.py <target-folder> <audio-file> \
  --no-case-context --no-import --language en \
  --magic-link-file <private-magic-link.txt>
```

The uploader saves the returned bundle under
`<target-folder>/hosted_voice_uploads/`. Import that bundle with the ordinary
folder importer below. If `case_manifest.json` exists, the uploader continues
to require a valid Clara case workspace.

## Import Into a Clara Case

Use the newest valid download by default:

```bash
python scripts/import_latest_hosted_voice_bundle.py <case-dir>
```

Point to a specific bundle only when necessary:

```bash
python scripts/import_hosted_voice_bundle.py <case-dir> <downloaded-bundle.zip>
```

The importer preserves the raw payload and media, registers the transcript as
source material, creates a local review pack, and prevents repeated imports of
the same session. Treat the imported transcript as evidence, not final advice.

## Import Into an Ordinary Folder

When the target does not contain `case_manifest.json` and the user only wants a
durable transcript:

```bash
python scripts/import_hosted_voice_bundle_to_folder.py \
  <target-folder> <downloaded-bundle.zip>
```

This path keeps or adopts the original ZIP/JSON, writes or adopts a readable
sibling transcript, and records relative paths and SHA-256 fingerprints in
`.clara/voice_imports.json`. Exact or repackaged duplicates reuse existing
artifacts. Missing transcripts may be repaired. Never overwrite or delete an
ordinary-folder document; unrelated collisions receive numeric suffixes. A
conflicting variant requires deliberate `--allow-variant` use.

This lightweight path does not create case JSON, infer speakers, register
judgement, or promote the transcript into advisory evidence.

## Speaker Attribution and Review

The hosted server transcribes audio; it is not the speaker-naming authority.
Import may create `attributed_transcript.md` only when a single known speaker
makes attribution trivial. Otherwise it creates `speaker_attribution_task.md`
and `speaker_attribution_report.json`.

Codex must complete that task in the same workflow:

1. Read the raw transcript, source metadata, and useful notes.
2. Assign real names only when supported; otherwise use stable labels such as
   `Speaker 1` and `Speaker 2`.
3. Preserve the original unattributed transcript.
4. Correct only obvious transcription errors whose intended wording is clear
   from context or a trusted case glossary.
5. Inspect for merged turns or wrong labels and keep uncertainty visible.

Do not use an audio diarization model for Clara speaker attribution. Do not
rewrite, summarize, or change meaning during the transcript-cleaning pass.

Finalize a reviewed transcript with the deterministic registry helper:

```bash
python scripts/finalize_hosted_transcript.py <case-dir> \
  <transcript-material-id> \
  <voice_sessions/.../attributed_transcript.md> \
  --audio-pointer <source_materials/interviews/...-audio.md>
```

When the reviewed transcript also requires judgement, questions, and live-issue
updates, Codex drafts a semantic integration plan and applies it with:

```bash
python scripts/integrate_transcript_review.py <case-dir> \
  --plan-json <integration-plan.json>
```

The helper applies an auditable plan; it does not interpret the transcript.
New judgement remains `pending` until the advisor makes the normal client-pack
inclusion decision. Update `advisory_evidence_map.md` before the transcript
changes a workpaper, storyline, deck, memo, or decision pack.

## Codex-Native Run UX

Use a short checklist covering source selection, hosted capture or upload,
bundle import, speaker attribution, transcript review, registry finalization,
and case-evidence update.

Show a compact Run Intake table with source recording or capture mode, target
case/folder, language, known speakers, source metadata, bundle path, and output
folder. Use a Decision Table only for unresolved material choices such as an
ambiguous target folder, a genuinely uncertain speaker boundary, or whether a
conflicting recording is an intentional variant.

Default output policy: preserve the source bundle and audio, produce a readable
reviewed transcript, and register it when the target is a Clara case. These are
not choices to propose when the user asked for the normal transcription run.
Speaker attribution is the approval checkpoint before advisory or deck use; do
not ask for ceremony when attribution is clear from inspected evidence.

Before long or write-heavy work, show an execution checkpoint naming the source,
target folder, expected local artifacts, and whether hosted upload is required.
End with an Artifact Card listing source bundle, audio, raw transcript, reviewed
transcript, attribution status, registry status, and unresolved uncertainty.
Create `codex_run_review.md` only for a blocked run or a repeatable import or
transcription gap. Never edit generated ZIPs during a run.
