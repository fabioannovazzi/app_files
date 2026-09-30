# Fusione guidata P1

P1 extends the recovered Discord proposal's two domestic OIC incorporation
branches. P0 records, imports, version-bound confirmations and impact history
remain available. The module executes reviewed workpapers and prepares a review
dossier; it does not execute a legal merger.

## Requirement and implementation

| Required increment | Implemented component |
|---|---|
| Two declared incorporation branches | Transactional `BranchDecision` workpaper, evidenced scope assertions, direct ownership edge for wholly owned cases; no semantic branch classifier |
| Valuation and exchange | Exact equity or enterprise bridge; per-shareholder exchange and resulting fractions; no implicit rounding; no new shares for cancellation of wholly owned target |
| Opening balances | Mapped reviewed balance sheets; explicit reciprocal pairs, retained mismatches, participation cancellation/new capital, separately reviewed difference allocation and independent fiscal values |
| Calendar | Source-bound events, last selected company anchor, days versus calendar months, actual-date checks, explicit reviewed adjustments and missing receipt state |
| Dossier | Model-authored evidence-bound professional sections plus exact workpapers, Markdown/escaped HTML exports, pending reviews and execution boundaries |
| Studio Archive | Actual client/engagement binding and receipt/byte verification through the existing ledger; explicit per-company imports; no implicit cross-client writeback |
| Review and change | Exact input references derived from request structure inside the write transaction; immutable results; stale inputs, unknown facts and declared applicability failures block approval |
| Acceptance | Both complete synthetic cases, actual archive calls, changed-input impact, adversarial arithmetic/calendar/access tests; P0 regressions retained |

Deterministic code is used for exact arithmetic, date conventions, reference/hash
integrity, access checks and transactions because those contracts are mechanically
verifiable. The model/professional selects the legal route, material facts, source
applicability, economic values, accounting classifications/policy and exceptions.

## Run

Activate the repository environment, then:

```sh
python plugins/fusione-guidata/scripts/check_dependencies.py
python plugins/fusione-guidata/scripts/run_fusione.py demo-p1 --output /absolute/new-demo
python -m pytest -q -o addopts='' --confcutdir=tests/plugins tests/plugins/test_fusione_guidata.py tests/plugins/test_fusione_p1.py --cov=plugins/fusione-guidata/scripts --cov-fail-under=80
```

The demo creates two synthetic Studio Archive client/engagements, verified input
receipts, a durable case, command requests, before/after review dossiers and
`p1-demo-results.json`. It neither reads real clients nor obtains actual professional
approval. Inspect the source review and exact request contract beside the skill.

## Scope and acceptance limits

P1 supports two companies, ordinary homogeneous rights, exact share/capital-unit
allocations and no cash adjustment. Fractional shares require a dedicated
allocation outside this increment. Source balances must already reflect the
professionally selected closing date and adjustments; P1 does not infer accruals,
retroactive-period entries or accounting categories. Differences are not goodwill
or distributable reserves by default. Tax positions are retained separately; tax
neutrality, deferred-tax policy and loss/group treatment are not determined.

Calendar arithmetic applies the explicit professional convention. Statutory
waivers, holidays, creditor exceptions and the correct law for the case are not
inferred. Source discovery found readable GU, MIMIT and OIC documents; current
Normattiva article retrieval failed. No pre-approved consolidated rulepack is
shipped. Each real case must acquire and review its applicable primary sources.

Partial/90%, inverse, sister-company, MLBO, IFRS, cross-border, crisis, regulated
and new-company merger branches remain unsupported. No signatures, filings,
external messages or real-client acceptance are claimed. Local actor declarations
and filesystem hashes do not authenticate people or encrypt client files.

## Acceptance scenario mapping

T01/T02/T15: the two calculation paths and exact independent-company example.
T04/T06/T17: outside-scope declarations refuse the simple path.
T08/T09: day/month boundary arithmetic (the model selects actual legal applicability).
T18/T19/T20: missing/invalid input, no automatic goodwill, unresolved reciprocal differences.
T29/T30/T34/T36: date/source changes, failed-source status, no invented filing,
selective reopening with retained prior approvals.
The other contributor scenarios, advanced tax outcomes and professional legal
acceptance are not represented as executed release tests. The tests assert
software behavior under their declared inputs, not correctness of every legal
conclusion in the original proposal.

## Verification on 2026-09-30

The P0/P1 suite passed 126 tests at 88.89% module coverage. Both synthetic cases passed all 16 checks from the Codex, ChatGPT-upload and Cowork archives, and from an isolated component with its vendored Studio Archive ledger. Black 25.1.0, Isort, Mypy and Bandit passed. This exercises the packaged helpers, not installation or host-driven professional acceptance.

The broader package, privacy, icon, website and release-alignment suite passed 659 tests with two conditional skips. All five function-page language controls were verified in the browser.
