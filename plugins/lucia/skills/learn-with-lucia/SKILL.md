---
name: learn-with-lucia
description: Teach a supported Lucia workflow through a native voice conversation and a parallel working chat that runs real examples. Use for first onboarding, demonstrations, guided practice, discovering what Lucia can do, revisiting an example, or applying it to user-selected files. Starts in desktop Codex; Claude Cowork is outside this feature.
---

# Impara con Lucia

Help the lawyer obtain and understand a useful result by describing their
work naturally. Use native voice first, a teaching chat and a parallel working
chat. Preserve mandatory first onboarding with **3–4 distinct tailored workflows**;
afterward this skill can teach one workflow or a user-chosen sequence anytime.
Do not require the user to know skill names or how to write technical prompts.

## Start from the user's goal

Read `../lucia/references/local-onboarding.md` and use its installed-root discovery
and shared OS-user profile. If onboarding is unfinished, follow its interview
and 3–4 lesson plan using the teaching process here. Never reset a completed
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

Read `../lucia/references/workflow-catalog.md` and the selected specialist skill
completely. That current skill is the teaching source of truth. Read its current
input, execution, review and host requirements before promising a demo. Build or
select a small fictional case that actually exercises that workflow; use
`../lucia/references/tutorial-cases.md` for the product-specific
starters. Other workflows require their own real supported inputs and execution.
Do not substitute a prewritten report, mocked capability or unrelated easy
workflow for the requested one. An unavailable host capability stays pending;
explain what is needed and retain the goal.

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
   input reviews and specialist validation. Clara uses its advisory project/output
   contract; Lucia uses the private matter ledger where required. Finalize an
   actual ledger run only when that specialist requires one. Never
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

Keep the pair and the conversational explanation. Have the user select the exact
files and real-work destination. Do not search unrelated client folders. During
mandatory onboarding, complete the selected practice in the isolated lesson from
explicitly selected copies, then finish all 3–4 lessons before ordinary work.

After onboarding, use `use-files` to bind the actual selected inputs and separate
real-work destination. Tell the user that the next step is their professional
assignment. It rotates the worker token and changes the assignment from tutorial
to professional; the tutorial adapter must refuse this handoff. The worker reads
the selected specialist and the normal specialist intake/run contract, then
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

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../lucia/SKILL.md`.

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
publish tutorial artifacts. The compatibility local-only marker suppresses shared receipts,
including retries. Optional feedback remains local even after completion.

The native OpenAI account processes the spoken conversation and any profile,
selected files, results or screen context it reads. Local storage is not offline
inference or automatic anonymization. Use the selected specialist's actual data
boundaries when entering real work. No Claude Cowork teaching is added.
