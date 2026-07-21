---
name: privacy-surface-review
description: Use when adding, changing, reviewing, or releasing a Vera workstream to trace what stays local, what Codex may read, what can be minimized mechanically, what requires semantic interpretation, what the commercialista should be told, and to update the workstream's registered privacy manifest before packaging.
---

# Privacy Surface Review

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Review the real boundary where information becomes available to Codex. Do not
classify risk from the input-folder contents alone and do not add generic
redaction. The relevant question is what Codex may read after local processing.

## Review workflow

1. Resolve the Vera root and read `components.json`.
2. Select the changed workstream and resolve its source as
   `modules/<workstream>` in an installed package or `../<workstream>` beside
   Vera in repository source. Treat that resolved root as the plugin working
   directory for the review.
3. Read that module's complete workflow skill plus relevant scripts, schemas,
   MCP tools, and review-payload builders. Trace every point at which Codex reads user
   instructions, source material, extracted text, structured results, review
   payloads, or generated artifacts.
4. Separate:
   - source data and mechanical work that remain local;
   - the minimum useful result Codex needs;
   - original language or case facts genuinely needed for interpretation;
   - material that enters context before the workflow can intervene, such as a
     user's typed prompt.
5. Use model judgment for semantic necessity. Never claim that a deterministic
   name, identifier, or personal-data detector can establish necessity or
   anonymization.
6. Update `privacy/workstreams/<workstream>.json` using
   `references/manifest-contract.md`. Write a concise Italian and English notice
   that describes the actual boundary without claiming GDPR certification.
7. Only after completing the semantic review, refresh the mechanical source
   fingerprint:

```bash
python skills/privacy-surface-review/scripts/validate_privacy_surfaces.py \
  --refresh <workstream>
```

8. Validate the complete register:

```bash
python skills/privacy-surface-review/scripts/validate_privacy_surfaces.py
```

9. Run the Vera package tests and rebuild the plugin ZIP.

## Judgment boundary

Use deterministic code only for schema validity, registered-workstream
coverage, wrapper-notice integration, exact file hashing, and stale-review
detection. These checks are mechanically verifiable and audit-sensitive.

Use model-led reasoning for whether content is necessary, whether local
reduction preserves professional quality, which residual privacy issue matters,
and what notice is useful. A validator must never overrule that judgment.

## Notice policy

- `none`: Codex receives no customer or case material for the workflow.
- `informational`: explain the boundary in the Run Intake before the first
  workflow-controlled evidence read; do not ask for redundant confirmation.
- `confirmation`: use only when a genuinely optional disclosure or processing
  route requires a user choice before it occurs.

If the user already typed case material into Codex, state that the material is
already in context. Do not imply that Vera can remove it retroactively.

Never describe a manifest as legal advice, a DPIA, automatic anonymization, or
proof of GDPR compliance.
