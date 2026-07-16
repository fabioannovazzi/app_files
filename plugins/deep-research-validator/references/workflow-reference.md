# Validate Deep Research Workflow Reference

This reference expands the core workflow in `SKILL.md`. Load it when a run needs detailed review categories, source-support wording, or packaging interpretation.

## Claim Selection

Review material claims rather than every sentence. Prioritize:

- conclusions and recommendations;
- legal, tax, compliance, or eligibility positions;
- numeric claims, percentages, dates, thresholds, and deadlines;
- causal claims and risk statements;
- claims used as premises for later conclusions.

Skip purely introductory, stylistic, or duplicated statements unless they carry a material conclusion.

## Verdicts

Use these verdicts in `claims_review.json`:

- `supported`: the cited source directly supports the same fact or conclusion.
- `partially_supported`: the source supports part of the claim or supports a narrower conclusion.
- `not_supported`: the source does not support the claim.
- `contradicted`: the source conflicts with the claim.
- `uncertain`: support cannot be determined because sources are unavailable, gated, too short, or ambiguous.

## Review Dimensions

For each reviewed claim, separate:

- source availability: URL/file reachable and parseable;
- quote match: cited passage found exactly or approximately;
- semantic support: source actually supports the claim;
- reasoning: conclusion follows from the supported premises;
- proposed fix: correction, caveat, or citation request.

## Output Guidance

The validation package is not a new substantive answer. It is a review record. State assumptions and source limits clearly. Preserve the user's document structure when writing a corrected Markdown document.

## Deterministic Audit Interpretation

`validation_audit.json` is a guardrail, not a legal conclusion. If it fails, repair missing review fields or invalid verdicts where possible. If source quote matching fails because only short excerpts were fetched, report the limitation instead of treating it as proof that the source is wrong.
