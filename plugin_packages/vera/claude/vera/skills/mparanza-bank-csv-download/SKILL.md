---
name: mparanza-bank-csv-download
description: Download original bank transaction CSVs through computer use and 1Password in the operator's existing browser, including Intesa Sanpaolo, UniCredit, BNL, Sella and BCC RelaxBanking. Use for requests to download bank movements before accounting; distinguish this acquisition from reconciliation of already supplied files.
---

## Operational incident continuity

At task startup, follow `skills/mparanza-vera/references/incident-recovery.md`. Call the
local `vera_incident_register` tool with empty arguments to reuse the retained
installation identity over ordinary HTTPS. Its credentials stay private inside
the reporter; do not pass credentials to local tools. If local execution is
unavailable, operate `https://mparanza.com/vera/incident-recovery` through the
host's permitted browser controls, preserving the original owner and request
identifiers as the reference describes. Never put credentials in URLs or
diagnostic evidence. Read `vera_incident_status` and deliver
any new remedy without interrupting ordinary work. Automatically report observed
technical failures with complete relevant technical evidence and record the
resumed original operation's actual outcome. Do not ask the user to report the
failure or answer a support questionnaire. Never send professional stdout,
client documents or unrelated personal information. Service failure does not
block the original task. After a managed helper fails, read any
`VERA_TECHNICAL_EVIDENCE` pointer or pending diagnostic from startup/context,
review its retained stderr locally, and attach complete relevant technical
causes to the original report with `evidence_for_report_id`. Follow the reference
before declaring missing diagnostics. Never upload raw stderr or unrelated case
content; acknowledge the actual recorded supplement to remove the local raw file.

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
override this Cowork contract. When invoked through Vera, task
usage, signed receipts, technical recovery and 1–5-star feedback through the
invoking product's incident service and rating form remain available. Follow the
primary task's workflow-usage contract and product identity. Tutorials retain
their no-reporting boundary.

<!-- VERA_WORK_CONTINUITY_BEGIN -->
## Work continuity

Before substantive work, read `../mparanza-vera/references/work-continuity.md` (from the
Vera root skill, `references/work-continuity.md`). Resolve prerequisites upfront,
retain passed choices and the exact job context, and recover failed operations
without discarding progress or making the user repeat settled setup. This also
applies to direct invocation, standalone work and studio-wide workflows.
<!-- VERA_WORK_CONTINUITY_END -->


<!-- VERA_WORKFLOW_USAGE_BEGIN -->
## Task usage and user feedback

Before substantive work, follow `../mparanza-vera/references/workflow-usage.md`: start one
retained task UUID for the primary user process (including AI-led work), reuse
it across helpers/resumption, and record only observed outcomes. Discover the
native `vera_incident_host_link` tool, including deferred tools, and verify the
same run's Computer ID on the server. Privacy reporting applies only to the fixed pipeline list in
`../mparanza-vera/references/selective-reporting.md`, using the exact Studio Archive run.
Studio Archive start and terminal writes automatically create a local report for
every run of those pipelines, including full exposure or incomplete observations.
The server proof binds the report hash to the same Archive run and existing Vera
userID. No agent-authored phase file or separate usage-task receipt link is needed.
Other pipelines and chat-only tasks do not get this report. After delivery ask once for the user's 1–5 stars and optional
comment; never infer a score. Studio Archive is infrastructure, not another rated
process. Synthetic/agent tests are marked and excluded. Start and record deliver
only the retained task's events. Retry with
`workflow_usage.py flush --run-id <retained-uuid>`; unrelated queued events do not
block this task. The shared contract applies even on direct skill invocation
and on both Claude and Cowork.
<!-- VERA_WORKFLOW_USAGE_END -->


<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->
## Connected studio knowledge

When the user or an adopted studio instruction requests relevant repository
evidence, read `../mparanza-vera/references/connected-studio-knowledge.md` before the
dependent work, including direct specialist invocation. Use only callable host
search/read tools; preserve citations and this workflow's qualification gates.
Without a repository, continue ordinary work. Studio skills remain independently
invoked by the user; Vera does not dispatch them.
<!-- VERA_CONNECTED_KNOWLEDGE_END -->

# Scarica i CSV bancari

This is Vera’s direct computer-use acquisition route. A request such as
“Vera, scarica i CSV della banca” selects it without a package download,
separate project, tutorial, developer handoff or recorded browser capability.
Read `references/banks.md` only for the selected bank’s public entry and portal
variants. Intesa Sanpaolo, UniCredit, BNL, Sella and BCC RelaxBanking are initial
targets, not a claim of live-verified bank coverage. Establish the actual export
path in the operator’s browser; do not block an authorized attempt because the
bank has not been tested before.

## Scope and browser

The requested result is the original CSV of booked account movements for an
identified client, account and inclusive period. Do not substitute a PDF
statement, scrape rows into an invented CSV, initiate payments, register entries
or change bank settings. If CSV is unavailable, retain the observed limitation
and ask only about an alternative that materially changes the result.

Use the host's documented computer-use controls in the operator's existing
browser profile. The current model interprets screens and chooses navigation;
do not add bank-specific guessed selectors or a second model API. Never pin a
Claude/model/OS version. Verify the actual browser and local-file capabilities.
Follow the current host's tab retention/handoff documentation.

The operator chooses the model in their host, including Terra 6.1 or another
computer-use-capable model. Do not ask for a particular model, change it, add a
separate model API or require a pre-recorded Playwright procedure. The current
model uses the documented computer-use surface directly, observing the actual
screen after meaningful actions. This route does not invoke Vera's portable
capability executor or claim that its qualification receipts were produced.

Resolve the selected client's account, exact portal variant and period from
the user's request or existing case before authenticated work. A bank brand
does not identify the portal or client. Ask only for missing scope, never for
credentials. Client authority already established in the conversation persists.
Resolve client/account/period with the current operator in their own session.
A developer or another user does not need to supply or receive those details.

## 1Password authentication

Use the official 1Password browser extension's matching Login and Autofill.
The instructions here are self-contained: no separately installed connector
or skill is required. The extension route needs no CLI or access to raw secrets. If several saved Logins match the site,
select by the client specified by the operator, not by the first suggestion.

The operator unlocks the vault and completes bank MFA on their device. If the
current browser controls cannot operate extension UI, hand off just Autofill;
resume the same task after authentication. Do not install an extension, connect
a vault or change 1Password settings as an implicit part of a download.

Never read or emit password fields, PINs, OTPs, clipboard values, CLI secret
output, cookies, browser storage or reusable session URLs. Do not capture a
login screen containing credentials. Credentials go from 1Password directly to
the bank, not through the model. Verify the authenticated client/account
indicator; filled controls alone are not a successful login.

## Export and local evidence

Vera performs routine navigation and checks without repeated confirmation.
Before the export, verify the active client's account, currency, booked versus
pending scope, date filter semantics, any transaction-type filters, pagination
and export limits. Derive these from the actual portal, not from the bank list.
Select the requested whole period; split into explicit subperiods only when
needed by an observed portal limit. Preserve a coverage list for every account
and subperiod, including zero-movement periods.

Resolve the installed Vera root as `../..` from this skill directory. Use its
existing managed Python and run `<Vera>/scripts/check_dependencies.py` before
the helper. Do not ask the operator to open a project, run a shell command or
install a package. For each individual export, invoke the helper immediately
before the export click, using a fresh private directory outside Git and
published folders. Create its parent locally within existing host permissions.
If helper persistence is unavailable, continue the authorized browser download
and deliver its useful original, explicitly recording missing retention
evidence rather than substituting a claimed pass.
The model prepares the request JSON; the accountant does not write JSON or run
commands. It contains exactly these fields:

```json
{
  "bank": "Intesa Sanpaolo",
  "portal": "Inbiz",
  "client": "local client reference",
  "account": "local account reference",
  "date_from": "2026-10-01",
  "date_to": "2026-10-31"
}
```

```sh
python <Vera>/scripts/bank_csv_download.py start --request <private-request.json> \
  --downloads <actual-browser-download-directory> --run <fresh-private-run>
```

The helper is included in Vera; the user supplies no script path. Reuse the browser's actual
download directory; do not change browser settings. The helper snapshots names
and file identity only, without reading existing bank files. Finish after the
download has completed:

```sh
python <Vera>/scripts/bank_csv_download.py collect --run <same-private-run>
```

Avoid unrelated downloads during this interval. A single new file alone cannot
prove its bank origin: correlate it with the observed export action and the
subsequent account/period/content review. This is directory-correlated evidence,
not a browser-event or bank-signed receipt.

The helper copies only a unique new, stable, regular file, with exclusive writes
and requested private file modes, retaining the original bytes and SHA-256.
POSIX modes are checked in the local tests; Windows inherits the private parent
folder's permissions, and this helper does not audit Windows ACLs. It does
not delete the source. Changed/overwritten existing files, disappearing old
partial files, concurrent arrivals, symlinks and unfinished downloads are
reported without claiming a verified export. Each collection attempt has its
own durable report. An interrupted acquisition remains resumable in the same
run. A collected original is reused on retry, not exported again silently.

The deterministic checks prevent attributing an unrelated/preexisting or still
changing file to the export; they do not determine bank account or CSV meaning.
`original_retained` proves local file retention, not population completeness,
correct account, format validity or successful accounting import.

 Do not transmit bank CSVs, screenshots or the client coverage report in technical feedback.

## Review and delivery

Review the export's actual format and header. Read CSVs locally with the
observed encoding, separator and preamble. Do not convert Excel files merely
because the filename suggests CSV. Have local code return only needed metadata:
record counts, first/last booked date and exact totals using reviewed column
meanings. Keep all original rows, including same-date/same-amount payments;
never deduplicate by description/date/amount alone.

Compare those local results with independent portal evidence when available.
Document date-filter meaning, source count/totals, account identity and the
export's handling of pagination. Counts alone cannot prove the right account.
Zero rows are acceptable only with observed no-movement evidence for that scope.
If the portal gives no independent count or total, disclose the check that
could not be made; do not invent a balanced reconciliation or an expected count.

Maintain a private Markdown coverage report across all requested accounts and
periods: request, actual export scope, original-file link, bytes/hash, observed
checks, unresolved exceptions, authentication handoffs and recoveries. Create
and update this report even for partial results. Report separately: file
acquisition, content/coverage review, privacy reporting, and bank acceptance.
A missing privacy report must not suppress a useful CSV or make acquisition fail.
No automated technical check is professional approval.

Deliver the original files and report, with missing scopes first. Download does
not authorize sending data to a gestionale or starting accounting registration.
Keep records local; no support submission, remote upload or publication follows
from this workflow. Later reconciliation is a separate requested workflow.

Track representative live cases for bank acceptance: ordinary and empty
periods, multiple accounts/clients, date/export limits, expired authentication,
interruption/resumption and a changed portal screen. Preserve all encountered
blocks and their recovery. Synthetic file tests prove only local mechanics;
they do not establish bank compatibility or unattended operation.

## Quali dati arrivano al modello

The selected host model may receive the user's bank/client/account references
and requested dates, plus the bounded authenticated browser observations needed
to select the account, filters and export. Screenshots or DOM observations can
contain names, account identifiers, balances and visible transaction rows.
This is not a local-only model workflow and no automatic anonymization is claimed.

The helper uses no network. Directory snapshots, original bytes and full private
request remain local. Its terminal response contains only collection status,
byte count, SHA-256 and the local report path. It does not emit filenames of
unrelated downloads or transaction contents. Do not print snapshots or full CSVs
into chat. Only inspect content in model context when necessary for the requested
work, describing the actual additional data read. 1Password secrets and bank MFA
are outside the model path. Host retention/training settings depend on the
operator's account and have not been audited by this workflow.
