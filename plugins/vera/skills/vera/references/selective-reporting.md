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

Prepare and start the run before opening sources for mapping or analysis. Keep
source inspection, local processing, model review and subsequent exact reads in
that run. Save the actual cumulative phase evidence using
`model-data-report-contract.md` as `model_data_report_input.json` in its output
folder. Counts must include initial mapping and later reads; splitting a complete
population into packets does not establish a reduction. Never infer measurements
from public descriptions, packet limits or a source file hash.

Archive finalization creates the local report and includes generated artifacts in
the output manifest. No separate report trigger is needed. It returns the readable
report, or an explicit `unavailable` reason when execution evidence is absent.
No measured local remainder means `not_applicable`, without a report or receipt.
Unknown exposure must not be described as zero. A missing privacy report must not
be disguised as a failed professional calculation.

If any phase has unmeasured exposure, the report is unavailable. If any phase
requires full context, this comparison is conservatively omitted: phase totals
alone cannot prove that a later read did not expose an earlier local remainder.

When receipt transmission is prohibited, save `model_data_report_options.json`
with `{"local_only": true}` in the output before finalization or recording a
failed/cancelled outcome. This prevents the automatic stamp request. Local
onboarding retains its existing automatic transmission suppression.

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
