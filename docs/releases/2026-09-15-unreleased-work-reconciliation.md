# Reconciliation of the old primary checkout

The primary checkout was at `d4486cde`, 132 commits behind the inspected
`origin/main` (`9644e38e`), with 1,058 changed tracked files and 959 untracked
files. Its diff was not a deployable release: it mixed unreleased source,
already released changes, superseded versions, generated packages and local
audit output.

## Recovered source

- Clara case writes use a recoverable journal and cooperating-process locks.
  Exchange imports validate portable paths and destinations before mutation.
- Reviewed decision narratives and final Markdown, Word and HTML deliveries
  bind to the current case and exact output files.
- Reporting preserves parser settings, reviewed execution policy and source
  identity, retains failed-attempt evidence, publishes complete generations,
  and exports relocatable bundles with their input and output evidence.
- Deck revisions resume from existing state and recheck source, approval and
  output identity. Media rendering retains attempt diagnostics and validates
  the completed generation.
- Chart adapters preserve signed, zero and small values, declared period scope,
  and source observations. Unsupported distribution bindings fail explicitly.
- Hosted voice uploads serialize chunk completion and cleanup. Interview jobs
  retain durable interruption state without automatically replaying uncertain
  provider calls. Provider errors expose classified metadata rather than raw
  response bodies.
- Fresh Windows reporting checks also exposed exclusive CRT reader locks;
  managed workflows now use Windows shared read locks, so nested processes can
  run while installers remain excluded. Installer probes exercise target package
  metadata and fall back to target ensurepip when an older launcher pip fails.
- The local review server reads private component metadata only for the browser
  render tool. Normal MCP results retain their existing structured payload.
- Public copy describes the actual journal-input and exact-duplicate contracts.

## Reconciliation decisions

Three-way comparisons used the old checkout as the base and current main as the
release baseline. Exact historical blob matches identified changes already
released. Current shared Python 3.12 setup, renamed specialist skills, expanded
business-planning workflows, publication registry and package parity rules were
preserved. Distinct regression tests from both histories were retained.

Generated ZIPs and extracted package trees are rebuilt from canonical source;
old generated copies are not merged. Historical local audit outputs are not
release evidence. Previous Clara native Cowork testing was stopped at the
user's request; this release does not claim that acceptance or model-quality
evaluation was completed.

The independent optional-onboarding change is integrated from PR #634 before
the final package build. The separate first-use-course task retains its own
active worktree and is not silently included in this recovery.

## Validation

The recovery, exchange, process, public-HTTP, semantic-execution and release-gate
selection passed 148 tests. A broader recovered-work selection passed 1,909
tests and exposed six integration/test failures; the repaired cases passed a
stable seven-test rerun. Thirty-three additional provider, converter and local
review boundary checks passed. Changed Python source passes Black and Isort;
Bandit reports no medium/high findings in changed production Python.

Canonical releases are Clara 0.1.207, Vera 0.1.255 and Lucia 0.1.49. Every Codex,
ChatGPT upload and Cowork package was rebuilt from source; product alignment and
Codex source-drift checks pass. Repository-wide tests and final CI remain release
gates. Native Cowork agent acceptance is not claimed.

The repository-wide formatting checks expose legacy formatting/import-order
debt outside this recovery; the changed source passes both checks. The existing
configured src mypy check passes, and src Bandit has no medium/high findings.

## Benchmark isolation repair

Recognize the renamed legal-tax-answer-planner skill in the baseline isolation guard. The full benchmark file passes; the package, icon, update and benchmark regression selection passes 414 tests with 2 conditional skips. The prompt-optimizer component is 0.1.50; Vera 0.1.255 and Lucia 0.1.49 packages were rebuilt. All previously collected tests are accounted for with 11,226 passed and 41 skipped after the repair.
