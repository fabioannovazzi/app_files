> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Persistent issues, cycles and reviewed-artifact binding

Keep `research_record.md` readable for the professional. Record the accepted
preparation, issue/source/claim map, actual queries, authorities opened or
rejected, versions, passages, access/coverage limits, provisional conclusions,
contrary evidence, changed premises and stopping judgment. Do not expose private
case identifiers in public queries without necessity and authorization.

Keep `research_review.json` alongside it in the running validation output.
This is a model-written work record, not a legal classifier. Start it with
`completion.status: in_progress` and issues marked `open`. Update after every
cycle, including final-review feedback; preserve previous entries on resumption.
Stable issue IDs connect critiques, actions and changed/dependent conclusions.
Add a cycle when a final review reopens research; do not overwrite the earlier
finding or treat a credible alternative as a defect merely because it differs.

The following is an illustrative record shape, not findings to copy:

```json
{
  "schema_version": "1.0",
  "method": "shared_agentic_legal_tax_research",
  "cycles": [
    {
      "id": "cycle-1",
      "purpose": "Establish whether the cited provision applies at the case date.",
      "issue_ids": ["issue-1"],
      "findings": "Actual research findings and source locators.",
      "validation": "Source support, applicability and reasoning assessment.",
      "challenge": "Strongest plausible contrary evidence examined and result."
    }
  ],
  "issues": [
    {
      "id": "issue-1",
      "question": "Which version governs the event?",
      "status": "resolved",
      "cycle_ids": ["cycle-1"],
      "treatment": "Actual follow-up, changed conclusion and affected claims.",
      "evidence": ["Source locator and passage actually examined"],
      "limits": []
    }
  ],
  "completion": {
    "status": "complete",
    "coverage_review": "Assessment against the original question and material phases.",
    "stopping_rationale": "Why further available investigation is unlikely to change the answer.",
    "limits": []
  }
}
```

Issue statuses are `open`, `resolved`, `qualified`, `evidence_limited` and
`professional_review`. Every treated issue records actual action and evidence
locators; the last three retain explicit limits and their effect on conclusions.
An inaccessible decisive source is an evidence limit, not proof of absence.
An actionable defect remains open until treated. A proposed fix is not treatment.

Completion statuses are `in_progress`, `interrupted`, `complete` and
`evidence_limited`. A tool/time interruption preserves unfinished issues and
never becomes complete solely to pass packaging. A record with an
evidence-limited issue cannot declare complete research. Professional judgment
remains visible even when the available investigation is complete. No number of
cycles, references or filled fields proves research quality.

After the final substantive review, run these helpers from the resolved shared
component root. Artifact arguments are relative to the running review output:

```bash
python scripts/research_record.py bind --output-dir <client-run-output> --client-engagement <client_engagement_path> --answer validated_document.md --answer-contract answer_contract.json --review claims_review.json --source-file research/sources/<actual-capture>
python scripts/research_record.py verify --output-dir <client-run-output> --client-engagement <client_engagement_path>
```

For a required opposing examination, bind `position/validated_document.md`,
`position/answer_contract.json` and `position/claims_review.json` instead after
both final reviews and the comparison. Repeat `--source-file` for every actual
retained capture, including new adverse evidence; omit it only when no source
capture exists and disclose that limit. The readable research log remains
`research_record.md` at the run root. The existing adversarial helper separately
verifies the opposing opinion and comparison. Declare all files at Archive
closure, including this record and faithful source captures.

Binding adds exact hashes of the research record and selected artifacts.
Verification is read-only and rejects edited records, changed answers,
contracts, source captures or reviews; open issues, interrupted investigation,
missing explanations and dangling issue/cycle references also prevent closure.
These checks are deterministic because they verify file identity and declared
record consistency. They never assess semantic support, legal correctness,
materiality, research completeness or the truth of a declared treatment.

A changed artifact requires renewed substantive review before rebinding.
Never refresh hashes alone to make a stale review pass. Without local tooling,
keep the issue/cycle history and reviews in chat and disclose missing durable
records and hash verification; do not report that a helper ran.
