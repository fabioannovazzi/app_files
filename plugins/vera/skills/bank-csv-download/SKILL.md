---
name: bank-csv-download
description: Download original bank transaction CSVs through computer use and 1Password in the operator's existing browser, including Intesa Sanpaolo, UniCredit, BNL, Sella and BCC RelaxBanking. Use for requests to download bank movements before accounting; distinguish this acquisition from reconciliation of already supplied files.
---

<!-- VERA_WORK_CONTINUITY_BEGIN -->
## Work continuity

Before substantive work, read `../vera/references/work-continuity.md` (from the
Vera root skill, `references/work-continuity.md`). Resolve prerequisites upfront,
retain passed choices and the exact job context, and recover failed operations
without discarding progress or making the user repeat settled setup. This also
applies to direct invocation, standalone work and studio-wide workflows.
<!-- VERA_WORK_CONTINUITY_END -->


<!-- VERA_WORKFLOW_USAGE_BEGIN -->
## Task usage and user feedback

Before substantive work, follow `../vera/references/workflow-usage.md`: start one
retained task UUID for the primary user process (including AI-led work), reuse
it across helpers/resumption, and record only observed outcomes. Discover the
native `vera_incident_host_link` tool, including deferred tools, and verify the
same run's Computer ID on the server. Privacy reporting applies only to the fixed pipeline list in
`../vera/references/selective-reporting.md`, using the exact Studio Archive run.
Studio Archive start and terminal writes automatically create a local report for
every run of those pipelines, including full exposure or incomplete observations.
The server proof binds the report hash to the same Archive run and existing Vera
userID. No agent-authored phase file or separate usage-task receipt link is needed.
Other pipelines and chat-only tasks do not get this report. After delivery ask once for the user's 1–5 stars and optional
comment; never infer a score. Studio Archive is infrastructure, not another rated
process. Synthetic/agent tests are marked and excluded. Start and record deliver
only the retained task's events. Retry with
`workflow_usage.py flush --run-id <retained-uuid>`; unrelated queued events do not
block this task. The shared contract applies even on direct skill invocation
and on both Codex and Cowork.
<!-- VERA_WORKFLOW_USAGE_END -->


<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->
## Connected studio knowledge

When the user or an adopted studio instruction requests relevant repository
evidence, read `../vera/references/connected-studio-knowledge.md` before the
dependent work, including direct specialist invocation. Use only callable host
search/read tools; preserve citations and this workflow's qualification gates.
Without a repository, continue ordinary work. Studio skills remain independently
invoked by the user; Vera does not dispatch them.
<!-- VERA_CONNECTED_KNOWLEDGE_END -->

# Scarica i CSV bancari

This is Vera’s direct computer-use acquisition route. A request such as
“Vera, scarica i CSV della banca” selects it without a package download,
separate project, tutorial, developer handoff or recorded browser capability.
Read `references/banks.md` only for the selected bank’s public entry and portal
variants. Intesa Sanpaolo, UniCredit, BNL, Sella and BCC RelaxBanking are initial
targets, not a claim of live-verified bank coverage. Establish the actual export
path in the operator’s browser; do not block an authorized attempt because the
bank has not been tested before.

## Scope and browser

The requested result is the original CSV of booked account movements for an
identified client, account and inclusive period. Do not substitute a PDF
statement, scrape rows into an invented CSV, initiate payments, register entries
or change bank settings. If CSV is unavailable, retain the observed limitation
and ask only about an alternative that materially changes the result.

Use the host's documented computer-use controls in the operator's existing
browser profile. The current model interprets screens and chooses navigation;
do not add bank-specific guessed selectors or a second model API. Never pin a
Codex/model/OS version. Verify the actual browser and local-file capabilities.
Follow the current host's tab retention/handoff documentation.

The operator chooses the model in their host, including Terra 6.1 or another
computer-use-capable model. Do not ask for a particular model, change it, add a
separate model API or require a pre-recorded Playwright procedure. The current
model uses the documented computer-use surface directly, observing the actual
screen after meaningful actions. This route does not invoke Vera's portable
capability executor or claim that its qualification receipts were produced.

Resolve the selected client's account, exact portal variant and period from
the user's request or existing case before authenticated work. A bank brand
does not identify the portal or client. Ask only for missing scope, never for
credentials. Client authority already established in the conversation persists.
Resolve client/account/period with the current operator in their own session.
A developer or another user does not need to supply or receive those details.

## 1Password authentication

Use the official 1Password browser extension's matching Login and Autofill.
The instructions here are self-contained: no separately installed connector
or skill is required. The extension route needs no CLI or access to raw secrets. If several saved Logins match the site,
select by the client specified by the operator, not by the first suggestion.

The operator unlocks the vault and completes bank MFA on their device. If the
current browser controls cannot operate extension UI, hand off just Autofill;
resume the same task after authentication. Do not install an extension, connect
a vault or change 1Password settings as an implicit part of a download.

Never read or emit password fields, PINs, OTPs, clipboard values, CLI secret
output, cookies, browser storage or reusable session URLs. Do not capture a
login screen containing credentials. Credentials go from 1Password directly to
the bank, not through the model. Verify the authenticated client/account
indicator; filled controls alone are not a successful login.

## Export and local evidence

Vera performs routine navigation and checks without repeated confirmation.
Before the export, verify the active client's account, currency, booked versus
pending scope, date filter semantics, any transaction-type filters, pagination
and export limits. Derive these from the actual portal, not from the bank list.
Select the requested whole period; split into explicit subperiods only when
needed by an observed portal limit. Preserve a coverage list for every account
and subperiod, including zero-movement periods.

Resolve the installed Vera root as `../..` from this skill directory. Use its
existing managed Python and run `<Vera>/scripts/check_dependencies.py` before
the helper. Do not ask the operator to open a project, run a shell command or
install a package. For each individual export, invoke the helper immediately
before the export click, using a fresh private directory outside Git and
published folders. Create its parent locally within existing host permissions.
If helper persistence is unavailable, continue the authorized browser download
and deliver its useful original, explicitly recording missing retention
evidence rather than substituting a claimed pass.
The model prepares the request JSON; the accountant does not write JSON or run
commands. It contains exactly these fields:

```json
{
  "bank": "Intesa Sanpaolo",
  "portal": "Inbiz",
  "client": "local client reference",
  "account": "local account reference",
  "date_from": "2026-10-01",
  "date_to": "2026-10-31"
}
```

```sh
python <Vera>/scripts/bank_csv_download.py start --request <private-request.json> \
  --downloads <actual-browser-download-directory> --run <fresh-private-run>
```

The helper is included in Vera; the user supplies no script path. Reuse the browser's actual
download directory; do not change browser settings. The helper snapshots names
and file identity only, without reading existing bank files. Finish after the
download has completed:

```sh
python <Vera>/scripts/bank_csv_download.py collect --run <same-private-run>
```

Avoid unrelated downloads during this interval. A single new file alone cannot
prove its bank origin: correlate it with the observed export action and the
subsequent account/period/content review. This is directory-correlated evidence,
not a browser-event or bank-signed receipt.

The helper copies only a unique new, stable, regular file, with exclusive writes
and requested private file modes, retaining the original bytes and SHA-256.
POSIX modes are checked in the local tests; Windows inherits the private parent
folder's permissions, and this helper does not audit Windows ACLs. It does
not delete the source. Changed/overwritten existing files, disappearing old
partial files, concurrent arrivals, symlinks and unfinished downloads are
reported without claiming a verified export. Each collection attempt has its
own durable report. An interrupted acquisition remains resumable in the same
run. A collected original is reused on retry, not exported again silently.

The deterministic checks prevent attributing an unrelated/preexisting or still
changing file to the export; they do not determine bank account or CSV meaning.
`original_retained` proves local file retention, not population completeness,
correct account, format validity or successful accounting import.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`. Do not transmit bank CSVs, screenshots or the client coverage report in technical feedback.

## Review and delivery

Review the export's actual format and header. Read CSVs locally with the
observed encoding, separator and preamble. Do not convert Excel files merely
because the filename suggests CSV. Have local code return only needed metadata:
record counts, first/last booked date and exact totals using reviewed column
meanings. Keep all original rows, including same-date/same-amount payments;
never deduplicate by description/date/amount alone.

Compare those local results with independent portal evidence when available.
Document date-filter meaning, source count/totals, account identity and the
export's handling of pagination. Counts alone cannot prove the right account.
Zero rows are acceptable only with observed no-movement evidence for that scope.
If the portal gives no independent count or total, disclose the check that
could not be made; do not invent a balanced reconciliation or an expected count.

Maintain a private Markdown coverage report across all requested accounts and
periods: request, actual export scope, original-file link, bytes/hash, observed
checks, unresolved exceptions, authentication handoffs and recoveries. Create
and update this report even for partial results. Report separately: file
acquisition, content/coverage review, privacy reporting, and bank acceptance.
A missing privacy report must not suppress a useful CSV or make acquisition fail.
No automated technical check is professional approval.

Deliver the original files and report, with missing scopes first. Download does
not authorize sending data to a gestionale or starting accounting registration.
Keep records local; no support submission, remote upload or publication follows
from this workflow. Later reconciliation is a separate requested workflow.

Track representative live cases for bank acceptance: ordinary and empty
periods, multiple accounts/clients, date/export limits, expired authentication,
interruption/resumption and a changed portal screen. Preserve all encountered
blocks and their recovery. Synthetic file tests prove only local mechanics;
they do not establish bank compatibility or unattended operation.

## Quali dati arrivano al modello

The selected host model may receive the user's bank/client/account references
and requested dates, plus the bounded authenticated browser observations needed
to select the account, filters and export. Screenshots or DOM observations can
contain names, account identifiers, balances and visible transaction rows.
This is not a local-only model workflow and no automatic anonymization is claimed.

The helper uses no network. Directory snapshots, original bytes and full private
request remain local. Its terminal response contains only collection status,
byte count, SHA-256 and the local report path. It does not emit filenames of
unrelated downloads or transaction contents. Do not print snapshots or full CSVs
into chat. Only inspect content in model context when necessary for the requested
work, describing the actual additional data read. 1Password secrets and bank MFA
are outside the model path. Host retention/training settings depend on the
operator's account and have not been audited by this workflow.
