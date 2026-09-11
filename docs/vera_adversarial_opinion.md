# Vera adversarial opinion

## Accepted behavior
- Informational legal/tax/compliance research follows preparation, research and validation. It does not automatically generate a counter-opinion.
- An opinion on a concrete position, or an explicit opposing-opinion request, includes the fourth stage after original validation. Respect explicit instructions to omit it. The user's intended result determines the scope semantically; keywords, client facts alone, research mode and validation outcome do not determine it.
- Use the current model and runtime; no model-diversity requirement, extra consent, or user configuration.
- Develop the strongest evidence-bound opposing case. Allow no substantial opposing case and evidence-limited outcomes; never force disagreement.
- Preserve the original opinion and its validation result. Review the opposing opinion with the existing source/support/reasoning discipline.
- Deliver the original opinion, adversarial opinion or reasoned negative result, and a concise comparison of decisive issues, evidence gaps, and professional choices.
- Keep a negative-result document concise. An evidence-limited result identifies the missing decisive evidence and the unresolved question; preserve its search and review records without manufacturing an opposing case.

## Implementation
1. Add a dedicated Vera adversarial-opinion skill and a Vera-specific execution reference describing the full exercise, same-engagement file lifecycle, research, and model-led judgments.
2. Record `adversarial_policy` (`required` or `not_required`) and `adversarial_rationale` from model-led scope review. Only the required path keeps original validation pending for the opposing stage. The ordinary path can complete validation and deliver without a combined opinion package.
3. Add an internal prepare/package/verify helper under Vera, reusing deep-research-validator. Bind the exact original package, counter-opinion review, and comparison; reuse current validation for both documents, enforce same-run paths and non-stale artifacts, and render a localized final delivery index. Code checks shape, exact hashes and declared statuses only.
4. Update the Vera router, workflow catalog/registry, release projections, public process explanation in five languages, and function-specific data-path manifests.
5. Verify synthetic complete, no-counterposition, limited-evidence, stale-input, invalid-source, missing-stage, and correction cases; exercise packaged CLIs as well as focused regressions and required release gates.
6. Rebuild canonical affected products and downloadable packages, merge through green CI, deploy through Git, verify live pages and exact ZIP hashes, complete publication if authorized tools permit, and remove this task's branch/worktree. Preserve pre-existing unrelated work.

## Evidence boundary
Automated acceptance proves lifecycle, artifact binding, and packaging behavior. Synthetic semantic exercises demonstrate inspected examples; they do not prove future usefulness or certify legal correctness.

## Inspected validation

The automated acceptance suite exercises independent original/opposing review
states, credible/negative/limited outcomes, missing or stale phase artifacts,
source membership, contract changes, recursive policy removal, path boundaries,
and completed-run read-only verification.

A separate forward test used a fictional contractual deadline dispute with
two plausible readings of the same supplied agreement. It produced both
reviewed opinions, a comparison, three visually inspected DOCX files, four
model-data phases and a completed Studio Archive run. Both opinions retained
their professional-review requirement. The original was unchanged.

The forward test found that verification initially rejected a completed run.
The CLI now permits read-only verification after completion while preparation
and packaging remain restricted to an active run. This is covered by real
Studio Archive lifecycle fixtures.

These are synthetic exercises. They do not establish legal correctness,
future usefulness, or performance on live client disputes.

## Scope regression cases

`plugins/vera/evals/adversarial_scope_cases.json` records representative intent
cases for model-led review, including informational tax-credit research,
concrete opinions, explicit overrides, ambiguous wording and scope changes.
It is not a runtime keyword classifier. Expected decisions are reviewed examples,
not proof that every future model run will infer intent correctly.

Automated package tests separately verify that `not_required` can finish
ordinary validation through both ordinary research and Deep Research, without
phase folders or an opposing-delivery dependency; invoking opposing preparation
with that policy is rejected without creating an adversarial run. Existing
tests retain the required opposing stage independently of validation outcome.
