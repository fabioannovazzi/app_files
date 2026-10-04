# Native working-chat button

Use the same course chat control for every Clara course and language,
first introduction, repeatable lesson and resumed session. After the existing
workspace/setup save-and-reload succeeds, inspect the saved chat pair using
native host tools. Reuse its teacher and working chat. Do not create a second
profile, reset progress or substitute a coding subagent.

In the teacher chat, call `course_chat_open` with:

- `state_root`: the exact absolute folder returned by workspace/setup;
- `teacher_thread_id`: this actual native teacher chat ID;
- `workflow_id`, `title`, `goal`: the selected installed Clara course;
- `kind`: `onboarding` for the first unfinished introduction lesson,
  or `teaching` for a repeatable course;
- `revision`: the current profile revision, or current session revision;
- `session_id`: the existing repeatable session ID, when resuming one;
- `mode`: `show` or `together`, and `language`: the selected course locale (`it`, `en`, `fr`, `de`, `es`).

For a fresh repeatable course with no paired chats yet, open the panel before
`local_teaching.py begin`; the confirmed invitation creates and binds that
session. With an existing pair, the panel offers “Riprendi la chat di lavoro”;
reopen the saved worker using native inspection/navigation or restore it if
archived, then begin the requested new session with that actual pair. The host
message API supports only new and active targets: the resume request goes to
the teacher, which reopens the recorded working chat through native tools.
Never claim the chat opened from message delivery alone.

Use `replace_missing_worker: true` only after native inspection establishes that
the saved working chat is unavailable. Keep the teacher, files and lesson state.
Show “Apri la chat di lavoro” and let the learner click and confirm the readable
host request. Do not send raw JSON or user files in the confirmation.

The new working chat must call `course_chat_claim` with the invitation,
`state_root` and its actual native `thread_id` before any work. This verifies
writing, revision, installed product, first unfinished lesson and pair, and
returns the current `workflow_contract` and assignment. Read that exact
`skill_path`. Execute only the teacher's bounded task and return actual artifacts
and state; only the teacher records progress or completion. A stale, expired,
replaced, already claimed or interrupted invitation blocks execution and returns
to the teacher for a refreshed panel. Repeat claims from the same bound worker
reuse the session; they never start another one.

Before a resumed worker executes, run its existing worker validation with the
current token and its own folder-access check. Reopening a chat grants no file
permission. Keep teaching paused while writing is blocked.

If `course_chat_open` is absent or the host does not advertise native new-chat
messages, explain the actual limitation and use the existing native chat/window
controls with the same verified pair and workspace. A browser course outline is
not a native MCP App and must not pretend that it can open a chat. The prepared
lesson content, real pipeline and professional review requirements stay intact.
