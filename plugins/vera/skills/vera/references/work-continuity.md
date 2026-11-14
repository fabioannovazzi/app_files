# Establish the work once; recover the same job

This contract applies to every Vera workflow, including direct specialist
invocation, studio-wide work, standalone work, Codex and Cowork. It governs
prerequisites and operational recovery. It does not invent professional facts,
approve conclusions, authorize external actions or change the requested scope.

Archive indexing, discovery, registration, navigation, reporting and recovery
storage are secondary services. Their failure must not block processing or
delivery when selected inputs and an authorized writable working folder are
available. This takes precedence over component instructions requiring Archive
setup, a retained checkpoint or Archive-only output storage as a general
prerequisite. Keep the engine's exact-input and output-ownership checks.
Use Archive normally for Archive-backed workflows. `configured:false`,
`setup_required:true` or `archive_not_configured` at first intake means setup is
missing, not an infrastructure outage. Reuse an already authorized absolute
Archive path; otherwise ask once where to save (including where to create an
already authorized general folder such as Vari), configure that location and
retain it for every stage. Do not ask again whether Archive is permitted, silently
choose a fallback, or postpone this missing location until calculation is underway.
Only after an actual Archive infrastructure failure, read `archive-failure.md` and use its maintained
working-folder route. Do not begin a repeated repair/setup conversation.

## Before substantive work

Establish the actual requested result, available sources, required capabilities
and a writable work/delivery destination. Inspect those requirements together
before starting dependent calculation or drafting. Reuse information, scope and
authorization already supplied; ask only for an unresolved material decision.
Never ask the professional to invent or remember a client, engagement, run or
job ID. Those identifiers are maintained by Vera.

For Archive work, use the single configured **Archivio dello studio**. Reuse the
destination when the current work already has one. Otherwise ask once whether
to file it under a **Cliente** or a **Progetto**, and ask for the name in the
same question. If the user has already supplied the choice and name, use them.
A client folder uses the confirmed client name or an exact existing match. A
project folder uses the user-confirmed project name and is registered with
`general_workspace: true`; it requires no client identity. Do not derive a
customer or project name from an input filename, a test label, or a run title.
Reuse an exact existing destination after checking its identity and scope.
Folder selection never changes the studio's configured Archive root.

### One incarico, one requested job

Client and project are the same filing level. Each incarico has one purpose and
one owning workflow, established from the user's request. Never ask the user to
pick a pipeline from a catalogue. Revisions, calculations, review decisions and
internal workflow stages stay within that incarico. A different assignment gets
a separate incarico and may explicitly reuse the earlier assignment's results.

For every client/project pipeline, establish the assignment **before** substantive
engine work, model generation or delegation. Read `vera_incarico_read`, then call
`vera_incarico_begin` with the exact client, engagement, user purpose and the owning
workflow resolved from that request. Pass this durable identity and returned
working directory to any delegated worker. Generated drafts stay in that working
area (or the already bound engine's run output area). Never generate a result
first and choose its destination only when saving. Standalone work retains its
normal standalone route when no Archive destination was requested.

For a legal opinion, `quesito-legale-fiscale` owns its optimizer and research
stages. Other pipelines use their own maintained workflow identities. A mixed
legacy engagement requires an explicit mapping; do not relabel its run headers.
`vera_incarico_update` uses the read revision to retain continuation and actual
chat associations without overwriting concurrent work.

All pipelines use the same publication contract. After completing their normal
substantive checks, call `vera_incarico_publish_result` for each logical deliverable.
The pipeline supplies a stable `entry_key`, a descriptive label, and **all formats
of that issued revision together**. For example, a report may have Markdown/PDF,
a reconciliation may have a workbook and summary, and a business plan may have
its model and report. Choose grouping from the actual deliverable, not filename
similarity. Verify each SHA-256. Use the entry's current revision (zero initially)
and retain one idempotency key for that exact save. A correction uses the same
entry key and a new revision, including its complete format set. The entry opens
the latest issued version; previous versions remain dated and numbered in Storico.
A lost-reply retry reuses its saved revision and cannot make an old result current.

Do not import generated results as `source` or `support`, and do not make a folder
or entry for every retry or format. Source documents remain sources. Drafts do
not appear as issued results. Publication does not sign, file, approve or send
work externally. Engine run finalization and its existing checks still apply;
publication organizes the deliverables and does not replace those checks.
For already imported legacy outputs only, reference the existing receipt as a
saved result without rewriting it. `vera_incarico_document` opens the exact
selected format/version, including work without a technical run.

If native tools are unavailable, use the maintained Archive CLI: `incarico`
(read/update), `begin-incarico`, `publish-incarico-result` and
`reuse-incarico-result`. Their JSON arguments carry the same complete fields,
formats, digests and revisions; do not fall back to importing generated outputs.

Use `vera_incarico_context` when returning in a new chat, then retrieve the
selected documents needed for the new request. Record the actual host-provided
conversation ID and title after checking it with available native host tools.
Never infer the chat from recency, a directory name or a document filename.
For a local Codex chat use host `codex` and the actual UUID; an empty URL is
rendered using the documented `codex://threads/<thread-id>` format. The chat
link opens history; the saved incarico context supports continuation even if
that chat later becomes unavailable. Do not claim that opening the link succeeded
until observed. Preserve other chat links when associating a new conversation.

To reuse work in a different incarico, use `vera_incarico_reuse_result` with
explicit originating and destination client/project and engagement identities.
Select the exact issued revision and format, digest and label; the source revision
is the issued receipt's `content_sha256` (or the assignment revision for a legacy
result declaration). Repeat for each required supporting format/file. The source
receipt and future engine input bindings retain this origin. Changing the source
later never silently changes a saved receiving job. Existing sealed engine
artifacts also support the `engagement_id` upstream selector in preparation.

For standalone or studio-wide work, retain that route and its task directory;
do not add Archive setup. Check the selected engine's actual capabilities and
source requirements at intake. Do not discover a known storage, identity,
dependency or mandatory-input requirement only after doing the dependent work.

Retain the actual returned destination, IDs, context path, source receipts,
output directory and native execution job IDs. Archive preparation also retains
an owner-private exact run binding independently of session configuration.
If this secondary binding cannot be saved, keep the returned context and continue
the existing job. Use the exact `context_path` on supported Archive native tools,
or `studio_archive.py --context <saved-context> <command> ...` (before the
command). This verifies the same saved run directly without writing a pointer.
For a new calculation stage, pass the preparation context to `prepare-workflow`
and retain the newly returned calculation context for all subsequent operations.
Record “saved locally, Archive registration pending” with that working reopen
route if the secondary pointer is unavailable; do not recreate the run.
Preparation and start return `recovery.status` for an independent owner-private
checkpoint. If it is unavailable, report reduced recovery coverage and continue
with the verified working copies. Retry checkpointing separately without blocking
processing or claiming that the failed backup exists.

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
`checkpoint-workflow`). Record its returned status; failure must not withhold the
saved stage, pause processing or redo completed work. Checkpoints contain admitted
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

Index/search failure leaves explicitly selected files usable. Stop only the
affected filing operation if tidying fails; retain its plan and operation journal
and continue unrelated work. Failed restart/recovery must identify unavailable
saved state; use healthy retained files without asserting missing state was
recovered. Never convert altered evidence into a successful recovery.

Deliver useful saved results even when Archive finalization/registration fails.
Show processing and Archive outcomes separately (for example, "Result completed;
archiving pending") and preserve the exact retry association. Archiving retries
must not rerun calculation or drafting. Privacy reporting remains a separately
visible outcome and never becomes a delivery gate.

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


### Introducing legacy work

For one unambiguous historical job, begin the existing incarico using its known
purpose and owning workflow. Identify any wrongly imported outputs from their
actual contents and prior instructions. Publish them into named entries with
`legacy_input_id` on each explicitly identified old output. This preserves the
original receipt and bytes and keeps the output out of the source-document list.
Do not infer current/issued status from a name such as “Definitivo.” Existing
record dates are evidence of retention; do not invent an original issue date.

For an old container holding unrelated workflows, inventory every run first.
Create and bind the distinct incarichi, then use `vera_incarico_map_legacy`
(or `map_studio_legacy_incarichi` / CLI `map-legacy-incarichi`) with each target
and its exact run IDs. Resolve ambiguous job boundaries from the actual work,
asking only for genuinely missing intent. The code records an explicit mapping
and links in both directions; it never moves or rewrites the old run headers,
inputs or outputs. Continue work in the mapped incarico. Use exact selected
upstream results as sources when creating a new calculation there.


The client/project page lists and reopens existing incarichi; it does not offer
manual fascicolo creation. The user requests work in Vera, and Vera creates the
corresponding incarico as part of that workflow. A result's reuse action prepares
an editable request with exact source references; it does not create an empty
incarico before the user sends that request. In a new Codex chat, use the actual
host-provided `CODEX_THREAD_ID` when available in that chat's execution environment,
and verify that exact ID with the native thread reader. Never use the Archive
service's randomly generated session ID as a conversation identity. Use the
canonical `fields` object returned by the read tool when updating metadata;
keep availability/projection fields out of the saved fields.
