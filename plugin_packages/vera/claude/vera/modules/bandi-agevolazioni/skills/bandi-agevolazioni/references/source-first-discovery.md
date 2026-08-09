> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Source-first discovery — operating contract

Use this contract for recent-opportunity discovery before general semantic web
search. It governs execution order and coverage evidence; it does not create a
universal source list or decide legal relevance.

## Reviewed priority-source registry

`source_plan.entries` is the persistent registry for one private radar. The
model proposes entries from the reviewed territory, activity and investment
context; the professional confirms them. Each entry records:

- an exact official HTTPS URL and publisher;
- `priority_direct` or `supplemental_direct` discovery role;
- source surface, such as official gazette, act repository, official register,
  funding portal or publisher page;
- territories, categories and act families that explain why it belongs in the
  radar; and
- DGR, DDR, BUR issue, call, annex, FAQ, amendment and portal-notice families
  where professionally relevant.

The fields are reviewed metadata, not deterministic routing rules. Code never
selects a domain from a territory or category string and never infers source
authority from an act label.

Representative source proposal shape:

```json
{
  "source_id": "SOURCE-VENETO-BUR",
  "authority_level": "regional",
  "publisher": "reviewed publisher name",
  "official_url": "https://reviewed-official-source.example/",
  "discovery_role": "priority_direct",
  "source_surface": "official_gazette",
  "territories": ["Regione Veneto"],
  "categories": ["artigianato"],
  "act_families": ["dgr", "ddr", "bur_issue", "annex", "amendment"],
  "relevance_rationale": "Model-led rationale for professional review.",
  "profile_refs": ["CLIENT-OPAQUE-001"],
  "next_check_on": "2026-08-09"
}
```

The example domain is intentionally non-operational. Supply only the exact
official URL inspected and accepted for the actual radar.

## Temporal scan

Start every recent discovery with an explicit inclusive `window_start` and
`window_end`; 30–60 days is an ordinary operating choice, not a hard-coded legal
rule. Record the query context using generic territory, category and request
summary only. Never put client identity, opaque references, project narrative,
financial facts, quotations or declarations into public research.

The model or operator proposes one query-scoped source selection from confirmed
registry entries. It does not choose sources by deterministic string matching.
For each exact territory and category in `query_context`, the proposal records
one `covered` claim with selected source IDs or one explicit `gap` claim with no
source IDs, plus a semantic rationale. The professional reviews this complete
selection before any worklist or source check can run.

The running scan seals that reviewed selection and its exact selected-source
registry revision. Render its worklist and execute these phases in order:

```json
{
  "scan_id": "SCAN-2026-08-08-VENETO-ARTIGIANI",
  "query_context": {
    "territories": ["Regione Veneto"],
    "categories": ["artigianato"],
    "request_summary": "Nuovi bandi per artigiani in Veneto"
  },
  "source_selection": {
    "priority_source_ids": ["SOURCE-VENETO-BUR"],
    "supplemental_source_ids": [],
    "scope_coverage": [
      {
        "dimension": "territory",
        "query_value": "Regione Veneto",
        "status": "covered",
        "source_ids": ["SOURCE-VENETO-BUR"],
        "rationale": "Proposta semantica da sottoporre al professionista."
      },
      {
        "dimension": "category",
        "query_value": "artigianato",
        "status": "covered",
        "source_ids": ["SOURCE-VENETO-BUR"],
        "rationale": "Proposta semantica da sottoporre al professionista."
      }
    ],
    "selection_rationale": "Razionale complessivo proposto per revisione."
  },
  "started_at": "2026-08-08T09:00:00+02:00",
  "completed_at": null,
  "window_start": "2026-06-09",
  "window_end": "2026-08-08",
  "semantic_web_check": {
    "status": "not_run",
    "checked_at": null,
    "result_count": null,
    "error_code": null
  },
  "outcome": "running",
  "error_codes": []
}
```

`record-scan` records exact model/provider/template provenance and forces the
selection to `proposed`. Review it with scope `scan_source_selection`. A
returned or rejected selection may be revised before source checks; a confirmed
selection cannot be silently replaced.

1. inspect every reviewed `priority_direct` URL directly across the requested
   window, including new publications and updates;
2. inspect professionally relevant acts and attachments that may precede a
   public-facing funding page, including DGR, DDR, BUR issues, annexes and formal
   amendments;
3. inspect reviewed `supplemental_direct` sources when applicable; and
4. only then use semantic web search to find leads, aliases or missed references.

The runtime may use read-only browser or web-fetch capabilities to inspect the
worklist. The plugin itself does not contain an authenticated publisher feed,
background crawler or scheduler.

## Check evidence and cursor

Record one source check against one running scan. It must include the scan ID,
stable check ID, observed time, covered date window, result count or failure,
and professional review. When the source exposes a stable publication ID, date
or URL, record it as `cursor_after`; a later zero-result check preserves that
cursor. Cursors accelerate delta review but never allow the runtime to skip the
requested historical window or assume that publisher ordering is complete.

```json
{
  "external_id": "reviewed-publication-id",
  "publication_date": "2026-08-07",
  "official_url": "https://reviewed-official-source.example/publication"
}
```

The terminal scan embeds immutable check snapshots, so later checks do not
rewrite prior coverage evidence. A changed source registry invalidates the
running scan; start a new scan rather than silently changing its denominator.

## Coverage gate

Code may record outcome `complete` only when the exact query-scoped selection is
professionally confirmed, every territory and category claim is `covered`, and
every selected priority source has a review-confirmed terminal `checked` or
`not_applicable` disposition for the whole requested window. Failed,
unavailable, missing or newly unreviewed selected sources remain in
`unverified_priority_source_ids`; declared query gaps remain in
`uncovered_scope_keys`; either condition requires a `partial` or `failed`
outcome. Rejected registry proposals that are not selected for the scan are
excluded and do not deadlock later scans.

This deterministic gate is justified by contract auditability: exact query
values, declared coverage claims, source IDs, windows, timestamps and review
states are mechanically observable. It never decides which source covers a
territory or category, which sources should be priority, whether an act creates
a measure, or whether an opportunity is relevant.

The report states query territories and categories, selection review, declared
scope coverage and gaps, sources checked, requested period, last verification
time, unverified priority sources and semantic-web status. Even full selected-
registry coverage is not the probability that all opportunities were found and
must not be described as exhaustive discovery.

## Lifecycle observations

Model reasoning proposes and the professional reviews every lifecycle meaning.
The record supports `announced`, `approved`, `published`, `upcoming`, `open`,
`closing_soon`, `extended`, `modified`, `funds_available`, `suspended`,
`closed`, `refinanced` and `unknown`. Preserve observations append-only with
effective date, observed time, source references and rationale. An amendment or
FAQ never changes a lifecycle state silently.
