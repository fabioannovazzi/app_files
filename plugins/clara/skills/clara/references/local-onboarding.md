# First conversation with Clara

This is Clara's mandatory, one-off onboarding for **Codex desktop**. It also
loads and resumes the same profile in **local ChatGPT Work on the same OS user
account**. An existing Clara user gets this introduction once when no completed record
exists. Plugin updates and new clients never
reset completion. This is separate from opening a professional assignment.

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

Before the first substantive Clara action in every session, including direct
specialist invocation, resolve the installed Clara root from this reference and
run `python3 <clara-root>/scripts/local_onboarding.py status` with the host's
local execution tool. Use the shared managed Python interpreter for lessons.
Do not require an API key or create an additional environment for the interview.
The helper uses only Python's standard library and makes no network calls.

The default directory is `~/.local/share/clara/onboarding` on macOS/Linux and
`%LOCALAPPDATA%/Clara/onboarding` on Windows. It is independent of the current
project, plugin version and `PLUGIN_DATA`. Codex and local Work must read this
same location, not conversational memory or separate host profile copies.
Verify that Work's execution is on the actual local machine and OS account.
If tools cannot access this location, connect the existing directory through
the host's normal permissions. Never interpret denied access, a different
sandbox home, corrupt JSON or a missing enrolled profile as a new user.

- `required`: start in a native Codex teaching chat, run `begin`, then conduct
  the conversation below. If first invoked from local Work, guide the user into
  that Codex chat. Do this for established Clara users too; do not infer completion
  from earlier work.
- `interview`: resume from `interview_notes`, without repeating answered questions.
- `teaching`: reflect the confirmed profile briefly and resume the first unfinished
  lesson, reusing its real outputs and the two existing chats where available.
- `complete`: use the confirmed profile as context for normal routing. The current
  request always takes precedence over stored interests, language or preferences.
- `recovery_required` or a failed command: explain the local access/recovery issue,
  preserve the existing files, and reconnect or recover before proceeding.

On cloud ChatGPT, mobile or a host without local execution, explain that the
first voice introduction needs desktop Codex. Do not create a pretend local
profile, start a second interview in a sandbox, or mark onboarding complete.
After desktop onboarding, cloud chats still cannot assume they can read it.
Claude Cowork is outside this feature; its projected package omits this flow.

This gate is a host instruction with checked local checkpoints; plugins cannot
intercept every native UI action. Follow explicit user instructions to pause,
use an accessibility text conversation, correct a preference or recover files.
Never claim a host microphone or second window was opened when it was not.

## Shared teaching process

Read `../../learn-with-clara/SKILL.md` for native voice, the two parallel chats,
interruptions, demonstration, explanation and guided practice. Onboarding uses
that same teaching process with the command contract below. Keep the first
3–4 workflows mandatory; later teaching uses separate repeatable sessions and
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
not need to know the word “pipeline” or select internal skill IDs. A planner,
validator, adversarial review or onboarding itself is not a standalone lesson.
Use the `plan` command to save the agreed sequence with the reason and goal.
Do not replace started lessons merely because the app resumed.

## Each onboarding lesson

Use the complete demonstration/explanation/practice process in
`../../learn-with-clara/SKILL.md`. Bind the native pair with `pair`, `start` the
first unfinished lesson, and use this helper's `worker`, `demo`, `practice` and
`finish` commands. Keep all required 3–4 lessons and the user's actual practice
and confirmed understanding. Read `tutorial-cases.md` for the real case adapter.
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
| `demo` / `practice` | `{"workflow_id":"…","artifacts":["relative/output.md"],"prompt":"Actual natural request","review":"Observed result and professional checks"}` |
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
