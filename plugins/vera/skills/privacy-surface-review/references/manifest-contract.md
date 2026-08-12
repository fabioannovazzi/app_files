# Runtime and external-boundary manifest contracts

Each file in `privacy/workstreams/` records one component from
`components.json`. It is a developer-maintained design record, not runtime
inspection of customer files and not a legal compliance determination.

Each file in `privacy/services/` records one shared Vera service from
`components.json`. Shared services are registered once rather than repeated in
every workstream that can reach them.

## Runtime profiles

`privacy/runtime-profiles.json` records model-processing and account boundaries
once for each supported runtime:

- `openai-codex` covers Codex model processing by OpenAI.
- `anthropic-cowork` covers Cowork model processing by Anthropic.

Both profiles state that the firm or user selects the account or workspace,
Vera cannot inspect or enforce account plan, model-training data controls, or
retention/deletion controls, and the account is reviewed before professional
use and when the account or terms change. Neither profile promises automatic
anonymization or local-only processing. Vera is not a separate model-processing
recipient.

Do not create provider-specific copies of a workstream manifest. Each
workstream references both profiles. A runtime-specific external route records
only the applicable profile IDs on that boundary.

## Required workstream fields

- `schema_version`: currently `3`.
- `workstream`, `display_name`, and `role`: registered component identity.
- `governed_paths`: component-relative files whose bytes form the freshness
  fingerprint.
- `governed_shared_paths`: optional Vera-package-relative shared implementation
  paths whose bytes also form the workstream fingerprint. Repository reviews
  resolve these paths from `plugins/_shared`; installed-package reviews must
  resolve them from the packaged Vera tree.
- `runtime_profiles`: exactly `openai-codex` and `anthropic-cowork`.
- `model_context.policy`: always
  `real_case_data_may_enter_selected_runtime_model_context`.
- `model_context.classes`: distinct classes a supported runtime can read, each
  with an `id`, `purpose`, factual description of `content`, and applicable
  `runtime_profiles`.
- `external_boundaries`: public research, hosted service, external connector,
  and send/publish boundaries. The array may be empty. Each boundary names one
  or more applicable `runtime_profiles`.
- `security_controls`: concrete controls enforced by the workstream. The array
  may be empty; local processing, absence of an API call, draft status, and a
  policy statement are not security controls by themselves.
- `governed_repository_paths`: optional repository-root-relative runtime files
  outside the plugin tree that implement the workstream. These files are
  included in the source fingerprint.
- `review`: review date, basis, reviewer, and deterministic source fingerprint.

## Shared-service fields

Shared-service manifests use schema version `2` and record `service_id`,
`display_name`, `governed_paths`, applicable `runtime_profiles`, every
`external_boundary`, concrete
`security_controls`, and the freshness `review`. Each boundary also records its
applicable runtime profiles, retention posture, and one activation mode:

- `governed_repository_paths`: optional repository-root-relative runtime files
  outside the Vera plugin tree. Use this for a hosted shared service whose
  executable API, persistence, or deployment wiring lives elsewhere in the
  same repository. Paths must remain inside the repository and are fingerprinted
  with a `repository:` logical prefix. Security controls implemented there use
  the same prefix in `implemented_by`.

- `automatic_session_start`;
- `automatic_after_prior_submission`;
- `automatic_after_prior_connection`;
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
and has not already been chosen by the user. Ordinary model processing in
Codex or Cowork has no routine privacy notice or consent step.

GDPR data minimisation remains applicable as a purpose-based professional and
legal judgment. The manifest and validator neither decide that judgment nor
certify GDPR compliance.
