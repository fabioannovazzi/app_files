# First conversation with Clara

This is Clara's optional, one-off introduction for **Codex desktop**, available
when the user asks to learn or chooses to start it. It can reuse the same profile
in **local ChatGPT Work on the same OS user account**. New and existing users can
use ordinary workflows without starting or completing this introduction. Plugin
updates and new clients never reset saved progress or completion.
This is not client or matter intake: each professional workflow keeps its own
required inputs, review and authorization rules.

For a demonstration, guided practice or discovery request, route to
`../../learn-with-clara/SKILL.md`. A working chat carrying a native teacher's
repeated-session handoff must validate its actual native thread ID, session,
workflow and token with `local_teaching.py worker` before execution. The original
onboarding handoff uses `local_onboarding.py worker`. Neither is inferred from
client files or a claimed worker role. A verified worker performs only the bounded
assignment and returns evidence; it does not restart the interview. Both chats
teach only Clara's own installed workflows. Read the exact Clara skill returned
in `workflow_contract.skill_path`; never substitute another plugin or continue
without a valid handoff. Return outside requests to the teacher for selection
of a supported Clara lesson.

## Entry and local profile

Do not run `local_onboarding.py status` before ordinary work or direct specialist
invocation. Do not require a profile, repeat an invitation or redirect a concrete
professional request into a tutorial. If the user skips, declines, pauses or
leaves onboarding, continue the requested professional workflow immediately.
Keep any existing lesson progress; skipping is not completion.

Only after the user requests a tutorial or chooses the introduction, resolve the
installed Clara root and run
`python3 <clara-root>/scripts/local_onboarding.py status` with the host's local execution tool. Use the shared managed Python
interpreter for lessons. Do not require an API key or create an additional
environment for the interview. The helper uses only Python's standard library
and makes no network calls.

The default directory is `~/.local/share/clara/onboarding` on macOS/Linux and
`%LOCALAPPDATA%/Clara/onboarding` on Windows. It is independent of the current
project, plugin version and `PLUGIN_DATA`. Codex and local Work must read this
same location, not conversational memory or separate host profile copies.
Verify that Work's execution is on the actual local machine and OS account.
If tools cannot access this location, connect the existing directory through
the host's normal permissions. Never interpret denied access, a different
sandbox home, corrupt JSON or a missing enrolled profile as a new user.

These statuses describe only the optional tutorial, never permission to use Clara:

- `required`: no tutorial record exists. The historical status name does not make
  onboarding mandatory. Run `begin` only for the introduction the user chose.
- `interview`: on a request to resume, use `interview_notes` without repeating
  answered questions.
- `teaching`: on a request to resume, use the first unfinished lesson and its real
  outputs and existing chats where available.
- `complete`: reuse the confirmed profile for requested teaching. The current
  request always takes precedence over saved preferences.
- `recovery_required` or a failed command: preserve the existing files and explain
  the issue only when it affects the requested tutorial. The user may recover it
  or leave the tutorial and continue the requested professional workflow. Never
  require recovery, Python setup, profile access or a completed lesson for ordinary
  work; do not reset state or manufacture completion to bypass the issue.

On cloud ChatGPT, mobile or a host without local execution, only the optional
desktop tutorial is unavailable. Continue ordinary work supported by the host and
the selected specialist. Do not create a pretend local profile, start a second
interview in a sandbox, or mark onboarding complete. Cloud chats cannot assume
they can read a desktop profile. Claude Cowork's package omits this tutorial.

Follow explicit user instructions to pause, leave, use an accessibility text
conversation, correct a preference or recover files. Never claim a host microphone
or second window was opened when it was not. Voice, window, course, helper or
profile failures affect only the requested tutorial and never access to Clara.

## Shared teaching process

Read `../../learn-with-clara/SKILL.md` for native voice, the two parallel chats,
interruptions, demonstration, explanation and guided practice. Onboarding uses
that same teaching process with the command contract below. The selected
introduction covers 3–4 workflows, but completion is never needed for ordinary
work. Later teaching uses separate repeatable sessions and
never resets this profile or completion record.

## A short interview

Start naturally: “Prima di cominciare, mi racconti di che cosa ti occupi nel
tuo lavoro e che cosa ti piacerebbe provare con Clara?”

Learn enough to choose useful work: main responsibilities and recurring tasks,
where time is lost, preferred deliverables, software/input formats where relevant,
and the first things they want to try. Ask whether they have already used Clara;
for an existing user, learn what they tried and what they want to improve.
Ask only useful follow-ups, not a fixed questionnaire or a comprehensive firm
survey. Save a short `notes` checkpoint after meaningful answers so interruption
is recoverable. Do not retain raw audio or create an interview transcript file.

Reflect back a compact profile in the conversation and let the professional
correct it. Save `profile` only after confirmation. Store work and preferences,
not client identifiers, credentials, tax records, audio, or unnecessary personal
details. Ordinary native OpenAI conversation processing still applies: local
storage does not mean the model or voice operates offline.

Then read `workflow-catalog.md` in full and select **three or four distinct
operational workflows** using model judgment. Explain each through an outcome
relevant to this professional and ask what they want to try first. They should
not need to know the word “pipeline” or select internal skill IDs. Clara's
registered assignment planner, case director and deliverable reviewer can each
be taught when that is the requested task. Internal assurance stages and
onboarding itself are not additional standalone lessons.
Use the `plan` command to save the agreed sequence with the reason and goal.
Select from the local course catalogue. Brand Fit, Hosted Interview and Research
Video remain unavailable in local teaching because their execution requires
hosted services; do not offer or dispatch them as onboarding lessons.
Do not replace started lessons merely because the app resumed.

## Each onboarding lesson

Use the complete demonstration/explanation/practice process in
`../../learn-with-clara/SKILL.md`. Bind the native pair with `pair`, `start` the
first unfinished lesson, and use this helper's `worker`, `demo`, `practice` and
`finish` commands. Record completion only after all selected 3–4 lessons, the
user’s actual practice and confirmed understanding. Read `tutorial-cases.md` for the real case adapter.
Use `pause`, `resume` and `checkpoint` with the active workflow ID and a short
`next_step` during teaching. Pausing revokes its token and prevents new lesson
steps until resumed. Save `notes` during the interview. Inspect native worker
state before resuming; token revocation cannot cancel an already running command.

The final lesson automatically sets completion only after all three/four lessons
have demo evidence, guided practice and confirmed understanding. Give a short
local recap with the practiced requests and file links. Optional feedback (“Che
cosa ti è stato utile? Che cosa miglioriamo?”) stays in the local `feedback`
field. No survey, receipt, change request, hosted voice interview, automatic
Mparanza feedback or server transmission belongs to onboarding. Do not invoke
`change_requests.py`. Do not publish tutorial artifacts. The enrollment root's
`.clara-onboarding-local-only` marker suppresses the receipt client's transmission
for tutorial reports, including later stamp retries. Keep the marker in place.
Normal native model/voice processing is still the user's OpenAI service.

## Local command contract

Run commands from any working directory using the **absolute installed script
path**. Normally omit `--state-root`; it is for an explicitly selected recovery
or isolated developer test root, not a new profile per host/chat/project.
Do not interpolate spoken text into shell commands. Write exact JSON to a local
file inside the onboarding directory with a file-writing tool, then pass its
quoted path. The helper's stdout is local tool output consumed by the native
model, not an upload to Mparanza.

`status` and `begin` need no input. Every change below uses:

```text
python3 <clara-root>/scripts/local_onboarding.py <command> --revision <latest-revision> --input <local-json>
```

Read the returned revision after each save; on conflict reload and reconcile
instead of overwriting another chat. Only the teacher updates progress; the
worker returns actual output evidence to the teacher.

| Command | JSON input |
| --- | --- |
| `notes` | `{"notes":"Short confirmed facts and the next unanswered question"}` |
| `profile` | `{"confirmed_by_user":true,"profile":{"language":"it","work":"…","interests":"…","experience":"…","preferences":"…"}}` |
| `plan` | `{"lessons":[{"workflow_id":"…","reason":"…","goal":"…"},…]}` (3 or 4) |
| `pair` | `{"teacher_thread_id":"…","worker_thread_id":"…"}` |
| `start` | `{"workflow_id":"…"}` |
| `pause` / `resume` / `checkpoint` | `{"workflow_id":"…","next_step":"Observed state and next bounded step"}` |
| `demo` / `practice` | `{"workflow_id":"…","artifacts":["relative/output.md"],"prompt":"Actual natural request","review":"Observed result and professional checks","execution_record":"demo-execution.json"}` |
| `finish` | `{"workflow_id":"…","confirmed_by_user":true,"understanding":"What the user understood; resolved questions"}` |
| `feedback` | `{"feedback":"User's optional feedback, kept local"}` |

`profile` may update an existing confirmed profile after completion; it never
restarts onboarding. No release version is stored as an enrollment condition.
`profile.previous.json` retains the preceding local checkpoint. If recovery is
needed, inspect and preserve the damaged file, select a valid local copy matching
`enrollment.json`, then use `recover --input <copy>` once the missing destination
is ready. Never erase enrollment or manufacture a completed flag. A stale empty
`.saving` directory may be removed only after verifying no save is running.
If the whole directory was deleted or the OS account changed, the helper cannot
infer historical completion; ask about and reconnect any existing local copy
before beginning again. There is no server recovery or automatic cross-device sync.

For each selected workflow, first reuse the prepared 5–8 minute course described
in `../../learn-with-clara/references/prepared-courses.md`. Read the current
specialist and check the course source fingerprints. Prepared pages do not count
as an executed demonstration, user practice or confirmed understanding.

Before recording demonstration or practice evidence, read
`../../learn-with-clara/references/execution-evidence.md`. Preserve the
actual working-thread run records and generated outputs; the prepared kit
cannot complete a lesson.
