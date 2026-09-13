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
included. Each passes the skill frontmatter validator. Final release versions,
validation results, merge and deployment evidence are recorded when completed.

These are workflow-name changes. No model substitution or claim of measured
improvement in Astra's skill selection is included.
