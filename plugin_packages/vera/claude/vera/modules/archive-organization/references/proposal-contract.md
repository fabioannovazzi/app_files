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
  "schema_version": "vera.archive_organization_model_proposals.v1",
  "inventory_ref": "archive_inventory_...",
  "proposals": []
}
```

Each `proposals` row must contain exactly:

- `item_ref`: exact opaque item reference from the projected inventory;
- `category_id`: a policy category ID or `null`;
- `document_type`, `entity`, `reference`, `practice`: supported text or `null`;
- `document_date`: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or `null`;
- `confidence`: `low`, `medium`, or `high`;
- `reason`: concise evidence-backed explanation;
- `probable_duplicate_of`: another projected `item_ref` or `null`;
- `anomalies`: a bounded list of concise observations.

Cover every projected inventory item exactly once. Local code resolves item
references back to immutable snapshot rows and verifies the inventory binding;
the model does not need raw hashes, Google Drive IDs, capabilities, versions,
or absolute execution paths. Document meaning, relevance, practice,
and probable duplication are model judgments. Do not use deterministic keyword
rules as a substitute. A filename can support a hypothesis but cannot by
itself authorize a category or move.
