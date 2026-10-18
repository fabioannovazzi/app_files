# Runtime and external-boundary manifest contracts

Each file in `privacy/workstreams/` records one registered workstream from
`privacy/registry.json`. It is a developer-maintained design record, not runtime
inspection of customer files and not a legal compliance determination.

Each file in `privacy/services/` records one shared product service from
`privacy/registry.json`. Shared services are registered once rather than repeated in
every workstream that can reach them.

## Runtime profiles

`privacy/runtime-profiles.json` records model-processing and account boundaries
once for each supported runtime:

- `openai-codex` covers Codex model processing by OpenAI.
- `anthropic-cowork` covers Cowork model processing by Anthropic.
- `openai-chatgpt` covers ChatGPT model processing by OpenAI.
- `google-antigravity` covers the model provider selected in Antigravity; the
  package does not identify that selected provider or enforce account settings.

All profiles state that the firm or user selects the account or workspace,
the product cannot inspect or enforce account plan, model-training data controls, or
retention/deletion controls, and the account is reviewed before professional
use and when the account or terms change. No profile promises automatic
anonymization or local-only processing. The product is not a separate model-processing
recipient.

Do not create provider-specific copies of a workstream manifest. Each
workstream references its reviewed runtime profiles. A runtime-specific external route records
only the applicable profile IDs on that boundary.

## Required workstream fields

- `schema_version`: currently `3`.
- `workstream`, `display_name`, and `role`: registered workstream identity.
- `governed_paths`: files relative to the registered product or component source whose bytes form the freshness
  fingerprint.
- `governed_shared_paths`: optional product-package-relative shared implementation
  paths whose bytes also form the workstream fingerprint. Repository reviews
  resolve these paths from `plugins/_shared`; installed-package reviews must
  resolve them from the packaged product tree.
- `runtime_profiles`: the reviewed profile IDs from the shared catalog.
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
  outside the product plugin tree. Use this for a hosted shared service whose
  executable API, persistence, or deployment wiring lives elsewhere in the
  same repository. Paths must remain inside the repository and are fingerprinted
  with a `repository:` logical prefix. Security controls implemented there use
  the same prefix in `implemented_by`.

- `automatic_session_start`;
- `automatic_on_first_use`;
- `automatic_after_prior_submission`;
- `automatic_after_prior_connection`;
- `automatic_per_durable_run`;
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

## Installed repository-source declarations

A product package may retain a shared service's complete repository review without
shipping the hosted application or the entire published course library. Source
validation must still inspect actual repository bytes before packaging and
reject a stale review; it must never use the declaration as a source fallback.

The installed service keeps `governed_repository_paths`, every original
security control and external boundary. An explicit `repository_source_review`
binds the exact service, `privacy/repository-source-reviews/<service>.json`, and
the scope `reviewed_repository_declaration_not_hosted_runtime`. Its review uses
`fingerprint_scope: installed_client_and_repository_review_declaration`.

The retained JSON has schema version 1, service identity and scope,
`hosted_runtime_verified: false`, the unchanged original source manifest and
review fingerprint, and complete file identities for every declared repository
root: repository-relative path, byte count, SHA-256 and every matching installed
copy. It includes three mandatory limitations: these hashes record inspected
repository bytes; installed validation checks local clients and the retained
declaration; hosted deployment, live controls and model delivery require
separate acceptance evidence. No hosted source code is executed from this
record, and the record contains no client-case material.

The installed fingerprint binds this exact declaration and the actual local
client implementations. Installed copies also match their retained source
size and SHA-256. The validator rejects foreign services, escaped or symlink
paths, missing source roots, duplicate or malformed identities, oversized
records, changed local copies, stale fingerprints, and any declaration claiming
hosted verification. It does not independently reconstruct absent source bytes
from hashes or authenticate the unsigned review record. A package-local pass
is not hosted acceptance or proof that a provider received model context.


## Shared product register

`privacy/registry.json` is the authoritative ownership inventory for all exposed
skills, embedded components, registered workflow IDs and public function pages.
A workstream can use product-root code or a registered shared component. Multiple
professional entry points may reuse a component, but component ownership and
each exposed skill's ownership are explicit. Studio Archive is infrastructure.

All products use these same schemas and validator. `runtime-profiles.json`
contains Codex, Cowork, ChatGPT and Antigravity account/model boundaries. A
manifest lists only reviewed routes; the packaged projection retains the exact
reviewed source contract and binds its actual installed bytes separately.
Unknown host behavior remains unknown. Availability is not inferred from an OS.

Every workstream has `service_ids` referencing registered common service records
and `public_explanations` keyed by its registered public page IDs. Each explanation
contains its reviewed status and complete paragraph arrays in every language
supported by that page. A placeholder is explicit incomplete review, never
`not-relevant`. The public catalog is generated from these exact fields.

`privacy/contracts/` retains canonical source documents and their SHA-256 index.
`source_contract_sha256` appears only after package projection. Do not change that
binding to conceal stale source. Regenerate contracts only after validation and
semantic review. Neither source hashing nor contract generation makes a semantic
approval decision or verifies a remote hosted deployment.

Host packaging keeps the complete source contract and marks installed records
with `packaged_for_runtime`. A different requested host cannot claim that installed
review. `registry.json` records the exact reviewed workstream, service and file
omissions for each host. New or removed omissions fail packaging and require an
inspected source review; the builder must never silently approve missing code.
