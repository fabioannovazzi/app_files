# Clara Cowork release acceptance

A successful Codex run or ZIP build does not approve a Cowork release. The
candidate must pass packaged script checks and a separately reviewed run of the
actual Cowork agent. Both records refer to the ZIP SHA-256, not just its version.

## Automatic candidate check

`.github/workflows/clara-cowork.yml` runs on pull requests, main pushes, and manual
dispatch. It checks source drift, then exercises the distributed Cowork ZIP on
Linux with the Cowork launcher baseline, Python 3.10. It uploads logs and outputs even on failure.
Candidate artifacts are labelled as candidates; this workflow does not publish.

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

Install the exact candidate into a fresh Cowork session/environment. Record the
application version and environment. Give `clara:clara` the packaged synthetic
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
  "schema_version": 1,
  "zip_sha256": "SHA256_OF_CANDIDATE_ZIP",
  "status": "pass",
  "host": "Claude Cowork",
  "workflow": "reporting-engine.period_comparison.trend",
  "fresh_install": true,
  "reviewer": "NAME",
  "tested_at": "ISO_TIMESTAMP",
  "cowork_version": "OBSERVED_VERSION",
  "environment": "OBSERVED_OS_AND_VM_PYTHON",
  "evidence": {
    "normal_answer": {"path": "answer.md", "sha256": "FILE_SHA256"},
    "report": {"path": "report.html", "sha256": "FILE_SHA256"},
    "transcript": {"path": "transcript.md", "sha256": "FILE_SHA256"},
    "visual_review": {"path": "visual_review.md", "sha256": "FILE_SHA256"}
  }
}
```

This is a reviewer attestation, not cryptographic proof that the app ran. The
verifier checks the exact ZIP, statuses, required reviewer fields, and evidence
file hashes. A changed ZIP or evidence file invalidates acceptance.

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

Repository administrators must require the `Fresh Clara Cowork ZIP`
check in branch protection. Local implementation does not change remote GitHub
settings. Existing build/deployment tools can still bypass the promotion command;
operators must use this gate before publishing. There is no verified unattended
Cowork driver wired into this repository yet, so a script pass remains explicitly
`cowork_agent_acceptance: unverified` until actual Cowork review is supplied.

The plugin creates its managed environment from the existing host Python and installs
its declared dependencies automatically. Users do not need to install or approve
two Python versions. The single CI baseline catches use of newer Python-only APIs;
the evidence records the interpreter actually used without requiring another run
on a second version.
