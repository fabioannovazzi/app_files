# Recovery release and withdrawn website lessons

The incident recovery release preserves the owner's deletions in
`9b74daa6030302ac3fe277d04da9178b8405afc1`. It must not recreate the Vera or Lucia
tax-litigation website lessons or their removed `_files` directories. The owner
explicitly approved omitting those two lessons from download packages and
changing the remaining affected download references to existing identical files.

An inspected comparison of every previous package download record found:

- Vera: 761 existing language-file copies with identical SHA-256 values; 17
  withdrawn attachments belonging only to the tax-litigation lesson.
- Lucia: 124 existing language-file copies with identical SHA-256 values; 17
  withdrawn attachments belonging only to the tax-litigation lesson.
- Clara: all 203 existing immutable downloads remain unchanged.

`scripts/course_materials/publication_policy.json` records these explicit
publication choices. Packaging removes only the two prepared lesson folders
and their index entries, retaining the professional skills and repository
authoring. Public catalogue generation omits their links. Other Vera and Lucia
lessons use existing language-file URLs with their original attachment hashes.
Publication checks still reject missing or altered bytes. Runtime HTTPS, host,
redirect, passive-file, size, timeout and SHA-256 controls remain enforced.
A later change to a language copy makes that older download fail its hash
check; a mutable URL does not authorize different content.

This change adds no recipient, upload, model call, credentials or client data.
It does not establish why Claude rejected the original directory. A passing
release check also does not prove directory acceptance or customer recovery.
