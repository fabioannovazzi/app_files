# External-boundary manifest contracts

Each file in `privacy/workstreams/` records one component from
`components.json`. It is a developer-maintained design record, not runtime
inspection of customer files and not a legal compliance determination.

Each file in `privacy/services/` records one shared Vera service from
`components.json`. Shared services are registered once rather than repeated in
every workstream that can reach them.

## Required fields

- `schema_version`: currently `2`.
- `workstream`, `display_name`, and `role`: registered component identity.
- `governed_paths`: component-relative files whose bytes form the freshness
  fingerprint.
- `governed_shared_paths`: optional Vera-package-relative shared implementation
  paths whose bytes also form the workstream fingerprint. Repository reviews
  resolve these paths from `plugins/_shared`; installed-package reviews must
  resolve them from the packaged Vera tree.
- `codex_context.policy`: always `real_case_data_may_enter_codex_context`.
- `codex_context.classes`: distinct classes Codex can read, each with an `id`,
  `purpose`, and factual description of `content`.
- `codex_account_boundary`: states that the firm or user selects the account and
  that Vera cannot inspect or enforce its plan, model-training data controls, or
  retention/deletion controls. Those settings are checked before professional
  use and when the account or terms change; no per-case record is required.
- `ordinary_processing`: limits the statement to ordinary Codex model
  processing under the firm's or user's existing ChatGPT/Codex account. Vera is
  not a separate recipient, does not automatically anonymize professional
  material, and filters or aggregates locally only when that helps the work.
- `boundaries_beyond_codex`: public research, hosted service, external
  connector, and send/publish boundaries. The array may be empty.
- `security_controls`: concrete controls enforced by the workstream. The array
  may be empty; local processing, absence of an API call, draft status, and a
  policy statement are not security controls by themselves.
- `review`: review date, basis, reviewer, and deterministic source fingerprint.

## Shared-service fields

Shared-service manifests record `service_id`, `display_name`,
`governed_paths`, every `boundary_beyond_codex`, concrete
`security_controls`, and the freshness `review`. Each boundary also records its
retention posture and one activation mode:

- `automatic_session_start`;
- `automatic_after_prior_submission`;
- `explicit_user_choice`.

An explicit route must be optional and confirmed. An automatic route cannot
ask for confirmation on every run. A shared-service security control names the
governed runtime path that implements it and what blocks or fails when the
control is violated; prose-only intentions belong in boundary workflow
conditions, not in `security_controls`.

## Drafting rules

Describe what the source actually does. Do not equate local preprocessing with
anonymisation, and do not claim that Codex sees only a deterministically defined
minimum. Real names and case facts may enter Codex context when the professional
work requires them.

An external boundary needs confirmation only when the route itself is optional
and has not already been chosen by the user. Ordinary Codex work has no routine
privacy notice or consent step.

GDPR data minimisation remains applicable as a purpose-based professional and
legal judgment. The manifest and validator neither decide that judgment nor
certify GDPR compliance.
