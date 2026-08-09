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
