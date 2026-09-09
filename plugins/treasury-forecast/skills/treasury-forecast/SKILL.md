---
name: treasury-forecast
description: Prepare and update one company's EUR cash forecast from fixed bank, outstanding-item, settlement, adjustment and planned-flow tables; review dates, retain decisions and explain changes between accepted forecasts.
---

# Budget di tesoreria

Never write run outputs inside this Git workspace or a published folder.
Use the selected Studio Archive client's engagement run inputs and outputs.
Read `references/input-contract.md` completely before preparing data.
This is a prebuilt treasury workflow. Business planning is not a dependency.
Install only the published requirements.txt through Vera's managed environment.
Local deterministic scripts own cent-exact calculations, evidence reconciliation
and version persistence. The model owns semantic review of supplied assumptions.
Reserve extra approval for external, destructive, approval-sensitive or material
steps; normal local preparation and recalculation proceed within the request.
Professional acceptance is a material decision on the exact displayed proposal.
The local server stores treasury_session.json and final_artifacts.json; the
session's immutable forecast versions contain the actual decisions it consumes.

## Eligibility and intake

Accept only the documented CSV headers or equivalent XLSX sheets, for one
company, EUR and a declared bank-account population. Required missing data or
unsupported formats stop this workflow. Do not generate a generic extractor,
infer outstanding balances from invoices, invent collection dates, or ask the
professional to program adapters or edit JSON. State the specific missing source.

Inspect actual supplied files before choosing their roles. Codex may perform a
reviewed column mapping into the published templates when the information already
exists unambiguously; preserve and cite the original inputs and describe that
preparation. Do not claim an arbitrary accounting export is supported. Ambiguous
allocations and date assumptions require focused accounting review.

The six input tables are accounts, bank movements, open items, additional planned
flows, cash allocations and non-cash adjustments. Empty tables still have headers.
Bank movements, allocations and adjustments concern the interval after the
previous cutoff; the first forecast starts from its current actual bank position.
Future unbilled activity must be supplied among planned flows if needed for the
declared horizon. Keep the scope and omitted populations explicit.

## Codex-Native Run UX

Resolve material choices from actual inputs before asking the professional:
company, account population, cutoff, horizon, coverage and unsupported date
assumptions. Do not propose extra scenarios or output variants unless the facts cue them.
Required missing data remains a specific stop, not a generic questionnaire.

Default output policy: create the workflow's review page, workbook and supporting
records in the bound run. These are not choices to propose separately. Keep a
short codex_run_review.md describing checks performed and remaining professional
questions. Do not place case files in source folders or generated ZIPs.

Supplied extracted FatturaPA XML is optional supporting evidence. The existing
parser extracts document identity, amounts and available payment terms. Those
fields do not prove payment or an unpaid balance. XML duplicates are checked.
Automatic Agenzia downloading, ZIP/P7M extraction, tax calculation, currency
conversion, account transfers and payment execution are not offered by this
workflow. An available later downloader can supply the same extracted XML files.

## Archive and execution

1. Resolve the module root: `modules/treasury-forecast` in installed Vera, or
   `plugins/treasury-forecast` in repository source.
2. Run `python scripts/check_dependencies.py` using Vera's selected managed
   interpreter. Dependencies belong in the shared published environment.
3. Select the exact Studio Archive client and engagement. Confirm the company,
   cutoff, horizon, account population and missing material assumptions only.
4. Import tables, optional XML and the accepted predecessor first. Prepare the
   small manifest described in the contract. Its paths must use each receipt's
   actual execution path relative to the run inputs:
   `imports/<input_id>/<basename-of-receipt-relative_path>`. Do not assume imported
   files sit directly in the inputs directory. The model writes the manifest
   from inspected sources and established choices; the commercialista does not
   author technical configuration. For an update, select the exact prior
   accepted `forecast.json` and bind its record digest.
5. Import the completed manifest into that engagement as well.
   Call `prepare_studio_client_workflow` with workflow ID `treasury-forecast`,
   then start the run. Use its returned portable context and immutable input paths.
6. Run:

```bash
python scripts/run_treasury.py prepare --client-engagement <portable-context> --manifest <run-inputs/manifest.json>
python scripts/run_treasury.py serve --client-engagement <portable-context>
```

Open the printed loopback review URL. The page must let the professional save
dates and their basis, recalculate, reopen and accept the displayed forecast.
Do not ask merely whether to show the normal review. Missing dates keep the
forecast incomplete; source and reconciliation failures cannot be waived.

When a browser server is unavailable, collect the same decisions in chat and
write a local review request in the output directory:

```bash
python scripts/run_treasury.py review --client-engagement <portable-context> --request <review-request.json>
```

The request binds `record_sha256` and contains `decisions` keyed by event ID.
Each date decision has `expected_date` and `basis`. Save edits first, read the
recomputed proposal, then collect an explicit professional acceptance with
`proposal_sha256`, `reviewer_ref`, `reviewed_at` and `conclusion` under
`review`. Do not supply professional acceptance merely because calculations pass.

## Updating and explaining

The scripts reconcile actual bank changes, supplied settlement allocations and
non-cash adjustments. A missing item is not a paid item without evidence.
Previously reviewed dates survive evidenced partial settlements when their basis
still applies; expired dates and changed source due dates return to review.
An explicit invoice replacement suppresses the corresponding planned payment.
The first version supports one invoice replacing one planned event; disclose and
stop unsupported partial or multiple replacement relationships.

Explain the comparable-period opening cash variance and event changes using the
canonical record. Distinguish amount changes, timing changes, newly reported
obligations, non-cash reductions and added forecast horizon. Use the model for
accounting interpretation and focused questions, not for recalculating figures.
An unallocated bank movement is included in actual cash, with its unknown
relationship exposed; never silently turn it into an invoice settlement.

Keep an alternative separate using `run_treasury.py scenario` and a JSON object
of event IDs to hypothetical dates. The returned scenario cannot be used as an
accepted predecessor. Do not promise that the alternative is commercially feasible.

## Delivery and model context

Read `final_artifacts.json` and the current immutable version. Deliver its XLSX,
HTML/Markdown report, daily/weekly/event/change CSVs and canonical forecast JSON.
Report whether this is incomplete, a draft, or a professionally accepted version.
Inspect the workbook's cash figures and ensure saved review decisions appear in
the resulting record. The scripts preserve prior versions; never overwrite them.
Present an artifact_card.md with the exact current report and workbook paths,
review status and any unresolved issue, so the result can be reopened directly.

`model_context.json` provides a bounded initial preview and explicitly states
truncation. Select relevant events through `run_treasury.py context --event-id
<id>`, or read the full local record or original evidence when that is needed.
Do not describe the preview as a technical limit on what the selected model reads.

Follow Vera's model-data report contract: record the real model phases, available
sources, locally processed populations, model-visible material and material never
read by the model. The scripts make no model/network calls themselves. Codex or
Cowork may read real case data through the user's selected provider account; there
is no automatic anonymization or local-only guarantee.

Generate the required model-data report JSON and Markdown, declare every physical
output including retained versions with `finalize_studio_client_workflow`, and
complete the archive run only after the exact output inventory is reviewed.
Stop the review server before finalizing a run. A later update uses a new run.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts. Identify only concrete
observed input, calculation, review or integration gaps. When running through
Vera, follow its separate consent-based feedback process for any transmission.
