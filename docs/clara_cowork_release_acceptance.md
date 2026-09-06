# Clara Cowork release acceptance

A successful Codex run or ZIP build does not approve a Cowork release. The
candidate must pass packaged script checks and a separately reviewed run of the
actual Cowork agent. Both records refer to the ZIP SHA-256, not just its version.

## Automatic candidate check

`.github/workflows/clara-cowork.yml` runs on pull requests, main pushes, and manual
dispatch. It checks source drift, then exercises the distributed Cowork ZIP on
Linux with the Cowork launcher baseline, Python 3.10. It uploads logs and outputs even on failure.
Candidate artifacts are labelled as candidates; this workflow does not publish.
CI also runs the Clara manifest regression suite. The exact ZIP check rejects an
explicit reference to the automatically loaded `hooks/hooks.json`, including
equivalent relative paths, and requires the startup hook to remain present.

For a local diagnostic run:

```sh
source .venv/bin/activate
python scripts/check_clara_cowork_release.py \
  plugin_packages/clara/clara-claude-plugin.zip \
  --output /private/tmp/clara-acceptance-new
```

The output directory must not already exist. The runner extracts the actual ZIP,
creates an empty bootstrap environment, clears inherited Python/runtime settings,
and gives the plugin a fresh managed-runtime directory. It does not install
application requirements or inject repository libraries into the plugin.
Only package-declared requirements are installed through the package's manager.

Coverage in this first gate:

- Core dependency check and every module CLI choice, plus registered modules that
  use their own checker (currently Business Planning).
- Missing dependency rejection before installation.
- Reporting Engine intake of the packaged synthetic retail fixture.
- Existing reviewed semantic fixture acceptance, including incompatible snapshots.
- Mechanical trend compatibility, actual trend rendering, expected January and
  February totals, output hashes, and PNG presence. HTML-only fallback fails.
- Invalid role bindings must fail for the expected reason and leave no manifest.

The expected sales totals are January current/prior 405,000/360,000 and February
426,000/379,500. The automated checks do not establish visual correctness or
business interpretation. They cover one reporting capability, not all 48, and do
not establish acceptance for other Clara workflows. Add cases before advertising
broader coverage. The original package remains untouched; outputs and errors are
retained alongside `result.json`. No undeclared package may be installed to force
the candidate to pass.

## Actual Cowork acceptance

Install the exact candidate into a fresh Cowork session/environment. Record its
ZIP SHA-256, plugin version, application version and environment. First inspect
the actual plugin manager's loading status and errors. Save that output as
`plugin-load.txt`: Clara must be loaded with no errors. Save the startup hook
execution log as `startup-hooks.txt`: all declared startup hooks must complete
successfully in this fresh session. A missing log, skipped hook, dependency setup
failure, or a plugin that loads with errors is not a pass.

For additional Claude Code diagnosis, extract this exact candidate and launch
`claude --plugin-dir /absolute/path/to/extracted-candidate --debug`. Inspect the
plugin manager and debug output for loading and hook registration errors. See
[Anthropic's plugin debugging reference](https://code.claude.com/docs/en/plugins-reference#debugging-and-development-tools).
`claude plugin validate` only checks syntax/schema; its success does not replace
this runtime check. Claude Code diagnosis does not replace the Cowork run below.

Give `clara:clara` the packaged synthetic
retail CSV and its source notes, with this normal request:

> Analyse these monthly retail sales, compare 2026 with 2025, and produce your
> normal reporting deliverable. Use your normal workflow and explain the findings.

Retain the normal answer, complete execution transcript, generated report, and
review of chart values, labels, layout, business claims, and limitations. A manual
fallback after a broken pipeline is a failure for this acceptance case. Do not
substitute a CLI script run or a Claude API/Code session for actual Cowork.

Create a receipt beside those files, after review:

```json
{
  "schema_version": 2,
  "zip_sha256": "SHA256_OF_CANDIDATE_ZIP",
  "status": "pass",
  "host": "Claude Cowork",
  "workflow": "reporting-engine.period_comparison.trend",
  "fresh_install": true,
  "fresh_session": true,
  "plugin_version": "VERSION_FROM_CANDIDATE_MANIFEST",
  "checks": {
    "plugin_load": "pass",
    "startup_hooks": "pass",
    "synthetic_workflow": "pass"
  },
  "reviewer": "NAME",
  "tested_at": "ISO_TIMESTAMP",
  "cowork_version": "OBSERVED_VERSION",
  "environment": "OBSERVED_OS_AND_VM_PYTHON",
  "evidence": {
    "plugin_load": {"path": "plugin-load.txt", "sha256": "FILE_SHA256"},
    "startup_hooks": {"path": "startup-hooks.txt", "sha256": "FILE_SHA256"},
    "normal_answer": {"path": "answer.md", "sha256": "FILE_SHA256"},
    "report": {"path": "report.html", "sha256": "FILE_SHA256"},
    "transcript": {"path": "transcript.md", "sha256": "FILE_SHA256"},
    "visual_review": {"path": "visual_review.md", "sha256": "FILE_SHA256"}
  }
}
```

This is a reviewer attestation, not cryptographic proof that the app ran. The
verifier checks the exact ZIP, statuses, required reviewer fields, and evidence
file hashes. A changed ZIP or evidence file invalidates acceptance. Never copy
`pass` from this example before observing each result. If the loader or Cowork
session cannot be exercised, record `unverified` and hold the release. Old receipts
without explicit loader and startup evidence no longer authorize promotion.

## Release decision and promotion

Download the CI script evidence artifact. One successful clean runtime is required. Run:

```sh
source .venv/bin/activate
python scripts/check_clara_cowork_release.py candidate.zip \
  --output script-evidence \
  --verify-release --cowork-acceptance cowork-review/acceptance.json
```

Any missing/failed/stale script or Cowork evidence returns nonzero. To copy an
approved candidate to a release staging path, add `--promote-to release/clara.zip`.
That destination is not touched when either gate fails. This does not deploy or
publish; use the separately authorized deployment process afterward.

Ordinary Clara builds now write only candidate files, leaving the public download
alone. After acceptance, stage the public download with the same verification:

```sh
python scripts/check_clara_cowork_release.py candidate.zip \
  --output script-evidence \
  --verify-release --cowork-acceptance cowork-review/acceptance.json \
  --promote-to static/shared/clara/downloads/clara-cowork-plugin.zip
```

Promotion verifies the copied bytes before atomically replacing the destination
and writes `script-evidence/release-verification.json` with version and ZIP hash.
Retain that record and both evidence bundles. Publish the promoted ZIP unchanged;
compare the downloaded published ZIP's SHA-256 to this record after publication.
Rebuilding or changing any byte requires new acceptance, even at the same version.

Repository administrators must require the `Fresh Clara Cowork ZIP`
check in branch protection. Local implementation does not change remote GitHub
settings. Manual uploads or filesystem writes outside this gate can still bypass
it; operators must publish only the promoted artifact. There is no verified unattended
Cowork driver wired into this repository yet, so a script pass remains explicitly
`cowork_agent_acceptance: unverified` until actual Cowork review is supplied.

The plugin creates its managed environment from the existing host Python and installs
its declared dependencies automatically. Users do not need to install or approve
two Python versions. The single CI baseline catches use of newer Python-only APIs;
the evidence records the interpreter actually used without requiring another run
on a second version.
