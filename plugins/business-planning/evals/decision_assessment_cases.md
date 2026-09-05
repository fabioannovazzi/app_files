# Business Planning acceptance evaluation

Run these cases through either registered storage adapter. Use the same structured
case to check numerical and report parity through the other entry point. The
repository fixtures are synthetic and contain no client documents.

## Ordinary request with contradictory documents

Prompt: “Prepare a business plan from these files. Does it make sense to proceed?”
Use `tests/fixtures/business_planning/case.json` and its selected sources.

Expected assessment: redesign before full commitment. Explain accepted negative
EBITDA and the absence of demand and operating evidence. Compare a smaller pilot,
different operating/channel choices and postponement. Distinguish the early cash
shortfall from the positive final cash balance. Explain why financing does not
repair the operating loss. Do not treat reconciliation status as viability.

Expected report: recommendation and conditions before business analysis; relevant
profitability and cash charts inside the argument; source comparison and complete
provenance accessible in the appendix. The artifact is one business report, not
separate Vera and Clara perspectives.

## Ordinary idea-only request

Prompt: “I want to offer mobile bicycle repairs. Help me prepare a business plan
and decide whether to try it.” Use `tests/fixtures/business_planning/idea-case.json`.

Expected assessment: propose a limited test before a vehicle commitment. Distinguish
the convenience proposition from demonstrated willingness to pay. Explain repair,
travel, parts and rework constraints; specify a paid-booking trial and the operating
data needed to decide. Compare mobile service with grouped repair appointments.
The result stays provisional without fabricating a forecast, funding amount,
professional reviewer or market facts. No charts without calculated data.

## Review method

A model/professional reads the complete report and checks whether its recommendation
follows from the evidence, the questions are substantively answered or explicitly
unknown, alternatives are meaningfully different, and next steps are actionable.
Record concrete omissions and contradictions. Do not assign a numerical quality
score or declare semantic quality from section presence. Automated tests cover
arithmetic, references, withheld claims, provisional display, audience control,
report ordering and chart bindings. They are not a substitute for this reading.

For an established company, retain the same questions but anchor them in actual
customer retention, pricing, capacity, costs, cash obligations and the specific
investment or continuation decision. Do not infer viability from historical profit
or automatically recommend a startup-style pilot when the decision is different.
