# Required course file access

This is a prerequisite for every course, every workflow and language, first
onboarding, repeated lessons, demonstrations and resumed practice. Apply it
before the interview, lesson explanation, window/voice setup or first exercise.
It does not make onboarding a prerequisite for ordinary professional work.

## Verify before teaching

1. Resolve the installed product root and run
   `python3 <product-root>/scripts/local_onboarding.py workspace`. This read-only
   command returns the exact shared `workspace_directory`, `state_root` and
   `setup_argv`. Preserve that root across both chats and later sessions. It is
   independent of the plugin install directory and the current client project.
   Never create another profile to escape denied access.
2. Establish the course workspace as described below, then run the returned
   `setup_argv` with the host's actual local execution tool. Setup uses only the
   standard library: it creates the requested tutorial's enrollment if absent,
   saves and reloads the actual profile, and returns `status: ready`, `workspace`
   and `course`. It does not ask an interview question, advance a lesson, change
   the saved revision or reset an existing profile. Require exit code 0 and
   `status: ready` before teaching. `workspace` and `status` are read-only and
   cannot establish write access. For a repeated lesson also run
   `local_teaching.py preflight --state-root "<state_root>" --session <id>`.
3. Add `--directory "<exact-course-or-output-directory>"` for each actual lesson,
   case/output or required runtime directory as it becomes known, before using
   it. Check existing lesson directories on resume. Use only the chosen course's
   directories, never unrelated client folders. Confirm any other prerequisite
   required by the specialist before offering an executable lesson.
4. Run `local_onboarding.py preflight --state-root "<state_root>"` with those
   extra directories and require exit code 0 and `status: ready`. The helper
   creates a unique temporary subdirectory and verifies create, write, read-back,
   update, replacement and deletion there. It leaves existing files unchanged and
   does not start or complete a lesson. Approval, a readable folder, a writable
   parent or a previous successful session is not proof of current access.
5. Each working chat must pass its own check after handoff validation and before
   executing. The teacher's permissions and test result do not transfer to it.
   `worker` checks its local storage before returning an executable handoff.

Do not start or advance teaching while any required access check or save is
blocked. Do not ask the learner to formulate a request, prepare an exercise,
review a lesson outline or continue a text-only/theoretical version meanwhile.
Text instead of voice changes only the conversation medium, never this gate.
Window confirmation and microphone approval do not authorize filesystem access.

## Establish the course workspace once

Use the active host's actual filesystem scope, not the shell's current directory,
to see whether the returned course folder is covered by write access. If it is,
run setup directly; do not interrupt the user with a redundant permission question.
If scope is unknown, let setup test it. Do not use `os.access` as evidence.

If the folder is outside the writable scope, request write access to **that exact
folder and its course subdirectories** through an available host permission tool.
Prefer a grant covering the course session. State what it saves: course inputs,
progress and results. Do not request the whole home folder, AppData, arbitrary
Python execution or Full Access. A one-command approval is not a session grant.

If the host only offers individual command approvals, guide the user through its
actual project/folder picker to open `workspace_directory` as a **local course
workspace**, then use that same workspace for the teaching and working chats.
This connects the existing folder in place; no course files are moved or copied.
If the folder does not exist, request one bounded approval to create that exact
folder first, then select it. Do not start a Git worktree or initialize a repository.
Use native project tools when exposed; otherwise describe the visible installed
host control and give the exact path to paste. Do not claim a picker or project
was opened without tool evidence or the user's confirmation. Merely running `cd`
inside an arbitrary chat does not change its filesystem grant.

After connecting, run setup again **with normal sandbox permissions** in that
workspace before continuing. This verifies that subsequent saves work without
requiring a special one-off approval for each course step. If normal access is
still blocked, inspect the returned error and follow the recovery steps below;
opening a folder cannot override a managed restriction or OS denial.

Pass the returned absolute `state_root` explicitly to **every** onboarding,
teaching and tutorial-case command, including the working chat. Keep it in each
handoff together with the saved identifiers. Both chats must use this same local
workspace or each hold a verified grant for it. Reusing an old worker in an
unrelated project is not enough. Reconnect the original workspace on resumption;
do not start a new profile in the currently open client project.

## Resolve access with the user

Explain in the user's language what must be saved, show the exact directory,
and identify the failed operation. Example (translate for other languages):

“Prima di iniziare dobbiamo consentire a Vera di salvare i file del corso
in [cartella]. La verifica di [operazione] non è riuscita. Ti guido
nell'autorizzazione e riprovo; il corso resta fermo finché il salvataggio funziona.”

Explain that this is access for the course folder, not evidence that Windows
cannot save files. Word and a sandboxed chat can have different access scopes.
Use the actual error and active host controls to choose the next step:

- **Host sandbox approval:** issue the host's real permission request for the
  exact directory/operation. On the Windows desktop app, the permission selector
  under the composer is **Ask for approval / Chiedi approvazione**. If needed,
  guide the user to that mode, then issue the request and ask them to approve the
  displayed operation. The selector itself grants no access, and a verbal “yes”
  is not a completed host grant. Prefer a directory-scoped grant when supported;
  otherwise request the bounded command through the available approval tool.
- **After approval:** retry through the host's actual grant mechanism, then run
  setup with normal sandbox permissions. If only the escalated command works,
  establish the course workspace above before teaching; do not repeat approval
  requests for every save. An approved one-off command does not permanently grant
  later commands or the other chat access. Continue only after normal setup AND
  the required course save succeed in each chat's applicable scope.
- **Approval denied or unavailable:** explain the actual notice and the specific
  permission that remains missing. Keep teaching paused. Do not silently fall
  back to unsaved work, a cloud copy, another folder or blanket full access.
- **Approved retry still fails:** show the exact command, folder, failed operation
  and native error code. Do not label every `PermissionError` a Windows defect,
  antivirus block or administrator problem. Distinguish sandbox setup failure,
  filesystem permissions, disk errors and invalid paths from observed evidence.
  For a demonstrated Windows sandbox setup failure, guide the user through its
  setup prompt and administrator approval, or their IT administrator if managed.
  For a demonstrated folder ACL denial, have IT inspect that exact folder in
  File Explorer > Properties > Security and grant only the required identity
  access. Do not guess the sandbox identity, disable security software, change
  ACLs broadly or tell everyone to run the app as administrator.
- **Not enough evidence:** request only the exact error/approval notice needed to
  select the remedy. Keep the learner at setup until the retry works. Explain
  any probe cleanup failure using its returned path; do not delete course data.

On macOS/Linux use the current host's matching permission controls and observed
error; do not give Windows instructions. If even the helper cannot start, its
launch error is the blocker and absence of JSON is never a successful check.

A later failed save immediately stops new teaching steps and dispatches. Preserve
existing files; save a pause checkpoint only if storage permits, otherwise say
that the pause could not be saved. Resolve access and recheck before resuming
from the last verified checkpoint. The user may leave the course for ordinary
work; do not describe that choice as course progress or completion.

Official host guidance (verify the installed host's controls if they differ):
- https://learn.chatgpt.com/docs/windows/windows-app
- https://learn.chatgpt.com/docs/windows/windows-sandbox
- https://learn.chatgpt.com/docs/agent-approvals-security
- https://learn.chatgpt.com/docs/permissions
