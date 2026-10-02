> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

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
