# External runtime compatibility

The Luna capsule previously admitted only an exact Codex executable, macOS
build, `sandbox-exec` binary and canary-reader binary. A normal host update
could prevent both journal/bank reconciliation residual review and passive
invoice review from launching their shared worker.

New work uses `journal_bank.luna_seatbelt_capsule.v5`. It snapshots the actual
executables, checks required CLI capabilities and the OS allow/deny boundary,
and rechecks the snapshots before publishing output. Updated versions and
different executable bytes between runs are accepted. Changes during a run,
failed isolation probes and missing required CLI capabilities remain errors.
There is no minimum or maximum Codex release in this policy.

The reviewed deny-default policy bytes, structured response schema, packet
limits, source receipts, no-reuse checks, inner read-only sandbox, ignored
configuration/rules and output validation remain in force. Executable digests
are observations and run-stability checks, not a permanent release allowlist.
Historical v1–v4 profiles remain available for verifying saved receipts only;
they cannot launch new work.

## Source audit

- `plugins/journal-bank-reconciliation/scripts/semantic_review.py`: permanent
  host identity gates replaced in host inspection, reconciliation worker and
  reusable structured worker. Receipt validation accepts recorded runtime
  identities while retaining the owned isolation policy and capability evidence.
- `plugins/passive-invoice-audit/scripts/luna_worker.py`: delegates to that
  shared worker, so the fix covers invoice chunks as well as bank residuals.
- Vera, Clara and Lucia managed Python checks select the supported CPython
  major/minor environment provisioned by the products. They do not require one
  exact patch binary or freeze the user's Codex installation.
- Browser process/version bindings protect the selected saved procedure and
  its lifecycle, rather than an externally updated executable release.
- Source adapters, artifact/schema versions, packaged dependency recipes,
  policy hashes and imported-source digests are internal contracts or evidence
  integrity controls. Removing those would not solve external compatibility.

## Preventing recurrence

`test_worker_runtime_compatibility.py` rejects fixed external identities in the
active policy and covers newer CLI versions, newer macOS builds, changed bytes
between runs, and changes during execution. The existing worker suite still
checks failed canaries, forbidden events, output tampering and packet limits.

`worker-runtime-compatibility.yml` runs regressions on changes and daily. Its
macOS job installs the latest official Codex and exercises real positive and
negative filesystem canaries and CLI capabilities without user credentials or
a model call. AGENTS.md forbids replacing capability checks with release pins.

These checks catch the original regression and detect future interface or
isolation incompatibilities. They cannot guarantee that every future upstream
change will remain compatible; such failures must identify the missing
capability rather than reject a release solely because its identity changed.
