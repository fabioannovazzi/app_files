# Windows reconciliation diagnostics

Report: `a62b1b17-a42c-42ee-bb4f-309c6672d945`.

The supplied Vera 0.1.659 / reconciliation 0.1.88 execution reached the native
schema canary using an explicit Codex executable. `host-status` returned 2;
that is not the canary's exit code. The service retained the canary bytes but
exposed only a filename, and the chat shell could not read it. Incident-state
JSON parsing also failed without parser coordinates. The Windows causes remain
unknown; this change repairs the diagnostic routes, not the underlying failure.

## Behavior

- `semantic_review.py host-status --probe-dir <original absolute directory>
  --canary-diagnostic schema-canary-prigrz7r.json` reads the selected existing
  record through `vera_execute`, component `journal-bank-reconciliation`, script
  `scripts/semantic_review.py`. Use a new job UUID and the existing task UUID.
  It does not rerun the canary or reconciliation. A zero helper exit means the
  diagnostic was read, not that worker readiness succeeded.
- A newly failing `host-status --probe-dir ...` includes the canary's exit code,
  stdout/schema equality, byte counts and redacted streams in the native job
  result. Exact original bytes remain in the local record.
- `vera_incident_diagnose_state` accepts no arguments and inspects the native
  reporter's own state without creating or modifying state, identity or queue.
  It returns access/encoding status, BOM flags and JSON parser coordinates,
  never credentials, snippets, raw state or parser messages. JSON syntax alone
  does not verify the reporting identity or queue. Clara and Lucia receive the
  same operation under their product prefix because the reporter is shared.
- Ordinary incident-state JSON failures attach numeric parser facts through the
  existing technical event channel. They still raise; no corruption is silently
  ignored and no replacement identity is generated.

## Boundaries

Only a bounded, ordinary single-link file with the retained canary filename and
closed record shape is accepted. No arbitrary-file operation is exposed. These
mechanical checks prevent this diagnostic reader from opening state or source
files as probe records. They do not add a gate to reconciliation execution.

Technical streams are untrusted evidence. Common credential, path, email and URL
forms are redacted; this is not universal anonymization. Host-model context can
contain the remaining technical messages. Review them before submitting an
incident supplement. Original hex/raw streams are not returned by the reader.
The state diagnostic performs no HTTP request. Privacy contracts document both
routes separately from the professional pipeline outcome.

## Windows acceptance still required

Install the updated selected distribution and verify the active native service
and component version. Use a fresh technical job with the updated helper;
restarting a previously bound Archive run does not migrate its saved package.
Read the retained canary and state diagnostics, then diagnose the actual error.
Do not change ACLs, reset state or declare reconciliation recovered based on
these diagnostics alone. No Windows execution or original-task recovery was
performed from this development Mac.

## Development checks and recovered blocks

- Native stdio tests exercise malformed, empty, UTF-8 BOM and UTF-16 state,
  unchanged bytes, no identity creation, no credential disclosure and rejected
  arbitrary path arguments. Unit checks cover access denial and normal parser
  technical facts.
- Canary regressions cover prior-record reading, direct failed-probe delivery,
  zero-exit output mismatch, stream redaction, forbidden filenames/symlinks,
  malformed records and output bounds. Existing isolation checks remain active.
- The sandbox initially denied a localhost test listener. The same integration
  tests passed when run with permission for that fixture. Production was not
  contacted by those fixtures.
- Release preparation detected stale catalogue, course-source hashes and privacy
  fingerprints after the version/source changes. Generated records were rebuilt;
  these were packaging checks, not Windows runtime failures.

## Verified development results

- Worker compatibility: 218 passed, 2 skipped in the initial selected suite.
  Diagnostic additions were then exercised separately with cumulative coverage:
  semantic_review.py reached 80.03% (required >=80%). The opt-in live native
  runtime probe was not enabled; this is not Windows sandbox acceptance.
- Native reporting: 28 stdio tests passed, including the localhost integration
  fixture. Nine targeted state-diagnostic/parser tests passed separately.
- Mypy passed for both changed Python sources; Black, isort and Node syntax
  checks passed. Bandit at the repository's medium/high threshold passed; the
  full scan reported three pre-existing low-severity subprocess findings.
- Generated Codex catalogues for all three products contain their exact
  product-prefixed incident_diagnose_state operation.
