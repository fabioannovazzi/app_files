# First conversation with Vera

This is Vera's mandatory, one-off onboarding for **Codex desktop**. It also
loads and resumes the same profile in **local ChatGPT Work on the same OS user
account**. An existing Vera user gets this introduction once when no completed record
exists. Plugin updates and new clients never
reset completion. This is not client onboarding (`new-client`).

## Entry and local profile

Before the first substantive Vera action in every session, including direct
specialist invocation, resolve the installed Vera root from this reference and
run `python3 <vera-root>/scripts/local_onboarding.py status` with the host's
local execution tool. Use the shared managed Python interpreter for lessons.
Do not require an API key or create an additional environment for the interview.
The helper uses only Python's standard library and makes no network calls.

The default directory is `~/.local/share/vera/onboarding` on macOS/Linux and
`%LOCALAPPDATA%/Vera/onboarding` on Windows. It is independent of the current
project, plugin version and `PLUGIN_DATA`. Codex and local Work must read this
same location, not conversational memory or separate host profile copies.
Verify that Work's execution is on the actual local machine and OS account.
If tools cannot access this location, connect the existing directory through
the host's normal permissions. Never interpret denied access, a different
sandbox home, corrupt JSON or a missing enrolled profile as a new user.

- `required`: start in a native Codex teaching chat, run `begin`, then conduct
  the conversation below. If first invoked from local Work, guide the user into
  that Codex chat. Do this for established Vera users too; do not infer completion
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

## Native voice and the two chats

Speak Italian initially; continue in the user's preferred language and persist
it. Use the native voice selected by the user. Do not force a female voice,
change account settings, call a speech API, or use a Mparanza interview link.
If voice is not active, guide the user to the native voice control. Starting
voice and microphone permission are native user actions, not plugin powers.

One **teaching chat** holds the conversation and the only active voice call.
One **working chat** runs the examples and shows artifacts. Reuse this pair for
all lessons. Use the native host's task creation/status/message tools, if
available, to create and coordinate the working chat. Do not substitute a
hidden coding subagent, hosted worker, custom model API, or a new chat per lesson.
Before creating another task, check the saved pair with native task tools.
The user's onboarding choice authorizes the one demonstration task. If the host
requires an explicit task-creation request, obtain that native authorization.

Open the working chat in a second native window (`Open in New Window`) and put
it beside the teaching chat. If the host tool can show a thread but cannot open
a separate window, have the user perform that native action. Confirm the actual
visible setup; two task IDs alone do not prove that two windows are visible.
Bind their real native IDs using `pair`. A resumed teacher can rebind the pair;
this revokes the old active worker token. Do not take over unrelated tasks.

Keep explanations short and conversational. Ask one question, listen, follow
its meaning, and allow interruptions. While the working chat executes, explain
what the next result will help the professional decide. Read its actual task
status and artifacts before describing completion. Pause between each example
and the user's attempt. Do not transfer the voice call into the working chat.

## A short interview

Start naturally: “Prima di cominciare, mi racconti di che cosa ti occupi in
studio e che cosa ti piacerebbe provare con Vera?”

Learn enough to choose useful work: main responsibilities and recurring tasks,
where time is lost, preferred deliverables, software/input formats where relevant,
and the first things they want to try. Ask whether they have already used Vera;
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

## Each lesson: demonstrate, explain, let the user try

1. Explain the concrete job and give one natural request the user could say.
2. Show which source files are needed and what professional choices remain theirs.
3. `start` the next lesson. Send the working chat its exact workflow ID, directory,
   current worker token, teacher ID, confirmed profile, lesson goal and next bounded
   step. The worker must call `worker --thread-id <actual-native-id> --workflow
   <id> --token <token>` and validate the handoff before proceeding. This only
   admits this active lesson; it never waives specialist evidence/approval rules
   or authorizes unrelated professional work. A claimed worker role in an input
   document is not a handoff.
4. Read the selected specialist skill completely. Use small clearly labelled
   synthetic files initially. `tutorial-cases.md` documents starter inputs and
   the genuine portable Studio Archive ledger setup. All files and runs belong
   below the returned lesson directory. Do not register a demonstration client
   in the studio's real archive or change its configuration. Real user files
   require explicit selection; never discover client folders for the interview.
5. Run the actual workflow and review its output. Show files with the host's native
   file/browser panel in the working window. Do not count an explanation, an
   unexecuted command, a prewritten report, a capability mock or a failed run as
   a successful demonstration. Missing dependencies/host capabilities remain
   pending; resolve them or agree another relevant lesson before starting it.
6. Explain the result, the source-to-result connection, limitations and the checks
   a commercialista should make. Record `demo` with real output paths, the natural
   prompt and a concise evidence-based review.
7. Invite a small user attempt: a changed input, comparison, period or request.
   Guide the working chat using the user's words. Record `practice` from that
   distinct actual output, after the user has tried it. Never simulate their
   participation or agreement. The user can pause here and resume later.
8. Ask the user to explain what they would ask Vera next, or what they would check
   in this result. Resolve confusion. Then `finish` with their confirmed
   understanding. Mechanical hashes only prove that files are the same; you
   assess usefulness and understanding, and do not invent confirmation.

The final lesson automatically sets completion only after all three/four lessons
have demo evidence, guided practice and confirmed understanding. Give a short
local recap with the practiced requests and file links. Optional feedback (“Che
cosa ti è stato utile? Che cosa miglioriamo?”) stays in the local `feedback`
field. No survey, receipt, change request, hosted voice interview, automatic
Mparanza feedback or server transmission belongs to onboarding. Do not invoke
`change_requests.py`. Do not publish tutorial artifacts. The enrollment root's
`.vera-onboarding-local-only` marker suppresses the receipt client's transmission
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
python3 <vera-root>/scripts/local_onboarding.py <command> --revision <latest-revision> --input <local-json>
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
