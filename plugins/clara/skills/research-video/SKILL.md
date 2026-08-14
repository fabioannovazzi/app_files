---
name: research-video
description: Turn a user-approved ordered set of research scene images into a source-faithful 16:9 narrated MP4 with restrained motion, synchronized narration in English, Italian, French, German, or Spanish, captions, a reviewable narration script, and mechanical media validation. Use for a research explainer, executive briefing video, client education video, or narrated visual short. Do not use for filming, avatar video, generative scene invention, or revising an existing video.
---

# Research Video

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

Create one short, source-faithful research video from an ordered set of approved
scene images. The supplied images and source material remain authoritative.
Clara may write narration and recommend scene order, but must not invent a
claim, statistic, map feature, figure label, visual object, or source basis.

## Runtime and output boundary

The complete workflow uses the authenticated Mparanza Research Video voice
page to generate one audio artifact per approved scene, plus a local Clara
runtime with Python and FFmpeg to build the MP4. No user API key is required.
Mparanza holds the provider credential; the packaged renderer contains no
provider credential and makes no direct speech-provider call.

The hosted service is currently open to every authenticated Mparanza account;
there is no Research Video email allowlist. Only the exact approved narration,
language, scene identifiers, and approval/plan hashes cross the hosted boundary.
Images, research sources, source-basis notes, Vera artifacts, and local paths
stay in the local workspace. Mparanza builds the response ZIP in memory and does
not write the request or generated audio to application storage. OpenAI receives
the narration under Mparanza's provider arrangement; do not infer or promise an
OpenAI retention period from this workflow.

Keep all run inputs and outputs outside plugin source and static/public folders.
Use an output folder beside the user's project material unless the user names a
different destination. Never put an API key in chat, a scene plan, a command
argument, a log, or an artifact.

## Decision boundary

Clara owns semantic work through model-led review:

- selecting and ordering only the user-approved research scenes;
- interpreting the supplied material;
- drafting concise narration in the approved language (`en`, `it`, `fr`, `de`,
  or `es`);
- deciding what each scene contributes to the argument;
- checking that narration says no more than its recorded source basis;
- identifying qualifications, uncertainty, and claims that should be removed.

Deterministic code owns work whose correctness is mechanically verifiable:

- scene-plan schema, path, file-type, dimension, and size validation;
- SHA-256 fingerprints for the plan and every visual layer;
- approval binding to the exact narration and visual plan;
- hosted voice request and bundle-manifest shape, scene-audio conversion and
  hashes, scene timing, caption timing, motion rendering, cross-fades, audio
  normalization, MP4 assembly, decoding, and artifact hashes.

Mparanza sends the exact approved narration to OpenAI using the centrally
selected model and language-specific voice, then returns an in-memory ZIP. The
local attachment code validates the source marker, request and approval hashes,
audio bytes, WAV metadata, duration, and scene order. These checks prove bundle
integrity; they do not prove pronunciation or semantic delivery.

The renderer requires source-basis entries but cannot judge whether they truly
support the narration. Clara must perform that semantic review before asking
for approval, and the user remains the final reviewer.

## Vera handoff boundary

Keep Research Video Clara-owned. When the input comes from Vera, use only the
exact accepted visuals and their current review artifacts from the relevant
Vera workflow. For a legal, tax, regulatory, accounting, social-security, or
professional communication, Vera continues to own source authority, governing
framework, applicability, claim assurance, professional acceptance, and any
send or publication decision. Clara may turn those accepted materials into the
reviewable video, but the presence of `source_basis` does not repeat or replace
Vera's professional review.

Do not route an unsupported Vera question to Research Video merely because a
video was requested. Finish the applicable Vera workflow first; if no Vera
workflow covers the professional task, stop rather than using the video plan as
an assurance substitute.

## Hosted-Voice Run UX

Before write-heavy work, show a compact Run Intake table with source files,
approved scene images, audience, target duration, language, work folder, output
root, privacy boundary, and review status. Keep a short checklist for source
inspection, scene plan, narration review, approval, render, mechanical checks,
semantic review, and delivery.

Use a Decision Table for resolved facts and evidence: scene order, source basis,
visual-layer availability, selected motion, narration status, approval hash,
and render status. These are facts to verify, not choices to propose after the
user has already requested a complete narrated video.

Before voice generation, show one execution checkpoint naming the run folder,
exact approved plan, scene count, Mparanza/OpenAI voice policy, and expected
artifacts. State that no user API key is involved. Default output policy: keep
the canonical plan, intake, narration, Mparanza voice request,
voice manifest and audio, review packet, approval, MP4, poster, captions,
reports, and artifact manifest outside plugin source. The generated ZIPs belong
in the repository only during an explicit plugin package or release task; never
edit them by hand.

At delivery, return an Artifact Card linking the MP4, poster, captions,
narration script, Mparanza voice request, attached voice manifest and scene audio,
render report, final artifact manifest, and editable run folder. Include source
count, scene count, duration, narration language, voice, the localized on-screen
AI-voice disclosure, motion boundary, validation status, and any residual issue.
Write `codex_run_review.md` when the run is blocked, a fallback is accepted, or a
repeated failure needs a durable handoff note.

## Workflow

### 1. Establish the run intake

Run Clara's dependency check from the Clara plugin root:

```bash
python scripts/check_dependencies.py
```

Inspect every proposed scene image and the controlling research sources. Confirm
the audience, intended duration, narration language (`en`, `it`, `fr`, `de`, or
`es`), output folder, and whether any scene has genuine separated background and
transparent foreground layers. Ask only about unresolved choices that
materially change the story or output.

Use chat and Markdown for review. A separate HTML application is unnecessary
for this bounded ordered-scene workflow.

### 2. Author the scene plan

Create `scene-plan.json` outside plugin source using
`references/scene-plan.schema.json`. Each scene requires:

- a stable `id`;
- one approved local `image`;
- the exact narration text to synthesize in the declared language;
- at least one `source_basis` item naming a reference and what it supports;
- optional restrained `motion`.

Supported flat-image motion is `zoom_in`, `zoom_out`, `pan_left`, `pan_right`,
or `static`. Flat images do not become true parallax. Use
`layered_parallax` only when the user supplies both a clean background image and
an aligned transparent PNG `foreground_image`; never manufacture depth layers
from the research image.

Prepare the run:

```bash
python scripts/managed_python_runtime.py run \
  skills/research-video/scripts/research_video.py prepare \
  --scene-plan <scene-plan.json> \
  --output-dir <project-output-folder>/research-video
```

Preparation writes `run_intake.json`, a canonical `scene_plan.json`, a clean
`narration_script.md`, and `review_packet.md`. It does not create the hosted
request, invoke voice, or render media.

### 3. Review and bind approval

Read `review_packet.md` completely. Re-open the source when a claim, number,
label, qualification, or visual meaning is material. Compare each narration
scene with its source basis and image. Remove unsupported language rather than
softening it into an untraceable claim.

Show the narration script and explain that Mparanza will send the exact approved
narration to OpenAI. Images, source-basis notes, Vera artifacts, and local paths
are not part of the hosted request. No user API key is used. The exact narration
still requires approval because it becomes a professional-facing spoken
artifact. The review packet also shows the localized AI-voice disclosure that
remains visible on every scene.

After the user approves the exact script and visual plan, bind that approval:

```bash
python scripts/managed_python_runtime.py run \
  skills/research-video/scripts/research_video.py approve \
  --run-dir <project-output-folder>/research-video \
  --approved-by <reviewer> \
  --confirmed-by-user
```

Any later change to narration, scene order, motion, source basis, or image bytes
invalidates the approval and requires preparation and approval again.
Approval writes `narration_approval.json` and the minimal,
hash-bound `mparanza_voice_request.json`.

### 4. Generate and attach hosted voice

Open `https://mparanza.com/case-notes/research-video/voice`, sign in to
Mparanza, upload `mparanza_voice_request.json`, and download the returned ZIP.
The service uses the server-held provider credential and the fixed policy in
`scripts/video_voice_policy.py`; never request or accept a user API key. The ZIP
manifest follows `references/hosted-voice-bundle.schema.json`.

Attach and normalize the downloaded bundle locally:

```bash
python scripts/managed_python_runtime.py run \
  skills/research-video/scripts/research_video.py attach-voice \
  --run-dir <project-output-folder>/research-video \
  --voice-bundle <research-video-voice.zip>
```

The attachment step rejects path traversal, symlinks, duplicate or undeclared
ZIP entries, unexpected fields, changed request/approval hashes, wrong provider
policy, incomplete scene order, stale WAV metadata, and changed audio bytes. If
the hosted service cannot return the bundle, leave the run
`approved_for_hosted_voice`; do not request an API key or substitute another
voice.

### 5. Render and validate

Render only after approval and hosted voice attachment:

```bash
python scripts/managed_python_runtime.py run \
  skills/research-video/scripts/research_video.py render \
  --run-dir <project-output-folder>/research-video
```

Rendering is local and requires no network access. The renderer consumes the
attached hosted voice artifacts, applies calm professional delivery already
captured in those files, and displays the localized disclosure that the voice
is AI-generated. It produces:

- `research_video.mp4` — 16:9 H.264 video with AAC voice-over;
- `poster.jpg` — first-scene poster;
- `captions.vtt` — scene-aligned captions in the narration language;
- `narration_script.md` — the approved narration;
- `mparanza_voice_request.json` — exact minimal hosted request per scene;
- `hosted_voice_manifest.json` — attached audio provenance, hashes, and duration;
- `hosted_voice/*.wav` — normalized scene-level narration artifacts;
- `render_report.json` — input hashes, timing, voice, media and validation data;
- `final_artifacts.json` — final handoff and readiness state.

### 6. Final semantic review

Watch the complete MP4 and inspect the poster, captions, narration script,
render report, and final artifact manifest. Mechanical validation proves media
shape and byte integrity, not scientific fidelity or editorial quality. Check:

- every spoken claim against its supplied source basis;
- figures, maps, text, labels, and statistics remain legible and uncropped;
- scene order supports the intended research argument;
- motion clarifies rather than distracts;
- transitions do not interrupt speech;
- pronunciation, pacing, captions, AI-voice disclosure, and qualifications are
  acceptable.

If any issue is material, revise the scene plan, prepare again, obtain a new
approval, and rerender. Deliver only when the final review is complete. State
plainly when a flat-image run has no true parallax.
