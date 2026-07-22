# Clara privacy-surface manifest contract

The records in `privacy/workflows/` and `privacy/hosted-services/` are
developer-maintained design records. They do not inspect customer files at
runtime and do not determine legal compliance.

## Workflow records

Every user-facing Clara skill has one workflow record. It states:

- the source paths whose bytes make the review stale when they change;
- the classes of real professional information Codex may read;
- the common ordinary-model rule: the user-selected ChatGPT/Codex account is the
  arrangement, Clara adds no separate recipient, and there is no automatic
  anonymisation;
- the ChatGPT/Codex account boundary selected by the firm or user;
- every boundary beyond Codex and any referenced hosted-service record;
- concrete controls enforced by the workflow, or an empty array when there is
  no source-enforced security control to record; and
- the review date, basis, reviewer, and source fingerprint.

## Hosted-service records

Each explicit Mparanza service has one record. It states:

- which workflows use it and which source paths define its client behavior;
- destinations, trigger, and whether it runs automatically;
- data sent and returned;
- source-backed access arrangements and controls; and
- the source-backed retention position. Use
  `not_established_by_plugin_source` when the governed client, service, and legal
  sources do not prove retention or deletion. Do not turn an expiring URL or
  local download into a deletion claim.

## Drafting rules

Real client and case data may enter Codex context. Do not equate local storage,
local preprocessing, filtering, or aggregation with automatic anonymisation.
Do not claim a deterministic minimum. Do not create a per-case record for
ordinary model use.

An external boundary needs separate confirmation only when the route is optional
and the user has not already selected it. The user's explicit route choice is
the confirmation.

The register records engineering facts. It does not certify GDPR compliance.
Local storage, review gates, source preservation, policy language, and
procedural consent or sanitisation instructions are not security controls.
