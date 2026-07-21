# Vera

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/vera) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Vera is a bounded AI colleague and reviewer for professional accounting
practices. She prepares, checks, and documents work across eleven specialist
workflows while keeping evidence and review steps visible. Vera does not replace
professional judgement: decisions and responsibility remain with the
commercialista.

The editable implementation of each workflow and its supporting engines remains
in its existing `plugins/<module>` directory. The package builder embeds those
sources under `modules/` when it builds the distributable ZIP.

Vera's umbrella layer owns discovery, routing, the shared icon, dependency
delegation, MCP server dispatch, and a shared local PaddleOCR adapter used by
modules that preserve their own page-level evidence. Each specialist workflow
retains its own deterministic checks, evidence trail, and review surfaces.

Every registered workstream also has a versioned privacy-surface manifest under
`privacy/workstreams/`. It records what remains local, what Codex may read, the
minimum useful context, residual risks, and the notice shown to the
commercialista. The `privacy-surface-review` skill supplies the semantic review;
its deterministic validator enforces complete coverage and fails when governed
workflow source changes without a refreshed review.

The New Client workflow verifies a final-ready document-preparation phase—or an
explicit standalone-evidence posture—and turns studio instructions into an
owner-only review dossier for identity, engagement, per-subject screening,
privacy decisions, mandate/privacy/AI applicability, AML, template-reference
planning, missing evidence, and monitoring. It does not render client legal
documents and never equates an exportable internal dossier with a compliant,
complete, signed, or active client relationship; those decisions and actions
remain with the commercialista.

The Previdenza INPS module registers hash-bound official portal exports and can,
only when the particular service's terms or another applicable permission have
been checked separately, take a read-only local snapshot of one already-open
INPS browser tab. The human performs login, profile/delegation selection, and
navigation with their own credentials. User or studio approval alone does not
establish INPS permission for software-assisted capture. Vera stores no cookies
or browser state and cannot submit or activate anything. Official downloads are
the default evidence; every conclusion remains a draft for professional review.

The Registro Imprese e SARI module prepares a source-backed draft for a
Registro Imprese/REA/Comunicazione Unica practice and keeps DIRE, INPS, INAIL,
SUAP, and IVASS/RUI questions separate. Its ordinary SARI flow is public,
browser-assisted, read-only, and human-selected. SARI's undocumented JSON routes
remain disabled without separately verified written reuse authorization. Vera
does not receive filing credentials, operate a live DIRE session, contact SARI
support, sign, pay, or submit.
