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

The run remained bound to package A `c68f3f56cd4c11ef036524fa0cf0d2d51ec73047e8c0a11510dca778437b89c1`. Package B was
`dcde04eee558f4fec3a568968773ae98e7725b546c941ae00110f4106a5a97bd`. B is an isolated 0.1.481-fixture label/index over candidate
A's code, not a published release. The run ID was `run_1e4da5e7d2a2d21acc447f42`.

This is a real packaged calculation/review-process regression. It is not a fresh
installed Codex chat, native visible UI acceptance, server receipt acceptance or
professional approval. The accounting result remains a reviewable draft. The
original failed 0.1.474 run and its evidence were not altered.

## Validation

- 302 runtime checks passed; combined runtime coverage 80.31%.
- 48 final native execution, live-update and installer tests passed.
- The final package started all 25 local services concurrently in at most 6.38
  seconds on this Mac, with one shared code tree. The earlier serialized
  verification path took 22.39 seconds; the lease now protects verification
  without holding the catalog lock through the reads.
- Both the Python owner and Node transport release the replaceable installation
  cwd. CLI children inherit a code lease before launch, including shared roots.
- The dated CI scenario verifies invoice and receipt dates in the normalized-row
  and reconciliation-detail workbook sheets, in addition to the source inputs.
- Black, Isort and Mypy passed. Bandit found no medium/high issues.
- Same-version replacement, upgrade, reconnect, concurrent starts/installs,
  bounded storage, cache tampering, cancellation, repeated signals and POSIX
  detached-worker survival are covered by regression tests.
- `tests/plugins/live_update_dated_case.py` preserves the dated packaged scenario
  in CI. The native test matrix covers Linux, macOS and Windows.

Package parity, complete CI, deployment and installed-host acceptance are separate
release checks; record their final state with the delivery result.
