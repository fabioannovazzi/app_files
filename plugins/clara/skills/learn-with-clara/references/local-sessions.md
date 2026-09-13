# Local repeated-session contract

Resolve `<clara-root>` as the directory containing this skill's parent `skills`
and the existing `scripts/local_onboarding.py`. Read the shared profile with that
helper. Never create a separate profile for a task, project, version or host.
Normal repeated sessions use `scripts/local_teaching.py` in the same root.

Use the absolute script path and ordinary local execution. Write spoken text as
JSON with a file-writing tool; do not interpolate it into shell commands.
`--state-root` exists only for an explicitly selected recovery or developer test
root. Normal users omit it. `status` is read-only and returns the current profile,
chat pair and example summaries. Add `--session <id>` for one full checkpoint.

`begin --input <json>` starts one session after mandatory onboarding. Reuse or
pause the current active session before starting another. Paused sessions remain
in the library. Its input is:

```json
{"workflow_id": "reporting-engine", "title": "Confronto con il budget", "goal": "Capire importi, percentuali e limiti", "mode": "show"}
```

Use `mode: together` for guided work. An optional `example_id` selects a completed
session ID or `onboarding:<workflow-id>` as the intent for a fresh run. This copies
no previous result or user approval. The session starts with native voice as the
preference and the last saved pair. Verify that pair through native host tools
before dispatch; update with `pair` if needed.

Every update uses the latest returned revision:

```text
python3 <clara-root>/scripts/local_teaching.py <command> --session <id> --revision <revision> --input <local-json>
```

| Command | Input |
| --- | --- |
| `pair` | `{"teacher_thread_id":"actual-id","worker_thread_id":"actual-id"}` |
| `checkpoint` | `{"next_step":"…","question":"optional user question","voice_preference":"native_voice"}`; `text_requested` only for the user's choice |
| `pause` / `resume` | `{"next_step":"Last observed state and next bounded step"}` |
| `demo` / `practice` | `{"artifacts":["relative/path.csv"],"prompt":"Actual natural request","review":"Observed result and professional checks"}` |
| `focus` | `{"result":"demo","artifact":"relative/path.csv","location":"Sheet / row / section","explanation":"Source-linked explanation","host_result":"queued"}`; host outcome is `opened`, `queued` or `user_confirmed` |
| `use-files` | `{"selected_by_user":true,"sources":["/absolute/selected/file"],"destination":"/absolute/real-work-directory","goal":"Actual requested assignment"}` |
| `application` | Same evidence input as `demo`, with result paths relative to the selected real-work destination |
| `finish` | `{"confirmed_by_user":true,"understanding":"User's demonstrated understanding and checks"}` |
| `feedback` | `{"feedback":"Optional user feedback, kept local"}` |

The native worker validates before every bounded step:

```text
python3 <clara-root>/scripts/local_teaching.py worker --session <id> --thread-id <actual-native-id> --workflow <id> --token <current-token>
```

Use the returned `lesson.directory`, latest shared profile and assignment scope.
The returned `workflow_contract` binds `plugin_id: clara`, the workflow ID, the
absolute Clara `plugin_root` and its `skill_path`. Read that exact skill and keep
the step within its Clara contract. Never resolve a matching name from another
installed plugin. If the skill is absent or the handoff is invalid, stop the
step and return to the teacher; do not generate substitute teaching materials.
A `tutorial` assignment can call the genuine case adapter below. A `professional`
assignment must follow the selected specialist's normal real-client intake and
output contract in `real_work.destination`; it may not use the tutorial adapter.
Teacher/worker tokens coordinate local sessions; they are not host authentication
or permission to ignore the specialist or host's approval requirements.

```text
python3 <clara-root>/scripts/local_onboarding_case.py --session <id> --thread-id <actual-worker-id> --workflow <workflow> --token <token> --phase demo --source <selected-source>
```

Use `--phase practice` after recording the demo. The original onboarding adapter
omits `--session`. The same genuine managed-case setup and specialist commands in
`../../clara/references/tutorial-cases.md` apply. One adapter call creates a new
attempt; inspect `tutorial_case.json` and reuse an interrupted attempt first.

Only the teacher records progress. The worker returns actual artifacts and state.
Pausing, rebinding, resuming and entering real work revoke the previous token.
They do not cancel an already running host task. A changed input, missing file,
changed result, wrong workflow/worker, stale revision or corrupt local state
requires inspection and reconciliation; it is never a new professional profile.

Each session is saved at `<onboarding-root>/teaching/sessions/<id>/session.json`
with `session.previous.json` retaining its prior checkpoint. Tutorial artifacts
live under its `files/`. The library derives summaries from the session files.
For explicit recovery, first preserve the damaged checkpoint, inspect a matching
valid copy, then use `recover --session <id> --input <copy>`. Recovery leaves the
session paused and invalidates old worker tokens. Never delete the enrollment,
mark lessons complete without participation or remove the local-only marker.

## Prepared course material

Before creating lesson materials, follow `prepared-courses.md` and reuse the
source-checked local library. Its renderer does not record demonstration,
practice or understanding; retain the actual session evidence requirements.
