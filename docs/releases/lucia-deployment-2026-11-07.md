# Lucia full-edition deployment preparation — 7 November 2026

This deployment builds the full local-MCP Lucia edition from the audited fixes
and current main. The reduced 0.1.216 Marketplace artifact remains in review;
this deployment does not replace or cancel that submission.

The complete release build exposed stale metadata missed by the earlier direct
ZIP build: Vera's localization catalogue bound the old manifest version, and
course records still bound the old shared receipt-helper SHA. Exact catalogue
skill entries were unchanged. The catalogue release binding, course source
hashes, dependent privacy fingerprints and already-tracked cross-host release
artifacts were regenerated. Existing jurisdiction judgments and course content
were preserved.

Validation of the deployment build: all 32 exact-full-ZIP cases passed in the
separate declared runtime, and all 27 focused edition/receipt tests passed.
Cross-host release alignment and GitHub CI are recorded with the deployment PR.
The earlier audit and publication-preparation reports contain substantive case,
module-load, CLI, MCP and negative-test evidence and their acceptance limits.

The reduced projection rebuilt from the final source differs from the submitted
ZIP only in execution-files.json and four privacy metadata files. Executable
helpers and workflow instructions are byte-identical. The original submitted ZIP
SHA remains `2e237b43c54016f0eec06bdee7c769faa7decf56788d32d9af39401f829a2013`;
it is retained unchanged in the publication review pack. The full download is
verified against its own final build, not against that distinct distribution.

Final deployed commit, download SHA-256, server checks, CI outcome and repository
counts are recorded in the local deployment evidence pack. Native-host,
clean-OS, cross-platform and independent professional acceptance are separate
from server deployment and are not established by this release.

Deployment CI caught a test fixture that did not accept the new edition keyword.
The fixture was corrected without production changes; all 65 metadata tests
passed locally with 98.55% coverage. Main advanced with variance repair #960
during CI. Its source changes were integrated; conflicting derived artifacts
were regenerated. Vera 0.1.591 and Clara 0.1.393 avoid active branch reservations.
An attempted bulk conflict resolution was rejected by automatic approval review;
no changes were applied by that command. Source conflicts were then inspected
individually: versions, source fingerprints and catalogue bindings only.
Both catalogue binding histories and all prior jurisdiction judgments survive.

After all 106 checks passed on d611a9439, the attempted merge was rejected because
main concurrently received #961 (3165c62f5), isolating managed pip setup from
ambient settings. Its implementation and tests are retained. New full release:
Lucia 0.1.218, Vera 0.1.593, Clara 0.1.395. The earlier full 0.1.216 deployment
candidates are superseded. The original reduced Marketplace 0.1.216 submission
remains untouched; unlike the earlier metadata-only rebuild, the latest source
also includes the managed runtime repair and new version metadata. No claim is
made that the submitted reduced artifact contains that later runtime repair.
The second alignment fixture failure was corrected by updating both remaining
mock signatures; 126 verifier/MCP tests passed with 100% verifier coverage and
189 downstream alignment tests passed. Runtime integration passed 51 tests.

All 106 checks also passed on 27ae8b9fa. Its merge was rejected when main
concurrently received #964 (c61cd071d), the grouped reconciliation/workbook fix.
That implementation is preserved unchanged. Structured JSON comparisons found
only version/fingerprint differences in conflicting product records; both new
catalogue history bindings are retained alongside Lucia's binding. Versions
remain Lucia 0.1.218, Vera 0.1.593 and Clara 0.1.395. The integrated packages are
rebuilt and rechecked; the preceding green CI run is retained as historical
integration evidence, not represented as validation of the later commit.

Main advanced again with Clara reduced-edition release #967 (3919ea2c7) while
104 of 106 checks were green. Its shared-builder changes are integrated with
Lucia's selector, preserving both explicit reduced editions. A parametrized
regression proves both selectors build their own package; the old assertion
that Clara must be rejected now checks the unsupported Vera reduction instead.
The first rerun exposed a test-harness lookup of Vera as a standalone package;
it was corrected to use the maintained package/bundle selector. Derived privacy
fingerprints and course hashes were regenerated without changing review judgments.
Full and reduced packages are rebuilt and their affected acceptance checks rerun.
