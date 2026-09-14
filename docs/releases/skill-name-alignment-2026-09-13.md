# Skill identifier alignment

This release changes seven identifiers across nine exposed entries in Vera,
Lucia and Clara. The skill directories, YAML names, explicit invocations,
Marketplace card keys, root routing, component handoffs and packaged copies use
these names:

| Product | Previous identifier | Released identifier |
| --- | --- | --- |
| Vera and Lucia | `prompt-optimizer` | `legal-tax-answer-planner` |
| Vera and Lucia | `deep-research-validator` | `legal-tax-answer-review` |
| Vera | `check-entries` | `vouching` |
| Vera | `bilancio-xbrl-it` | `bilancio-oic` |
| Vera | `passive-invoice-audit` | `purchase-invoice-review` |
| Vera | `report-builder` | `financial-report-builder` |
| Clara | `interview` | `hosted-interview` |

The retired identifiers are no longer exposed as skill aliases. The localized
public labels are preserved, including Vouching / Verifica documentale. Clara's
Reporting Engine and chart catalog are unchanged.

Component directories, tool APIs and persisted workstream IDs remain the
implementation interfaces of the same workflows. Explicit component-to-skill
metadata now resolves the differently named skill folders for privacy review.
This does not migrate client records or alter calculations, assurance methods,
data transmission, permissions or professional-review requirements.

Codex and ChatGPT expose all nine renamed entries. Cowork exposes the renamed
Vera/Lucia entries and continues to omit Clara's hosted participant interviews.
The Cowork-specific purchase-invoice template also declares the new skill name.
A 27-case artifact regression verifies these host-specific identities, including
the intentional omission, and runs in the product-release CI workflow.

The source rename covers 15 skill folders when canonical component copies are
included. Each passes the skill frontmatter validator. The canonical versions
are Vera 0.1.248, Clara 0.1.197 and Lucia 0.1.45, each aligned across Codex,
ChatGPT upload and Cowork. The release incorporates the teaching-scope changes
merged in PR #620. Renamed operational lessons resolve to existing ledger
component IDs, while answer-planning and review stages retain their lesson
exclusions.

Validation on the combined release:

- Package, privacy, icon and update-notification regressions: 511 passed, 2 skipped.
- Local teaching, product scope and packaged lesson regressions: 158 passed;
  87.69% coverage. This includes 10 rename-specific lesson cases.
- Workflow regressions: 545 passed; the remaining Spanish Vouching expectation
  was updated to its existing public label and passed on targeted rerun.
- Website journey and name-contract regressions: 180 passed, 1 skipped.
- Package builder/privacy coverage: 80.20%; source-drift checks passed.
- Black, Isort, Mypy on six affected source files, and Bandit passed.

An exploratory broader Clara suite also encountered three pre-existing
assertion/contract failures outside these renames: the cache-busted function-page
script URL, optional OCR package identity and management-control dependency
catalog membership. The relevant functions and production sources were unchanged
from the starting commit; this release does not repair those separate issues.

PR #621 contains the reviewable change, merged and deployed on 2026-09-13.
PR #622 aligned the remaining HTML and video-catalog workflow references;
181 website tests and all 23 CI checks passed, and the six changed public assets
matched the deployed source.

On 2026-09-14, Vera 0.1.248, Clara 0.1.197 and Lucia 0.1.45 each showed
Published in OpenAI Platform and the same version in the public directory.
All 63 skill checks passed (Vera 37, Clara 16, Lucia 10). The user confirmed
the four publisher declarations before submission and publication.
`marketplace-publications.json` records each submission URL and the SHA-256
of the exact uploaded archive; the public update manifest advertises the
confirmed Vera and Clara versions.

The subsequent teaching release in PR #623 advanced repository packages to
Vera 0.1.249, Clara 0.1.198 and Lucia 0.1.46. Those repository versions remain
unchanged by this publication record. Refreshing Clara's privacy fingerprint
for the update manifest rebuilds its current 0.1.198 archives; the Marketplace
hash continues to identify the actual published 0.1.197 archive.

Publication follow-up validation: 477 package, update-notification, release,
skill-identity and privacy tests passed, with two environment-dependent skips.
All three product distribution checks passed. Comparing both rebuilt Clara ZIPs
with their PR #623 versions found only the reviewed
`privacy/hosted-services/plugin-update-check.json` change.

These are workflow-name changes. No model substitution or claim of measured
improvement in Astra's skill selection is included.
