---
name: innovation-report-validator
description: Use when working on the slide/deck validator for innovation monitoring reports, launch report PDFs, launch package validation, OCR text-unit review, claim filters/checkers, validation overlays, or files such as src/slides/launch_pdf_validator.py and scripts/validate_launch_reports.py. This skill keeps the work scoped to deterministic innovation-report validation, not generic deck validation.
---

# Innovation Report Validator

## Required Documentation

Before working on the validator, read and follow the fixed loop in
`docs/innovation_report_validator_loop.md`.

That document is the source of truth for the validator process. Do not replace
it with a different taxonomy, review workflow, or deck-level pass/fail framing
unless the user explicitly asks to change the loop itself.

## Vocabulary

Terms such as emerging, winning, fragmented, stable, brand-led, broad-based, niche, declining, and premium-skewed should become deterministic only when they have computable definitions against package data.

Example: emerging can mean a defined recent-vs-rest presence gap, ratio, support count, and brand-count threshold. The exact definition must be encoded in Python before it becomes deterministic validation.

## UI/Debugging Principle

Prefer auditable validation surfaces over opaque status summaries. When building or changing validator UI, expose what the system read and decided:

- extracted text unit and source kind: title, bullet, table row, visual text, figure region, fallback OCR
- classification: deterministic claim, residual claim, non-claim, OCR/layout issue
- rule/checker that fired
- source package evidence used
- observed value, expected value, denominator, tolerance, and reason

A visual overlay similar to the slide-deck OCR view is appropriate: show/hide extracted units and color approved, not approved, unresolved, residual claim, and non-claim text differently.

## Standards For Changes

- Do not critique the validator for not handling arbitrary decks.
- Do not add one-off rules that only memorize one deck instance.
- Do add rules derived from real report text when they represent reusable innovation-report claim families.
- Keep deterministic checks separate from LLM advisory classification.
- Before changing final status logic, first establish coverage, false positives, false negatives, source mapping correctness, and residual claim handling.
