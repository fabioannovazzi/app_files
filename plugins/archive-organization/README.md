# Vera · Riordino archivio

Client-bound workflow for screening a customer folder, proposing a versioned
studio filing plan, collecting persistent collaborator decisions, and applying
only explicitly approved changes with no overwrite, an operation journal, and
rollback.

The workflow is intentionally two-layered: Codex/model reasoning proposes the
meaning of documents and probable duplicates; deterministic code owns hashes,
path containment, exact duplicates, collision checks, file operations, and
recovery.

## Google Workspace mode

The workflow supports both ordinary local folders and a Google Drive v3 mode
for My Drive or Shared Drive client folders. Studio Archive binds one stable
Vera client ID to one exact Drive folder ID and snapshots descendant file IDs,
parent IDs, versions, capabilities, and available checksums. Google-native
Docs, Sheets, and Slides are version-bound because Drive does not expose their
binary checksums; exact-duplicate detection is therefore limited to binary
files with a Drive SHA-256 checksum, while semantic duplicate judgment remains
model-led.

After review and a second explicit approval, Drive apply creates only the
needed target folders and changes each approved file's parent and name through
the Drive API. File IDs, links, sharing, and history remain attached to the
same item. Apply revalidates remote state, rejects existing or duplicate target
names, journals original parents and names, and can move unchanged items back.
Created empty folders are deliberately left in place after rollback rather
than silently deleted.

Native mode requires the restricted
`https://www.googleapis.com/auth/drive` OAuth scope. A production multi-tenant
deployment must complete Google's applicable OAuth verification and security
assessment. Tokens are stored only in Studio Archive's private state directory.
