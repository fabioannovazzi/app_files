# Source and template policy

## Authority

Prefer, in order, current legislation from official publication services,
current CNDCEC rules or operational material, other institutional guidance,
and then secondary professional material. A page that links to a document is a
distribution path, not necessarily its authority.

The shipped source registry is a versioned research seed. It records what the
component's mechanical rules were built against; it does not prove that a rule
remains current or applies to the case. Before a real run, Codex should verify
current primary sources and the professional should confirm temporal and case
applicability.

The registry records a maintained `currentness` status, `reviewed_on`, and
inclusive `review_by` date. That date is a mechanical re-review boundary, not a
legal conclusion. It participates in the package's earliest-deadline horizon,
which is rechecked against the system UTC date at Apply.

## Reuse

Public availability does not establish permission to redistribute a template.
Every template reference needs a stable ID, version, exact local content hash,
approving studio actor, approval time, reuse status and scope, jurisdiction,
language, review date, and source-basis hash. Values with unknown, prohibited,
withdrawn, pending, stale, or mismatched status may support provenance or
research, but they cannot satisfy a document plan and their wording must not be
copied into the plugin or a client document.

Studio-authored approved templates should live outside the plugin source and
outside published folders. The case artifact records and verifies their
reference; New Client does not copy, merge, render, or populate them.

## Seed source roles

- CNDCEC Regole Tecniche antiriciclaggio, 16 January 2025: professional rule.
- CNDCEC AML operational guidance and supporting forms, March 2026:
  operational guidance and form provenance.
- GDPR and official Italian privacy sources: primary legal framework.
- CNDCEC privacy guidance: professional guidance; it does not by itself decide
  controller/processor status for a service.
- Italian Law 132/2025, article 13: AI-transparency research cue; applicability
  and current wording require verification.

Only these runtime source records may appear in a client review. External
background materials evaluated during workflow design are logged separately in
`research-provenance.json`. Those records provide audit history only: they are
excluded from runtime authority, fee logic, client source lists, and
redistributable wording.

The Table 1 treatment mapping is mechanical only after the professional records
and confirms case applicability with a basis. The source registry and service
description must never decide Table 1 applicability automatically.

## Source change

A new or superseded runtime source version changes a basis hash. The dependent
AML, applicability, document, and monitoring bindings then fail validation and
require a new run and review revision. Template source-basis drift also blocks
that template reference. Preserve the prior review history; do not overwrite it
in place.
