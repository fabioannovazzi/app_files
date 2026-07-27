---
name: privacy-surface-review
description: Use when adding, changing, reviewing, or releasing a Vera workflow or shared service to record model-context, provider-account, external-data, and security boundaries before packaging.
---

# External Boundary Review

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

This is a developer and release workflow, not a customer-case intake step. A
normal Vera run does not show a privacy notice or request privacy confirmation
merely because the selected model runtime reads professional case data.

## Review workflow

1. Resolve the Vera root and read `components.json`, including registered
   workstreams and shared services.
2. Select the changed workstream and resolve its source as
   `modules/<workstream>` in an installed package or `../<workstream>` beside
   Vera in repository source. Treat that resolved root as the plugin working
   directory for the review.
3. Read that module's complete workflow skill and the relevant scripts, schemas,
   MCP tools, and review-payload builders.
4. Record the classes of information the workflow can place in model context.
   Real client and case data may enter the selected runtime's model context. Do
   not promise local-only processing when OpenAI Codex or Anthropic Cowork reads
   the material.
5. Read `privacy/runtime-profiles.json`. Each workstream references both
   `openai-codex` and `anthropic-cowork` rather than duplicating provider copies
   of the workstream manifest. The shared profiles state the selected account,
   provider model-processing destination, absence of automatic anonymization,
   and absence of a local-only guarantee.
6. Record every external boundary: public research or URL fetching, a
   hosted service, an external connector, or a send/publish action. An empty
   list is a valid and useful result.
7. For each external boundary, state the destination, purpose, content,
   applicable runtime profiles, whether it is optional, whether confirmation is
   required, and the controls enforced by the workflow. A separate confirmation
   is required only when the route is optional and the user has not already
   chosen it. The user's explicit route choice is the confirmation; do not ask again.
8. Record only concrete security controls and the account boundary selected by
   the firm or user. An empty security-control array is more accurate than
   relabelling local processing, draft status, or policy wording as security.
   Vera cannot inspect or enforce the user's plan, model-training data controls,
   or retention/deletion controls. The firm or user checks those before
   professional use and when the account or terms change, not in a per-case form.
   For ordinary model processing, record that the selected OpenAI Codex or
   Anthropic Cowork account arrangement applies, Vera is not a separate
   recipient, nothing is automatically anonymized, processing is not local
   only, and local filtering or aggregation is used only when it helps the
   work.
9. Update `privacy/workstreams/<workstream>.json` or
   `privacy/services/<service>.json` using `references/manifest-contract.md`,
   then refresh its source fingerprint:

```bash
python skills/privacy-surface-review/scripts/validate_privacy_surfaces.py \
  --refresh <workstream>

python skills/privacy-surface-review/scripts/validate_privacy_surfaces.py \
  --refresh-service <service>
```

10. Validate the complete register, run the Vera package tests, and rebuild the
   plugin ZIP:

```bash
python skills/privacy-surface-review/scripts/validate_privacy_surfaces.py
```

## Judgment boundary

Use deterministic code only for JSON shape, registered-workstream coverage,
allowed boundary kinds, confirmation consistency, exact file hashing, and
stale-review detection.

GDPR data minimisation remains a legal principle. Do not implement it here as
deterministic deletion, automatic anonymisation, personal-data detection, or a
`minimum useful context` classifier. Whether a fact is relevant to the
professional purpose is semantic, case-specific judgment outside the
validator. A name or tax identifier may be relevant and may be read by the
selected model runtime.

The register is an engineering boundary review. It is not legal advice, a DPIA,
an account-configuration audit, or proof or certification of GDPR compliance.
