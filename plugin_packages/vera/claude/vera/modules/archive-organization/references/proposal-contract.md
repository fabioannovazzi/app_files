> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Semantic proposal contract

Write one UTF-8 JSON object with this exact top-level shape:

```json
{
  "schema_version": "vera.archive_organization_proposals.v1",
  "client_id": "client_...",
  "snapshot_sha256": "64 lowercase hex characters",
  "proposals": []
}
```

Each `proposals` row must contain exactly:

- `relative_path`: exact client-relative path from the snapshot;
- `category_id`: a policy category ID or `null`;
- `document_type`, `entity`, `reference`, `practice`: supported text or `null`;
- `document_date`: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or `null`;
- `confidence`: `low`, `medium`, or `high`;
- `reason`: concise evidence-backed explanation;
- `probable_duplicate_of`: another snapshot relative path or `null`;
- `anomalies`: a bounded list of concise observations.

Cover every snapshot file exactly once. Document meaning, relevance, practice,
and probable duplication are model judgments. Do not use deterministic keyword
rules as a substitute. A filename can support a hypothesis but cannot by
itself authorize a category or move.
