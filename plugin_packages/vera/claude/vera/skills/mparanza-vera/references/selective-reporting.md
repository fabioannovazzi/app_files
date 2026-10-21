> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Selective privacy reporting

The fixed scope is the `model_data_reporting.pipelines` list in
`usage/pipelines.json`, enforced by `scripts/selective_reporting.py`. It contains:

- `journal-bank-reconciliation`
- `open-item-reconciliation`
- `journal-sampling`
- `vouching`
- `fatture-xml-check`
- `purchase-invoice-review`
- `centrale-rischi-review`
- `financial-report-builder`
- `report-enti-locali`
- `management-control-pack`
- `variance-analysis`
- `agenzia-acquisition`
- `archive-organization`

There is one report boundary per Studio Archive run, never per chat or inferred
substantive task. The same run survives retries and a different chat.

Prepare and start the Archive run before source inspection. Its start write
creates the local report and initializes collection automatically. No agent
creates `model_data_report_input.json` or decides whether work is substantive.
The measurement boundary is what Vera sends: its own tool responses, command
output and worker submissions. These producers retain their outgoing payloads
locally before returning them. The collector does not inspect Claude, transcripts,
chat messages or tools outside Vera, and requires no reporting hooks or hook trust.
Use `read_studio_run_artifact` (or Archive's `read-run-artifact`) for selected input
reads. Vera records the returned rows/cells and deduplicates repeated selections
against the same source hash. Preparing a packet on disk does not count as sending
it. Producer-registered coordinates identify original cells in supported derived
packets; an unsupported mapping remains explicitly unknown.

The review-ready Archive write saves a draft report and seals professional outputs.
Collection continues during review. Completion, failure or cancellation closes the
run and immediately triggers the final report and hash submission. Report maintenance can reseal only reserved report
artifacts; the already sealed professional outputs must remain unchanged.

Every run of the 13 pipelines gets a local JSON and readable Markdown report,
including full exposure and zero local remainder. Missing measurements or source
lineage produce an explicitly incomplete report, never an exemption or a
zero-exposure claim. Derived data must not be described as proving that its
original inputs stayed local. “Not sent by Vera” makes no claim about anything
the user or another tool independently sent in the chat.

The server receives the report SHA-256 with the same Archive run ID, report
revision and existing Vera userID, authenticated with the installation's existing
credentials and machine link. These fields are covered by the receipt signature.
It receives no report body, outgoing payloads, source filenames or source values.
Ordinary Archive use retries pending receipts without rerunning professional work.
Verify a local report against its machine identity with
`scripts/archive_report_receipt.py verify --report PATH`.

After completion, failure or cancellation, include the returned
`vera_reporting.display_markdown` directly in the final answer, followed by the
saved report and receipt links. An incomplete report must still be shown, with
its actual limitations. A link alone, a JSON excerpt or a statement that the
report exists does not deliver it. If the returned text is unavailable, reopen
the saved report with `scripts/model_data_report.py show --report PATH` and
present that Markdown. Do not ask the user to request the report separately.
Reopening the saved report does not start another run or submit its contents to
the server. A pending server receipt does not change the frozen report bytes.

When receipt transmission is prohibited, save `model_data_report_options.json`
with `{"local_only": true}` in the output before the terminal Archive write.
Local onboarding retains its automatic transmission suppression. Both keep the
local report and suppress the request; a network or identity failure instead
retains a pending receipt.

Use `fatture-xml-check` as the Archive workflow identity for the dedicated XML
check. Its execution engine remains `client-file-preparation`; broader intake
and New Client runs are excluded. Use `report-enti-locali` for that report preset;
its engine remains `report-builder`. The existing component identities
`check-entries`, `passive-invoice-audit`, and `report-builder` map respectively to
Vouching, Purchase Invoice Review and Financial Report Builder.

For Agenzia acquisition, bind each selected client's acquisition to its Archive
engagement before the worker starts. The acquisition plan is its initial input;
downloaded documents are outputs. Preserve each client/run identity when importing
those documents. A batch spanning clients has one bound run per client.

Reports already saved can still be shown and validated, including historical
reports outside the new scope. Do not rewrite their bytes or signatures. On a
resumed run, Archive preserves the previous report separately; the new finalization
uses cumulative evidence for that same run. Never rerun professional work merely
to display a report.
