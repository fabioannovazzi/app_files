# P0 case contract

`scripts/run_fusione.py` provides `init`, `apply`, `show`, `export` and `demo`.
All non-demo commands require `--case /absolute/case-directory --actor actor_id`.
`init` and `apply` require `--request /absolute/request.json`. `show --id object_id`
returns one current record and its effective status. `export` requires a fresh
`--output` directory and accepts `--runtime-profile openai-codex|anthropic-cowork`.
Do not use an example actor to represent an actual professional.

Initialization request:

```json
{
  "operation_type": "fusione",
  "objectives": "The user's documented objective",
  "jurisdictions": ["IT"],
  "planned_date": null,
  "actual_date": null
}
```

The helper generates an operation UUID. Each stored record has `id`, `kind`,
`version`, `operation_id`, `scope` (company IDs), `work_status`, `created_at`,
`author`, `data`, `dependencies`, and `sha256`. Work status is `draft`,
`in_progress`, `missing_evidence` or `review_pending`. It is separate from the
fact state and from effective professional approval.

Every dependency uses exactly `operation_id`, `id`, `version`, `sha256`, copied
from an inspected record. An identity cannot change kind or company scope.
Cycles and duplicate dependency identities are rejected. Missing references and
foreign operation IDs are rejected. A record retains the union of its dependencies'
company scopes so a combined draft cannot leak another company's information.

`apply` actions:

| Action | Required fields besides `action` |
|---|---|
| `put` | `object_id`, `kind`, `data`, `scope`, `dependencies`, `expected_version`; optional `work_status` |
| `import_evidence` | `object_id`, `entity_id`, absolute `source`, `locator`, `description`; optional `expected_version` |
| `artifact` | `object_id`, absolute `source` under this case's `drafts/`, `scope`, `dependencies`, `recipient`; optional `expected_version` |
| `approve` | new `object_id`, exact `target` reference, `professional_role`, `scope_text`, `confirmation` |
| `grant` | `actor`, `role` (`reader`, `editor`, `reviewer`), explicit `entities` |

`expected_version` is zero for a new object or the current version for a revision.
Generic `put` cannot create Evidence, Artifact, Decision or ChangeImpact. Imports
copy one ordinary file from the company's explicitly registered directories into
the database; symlinks and files over 20 MiB are rejected. The source's path, size,
hash, locator, importer and original bytes are retained. Artifact bytes are also
snapshotted; a PDF alone never creates a verified signature or filing status.

## Data fields

The following fields are exact: unexpected or missing fields fail validation.
Use the complete example in `scripts/fusione_demo.py` to compose reviewed requests.

| Kind | Data fields |
|---|---|
| Operation | `operation_type`, `objectives`, `jurisdictions`, `planned_date`, `actual_date` |
| Entity | `name`, `legal_form`, `role`, `residence`, `accounting_framework`, `source_roots` |
| OwnershipEdge | `holder`, `company`, `ratio`, `rights`, `as_of` |
| Fact | `description`, `fact_status`, `value_kind`, `value`, `unit`, `as_of` |
| SourceVersion | `title`, `url`, `checked_on`, `access_status`, `error`, `source_version` |
| RuleVersion | `statement`, `citation`, `review_status`, `published_on`, `effective_from`, `effective_to`, `applicable_from`, `applicable_to`, `transitional_notes`, `scope`, `preconditions`, `exceptions`, `test_refs` |
| BranchDecision | `branch`, `rationale`, `conditions`, `support_status` |

An Entity has exactly its own ID in record `scope`; only the case administrator
creates/revises company bindings and grants. Explicit unknown identity details can
be recorded as text describing the gap, rather than invented legal forms or regimes.
Ownership requires exact Entity dependencies for both participants and a fraction
between `0/1` and `1/1`. This structural range does not decide economic control.

Fact states are `known`, `unknown`, `disputed`. Unknown/disputed `value` is null;
alternatives stay in the linked evidence and description. Known/disputed facts need
an Evidence dependency. Value kinds are `text`, `decimal`, `fraction`, `date`,
`boolean`. Amounts are decimal strings (`"100.00"`); ratios are exact fractions
(`"2/5"`); dates are ISO calendar dates. No float or months-to-days conversion exists.

Source access is `retrieved`, `failed`, `not_checked`. Retrieved requires an Evidence
snapshot; failed requires a non-empty error; other attempts use a null error. Every
attempt is a new version, including failures. `url` is a locator, not a fetch command.

Rule review states are `candidate`, `source_checked`,
`professional_review_pending`, `superseded`, `withdrawn`. Rules require exact
SourceVersion dependencies. Temporal fields may be null when unknown; no current-law
claim follows from download time. Approval requires pending professional review,
explicit applicability start, declared tests and accessible successful source
dependencies. These prerequisites do not prove legal validity or test execution.
`approved_for_defined_scope` is derived from a separately recorded Decision for the
unchanged version. A new rule revision never inherits that approval.

All P0 BranchDecision records have `support_status: "unsupported"`. The model
records the proposed branch and why further work is needed; code never selects it.

## Revision and approval semantics

Approval is blocked by unknown/disputed facts, failed/unread sources, stale or
withdrawn dependencies, unsupported branches, missing evidence, corrupted snapshots
and unapproved rule dependencies. A professional confirmation stores exact approved
content, target hash, actor, role, timestamp, scope and confirmation evidence.
Whitespace-only confirmations fail. This records an asserted confirmation; it is
not an authenticated electronic signature.

Revising an object appends a ChangeImpact with old/new references and the transitive
dependent versions. Effective status becomes `needs_review` only for affected
records. Prior records, documents and decisions are never overwritten. Explicitly
revise each dependent after review; the helper does not regenerate prose or approve
new versions. Unrelated work may proceed.

The selected actor's reports include every accessible revision and recorded impact.
Combined-company objects remain hidden if any company is inaccessible. Reading the
database directly is outside this logical access boundary. SQLite transactions
serialize writes; callers must use current `expected_version` values.

## P1 handoff

Before enabling either ordinary domestic OIC incorporation or direct wholly owned
incorporation, validate dated primary sources and professional assumptions; add
exact calculation and calendar contracts, Studio Archive multi-company integration,
source-supported examples, and branch-specific positive/negative acceptance cases.
The 36 contributor scenarios remain requirements, not executed workflow tests.
