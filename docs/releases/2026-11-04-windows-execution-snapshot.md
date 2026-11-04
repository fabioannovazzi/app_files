# Windows execution snapshot repair

Observed: the production reconciliation incident
`cc4baa5e-47d7-4889-89ab-6c6dd41d8afd` contains a November 4 Vera 0.1.560
installation-preparation `FileNotFoundError` report
`9356790c-6021-4d2e-9381-055b8f95b4a2`. It has no traceback or missing filename.
An older report in that grouped incident has a reviewed Windows error 3 for
`modules/presenza-digitale-studio/skills/presenza-digitale-studio/references/website-quality-standard.md`
in its runtime snapshot. That file exists in the source-built ZIP. Shared
snapshot publication replaces a short staging directory name with a 64-character
digest while retaining nested package filenames.

Inferred: a Windows path-length failure is a supported failure mode of that
snapshot implementation. It is a candidate explanation for the customer symptom,
not a diagnosis established by grouping the reports.

Unknown: the November 4 report's exact failing path, source line and Windows
error number; whether this change restores the customer's installation and
original reconciliation. The screenshot's matching time and workflow do not
independently establish machine ownership. No customer files were accessed.

The shared verifier now uses Win32 extended paths for its private code store and
temporary execution copies. It retains the same storage location, exact inventory,
digest checks, link checks, kernel leases and collection rules. It changes no
machine policy or permissions. Path normalization is a mechanical filesystem
operation; it makes no semantic decision about professional inputs.

Preparation reporting additionally retains source coordinates from the
independently verified verifier, a numeric Windows error when available and the
failed pathname's character count. It excludes the actual pathname, exception
message/values, locals and document contents. Capture completeness does not mean
that the cause is diagnosed or the operation recovered. Existing reporting failure
fallback remains visible. Privacy service descriptions record these exact fields.

The native Windows regression uses the reported package-relative reference path,
a long runtime parent, both ordinary and already extended configuration paths,
and a simulated legacy Win32 path limit even on CI images with long paths enabled.
It checks successful verification/read and collection of the complete snapshot.
An independent Windows CI job runs this regression without waiting for package
builds. Existing tamper, link and lifetime tests remain applicable.

Validation preparation encountered these recoverable blocks:

| Block | Effect and recovery |
| --- | --- |
| Stale privacy source fingerprints | Packaging stopped. Reviewed the changed runtime/report payload and unchanged recipients, updated its service descriptions, then refreshed the affected source reviews and generated contracts. This is agent engineering review, not professional or legal approval. |
| Version-bound localization catalogue | The release check rejected the changed manifest. Verified exact skill entrypoint bytes and IDs were unchanged, then rebound the existing catalogue/assessment without changing jurisdiction judgments. |
| Course implementation hashes | Prepared kits referenced the previous verifier bytes. Regenerated the kits and refreshed affected onboarding/prepared-course reviews. Lesson content and professional acceptance were not inferred from hash refreshes. |
| Package tests started before archive generation finished | The premature run had 20 missing-archive failures and 79.23% coverage. It is not a product result; package verification must be repeated after all archives exist. |
| Incorrect initial coverage selector | A filesystem filename was supplied as a coverage module selector, producing no data. Use the repository's `tests/plugin_runtime.coveragerc` instead. |

Local source checks passed with 112 tests, two native Windows cases skipped on
macOS, and Black, Isort, Mypy and Bandit checks. The final managed-runtime suite
passed 326 tests with two native Windows skips and 81.90% coverage after archive
generation. Final package checks and native Windows CI are recorded with the repair PR. Local
CLI evidence does not establish an installed customer or fresh-chat acceptance.
No reconciliation or its run-level privacy report was produced in this repair.
The original pipeline outcome remains failed/unexecuted; its incomplete diagnostic
capture and lack of recovery remain explicit. No Marketplace action is authorized
by this repair.
