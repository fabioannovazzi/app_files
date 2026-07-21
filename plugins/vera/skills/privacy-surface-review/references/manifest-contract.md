# Privacy manifest contract

Each file in `privacy/workstreams/` records one component from
`components.json`. It is a design-time register, not a runtime scan of customer
files and not a legal compliance determination.

## Required fields

- `schema_version`: currently `1`.
- `workstream`: exact registered component ID.
- `display_name`: human-readable workflow name.
- `role`: `workflow` or `internal_engine`, matching `components.json`.
- `governed_paths`: component-relative files or directories whose bytes form
  the freshness fingerprint. Normally include `skills`, `scripts`, `mcp`, and
  `schemas` when present.
- `data_flow.local_sources`: source classes that remain in the local workspace.
- `data_flow.local_processing`: mechanical processing performed before Codex
  reasoning.
- `data_flow.codex_context`: every distinct Codex-reading surface. Each entry
  records `id`, `purpose`, `content`, `minimum_necessary`,
  `semantic_reasoning_required`, and `full_source_expected`.
- `residual_risks`: remaining context risks and their design mitigations.
- `commercialista_notice`: `level`, `timing`, `message_it`, `message_en`, and
  `requires_confirmation`.
- `review`: review basis, limitations, date, and deterministic source
  fingerprint.

## Drafting rules

Describe content classes, not hypothetical identifiers. Do not say that data is
anonymous merely because a deterministic parser did not recognize a name.
`minimum_necessary` is a design judgment about the workflow, not a GDPR legal
conclusion. Set `full_source_expected` to true only when normal professional
quality requires the complete source in Codex context.

Notices must say what Codex receives and what remains local. Avoid warnings that
repeat the same point or ask for consent when no optional choice exists.
