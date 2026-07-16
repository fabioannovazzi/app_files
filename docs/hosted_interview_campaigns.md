# Hosted Interview Campaigns

Hosted interview campaigns are explicit, versioned briefs. They are separate
from outreach batches so a dated email run cannot silently determine or reuse
the wrong interview objective.

## IDs

- `interview_campaign_id` identifies the stable interview objective and brief,
  for example `commercialisti-ai-working-group-v1`.
- `campaign_id` in outreach identifies the dated sending batch, for example
  `italy-commercialisti-2026-07-12`.

Never reuse an `interview_campaign_id` after changing its meaning. Add a new
version instead. Exact ID lookup is intentional: an unknown ID fails rather
than falling back to another brief.

## Registered campaigns

| Interview campaign ID | Purpose |
| --- | --- |
| `professional-firms-ai-adoption-research-v1` | Comparative research on current AI use, limits, trust, and adoption barriers. |
| `clara-needs-research-v1` | Invited-user research on the Clara functions participants would use, improve, or add. |
| `commercialisti-ai-working-group-v1` | Commercialisti AI Working Group: understand what participants need, what AI provides well or poorly today, and the unmet gap. |

The Clara needs interview is intentionally not limited to consultants. It starts
with the first concrete task the participant would ask Clara to perform. It then
describes relevant current functions in plain language before asking which are
useful, which should improve, and which are missing. It does not begin with a
broad review of the participant's work or turn into generic AI-adoption research.

The Commercialisti AI Working Group uses this spine:

> Understand where commercialisti want AI to support their work, what they need,
> what AI currently delivers well or poorly, and the gap between the two—so the
> plugins can address real unmet professional needs.

Definitions live in `modules/hosted_interviews/campaigns.py`. They own the
purpose, context, priority dimensions, and boundaries. They intentionally do
not contain a fixed questionnaire; the Realtime interviewer remains adaptive.

## Preparing links

Authenticated preparers can list campaigns:

```text
GET /case-notes/api/voice/interviews/campaigns
```

They can prepare a participant link from one registered brief:

```text
POST /case-notes/api/voice/interviews/campaigns/{interview_campaign_id}/interviews
```

Example body:

```json
{
  "case_id": "participant-001",
  "participant_name": "Participant Example",
  "language": "it"
}
```

Outreach code must also pass `interview_campaign_id` explicitly whenever its
message contains `{interview_url}`. A queue row may reuse a URL only when the
stored and requested interview campaign IDs match exactly.

## Legacy records

Older records keep their embedded briefs. When they lack an explicit campaign
ID, the server labels them `legacy-unclassified-v1`; it does not assign a new
registered brief. A campaign change therefore requires new participant links;
existing links keep the copy and brief stored when they were created. Revoking
legacy links is a separate, deliberate data operation.
