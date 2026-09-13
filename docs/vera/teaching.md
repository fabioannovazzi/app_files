# Impara con Vera: reusable teaching and acceptance

Vera 0.1.245 adds `learn-with-vera`, a reusable native-voice teaching skill.
“Mostrami come funziona”, “proviamo insieme”, “rifacciamo quel controllo” and
open discovery requests route here through the native model. It reads the current
specialist procedure, executes a real example in a second native chat, explains
the actual result and professional checks, and retains a local checkpoint.

The mandatory first onboarding remains three or four tailored workflows, each
with a demonstration, a distinct user practice and confirmed understanding.
Existing users still complete it once. Later sessions do not repeat the interview,
reset completion or create another professional profile. One teaching/working
pair is reused, with native voice held by the teacher. No Cowork teaching is added.

## Implementation boundaries

- `local_teaching.py` reads the same OS-user profile as `local_onboarding.py`.
  Each teaching session has an atomic revisioned checkpoint and prior copy;
  the example library is derived from those records and completed onboarding.
- The native model interprets goals, selects relevant workflows and judges what
  needs explanation. Python enforces exact session identities, current revisions,
  supported workflow membership, file hashes and completion prerequisites.
- Worker handoffs are bound to actual native task IDs, workflow and a revocable
  local coordination token. That token is not an API key or host authentication.
  Pausing stops new bounded steps; it cannot cancel an already running command.
- The genuine portable case adapter supports both the original lesson and a
  repeated session. Ordinary specialist execution, reviews, model-data reports
  and artifact finalization still apply. Three existing fictional starters cover
  XML checking, journal sampling and variance analysis; other workflows require
  their actual supported inputs and current procedure, not a canned mock report.
- The selected-file handoff hashes only files explicitly chosen by the user and
  requires a separate real-work destination. It revokes the tutorial token and
  makes the tutorial adapter refuse execution. The worker must enter the normal
  specialist/Studio Archive contract, preserving its approval and data boundaries.
- Tutorial profiles, examples, checkpoints and feedback remain local. The local
  marker suppresses server receipts; tutorial feedback is not a change request.
  No custom speech/model API, account credential or Mparanza interview is added.
  Native OpenAI processing still applies to conversation and model-visible files.

## Verified on 13 September 2026

The onboarding/teaching suite exercises profile continuity, repeated sessions,
fresh results, token rotation, stale writes, pause/resume, corrupt-state recovery,
changed inputs/results, exact output focus, guided-practice requirements and the
selected-file transition. Its 60 runtime tests pass with 88.01% combined coverage
and 92% coverage of the new helper. Package tests additionally compare source
bytes in Codex and ChatGPT uploads and absence of teaching in Cowork's files,
router, catalog and registry. Python formatting, imports, typing and Bandit pass.
The full affected regression set passes: 753 tests and two environment-dependent
skips, covering Codex/Cowork packaging, release alignment, routing, website
journeys, privacy, model-data reporting and update behavior.

A separate native Codex task executed the current XML workflow through the
repeated-session adapter and the existing managed Python environment. It checked
the assignment before bounded steps, imported the fictional source into a genuine
portable engagement, and produced invoice CSV/JSONL, anomalies and a reviewed
report. The teacher independently read the report and verified all 11 artifact
hashes. The result was one DEMO-001 invoice: EUR 1,000 taxable, EUR 220 VAT and
EUR 1,220 gross. The model-data report was valid; the completed ledger preserved
all artifacts. Server receipt status was `not_requested`, reason `local_onboarding`.

The teacher recorded the real demo and exact report/CSV focus, then paused the
fixture session. The native file-panel response was `queued`; visibility was
not asserted. The isolated acceptance root was explicitly manufactured by test
fixtures, and neither the real user's onboarding nor their understanding was
marked complete. User participation and professional approval were not simulated.

The new public page was inspected in Chrome, including its rendered Italian
layout and all five language controls. Each version ends with the function's
specific model-data explanation. The marketplace and directory expose the same
“Impara con Vera” entry. Cowork retains its previous professional behavior.

Four broader function-page architecture tests also fail on the unchanged
`c975a888a3d5e1a029d2ddfb49c6541be6b9f14f` baseline: the existing treasury page
has no breadcrumb mapping, the bandi test's text slice spans another function,
the standalone-page count is stale, and a pre-existing paragraph-count assertion
fails. Those unrelated production pages were not changed to mask the failures.

## Native acceptance still requiring a user

The skill can coordinate real native tasks and request artifact panels. It cannot
force microphone permission, start native voice or select the account voice.
The user opens the native voice call and, where no window tool is exposed, opens
the worker in a second window. A queued panel is not proof of visible windows.

Live acceptance must verify: native Italian conversation and interruptions;
visible teacher/worker windows; three or four actual first-use practice lessons;
a later invocation that reuses the profile and pair; pause/resume at the actual
worker checkpoint; and a user-selected real assignment through its normal review
contract. Local ChatGPT Work must separately demonstrate access to the same
OS-user files and native controls. Cloud/mobile access is not inferred from local
storage. These host checks are not certified by package publication or fixtures.
