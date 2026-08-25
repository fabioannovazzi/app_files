# Browser capability contract

A capability is a portable, process-specific instruction package interpreted by
the generic `browser-automation` skill. It is not a stored browser session and
it is not a standalone bot.

## Capability factory

The primary developer tool is a generic discovery session that runs on the
authorized operator's computer. The operator describes the target function and
uses one of three modes:

- `guided`: demonstrate the main path while the model observes bounded
  before/after control states;
- `autonomous`: let the model explore safe reversible paths;
- `hybrid`: demonstrate the main path and let the model inspect gaps and safe
  branches.

The factory produces two different handoffs. First, a reviewed sanitized
developer pack lets a remote developer understand a system they cannot access.
Second, after separate authoring approval and replay, it produces the portable
process-specific capability that the receiving operator can run. Gmail is a
proof surface; Agenzia, TeamSystem, and another browser-based gestionale use the
same engine with different site/process contracts.

## Runtime split

- The model owns page interpretation, milestone planning, branch recognition,
  locator selection, and recovery when the observed UI differs.
- `scripts/capability_runtime.mjs`, running beside the connected Chrome tab,
  dispatches the executable JSON through `tab.playwright`. It owns bounded
  navigation, typed input substitution, locator fallback, waits, extraction,
  assertions, branches, downloads, and machine receipts.
- Computer Use is allowed only for a real operating-system or non-browser gap.
  It is not a fallback browser controller.
- `scripts/capability_pipeline.py` owns schema validation, reviewed-discovery
  provenance, origin bounds, secret-exclusion fields, validation-receipt checks,
  hashes, permissions, and non-overwriting bundle output.
- `scripts/discovery_runtime.mjs` performs read-only bounded polling during an
  operator demonstration. It records query-free paths and semantic control
  metadata without form values, business rows, HTML, screenshots, or a claimed
  raw click stream.
- `scripts/discovery_pack.py` validates and seals the separately reviewed
  `browser-discovery-evidence/v1`, `browser-discovery/v2`, and non-executable
  draft into a hash-linked developer pack. Transfer approval is not capability-
  authoring approval.

## Capability states

- `scaffold`: the target and process are named, but no authenticated live
  discovery has established controls or transitions.
- `draft`: a private discovery record informed the capability, but the exact
  record has not yet been reviewed and approved by the operator. A draft is not
  executable.
- `discovered`: an authorized live discovery produced an operator-reviewed
  private discovery record and an executable plan, but clean replay is not yet
  proven.
- `validated_local`: the exact capability completed two clean runs from its
  declared start state in the same origin UI, without locator edits during
  either run. This is environment-specific evidence, not a portability
  guarantee.

After any repair, reset to the declared start state and repeat the validation
runs. Never count the repair run as a clean replay.

A missing locator for a read-only or reversible action may be recovered during
one run through a model-provided `recoveryHandler`. The model proposes exactly
one semantic locator. When the failure is inside a repeated structured
extraction field, it may instead propose one bounded CSS locator scoped to the
already resolved record container. The mechanical runtime preserves the action
ID, intent, operation, effect, input/output contract, field name, read method,
postcondition, maximum record count, and allowed origin. It never changes a
consequential action, workflow branch, origin, data class, or output scope and
never mutates the capability in place.

Promotion compares the draft with the exact reviewed record. Site, process,
runtime, authority, and privacy boundaries must match, and every executable
milestone must have a discovery observation. Review of a narrower proof does not
authorize a broader capability.

## Portable content

The portable bundle contains only `capability.json`, a hash lock, a short
README, and the sanitized machine receipts required by a `validated_local`
claim. The lock hashes every included file except itself and verification rejects
unlisted files and unsafe paths. A bundle may contain semantic UI names and
query-free paths necessary to run the process. It must not contain credentials,
cookies, browser storage, session URLs, HTML, screenshots, network bodies,
downloaded file bytes, runtime `outputs.json`, observed private values, account
identifiers, or the private discovery record.

Inputs are typed references such as `query`, `date-from`, or `client-code`,
never values copied from the discovery account. Private input values remain in
the live browser task. Receipts contain input hashes, not values.

## Locator order

Prefer role and accessible name, then label, placeholder, stable test ID, or
bounded visible text for interactive controls. CSS may appear as a fallback.
Repeated structured extraction fields may use bounded CSS when accessibility
semantics do not identify fields inside a row; those locators remain subject to
clean replay evidence. A transition may use CSS without a semantic fallback only
for a structural `locator_visible` state marker explicitly scoped with
Playwright's `:visible` filter. This prevents retained hidden SPA content from
counting as the current state while avoiding a broad semantic fallback that
matches unrelated containers. Interactive actions still require a semantic
locator candidate. Never rely on coordinates in a portable capability.

Each milestone contains ordered executable actions and ordered transitions.
Each action declares its operation, intent, effect, locator candidates, typed
input or output reference, timeout, and postcondition. Record extraction uses
`single` or `list` mode with an exact declared field shape, typed coercion, a
hard maximum, an optional positive-integer runtime limit, required fields, and
deduplication keys. Scalar and summary extraction uses `text` mode. Required
non-collection outputs must be produced on every terminal path; an empty
`record_set` remains a valid no-result output. `consequential` actions require
action-time confirmation. A capability never treats a successful click as
completion; it verifies the declared visible state, URL path, structured output,
or download event. The executor independently rejects unknown action effects,
incorrect confirmation modes, and approvals that do not name a declared
consequential action even when a caller skipped the separate Python validator.
Download completion additionally requires the connected Chrome event object to
expose `path()` so the runtime can hash actual local bytes. A missing method is
a sanitized `native_gap`, not successful download evidence.

## Run evidence

Every run uses a fresh owner-only directory outside the Git workspace. The
runtime writes:

- `outputs.json`: structured output values. `artifact_only` values are not
  returned to the model unless the operator separately requests interpretation.
  Values declared `model_and_artifact` or `model_summary` are returned as part
  of the runtime result and therefore enter the selected model context.
  Download sets are always `artifact_only`; each local download entry records
  its path, byte length, and SHA-256 without placing file bytes in the receipt.
- `run.receipt.json`: capability and discovery hashes, hashed inputs, milestones,
  sanitized action outcomes, output counts and hashes, terminal state, and
  environment. Raw errors and private values are excluded; model-visible
  failures contain only a stable category and a SHA-256 of the local detail.
- `run.lock.json`: hashes linking the receipt and output artifact.
- `recovery.proposals.json`, only when bounded model recovery was attempted:
  the proposed semantic locator, semantic rationale, uncertainty, original
  contract hashes, sanitized error hashes, and outcome. The file is owner-only,
  non-portable, and unapproved for persistence. A version-2 run lock hashes it.

Recovery is a two-pass host-model interaction. A first run with a missing safe
locator fails with a model-visible `recovery_request` containing the unchanged
action contract, exact action-or-field recovery target, current origin and
query-free path, and failure hash, but no runtime input. The host model then
inspects the bounded live state and retries from the declared start with one
semantic candidate, or one row-scoped CSS candidate for a structured extraction
field. The JavaScript runtime does not call an API or claim to invoke an LLM
inside the original execution.

Only the runtime writes receipts. `finalize` requires two unique passed receipts
whose execution hash, discovery hash, capability version, terminal, outputs,
and environment match, with `locator_changes_during_run: false`. A recovered
run may complete useful work but cannot count toward validation. Capability
status and validation metadata are excluded
from the execution hash so promotion from `discovered` to `validated_local`
does not invalidate the proven executable contract.

The finalizer also requires each canonical receipt beside its canonical
`outputs.json` and `run.lock.json`, verifies all cross-hashes, declared input
hashes, output types and shapes, allowed origins, locator evidence, and the
recorded milestone and action sequence. This proves artifact consistency; it is
not a cryptographic attestation of a physical user, machine, or website.
Preserve that limit in any validation claim.

## Handoff

Run `verify-bundle` and send the sealed capability folder, not the discovery or
run-output directory. The receiving
operator installs or opens Vera, supplies the capability path, connects their
own Chrome extension, authenticates personally, and runs a local validation.
Authentication state, secrets, cookies, and downloaded business data are never
transferred with the bundle.
