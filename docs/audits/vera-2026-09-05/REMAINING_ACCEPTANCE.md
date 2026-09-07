# Vera remaining acceptance

**Closed by user scope decision.** Mac-specific checks and Windows testing are
excluded. See [CLOSURE.md](CLOSURE.md) for the final state; the historical
requirements and evidence limits below are retained for traceability.

This is the current concise acceptance record, subordinate to the original
T01–T20 handoff and the user's later scope decisions. It does not certify
completion or authorize a release.

## User scope decisions

- Windows testing is excluded.
- Use the correct public Banca d’Italia documents; old third-party PDFs are not
  prerequisites. The selected official corpus passed all 25 checks.
- Lucia/Clara-specific issues are not additional Vera functional requirements.
- No deployment, merge or publication is authorized.

## Two unresolved execution checks

1. **Local report rendering.** Business Planning and Management Control generated
   reports have numerical and file-level checks. Browser Use explicitly rejects
   their local file URL and prohibits alternate-route circumvention. Public
   Vera page screenshots and synthetic browser interactions do not prove that
   these generated report files render correctly. This needs a permitted visual
   inspection surface; another approval to continue is not the missing input.
2. **Isolated accounting worker.** The current read-only diagnostic returns
   `unsupported`: Mac build25G83 differs from the retained25F84 profile, and
   three executable checks differ. The worker and canaries were not launched.
   Previous sanitized candidate runs and negative probes are retained in
   HOST_QUALIFICATION.md, but do not supply the missing hidden-image boundary
   evidence needed to qualify a replacement profile. No hashes or isolation
   rules were loosened.

## Integration limits

Vera0.1.211 packages, 18 MCP startups and the refreshed shared catalog pass.
The partial-build catalog drift defect is fixed in the builder with regression
tests. Repository-wide frozen coverage remains79.5029%; unrelated legacy/product
failures do not become Vera functionality requirements, but the repository is
not certified globally green for a merge. The full scope ledger records the
individual Vera evidence and bounded outcome limits.

Current host evidence: final-native-host-status-parsed.json. Browser evidence:
current-mac-browser-observations.json and vera-public-browser-review.json, all
under /private/tmp/vera-remediation-01a07083.

The complete Cowork builder/package test module finished: 44 tests, 0 failures, 0 errors, 0 skips. Evidence: cowork-builder-final-suite.xml.
