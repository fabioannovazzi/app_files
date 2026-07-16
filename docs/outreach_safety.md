# Outreach safety workflow

Use this workflow for cold outreach batches.

## Morning automation

The active Codex automation for the `mailing` thread is only a queue sender.
It runs Monday-Friday at 08:00 local time and does not run on weekends.
Skipped days are not caught up later.

The morning automation must not discover firms, browse the web, scrape pages,
run Playwright, or regenerate the lead bank. It consumes only existing approved
queue rows from:

- `data/outreach/queues/italy.csv`
- `data/outreach/queues/swiss-romande.csv`
- `data/outreach/queues/swiss-german.csv`
- `data/outreach/queues/uk.csv`
- `data/outreach/queues/italy-organization.csv`

A queue row is sendable only when `status` is blank or `queued`. Rows with
`prepared`, `sent`, `blocked_duplicate`, `blocked_invalid_email`, `rejected`,
or `unsubscribed` are not sendable. If a queue contains fewer than `10`
sendable rows, Codex sends the available rows and reports the shortage. It does
not discover replacement leads during the morning run.

Before a row is prepared, Codex computes the normalized email hash and checks
`data/outreach/outreach_ledger.jsonl`. If the hash already exists with a
blocking status, the row is marked `blocked_duplicate`, the raw email is
scrubbed from the queue, and no mail is sent to that address.

After Gmail confirms a send, Codex records `status=sent`, `email_hash`,
`quota_key`, `quota_day`, campaign/template metadata, Gmail message ID, and
`sent_at` in `data/outreach/outreach_ledger.jsonl`. After deleting the outreach
copy from Gmail Sent, it also records `gmail_sent_deleted_at`. Raw recipient
emails are then removed from sent queue rows and sent batch files.

First-touch outreach emails must not include clickable links or attachments
unless the operator explicitly approves a new template. They should ask interested
recipients to reply so the operator can send the relevant beta details separately.

Italian individual-recipient templates must start with `{salutation}`. For
Italian professional-register rows with a usable person name, Codex renders it
as `Gentile Dott. {Cognome},` using `Dott.` for every gender. If no usable
person name is available, Codex renders `Buongiorno,`.

At the end of every scheduled run, Codex sends a control email to the operator
address configured for that deployment. Subject format:
`Mparanza outreach YYYY-MM-DD: SENT / PARTIAL / SKIPPED / FAILED`. The body
must state whether outreach was managed, per-region sent counts, shortages,
skipped/blocked reasons, Gmail delete failures, scrub status, and the ledger
path updated. It must not include raw recipient email addresses. The control
email is not outreach, does not count toward quota, and must not be deleted by
outreach cleanup.

If Gmail send/delete is unavailable, Codex stops without sending outreach. If
possible, it sends the operator a `FAILED` control email; otherwise it leaves the
failure report in the `mailing` thread.

## Lead-bank build

Lead-bank discovery is separate from the morning automation. Run it explicitly
when a queue needs replenishment.

Discovery is source-first:

1. Identify public registries, professional directories, public registers,
   association directories, and official listing pages for the target market.
2. Check the source terms before using contact data. If a source prohibits
   advertising or marketing use, use it only for permitted research/validation
   or skip it for outreach.
3. Scrape the source pages first with `scripts/build_outreach_lead_bank.py`.
   Use `--use-playwright` only when the source requires browser rendering.
4. Only after public source pages are exhausted should Codex inspect individual
   firm websites to find a public client-facing contact route.

Useful public source families include:

- Italy: CNDCEC `Albo Nazionale` searches for registered members and società,
  plus territorial ODCEC albo pages.
- UK: ICAEW `Find a chartered accountant` and ACCA `Find an accountant` /
  `Find an ACCA accountancy firm`.
- Switzerland: FIDUCIAIRE|SUISSE / TREUHAND|SUISSE member directories, the RAB
  public register for licensed audit providers, Zefix/cantonal commercial
  registers to identify firms, and firm websites for public contact pages when
  the register itself does not publish a usable client-facing email.

The lead-bank builder appends only new rows to the queue. It skips any email
whose normalized hash is already in the ledger or already in the queue. The
durable no-repeat rule is the normalized email hash, not firm domain.

For the ODCEC/Ordini organization track, `italian_odcec_organization_ranking_*.csv`
is only a priority list. The morning automation sends only from
`data/outreach/queues/italy-organization.csv`, which can be populated from the
CNDCEC territorial-order detail pages with
`scripts/build_italy_organization_queue.py`.

Example source-first lead-bank run:

```bash
source .venv/bin/activate
python scripts/build_outreach_lead_bank.py \
  --region uk \
  --url 'https://www.icaew.com/about-icaew/find-a-chartered-accountant' \
  --url 'https://www.accaglobal.com/gb/en/member/find-an-accountant.html' \
  --source-note public-directory
```

For JavaScript-rendered directories:

```bash
source .venv/bin/activate
python scripts/build_outreach_lead_bank.py \
  --region uk \
  --url 'https://find.icaew.com/?do=register' \
  --source-note public-directory-playwright \
  --use-playwright
```

## Queue and ledger rules

The ledger stores recipient hashes, quota key, language, quota day, campaign,
variant, source metadata, and optional locale metadata. It must not store raw
email addresses.

The queue may temporarily hold raw emails only before send or manual rejection.
After a row is sent or blocked as a duplicate, its raw email is scrubbed.

The outreach prep code enforces:

- maximum `10` sent records per country/market quota key per day;
- maximum `5` sent records per day for the separate `italy-organization`
  quota key used for ODCEC/Ordini outreach;
- duplicate prevention by normalized recipient hash;
- message variant tracking with `variant_id`;
- region-specific product URL tracking as metadata for reply follow-up.

## Local helpers

`scripts/run_outreach_automation.py` is a local cold-test layer for queue
selection, templates, quotas, hashes, holidays, and batch output. It does not
discover firms and does not send/delete Gmail messages by itself.

```bash
source .venv/bin/activate
python scripts/run_outreach_automation.py
```

Legacy local scheduler note:

The local macOS LaunchAgent is not the active Codex automation and should not
be installed for this weekday mailing workflow unless explicitly requested. It
can only run local helper scripts; it cannot use the connected Gmail workflow by
itself.
