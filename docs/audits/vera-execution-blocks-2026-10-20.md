# Vera execution-block audit — 20 October 2026

Status: in progress. This document is not a release or acceptance claim.

## Mandate and acceptance

Inspect repository instructions and execution blocks; remove restrictions that
have no demonstrated contribution to correctness or authorized operation.
Deploy through Git and verify source, packaged/installed behavior and normal
chat behavior. Keep every observed block in the test record, including recovered
ones. A successful final result must not hide intermediate restrictions.

The existing 13-pipeline acceptance remains outstanding. Bank reconciliation is
first; no later pipeline may start until its result, automatic privacy-report
delivery and server hash/userID verification pass. Test chats use GPT-6.1 Sol;
repairs take place in the main Astra chat.

## Findings established from inspected evidence

| Finding | Evidence | Decision and current state |
| --- | --- | --- |
| Exact external executable allowlist stopped Luna after a Codex update | First test chat `01a157c4-1566-7283-bb31-62844503eb81`; previous `semantic_review.py` profile pinned CLI 0.160.1 | Previous change `e97e0ef65` replaced this rule. Fresh installed behavior still needs acceptance in this audit. |
| Shared Python policy 13 was rejected by plugin policy 12 | Second test chat `01a15840-c44f-7882-99e4-cd13beb0b5c6`; `_shared_python_runtime._install` | Remove policy revision and same-revision recipe rejection as execution prerequisites. Actual declared dependencies determine reuse. Source repair in progress. |
| Backend/recipe differences forced a working environment through installer policy gates | `_shared_python_runtime.ready` compared hashes against current package bytes | Replace with installed version and component checks. Preserve existing installation receipts on compatible reuse. A read-only probe of the previously blocked environment passed without changing either metadata file. |
| Documentation and tests reinforced the policy rejection | `docs/shared_python_runtime.md`; former `test_older_plugin_cannot_downgrade_shared_policy` | Rewrite documentation and tests around usable compatible environments and real missing dependencies. Keep serialization during package mutation. |
| A changed Python platform label required a manual rebuild | `_shared_python_runtime.ready` and `_install`; former `test_actual_interpreter_mismatch_rejected_before_mutation` | Check the current CPython interpreter, declared package versions and native component imports. Compatible changes reuse the environment without rewriting installation history; failed imports remain unavailable after failed repair. |
| Installed-version acceptance rejected all local candidates | `scripts/check_installed_product.py`, `.agents/skills/plugin-release/SKILL.md` and its local-installation rejection test | Accept one enabled matching candidate. An optional exact plugin registration checks a particular distribution; local acceptance never proves Marketplace rollout. Keep version and current-session skill checks. |
| The test-harness instruction could be read as forbidding requested product repairs | `AGENTS.md`, Coding Practices | Clarify that fixing import/fixture defects in tests is separate from fixing an observed production defect. Existing rejection tests are not product authority. |
| Mapping-review text leaves agent versus professional review unclear | `journal-bank-reconciliation/SKILL.md`, `seal_review_receipts.py`, `journal_bank_core.build_mapping_review_receipt` docstring; first chat's recovered approval rejection | Inspection continues. Automated approval review rejected proposed clarification as removal of human-review safeguards. Exact user clarification requested; no rejected edit applied. |
| UI strategy includes “before doing anything else” setup choices | `.agents/skills/plugin-ui-strategy/SKILL.md` | Candidate instruction change, pending resolution of the rejected instruction patch. The same skill already prohibits ceremonial continuation requests. |
| Reporting imposed an Archive prerequisite on non-Archive model operations | `mcp/workspace.cjs`, `native_workspace._reporting_case`; 14 Transformation source-MCP failures returned “Vera could not bind this request to its outgoing-data record” | Pass the actual operation from the MCP server. Transformation and practice-review workspaces do not acquire an unrelated Archive reporting prerequisite. Eligible Archive workflows retain their binding and recording checks. The first previously failing complete context/stage/adoption case passes after repair. |
| Shipped operational guidance still declared repaired native routes unavailable | `skills/vera/references/native-workspace.md`, `privacy/services/native-workspace.json`; current communication lock exclusion, resolved transformation replay directory and initial-adapter code identity | Replace obsolete failure counts and unapplied-repair statements with the inspected current behavior. Communication source/UI tests pass; the first full Transformation source-MCP case passes. Keep installed-host acceptance separate. |
| Patent Box guidance still demanded a signature and firm mandate before calculation, although the producer now requires the user's exact proposal confirmation | `patent_box/proposal_review.py`; `test_patent_box_real_local_review_does_not_authorize_calculation`; native guide and service declaration | Align guidance with the existing proposal-confirmation contract. Human confirmation remains required; signed-document formalities are a separate optional route. No agent approval is substituted. |
| PDF layout recovery has fixed lifetime caps despite evidence-based revisions | `vera_journal_pdf/recovery.py`: four attempts and twelve inspections; shared `pdf-recovery.md` | Removed lifetime count gates. Distinct evidence-based trials and inspections can continue; duplicate recipes, source integrity, full replay and per-call evidence bounds remain enforced. Five focused regressions passed, including a valid trial after 100 previous trials and a thirteenth inspection. |
| Rating Legalità refuses evidence processing for absent mandate/data-governance review or an overdue review date | `rating-legalita/scripts/practice_controls.py:practice_summary`, called before evidence assessment by `rating_case.py` | Confirmed execution gate. Its professional-review requirements remain under review; no removal or replacement with agent approval has been applied. |
| New shared-runtime integration initially restored the old restriction during a build | `sync_reporting_runtime.py` copies `_shared/reporting-runtime/_shared_python_runtime.py` into all three products | Corrected the canonical shared source, then synchronized all copies. Product-copy edits alone were insufficient. Rebuilding must preserve the repaired shared source. |

The policy number is Mparanza installation metadata, not a Python version.
The local environment identifies CPython 3.12. This audit has not established
which process originally wrote local policy 13.

## Audit coverage and outstanding work

Initial searches retained 160 instruction candidates and 1,230 code candidates
in `/private/tmp/vera-instruction-block-candidates.txt` and
`/private/tmp/vera-code-block-candidates.txt`. These are search hits, not verdicts.
Generated host packages are derived from source and must be rebuilt after changes.

Still to inspect:

- Mandatory human-review, preview and export gates across the 13 pipelines and
  other Vera specialists; distinguish result preparation from adoption or filing.
- Mandatory mandate/data-governance records in `rating-legalita` before evidence
  processing, including the effect of an overdue review date.
- Source-layout, identity-format, model/host and receipt-version restrictions.
- Instructions that treat existing rejection behavior as a requirement rather
  than test a concrete failure and a valid case that must remain usable.
- Remaining component and native Archive entrypoints using the shared runtime.
- Package integrity, installed activation, production deployment and repeated
  normal-chat acceptance after the final changes.

The audit does not infer that a matching string proves a restriction is useless.
Client identity boundaries, exact source/output receipts, actual missing
capabilities and authorization for external actions require separate evidence.

## Verification record

- The original baseline automatic-reporting and native Archive-closure tests
  passed before this audit; those tests did not prove installed workflow success.
- Modified source accepted the actual policy-13 bank-reconciliation runtime;
  policy and ready-receipt SHA-256 values were unchanged.
- Repeated that read-only live probe after integrating PR #879's dependency locks
  and inventory validation: readiness passed, with installed revision 13 and
  source revision 14; both metadata files remained unchanged.
- Runtime and managed-launcher regressions passed after removing platform-label
  gating (118 selected tests). Compatible changed-platform cases, real dependency
  failure and unavailable-interpreter metadata preservation are covered.
- Relationship, mapping-receipt and installation-checker tests passed (128 tests).
- Communication source and UI tests passed (18 tests).
- A wider native selection returned 153 passes and 19 failures. Fourteen
  Transformation failures were traced to the reporting binding described above.
  Five closure/package failures were traced to generated privacy records still
  describing the pre-edit source. They require regeneration and retesting, not
  removal of the source-integrity check.
- Four focused reporting-scope regressions pass after the routing repair,
  including refusal for an eligible bank run without its authorized Archive.
  The previously failing full Transformation context/stage/adoption case passes.
- After integrating main and rebuilding contracts/packages, the broader source
  regression run passed 351 tests (automatic reporting, Transformation routes,
  PDF recovery, relationship assurance and installed-product checking).
- The integrated managed-runtime suite passed all 268 tests with 82.77% measured
  coverage. Its launcher fixture now supplies the declared requirement parser
  inside the isolated test interpreter; 18 failures from the empty fixture were
  repaired in tests, without weakening production readiness checks.
- All 68 Archive closure tests passed after regeneration, including the earlier
  failures caused by stale packaged privacy dependencies.
- Final packages built successfully for Vera 0.1.438, Clara 0.1.317 and Lucia
  0.1.141 across Codex, Cowork and Antigravity. Shared dependency lock exports,
  coordinated revision, source synchronization and the 55-entry Geneva catalogue
  checks passed. Declaring the requirement parser directly changed no dependency
  version pins. Its lock files and evaluator are now included in the runtime
  service's governed source inventory.
- Changed-file Mypy (including the 29-file managed-runtime configuration and
  native routing), medium/high Bandit and formatting checks passed after
  integration. Remote CI and installed normal-chat acceptance remain outstanding.
- No deployment or successful normal-chat acceptance is claimed yet.

## Related work

PR #879 (`fix/shared-runtime-equivalence`, inspected head
`dffe70a179e76c37e30e04a3acfcf33b9b4d314f`) also changes the shared installer
and uses policy 13. It retained the newer-policy rejection. It merged into main
as `eb2065b62`; its integration has passed the local checks above. Preserve its
hash-checked dependency locks, installed-inventory checks and serialized setup,
while retaining capability-based reuse and removal of policy-number rejection.
This audit uses revision 14 solely as installation history. Current candidates
are Vera 0.1.438, Clara 0.1.317 and Lucia 0.1.141; none has been deployed by this
audit. The process that wrote the local policy-13 file has not been established.
