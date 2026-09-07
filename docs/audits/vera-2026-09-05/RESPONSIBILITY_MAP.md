# Vera implementation responsibility map

Measured on an intermediate local remediation tree on 5 September 2026.
This snapshot precedes the Studio Archive report helper and later New Client
consumer changes; the counts are not the final tree inventory. This is an AST
inventory of top-level Python files under each declared component's scripts
directory. Generated package copies, vendored modules, nested functions,
JavaScript, and retained .source implementations are excluded from these
numbers. Static import absence is not proof that a plugin file is unreachable.

| Component | Python scripts | Lines | Top-level functions |
| --- | ---: | ---: | ---: |
| open-item-reconciliation | 8 | 14895 | 318 |
| archive-organization | 2 | 2370 | 49 |
| client-file-preparation | 11 | 9683 | 234 |
| new-client | 6 | 9366 | 113 |
| aml-review | 2 | 337 | 9 |
| journal-sampling | 9 | 9413 | 204 |
| check-entries | 11 | 10838 | 220 |
| journal-bank-reconciliation | 9 | 14968 | 307 |
| passive-invoice-audit | 5 | 2807 | 58 |
| sales-plan | 5 | 4980 | 107 |
| business-planning | 9 | 5013 | 78 |
| variance-analysis | 16 | 16220 | 390 |
| management-control-pack | 5 | 2469 | 53 |
| centrale-rischi-review | 8 | 5119 | 90 |
| financial-analysis | 10 | 10451 | 179 |
| report-builder | 17 | 11278 | 237 |
| concordato-plan-review | 12 | 11878 | 213 |
| comunicazione-professionale | 19 | 8723 | 170 |
| presenza-digitale-studio | 13 | 2472 | 67 |
| prompt-optimizer | 7 | 5162 | 144 |
| deep-research-validator | 6 | 3887 | 96 |
| previdenza-inps | 10 | 6884 | 175 |
| registro-imprese-sari | 8 | 3996 | 74 |
| bandi-agevolazioni | 14 | 7737 | 135 |
| bilancio-xbrl-it | 31 | 21437 | 342 |
| browser-automation | 5 | 4203 | 92 |
| studio-archive | 5 | 8753 | 211 |

The scan covered 263 scripts and 215,339 lines, parsed without syntax errors,
and found 66 groups of matching normalized function bodies of at least 13 lines.
Normalization ignores function names and docstrings, not referenced globals;
a match therefore does not prove that moving the function preserves behavior.

| Responsibility | Observed duplication | Treatment |
| --- | --- | --- |
| Audit-envelope validation | A 666-line function in Sales Plan and Financial Analysis kernels | Keep separate until global dependencies, error classes and exact-tree bindings are mapped and differential cases pass. |
| Safe relative file opening | A 134-line function in the same kernels | Security-sensitive; preserve directory pinning, inode checks and symlink rejection before considering extraction. |
| Review execution trace | A 26-line function in nine workflows | Pure trace assembly is a candidate shared boundary; local output references and writer behavior remain dependencies. |
| Dependency-check CLI | A 43-line main function in five components | Startup independence and import paths are part of the contract; avoid creating a new bootstrap dependency merely to remove lines. |
| Runtime installation | Vera and Clara retain byte-identical standalone managers | Cross-package availability is intentional; a test checks equality. Generation publication and locking now replace unsafe in-place installation. |
| Model-data report generation | Studio Archive packages the canonical Vera generator through a vendor overlay | One implementation; the generic wrapper explicitly uses local-only reporting while Vera retains automatic server stamping. Packaged paths and privacy hashes are projected together. |
| Local mutation locking | Shared assurance serialization provides one OS lock helper | Archive apply and rollback use it across runs for the registered client. |

The current remediation does not claim a package-size reduction: bundles were rebuilt for correctness and integration, not size optimization. No vendored dependency has been removed
based solely on this scan. The unchanged duplication baseline is deliberate
until an extraction has a demonstrated benefit and preserved behavior. The
large audit-envelope kernels must not be replaced by a generic semantic
validator: they own mechanical receipt, identity and arithmetic checks.

Reachability remains incomplete across all dynamic imports and plugin bootstraps.
The retained Open Item implementation is now positively traced below; its five
source modules are active and must remain. Other dependencies still need their
own execution and exclusion evidence before pruning. The detailed function inventory is temporary evidence
outside the checkout, not a generated source dependency.

## Latest before/after measurement

The same top-level-script scan was applied to `d4486cde` and the current working
files using current Vera component membership. No baseline script in that scope
was missing from the working tree. This measures the combined checkout, including
other owners' changes; it does not attribute every addition to this remediation.
Both sides were recomputed with identical function-body normalization: omit the
docstring, preserve referenced identifiers, and include functions with at least
13 source lines. This recomputation gives 169/172 duplicate occurrences; the
earlier checkpoint recorded 168/171 and is not mixed into this comparison.
Machine-readable evidence is `responsibility-current-measurement.json` in the
external evidence directory.

| Measure | Baseline | Current measured tree |
| --- | ---: | ---: |
| Python scripts | 258 | 266 |
| Source lines | 212,990 | 216,184 |
| Duplicate normalized function groups (at least 13 lines) | 64 | 66 |
| Function occurrences within those duplicate groups | 169 | 172 |
| Vera Codex ZIP bytes | 5,311,504 | 5,406,646 |
| Clara Codex ZIP bytes | 5,159,312 | 5,190,487 |
| Lucia Codex ZIP bytes | 925,337 | 943,315 |

The shared lock and report-generator boundaries have concrete reuse, but neither
the whole-tree duplicate count nor package size decreased. The measurements do
not justify claiming general decomposition or size optimization complete. The
scan excludes vendored code, generated copies, nested functions, JavaScript and
retained `.source` implementations; reachability qualification remains open.

## Observed Open Item dynamic execution

`implementation_bootstrap.py` registers five exact retained source files, reads
stable validated bytes, and compiles them with logical `.py` filenames. Public
entrypoints initialize this bootstrap. Ordinary `.py` import searches and normal
file-extension inventories therefore miss these implementations.

A Python call trace of the existing synthetic native successor-workflow test
observed the following source-declared functions. AST matching excludes module
initialization, class bodies and generated dataclass code from these counts.

| Retained module | Distinct executed functions | Calls |
| --- | ---: | ---: |
| accountant_report.source | 21 | 182 |
| locale_support.source | 8 | 327 |
| reconciliation_helpers.source | 67 | 1,719 |
| review_session.source | 47 | 534 |
| workpaper_outputs.source | 44 | 1,084 |

The native successor test passed. Three additional existing synthetic tests
covering Spanish missing-evidence output, review contracts and forbidden Git
workspace output also passed; their separate trace must not be summed as unique
coverage. Tracing used the isolated validation tree after verifying all 30 Open
Item files and all eight shared assurance files matched current canonical source.
The first native-test attempt skipped without Node on PATH; the recorded passing
rerun used the bundled Node runtime.

Evidence: `open-item-workflow-reachability.json`,
`open-item-workflow-reachability-tests.xml`, `open-item-runtime-reachability.json`
and `open-item-reachability-tests.xml` under
`/private/tmp/vera-remediation-01a07083/`. These are positive reachability proofs,
not proof that every branch was exercised or that unobserved functions are dead.
All five retained modules remain necessary for the exercised public workflow;
removing or renaming them merely to simplify a static inventory is rejected.


## Trace payload extraction qualification — 6 September 2026

Current AST comparison finds 14 byte-equivalent normalized function bodies for
_append_execution_trace in ordinary review_session.py files. This is a wider
trace-helper scope than the original top-level responsibility snapshot; retained
.source files remain outside this particular scan. Every helper depends on its
workflow's WORKFLOW_NAME, _local_output_refs and _write_json. Centralizing file
I/O would therefore change more than the shared payload construction.

An isolated differential experiment compares a pure payload constructor against
all 14 current function bodies over eight cases: missing input keys, fallback
inputs, filtered empty/nontext values, authoritative empty local-file lists,
explicit local inputs, null/malformed posture, null input collection, and
replacement of a previous trace. All112 comparisons preserve both exact written
payload and TypeError behavior, including no write on failure. The experiment
substitutes file reading/writing and output collection; it does not qualify a
new shared import, filesystem boundary or full workflow execution.

Maintenance opportunity: centralize the repeated trace fields while retaining
workflow-specific readers, writers and artifact collection. The current proof
supports that payload boundary only. No production helper, package import or
vendored file was moved or removed. Next prerequisite is shared-module import
qualification for the affected direct CLI and packaged entrypoints, followed by
actual differential workflow tests before extraction is accepted.

Evidence in /private/tmp/vera-remediation-01a07083:
review-trace-dependency-inventory.json (source hashes, lines, static callers and
external names), qualify_trace_payload.py and review-trace-differential.json.


## Shared trace constructor implemented — 6 September 2026

Extracted build_review_execution_step into the existing shared assurance
serialization module for Check Entries, Journal Sampling, Journal–Bank,
Concordato and Report Builder. These five public entrypoints already initialize
that package. Their local readers, writers and output collectors remain intact;
the shared helper constructs only the previously identical trace fields.
Output collection still follows input/command conversion, preserving error order.

Before implementation, all 10 direct/public-packaged startup probes found the
existing module. After rebuilding, all10 probes call the new helper successfully.
112 isolated comparisons of the production constructor against the unchanged
original helper preserve payload and exception behavior. AST comparison confirms
all pre-existing serialization logic is unchanged. These are bounded proofs,
not substitutes for the full workflow regressions now running.

The five helper bodies shrink from130 to65 lines; the shared function adds19,
for84 lines total (46 fewer). Other helpers retain their existing implementation
until their own startup paths are qualified. Vera ZIP size increases by6332 bytes
(Codex),6427 bytes (Cowork) and6338 bytes (upload): the shared module is replicated
in packaged component trees. This is a maintenance reduction in canonical code,
not a package-size reduction. No vendored dependency was pruned.

23 affected Vera privacy fingerprints refreshed after the output-boundary review;
the complete register passes. All9 local Vera/Clara/Lucia ZIPs rebuilt and passed
parity checks. Clara's privacy validator also passes. Lucia has no standalone
privacy CLI at the assumed path; its existing opening-matter fingerprint failure
is separate and has not been refreshed without source review. No public version,
deployment, merge or publication was performed.

Evidence under /private/tmp/vera-remediation-01a07083:
shared-trace-boundary-review.json, shared-trace-production-differential.json,
trace-shared-import-probe/result.json, trace-shared-import-after/result.json,
shared-trace-size-comparison.json and shared-trace-package-hashes.json.

The full six-module assurance/workflow regression remains active in session27113,
with shared-trace-regression.log and eventual shared-trace-regression.xml. Do not
restart it on an observation timeout or claim it passed before terminal evidence.


## Trace extraction extended to nine supported workflows — 6 September 2026

A second direct/packaged probe found the existing assurance module usable by
Client File Preparation, Deep Research Validator, Prompt Optimizer and Variance
Analysis. These four now use the same pure trace constructor. Distribution,
Mix Contribution, Period Comparison, Scatter Bubble and Set Overlap fail that
additional module import in both source and package probes; their ordinary
startup completed first. This establishes a missing shared dependency for the
proposed extraction, not broken ordinary workflow startup. They remain unchanged.
No new search path or bootstrap dependency was introduced merely to remove lines.

Nine caller functions plus the shared helper total136 lines versus234 before
(98 fewer). File I/O, output-reference collection and workflow naming remain
local. The production helper passes112 comparisons against the archived original
function, now explicitly loaded from the pre-change extracted package so the
comparison cannot silently become self-comparison after adoption.

Deep Research Validator, Prompt Optimizer and Variance suites:169 passed, no
skips/errors/failures. Client File Preparation initially60 passed/16 Node skips;
all16 skipped MCP cases then passed with Node on PATH. This is combined evidence,
not a single fresh76-test run. The original six-module run in session27113 is
still active; do not restart it. No terminal outcome is claimed for that run.

All9 local package builds/parity checks pass after this extension; exact hashes
are in shared-trace-nine-workflows-package-hashes.json. Vera and Clara privacy
registers pass. The local public ZIP parity failure remains specifically Clara:
its builder intentionally disallows public promotion without the separate real
Cowork/Linux acceptance gate in check_clara_cowork_release.py. Vera and Lucia
public ZIP bytes match their candidates. Do not copy Clara's candidate to its
public path or relax the test to hide this unfulfilled release condition.
The separate catalog-test attempt failed because Node was absent from PATH;
its corrected exact rerun is tracked separately, not inferred from that failure.

Evidence under /private/tmp/vera-remediation-01a07083:
trace-shared-import-remaining/result.json, shared-trace-additional-regression.xml,
shared-trace-file-preparation.xml, shared-trace-file-preparation-native.xml,
shared-trace-nine-workflows-size.json and shared-trace-nine-workflows-package.log.


Trace extraction verification follow-up: 90 isolated comparisons of all nine
current wrappers against the archived original preserve exact read/output/write
order, written payload and exception type. Cases include malformed JSON,
nonobject/null inputs, null command, output-read failure, write failure, explicit
empty local-file posture and pre-existing trace replacement. No output read
occurs after malformed intake and no write follows failed output collection.
Evidence: qualify_trace_io_order.py and shared-trace-io-order.json.

The configured unsuppressed 20-source-file Mypy check passes; Bandit reports no
medium/high issue in the ten changed trace/shared source files. Logs:
shared-trace-mypy.log and shared-trace-bandit.log. Isort found an existing
hashlib/json order issue at the top of Journal Sampling review_session.py. Its
fix is intentionally deferred until session27113 completes so the source is
not changed during the active suite. No full-repository gate closure is claimed.


Post-formatting closure: the actual Journal Sampling artifact/workbook smoke
test passes1/1 with no skips, and all three refreshed Vera ZIPs pass parity
checks (including18 packaged MCP startup/tool-list checks). The complete Vera
privacy register passes. Exact files: shared-trace-final-sampling-smoke.xml,
shared-trace-final-privacy.log, shared-trace-final-vera-package.log and
shared-trace-final-vera-package-hashes.json. The queued import-order issue is
resolved. No trace-regression process remains active.

This closes the implemented nine-workflow trace extraction's local verification.
It does not establish whole-repository coverage, professional/native-host
acceptance, or proof that unobserved vendored code is unreachable. The original
T01–T20 scope and other recorded qualification gaps remain open.

## Shared-source projection reconciled after the frozen test run

Current-frozen-source-delta.json records112 changed existing files by exact
before/current hashes. This is a delta inventory, not an attribution of all
changes to Vera or a substitute for test coverage.

Inspected three changed shared chart modules. Vera's actual ZIP contains the
Variance-specific overlay of draw_waterfall, draw_charts_utils and
multidimensional_charts_prep. Exact packaged bytes match plugins/_shared/variance,
not plugins/_shared/vendor. Thus concurrent average/population/zero-value changes
in the latter two generic modules are not incorporated into Vera's Variance
module. No unrelated source was reverted or altered.

The relevant dedicated-overlay change forwards the existing selected font size
to fallback waterfall panels. It changes presentation, not amounts or data
selection. Existing targeted public chart tests pass11/11: waterfall, small
multiples, fallback and bottom-up mix cases. This does not prove native browser
layout. The package/source comparison is recorded in
current-variance-shared-projection.json; regression evidence is
current-variance-vendor-regression.xml/log.

The frozen worktree remains an exact source reference for the original global
run. No test process remains live there; it is not a reason to wait. All new
checks above ran against current primary source.
