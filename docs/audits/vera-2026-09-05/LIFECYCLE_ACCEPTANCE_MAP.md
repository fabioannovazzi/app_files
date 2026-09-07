# T11 lifecycle evidence map — 6 September 2026

This is an inspected source/test-to-evidence map, not a new test run or a claim
of provider transmission. Evidence root is
`/private/tmp/vera-remediation-01a07083`.

| Original requirement | Inspected evidence and scope |
| --- | --- |
| Successful report | `test_vera_model_data_report.py::test_reduced_projection_builds_hash_bound_localized_report` validates source hashes and localized output. Current managed Business Planning runs additionally retain actual disclosures and finalization under `business-remaining-boundaries/`. |
| No-model run | `tests/model_data_helpers.py::write_no_model_report` explicitly describes a synthetic process that makes no model/network call, using `no_case_data` and `workflow_receipt`. It is a fixture declaration, never proof that the enclosing Codex conversation exposed no data. |
| Unknown/attested exposure | Canonical `model_data_report.py::_validate_phase` restricts `not_measurable` to `host_attested` or `not_measurable` evidence. Current managed Business Planning evidence uses host attestation and expressly leaves exact transmission unmeasured. |
| Offline stamp | `test_receipt_outage_keeps_completed_work_and_returns_pending` injects an outage; JSON/Markdown and the minimal retry request remain, receipt files do not appear, and status is pending. This is a local transport-double test. |
| Later retry after sealing | `test_late_receipt_preserves_sealed_outputs_and_original_request` checks original output bytes and idempotency request bytes. Canonical `_receipt_output_directory` verifies run/report hash against the manifest and writes under `receipts/<report-hash>` outside outputs. |
| Duplicate retry | `test_duplicate_stamp_reuses_receipt_without_network_or_artifact_changes` rejects any network call on the duplicate operation and compares all artifact bytes. |
| Required reports | `test_vera_client_workflow_filesystem.py::test_finalization_rejects_missing_model_data_reports` exercises the public ledger finalizer and rejects a result without disclosure artifacts. |
| Resume after finalization | Supplementary stamping is supported above. General reopening of a completed run is a separate lifecycle operation; the ledger finalizer accepts only running/review-ready state. Do not interpret a late receipt as permission to mutate sealed deliverables. |

The retained `model-data-retry-current.xml` records 34 passing report/receipt
tests, including the delayed and duplicate cases. These were re-inspected, not
rerun. Test doubles establish the local persistence and retry contract, not live
server availability. Current source still contains the supplementary destination,
sealed hash check, and stored-receipt reuse paths.

The source helper's local-only mode returns `server_receipt.status=not_requested`
and does not require a receipt module or network; both source and isolated-copy
tests cover this. Server UUID/hash receipts are acknowledgments of receipt
metadata. No evidence here authenticates exact provider input delivery.

Final public-page privacy claims still need comparison with their actual deployed
versions. This map does not close that external-surface requirement or the entire
T01–T20 goal.
