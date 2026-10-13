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
  "schema_version": "2.0",
  "method": "shared_agentic_legal_tax_research",
  "answer_revision_sha256": "SHA256 of the actual delivered answer bytes",
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
      "treatment_type": "source_assessment",
      "evidence": [{"kind": "source_capture", "artifact": "research/sources/text-<actual-sha>.txt", "sha256": "actual text SHA256", "inventory": "research/source_inventory-<actual-sha>.json", "inventory_sha256": "actual inventory SHA256", "source_id": "source-001", "capture_id": "actual examined capture ID", "start_char": 0, "end_char": 42}],
      "effects": [{"kind": "claim", "artifact": "claims_review.json", "sha256": "actual final review SHA256", "claim_index": 1}],
      "dependencies": [],
      "dependency_review": "Actual assessment of effects on dependent issues and claims",
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

Schema 2.0 requires nonempty structured evidence and effects for every treated
issue. References pin an existing file revision and an actual JSON pointer,
claim index or character span. Treatment types are model-declared work:
`source_assessment`, `fact_confirmation`, `scope_revision`, `calculation`,
`claim_removal`, `qualification` or `professional_judgment`. Use source/access
records for a source assessment, facts for fact confirmation, scope/contract
for scope revision, calculations for arithmetic and claim/note references for
professional judgment. A qualification can reference claims, sources or facts.
A removed claim remains in the final review with its removal disposition.
Effects reference the current reviewed claim, answer, contract or scope.
Dependencies are actual other issue IDs; assess changed dependent conclusions
before closure. Empty evidence, free-form invented locators and mere proposals
cannot close an issue. No reference schema determines whether an action is
substantively adequate.

To pin hashes without guessing them, save a model-selected reference object
without its hash fields and run:

```bash
python scripts/evidence_refs.py --output-dir <client-run-output> --selection <selected-reference.json>
```

This read-only helper emits a fully resolved reference. It does not select
sources, infer support, or repair a mismatched retained capture. Keep the actual
answer revision SHA256 in the record; changing the answer requires reassessment.
Binding automatically includes referenced files and the final review inventories,
reruns the final review integrity checks, rejects untreated review defects, and
requires evidence limits or professional judgment to remain visible in closure.
Preserve `source_capture_manifest.json`, immutable inventory snapshots and all
original/text captures when registering the complete run in Studio Archive.
The newest `source_inventory.json` is a pointer, not a substitute for history.
