> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Record contract v1

The model authors JSON; the user does not fill technical fields. All narrative
strings are in the user's language. The helper verifies references and integrity,
not evidence meaning, professional judgment or completeness of the legal analysis.

Required top-level fields:
- `schema_version`: 1; `jurisdiction`: "IT"; `as_of`: ISO date.
- `scope`, `company_context`, `proportionality_basis`, `assessment`, `limitations`:
  nonempty narratives. Record excluded and unassessed areas in scope/limitations.
- `sources`: nonempty array of `{id, path, title, sha256}`. Paths are relative to
  the exact run inputs directory; hashes bind imported source bytes.
- `legal_basis`: nonempty array of `{title, url, locator, checked_at, applicability}`.
  `checked_at` is the actual ISO retrieval date; a value is not proof of verification.
- `observations`: nonempty array of `{id, area, description, proportionality,
  assessment, evidence_state, citations}`. `evidence_state` is `documented`,
  `reported`, `operating_evidence` or `unknown`. For an unknown, cite the supplied
  inventory, statement or evidence that establishes the review's limitation.
  Several observations can describe the same arrangement. Do not force them into
  a single favorable or unfavorable state.
- `findings`: array of `{id, observation_ids, observation, interpretation,
  alternatives, follow_up, citations}`. Include the company's concrete consequence
  in interpretation. Empty findings are valid and never constitute certification.
- `assessment_citations`: nonempty citation array.
- `actions`: array of `{id, finding_ids, proposal, owner, timing, priority_reason,
  completion_evidence_needed, status}`. Owner/timing are proposals or explicitly
  unresolved text. Status: `proposed`, `in_progress`, `completed` or `deferred`.
  Completed actions also require `completion_citations` and `completion_assessment`.
  Citations are `{source_id, locator}` objects with exact source IDs.

Optional prior review:
- `previous`: `{source_id, record_sha256}` referencing an imported finalized
  record from this client and engagement.
- `changes_since_previous`: explanation, required when previous is present.
- `prior_action_review`: mapping containing every previous action ID and a
  structured disposition: `{status, assessment, citations, current_action_ids}`.
  Status is `open`, `completed`, `deferred`, `superseded` or `not_assessed`.
  Assessment is a reasoned narrative. Completed requires nonempty current source
  citations; prior completion is not assumed current. Other statuses may use an
  empty citation list when evidence is unavailable. Superseded requires nonempty
  current_action_ids identifying the replacement actions. Otherwise this list
  may be empty. A carried-forward action may keep its ID; explain any replacement.

Optional `professional_decision`: `{proposal_sha256, reviewer_ref, reviewed_at,
conclusion, finding_dispositions, next_review_date, review_date_reason}`. The exact
proposal digest comes from the draft record, excluding professional_decision.
Finding dispositions must address every finding and any associated action changes.
`next_review_date` may be null; recording a date does not schedule monitoring.
Never populate a decision from model inference or a request merely to prepare work.

Run the helper again with explicit professional decisions to append a new record.
The JSON and readable memo have content-addressed filenames; retries are idempotent
and cannot overwrite different output. The archive supplies client/run identity.
Keep legal source validation and per-phase model-data reports as normal companion
artifacts. Validation of this JSON alone does not establish delivery readiness.
