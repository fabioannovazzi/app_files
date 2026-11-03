# Vera UI consolidation and Desktop reopening

Status: source repair and release preparation; installed-host acceptance is pending.

The release combines the retained UI branch with production `c7448d4c0`, preserving
its native-only editor retirement, private report preview and privacy controls.
Vera advances to 0.1.559, Clara to 0.1.372 and Lucia to 0.1.198.

## Observed Desktop failures

A retained temporary Bilancio audit panel returned `PermissionError: Run is not
authorised in this workspace`, including after refresh. The fresh `aurora_2025`
card opened, returned to its one-case authorized directory and reopened the same
saved case. This establishes a failed retained-card path; it does not establish
why that older panel held an unusable connection or reference.

The ordinary installed Vera panel opened the client directory and navigated an
existing synthetic client, engagement and saved bank reconciliation. The real
read-only result was visible. This is distinct from the temporary audit servers.

At 21:57–21:58 UTC, the Desktop application log recorded the central app page
failing to read `ui://vera/workspace-v1.html`: its app-launch connection failed
MCP initialization with `connection closed: initialize response`. Discovery also
failed for Clara and computer use. The app error appeared before Vera rendered.
The separate active-chat Vera connection continued to work. These are separate
observations, not proof of one common cause.

## Repairs

A failed review-card open now offers an explicit return to the current
connection's authorized directory. The existing backend authorization and dirty
local draft guards remain mandatory; recovery never guesses another run, widens
access, edits the binding file or retries a professional write.

Product MCP entries use the documented `${PLUGIN_ROOT}` paths. A relative entry
was observed to initialize from the plugin directory and fail from an unrelated
working directory. Regression tests initialize an integrity-sealed synthetic
installation outside its directory. Cowork projection maps the root placeholder
to its existing `${CLAUDE_PLUGIN_ROOT}` form. This is a launch-path correction;
Desktop's central app route still requires installed-host retesting.

The consolidated UI retains responsive queues, grouped supporting evidence,
readable source selections, Italian Bilancio issue captions, structured synthetic
transformation fields, current agenda form selection, and bundled font weights.
No new external recipient or model-context producer was introduced by these UI
changes. Professional requests retain their existing exact source selections,
server-side validation, signed authority and explicit execution controls.

## Shared runtime and privacy review

The common runtime source, all three projections and the generated universal
lock now use policy revision 16. Intel macOS selects cryptography 48.0.1 and other
supported platforms retain 50.0.1. The installer requires cryptography wheels;
no runtime compiler toolchain is introduced. The upstream changelog records the
removal of Intel macOS support in version 49:
https://cryptography.io/en/49.0.0/changelog/
This is lock/selection evidence, not execution on Intel hardware.

The privacy source review inspected the changed UI/transport paths, package
projection, local installer arguments, registry/component inventory and retained
model-data contracts. UI data remains in existing app metadata; explicit chat
handoffs retain their existing model boundary. The installer sends only declared
package requests to the existing index. Changes add no client-data transmission,
new recipient, retention store, authentication exception or professional approval.
Fingerprints are refreshed after that source review, not treated as its substitute.

All 58 rebuilt teaching courses compare equal to production except their source
identities. Existing language content, inputs, practice definitions and historical
editorial judgments are preserved. The new course hashes require fresh native
teaching CI; no historical execution is relabelled as a fresh run. Geneva's 55
entrypoint IDs and skill hashes are unchanged; only its manifest binding advances.

## Acceptance boundaries

Passing source regressions, package validation, installation, deployment, public
ZIP verification and actual Desktop navigation are separate gates. The central
app startup failure and complete installed UI campaign remain open until tested.
No Marketplace upload, submission or publication is part of this release.

## Source verification recorded before deployment

The focused UI selection passed 177 tests. Seven additional real Chromium
regressions initially failed before browser startup because the local sandbox
refused Chromium's Mach-port registration; all seven passed with the required
host execution permission. Retained bank review/navigation passed 19 tests.
The on-demand transport suite passed 63 tests with 92.31% coverage of its
catalogue builder. The three explicit plugin-root launch regressions are part
of that suite. Runtime lock selection passed 16 tests. Full package/runtime
checks, native teaching CI and installed-host acceptance remain separate gates.

Vera 0.1.558 was installed as a local candidate from the built Codex package
with package identity
`8a1d33c373987b780de3667c539602350db9606151c01a1b6aecd46017b1e175`.
The installer reports that active-chat acceptance requires a fresh chat; this
installation is not recorded as a successful central-app reopen. Exact final
CI artifact installation and public release verification are still required.

All three Codex, Cowork and Antigravity product builds completed with aligned
versions. The runtime selection reached 80.40% coverage with 319 passing tests;
one legacy test still allowed only the relative entry spelling. Its allowlist
now also accepts the exact plugin-root on-demand launcher, independently exercised
by the process-level launch regression. Both focused launcher checks then passed.
The consolidated change is reviewed in repository PR #945. CI results and final
deployment evidence must be attached to its final tested head, not inferred from
this local build or the candidate installation.

## Corrected course display handshake

CI for the first consolidated candidate caught a regression introduced during
consolidation: copying the course branding edit also dropped the deployed
fullscreen capability declaration. All failed archive builds stopped at the same
packaged course-resource check. Restore the existing inline/fullscreen handshake
and assert the actual emitted initialization message in the course UI behavior
harness. The corrected Vera candidate uses 0.1.559, leaving the earlier installed
0.1.558 candidate identifiable. That earlier installation is not final acceptance.
The correction restores the deployed display contract and adds no data boundary.

The corrected 0.1.559 candidate passes all 42 course-chat behavior tests and the
exact finished Codex-package resource check used by the archive CI gate. All
three host formats rebuilt successfully for Vera 0.1.559, Clara 0.1.372 and Lucia
0.1.198. The corrected locally installed Vera package identity is
`57acbebf4dc6c808631941cba6b8873be1b4c077ccd6a08b7d6841f5fad31f46`.
The final CI artifacts, deployment and fresh Desktop connection remain separate
verification gates.
