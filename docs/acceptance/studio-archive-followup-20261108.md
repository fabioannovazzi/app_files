# Studio Archive follow-up — 8 November 2026

## Observed defects and repairs

An explicitly restored client was treating its parent directory as the whole
Archive, rejecting an ordinary sibling document. Imports now recognize the
configured Archive root and actual client-ledger ownership. Another client's
documents remain rejected, including clients outside the configured root.

The corrected boundary exposed a second restore defect: run checkpoints preserve
admitted run copies but omit the engagement's original input collection. Explicit
restore now creates that ordinary input directory when absent. It neither
invents historical input receipts nor replaces retained documents.

Native Archive incident retries lacked a case/run binding. An original report
UUID could therefore associate another run's success with the failed operation.
Retries now compare a keyed binding of command, client, engagement and run.
Explicit corrections to artifact data within that command/run remain possible;
independent writes retain independent operation IDs. Legacy reports require the
exact retained invocation. Reporting rejection does not block professional work
and never closes the incident.

## Validation and limitations

The initial focused batch passed 172 tests and exposed two failures at the
missing restored input directory. After repair, all 189 targeted tests passed.
The wider incident suite passed 577 tests, skipped eight and reached 83.24%
coverage. A separate added regression confirms successful result preparation
despite a rejected cross-run incident association.

The first recovery-suite run passed 151 tests and skipped three but could not
run two distributed-package tests before the ZIPs were built. Its coverage
database overlapped the concurrent incident suite and is not acceptance
evidence; the final recovery run must use a separate coverage file.

The isolated final recovery run passed 153 tests, skipped three and reached
85.43% coverage. The final focused suite passed 190 tests. Reporting transport,
task scope and model-data-report checks passed all 58 tests after granting their
localhost fixture permission; the first transport attempt was denied by the
host socket sandbox before those 15 tests executed. Black, Isort, Mypy and
Bandit checks passed for the changed checked helpers.

Vera 0.1.602 also completed the native JSON-RPC/managed-runtime lifecycle on a
fictional retained case: inventory, import, reopen, prepare, start, write,
finalize and complete. The separately selected ordinary Archive was unchanged.
This client-file-preparation continuation had no selected reporting pipeline,
so its privacy outcome was `not_applicable` / `pipeline_not_selected`, not a
passed privacy report. This does not establish fresh-chat report delivery.

Release preparation encountered stale source bindings after the source and
version changes. All 18 affected compiled courses were compared field by field
against main: only source records changed. Historical editorial judgments are
preserved; fresh native CI remains required. Privacy records describe the new
keyed retry binding without adding raw case IDs to transmitted reporting data.
The localization inventory changed only for the product manifest version;
function IDs, skill hashes and jurisdiction assessments are unchanged.

This is source and synthetic package evidence. Existing chats, affected Windows
machines and original customer operations require their own verification.
No Marketplace publication, customer communication or incident closure is part
of this follow-up.
