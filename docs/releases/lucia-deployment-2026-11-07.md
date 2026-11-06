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
