---
name: agenzia-acquisition
description: Acquire delegated clients' Agenzia delle Entrate invoices, corrispettivi and quarterly stamp-duty evidence with Vera's single local acquisition worker; review exceptions, resume verified originals and prepare an explicitly reviewed F24 working paper. Optional native panel and ordinary chat commands use the same files.
---

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
