# Vera host qualification checkpoint

The isolated worker's read-only diagnostic is:

`python plugins/journal-bank-reconciliation/scripts/semantic_review.py host-status`

It does not read client sources, credentials or global instructions, launch a
model, run canaries, or qualify a new host. Exit 2 means prerequisites are
unsupported. Matching prerequisites still requires the normal guarded launch,
boundary canaries and output validation.

| Surface | Observed evidence | Qualification |
| --- | --- | --- |
| Existing native capsule profile | Source pins macOS 25F84, Codex CLI 0.148.0-alpha.21 and exact executable/profile hashes | Retained existing profile; not rerun on its original host here. |
| Current Mac | macOS 25G83; CLI 0.153.1; diagnostic rejects OS, Codex, sandbox-exec and cat hashes | Unsupported for this capsule; no pins weakened. |
| Windows isolated worker | Source rejects non-macOS execution | Unsupported; no Windows run claimed. |
| Managed Python installation | Local concurrent-launch, failed-generation, timeout and malformed-pointer tests pass; 82.62% module coverage | Technical tests, not Windows platform acceptance. |
| Current Chrome with unified CUA | Shipped loopback fixture reached its expected form result | Diagnostic form interactions only; no portable runner or downloaded-byte proof. |

A new native profile must retain deny-default isolation and exact source read
boundaries, run negative canaries (including the hidden image-reading path),
and retain a normal sanitized worker answer plus its report and boundary
evidence. Model alternatives require representative outcome comparisons.
Updating a version string or a binary hash alone is not qualification.

## Versioned retained-profile registry — 2026-09-06

The shared worker now resolves `journal_bank.luna_seatbelt_capsule.v1` through
one immutable registry record with `retained_legacy` provenance. The record
owns the exact OS/CLI versions, executable paths and hashes, Seatbelt hash,
disabled features and retained qualification basis. Unknown profile IDs,
mismatched record identities and unqualified provenance fail closed. There is
no runtime registration or user configuration surface for adding profiles.

Graph preparation, host diagnostics, executable checks before and after launch,
canaries, Seatbelt invocation, worker arguments, launch receipts and receipt
replay consume the resolved record. Existing pin names remain derived aliases.
The diagnostic exposes provenance; it does not establish execution qualification.

Independent before/after captures preserve all 13 recorded legacy envelope
fields, including exact Seatbelt text and actual/redacted worker arguments.
Mocked public generic launches emit identical receipt content, and generic and
Journal–Bank receipt field sets remain unchanged. Focused tests cover unknown or
unqualified records, forged replay bindings and disabled-feature argument
tampering. Passive's actual dynamic shared-module import is also exercised.
Evidence is in `/private/tmp/vera-remediation-01a07083/host-profile-implementation/`.

These are local implementation and replay checks with mocked launches. No new
model call or canary was run. The registry retains the original envelope,
including its existing network rules and feature list; it adds no read or
network access and does not qualify the current host or hidden-image path.

## Current-host candidate probes

Temporary test scripts overridden only in their own process tried the current
macOS 25G83 / Codex CLI 0.153.1 binaries with the unchanged deny-default Seatbelt
profile. Production pins were not changed. Native sandbox creation required
host execution approval; the ordinary enclosing sandbox rejected nested setup.

- The exact schema read succeeded and an outside-file read with `cat` was denied.
- A real synthetic arithmetic worker returned its normal schema-valid answer
  (`20 + 22 = 42`), JSONL events and launch receipt.
- The hidden-image diagnostic returned unavailable without disclosing the
  synthetic nonce. No attempted hidden-tool read was observable; Code Mode was
  unavailable. This does not qualify the hidden-image boundary.
- The CLI image-attachment diagnostic did not disclose its nonce. A later
  narrowly filtered macOS log query independently recovered the exact denied
  attachment read; see the OS evidence below. This establishes that attempt,
  not the separate hidden-tool path.

Evidence is retained outside the checkout in
`/private/tmp/vera-remediation-01a07083/native-candidate-{canaries,worker,image,attachment}`.
The current host remains unqualified for the production capsule pending a
conclusive image-path canary and the remaining profile acceptance. Do not
promote hashes merely because a synthetic normal answer succeeded.

## Latest browser access check

The earlier Mac lock was resolved by subsequently observed browser access.
The documented unified-CUA `tab.playwright` API successfully filled the shipped
synthetic form, pressed Enter, selected Invoice, checked Reviewed, prepared the
package, extracted the exact completion text and observed a download event.
The canonical runtime module can be imported into the CUA session. A download
event and callable method presence do not prove readable downloaded bytes.

Three validated, unapproved capability-review artifacts and REVIEW.md are in
`/private/tmp/vera-remediation-01a07083/browser-capability-review/`. Explicit
approval for authoring and two local replays was requested; no approval has been
inferred. Full packaged execution, download bytes and receipt finalization remain
unqualified. No alternate route was used to open the previously blocked HTML.

Browser runtime version 13 fixes a separate reproduced origin-boundary defect:
input dispatch previously preceded the origin rejection. Checks now run before
and after asynchronous locator resolution and immediately before extraction.
Regressions demonstrate no guarded input/read on the tested unexpected-origin
paths. This is not an atomic guarantee against every browser navigation race.

## Shared-worker output symlink regression

The generic native worker now rejects a symlink output leaf before resolving it
and before opening authentication-boundary inputs. The retained public-entrypoint
regression failed before the change and passes afterwards, with no target writes.
This is a local filesystem correction, not new host/model qualification; all
existing host pins and launch-time boundary canaries remain required.

## Initial model comparison

MODEL_SELECTION_EVALUATION.md records twelve completed synthetic decision probes:
Luna 5/6 and Astra 6/6 against proposed engineering expectations at low effort.
The opposite-sign failure is retained. Six current production sign-policy tests
passed separately. This is preliminary model evidence, not a production-packet
benchmark or authority to change the capsule model or qualification pins.

## OS evidence for the attachment boundary

A read-only macOS unified-log query over the original attachment test window
(12:15:35–12:16:10 local time, 5 September 2026) returned one matching kernel
sandbox event. At `2026-09-05 12:15:45.731311+0200`, `Sandbox.kext` recorded:

```text
Sandbox: codex(97270) deny(1) file-read-data /private/tmp/vera-remediation-01a07083/native-candidate-attachment/outside-capsule.png
```

The exact canary path, test time and Codex process identify a denied attachment
file-read attempt independently of the model response. The query was limited to
that synthetic path and window. The initial enclosing sandbox prevented access
to the log command; the read-only host retry succeeded. Raw JSON is retained as
`native-candidate-attachment/os-denied-read.json`; `os-evidence-review.json` binds
the raw log and original launch receipt by SHA-256 and records the limitation.
No production pins, sandbox rules or model configuration changed.

A separate query for the earlier `native-candidate-image/outside-capsule.png`
path over 12:11:35–12:13:50 returned no entries. Absence of a log event is not
proof of access denial or absence of an attempted read. Its `view_image` path
therefore remains unqualified; the attachment denial must not be relabelled as
a successful hidden-tool canary. The two raw probes and their original outcomes
remain unchanged.

## Reviewed selection implementation checkpoint

The generic `run_isolated_luna_worker` API now accepts an optional
`worker_selection` using the existing `vera.reviewed_decision_receipt.v1`
contract. The decision type is `worker-model-selection`, adapter
`vera-native-worker` version `1`, and status must be `reviewed`. Its content
contains exactly `workflow_id`, `model`, `reasoning_effort` and
`benchmark_sha256`; the source reference must be `benchmark-<digest>`.

The API checks the content digest, workflow binding, supported effort spelling,
model identifier shape and benchmark reference. An explicitly supplied effort
must agree with the reviewed decision. The normalized review is retained in
`requested_worker_configuration.selection_review`; requested model and effort
flow through the CLI arguments, banner comparison and returned receipt. With
no review, the prior Luna/low default remains. Native qualification, executable
hashes, canaries, output validation and read boundaries remain separate and
unchanged. A reviewed selection cannot approve an unsupported host.

This validates a locally supplied review declaration. It neither authenticates
the named reviewer nor independently verifies benchmark contents or quality;
no replacement model has been selected by this implementation. Eighteen focused
shared/domain worker tests pass, including default and reviewed configuration,
draft/stale review rejection, conflicting effort, wrong workflow, invalid
identifier and the unsupported-host negative case. Evidence:
`worker-selection-shared.xml` and `.log` in the external evidence directory.

Journal–Bank now propagates the selection through `prepare`, graph replay,
launch arguments, launch-receipt validation and both generations of `run-all`.
The CLI accepts `--worker-selection` as an authorized engagement input. Invalid
selection rejects before existing-generation archival. All 64 selected semantic
and worker regressions pass, including the new CLI, divergence and generation
preservation cases (`worker-selection-journal-final.xml`). Mocked launches test
configuration transport, not actual alternative-model or host qualification.
Passive Invoice now propagates the reviewed choice through both CLIs,
configuration, job fingerprints, returned results, checkpoints and native
recovery. Rehashed mismatching model/review receipts are rejected. The integrated
Journal–Bank/Passive Invoice batch passes 130 tests with one opt-in native-run
skip (`worker-selection-integrated.xml`); Mypy passes all 20 configured source
files. These are mocked-launch and local contract checks, not host or alternate
model qualification. Complete privacy-register reconciliation and generated
package refresh remain outstanding.

## 2026-09-06 Computer Use connection update

The current supported entry point is Settings → Computer Use → Google Chrome.
A live extension-backed Chrome binding was observed through `cua.getState()` and
its documented `tab.playwright` controls completed the shipped synthetic fixture:
client-code submission, Invoice selection, Reviewed check, package preparation
and exact terminal text. No separate Chrome plugin is required. Source guidance
and privacy instructions now reflect this setup; the portable runtime still
excludes native desktop actions.

The current `downloadMedia()` call returned without error but exposed no local
file receipt. This particular observation does not prove downloaded byte length
or SHA-256 and is not a new clean capability replay. Preserve earlier individual
receipts with their original scope rather than treating this setup migration as
new portability or native-worker qualification.

### Recovery-case fixture coverage — 2026-09-06

The shipped acceptance fixture now advertises three `recovery_cases` URLs:
`changed-selector` preserves the Client code label while replacing its old DOM
identifier; `unexpected-login` is a synthetic handoff page without credential
controls; `redirected-origin` returns HTTP 302 from 127.0.0.1 to localhost on
the same loopback port, producing a distinct browser origin. The fixture's
self-check probes all three conditions. Both fixture tests pass without skips
(`recovery-fixture-tests.xml` in the remediation temporary evidence directory).

Current Chrome inspection verified zero matches for the old selector and one
for the semantic label, then observed the redirect commit to localhost. No
credentials were entered, no consequential action was performed, and the test
tab and server were closed. This is fixture/browser evidence only. The current
documented CUA surface exposes Playwright but no same-session module-loading
entry point for the shipped capability runner; browser capabilities list only
viewport. Manual clicks are not substituted for `executeCapability` receipts.
Runner-level stale-selector recovery, login handoff, and origin rejection remain
unqualified on this surface.

The browser privacy fingerprint was refreshed after reviewing these loopback-only
synthetic routes. The full privacy validator and all three rebuilt Vera package
checks pass (`recovery-fixture-build.log`, `recovery-fixture-check.log`).
