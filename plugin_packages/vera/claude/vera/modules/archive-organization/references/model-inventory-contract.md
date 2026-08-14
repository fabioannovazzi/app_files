> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Model inventory contract

Archive Organization receives one complete projected inventory with schema
`vera.archive_organization_model_inventory.v1`. It contains:

- an opaque `inventory_ref`, storage kind, root display name, capture time,
  bounded file count, known aggregate size, and exclusions;
- one row for every snapshotted file, with an opaque `item_ref`, projected
  client-relative path, filename, extension, MIME type when available, size,
  modification time, content-opening availability, and opaque exact-duplicate
  relationships;
- explicit flags confirming that raw hashes, Google Drive IDs, and absolute
  paths were not returned.

The projection does not sample the archive: every file within the 5,000-file
and 2 GB snapshot bounds remains available for semantic classification. Local
deterministic code retains and revalidates the raw path, content hash, Drive
file and parent IDs, version, checksum, and capability data required for safe
opening or execution.

Call `open_studio_archive_organization_item` with the selected `item_ref` when
document content is needed. It returns bounded extracted evidence after local
identity revalidation and does not return the underlying execution identifier.

This is purpose-limited pseudonymization of technical handles, not
anonymization. Client-facing names, projected relative paths, and selected
document content remain visible when they are material to professional filing
judgment.
