---
name: agenzia-acquisition
description: Acquire delegated clients' Agenzia delle Entrate invoices, corrispettivi and quarterly stamp-duty evidence with Vera's single local acquisition worker; review exceptions, resume verified originals and prepare an explicitly reviewed F24 working paper. Optional native panel and ordinary chat commands use the same files.
---

## Cowork execution contract

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
environment per OS host with the published shared requirements, outside client
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

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

# Acquisizione Agenzia delle Entrate

Use this operation for ordinary acquisition from Fatture e Corrispettivi. The
procedure adapts the software supplied by Francesco Platania into one maintained
Vera implementation. The generic browser teaching/catalog workflow does not run
this operation. Do not rebuild a second downloader, request a fresh demonstration,
or invoke the retired category/year runners or invoice ZIP scaffold.

## Prepare the work

The operator provides an authorized client Excel/CSV file, dates, requested
operations and a local destination. Read only what is needed to resolve these
inputs. Recover an existing exact plan/run when resuming. Ask for genuinely
missing choices, not technical JSON, paths to internal helpers or CR numbers.
Vera prepares all command arguments and plan files. Never read or copy passwords,
PINs, browser cookies or a private standalone application's credential config.

Use the host's already prepared shared Python 3.12 runtime. From the Vera root,
follow the installed managed-runtime instructions in Vera’s skill and
`skills/vera/references/cowork-runtime.md` for Cowork. The component's optional requirements are declared
in `requirements-agenzia.txt`; run `scripts/check_dependencies.py --requirements
requirements-agenzia.txt` before starting. Do not pip-install packages into client
folders, a host system Python or a new per-workflow environment. `agenzia_runtime.py`
locates an existing ready shared environment; it does not install dependencies.

The worker requires installed Google Chrome and access to the operator's local
graphical desktop. A remote/headless Cowork sandbox cannot provide that access;
state that precise boundary if observed. The ordinary command/file route remains
available without native UI on a host that can launch its local visible browser.
Do not claim Windows, Cowork or live AdE acceptance from synthetic tests.

Run from this component root using the selected runtime:

```bash
python scripts/agenzia_acquire.py plan --clients CLIENTS.xlsx --date-from YYYY-MM-DD --date-to YYYY-MM-DD --operations ricevute emesse corrispettivi bolli --access-mode delega_diretta --output PRIVATE/plan.json
```

Supported operations: `emesse`, `estere`, `ricevute`, `mancata-consegna`,
`corrispettivi`, `bolli`. For intermediary access select `--access-mode incaricato`
and the explicit `--work-identity TAX_IDENTIFIER`. Required client columns are name, codice fiscale and partita IVA. Accepted
name headers include `NOMINATIVO CLIENTE`, `DENOMINAZIONE`, `CLIENTE` and
`NAME`. For other headers, map the supplied fields explicitly into a local
normalized CSV; do not infer a missing tax identity.
Preserve leading zeroes. Ambiguous or incomplete identities stop plan preparation.
Only include requested clients. When narrowing an existing plan, preserve each
selected client's exact identity record and validate it through `Plan.parse`.
Destination and plan must be private local folders outside source repositories.
Dates filter invoices and corrispettivi; bolli always cover the whole intersecting
quarter, including Q4. Explain that difference in the selected plan.

## Native panel or ordinary chat

If `agenzia_workspace_open` is callable and this host supports MCP Apps, call it
with the exact `plan_path`, `output_directory` and optional selected `run_id`.
The thread panel shows client/period selection, progress, exceptions, invoices,
corrispettivi, quarterly bolli, reviewed F24 values and output downloads. It is a
projection over this worker and its saved files, not another client database.
Do not require the panel or manufacture a native host acceptance claim.

Otherwise use the same entry point:

```bash
python scripts/agenzia_acquire.py start --plan PRIVATE/plan.json --output PRIVATE/acquisizione
python scripts/agenzia_acquire.py status --output PRIVATE/acquisizione --run-id RUN
python scripts/agenzia_acquire.py continue --output PRIVATE/acquisizione --run-id RUN
python scripts/agenzia_acquire.py cancel --output PRIVATE/acquisizione --run-id RUN
python scripts/agenzia_acquire.py resume --output PRIVATE/acquisizione --run-id RUN
```

`start` opens one visible local Chrome window with an ephemeral browser context.
The operator completes access personally, including PIN/second factor. Only then
use `continue` or the panel's “Ho completato l'accesso”. No credentials are sent
to Vera. Chrome stays alive with the detached worker, independently of a tool
call timeout. Poll the saved status at bounded intervals; report actual progress.
One destination permits one active worker. Never delete a lock to force a start.

A failed or interrupted run retains its originals and per-record evidence.
`resume` creates a new run for the same requested window, re-enumerates the portal
and reuses only originals whose size and hash still match. Missing/corrupt originals
are acquired again. A browser/session failure requires a fresh personal login.
Cancellation is cooperative, so an in-progress browser action may finish first.
Do not claim completeness when any scope is incomplete, unavailable or unattempted.
A changed count, repeated page or wrong client identity stops that scope.

## Deliver and review

Read the saved `status.json` first. Deliver `riepilogo.xlsx`, `fatture.csv`,
`report.html` and the original-file directory, with counts of new originals,
verified existing originals, failed documents and incomplete scopes. `report.json`
and `events.jsonl` retain structured source evidence; do not paste full files into
model context when a bounded local query suffices. A worker exit is not proof that
all requested scopes completed or that a professional review took place.

XML originals and signed P7M originals are retained without overwriting prior
files. P7M extraction preserves a hash-linked XML copy; it does not validate the
signature. HTML error pages and wrong-client XML cannot count as downloaded
invoices. Unsupported/missing original formats remain failures, never substituted
with a portal metadata screen or a fabricated PDF.

Corrispettivi retain all discovered device types and source rows. Excel includes
raw invii, daily and monthly totals based on the returned “data rilevazione”, not
an inferred accounting date. Missing amounts, invalid dates and duplicate invio
identities remain visible issues; they are not silently converted to zero or
counted twice. Review these before reconciling accounting records.

Bolli record quarterly portal amounts and available payment status. These are
not automatically unpaid balances. For an F24 working paper, the professional
explicitly chooses the residual amount, due date and reason for each included
client/year/quarter. Vera does not calculate legal deferrals, mark amounts paid,
transmit F24 or order payments. Prepare a local review JSON and use:

```bash
python scripts/agenzia_acquire.py f24 --output PRIVATE/acquisizione --run-id RUN --review PRIVATE/review.json
```

The exact review format is:

```json
{"schema_version":"vera-agenzia-f24/v1","reviewed":true,"items":[{"client":"01234567890","year":2026,"quarter":4,"amount":"12.00","due_date":"2027-03-01","note":"Example only: replace with the professional's actual residual and due date review."}]}
```

This example is fictitious, not a supplied due date or amount. Every item must
match acquired quarterly evidence. The PDF is labelled as a working paper and
preserves the reviewed values alongside the source amounts in its JSON receipt.

When requested, import verified originals through existing Studio Archive client
and engagement bindings. Add `archive_client_id` and `archive_engagement_id` to
exact client records only after resolving their tax identity through Studio
Archive. Call `archive --output PRIVATE/acquisizione --run-id RUN`. Do not create
an alternative authoritative client registry or infer an archive binding from a
name. Import receipts survive a partial import and prevent duplicate attempts.

## Prepared local lesson

For the supplied `agenzia-acquisition` course only, read its fictional fixture and
run `python scripts/agenzia_demo.py --fixture DEMO_JSON --output LESSON/acquisizione`
using the same shared runtime. Practice runs `practice.json` in that exact output
directory after `demo.json`. The script injects a labelled fictional source into
the production engine, does not open a browser and does not contact Agenzia.
Show the actual generated files and distinguish the first partial run from the
new run's verified-existing and newly acquired originals. Never use this teaching
adapter for real clients or describe its outputs as live portal evidence. Explain
results in the learner's terms; Vera supplies the internal command arguments.

## Dati al modello e conclusione

The local Python/Playwright worker has no model API calls. It sends authenticated
requests to Agenzia and retains client identities, invoice files, portal rows and
reports locally. The optional panel receives client/financial detail in app-only
metadata; tool text contains run status and counts. Those local files are not
automatically attached to the model. The chat's requested scope, exact paths,
selected summaries and any content Vera explicitly reads do enter model context.
Login secrets stay in the operator's Chrome context and are not persisted by Vera.

Follow Vera's `model-data-report-contract.md` for actual conversation reads and
the required final delivery. The worker writes canonical `model_data_report.json`
and `.md` describing its own no-model-call phase, and marks the surrounding chat
phase as unmeasured. Do not present that initial report as proof the chat read no
client data. Incorporate actual observed reads and the standard delivery stamp
through Vera's established finalization; never stamp a tutorial or invent receipts.
The ordinary report files remain available when the native UI is unavailable.
