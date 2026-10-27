# Establish the work once; recover the same job

This contract applies to every Vera workflow, including direct specialist
invocation, studio-wide work, standalone work, Codex and Cowork. It governs
prerequisites and operational recovery. It does not invent professional facts,
approve conclusions, authorize external actions or change the requested scope.

## Before substantive work

Establish the actual requested result, available sources, required capabilities
and a writable work/delivery destination. Inspect those requirements together
before starting dependent calculation or drafting. Reuse information, scope and
authorization already supplied; ask only for an unresolved material decision.
Never ask the professional to invent or remember a client, engagement, run or
job ID. Those identifiers are maintained by Vera.

For Archive work, reuse the selected destination and engagement. A general
destination such as **Vari** is valid when the user selects it. Use
`general_workspace: true` when creating or registering such a folder; no legal
name, email or tax identity is required for registration, and its display label
is not a legal identity. Folder creation does not initiate the New Client
professional workflow. Run that workflow only when the task actually requests
client onboarding. General storage does not replace any client facts needed by
the substantive professional question.

For standalone or studio-wide work, retain that route and its task directory;
do not add Archive setup. Check the selected engine's actual capabilities and
source requirements at intake. Do not discover a known storage, identity,
dependency or mandatory-input requirement only after doing the dependent work.

Retain the actual returned destination, IDs, context path, source receipts,
output directory and native execution job IDs. Archive preparation also retains
an owner-private exact run binding independently of session configuration.
If this secondary binding cannot be saved, keep the returned context and resolve
its durable retention before dependent work; do not recreate the prepared run.
Preparation and start return `recovery.status` for an independent owner-private
checkpoint. Verify that it says `retained`; if unavailable, establish an available
recovery location at intake while keeping the existing prepared job.

Before each engagement creation or run preparation, generate a request key and
save it with the exact requested operation in the task's durable working notes.
Supply it as `idempotency_key` (CLI: `--idempotency-key`), including when creating
an explicitly separate run. Reuse that same key and request after an interrupted
tool call or lost reply. Never ask the professional to supply this internal key.
Engagement creation records its intent before directory creation; run preparation
recognizes a committed request before rereading intake sources. A retry returns
the saved identity and current state, without allocating another engagement/run.

## During the work

Passed startup choices stay passed for this job. Every helper inherits the same
scope. Do not ask the user to select the client, destination, sources, language
or other settled choices again because a tool or conversation lost context.
Recover them from the retained job. Do not infer identity from the most recent
run, a filename or another client's work.

Use the exact prepared input copies. Their sealed run input manifest retains
the admitted source identities and receipt hashes; newly prepared runs also
retain source-receipt snapshots. An original moving, disappearing or being
edited later does not invalidate the unchanged run copy. A changed execution
copy is different evidence: preserve it and restore the admitted bytes from a
verified copy before continuing the affected operation. Never silently accept
changed bytes as the original or repeat the whole task to repair one input.

Keep completed stages, decisions, drafts, artifact versions and diagnostics.
Managed commands checkpoint the same run before and after each helper. For direct
file edits or specialist steps outside that launcher, call
`checkpoint_studio_client_workflow` after saving a completed stage (CLI:
`checkpoint-workflow`). Check its returned status. Checkpoints contain admitted
inputs, receipt snapshots, completed outputs and run headers; they are additional
private local copies, with no external upload or automatic deletion.
An unfinished native command is still the same job: query its retained job ID.
A timeout is not evidence of failure and does not authorize another execution.
For an uncertain mutation, inspect its durable outcome before retrying. Reuse
the existing idempotency key and identity; do not create another client,
engagement or run to get past an error.

## When an operation fails

Diagnose the specific failed operation and recover from the last verified
progress. Continue independent work that remains possible. Do not equate one
failed command, unavailable panel, missing optional service or failed report
with a failed professional task. A successful start remains acknowledged even
if its separate privacy-report initialization fails. Keep reporting errors
visible and retry reporting without recalculating the result.

If a save destination becomes unavailable, preserve accessible work in a
suitable already-authorized durable location. If none is established, ask only
where to save it. Retain the original job identity, source receipts, completed
work and pending delivery association; verify saved bytes before claiming the
work is secured. Resume the affected step. Do not discard the result, re-run
completed stages or tell the user to start again because its delivery location
failed. Do not promise that inaccessible bytes were saved elsewhere.
For an unavailable Archive destination, use `restore_studio_client_workflow`
(CLI: `restore-workflow --destination ABSOLUTE_PATH`) with the retained IDs and
an authorized alternate folder. The destination must be new or belong to that
exact interrupted restore. The returned context contains the relocated paths;
continue from those paths. Keep existing artifacts' original bytes and provenance.
Some artifact formats retain absolute source paths: inspect the next helper's
supported relocation/resume operation before using it, and preserve the completed
result even if that helper cannot yet continue from the relocated workspace.

Use maintained recovery operations and actual verified copies. Do not blindly
rewrite hashed artifacts, remove locks, relax host permissions, switch clients,
overwrite uncertain outcomes or disguise a partial result as complete. When a
necessary resource needs the user's action, retain the resumable job and ask
only for that action. Recovery remains part of the current task.
