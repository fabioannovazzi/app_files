# CI incident isolation and reviewed test closure

The November 12 morning alert described four Clara 0.1.409 Cowork dependency
failures. Retained evidence from CI run 43013688712 contains the same platform,
Python version, exact missing-dependency list and failure timestamps as the four
server reports: Linux 3.10 at 11:59:15 UTC, macOS 3.12 at 12:00:45, Windows 3.12
at 12:03:21 and Windows 3.10 at 12:04:14 (server receipt 12:04:13). This is an
operator review of those exact reports, not a rule that classifies future errors
from their text, version, platform, installation or machine identity. The next
candidate's same four CI jobs passed in run 43018141915; its dependency-check
correction is already in the deployed Cowork package.

The acceptance runner rebuilt its child environment after removing inherited
`MPARANZA_` variables, losing local-only incident isolation. It now explicitly
sets `MPARANZA_INCIDENT_DELIVERY=local-only`. Every CI workflow has the same
default. Failed steps remain failed, with diagnostic logs and result JSON
retained; production user reporting and test assertions remain enabled.
Root and standalone plugin pytest entrypoints use the same default for local
automated tests, including collection before individual fixtures run.
The shared minimal Python/Node child environment also preserves this named
delivery setting; its generated Check Entries source copy matches the canonical
list. It still excludes unrelated credentials and tokens.
Mocked delivery tests opt into automatic delivery only for an in-process SQLite
transport or their owned loopback server. The CI regression rejects a workflow,
job or step overriding this default to automatic delivery.

`manage_incidents.py close-test` adds an operator-only administrative disposition.
It requires a review note, evidence references and the exact inspected incident
digest. The full reports and supplements remain retained with the immutable
closure history. No successful retry, recovery outcome or customer acceptance is
invented. Closed tests leave the open queue and unresolved counts. A new report
or supplement reopens the group and requires another review; no identity is
permanently excluded. Stale evidence prevents closure. The summary accepts the
explicit disposition when reconciling an incident that left the queue.

The hosted operator data changes require refreshed source declarations in all
three product privacy packages: Vera 0.1.617, Clara 0.1.411, Lucia 0.1.234. Skill
entrypoint bytes and compiled teaching content are unchanged. Localization binds
the new manifest without altering jurisdiction judgments. This is engineering
review, not new learner, customer-host or professional acceptance. No Marketplace
action is authorized or performed.

Validation before CI: 269 incident-service tests passed with 86.45% coverage;
320 native/reporting tests passed under the CI local-only default, with eight
native Windows cases skipped on macOS; 54 acceptance-harness tests and 65 workflow
isolation/teaching-scope tests passed. Black, Isort and Bandit pass. Mypy passes
for the changed store/operator/summary modules. Running Mypy additionally over
the acceptance script exposes its existing unannotated `trend` variable; its
pre-existing implementation was not changed to repair a test-harness check.
The initial local-only test run exposed delivery mocks that inherited CI policy;
their isolated fixtures were corrected, with no production behavior weakened.
The complete incident CI command subsequently passed 596 tests (eight Windows
skips on macOS) with 83.17% coverage. All 72 shared environment/workflow tests
passed, and all five closure regressions passed, including immutable re-closure
history. An early package run overlapped the reviewed environment source refresh;
its stale-contract failures are discarded and a stable full rebuild/recheck is
required. The local curated Clara cache also exposes a pre-existing discrepancy
with the historical public Marketplace update manifest (0.1.407 versus 0.1.248).
This task does not infer publication from a cache or change Marketplace state.

Final stable-source verification: 597 incident CI tests passed with eight native
Windows skips on macOS and 83.17% coverage without an externally supplied
delivery override; 55 harness tests passed with the plugin pytest default.
Package/update/index checks passed 432 tests, with the two local installed-cache
publication comparisons explicitly deselected as unrelated mutable external
state. Fresh CI runs those original tests unchanged in its own environment.
All three Codex ZIP/source drift checks and generated privacy contract checks
passed after the stable all-host rebuild. No source refresh ran during this
final package check.

Fresh current-head CI, deployment, exact package/download verification and the
four administrative closures are separate required completion steps. No closure
is claimed merely from these source checks.
