# Opportunity radar — operating contract

The radar precedes application instruction. It answers two bounded professional
questions without claiming completeness or eligibility:

1. given one reviewed company profile, which source-backed opportunities merit
   professional attention; and
2. given one newly observed opportunity, which opaque profiles in the selected
   portfolio merit professional attention.

## Company opportunity profile

Use opaque `client_ref` values. The radar lives in an explicitly authorized,
owner-only studio workspace with asserted local authorization and retention
ownership; it is not a Studio Archive client run. Build separate dated facets for territory,
ATECO, size, legal form, company age, ownership, planned investments, property,
workforce, energy, digitization, vehicles, export, training, innovation, and
case-specific other facts. Do not fill every category by inference. Each facet
records its provenance, evidence references, as-of date and review status.
Document observations must resolve to same-client opaque evidence receipts with
an exact SHA-256. Confirmed profiles change only through append-only revision
events, and every dependent match becomes proposed again.

Profile relevance and missing facets are semantic professional judgments. The
schema enforces only allowed categories, dates, identifiers, provenance and
review state. A `single_client` radar rejects a second profile; use `portfolio`
only for an explicitly selected private portfolio scope.

## Source coverage plan

The model proposes a source plan from the reviewed profile and jurisdiction.
There is no universal deterministic list. Depending on the facts, a plan may
include national bodies and incentive portals, a region and its agencies, the
competent chamber of commerce, province, municipality, EU programmes, and
sector-specific official publishers. The professional confirms relevance.

Each plan entry records one official HTTPS source, authority level, publisher,
relevance rationale, profile references, next check date and review state.
Public discovery queries contain generic call, territory, programme and topic
terms only; they exclude client identity and client evidence.

Coverage is exact execution evidence:

```text
checked reviewed-plan sources / applicable reviewed-plan sources
```

A proposed, returned or rejected plan entry never enters the reviewed-plan
denominator. A professionally confirmed `not_applicable` source leaves the
denominator only after its exact check disposition is separately confirmed.
Unavailable and failed sources remain visible and uncompleted. The percentage
is never a discovery probability and never supports “all available grants were
found.”

## Opportunity lifecycle and monitoring

Store every status observation with its source references, observed time,
effective date, rationale and review state. Allowed observations are
`announced`, `upcoming`, `open`, `funds_available`, `suspended`, `closed`,
`refinanced`, and `unknown`. Their meaning is model-led and reviewed. Code only
requires chronological observed times, requires the current value to equal the
last preserved observation, and rejects rewriting confirmed history. Confirmed
dates, URLs, titles and summaries may change only through a source-referenced
append-only revision event; affected matches become proposed.

Monitoring scans are idempotent and resumable. A running scan can be completed;
a completed scan is immutable. Failed and partial scans retain error codes and
do not masquerade as complete coverage. Scheduling metadata records the next
intended check but does not create an external background job by itself.

## Bidirectional matching

Each match links exactly one opportunity, one opaque client reference, relevant
profile facets and official source-plan entries. The model proposes:

- compatibility (`high`, `medium`, `low`, `no_match`, or `unknown`);
- rationale, missing information and contradictions;
- application complexity;
- an optional economic estimate with explicit assumptions; and
- the next professional action.

These are semantic proposals, not scores produced by keywords or a universal
rule library. The contract prevents a match from using another client's facet.
The professional reviews each match before client contact or application work.

## Economic estimate

The ordinary estimate is a range, not a promise:

```text
net minimum = gross benefit minimum - preparation cost maximum
net maximum = gross benefit maximum - preparation cost minimum
```

Exact subtraction is deterministic because the inputs and assumptions have
already been supplied semantically and the arithmetic must reproduce for audit.
Code does not invent grant rates, eligible expenditure, award probability,
professional fees, effort or strategic value. The professional reviews the
inputs, methodology, assumptions and recommended action. Do not label this
range as a statistically expected value unless a separately supported
probability model exists.

## Handoff

A handoff requires confirmed profile evidence, profile, opportunity, match and
every referenced source-plan entry and exact check result. It contains only the
selected client's subset and seals that subset and its embedded source entries
with hashes the recipient can recompute. Import it into a new client-bound
Studio Archive engagement; registration validates schema, hashes, client
identity and reference closure. Then register and review the exact call,
amendments, annexes, FAQs, forms and client evidence.
The handoff does not establish eligibility, replace official sources, contact a
client, authenticate, sign, save or submit.
