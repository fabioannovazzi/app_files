# Task reporting through the local CLI

Use one random UUID per mandate and retain it through retries. Select the process
from `usage/pipelines.json` using the actual request. Nested document steps reuse
that task. Use `agent_test` for acceptance and `user` only for real work.
Run with the managed Python from the installed root:

When transmission is prohibited, set `MPARANZA_INCIDENT_DELIVERY=local-only`
in the environment of **every** CLI invocation, including start, record and
status. Those lifecycle commands do not take a `--local-only` flag. They still
persist the task and pending events; do not replace them with invented lifecycle
records or claim acknowledgements. Also pass `--local-only` to `build-report`.
Keep that setting for retries and reopening; do not flush pending events without
later authorization. Shell variables are not automatically forwarded to another
process such as a host MCP server; this edition uses these local CLI processes.

```
python scripts/workflow_usage.py start --run-id <uuid> --pipeline <id> --host codex --sample-kind agent_test
python scripts/workflow_usage.py status --run-id <uuid>
```

Use the observed host, never infer it from this package. Start before substantive
work. The CLI retains events and uses the existing local identity/outbox and HTTPS
service. Inspect acknowledgements for the same UUID: local saved is not delivered,
and absent Computer ID linkage is unverified. Do not create a new owner to recover.

After delivery record the actual whole-task outcome (`completed` or `failed` only
when justified); an incomplete draft or missing reporting is not a failed task.

```
python scripts/workflow_usage.py record --run-id <uuid> --kind completed
python scripts/workflow_usage.py build-report --run-id <uuid> --input <actual-input.json> --evidence-root <run> --output-dir <run>
python scripts/workflow_usage.py status --run-id <uuid>
```

Read `model-data-report-contract.md` for actual phase evidence and input schema.
The helper preserves the ordinary local report and requests its signed receipt.
Show readable report and actual receipt links. Pending stamping, hash mismatch,
missing measurements or identity verification remain open reporting issues.
Use `stamp-report --run-id <uuid> --report <model_data_report.json> --output-dir <run>`
for the existing report; never rerun professional work to fix reporting.
Reopen saved Markdown/JSON and receipt without recomputing the task.

For actual users only, reserve `record --kind feedback_prompted` once after
delivery and ask for 1–5 stars only if `ask=true`. Explain feedback goes to the
Lucia team. Send only the user's answer using `record --kind feedback --fields
<feedback.json>` with stars, feedback_source=user_chat and optional comment.
Never invent feedback or request it for tests.

Respect current host permissions, including denials. If the CLI cannot write or
transmit, preserve exact pending evidence where permitted, report the limitation
and continue the document task. Do not claim server or Computer ID verification.
See `incident-recovery.md`; unavailable reporting is not a reason to expand access.
