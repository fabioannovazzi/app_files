# Case-direction return contract

Use this contract whenever a bounded research, data, interview, reporting,
partner-challenge, or validation branch returns to the case director. It is the
common hand-off into the spine, not a schema for how the branch performs its
analysis.

## Authorship boundary

The active model authors:

- the question the branch answered;
- the branch answer and its limitations;
- the evidence observations and claim relationships;
- the claims that now carry the answer;
- whether the current case answer strengthens, weakens, changes, splits, or
  remains unchanged; and
- which questions were answered, dismissed, retained, or newly opened.

`record_case_direction_return.py` checks the stable mechanics only: JSON shape,
exact artifact bytes, known IDs, active result claims, complete declared claim
and evidence closure, atomic updates, immutable return IDs, and replay safety.
It does not decide what the branch means or whether a claim is true, material,
well supported, or decision-relevant.

## Common return

Author one JSON object against
`contracts/advisory_case_direction_return.v1.schema.json`:

```json
{
  "schema_version": "1.0",
  "return_id": "return-market-research-001",
  "return_type": "analysis_branch",
  "branch": {
    "workflow": "clara:advisory-case-director",
    "question_id": "q-0001",
    "question": "What makes the observed profit pool plausible?",
    "answer": "The model-authored bounded answer to that question."
  },
  "answer_effect": "strengthens",
  "result_claim_ids": ["cl-market-001"],
  "source_artifacts": [],
  "limitations": ["What remains unproven about the target."],
  "evidence_receipts": [],
  "claims": [],
  "judgement_entries": [],
  "question_updates": [
    {
      "question_id": "q-0001",
      "status": "answered",
      "explanation": "Why the returned evidence answers this bounded question."
    }
  ],
  "new_questions": [],
  "validation_binding": null
}
```

`result_claim_ids` may reference claims created in this return or claims already
recorded by a specialist adapter. This permits a Reporting Engine or transcript
workflow to preserve its own authoritative mechanics and still return through
the same case-direction interface without duplicating claims.

Every new claim and evidence receipt in the envelope must belong to the
dependency/evidence closure of the active result claims. Register source
materials before using their material IDs in evidence receipts. If the return
is bound to an existing `question_id`, copy its question text exactly and
declare the question's resulting status. A new question may cite existing
judgement IDs through `source_entry_ids` and judgements created in the same
return by their zero-based `source_judgement_indexes`; this preserves partner
or model origin without requiring the model to predict generated IDs.

Record the return before revising the workpaper:

```bash
python scripts/record_case_direction_return.py \
  <case-dir> <model-authored-case-direction-return.json>
```

The helper writes an immutable receipt under `case_direction_returns/`. A retry
with identical declared content returns the existing receipt; reuse of the same
`return_id` for different content fails.

## Validator return

For `return_type: "validation_feedback"`, use the same envelope and provide a
non-null `validation_binding` with exact receipts for
`advisory_validation_review.json` and `validation_audit.json`, plus the material
finding IDs used by the case director. The helper verifies the files, their
mutual deliverable and reviewed-claim bindings, and the pre-feedback evidence
and claim-register hashes. A stale validation cannot be applied to a changed
spine.

The model decides the semantic response:

- no semantic change: return the still-active reviewed claim IDs;
- changed evidence or wording: add a successor claim and return its claim ID;
- a completed recheck: add the new evidence receipt and ensure the active
  result-claim closure includes the full evidence history;
- unresolved support or reasoning: keep the affected question open or add the
  smallest decision-relevant next question; and
- professional judgement required: record that boundary without inferring an
  approval.

After feedback changes the case answer, update and checkpoint the workpaper,
rebuild the affected deliverable, bind its claim appearances, and rerun the
validator. A validator report is a bounded contribution to the spine, not a
second case controller.
