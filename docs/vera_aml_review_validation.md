# Vera AML review — implementation and validation

Date: 2026-09-05. Scope: local implementation; no deployment or publication.

## Implemented

- `plugins/aml-review/skills/aml-review/SKILL.md` supplies the Italian AML
  investigative method for new clients and subsequent reviews. The model examines
  ownership, economic explanations, contradictions, counterevidence and changes.
- `plugins/aml-review/scripts/aml_review.py` checks exact source receipts, binds
  professional decisions to the proposal, preserves immutable content-addressed
  records, and calls the existing validated New Client calculation when supplied.
  It does not select risk factors, decide suspicion or certify compliance.
- Vera routing, Marketplace card metadata, archive Python and MCP registries,
  component packaging, icon and privacy registration include `aml-review`.
- `static/shared/aml-review/index.html` explains inputs, method, illustrative
  example, output, limitations and the actual model-data boundary in IT/EN/FR/DE/ES.
  The page is linked from Vera's Italy function directory and New Client's AML
  section. Its final process section explains model-visible data.

## Checks performed

| Check | Result |
| --- | --- |
| AML helper tests | 21 passed; 90.31% coverage across both new scripts |
| AML, archive, icon and New Client taxonomy regression set | 127 passed |
| Actual archive CLI | Passed with running v2 receipts; wrong workflow rejected |
| Successor run | Passed using a finalized prior record in the same engagement |
| Existing calculation reuse | Passed; unresolved Table 1 remains blocked |
| Record mutation and review binding | Changed evidence, stale decisions and mutated records rejected; prior versions retained |
| Black, Isort, Mypy and Bandit on new Python | Passed |
| Skill frontmatter and standalone component source validation | Passed |
| Browser review | Italian layout inspected; all five language switches and final data sections verified |
| Git whitespace check | Passed |

The independent synthetic behavioral test is at
`/private/tmp/aml-forward-test/review.md`, with limitations and assessment in
`/private/tmp/aml-forward-test/evaluation.md`. Five invented source documents
included an ownership discrepancy and an explained third-party payment. The
review retained the ownership issue, recognized the documented payment mandate,
preserved counterevidence and did not infer either suspicion or clearance from
the mismatch alone. This is one synthetic test, not real-client validation or a
measurement of error rates. The independent agent authored and assessed its case;
it was not blind scoring against an external benchmark.

CNDCEC 2025 rules and March 2026 guidance were verified. The Normattiva entry
point returned an error; the professional-method reference discloses this and
requires current consolidated-law verification before article-level conclusions.
During the continuation check, an alternative official Normattiva result loaded
but displayed text effective on 2023-02-06 despite a 2026 amendment date in its
header. The method now explicitly distinguishes those dates and explains how to
recover from a failed URN without treating historical text as current law.

## Deployment validation (2026-09-05)

Release assembled in an isolated checkout from main after PR #520. Unrelated
Business Planning and runtime source edits in the primary checkout are excluded.
Vera Codex, ChatGPT upload and Cowork packages were rebuilt and passed source
checks; Cowork initialized all 18 packaged MCP servers. Shared archive identifier
changes also require regenerated Clara and Lucia install artifacts, without
changes to their product workflows. Privacy fingerprints are current.

The broader first run passed 510 tests and found seven failures. Two old test
expectations needed the additional AML skill count and homepage mapping; one
required regenerating shared dependent packages. Two Clara image-output checks
and an existing homepage CSS check concern unchanged code outside the AML change.
The update notification check also detects Clara 0.1.164 installed against
published_version 0.1.163; the publication listing could not be inspected under
the current approval scope, so the public notification manifest was unchanged.

Marketplace publication is separate from server deployment. These tests do not
establish real-client reliability or host-level professional workflow acceptance.
