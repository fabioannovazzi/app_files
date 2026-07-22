---
name: interview
description: "Prepare and operate Clara-hosted external voice interviews: select an exact versioned research campaign or define a scoped one-off case interview, create an expiring no-login participant link, check its status, and retrieve the completed JSON bundle and post-interview quality review. Use when the user asks to interview a client, stakeholder, expert, research participant, or other external respondent through a hosted browser link, or asks to retrieve or review that interview's result. Do not use for interviewing the user in chat, advisor voice debriefs, uploading or transcribing existing recordings, bulk outreach or email campaigns, or importing Hosted Voice bundles."
---

# Interview

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or another static-site folder. Keep receipts, briefs,
bundles, reviews, and `codex_run_review.md` in the user's project/output folder.

Use this skill for the external-participant workflow. An authenticated preparer
defines the brief and creates a bearer link; the participant opens that link
without signing in and speaks with Clara's adaptive browser interviewer for up
to 15 minutes. This is separate from `transcribe`, which captures or imports an
advisor discussion or existing recording.

## Boundaries

This skill owns:

- selecting one exact registered campaign or drafting one scoped custom brief;
- choosing `case_interview` or `research_interview` from the intended output;
- creating a participant-specific expiring link only when the user asks;
- checking a known link's status;
- retrieving its JSON bundle and post-call quality review before expiry;
- handing the retrieved evidence to the main `clara` case workflow only when
  the user explicitly asks to add it to a case.

It does not own:

- interviewing the user in chat;
- consultant debriefs, uploaded recordings, or Hosted Voice bundles—use
  `transcribe`;
- deck changes from spoken feedback—use `deck-correction`;
- bulk outreach, invitation email, campaign-registry changes, revocation,
  raw-media download, or cross-interview synthesis;
- treating the generated review as proof that every statement is correct.

The participant URL is a bearer credential. Show it to the requesting user, but
never send it to another person or mailing list unless the user explicitly asks
for that external action. Keep it in the private `0600` receipt written by the
helper; never put the URL/token, authentication cookies, or magic links directly
in command arguments, shell history, ordinary logs, or source files.

## Interview Modes

Use `case_interview` when the output should represent one situation deeply:
context, chronology, constraints, decisions, risks, bottlenecks, and unresolved
questions. Use `research_interview` when the output must preserve natural
conversation while covering common dimensions well enough for later comparison.

Do not turn either mode into a fixed questionnaire. A custom brief supplies the
purpose, context, priority topics, prepared questions, red flags, and boundaries;
the server-side interviewer decides how to cover them adaptively.

Supported configured languages are `it`, `en`, `fr`, `de`, and `es`. The participant
page uses microphone audio. Do not promise screen capture or raw-media download.

## Authenticated Helper

Run commands from the Clara plugin directory. Keep the magic link or Cookie
header in a temporary local file with restrictive permissions. Prefer the magic
link file; delete the secret file after the authenticated operation.

Check the plugin environment before using the helper:

```bash
python scripts/check_dependencies.py
```

List the registered versioned campaigns:

```bash
python scripts/manage_hosted_interview.py \
  --magic-link-file <private-magic-link.txt> \
  list-campaigns --output <project-output-folder>/interview_campaigns.json
```

The currently registered campaigns are returned by the server. Never guess an
ID, silently fall back to another brief, or reuse an ID after its meaning has
changed.

Prepare one participant link from an exact campaign:

```bash
python scripts/manage_hosted_interview.py \
  --magic-link-file <private-magic-link.txt> \
  prepare-campaign <exact-campaign-id> \
  --case-id <non-sensitive-participant-id> \
  --participant-name "<participant>" \
  --language it \
  --output <project-output-folder>/hosted_interview_receipt.json
```

For a one-off interview, Codex writes a private brief JSON and submits it:

```bash
python scripts/manage_hosted_interview.py \
  --magic-link-file <private-magic-link.txt> \
  prepare <project-output-folder>/hosted_interview_brief.json \
  --output <project-output-folder>/hosted_interview_receipt.json
```

The custom brief uses the server contract:

```json
{
  "interview_campaign_id": "client-operations-interview-v1",
  "case_id": "participant-001",
  "case_name": "Operations discovery",
  "participant_name": "Participant name",
  "client_project": "Project label",
  "interview_title": "Operations interview",
  "interviewee_role": "Operations lead",
  "interview_mode": "case_interview",
  "language": "it",
  "purpose": "Understand the current operating bottlenecks.",
  "participant_intro": "A short participant-facing explanation.",
  "background_context": "Private context for the interviewer.",
  "hypotheses_to_test": [],
  "priority_topics": [],
  "questions": [],
  "red_flags": [],
  "boundaries": ["Do not ask for confidential client details."],
  "expires_in_hours": 168
}
```

The custom campaign ID must be a lowercase, hyphenated, explicitly versioned
identifier ending in `-v1`, `-v2`, and so on. Treat `participant_name`,
`case_name`, `interview_title`, and `participant_intro` as participant-visible.
If `participant_intro` is empty, the public page falls back to `purpose`, so the
purpose must also be participant-safe in that case. The unauthenticated status
endpoint exposes `case_name` and `interview_title`. Keep all of those fields
non-sensitive; only the remaining brief fields are private interviewer context.
The helper restricts both the input brief and output receipt to local `0600`
permissions.

If no authentication material is available, the helper can request a magic
link and prompt for it:

```bash
python scripts/manage_hosted_interview.py \
  --request-magic-link <authorized-email> list-campaigns
```

Do not claim link creation succeeded until the server returns `public_url`,
`expires_at`, and `interview_campaign_id`.

## Completion and Retrieval

Check a known participant link without putting its bearer token in the command:

```bash
python scripts/manage_hosted_interview.py status \
  --receipt <project-output-folder>/hosted_interview_receipt.json \
  --output <project-output-folder>/hosted_interview_status.json
```

If no receipt exists, save the participant URL by itself in a private local file
and use `--participant-link-file <private-link.txt>`. Never paste it as a
positional command argument.

Statuses include `ready`, `started`, `completed`, `failed_technical`,
`incomplete`, and `unusable`. An unchanged status is not an error. Do not create
a replacement link unless the user asks or the known link cannot be retried.

After completion, retrieve the bundle and review before the bearer link expires:

```bash
python scripts/manage_hosted_interview.py \
  --magic-link-file <private-magic-link.txt> \
  bundle --receipt <project-output-folder>/hosted_interview_receipt.json \
  --output <project-output-folder>/hosted_interview_bundle.json

python scripts/manage_hosted_interview.py \
  --magic-link-file <private-magic-link.txt> \
  review --receipt <project-output-folder>/hosted_interview_receipt.json \
  --output <project-output-folder>/hosted_interview_review.json
```

The bundle contains the prepared record, completion data, current-run events,
transcript material, media metadata, and any generated review. It is not a ZIP
and does not contain raw audio or video bytes. The review should distinguish
evidence-backed claims, uncertainties, contradictions, missed opportunities,
and follow-up questions. Inspect the transcript evidence before repeating any
review conclusion.

There is no automatic hosted-interview-to-case importer. If the user asks to
use the result in a Clara case, preserve the downloaded JSON as source material,
then use the main `clara` workflow to index and interpret it. Do not pass it to
the Hosted Voice bundle importers; the schemas are different.

## Codex-Native Run UX

Use a short checklist covering brief selection, participant fields,
authentication, link creation, status, retrieval, and handoff.

Before creating a link, show a compact Run Intake table with interview mode,
campaign or custom brief, participant, language, expiry, boundaries, receipt
folder, and whether any external sending was requested. Use a Decision Table
only for unresolved material choices such as case versus research mode, a
missing exact campaign ID, an ambiguous participant-facing introduction, or a
boundary that materially changes the interview.

Default output policy: create one participant link plus a private receipt, then
retrieve a bundle and quality review only when the interview completes or the
user asks. These are not choices to propose when the user asked for the normal
hosted-interview lifecycle. Creating a participant link is the approval
checkpoint; sending it to someone is a separate external action and requires
explicit authorization.

Before write-heavy or external work, show an execution checkpoint naming the
authenticated endpoint, non-secret inputs, expected receipt, and external side
effect. End with an Artifact Card listing the participant link, expiry, status,
receipt, bundle, review, and any unavailable artifact. Create
`codex_run_review.md` only when the run is blocked or exposes a repeatable gap.
Never edit generated ZIPs during a run.
