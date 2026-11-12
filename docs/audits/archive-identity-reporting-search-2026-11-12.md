# Archive identity, privacy reporting and search acceptance

## Observed defects and changes

The existing-context fallback treated a generated client storage namespace as a supplied professional client identity. It also discarded the saved reporting outcome, returning `not_checked` after a completed reporting run. Reopening now uses the sealed working record only when client, engagement, run and workflow match the admitted context. General work remains general, an explicitly supplied client identity is retained, and the matching privacy outcome is preserved. Missing, corrupt or foreign metadata does not block delivery and cannot manufacture an identity assertion.

Fresh search acceptance found that archived working-folder bookkeeping was indexed as a document and its lock produced an unsupported-extension warning. Search now excludes the reserved work record, request/publication markers and lock only at the root of a verified client ledger. Identically named ordinary files outside a ledger remain searchable. No files are removed or modified by the filter.

## Verification

- 710 continuity, optional-service, output-boundary, launcher, reporting, recovery, concurrency and native-intake tests passed, including seven new identity/reporting regressions.
- Nine search regressions passed, including four reserved-file cases and a non-ledger source-preservation case.
- Black, Isort and diff checks passed. Mypy passed for the changed work-folder module. Bandit found no medium/high findings in the two changed production modules.
- A fresh AI-authored bank/journal example produced one reference match and two residual items (one bank, one journal), with the ordinary workbook and review artifacts. The source helper used an explicitly attributed agent review; no human adoption was claimed.
- Vera's actual reporting reader emitted the audit through its measured boundary. Automatic finalization produced JSON and readable Markdown with collection status complete. The actual server stamped the receipt; the maintained verifier checked the current local identity, exact report hash, run, revision and Ed25519 signature. This was a real authenticated receipt, not a mocked transport.
- Reopening the completed work preserved general/false identity metadata, the available reporting result and unchanged report bytes. The maintained read-only report-show command reopened the report without rerunning calculation or stamping.
- After copying to an isolated Archive, refresh indexed two canonical input workbooks. Searching the synthetic reference found both, and opening each reverified its bytes. Changing a source caused the old citation to be rejected; restoring the bytes allowed refresh. Incremental refresh and a full rebuild both retained two documents and zero scan/document issues.

## Boundaries and recovered checks

Acceptance used synthetic files and isolated Archive/reporting state on macOS, with the existing authenticated reporting identity. It did not alter the user's selected Archive root or real client data. Source testing is distinct from installed-package and active-chat acceptance. A report measures Vera-owned emissions, not the whole conversation, other tools, or provider-side receipt.

The first receipt-verification harness call omitted its required current-user argument; it was corrected and repeated against the same unchanged report. The initial index result included a bookkeeping marker and a lock warning; both were corrected and the existing index refreshed, removing the obsolete indexed marker without deleting its file.

Package gates identified stale generated source fingerprints after the code/version changes. The affected privacy source bindings were reviewed for this delta: preserved identity/report status and exclusion of technical bookkeeping introduce no model calls, recipients or external payload expansion. Product version changes affect update/receipt metadata only. Three affected compiled courses differed only in source bindings; separate agent-attributed compatibility notes preserve historical editorial judgments and explicitly do not claim new learner acceptance.

No Marketplace publication is part of this work. Existing 0.1.615 reports and signatures remain unchanged and verifiable after the update.

## Installed 0.1.618 acceptance

The supported local installer updated Vera from 0.1.615 to 0.1.618 with exactly one enabled vera@mp-vera registration. All 2,231 installed file hashes remained unchanged by testing. The same installed components passed 710 continuity/reporting tests and nine search tests. The package build and cross-host parity check passed. Broader package/update tests recorded 416 passes, one skip and one unrelated failure: Clara's public update manifest says 0.1.248 while this machine has curated Clara 0.1.407. No Marketplace state was changed.

A fresh installed-0.1.618 synthetic reconciliation completed and delivered while sandbox DNS restrictions prevented receipt stamping. The report was available and the receipt honestly pending. An immediate verification before retry returned 404 because no receipt had yet been stamped. The maintained pending-receipt retry then stamped the unchanged saved report with network access; verification confirmed version 0.1.618 and a valid signature. No calculation was repeated. The report records one Vera emission of 14,965 characters, with provenance of one audit document and three worksheet rows from each synthetic workbook, including headers (15 bank cells and 18 journal cells). This measures the Vera emission boundary, not provider-side receipt or whole-chat visibility.

The installed Archive indexed two input documents, opened both verified sources, rejected a deliberately changed source, and passed incremental refresh, full rebuild and scoped search with zero scan/document issues. General work remained general with client_identity_asserted false.

The active-chat checker correctly rejected this conversation's stale 0.1.615 skill references after installation. A restart and fresh chat are required for active-chat acceptance. Direct installed runtime acceptance passed; it is not a claim that this already-open chat loaded the new skills. Local installation is complete; repository merge and deployment are not yet complete.

## Integration with incident-isolation release

The initial PR head passed all 111 GitHub checks. Before merging, main advanced to 104120abe (PR #984), requiring release metadata reconciliation. Incoming incident-isolation source and its Geneva review note were preserved. The 15 non-generated conflict comparisons were limited to version, source-fingerprint and catalogue-binding fields; generated artifacts were regenerated from combined source. Approved product versions remain Vera 0.1.618, Clara 0.1.412 and Lucia 0.1.235. Focused combined-source verification passed 337 Archive identity, ledger and reporting tests. The full CI check set must pass again on the integrated commit before deployment. The previously installed 0.1.618 candidate predates these incoming incident-isolation changes; version equality alone does not prove byte parity with this rebuilt package.
