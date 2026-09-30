> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Case record contract

The helper stores case snapshots as declared artifacts in Studio Archive.
Use one engagement per professional role. It reads prior CNC snapshots across
that engagement's runs under the archive's existing lock. Expected revision
prevents lost updates; retrying the identical request/key returns its original
snapshot. A reused key with different content fails. On conflict, resume and
reconcile; never silently substitute the new revision number.

`request-001.json` has exactly these fields:

```json
{
  "expected_revision": 0,
  "idempotency_key": "cnc-intake-001",
  "role": "advisor",
  "stage": "Valutazione iniziale; il dettaglio degli incassi non è disponibile.",
  "change_reason": "Primo esame dei documenti selezionati.",
  "next_action": {
    "task": "Richiedere scadenzario, contestazioni e incassi successivi.",
    "why": "Il saldo contabile non documenta importi e tempi incassabili.",
    "capability": "open-item-reconciliation",
    "output": "Prospetto delle posizioni con riscontri e gap.",
    "decision": "Valutare recuperabilità e tempi prima del forecast."
  },
  "upsert_nodes": [
    {
      "id": "receivable_gap",
      "kind": "gap",
      "title": "Scadenzario da acquisire",
      "content": "Mancano scadenze e contestazioni; gli incassi restano da verificare. Possiamo intanto ricostruire le esposizioni bancarie.",
      "classification": "missing",
      "depends_on": [],
      "citations": [],
      "responsibility": "advisor",
      "source": null
    }
  ],
  "reviews": []
}
```

Node IDs are stable lowercase identifiers. `kind` is document, fact,
assumption, analysis, draft, gap, source, question, event or deadline.
`classification` is documented, reported, calculated, assumed, judgment,
missing, unreadable or unverified. These are model-authored descriptions of
evidence, not credentials or completion flags. `responsibility` is the case
role or common. `content` must contain the actual finding/draft, not a title
standing in for work. Mark a resolved gap in its content with the resolving
evidence; preserve its stable ID rather than deleting history.

`citations` contain exactly `binding_id` (from the current input manifest) and
`locator` (page, cell, paragraph or quoted passage location). The helper adds
the actual receipt hash, run and source path. Document nodes require citations;
documented/calculated nodes require citations or dependency references. A
hash is not proof that the document has been read. Preserve unreadability.

For a public source, `source` contains exactly `url` (HTTPS), `kind` (rank/type),
`checked_on`, `applicable_on`, `inspected_scope` and `limitations`, all nonempty
strings. Other node kinds use null. Record unavailable or partially inspected
sources honestly; these fields do not certify legal currency.

`depends_on` lists node IDs actually used. The helper captures their exact
versions. On change, direct and transitive descendants become stale. Updating
a node regenerates its dependency bindings; do so only after real reanalysis.
Unknown IDs and cycles fail. Nodes omitted from an update are retained.

For an existing capability's result, finish and declare its source run first;
select that artifact in `prepare_studio_client_workflow.upstream_artifacts`.
Use its returned binding ID and locator in the CNC analysis node. Do not claim
that merely listing `treasury-forecast` executed a calculation.

After a real professional confirmation, a review row has exactly:

```json
{
  "node_id": "creditor_proposal",
  "node_version": "copy the exact saved node version digest",
  "reviewer_ref": "the professional's supplied reference",
  "confirmation_ref": "the actual user confirmation or reviewed document reference",
  "decision": "accepted",
  "reason": "the professional's stated disposition and scope"
}
```

Decisions may be accepted, changes_requested or rejected. A stale target or
wrong version is rejected. The helper labels every review
`record_only_identity_not_verified`: it cannot authenticate the reviewer or
turn the record into a signature/filing authority. Never generate confirmations
for the user. Historical decisions remain in every subsequent snapshot.

After saving, read both the snapshot and the memo. Finalization declares the
request files, every `workflow-revision-*.json`, every `cnc-revision-*.md`, and
the actual model-data reports. A crash after the JSON write can be repaired by
replaying the identical request to regenerate the missing memo. Do not alter
closed artifacts; start a successor run. Snapshots are append-only through
this API; the filesystem itself is controlled by the local user, not an
authenticated immutable remote store.
