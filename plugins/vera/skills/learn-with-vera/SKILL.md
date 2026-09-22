---
name: learn-with-vera
description: Teach only this installation's supported Vera workflows through a native voice conversation and a parallel working chat that runs real examples. Use for first onboarding, demonstrations, guided practice, discovering what Vera can do, revisiting an example, or applying it to user-selected files. Starts in desktop Codex; Claude Cowork is outside this feature.
---

# Impara con Vera

Help the commercialista obtain and understand a useful result by describing their
work naturally. Use native voice first, a teaching chat and a parallel working
chat. Onboarding is optional: start the introduction with **3–4 distinct tailored
workflows** only when the user chooses it. The user can pause or leave at any time
and use ordinary workflows without finishing. After the introduction this skill
can teach one workflow or a user-chosen sequence anytime.
Do not require the user to know skill names or how to write technical prompts.

## Vera workflows only

Teach only operational workflows listed in Vera's current
`../vera/references/workflow-catalog.md` whose `../<workflow-id>/SKILL.md` exists
inside this same Vera installation. Read that Vera skill and follow its declared
components. Another installed plugin, a similarly named skill, a shared Python
environment or a saved example does not extend Vera's teaching scope. This rule
applies to the teacher, the working chat, first onboarding, repeated lessons and
practice on the user's files.

If the requested skill is outside Vera, say that Vera cannot teach it. Offer
relevant workflows from Vera's own catalog, explain their actual scope, and let
the user choose before preparing materials or dispatching work. Never teach,
invoke or hand off to Clara, Lucia or a standalone plugin as a Vera lesson, even
when that plugin is installed. Do not relabel another workflow with a valid Vera
ID or recreate its method in an improvised script or lesson.

For example, a request for Clara's `reporting-engine` is outside Vera. Vera's
`financial-report-builder`, `variance-analysis` and `management-control-pack` may be relevant
alternatives depending on the goal; none is an alias for Reporting Engine. A
general request to learn reporting can use one of these Vera workflows when its
actual input/output contract fits. Read that contract before making the choice.

## Start from the user's goal

Read `../vera/references/local-onboarding.md` and use its installed-root discovery
and shared OS-user profile. For this user-requested tutorial, if onboarding is
unfinished, explain the optional introduction and follow its interview and 3–4
lesson plan only if the user chooses it. If they decline or want ordinary work,
route directly to the requested specialist. A tutorial setup or recovery error
must never prevent that transition. Never reset a completed
profile or use repeated teaching to manufacture onboarding completion.

For a completed profile, read `references/local-sessions.md`, then run
`local_teaching.py status`. Read the current profile explicitly in Codex and
local ChatGPT Work on the same OS account. Use the user's current request over
stored preferences. Verify actual local access; a cloud sandbox is not the
user's computer. Start this two-thread voice journey in Codex desktop. Local
Work may reuse its saved profile and sessions when the required native controls
and local execution are actually available. Cowork receives no teaching skill.

When the request is open, ask “Che cosa vorresti fare oggi?” If the user says
“Non so cosa chiederti”, offer two or three concrete outcomes relevant to their
confirmed profile. A task already described is the starting point; ask only
missing questions. Interpret meaning with the native model, without keyword
classification or an automatic daily greeting that interrupts ordinary work.

Read `../vera/references/workflow-catalog.md` and the selected specialist skill
completely, including its delegated current procedure. That procedure owns the
input, execution, output and review contract. The teaching kit supplies prepared
fictional inputs and a lesson outline; it never replaces the actual pipeline.

## Prepared teaching kits and live execution · 5–8 minutes

Read `references/prepared-courses.md`. Use `scripts/local_courses.py list`, then
`show` for this product's exact workflow and a supported language. Explain the
function in plain terms: when to use it, which files to provide, what to ask,
what happens, what is delivered, what to review and how to repeat it. Teach a
complete ordinary first use. Technical exceptions belong only where they affect
that use or answer the learner's question. Use the plain workflow title.

Materialize its kit once below the active lesson's local files. Read `teacher.md`
and, when supplied, `execution-request.json`. Open `course.html` as a rendered browser outline in the working
window using the **Browser preview** procedure in `references/prepared-courses.md`
(never `open_in_codex` with `type: "file"` for HTML), then inspect the supplied input files with the user. Import those exact
source files through the real tutorial case adapter. Preserve the returned
input bindings and output directory. Read the active worker contract before
each bounded dispatch and execute the actual current pipeline in that worker.
The teacher stays in the voice chat and follows the worker's verified progress.
Pause at the kit's relevant checkpoints during execution, not as an unrelated
quiz after the explanation. Never simulate the user's answers or participation.

When the worker produces the normal deliverables, open those actual files in its
window. Explain where to start, what the main sections mean, how a finding links
to the inputs and what the user can do next. Rendering the outline produces no
execution evidence and completes no demo. A retained course may include an
`example.html` specimen; explain that it is prepared material, not this session’s
result. When no execution request is supplied, use its `teacher.md`, authored
inputs and the current own-product skill to perform the live example. A prepared input, outline, request or
old execution output is never proof of this session's execution. A missing,
blocked or interrupted pipeline stays pending; do not substitute a generic
report, another product's skill or an invented result to finish the lesson.

Let the user make the short practice request using the supplied practice inputs.
Use a fresh bound case and preserve the demo outputs. Explain and record the
actual practice result, then ask the user to show how they would repeat the
workflow on their work. First onboarding selects 3–4 relevant workflows and
requires demonstration, participation and confirmed understanding for each.
Supporting intake tasks are identified as such in the catalogue; do not inflate
the number of distinct main functions by counting those subtasks or translations.
A later demonstration-only session may end after the demo at the user's choice,
without pretending that practice or understanding was confirmed.

The explanation and a short practice target 5–8 minutes. Processing, questions
and additional practice can extend the session. Adapt spoken pace, depth and
examples to the local profile and current request. Prefer the prepared case;
create a custom variation when it makes the workflow more relevant, explicitly
state the changed fictional facts, validate its supported inputs and execute
it afresh. Do not force identical wording or recreate all materials every time.

If kit or workflow fingerprints differ, require editorial refresh before reusing
that kit. Current product membership and source checks apply to custom examples
too. Normally hosted steps require a separate explicit user choice through the
normal professional handoff; preparation alone never counts as their execution.
Keep the interview, profile, lesson progress and tutorial files local. Do not
silently send teaching data to hosted services to make a demonstration complete.

## Native voice and two parallel threads

Keep one teaching chat and one working chat, reused across onboarding, later
lessons and the transition to the user's files. Inspect the saved pair through
native task read/status tools before creating anything. Resume it when available;
if its working chat is missing or archived, restore it through native tools or
create one replacement with the user's existing teaching authorization where
the host permits. Bind the actual thread IDs and revoke the previous handoff.
Do not take over unrelated tasks or create a hidden coding subagent in place of
the user-visible working chat. Respect any explicit task-creation requirement.

Voice stays in the teaching chat, using the user's native selected voice. Speak
Italian initially and use their preferred language thereafter. If voice is not
active, guide them to **Start voice chat** or **Start new voice chat**. The user
controls microphone permission and the account voice. If unavailable, explain
the actual host limitation and preserve progress; use text when the user chooses
it or needs accessibility support. Do not quietly replace conversation with
speech-to-text dictation, add a custom speech/model API, or call Mparanza.

Show the working chat in a second native window beside the teacher. Use native
window controls when exposed; otherwise guide the user through **Open in New
Window**. Confirm visibility from native evidence or the user. A task ID, queued
panel, screenshot of another app, or “opened” tool response alone does not prove
two windows are visible. Do not promise to start voice or arrange windows without
an available native operation. These setup actions need not be repeated while
the same visible pair remains in use.

Send the worker **one bounded step at a time**: exact session/lesson identity,
workflow, teacher ID, current token, files and intended output. The worker reads
its actual native thread ID and validates `worker` before each new step. Keep
the Vera-only scope in every handoff. Both chats must use the returned
`workflow_contract.plugin_root` and `workflow_contract.skill_path`; the worker
reads that exact Vera skill before preparing inputs or executing its method.
If validation fails, return to the teacher without generating an example or
using another plugin. Revalidate resumed steps; a remembered lesson is not
permission to execute a skill missing from the current Vera installation. Keep
technical IDs and tokens in tool handoffs, not in spoken instructions to the user.
The worker returns real task status, artifact paths, relevant sections and the
review state. Read these and inspect the result before explaining it. Coordinate
through native task tools; no separate API credentials or hosted worker.

## Demonstrate, explain and try together

1. Give one natural request and explain the useful result it should produce.
   Show the required input and the professional choices that remain the user's.
2. Start the selected onboarding lesson or repeated session. Prepare a genuine
   portable tutorial case beneath its local marker using `local_onboarding_case.py`.
   Follow the specialist's complete execution contract, including managed runtime,
   input reviews, validation, model-data report and ledger finalization. Never
   configure the real studio archive to run a demonstration.
3. Execute in the working chat. Keep voice turns short: explain the next decision,
   then listen. Check progress when useful. Do not narrate invented intermediate
   results, drown the user in logs, or keep speaking through a long computation.
4. Inspect the actual output, record `demo` evidence, and open the exact file in
   the working chat's native file/browser panel. Point to a sheet/cell, row,
   figure or document section while explaining the source-to-result connection.
   For repeated sessions record `focus` with the actual panel outcome. If queued,
   say it is waiting to be shown; do not say “you can see” until verified. Recheck
   file identity before returning to a previously explained result.
5. Teach the professional check: what input supports this figure or conclusion,
   what remains uncertain, what would change it and what needs human judgment.
   Passing arithmetic or a script does not certify accounting or legal treatment.
6. Invite a useful next move: another period, changed input or comparison. Let the
   user describe it naturally, run the actual distinct attempt in the worker and
   record `practice`. Onboarding requires this for all 3–4 lessons. A later
   “show me” session can finish after a reviewed demo and confirmed understanding;
   “let's do it together” also requires the user's attempt or real-work result.
   Never simulate their words, participation, approval or understanding.
7. Explain any confusion and save the confirmed understanding. Retain the natural
   requests, reviewed results, professional checks and next step locally. Finish
   only when the requested work is evidenced; pause a blocked or unfinished run.

## Interruptions and pacing

Treat speech as ordinary user steering. “Fermati” stops the explanation and new
worker dispatches. Save a pause checkpoint and revoke the token for further steps;
use the host's stop control if callable, otherwise have the user stop the active
worker. Revoking a token cannot cancel an already executing command: inspect its
state and any partial output before resuming, and report that limitation plainly.
“Più lentamente” changes the pace; “Perché?” explains the current source/result;
“Fammi un altro esempio” prepares a fresh actual example. These are examples of
meaning, not a keyword command parser. A question does not silently replace the
original goal. Save a short next-step checkpoint at meaningful interruptions. Use the original
onboarding helper with the active workflow ID for first lessons, and the repeated
session helper with its session ID afterward; both support pause/resume/checkpoint.

Resume from the real worker state and existing files, refresh revoked tokens,
and finish the interrupted step before issuing a duplicate. Follow native voice
stop/transfer rules; never end the call merely because a lesson is complete.

## “Ora facciamolo con i miei documenti”

If the user wants ordinary work during the optional introduction, pause the
active lesson and route directly to the requested specialist. Preserve unfinished
progress; do not finish other lessons, require recovery or mark completion.
Keep tutorial files under their local-only marker. Have the user select the exact
files and real-work destination through the specialist’s normal intake.
Do not search unrelated client folders or reuse a tutorial token for real work.

After onboarding, use `use-files` to bind the actual selected inputs and separate
real-work destination. Tell the user that the next step is their professional
assignment. It rotates the worker token and changes the assignment from tutorial
to professional; the tutorial adapter must refuse this handoff. The worker reads
the selected specialist and the normal Studio Archive intake/run contract, then
imports the exact bound files into that real assignment. Existing host and
specialist permission/review requirements apply. Choosing files is not permission
to send messages, publish, file, sign or transmit professional material.

Record `application` only from the actual reviewed outputs beneath that selected
destination, and explain the same professional checks. Do not label a tutorial
client as real, remove its local-only marker, move a demonstration report to obtain
a receipt, or carry tutorial exceptions into the professional run. Preserve
interrupted work. If inputs change, review them and start a fresh session/handoff
instead of silently using different files. Normal professional data boundaries
are those of the specialist; the personal tutorial library and feedback stay local.

For the professional assignment entered through the selected-file handoff:

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

The main skill's local tutorial exception always applies to learning: keep all
interview, lesson and teaching feedback local, including after completion. Never
construct or send a change request from the personal teaching record.

## Personal examples and privacy

The local library includes completed onboarding examples and repeated sessions.
For “Rifacciamo quel controllo”, interpret the saved titles/goals and ask only if
more than one example fits. Show the old result on request after inspecting its
current files. Reuse the intent in a **fresh** session; rerun the current skill
on selected inputs. Do not present an old result as a new calculation or assume
its rules, sources, dependencies or user confirmations are current.

Profile, checkpoints, example metadata and optional feedback stay in the local
OS-user directory. Do not store audio or raw interview transcripts. Do not call
hosted interviews, telemetry, `change_requests.py`, tutorial receipt stamping or
publish tutorial artifacts. The existing local-only marker suppresses receipts,
including retries. Optional feedback remains local even after completion.

The native OpenAI account processes the spoken conversation and any profile,
selected files, results or screen context it reads. Local storage is not offline
inference or automatic anonymization. Use the selected specialist's actual data
boundaries when entering real work. No Claude Cowork teaching is added.
