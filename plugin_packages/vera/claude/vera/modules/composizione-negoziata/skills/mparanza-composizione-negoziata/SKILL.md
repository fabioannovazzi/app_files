---
name: mparanza-composizione-negoziata
description: Guide an Italian composizione negoziata case as company advisor or independent expert, using existing Vera analyses, evidence-linked drafts, persistent case revisions and change-impact review.
---

## Cowork execution contract

Select the exact files needed for this request. Folder access does not select
all its contents: if the task needs two files in a folder containing four, use
only those two. Resolve genuinely ambiguous choices with the user; reuse clear
choices without another confirmation.

Before parsing documents or creating a client, engagement or run, call
`check_studio_import_sources` with all selected paths on the actual importer
host. It needs no configured Archive and creates no records. If the MCP tool is
unavailable, use the packaged `check-import-sources --source-path <path>` CLI
through the maintained managed launcher on that same host (repeat the flag per
file). A cloud-shell `ls` is not proof of access by a computer-side importer.
Readable attachments, including `/mnt/user-data/uploads/` paths when the importer
can read them, continue directly without requiring a connected computer folder.

If files are unavailable, explain the cause immediately before creating anything:
"The file is in the chat, but the import tool looks for it on your computer."
Do not keep trying that same inaccessible path. Use this recovery sequence:

1. Inspect the host's actual callable file-transfer capabilities and the already
   connected folders. Reuse an authorized ordinary working folder outside the
   managed `Vera/engagements/.../inputs` tree. Offer **Add folder** from the **+**
   menu only when the current host offers it; otherwise explain the available
   connection method. Ask for a folder only if an accessible destination is needed.
2. With a supported bridge, copy only the selected original attachments to that
   folder as files. Compute each original SHA-256 through the host file tools.
   Do not recreate CSV text, convert encodings or line endings, relay document
   contents through model-authored tool arguments, guess a mount translation,
   overwrite a different file with the same name, or scan unrelated folders.
   A verified byte-for-byte copy may reuse its destination on retry.
3. Check the actual destination paths with `check_studio_import_sources`, passing
   `expected_sha256` as the original hashes in the same order as `source_paths`.
   The CLI takes one `--expected-sha256` per source. Archive hashes the destination
   locally and returns `ready=true` only when all supplied original hashes match.
   If no byte-preserving host transfer is available, say so and ask the user to
   save the original selected files to the accessible working folder; then verify
   them. Do not promise a bridge operation that is not callable.
4. Only after all selected sources are ready, select/create the client and
   engagement and import each through `import_studio_client_document` (CLI
   `import-document`). Pass that file's `expected_sha256` / `--expected-sha256`
   when a transfer was required. The importer checks it again during copying and
   creates the input ID and SHA receipt itself. Never manually populate `inputs`.

The path importer does not itself fetch chat attachments. Direct attachment use
requires actual importer access or a demonstrated host transfer. If neither an
importer-side check nor transfer is callable, explain the missing capability
before creating records; do not create a cloud-only replacement for a local Archive.

On any later import failure, disclose the existing `client_id` and `engagement_id`
and resume those same records. A folder-name collision calls for inspecting the
returned existing scope and reusing it when its identity matches; never clear old
folders or change the client's name just to get past the error. A deliberately
separate synthetic test may have a distinct name; retries retain their identities.
Documentless client work needs no file check. Standalone workflows check access
on their own execution host and do not require Archive or a computer folder when
that engine can read the inputs.

Public workflow names select skills; component IDs select module paths.
`financial-report-builder` uses component `report-builder`, `vouching` (historically
called Check Entries) uses `check-entries`, and `purchase-invoice-review` uses
`passive-invoice-audit`. These component IDs are not additional workflows.

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, financial-report-builder and vouching only, optional cache
cleanup uses the corresponding component ID from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
This supported maintenance command is the only cache-cleanup exception to the
prohibition on editing the installed tree by hand. It is optional: ordinary
validation and execution tolerate incidental bytecode without removing it.
On a read-only installation, skip cleanup. If the command reports a permission
error, retain that error and continue the ordinary validated workflow when its
checks pass; do not chmod, delete files manually, copy or patch the installation,
or bypass the host's permissions to make cleanup succeed.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launcher provisions and reuses one user-scoped CPython 3.12
environment per OS host with the published, hash-checked dependency locks, outside client
folders. Modules and products share this dependency environment; it does not
isolate client matters. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted suggestion or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract. When invoked through Vera, Clara or Lucia, task
usage, signed receipts, technical recovery and 1–5-star feedback through the
invoking product's incident service and rating form remain available. Follow the
primary task's workflow-usage contract and product identity. Tutorials retain
their no-reporting boundary.

# Composizione negoziata

Use for assessing, starting, continuing or closing an Italian composizione
negoziata. General legal questions use `quesito-legale-fiscale`; an actual
concordato preventivo review uses `concordato-plan-review`. A different
jurisdiction requires separate assessment.

## Start from the professional problem

Establish only the role, client/engagement, accessible documents and urgent
events not already clear. Read supplied evidence before asking for more.
Read only the appropriate guide in `../../references/advisor.md` or
`../../references/esperto.md`. The role (`advisor` or `esperto`) is fixed for
this engagement. A change requires a separate authorized engagement and an
independence/conflict assessment, with separately selected documents. Never
copy the advisor's private file into the expert's case automatically.

Use model reasoning to identify the next professional problem, select evidence,
explain priority, choose an existing capability and draft the result. Do not
invent scores, mandatory phase sequences or admissibility classifiers. Read
`../../references/financial-and-research.md` for cash, plans, assumptions or law,
and `../../references/events-and-closure.md` for change impact. For access or urgent measures read `../../references/access-and-measures.md`; for negotiations and special events read `../../references/negotiations-and-special-events.md`; for the final report, unsuccessful outcomes and residual work read `../../references/report-and-handoff.md`. Load only the guide needed now.

Unreadable evidence remains unreadable. Missing aging, proof of collection,
court receipts or current law stays a gap, never zero or an inferred fact.
Continue unrelated analysis. Examine contrary evidence: a balanced ledger
does not establish collectible receivables; growth needs a basis; an expression
of interest is not committed cash. A negative outcome is valid.

## Use Studio Archive

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

Select the client and engagement, import selected sources, and prepare workflow
`composizione-negoziata`. Start the prepared run before writes. Use the returned
`client_engagement_path`; never fabricate context, IDs or permissions. Read the
input manifest for bound files and exact citations. From this component root:

```sh
python scripts/check_dependencies.py
python scripts/cnc_case.py --client-engagement <absolute-context> --resume
```

The component uses only Python's standard library and Vera's packaged archive;
`requirements.txt` declares this. Do not install extra packages for this helper.
Local deterministic scripts own exact hashes, references, revision conflicts and
dependency-version checks because these are mechanically verifiable. The model
owns meaning, source selection and professional next steps. Local file storage
does not make the selected model runtime local-only.
Reserve explicit approval for external, destructive, approval-sensitive or
material steps. Ordinary local inspection and drafting proceed within the
agreed scope; professional acceptance concerns the exact displayed version.

No snapshot on first use means a new case, not recovered history. On resume,
read the latest immutable snapshot and memo: role, issues, sources, analyses,
version-specific decisions and stale dependencies. History spans this
engagement's CNC runs. Closed runs are read-only; prepare/start a new run for
further work. Old snapshots remain in their original runs. No watcher or
scheduled monitoring is supplied.

## Produce and persist useful work

1. Explain the current problem, observed evidence, contrary evidence and gaps;
   choose the next task with its reason.
2. When useful, invoke an existing Vera capability. Read its skill and follow
   its managed-run/review contract. Finish that run and bind its declared result
   as an upstream artifact in the next CNC run. A capability name in
   `next_action` is a plan and never proves execution.
3. Prepare the actual memo, request list, analysis or role-specific draft with
   page/cell/paragraph locators. Separate documented, reported, calculated,
   assumed, judgment, missing, unreadable and unverified material.
4. Read `../../references/case-record.md`, write an update in the run output
   folder, then execute:

   ```sh
   python scripts/cnc_case.py --client-engagement <absolute-context> \
     --request <run-output>/request-001.json
   ```

5. Read the saved JSON and `cnc-revision-*.md`; deliver the draft and unresolved
   decisions. The helper checks explicit references, hashes, graph structure
   and revision conflicts. It does not judge truth or evidential sufficiency.

When facts change, update the affected fact/assumption/source under the same
stable ID. The helper marks descendants stale. Assess semantic impact beyond
recorded edges and add missing dependencies. Regenerate affected analyses with
the relevant capability, then record new drafts. Do not clear staleness by
copying an old conclusion. Unchanged wording can still need new evidence and
professional review.

## Professional decisions and authority

Record a review only after the professional confirms the exact displayed version.
Local attribution records remain `record_only_identity_not_verified` and never
approve a handoff. For an authenticated review, use the optional Mparanza account
route only after the user chooses it; reuse an existing explicit choice. Explain
that the server receives opaque case/node identifiers, version digest, decision,
account email and timestamp, and retains them until administrative deletion.
Documents and the report text stay local; the browser reads the selected file.

Prepare the exact current node without sending data:

```sh
python scripts/cnc_case.py --client-engagement <absolute-context> --review-node <node-id>
```

Give the generated local JSON and `https://mparanza.com/vera/cnc-review` to the
professional. Only that person signs in, reads and confirms. Never click the
confirmation, automate sign-in as the reviewer, or manufacture a receipt. The
first authenticated reviewer owns the case's review scope; another account or
role cannot approve it. This permission concerns hosted review records; local
file access remains controlled by the host/OS and Studio Archive, not a remote
multi-user document vault.

Import the downloaded receipt into the running run's declared output area.
Include its exact parsed object as `server_receipt` in the ordinary review row.
The helper checks the fixed HTTPS server record and binds its actual account to
the current role, case, node and version. Wrong, changed or unavailable receipts
cannot create authenticated approval. Keep drafting if the service is unavailable;
report the approval as pending. A later rejection overrides a previous acceptance.
See `../../references/case-record.md` for the contract.

Neither authenticated account ownership nor a local record proves professional
qualification, independence, appointment, legal validity or a signature. External
filing, signing, communications and payments remain outside this module. Prepare
a handoff with actual receipts or explicit gaps. Changed dependencies require a
new review; never transfer acceptance to an updated draft.

## Close the working session

Composizione Negoziata is outside the comparison-report scope. Retain evidence of
the documents, case records, drafts and public queries actually used. Declare
every physical output, including requests, revision JSON and memos. Finalize, review the declaration
and complete the run; fail or cancel abandoned work explicitly. Completing a
run does not close the legal procedure.

Deliver the case position, work performed with links, findings and gaps,
changes requiring review, and the next professional decision. Client data may
enter Anthropic Claude or Anthropic Cowork through the selected account. No
automatic anonymization or local-only model guarantee is provided.

Without local Studio Archive execution, continue useful analysis and drafts in
chat, state that durable revisions/conflict checks have not run, and provide an
exportable summary. Never simulate saved history.
