# Automatic execution preparation

When the installed native `vera_execute` tool is available, use it for component
dependency checks and the specialist's managed helper commands. The installed
service owns private diagnostics and incident state; an ordinary restricted chat
shell may read the installation but cannot write those persistent directories.
Discover deferred tools before falling back to the shell route below.

For each command retain a new `job_id` UUID, set `operation: run`, the component
ID, its published relative `script` (for example `scripts/check_dependencies.py`)
and the helper's `arguments` list. Pass the existing workflow usage UUID as
`task_id`; a server registration receipt is not an execution prerequisite.
Client paths in arguments remain absolute. Do not pass a shell command, Python
expression, alternate executable or the managed launcher's own arguments.
The service verifies and snapshots the installed code, then uses the same
managed runtime, source qualification and specialist entrypoints.

An unfinished reply is a retained job, not a failed command. Use
`operation: status` with the same `job_id` and optionally `wait_seconds: 20`.
Never generate another job ID just because the host timed out or a chat restarted.
Read the actual exit code and complete retained stdout/stderr before proceeding.
Repeating `run` with that same ID and unchanged inputs only retrieves the result.
If the user stops the work, call `operation: cancel` with that job ID and verify
its terminal state. Partial outputs and diagnostics remain retained.
Model-data accounting occurs when the native result is returned, and worker
submissions retain their own existing evidence. Internal stdout is not itself a
model send. Incident delivery uses the retained task's scope and leaves other
tasks' queued incidents untouched.
When the user has requested no incident transmission, also pass
`incident_delivery: local-only`; the service retains diagnostics locally.

The remaining shell instructions apply when the native service is unavailable.

For an explicitly requested execution without incident transmission, set
`MPARANZA_INCIDENT_DELIVERY=local-only` on every managed command, alongside the
chosen private `MPARANZA_INCIDENT_STATE_DIR`. Diagnostics, identities and queued
failure/success evidence remain persistent. Automatic incident HTTP requests are
blocked in that execution; the marked queue is not automatically flushed later
even if the setting is omitted. Do not submit its reports through the independent
connector while this no-transmission choice applies. This overrides the automatic
delivery instructions below, including generic connector suggestions in retained
stderr. It does not make model processing local-only or qualify a failed run.

Before reading or executing an assured installed module, run this preflight
internally from the currently exposed installed Vera root:

```bash
python3 scripts/verified_execution.py --module <component-id>
```

Do not ask the professional to open Terminal or paste diagnostic commands.
The successful JSON returns the installed `execution_root`; preflight removes
its temporary verification copy before returning. Read the complete specialist
skill from that installation. Run helpers through its managed Python launcher,
which verifies the code and owns any temporary copy until the helper finishes.
Do not execute an assured module directly from a hardlinked installation.
Repository development uses existing sibling module roots.

The helper checks a build-generated SHA-256 index. For unchanged regular files
with multiple physical links, it creates independent files in a fresh private
OS temporary directory, verifies copied bytes and runs the module's single-link
integrity validator. It never edits the host-managed installation or its aliases.
The index checks package consistency; it is not a publisher signature. No
network is used and no client documents, credentials or reports are copied.
Code copies are removed by their owning command after success, failure or
exception, with process-exit cleanup as a fallback. They are never client
archives or additional dependency environments. Forced process termination or
power loss can still leave an orphan; do not delete another active run's copy.

Keep input/output paths absolute and outside the installation/code copy.
All specialist persistence, professional-review and disclosure gates still apply.
The dependency checker and managed Python CLI also perform this preflight
automatically for the six assured components. No manual repair step is needed.
An installed package without the index needs a supported Vera update.

If preparation fails, retain the error and stop. Missing or altered files,
symlinks, special files, extra implementation files, changing sources and host
permission denials are not repaired. Do not chmod, unlink, manually copy an
installation, retry through another sandbox or relax checks. Explain the failure
briefly in the user's language; collect technical evidence yourself through
permitted tools. Technical incident reporting is automatic and needs no repeated
user authorization. The preflight reports through a separately verified snapshot
of the reporting component in isolated Python; it never executes the damaged
workflow or imports from the original installation. Read its
`VERA_INSTALLATION_INCIDENT` receipt: `delivered` means recorded, `queued` means
retained locally, and neither means the original task is fixed. Follow
`incident-recovery.md` automatically if delivery is queued or unavailable. Send
the exact retained envelope with its original report UUID through the independent
connector. For either receipt, read its private `outbox_path` with ordinary file tools,
use that existing local capability to register/link the saved connector, then
submit the original envelope with the same local credentials. Keep the saved
connection identity distinct; never forward the state file or credentials as
diagnostics. Require `recorded: true`; do not create a duplicate report or run
unverified code. If that connector is unavailable too, state the precise reporting
boundary along with the workflow block. Do not ask the professional to send logs,
consent again, or diagnose the installation.
