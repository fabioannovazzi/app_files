# mparanza_app

Plugin-first professional-work repository with a narrow FastAPI hosted-services
boundary and a Polars-first backend.

## Table of Contents
- [Overview](#overview)
- [Codex Plugins](#codex-plugins)
- [OpenAI Build Week 2026: Vera](#openai-build-week-2026-vera)
- [Key Features](#key-features)
  - [Polars-first backend](#polars-first-backend)
  - [PDF journal ingestion](#pdf-journal-ingestion)
  - [Period aggregators](#period-aggregators)
  - [Explanation and context columns](#explanation-and-context-columns)
  - [Journal ingestion CLI](#journal-ingestion-cli)
  - [Bank statement QA & debug](#bank-statement-qa--debug)
  - [Add Attributes workflow](#add-attributes-workflow)
- [Research and entry-check workflows](#research-and-entry-check-workflows)
- [Development Setup](#development-setup)
- [Running the Project](#running-the-project)
- [Deployment](#deployment)
- [Testing](#testing)
- [Session Maintenance](#session-maintenance)
- [Contributing](#contributing)
- [License](#license)

## Overview

Vera, Clara, and Lucia run primarily as Codex plugins. Their deterministic Python
components process documents and structured data, build analyses, and create
reviewable outputs locally. FastAPI is limited to the public site and the
hosted services that require a server boundary: authentication, interviews,
voice capture, Attribute Reporting/Brand Fit evidence exchange, and plugin
change requests.

## Codex Plugins

The Codex plugin source is maintained in this repository and licensed under
the [GNU Affero General Public License v3.0](LICENSE). Every plugin manifest points to the canonical
[GitHub repository](https://github.com/fabioannovazzi/app_files), and each
plugin README links directly to its source folder.

- Clara and reporting: [Clara](plugins/clara), including its internal [Reporting Engine](plugins/clara/modules/reporting-engine), plus [Attribute Reporting](plugins/attribute-reporting), [Distribution Analysis](plugins/distribution-analysis), [Funnel Analysis](plugins/funnel-analysis), [Mix & Contribution Analysis](plugins/mix-contribution-analysis), [Period Comparison](plugins/period-comparison), [Scatter & Bubble Analysis](plugins/scatter-bubble-analysis), [Set Overlap Analysis](plugins/set-overlap-analysis), [Statement Analysis](plugins/statement-analysis), and [Variance Analysis](plugins/variance-analysis).
- Vera and accounting: [Vera](plugins/vera), [Open-item Reconciliation](plugins/open-item-reconciliation), [Check Entries](plugins/check-entries), [New Client](plugins/new-client), [Concordato Preventivo](plugins/concordato-plan-review), [Deep Research Validator](plugins/deep-research-validator), [Journal-Bank Reconciliation](plugins/journal-bank-reconciliation), [Journal Sampling](plugins/journal-sampling), [Previdenza INPS](plugins/previdenza-inps), [Prompt Optimizer](plugins/prompt-optimizer), [Registro Imprese e SARI](plugins/registro-imprese-sari), and [Report Builder](plugins/report-builder).
- Lucia for independent lawyers and law firms: [Lucia](plugins/lucia), starting with the shared [Prompt Optimizer](plugins/prompt-optimizer) and [Deep Research Validator](plugins/deep-research-validator) workflows.

## OpenAI Build Week 2026: Vera

[Vera](plugins/vera) is a pre-existing, review-first Codex plugin for accounting
practices. The work submitted for OpenAI Build Week is the electronic-invoice
evidence workflow added after the event began and committed on July 17, 2026.
It adds:

- in-memory Italian FatturaPA XML/ZIP parsing;
- unique invoice matching only when one candidate agrees on at least two
  independent signals among invoice number, amount, date, and party;
- provenance for local exports produced by an authorized accounting-system
  connector, without accepting provider credentials;
- targeted PDF fallback only for sampled entries that remain unresolved; and
- local review payloads, audit artifacts, and reviewer-action persistence.

The extension was developed in Codex with `gpt-5.6-sol`. Build evidence:

- Codex session: `019f7116-974f-7381-a934-e67739047504`
- qualifying commit: [`05b99c52d263ef81104e44f8bd85fa66a0c6de33`](https://github.com/fabioannovazzi/app_files/commit/05b99c52d263ef81104e44f8bd85fa66a0c6de33)
- implementation: [Check Entries](plugins/check-entries)
- synthetic test data: [examples/vera-build-week](examples/vera-build-week)
- primary Vera install page: [OpenAI plugin listing](https://chatgpt.com/plugins/plugins_6a57ac5ce65c8191ae7bd0a51160eb7d)

GPT-5.6 was the Codex development collaborator; Vera does not pin GPT-5.6 as
a runtime model or call the OpenAI API directly. Deterministic Python owns XML
parsing and mechanically verifiable comparison. Codex owns the conversation,
non-inferable mapping questions, review explanation, and professional handoff.
The commercialista retains judgment and responsibility.

### Reproduce the synthetic Build Week flow

The source path below was verified on macOS with Python 3.12. The deterministic
check can run without an accounting-system account or customer data. Node.js is
needed only to open the local MCP review workbench.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r plugins/check-entries/requirements.txt

demo_dir="$(mktemp -d)"
python plugins/check-entries/scripts/inspect_entries.py \
  examples/vera-build-week/journal.csv \
  examples/vera-build-week/invoice_INV-42.xml \
  --output-dir "$demo_dir/inspection" \
  --language en \
  --document-language it
python plugins/check-entries/scripts/run_checks.py \
  examples/vera-build-week/journal.csv \
  examples/vera-build-week/invoice_INV-42.xml \
  --output-dir "$demo_dir/checks" \
  --recipe "$demo_dir/inspection/suggested_recipe.json" \
  --language en \
  --document-language it
python scripts/serve_review_workbench.py \
  "$demo_dir/checks" \
  --plugin check-entries
```

Expected result: entry `1001` is supported by a unique FatturaPA match and
entry `1002` remains visibly unresolved with a targeted document request.

## Key Features

### Polars-first backend

All data manipulation uses the [Polars](https://pola.rs) library. Lazy
`DataFrame` operations keep memory use low and compatibility patches are applied
at startup via `modules.polars_compat`.

Avoid relying on implicit truth testing when working with Polars objects:

```python
if df.height > 0:  # instead of `if df`
    ...
```

Marimekko charts run lazily as well. Helper functions like
`prepare_data_for_marimekko` accept `LazyFrame` inputs for efficient pipelines.

### PDF journal ingestion

`parse_journal` automatically detects header rows in extracted tables. It scores
candidate lines against keywords (for example `"Attivita"` or
`"Data registrazione"`) and merges multi‑line headers. Detection now recognises
split words such as `"Descrizione"` and `"dell'operazione"` across adjacent
rows. Blank cells are normalised to `col_0`, `col_1`, … to avoid crashes.
Override detection when necessary:

```python
from modules.process_pdf_journal.logic import parse_journal

df = parse_journal(pdf_bytes, header_row=3)
# Merge two header lines
parse_journal(pdf_bytes, header_row=(3, 4))  # or "3,4" in the UI
```

`parse_journal_any` now accepts any non‑empty DataFrame, allowing tiny tables to
surface. When table and layout strategies fail, a posting‑group fallback buffers
lines from the row number until the next amount, inheriting the header's date,
causale, activity and branch. Amounts are positioned with
`infer_dare_avere_x_positions` to decide between Dare and Avere. If that also
fails, a simpler text‑mode parser scans lines like
`"1 100 Cassa operazione 1.234,56"` and returns a frame with a single `amount`
column. Account codes are recognised with
`ACCT_PATTERN = r"(?P<conto>\d+(?:\s*[*/.-]\s*\d+)+)"`, which handles
segments separated by slashes, dashes, dots or asterisks (for example
`"27 / 5 / 3"` → `"27/5/3"`). If the description cannot be reliably split into
account and operation parts it is kept intact and can be mapped later in the UI.
Amounts and dates are parsed with the same `parse_amount` and `parse_date_str`
helpers used for Excel ingestion, ensuring numeric and date consistency across
formats. Ambiguous Series truth values are logged and skipped, ensuring the UI
never receives the exception.

### Explanation and context columns

Validation checks return a `status` field and an `explanation` column. When the
status is `mismatch` the explanation highlights the reason (amount mismatch,
beneficiary mismatch, and so on). Extra context columns (for example
`source_page` or `source_text`) provide additional clues for manual review.

### Journal ingestion CLI

A command‑line interface is available for batch PDF parsing:

```bash
journal-parse input.pdf --output out.csv --auto
```

### Bank statement QA & debug

`bank_ingestion.check_statements` estimates how many transaction‑like rows were
found in a PDF and how many were extracted. Coverage reports are stored under
`caches/bank_extract_reports/`. Journal-to-bank reconciliation for customer work
is now handled by the Codex Journal-Bank Reconciliation plugin rather than the
web application.

Transaction descriptions are cleaned before fuzzy matching. Prefixes such as
"BONIFICO o/c" or "DISPOSIZIONE A FAVORE DI", ABI‑CAB numbers, CIG/CUP codes,
dates, amounts and standalone digits are stripped. For customer reconciliation
runs, the Codex plugin uses deterministic scripts and Codex review rather than
direct API-model calls from application code. See `docs/caches.md` for cache
root selection and file locations.

Advanced reconciliation options
-------------------------------

- Grouping guardrails to keep matching interactive on dense days:
  - Group limit default is 2 (pairs); triples are optional.
  - Group candidates cap, max combos per bank, and per‑bank time budget (ms).
- AI enhanced matching toggle: enable/disable LLM normalisation with absolute and
  percentage thresholds for auto‑escalation. Defaults bias toward manual review
  on small datasets.

Staged reconciliation sequence
------------------------------

Hosted services
---------------

The FastAPI service supports authentication, Hosted Interview, Hosted Voice,
the Attribute Reporting/Brand Fit bridge, plugin change requests, and the
public/static site. Dataset analysis, journal checking, slide work, and
reporting run through the plugins and local deterministic scripts rather than
web execution routes.

The legacy Sample Entries web workflow has been retired. Journal sampling now
runs through the Journal Sampling Codex plugin, where Codex handles variable
journal formats and deterministic scripts produce the normalized rows, sample,
diagnostics, and audit trail.

The accountant workflows are plugin-first. Public pages under `static/shared/`
are install/onboarding pages for Codex plugins and downloadable ZIPs; they are
not execution UIs.

Matching proceeds through these stages:

1. Amount and Date Window
2. Bank Fees and Charges
3. Cash Withdrawals/Deposits
4. Card Payments
5. Payroll and Taxes
6. Beneficiary Name
7. IBAN
8. References (Invoice/CRO/TRN)

### PDP Attribute Workflow

The upstream attribute pipeline now runs directly from the configured PDP store.
Use `scripts/export_pdp_attributes.py --retailer <name> --category <key>` to
rebuild deterministic and text-LLM attributes for a retailer/category slice. If
you also want image/VLM enrichment in the same run, add `--run-vlm`; that runs
the VLM stage for the same scope and refreshes the written exports afterward.

For brand-site web-search fill without rebuilding the export files, use
`scripts/brand_web_search_attribute_fill.py --retailer <name> --category <key>`.
Image/VLM enrichment belongs to `scripts/export_pdp_attributes.py --run-vlm`.



## Research and entry-check workflows

Deep Research prompt preparation and answer validation run through the
Prompt Optimizer and Deep Research Validator plugins. Journal-entry support
testing runs through the Check Entries plugin. These workflows are no longer
served by the FastAPI application.

## Development Setup

Install runtime and development dependencies before running tests:

```bash
./scripts/setup.sh
```

The script installs the packages listed in `requirements.txt` and
`dev-requirements.txt`.

## Running the Project

On this machine, use the local virtual environment at `.venv` before running
Python commands:

```bash
cd ~/Documents/GitHub/app_files
source .venv/bin/activate
```

Run the hosted-services boundary locally only when working on a hosted feature:

```bash
uvicorn src.fastapi_app_entry:app --reload
```

For ordinary Vera and Clara work, invoke the relevant plugin workflow instead.

For Codex, explicitly use the local virtual environment at `.venv`; activate it
first with `source .venv/bin/activate` before running Python commands.

### Authentication environment variables

Set the following variables in your `.env` file or shell profile when enabling
Google sign-in:

For repository-based environments, copy `config/secrets.example.toml` to the
ignored `.secrets/secrets.local.toml`, restrict the directory to mode `0700`
and the file to `0600`, and populate it locally. Never commit live credentials.

- `AUTH_ENABLED`: Toggle authentication. Accepts `1`, `true`, `yes` or `on` to
  enable verification.
- `GOOGLE_CLIENT_ID`: OAuth client identifier generated in the Google Cloud
  console.
- `GOOGLE_ALLOWED_DOMAINS`: Optional comma-separated list of email domains
  authorised to sign in (for example `example.com,sub.example.org`).
- `GOOGLE_ALLOWED_EMAILS`: Optional comma-separated allow-list of individual
  email addresses when you want finer control than domain matching.
- `AUTH_SESSION_SECRET`: Required when `AUTH_ENABLED=1`. Must contain at least
  32 bytes and signs the session cookies issued after Google verification.
- `AUTH_SESSION_TTL_SECONDS`: Optional cookie lifetime (seconds). Defaults to
  43 200 s (12 h).
- `AUTH_COOKIE_SECURE`: Defaults to `1` and must remain enabled for a production
  HTTPS origin.
- `AUTH_PUBLIC_BASE_URL`: Canonical HTTPS origin used for security-sensitive
  email links; defaults to `https://mparanza.com`.
- `AUTH_TRUSTED_HOSTS`: Optional comma-separated additional Host values. The
  canonical host is always trusted and unlisted hosts are rejected.
- `AUTH_MAGIC_LINK_TTL_SECONDS`: Optional magic-link lifetime (seconds). Defaults to
  900 s (15 min).
- `AUTH_MAGIC_LINK_DEFAULT_REDIRECT`: Optional path to redirect users to after they click
  the email link. Defaults to `/`.
- `AUTH_MAGIC_LINK_STORE_PATH`: Optional local JSON file used by the non-Redis magic-link
  store. Defaults to `caches/magic_link_tokens.json`.
- `REDIS_URL`: Connection string (for example `redis://localhost:6379/0`) used to store magic
  link tokens. Recommended when running multiple workers so links are shared across processes.

When `AUTH_ENABLED` is off, the remaining variables are ignored.

### Email delivery (Resend)

Configure Resend to send magic links and job-complete notifications. Store the
credentials in `.env`:

- `RESEND_API_KEY=...`
- `RESEND_FROM_EMAIL="Acme Notifications <notify@your-domain.com>"`
- `PDP_RUN_NOTIFY_EMAILS="operator@your-domain.com"` for optional PDP run
  notifications (comma-separated when more than one recipient is needed)
- `HOSTED_INTERVIEW_NOTIFICATION_EMAIL="operator@your-domain.com"` for
  optional hosted-interview completion notifications

The `.gitignore` entry keeps the file local so the key is never committed. Use a
dedicated API key per environment so you can rotate credentials without
downtime. The `RESEND_FROM_EMAIL` value must reference a sender identity that
belongs to your verified domain in the Resend dashboard. Recipient variables
are optional; when omitted, the corresponding notification is skipped.

### Magic link workflow

When `AUTH_ENABLED=1`, you may offer passwordless sign-in alongside Google OAuth:

- `POST /auth/magic/request`: accepts `{"email": "...", "redirect_path": "/app"}` and sends the
  user a one-time link via Resend. Email addresses and domains obey the same allow-lists used
  for Google login.
- `POST /auth/magic/verify`: accepts `{"token": "..."}` from the emailed link and sets the
  session cookie (response mirrors the Google `/auth/login` payload and includes the
  resolved `redirect_path`).
- `GET /auth/magic/consume?token=...`: browser-friendly version that sets the cookie and
  redirects to the stored path (defaults to `/` when unspecified).

Tokens expire after the configured TTL and are single-use. Without `REDIS_URL`, hashed token
records are stored in the local `AUTH_MAGIC_LINK_STORE_PATH` file so a normal single-process
server restart does not invalidate unexpired links. Set `REDIS_URL` when every worker must
share the same token store.

With authentication enabled, protected hosted-service endpoints require a
valid session cookie. Public landing, legal, interview-participant, static, and
change-request routes retain their route-specific access rules.

## Deployment

Run the FastAPI service with the default entrypoint:

```bash
uvicorn src.fastapi_app_entry:app --host 0.0.0.0 --port 8000
```

The entrypoint calls `modules/hosted_services/api.py:create_app`, which mounts only the
public site and the current hosted-service routers. Legacy review, sales,
check-entry, hierarchy, column-identification, slide-editor, project, and
presentation routes are intentionally not mounted.

Set the same environment variables on your deployment target so the FastAPI
processes share the configuration:

- `AUTH_ENABLED`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_ALLOWED_DOMAINS`
- `AUTH_SESSION_SECRET`
- `AUTH_SESSION_TTL_SECONDS` (optional)
- `AUTH_COOKIE_SECURE`
- `AUTH_PUBLIC_BASE_URL`
- `AUTH_TRUSTED_HOSTS` (optional)
- `AUTH_MAGIC_LINK_TTL_SECONDS` (optional)
- `AUTH_MAGIC_LINK_DEFAULT_REDIRECT` (optional)
- `AUTH_MAGIC_LINK_STORE_PATH` (optional)
- `REDIS_URL` (recommended when running multiple workers)

`GOOGLE_ALLOWED_DOMAINS` may be left empty to admit accounts from any domain,
but `GOOGLE_CLIENT_ID` is always required when authentication is enabled.

To enable email notifications and magic-link delivery add:

- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL`

### Page-level permissions

The FastAPI site routers enforce page-specific allow-lists through two JSON
files. `config/permission_structure.json` maps each `page_key` to the list of
route prefixes it protects, and `config/site_page_permissions.json` maps each
`page_key` to the list of Google sign-in email addresses that may access those
routes. Emails are normalized to lowercase before matching, so enter them in
lowercase to avoid confusion. When a route prefix is absent from
`permission_structure.json`, everyone with an authenticated session may load
that page or API. When a route prefix is mapped to a key in
`permission_structure.json` but that key is missing from
`site_page_permissions.json`, the route is denied.

| `page_key` | Routes guarded | Purpose |
| --- | --- | --- |
| `clara` | `/case-notes/voice`, `/case-notes/api/voice` | Clara voice notes. |
| `attribute_reporting` | `/case-notes/api/attribute-reporting` | Attribute Reporting and Brand Fit evidence exchange. |

To grant access add the user’s Google address to the corresponding list. Use
`"*"` to allow every authenticated user while retaining the route mapping for
future email allow-listing. To
protect a new page, add a route prefix entry in `config/permission_structure.json`
and create a matching entry in `config/site_page_permissions.json`.

Real permission maps are deployment-private state, not source files. Git tracks
the corresponding `*.example.json` contracts and ignores
`config/*_permissions.json`. Production should set
`APP_PRIVATE_CONFIG_DIR=/home/<service-user>/.config/mparanza`; an explicit
`SITE_PAGE_PERMISSIONS_FILE` overrides only the site-level map. Protected site
routes fail closed when their site permission map is missing or empty.

After changing an ignored permission map locally, validate and publish all
private maps over SSH without committing their contents:

```bash
APP_FILES_DEPLOY_HOST=myserver \
  .venv/bin/python scripts/deploy_private_permissions.py
```

The publisher defaults to `.config/mparanza` under the SSH user's home, matching
the application path above when the SSH and service accounts are the same.

See `config/PERMISSIONS.md` for the dry-run command, path precedence, and the
server-side file contract.

## Testing

Run the test suite with coverage:

```bash
pytest --cov=src --cov-report=term-missing
```

Coverage must remain at **80 %** or higher. `make check` runs the same command
alongside formatting and static analysis.

## Session Maintenance

FastAPI workflows persist sessions under `tmp/*_sessions`. The API server now
launches a nightly cleanup thread that removes artifacts older than seven days
(168 hours). You can also run `make cleanup-sessions` manually (or via cron)
when you want to trigger the same cleanup immediately. The target calls
`scripts/cleanup_sessions.py`, which supports `--dry-run` if you just want to
preview deletions.

## Contributing

Commit messages follow the
[Conventional Commits](https://www.conventionalcommits.org/) style (for example
`feat:` or `fix:`). Run `make check` before opening a pull request to ensure
formatting, static analysis and tests succeed. The pre‑commit configuration
scans `src`, `ui` and `tests` for `len(df)` and similar patterns; use
`df.height` and `df.width` when working with Polars. Any occurrence of
`streaming=True` in tracked files triggers a pre‑commit failure.

Avoid silent `except` clauses or broad `Exception` catches. Only suppress
expected errors and handle or re‑raise the rest.

## License

This project and its Codex plugins are available under the
[GNU Affero General Public License v3.0](LICENSE).
