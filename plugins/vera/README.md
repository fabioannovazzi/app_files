# Vera

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/vera) · [MIT License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Vera is a bounded AI colleague and reviewer for professional accounting
practices. She prepares, checks, and documents work across eleven specialist
modules while keeping evidence and review steps visible. Vera does not replace
professional judgement: decisions and responsibility remain with the
commercialista.

The editable implementation of each module remains in its existing
`plugins/<module>` directory. The package builder embeds those sources under
`modules/` when it builds the distributable ZIP.

Vera's umbrella layer owns discovery, routing, the shared icon, dependency
delegation, MCP server dispatch, and a shared local PaddleOCR adapter used by
modules that preserve their own page-level evidence. Each specialist module
retains its own deterministic checks, evidence trail, and review surfaces.

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
