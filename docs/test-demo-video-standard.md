# Standard for test and demo videos

Fabio approved this standard on 2026-10-28 after viewing the remade Vera Test 1
video: "much better. make this the stardard for videos of tests and demos.
write it down somewhere".

Use this format by default for project test and demo videos, including Vera,
Clara and Lucia, unless Fabio requests a different format. Reuse the design
across the campaign; supply each video's actual conversation and results.

## Conversation layout

- Present a polished Codex-inspired conversation window: light canvas,
  restrained header and sidebar, clearly identified user and assistant,
  a user-message bubble and readable assistant responses.
- Show the real request and selected files, then the actual response, result
  tables and deliverable cards. Preserve important limitations and open items.
- Use a small persistent label such as "Replay della conversazione reale" or
  "Replay of actual conversation". Keep the conversation visually prominent.
- Use consistent typography, spacing and colors. Avoid large text-only slides,
  oversized disclaimers, dense tool logs and decorative effects.
- Reveal the conversation in readable stages with short transitions. Remove
  idle time. Adapt the duration to the content; the approved example is 62
  seconds, not a required length for every video.

## Actual evidence

Use recorded visible prompts and answers and the real generated artifacts.
Exact excerpts are allowed when labelled; retain the full visible transcript
and the source message IDs. Do not display a paraphrase as a verbatim message
or invent progress, approvals, UI events or successful outcomes. Keep private
reasoning, credentials and unrelated client material out of the video.

Clearly identify synthetic demo data. A replay of an actual test is an edited
presentation, not evidence of native screen capture. When native capture is
specifically requested as support evidence, a replay does not satisfy that
requirement. Use permitted capture routes only; do not bypass tool restrictions.

Keep pipeline, privacy-report and video outcomes separate. Preserve failed and
recovered blocks in the test evidence even when the short video uses excerpts.
A presentation remake uses the saved results: it does not require rerunning the
pipeline, regenerating a privacy report or issuing a new receipt.

## Reuse and delivery

Maintain one reusable renderer/template driven by a scene or transcript JSON.
For each video retain the visible transcript, selected excerpts, source IDs,
artifact references, source/output hashes and a provenance manifest. Templates
and presentation files are separate from immutable workflow outputs.

Deliver an MP4 in H.264, normally 1920 × 1080 with faststart, plus a preview PNG
or contact sheet. Check full video decoding and inspect representative frames
at full size for readable text, correct tables, wrapping and cropping. Confirm
that displayed statements match the source conversation. These checks concern
the video artifact; they do not create new execution gates for the product.

## Approved reference

- [Test 1 conversation replay](</Users/fabio/Documents/Codex/2026-10-27/vera-0513-tests-video-restart-20261027/outputs/test01/test01-journal-bank-reconciliation-vera-0.1.513-conversation.mp4>)
- [Preview](</Users/fabio/Documents/Codex/2026-10-27/vera-0513-tests-video-restart-20261027/outputs/test01/conversation-preview.png>)
- [Reusable template and commands](</Users/fabio/Documents/Codex/2026-10-27/vera-0513-tests-video-restart-20261027/outputs/conversation-replay-template/README.md>)
- [Provenance](</Users/fabio/Documents/Codex/2026-10-27/vera-0513-tests-video-restart-20261027/outputs/test01/conversation-provenance.json>)

These local artifacts are reference examples. The standard above remains usable
if a historical chat directory is moved or unavailable.
