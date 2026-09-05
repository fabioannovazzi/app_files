> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Institutional discovery in Claude and ChatGPT

This is the shared operating method for CR-38, CR-39 and CR-40. Apply it to
public research before a client is selected as well as to portfolio radar work.
Read `source-first-discovery.md` for the existing scan and review commands.

## Establish scope and available capabilities

State the inclusive publication window and reference date, territories, sector
and investment topic. For an unspecified region, start with an explicitly
national scope and identify territorial coverage as unresolved; do not silently
claim coverage of every municipality. Ask for location only when it materially
changes the requested result. A public scan does not require private client
records, a portfolio or a Stage B application engagement.

Check whether this session can read public web pages, execute the bundled
scripts and retain private artifacts. In Claude or ChatGPT with those capabilities,
use the same source registry, scan, issue inventory and review commands. Run the
declared dependency check first. Never claim a script ran from a suggested
command or manufacture professional confirmation.

With browsing but without local execution, apply the same research order and
coverage rules and render the registry, issue ledger and findings in the answer
or an available downloadable artifact. Keep reviewer decisions explicit and
unreviewed conclusions provisional. State that no local schema validation,
hash-bound review, workspace isolation or durable persistence was performed.
Do not invoke unavailable CLI tools or abandon research solely because this is
ChatGPT. With no durable storage, return the full register for the user to retain
and reattach on the next run. With no browsing, inspect provided official
material only and report partial coverage; do not claim a current scan. Stage B
still requires its bound Studio Archive context to produce a validated dossier.

## Build a fresh, auditable institutional inventory

For each request, reason about relevance across all these source families:

- EU funding and programme authorities;
- Gazzetta Ufficiale, relevant ministries including MIMIT, Incentivi.gov.it and
  Invitalia;
- Agenzia delle Entrate, INAIL, GSE, ISMEA, SIMEST and ICE;
- Unioncamere and the relevant territorial Camere di commercio;
- Regioni and Province autonome, their BUR and act repositories, FESR managing
  authorities and regional finance agencies;
- Province, Città metropolitane and the relevant Comuni and their public notices.

This is a coverage checklist for model reasoning, not a fixed allow-list or a
rule mapping a sector to a domain. For each family record included sources,
a reasoned exclusion, or an unresolved gap. Being a national request is not
proof that regional measures are irrelevant. Include Gazzetta Ufficiale in a
broad national recent-PMI scan and inspect all its Serie Generale summaries in
the window; any narrower scope needs an explicit rationale.

Discover additional institutions through links and directories on inspected
official pages, programme documents and issuer references. If necessary, use a
narrow institutional-directory search to locate an official source; this is
registry construction, not general opportunity discovery. Verify the destination
and publishing authority directly before accepting it. Preserve the referring
URL and discovery rationale in `relevance_rationale`. Follow relevant newly
found sources recursively until the reviewed scope is covered or explicitly
bounded. Never treat an unreachable, stale or search-snippet-only page as checked.

Use `record-source` for each new source, with a stable ID, exact official URL,
publisher, authority level, territory, categories, act families, discovery role,
provenance and next-check date. Use empty `profile_refs` for public-only research.
Review entries and the query-scoped selection before the source worklist. To
replace an obsolete endpoint, append a new source ID explaining which prior
entry it replaces and why; select it in a new reviewed scan and retain the old
entry and snapshots. Do not overwrite prior check history. If a new relevant
source is found during complementary search, register and check it in a follow-up
scan before claiming it is covered; disclose the earlier scan's narrower scope.

The delivered register must show family, ID, publisher, URL, relevance and
origin, selection/review state, date checked, covered window, outcome and gaps.
Retain reasoned exclusions and unresolved families in the selection rationale
and the visible scope discussion. Ratios describe the reviewed selection only.

## Enumerate gazette issues before interpreting acts

Read the official date index/archive, including every pagination page and
relevant supplement, to enumerate all issue summaries in the inclusive window.
Open each summary sequentially. Do not infer the inventory from search results,
weekday rules, issue-number arithmetic or a last-seen cursor. Read every summary
entry, then open the potentially relevant acts and attachments. A funding
programming decree is a candidate even if no application calendar exists.
Record inaccessible summaries individually and make the source check partial
(`unavailable` or `failed` in the CLI), never `checked`.

Pass `--issue-inventory-input <inventory.json>` to `record-source-check` for an
`official_gazette`. The object uses this shape (synthetic example):

```json
{
  "index_urls": ["https://official.example/archive"],
  "enumerated_at": "2026-09-02T09:00:00+02:00",
  "window_start": "2026-08-29",
  "window_end": "2026-08-29",
  "enumeration_complete": true,
  "empty_window_rationale": "",
  "issues": [{
    "issue_id": "GU-SG-2026-200",
    "official_url": "https://official.example/issue-200",
    "publication_date": "2026-08-29",
    "status": "checked",
    "checked_at": "2026-09-02T09:10:00+02:00",
    "act_urls": ["https://official.example/act-26A04448"],
    "notes": "Full summary inspected; programming act retained for review."
  }]
}
```

Replace every example URL with observed official evidence. `index_urls` lists
all archive pages actually used. `enumeration_complete` is an operator assertion
for professional review, not automated proof of publisher completeness. Empty
windows require an evidenced rationale. Each issue records `checked`,
`unavailable`, `failed` or `not_checked`, an observation time when checked,
relevant act URLs (possibly empty), and notes on the inspection or obstacle.
The helper validates schema, unique issue IDs, dates, coverage, and review hashes;
it cannot prove a page was read or judge an act's relevance. Preserve the same
fields in chat when scripts are unavailable. A complete source check requires a
complete enumeration and every enumerated issue checked. The sealed scan keeps
this inventory and its review binding.

## Interpret and deliver

After priority-source attempts, perform complementary semantic searches and
cross-check official leads. For every candidate cite the precise act/page,
publication date and latest checked implementing material. Separate open calls,
upcoming openings with supported dates, programmed measures (`programmed`),
closed calls, and measures without an operating calendar
(`no_operating_calendar`). Do not turn publication, an allocation or an expected
future implementing act into an open application window. Preserve source-backed
lifecycle history, uncertainty and required professional review. Show candidates
even when there is no profile or match.

The report ends with the exact period, source and issue coverage, failed/stale
sources, excluded or unresolved families, review status and runtime limitations.
Describe a scan as complete only for its declared reviewed selection after all
coverage conditions are met; never claim all opportunities have been found.

## Acceptance case from CR-38

The reported reference is decree 28 July 2026, act 26A04448, in Serie Generale
200 of 29 August 2026, concerning programming funds for Brevetti+, Marchi+ and
Disegni+. Use the official issue summary and act as a live acceptance target,
not a hard-coded source selector or a permanent assertion of opening status.
A scan whose window contains that issue must inspect its summary, retain the
programming candidate, and check later implementing acts before assigning dates.
Repeat the same scenario in both Claude and ChatGPT and retain the normal answer,
source inventory, issue ledger, runtime capabilities and exact package version.
Packaging tests prove shared instructions are present; they do not prove either
product executed the research correctly.
