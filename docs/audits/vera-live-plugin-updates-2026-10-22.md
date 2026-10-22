# Vera live plugin update regression, 22 October 2026

The observed failure was a running review service whose cwd and helper files
were removed during replacement of Codex's installed cache. No reconciliation
matching rule needed changing.

The release candidate pins all local MCP services and managed Vera helpers to
verified read-only code outside that cache. One package-index SHA-256 identifies
one shared code tree. Kernel leases protect active services/workers; catalog and
installer locks serialize publication and collection. Two idle code releases and
the current/previous managed installation sources are retained. Client state,
outputs and logs are outside this code store. Exact file hashes, inode identity
and kernel lock ownership are mechanically verifiable concurrency/integrity
facts; they make no semantic accounting decisions.

An active run binds its first package hash. Native jobs and component review
routing select that package across reconnects. See `docs/live-plugin-updates.md`
for the supported local updater and host/reconnection limits.

## Dated case 1

The final candidate calculation used invoice FT-2026-0101 dated **2026-07-01**,
with a bank receipt dated **2026-07-10**, EUR 610 and the explicit invoice reference.
The opening cutoff remained 1 July and the assumptions explicitly included the
later receipt. No date was backdated or omitted. The calculation reported
`semantic_resolution.status=not_required`, zero batches and no semantic blocks.

The actual packaged MCP validator returned `ok=true` after each operation:

1. Delete the running service's original cache and reinstall the same package.
2. Delete that cache again and install an upgrade fixture while the service stays live.
3. Open a fresh service from the upgrade fixture and validate the original run.

The run remained bound to package A `c503dda9b931530f2a515e976ea96a185d640e0bfb3ec2e0604062af11e3baa4`. Package B was
`0a24934c881dfbcbc0faa9e55b7a3971087c061eba70cf759ec1a15c4ae53ec3`. B is an isolated 0.1.479-fixture label/index over candidate
A's code, not a published release. The run ID was `run_9638be7330fc442ea38924e8`.

This is a real packaged calculation/review-process regression. It is not a fresh
installed Codex chat, native visible UI acceptance, server receipt acceptance or
professional approval. The accounting result remains a reviewable draft. The
original failed 0.1.474 run and its evidence were not altered.

## Validation

- 296 runtime checks passed; combined runtime coverage 80.91%.
- 54 final native execution, live-update, installer and reporting tests passed;
  the subsequent interrupted-installer regression also passed.
- 110 shared-launcher/managed-runtime tests and 144 integrity/reporting tests passed.
- Black, Isort and Mypy passed. Bandit found no medium/high issues.
- Same-version replacement, upgrade, reconnect, concurrent starts/installs,
  bounded storage, cache tampering, cancellation, repeated signals and POSIX
  detached-worker survival are covered by regression tests.
- `tests/plugins/live_update_dated_case.py` preserves the dated packaged scenario
  in CI. The native test matrix covers Linux, macOS and Windows.

Package parity, complete CI, deployment and installed-host acceptance are separate
release checks; record their final state with the delivery result.
