---
name: studio-archive
description: Use when Vera must create or resume a durable client engagement, import a source, journal, or support file, search one client's callable Gmail connector, inspect a capability-gated WhatsApp Desktop chat, or search connected studio documents without mixing clients.
---

<!-- VERA_WORK_CONTINUITY_BEGIN -->
## Work continuity

Before substantive work, read `../vera/references/work-continuity.md` (from the
Vera root skill, `references/work-continuity.md`). Resolve prerequisites upfront,
retain passed choices and the exact job context, and recover failed operations
without discarding progress or making the user repeat settled setup. This also
applies to direct invocation, standalone work and studio-wide workflows.
<!-- VERA_WORK_CONTINUITY_END -->


<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->
## Connected studio knowledge

When the user or an adopted studio instruction requests relevant repository
evidence, read `../vera/references/connected-studio-knowledge.md` before the
dependent work, including direct specialist invocation. Use only callable host
search/read tools; preserve citations and this workflow's qualification gates.
Without a repository, continue ordinary work. Studio skills remain independently
invoked by the user; Vera does not dispatch them.
<!-- VERA_CONNECTED_KNOWLEDGE_END -->

<!-- VERA_OPENAI_ONBOARDING_BEGIN -->
Onboarding is optional. Continue ordinary professional work immediately,
including direct specialist invocation, without checking or completing a local
onboarding profile. Missing, unfinished, inaccessible or corrupt onboarding state,
or unavailable voice/window controls, must never block ordinary work. Do not
automatically start, resume or repeatedly offer onboarding.
Only for a user-requested tutorial or a native teaching handoff, read
`../vera/references/local-onboarding.md`. A verified paired lesson worker
executes only its bound lesson and token; never bypass tutorial validation.
Tutorial profiles, progress, examples and feedback remain local; never send a
change request, stamp a tutorial receipt or call hosted interviews for a tutorial.
Current user requests take precedence over saved preferences.
<!-- VERA_OPENAI_ONBOARDING_END -->

## Surface routing

In ChatGPT, continue with connected Gmail when its read tools are callable and
with material supplied in the conversation or an existing callable studio
knowledge repository, following the shared connected-knowledge reference.
WhatsApp Desktop control and local archive indexing remain Codex Desktop
capabilities. For those local routes,
complete any useful preparation or review available in chat, recommend Codex
using the localized wording in `../vera/SKILL.md`, and continue in ChatGPT.

# Archivio dello Studio

For work starting from supplied files, first follow "Check supplied files before
starting client work" in `../vera/SKILL.md`. Call `check_studio_import_sources`
on every selected path before processing attachments or creating a client,
engagement or run. Report an unavailable chat upload immediately and explain
the supported host transfer or folder route. Verify transferred originals with
`expected_sha256`; never manually write the managed inputs directory. Reuse and
disclose any existing client and
engagement IDs after a later import failure; do not duplicate them.

For a user-authorized external folder delivery into a selected client's working
area, use the component's `copy_studio_client_source_folder` operation. It
preserves the tree outside `Vera/` for Archive Organization and retains a copy
receipt. Single-document engagement imports remain a separate route; they are
not a substitute for the working-folder delivery. Reuse the selected client,
engagement and explicit copy authority; do not ask again for settled choices.

For a Geneva (CH-GE) mandate, read `../vera/references/localization/geneva.md` first and use this existing function’s Geneva adaptation in its resolved component skill. Language alone never selects jurisdiction.


After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

For the local client-work route, the customer folder is the portable source of
truth. Client selection, engagement creation, immutable import, exact run
preparation, start, bound execution, artifact finalization, review/completion,
recovery, rename handling, and retention must remain separate explicit steps.
The machine-local index and configuration are rebuildable aids, not the run
ledger.

Use the returned completeness flags when discovering clients or resolving names.
`directory_complete: false` or `identity_registry_complete: false` does not mean
the archive is empty. Report the listed issues and continue with healthy selected
clients. A name lookup with `resolution_status: incomplete` cannot establish
absence; reuse an established stable client ID and validate its folder rather
than register it again. Previously known folder locations can support recovery
when root listing is unavailable, but do not replace current identity validation.

For local archive delivery, show the generated `readable_archive.index_path`
(`Vera/APRI ARCHIVIO.html`) and the dated, named folders under `Vera/Pratiche/`.
These are portable, rebuildable navigation pages, not a replacement for the
exact `engagements/` ledger. A completed execution does not imply professional
approval. Check the returned readable-view status before claiming navigation
is available.

For a resumed local engagement without a specialist run, preserve a generated
follow-up as a clearly identified Vera-derived support note through the shared
component's `import_studio_client_document` route. Re-list that engagement,
then call `verify_studio_client_inputs` for the exact saved input IDs before
claiming progress is saved. Copy prior `input_id` / `content_sha256` pairs
from the import or verification response into `expected_receipts` to check
preservation; never invent a baseline. Require `verified: true`. Read the
controlled document for semantic work using the returned verified receipt's
`path`; byte verification alone is not a semantic read. Never write an ad hoc
verifier or assume raw `receipt.json` / `engagement.json` has the fields of
the maintained listing. Return the
archived copy, not only a memo in the chat workspace. Exact retries reuse its
receipt; changed notes preserve earlier copies. Do not invent an archive run
or bypass a specialist run's output/finalization contract. Read the component's
complete follow-up preservation steps before doing this work.

When the Codex native workspace is callable, read
`../vera/references/native-workspace.md` and open “Lavori dello studio”. Its
ordinary directory uses this workflow's owned local archive session and portable
client ledger. If setup is required, the panel offers the maintained operating
system folder chooser, accepting no path from browser/model content. Cancellation
does not save configuration. Navigate client, engagement and exact run explicitly;
refresh/recovery uses the unchanged archive service. Private contacts remain in
the existing registry. Unregistered folders require confirmed client registration
through the specialist route; the panel does not register them automatically.
The panel can create an explicitly labelled engagement for a registered client,
import explicitly selected file bytes, list verified imported receipts, prepare an idempotent run with an explicit
workflow/input/label/purpose choice, and move one prepared or failed run to running.
These app-only actions require the exact displayed signed scope, current receipts
and reviewer authority, and use this workflow's maintained APIs. Creation retains
a separate native request receipt: identical retries reuse the engagement, while
an interrupted uncertain outcome requires archive verification before another
request. Preparation and start do not execute a specialist engine, qualify
sources, approve a result or complete a run. Workflow choices come from the
maintained Vera engagement gate; excluded prototypes remain excluded.
“Importa documenti” requires a file selection and an explicit journal, source or
support role for each file, then confirmation of the displayed engagement.
It transfers at most 64 MiB per file in 64 KiB chunks, verifies the complete
selected-file digest, and calls the unchanged public importer. The browser
does not supply the original OS path; transport receipts say so. Original files
remain unchanged. Reopening shows retained bytes and roles without restoring
confirmation. Resume only the same selected bytes; explicitly complete a known
interrupted import intent through the same public deduplication gate. Changed,
unreceipted or foreign state requires specialist verification. A pending write
blocks new imports and new run preparation until resolved. Importing does not
classify or inspect the document, select it for a run, or start a workflow.
Larger files use the maintained specialist import. File bytes pass through the
selected host's app/tool channel; this route makes no separate model call or
external connector request. Later workflow reads have their own data path.
“Appunti del colloquio” retains the user's complete literal text, optional declared
speaker and chosen JSON basename in a private recoverable draft. No questionnaire
answers, speaker identity or company evidence are inferred. Explicit conservation
captures one immutable `vera.user_statement.v1` original with the actual capture
time, configured actor/tenant/client/engagement references and unverified
attribution, then uses the same complete-byte public import. Capture time is not
the date when a fact happened or became known; a statement is not independent
evidence of truth, adoption or operation. Recovery reopens that exact original
without restoring confirmation or generating a new timestamp. Clearing the draft
keeps captured originals and imported receipts. Text above 256 KiB uses original
file import without excerpts. Choose the source and workflow separately to prepare
and start a run. Notes and metadata pass through the selected host; later selected
workflow reads may place them in model context without automatic anonymization.
For a running maintained run, “Output e chiusura del run” lists every physical
output in pages, including working requests, versions and the actual run-bound
model-data JSON/Markdown report. Declare each file's reuse reference, purpose,
audience and media type explicitly; no filename-based classification or default
deliverability is inferred. Unfinished declarations remain private local drafts
outside official outputs, with owner/run/output and concurrent-draft checkpoints.
Recovery is explicit and never restores confirmation; changed outputs require
explicit discard or specialist recovery. The panel validates the existing
report's schema, evidence, run identity and exact rendered Markdown. It never
interprets missing telemetry as zero exposure. For the 13 selected pipelines,
Archive start initializes the report and Vera's own producers record outgoing data.
Completion, failure or cancellation freezes the local report and requests its
hash proof bound to the existing Vera userID and the same Archive run.
Finalization requires all files and a separate confirmation and calls the
unchanged Archive finalizer to produce ready-for-review status. Completion is
another explicit action over revalidated sealed outputs; it does not attest
professional approval, valid accounting/legal conclusions, signature, filing or
delivery. Each request has a durable private intent/outcome. Successful exact
retries revalidate the manifest; interrupted or changed outcomes require
specialist verification without replay or automatic adoption. Concurrent
specialist writes can leave a sealed result requiring that verification; the
native panel does not roll back the authoritative ledger.
The native preparation page also lists verified sealed artifacts from ready or
completed runs in this same engagement. Explicitly select each artifact and
author its role in the new run. The maintained preparer verifies its receipt and
bytes again and preserves directory structure, including reviewed invoice source
groups. Invalid upstream runs remain unavailable rather than becoming sources.
Specialist source qualification, bound execution,
engagement closure, cancellation/failure and recovery remain on existing
specialist routes. Missing native tools never
block those persistent routes, including in Cowork. Operator-bound development
pilots retain their explicit allowlist and do not adopt another archive session.
After destination loss, use `restore_studio_client_workflow` with the retained
IDs and an authorized alternate folder, then continue from its returned context.
Checkpoint direct edits with `checkpoint_studio_client_workflow`. Treasury
resolves its saved source references against exact admitted inputs after a rename
or restore, preserving the original session and forecast bytes. Other engine
formats may still need their maintained relocation route; inspect that route
before claiming continuation, and keep completed results available.

Choose the route before resolving any module:

A fresh session reuses the last explicitly approved root from the owner-private
profile after access revalidation. Existing sessions keep their own pinned root,
run selection and index. Confirmed aliases persist privately per archive root;
raw aliases are not returned in the safe client directory. If no approved root is
available, say “the archive location is not connected”; do not say the client is
unregistered or propose New client until the archive has been listed. Reuse an
existing client/engagement and the user's established choices. Before the first
copy, consolidate the selected client, engagement, sources and write permission
into one concise confirmation; internal ledger steps remain separate.


1. When the user asks to inspect WhatsApp messages, confirm that Computer Use
   can control the local WhatsApp Desktop application on the same computer.
   - If it is available, read `references/whatsapp-desktop.md` completely and
     follow it. Do not resolve the local document module as a workflow or call
     its MCP. Resolve only the bundled Studio Archive
     `scripts/whatsapp_desktop_guard.mjs` named by that reference; do not call a
     WhatsApp MCP server, use a browser, or run any other WhatsApp script.
   - If it is unavailable, explain that message inspection requires Codex
     Desktop, Computer Use, and the user's already-authenticated WhatsApp
     Desktop application. Complete any useful scope or question preparation in
     chat, use the localized Codex recommendation in `../vera/SKILL.md`, and
     continue the conversation. Do not fall back to WhatsApp Web, a Mparanza
     server, exported chats, or an unofficial API.
2. When the user asks to search Gmail or email, check whether Gmail
   `get_profile`, `search_emails`, and `batch_read_email` are callable.
   - If they are callable, read `references/marketplace-gmail.md` completely and
     follow it. Do not resolve the local module, call Studio Archive MCP tools,
     or run local scripts.
   - If they are unavailable, say that the separately distributed OpenAI Gmail
     connector must be installed, enabled, and connected on the current
     surface. Do not use IMAP, browser scraping, or ask the user to save `.eml`
     files.
3. When the user asks to search an existing connected studio knowledge
   repository, follow `../vera/references/connected-studio-knowledge.md` using
   its callable search/read tools. This route needs no local document module,
   archive configuration or Microsoft 365 account. Keep Gmail and WhatsApp on
   their dedicated routes above.
4. When the user asks to identify or create a client workspace, import or
   resume a source, journal, or support engagement, or configure, refresh, or
   search local studio documents, resolve `../../modules/studio-archive` from
   this skill directory when it exists; otherwise resolve
   `../../../studio-archive` in the repository. Read that module's
   `skills/studio-archive/SKILL.md` completely and follow it. Treat the resolved
   module root as the plugin working directory for local commands, scripts,
   requirement files, MCP tools, and archive state.
   When `list_studio_archive_clients` reports `configured: false` and
   `setup_required: true`, tell the user that Vera will open the operating
   system's folder chooser and call `setup_studio_archive` before asking for an
   absolute path. Request a path manually only when that guided action returns
   `archive_folder_picker_unavailable`; cancellation means no configuration was
   written and should lead to an offer to reopen the chooser.

The Gmail, WhatsApp Desktop, connected knowledge, and local document routes
are independent. Gmail uses OpenAI's separately connected connector in ChatGPT
or Codex. WhatsApp is
an on-demand view of the local application through Computer Use. There is no
Vera or Mparanza WhatsApp webhook, background sync, hosted connector, message
database, or retention period. WhatsApp content read for the task may still
enter the model context of the user's selected Codex or ChatGPT account.

## Authored files and execution prerequisites

Use `write_studio_run_artifact` to persist agent-authored drafts, JSON recipes or Python adapter source in
one exact running run. It writes only `outputs/authored/<name>`, returns the
actual path and SHA-256, and never modifies imported inputs or specialist
receipts. Repeating the same name and bytes returns the same artifact; changed
content needs a new name. CLI fallback: `studio_archive.py write-run-artifact
--client-id <id> --engagement-id <id> --run-id <id> --name <filename>
--content=<complete text>` through the managed Archive service (one argv
argument, or `--content-stdin` when the host supports stdin). Do not invent
source lineage for authored text. Always pass the returned path to consumers;
do not assume another output subfolder. This saves source code but does not
execute it: use the specialist's maintained adapter/trial entrypoint. Finalize
its returned path normally.

For Vera's saved terminal privacy reports, use `verify_studio_run_report` with
the exact client, engagement and run IDs. The service performs the read-only
network verification without a chat-shell command. An `unavailable` result is
a reporting issue, not a failed calculation: deliver the existing result and
report the verification gap. Retry the same verification without regenerating
the report, restamping it, or creating a new run. A saved local-only choice
returns `not_requested` without contacting the receipt server.

Wait for each required write to succeed before launching its consumer. A denied
or failed write is not a completed prerequisite. Preserve the same client,
engagement and run; resolve access through the owning service or normal host
approval, then retry the exact operation. Never create a replacement run merely
because a write failed. Poll an unfinished execution with its existing job ID;
a new job is appropriate only after a confirmed terminal failure and correction.

The on-disk `context.json` is a sealed, portable reference, not the expanded tool
response. It deliberately points to `input_manifest.json` and contains no
`input_bindings` or machine-specific absolute source paths. For helper code use
`vera_assurance.load_client_engagement_context_file(path,
expected_workflow_id=..., output_dir=...)`; it verifies and hydrates the manifest
and current receipts before returning `input_bindings`. Archive tools already
return this expanded projection. Do not parse raw context JSON as that projection
or bypass the loader by constructing unverified paths from the manifest.
