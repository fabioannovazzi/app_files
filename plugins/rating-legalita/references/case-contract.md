# Case contract and provenance

Adapted from Francesco's `Vera_Rating_Legalita_2026.zip`, shared in
https://discord.com/channels/1550191335917625474/1555470084464578570/1555470267004756048
on 2026-10-02, and the subsequent channel review. The original 64-control
catalog and templates are reference material; their statements about prototype
status are historical. This implementation narrows execution to first attribution.

`schemas/case.schema.json` defines the input. `rating_case.py init` writes a
minimal valid case. The main additions to the supplied schema are an exact
`excerpt` in every evidence link, a `scope.source_current` review flag, and
restrictions preventing official results and external actions in this prototype.
Evidence `uri` is a relative UTF-8 file path inside the imported run inputs.
For PDFs, preserve the original and a reviewed extraction with page locators.
The script checks the extraction, not the visual PDF or OCR correctness.

T0 and every earlier snapshot are immutable when `--previous` is supplied.
Always supply the previous dossier on continuation; the tool cannot discover
an omitted prior dossier in another folder. New evidence must use new IDs;
do not repoint old evidence IDs to different bytes. The hash chain proves
record consistency, not authenticity or the identity of the reviewer.

The first-application checklist requires a professional decision (including
reasoned non-applicability) for all A01–A05, S01–S05, B01–B18 and C01–C12
controls. Include every expanded mandatory instance in
`scope.required_instance_ids`. The professional, not a script, determines
subject/event applicability and certifies completeness through
`scope.coverage_review`. Missing controls and uncovered included subjects
prevent a positive base status. Passing these mechanical checks does not
certify the legal completeness of the chosen scope.

For P01–P08, `verified` means a supported premium; `failed` means absent.
For P09, `verified/satisfied` means the deduction applies;
`failed/not_satisfied` means a reviewed absence of that deduction.
`not_applicable_reviewed` always requires a reason and evidence. Never mark
P09 verified merely because someone examined ANAC. P10 continuity is not used
for an initial application. The estimate excludes conditional scenarios and
does not turn unknown premiums into a promised future score.

The renderer derives current status and score from decisions. Input fields
`base_status`, `estimated_rating` and `status` cannot grant eligibility.
`ready_for_review` is documentary readiness, not a completed official form,
permission to send, professional certification or an AGCM award.

Source verification on 2026-10-02: the AGCM regulation and FAQ were opened
from the official site. The inherited source register preserves the original
author's retrieval claims for other references; refresh applicable references
on each real case. Renewal/calendar functions in `core_rating.py` remain
tested reference arithmetic and are not exposed as a complete renewal process.

## Anna's practical review, 2 October 2026

The changes below respond to the comment at
https://discord.com/channels/1550191335917625474/1555470084464578570/1555496326966415401.

`practice` records the mandate and data-governance review before a real pilot,
append-only event reviews, and actual professional time intervals. Required
review metadata and evidence hashes establish a recorded decision, not legal
adequacy, authenticity of a signature or authority to process judicial data.
Pre-intake and synthetic cases can leave prerequisites null. Real evidence is
refused without both reviews; the host may already have seen uploaded material,
so the skill requires the review before requesting or reading judicial sheets.

The event calendar uses qualified occurrence dates plus 30 calendar days. Unknown
or unreviewed events remain urgent questions; no deadline is inferred from the
date of discovery. A recorded receipt records someone else's actual transmission,
not an action by this helper. Events, event-review history and time records cannot
be rewritten when continuing with the prior dossier. New legal judgments require
new reviews and revisiting affected substantive controls. No automatic reminders,
portal filings, sanctions, retention deletion or permission changes are provided.

Primary sources checked on 2026-10-02: AGCM Regulation 31812/2026, Articles 12
and 21 (S01). Article 21(3) measures eighteen months from cessation of the obstacle's
legal relevance; paragraphs 4–5 govern premium changes separately. The calendar
does not decide those classifications or calculate that reapplication date.
For judicial-data qualification, see GDPR Articles 5, 6, 10, 13–14 and applicable
Italian law; the Garante's decision 10113493 and transparency guidance in decision
10009033 illustrate that a notice alone is insufficient and retention must be
purpose-bound. These sources do not establish this particular studio's authority:
https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/10113493
https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/10009033

Professional time is entered as actual timezone-aware start/end timestamps and
breaks, grouped by stage. No measured session means unknown time. The helper
rejects duplicate IDs, negative durations and overlapping intervals for one person.
It does not measure unrecorded work or infer profitability. The three document-led
pilot exercises remain distinct from tests on prequalified synthetic facts.
