# Vera incident pipeline review

Automation is paused. This branch is a release candidate, not a production
acceptance claim. The earlier 0.1.370 capture correction is already deployed.

## Observed defects and corrections

| Boundary | Inspected evidence | Correction |
| --- | --- | --- |
| Connector delivery | Native 0.1.370 recorded three original reports, but the blocked shell left three local outbox items and `registered:false`. | Actual recorded original/outcome receipts acknowledge only their exact local queued IDs; identity and raw diagnostic files are preserved. |
| Polling and fixed retry | `check` raised `URLError: Tunnel connection failed:403Forbidden` before status or action processing. | An unavailable direct transport returns the independent route. Actual cached connector status can drive the two fixed actions with a matching existing local receipt; no HTTP poll is needed. |
| Remedy scope | A self-contained two-installation reproduction sent the first case's action to the second installation because generic signals shared an incident. | Every actionable remedy targets an explicit latest original report. Status and outcomes use the applicable revision for that report. Unrelated remedies do not replace it. |
| Revision evidence | `remedy` overwrote the previous JSON. `show` exposed no history. | Retain revisions from the surviving migration snapshot onward. Lost legacy revisions remain unknown. |
| Closure | A helper name/workflow match automatically closed setup incidents without proving the original case. | Helper success is readiness. Host AI must verify original task and inputs before recovered status for every incident type. |
| Delayed outcomes | A new delayed failed outcome for the same already recovered report could reopen its delivery. | Retain the outcome as history without reopening that episode. New failure episodes require a new original report. |
| Parent/early failure | Parent RuntimeError was not retained; missing entrypoint/integrity errors returned before helper reporting. | Retain complete known parent exception chains. Early guards explicitly route observed evidence through the independent connector without running unverified reporting helpers. |
| Cached readiness | A recovered service record still left an offline observed-success hint locally. | Reconcile actual cached status with existing local receipts. Queue readiness as action-required or clear only matching recovered hints; retain unlinked hints. |
| Recovery diagnostics | Fixed-action stderr was mechanically scrubbed and immediately uploaded. | Retain complete raw stderr privately for model review; transport no raw recovery output. |

The baseline 99 tests passed despite these gaps. New regressions cover scoped
remedies, independently applicable revisions, migration, delayed outcomes,
connector acknowledgement, receipt ordering, offline retries and private
recovery diagnostics. Required CI and native acceptance must pass before release.

## Authority and remaining boundaries

Diagnosis and relevant technical evidence selection remain model-led. Fixed
checks enforce mechanical identity, ownership, revision and receipt matching.
The service receives no client files, prompts or professional stdout. The host
model can read retained stderr under its selected account and excludes unrelated
private material before submitting relevant diagnostics.

Automatic approval review rejected constructing a local retry receipt from
remote metadata. That proposal is not implemented. The current route requires
an existing local receipt. Old linked incidents remain readable through the
saved connection; ordinary authorised workflow resumption remains available
when the original case context is present. Neither missing receipts nor missing
case inputs are fabricated.

The original real bandi cause and recovery are still unknown. Its old exit-only
reports cannot retroactively supply a missing stderr chain. Controlled native
acceptance establishes protocol behaviour, not recovery on someone else's PC.
No Marketplace publication, external support messages, permission expansion or
new Windows-specific tests are part of this work.

## Local validation of the release candidate

The incident regression suite passes 119 tests with 89.71% combined backend and
client coverage. Black, isort and mypy pass for the changed source. Bandit reports
no medium or high findings. Package startup checks include all 22 Cowork
connectors. Required PR CI, public artifact parity and native acceptance are
independent release gates; the monitor remains paused.

The shared course-review folder also governs Clara teaching privacy. Its unchanged
record is rebound without changing review dates or data flows. Clara 0.1.271 is
a binding-only companion package; Vera remains 0.1.372. ChatGPT upload archives
are regenerated as downloads, without Marketplace submission. The expanded local
package suite passes 641 tests with two environment-dependent skips; all 84
Clara release/privacy checks pass.

The additional cached-readiness reproduction is corrected. The final local
incident suite passes 124 tests with 89.87% coverage, including preservation
of unlinked and unacknowledged readiness hints.
