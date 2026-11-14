# Vera Archive release — 14 November 2026

Archive retrieves a client's or project's incarichi, current documents, issued
revisions and associated chats. Requests, new attachments and revisions belong
in the associated host chat. One incarico owns one purpose and pipeline. The
main page opens document and chat titles directly; it has no request composer,
generic pipeline launcher, manual assignment creation or repeated format buttons.
The mixed global tools menu is removed. Existing specialist reviews reopen from
their exact saved work and retain decisions. The generic chat action is
**Vai alla chat**; recovery says **Torna ai lavori dello studio**.

Shared publication keeps stable named deliverables, grouped formats, dated
revision history and idempotent retries. Cross-assignment sources identify the
exact issued version and origin. Interrupted work and prior receipts remain
recoverable. Product-scoped defaults keep Vera's `studio_archive` separate from
Lucia's `lucia_archive`; temporary selections do not replace those defaults.

## Release integration

- Vera 0.1.643 contains the accepted local 0.1.642 implementation and current
  main's reconciliation budget fix from #999.
- The separate Lucia #1000 release is integrated before deployment. Its accepted
  HTML, wrapper, service registration, fonts and Archive skill remain byte-identical.
  Lucia 0.1.252 distinguishes the subsequently combined shared runtime from its
  independently released 0.1.251 package.
- Clara 0.1.420 and Lucia 0.1.252 rebuild the shared session, assignment, recovery
  and source-binding dependencies. Their professional engines are not redesigned.
- Generated host packages, course source bindings and privacy projections are
  rebuilt from the combined canonical source. Authored lesson content and prior
  editorial/output evidence are retained; source hashing adds no new acceptance.

## Evidence

- Source/UI/default checks: 98 passed.
- Assignment/publication/recovery/native component checks: 398 passed, with
  84.98% coverage of the shared assignment and publication core.
- Combined product defaults, Lucia panel and on-demand transport: 103 passed.
- All host builds and independent package alignment checks pass for Vera 0.1.643,
  Clara 0.1.420 and Lucia 0.1.252. Eight Vera/Lucia host packages pass 108 exact
  resource comparisons. The 129 packaged integration cases pass across the initial
  and corrective runs; the recovered fixture failures are described below.
- Six key Vera UI/continuity source files match accepted 0.1.642 bytes. Seven
  Lucia panel/service/skill assets match the coordinated #1000 release exactly.
- Existing installed-host acceptance: Fabio confirmed saved-document opening and
  associated-chat reopening in Eutekne → E26-01, and the saved business-plan review.
- Synthetic continuation retained the same incarico, imported one new source,
  issued Parere revision 3 with both formats and kept revision 3 on exact retry.
- Reconciliation reopened the saved run with its two accepted decisions and one
  document request byte-identical. Fabio's screenshot confirms the saved request
  and its text. Two accepted labels in the collapsed chooser remain visually
  unconfirmed; Fabio explicitly removed that extra observation as a completion gate.
- Bilancio-to-plan recovery retained both exact revision-1 source formats after
  source revision 2. The user confirmed the saved plan review was visible.

The suites overlap. Registry/UI checks do not mean every professional engine was
rerun. CI and package checks do not prove new native-host or signed privacy-report
acceptance. A mistyped test filename initially ran no tests; the corrected existing
test selection passed. Extracting only workspace.js initially omitted its sibling
review-routes.json; the same unmodified ZIP passed all 73 UI cases after complete
UI extraction. Two public-to-native session cases hit sandbox restrictions on the
installed shared runtime. A temporary runtime-root override instead triggered an
empty environment and blocked package-index access; that override was reverted.
Both cases pass using the existing shared runtime under authorized local access,
with synthetic archives and profiles still isolated. Assertion errors now preserve
complete JSON diagnostics. No product guard was bypassed. Generated merge conflicts were resolved through canonical
source integration and package rebuilding, without hand-merging ZIP contents.

The original dirty Vera checkout and drafts are explicitly retained. Only the
isolated release checkout is used to update #998. Deployments are sequential:
Lucia first verifies its release, then releases the deployment slot to Vera.
Marketplace upload, drafts, review submissions and publication are excluded.

Final CI, deployment commit and public artifact hashes are recorded in the task's
release evidence after they are observed; this document does not pre-claim them.

CI fixture corrections retain production validation: the synthetic reporting
session now uses a valid UUID for automatic chat association, and Lucia's panel
fixture reads its Italian text explicitly as UTF-8 on Windows. Neither correction
changes the validated package contents or accepted interface.

The readable Archive CI suite now exercises two issued revisions and their chat
link after a client-folder move, including a missing historical format. All 14
cases pass with 85.02% coverage; the required 80% threshold is unchanged.

The shared tutorial and merger adapters register their dynamically loaded Archive
modules before execution, matching the existing adapters. Without registration,
assignment and publication calls raised a missing-module error outside pytest as
well. Both adapter regressions failed before the repair and now pass; the combined
assignment/tutorial/merger suite passes 258 cases. The exact input/source job passes
368 cases with one skip and 86.46% coverage. All 65 browser/review cases pass after
updating the expected direct-native routes and checking the visible heading's font
instead of the removed subtitle. The first local browser run was denied OS launch
access by the sandbox; the authorized rerun used the existing Chromium installation.

All host distributions are rebuilt for the loader repair. Fifteen course source
bindings and five privacy fingerprints were refreshed after reviewing the two
registration changes; authored lessons, historical review evidence, recipients and
the accepted product interfaces are unchanged.

Canonical theme synchronization moves the generated block after the local Archive
rules. Its output is byte-identical to the already validated package stylesheet;
114 theme tests pass. Fourteen additional Vera-only privacy fingerprints are
refreshed for the canonical source, with no course binding change. The course
review/projection checks pass 64 cases with one skip.

The full teaching CI run then passed 1,747 cases and exposed five follow-up
failures in the test-only New Client helper. That helper omitted registration of
its dynamically loaded Archive module. Registering it fixes all ten demo and
follow-up cases across five languages; Black and isort pass. This correction
changes no production source, package, authored lesson or acceptance boundary.
