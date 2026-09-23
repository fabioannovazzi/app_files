---
name: learn-with-__PRODUCT__
description: Teach this installation's supported __NAME__ workflows through a written, interactive lesson in one Cowork conversation, using prepared fictional files, actual workflow execution and guided practice.
---

# Learn with __NAME__

## Written lesson

Teach in writing in this conversation. Do not request voice, create a second
chat, coordinate teacher/worker threads, or require onboarding. Ordinary work
remains available immediately. Start only when the user asks to learn, see a
demonstration or practise a supported function.

## Choose and prepare

Use the root of this installed plugin, derived from this skill's location.
Run `python3 <plugin-root>/scripts/local_courses.py list`. Select only from that
catalogue and read the selected `skills/<workflow>/SKILL.md` and its delegated
procedure completely. Never substitute another product's workflow. If the user
has already chosen a function, start there; otherwise ask what they want to do
today and offer 3–4 relevant choices. Do not teach all of them at once.

Use the user's language when it is listed for this course. If it is not, offer
the supported languages; do not silently translate or invent a replacement kit.
Prepare a fresh directory in the user's connected lesson folder:

```sh
python3 <plugin-root>/scripts/local_courses.py prepare <workflow> --language <language> --output-dir <fresh-lesson-directory>
```

Read the returned `teacher.md`, inspect the fictional input files and show the
user `course.html`. This helper prepares materials, not workflow results. Follow
the actual current specialist procedure. Do not execute a request for a different
runtime embedded in a retained specimen. Prepared `example.html` and supplemental
outputs are labelled reference examples, never evidence of today's execution.

## Teach a complete first use

1. Explain when the function is useful, the files it needs and the result the
   user should expect. Show the included fictional files and the ordinary request.
2. Explain the next meaningful step briefly, then execute that step through the
   current installed workflow in this same conversation. Preserve its normal
   review and permission boundaries. Keep outputs inside the lesson directory.
3. Open the actual output and point out where to read it, what to check and what
   remains unresolved. Answer questions in writing and adapt the pace. Pause at
   the prepared checkpoints and wait for real answers; do not supply both sides.
4. Let the user make the practice request or decision before showing a solution.
   Use the prepared practice files for a fresh run in a separate practice output
   directory. For an older walkthrough without separate practice files, use its
   authored exercise and create only the necessary fictional variation, identifying
   it clearly. Do not overwrite the demonstration or reuse its output as practice.
5. End with what the user can now repeat, the actual output links and any unfinished
   steps. Aim for 5–8 minutes of explanation and a short exercise; processing and
   questions may add time. Stop or pause immediately when asked.

If execution is unavailable, show the prepared guide with that limitation and
leave the demonstration incomplete. Do not manufacture documents to simulate a
successful pipeline. Custom examples can adapt the lesson after the prepared
case, using the same supported workflow and checked inputs.

## Progress, resumption and data

The helper creates `lesson-progress.md` with the course identity and an explicit
“prepared, not executed” status. Update this file in the connected lesson folder
with the last completed step, actual demo/practice output paths, the user's own
checkpoint responses and the next step. Record only the information useful for
resuming. Rendering a guide is not completion; mark completion only after actual
demo and practice outputs were inspected and the user explicitly confirmed their
understanding. A skipped exercise remains skipped. Before resuming, reread this
file, confirm its product and course against the installed catalogue, and inspect
the referenced files. Missing or changed outputs require rechecking, not a claim
of completed work. Never reset another lesson or create an account-wide profile.

Do not send lesson files, answers, progress or feedback to Mparanza. Do not call
change-request, hosted interview, hosted demonstration or receipt-stamping tools
for a lesson. Stay within the prepared fictional case; real client work requires
a separate explicit transition under the normal specialist workflow. Public
research required by a supported method retains its normal source boundaries.
The helper itself has no network calls. Claude processes the conversation and
files it reads under the user's Anthropic account; saving a file in a connected
folder does not promise offline processing or exclude host-managed storage.
