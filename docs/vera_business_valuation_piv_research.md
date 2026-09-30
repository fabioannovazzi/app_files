# PIV primary-source inspection — 30 September 2026

Status: partial source inspection; professional review pending. This is an
engineering research note, not a release attestation, conformity assessment or
activation of a professional purpose. Code inspected at
`9674b8216d5f96525531734aa26b2eca1450a50f`.

## Sources and reading boundary

- [OIV publication page](https://www.fondazioneoiv.it/piv/), checked on
  30 September 2026: definitive 2026 edition, application from 1 January 2027,
  online consultation and restrictions on commercial reproduction.
- [Principles](https://www.sfogliami.it/fl/331518/bg1gy2s9by8gvfb8613s32r1pt7k2q9):
  printed pages **2–4, 29–42 and 65–72** read in the consultation viewer.
- [Rationale](https://www.sfogliami.it/fl/331519/cs65n8uchbdr71syt4q2ygz3vesmmh):
  printed pages **75–80** read. Its index was used only for navigation.

The Principles distinguish their authority from the illustrative Rationale
(p. 3). The application discussion also addresses retrospective review (p. 4).
Edition selection therefore remains an explicit professional decision.
Neither volume was downloaded or reproduced in the repository. These links,
reference identifiers and original engineering observations do not replace the
source. Full reading and applicable reuse permissions remain unresolved.

## Candidate references for the contributor's topics

The topic labels originate in the supplied pack. References below were read in
the definitive Principles, rather than inferred from an index. They are a
starting point, not an exhaustive mapping. Every row remains professionally
unreviewed; no reviewer identity or interpretation approval has been supplied.

| Pack topic | Inspected Principles references and printed pages |
| --- | --- |
| T01 Mandate / independence | I.2.1–I.2.3, p. 31; I.3.1, pp. 31–32; II.2.1–II.2.15, pp. 68–70 |
| T02 Value basis | I.6.1–I.6.4, p. 39; I.6.8–I.6.9, p. 42; II.2.9, p. 69 |
| T03 Dates / information | I.5.5, p. 37; II.2.10, p. 69; introduction, p. 4 |
| T04 Subject / rights | II.2.6, p. 69; subject scope only, rights-specific sections unread |
| T05 Information quality | I.5.1–I.5.11, pp. 35–38 |
| T06 Fundamental analysis / plan | I.5.6–I.5.10, pp. 37–38; plan-specific sections unread |
| T07 Methods | I.1.7, p. 31; method-specific sections unread |
| T08 Capital cost | I.17.15–I.17.17, pp. 65–66; earlier discount-rate section unread |
| T09 Terminal value | No topic-specific principle inspected |
| T10 Comparables / multiples | No topic-specific principle inspected |
| T11 Assets / intangibles | No topic-specific principle inspected |
| T12 Premiums / discounts | No topic-specific principle inspected |
| T13 Distress / liquidation | No topic-specific principle inspected |
| T14 Legal purposes | No purpose-specific principle inspected |
| T15 Synthesis | I.4.3, p. 33; II.4.2, pp. 70–71 |
| T16 Reporting / documentation | II.4.1–II.4.2, pp. 70–71; II.5.1–II.5.2, pp. 71–72 |
| T17 SME proportionality | I.4.5, p. 34; no general SME exemption inferred |
| T18 Review / limitations | I.3.2–I.3.7, p. 32; I.4.4–I.4.9, pp. 34–35; II.3.1–II.3.2, p. 70 |

Related Rationale comments read: II.2.1–II.2.15 (pp. 75–78),
II.3.1–II.3.2 and II.4.1 (p. 79, with II.4.1 continuing on p. 80),
II.4.2 and II.5.1–II.5.2 (p. 80). These remain explanatory references.
Prescriptive language must be recorded at individual-principle level during
the final mapping; a mixed section cannot receive one blanket classification.

## Observed implementation and engineering gaps

These are observations about our schema and code, not a translation of PIV.

1. `valuation-case.schema.json` has no structured standard identity, edition,
   adoption rationale or exception record. The skill asks for research, and
   `valuation_case.py` always returns `piv_conformity = not_assessed`.
   Proposed next increment: source-bound standards context, preserved as an
   explicit selection with no date-driven selector or automatic compliance flag.
   Reference anchors: introduction p. 4; II.2.2; I.2.2.
2. `mandateDetails` records commissioning party, competence, conflicts,
   recipients and dates. It lacks dedicated fields for expert/signatory identity,
   written mandate evidence, fees, deadline and amendments. `build_mandate`
   checks evidence and confirmation for existing fields but does not authenticate
   the professional. Proposed increment: extend this same evidence-record
   mechanism, retaining nulls and expiring dependent reviews on changes.
   Reference anchors: II.2.3–II.2.4, II.2.13–II.2.15.
3. Inputs use `fact`, `assumption` and `hypothesis`; claims add `opinion`.
   There is no separate assumption-characteristics record. Free-form limitations
   do not distinguish different origins of a restriction. Proposed increment:
   explicit model/professional classification and explanation, without a keyword
   classifier or a rule that treats filled fields as substantive approval.
   Reference anchors: I.4.4–I.4.7; I.5.8.
4. Benchmark dates are compared with `information_cutoff`; this is not a general
   source-availability assessment. The reviewed contract permits a later cutoff
   with explanation, but the basic mandate schema has no dedicated explanation
   record. Proposed increment: record availability reasoning and excluded
   evidence explicitly; retain historical source bytes. Do not silently rewrite
   dates or infer historical availability from retrieval time.
   Reference anchors: I.5.5; I.5.10–I.5.11.
5. `valuation_report.py` projects mandate fields and source-bound claims from
   one result. There are no dedicated records for outside experts or a reviewed
   ESG relevance decision. The canonical package does not create a separately
   qualified report extract. Proposed increment: explicit optional report
   context with source dependencies, then the same fields in every output.
   Reference anchor: II.4.1–II.4.2.
6. Archive runs retain receipted sources and immutable outputs. This does not
   establish a legally appropriate retention period or a complete record of
   correspondence and material supplied outside the run. Proposed increment:
   review the engagement's actual retention and correspondence workflow with
   the responsible professional. Reference anchors: II.5.1–II.5.2.

Existing evidence includes tests for missing mandate evidence, changed mandate
dependencies, separate conclusion acceptance, source tampering, audience changes,
report replay and immutable archive runs in `test_business_valuation.py`.
They establish software behavior only. No tests or release gates were rerun or
cleared by this document-only research checkpoint.

## Engineering follow-up — 30 September 2026

The subsequent local implementation addresses the record-keeping mechanisms in
gaps 1 and 2: explicit source-bound standards/edition/reason/departures and five
additional engagement fields. Missing information stays incomplete; changing it
expires dependent reviews. The numerical result is unaffected, and conformity,
professional identity and purpose activation remain unassessed. This is not an
approved interpretation of the cited principles. See the engagement-and-standards
checkpoint in `vera_business_valuation_implementation.md` for 623 passing tests,
95.68% component coverage and the synthetic document/archive verification.
Gaps 3–6, unread sources, individual-principle classification and qualified review
remain unresolved. The historical observations above refer to the inspected
`9674b8216d5f96525531734aa26b2eca1450a50f` code checkpoint.

## Remaining decisions

P0-01 remains open. Finish the unread relevant Principles and Rationale sections;
complete the individual-principle mapping, original interpretation, implementation
and test link; resolve applicability and terminology questions with an identified
qualified reviewer. P0-02 still requires review for each purpose to be activated.
All 21 purpose profiles retain their existing development-only state.
The later owner approval authorized the bounded engineering release-metadata corrections and public PR update; those are now applied. This does not resolve the substantive PIV or professional-review work described here.
