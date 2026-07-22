# External-boundary manifest contract

Each file in `privacy/workstreams/` records one component from
`components.json`. It is a developer-maintained design record, not runtime
inspection of customer files and not a legal compliance determination.

## Required fields

- `schema_version`: currently `2`.
- `workstream`, `display_name`, and `role`: registered component identity.
- `governed_paths`: component-relative files whose bytes form the freshness
  fingerprint.
- `codex_context.policy`: always `real_case_data_may_enter_codex_context`.
- `codex_context.classes`: distinct classes Codex can read, each with an `id`,
  `purpose`, and factual description of `content`.
- `codex_account_boundary`: states that the firm or user selects the account and
  that Vera cannot inspect or enforce its plan, model-training data controls, or
  retention/deletion controls. Those settings are checked before professional
  use and when the account or terms change; no per-case record is required.
- `boundaries_beyond_codex`: public research, hosted service, external
  connector, and send/publish boundaries. The array may be empty.
- `security_controls`: concrete controls enforced by the workstream.
- `review`: review date, basis, reviewer, and deterministic source fingerprint.

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
