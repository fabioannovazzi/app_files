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

## Intelligent assessment extension

For new runs include `intelligent_review` with `version: 1`. Historical v1 reviews
without it remain readable for follow-up; omission is not evidence of a complete
new assessment. All fields below are model-authored. Code checks shape and links,
not whether scope, questions or conclusions are good.

- `coverage`: nonempty array `{id, area, status, reason, observation_ids}`.
  Status: `assessed`, `excluded`, `unresolved`. Assessed areas need observation
  links; the other two may have `[]` with an explicit reason/limitation.
- `processes`: array `{id, process, risk, responsibility, control,
  information_flow, operation, gap, observation_ids}`. All narrative fields are
  nonempty, including explicit unknowns. Use existing observations for evidence
  and counterevidence, including dated attributed statements.
- `questions`: array `{id, question, why_it_matters, evidence_needed, status,
  observation_ids}`. Status is narrative: unanswered, response and attribution,
  or why no longer needed. Preserve contradictions after an answer.
- `chronology`: array `{id, event_date, known_at, recipient, event, response,
  uncertainty, observation_ids}`. Dates are narrative so unknown dates and
  intervals can be retained honestly; use ISO dates when known, and distinguish
  document dates, upload dates and operating events.
- `decision_brief`: nonempty narrative of decisions to discuss, supporting
  finding/observation references, disagreements and unresolved choices.
- `action_ids`: array of linked proposed actions, possibly empty.
- `next_review`: nonempty narrative of proposed trigger, evidence to inspect and
  unresolved commitments; no monitoring is scheduled by recording it.

IDs must be unique within each section. Every process, question and chronology
row links to one or more observations. Empty arrays for these sections are allowed
when the case warrants it; explain the limitation or exclusion in coverage and
the brief. Do not generate filler rows. The memo renders the complete extension,
so the professional can read the reasoning without inspecting JSON.
