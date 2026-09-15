> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Automatic preparation of an ECONS invoice review

Use this route when the operator asks Vera to prepare the TeamSystem Studio
ECONS passive-invoice review automatically. It acquires existing data and
mappings through Playwright and saves a populated private review. It does not
post, modify accounts or VAT, approve invoices, or mark invoices controlled.
It is distinct from the Agenzia invoice-download capability.

Read `passive-invoice-procedure.md` for the shared professional procedure.
The following bindings and execution contracts remain ECONS/browser-specific.

## New-conversation startup

An ordinary request such as "Vera, registra le fatture passive in TeamSystem"
must work as the entry point in a new conversation. The installed procedure is
the source of professional instructions; an old thread, CR, download or developer
handoff is not a prerequisite.

1. Read `passive-invoice-procedure.md`. In the existing host Node runtime import
   `scripts/econs_setup.mjs` and call `loadEconsSetup()` with no directory argument.
   It reads only Vera's known private setup store: `%LOCALAPPDATA%/vera/econs` on
   Windows and `~/.local/share/vera/econs` on other hosts. This lookup requires no
   Python setup, browser connection, user-managed file or package installation.
2. `saved_setup` returns the acquisition profile, any learned processing profile,
   studio exclusions, setup ID and prior run location. Reuse them. Inspect the
   last local report for uncertain posting attempts before new writes; reconcile
   those with the current UI instead of retrying a saved attempt. Reconfirm actual
   account/client identity and apply current authorization, which is never saved
   by this helper. Existing phase preconditions check the current controls.
3. `setup_required` starts technical binding from the installed procedure and
   authorized current screen. It does not start professional teaching again.
   `setup_incomplete` recovers partial bindings and `pendingStep`; finish that
   exact gap. Save after each meaningful observation with `saveEconsSetup`,
   `incomplete: true`, the observed partial phases and a precise `pendingStep`.
   Unknown exclusions remain `null` in a draft, never an invented empty list.
   Use the returned `setupId` for all later saves. Complete profiles use
   `incomplete: false`; partial profiles are never executable.
4. `choose_setup` needs only identification of the correct named studio; never
   choose another studio's exclusions or overwrite its setup. A corrupt/missing
   selected record is a concrete recovery error, not permission to reset it.
5. `company_signal_update_required` preserves a v1 profile but requires only the
   company phase to be rebound to the actual new-invoice arrival signal and the
   profile schema changed to v2. Do not relabel a nightly-synchronization switch
   as proof of new invoices. Retain the invoice/detail and processing bindings.
6. Connect or recover the authorized Chrome session using `browser-session.md`.
   For registration, finish only missing processing phases and create the five
   model callbacks from the installed processing instructions. Do not silently
   replace registration with read-only review. Provision/reuse the shared managed
   Python environment when its helpers are needed, once for this setup; never
   create another environment or repeat a failed setup without new evidence.

```javascript
const { loadEconsSetup, saveEconsSetup } = await import(`${moduleRoot}/scripts/econs_setup.mjs`);
const saved = await loadEconsSetup();
// Interpret saved.status; no chat history or old run path is an input.
// After finishing only the missing observed bindings:
const setup = await saveEconsSetup({ profile, processingProfile, excludedCompanyCodes,
  setupId: saved.setupId ?? null });
```

Run `collectEconsReview` in a new private run directory, passing that `setupId`.
The collector saves the current setup and a pointer to its durable report before
its first browser action. A review-only run preserves learned posting bindings.
The store keeps immutable setup revisions, hashes and private file permissions;
it contains no cookies, credentials, browser session or reusable approval.
Technical errors must preserve a specific next step and partial local evidence;
do not repeatedly restart discovery or make the operator reconstruct the setup.

## First use: finish the screen binding, not the teaching

Read the installed professional procedure first. A developer pack, if supplied,
is supplementary evidence, never execution instructions. The ECONS workflow uses
the observed new-invoice arrival signal, exclusions, invoice states, extended descriptions,
existing account/VAT mappings and controlled popup. Its reported posting
examples are not clean executor receipts. The sanitized origin, missing row
selectors and missing frame path cannot be run as supplied.

Vera owns this technical setup. Do not ask Francesco for code, selectors, JSON,
column formatting choices, or a complete repeated demonstration.

1. Reuse the authorized connected Chrome task and authenticated ECONS session.
   Establish the authorized invoice-data boundary once, using existing
   authorization when supplied. Do not inspect login material.
2. Inspect only missing company/invoice/line controls and the selected frame
   path. Include the actual top-level and intermediate frame origins in the
   phase capabilities. Reuse a saved profile when available; verify current
   controls rather than regenerating it on every run.
   On a genuinely unconfigured installation, use documented `tab.playwright`
   read-only/reversible navigation to reach one authorized invoice and read its
   complete fields before assembling a general batch capability. This is a
   model-guided first acquisition, not an executor replay. Save its observed
   bindings and exact next step immediately. Do not build nine complete phases,
   run a synthetic acceptance exercise or redesign the workflow merely to open
   the first invoice. Accounting writes still require the processing contract.
3. Author three `browser-capability/v2` acquisition phases from this evidence.
   Use the normal discovery, review, promotion and validation tools. Existing
   explicit approval to implement this scope authorizes authoring; it is not
   proof that an unobserved locator works. Never fabricate reviewed discovery,
   an origin, row identity, count, approval record or replay receipt.
4. Each phase must start from the preceding phase's actual end state. The
   invoice-list phase must also work after the previous company's final detail;
   the detail phase must work from the list and from the previous detail. Include
   the observed reversible return/open/select actions. Prefer exact stable row
   identifiers over invoice number alone. The selected invoice header must
   prove both company and document identity.
5. Read the complete description through targeted `text_content` or an observed
   full-value attribute. Do not substitute the column heading, drag a separator,
   or silently accept truncated text. A missing full value is a gap to resolve.
   Field locators are scoped to the row; use `locator_candidates: []` for the
   row itself.
6. Compare populations against independent displayed totals. For a virtualized
   or paginated grid, bind a supported complete-selection view or retain a
   partial result with the exact paging gap. The collector does not invent page
   traversal or treat one visible page as all invoices.
7. Prove one populated review entry on ECONS, then reuse the same profile for
   the batch. Synthetic tests demonstrate the code path, not live compatibility.
   Retain two clean same-contract runs before a validated claim.

## Saved local profile

Save one private JSON object with `schema_version: "econs-review-profile/v2"`
and `phases: {companies, invoices, detail}`. Each phase is a complete capability
object, not a filename or a description. It must pass the capability validator,
carry actual reviewed discovery and have `discovered` or `validated_local`
status. The original posting draft is not an acquisition profile and must not
be relabelled as one.

| Phase | Required text inputs | Exact outputs |
| --- | --- | --- |
| `companies` | None | `companies` record set: `company-code`, `has-new-invoices`; `company-count` scalar |
| `invoices` | `company-code` | `company` record: `company-code`; `invoices` record set: `invoice-id`, `invoice-number`, `supplier`, `status`; `invoice-count` scalar |
| `detail` | `company-code`, `invoice-id`, `invoice-number` | `invoice` record: `company-code`, `invoice-id`, `invoice-number`, `supplier`, `status`; `lines` record set: `line-id`, `description`, `account`, `vat-code`, `amount`; `line-count` scalar |

All fields except the boolean `has-new-invoices` are text. Keep amounts as observed text.
Bind that boolean to the observed indication of newly arrived invoices for each
client. A configured nightly synchronization without that indication is false.
Process selected clients in their observed order and retain studio exclusions.
Counts must be plain nonnegative integer text extracted from an independent
total control, not calculated from the rows being checked. Outputs use
`delivery: model_and_artifact`, making exact authorized values available to
Vera for professional review. Line content fields may be optional/null when
missing; identity fields must be present. Blank accounts or VAT codes become
explicit exceptions, never invented assignments. The collector supports at most
90 lines per invoice in this first review format; larger invoices stop with a
partial result and retain the phase's acquired values for continued review.

Use `runtime.frame_selectors` for the fixed inspected nested frame path, at
most five selectors. It is part of the execution hash and reviewed provenance;
every selected frame must belong to `site.allowed_origins`. Never copy a
synthetic test's frame selector into a live profile.

Phases may use only reviewed read-only/reversible `goto`, `wait_for`, `click`
and `extract`. Do not mislabel a posting button as reversible. `Contabilizza`,
`Conferma`, editing fields and the controlled popup do not belong in this profile.
Empty lists need an observed no-result branch that still produces the zero
count; do not guess that a missing grid is empty.

## Run and reuse

### A bounded trial or an explicitly selected client

For a request such as "try three invoices" or "review these invoices for this
client", reuse the saved profile and read the authorized company/invoice list to
resolve exact identities. Pass `invoiceSelection`, an object mapping observed
company codes to arrays of observed invoice IDs. The operator's request and the
model's interpretation select the invoices; the helper only checks exact IDs.
Do not ask the operator to write this object or repeat the professional teaching.

`maxInvoices` and `maxCompanies` are fail-safe limits, not sample selectors.
Setting `maxInvoices: 3` alone rejects a client list containing four invoices
before any detail is acquired. For three selected invoices, pass their identities
in `invoiceSelection` and set the capacity to at least three. Do not invent IDs,
raise the capacity to process the whole list, or silently substitute an invoice
which is no longer present. An explicit client may lack the arrival signal; studio
exclusions still apply. Without a selection, clients with the observed new-invoice arrival signal are selected.

The executor rechecks the complete displayed list and its independent count,
then opens only the selected details. Its report identifies the selected scope;
it does not claim to cover the full population. The same selection can accompany
explicitly authorized `processing`; posting still requires its existing review
and authorization. A request to register invoices must not be silently routed to
read-only review: state the actual operation before starting. If the required
processing profile is absent, identify that missing setup before expanding work.

Run installation/dependency preflights with Vera's managed interpreter. Import
the collector beside the existing Chrome tab in the host Node runtime:

```javascript
const { collectEconsReview } = await import(`${moduleRoot}/scripts/econs_review.mjs`);
const result = await collectEconsReview({
  tab,
  profile,                    // parsed saved reviewed profile
  excludedCompanyCodes,       // exact local studio list; [] when explicitly empty
  runDirectory,               // new absolute private folder, existing parent, outside Git
  pythonExecutable,           // absolute managed Python path, never a new environment
  setupId,                    // returned by the automatic local setup lookup
  maxCompanies: 50,
  maxInvoices: 200,
  invoiceSelection: null,     // or { [observedCompanyCode]: observedInvoiceIds } for a bounded trial
  environment: { locale: "it-IT" }
});
```

The collector validates every phase before browser actions and executes all
navigation/extraction through `executeCapability` and `tab.playwright`. It
checks exact company/document identities, duplicate IDs, counts and exclusions.
The model decides accounting treatment; no colour classifier does so. All
invoice states, including red, remain visible for review. Posting-specific
red-skip rules do not hide invoices from the acquisition report.

The collector saves the profile, selection, per-phase outputs/receipts/locks,
private phase summaries (including a bounded recovery request when available),
and the existing `batch_review.py` JSON/HTML history after each invoice. Explicit
selection is retained in `selection.json`; `acquisition.json` distinguishes the
source population count from each client's selected count. It uses
the supplied interpreter for fixed local scripts without a shell, installation,
new model service or additional upload.

Open `result.review_path` and inspect `acquisition.json`. `acquired` means the
selected population was collected, not professionally approved. Entries remain
pending review or set aside for missing fields. The batch review stays paused
until model-led review is complete. `partial` means collection stopped; the full
population count stays unknown and earlier entries remain saved. Read the failed
phase's private summary to repair only the actual gap. A restart uses a fresh
folder and the saved profile; it recollects current read-only data and does not
overwrite an earlier review.

Next, read the saved evidence, propose treatment with an evidence-based reason,
and append it through `batch_review.py`. Existing mappings are source evidence,
not automatically endorsed proposals. Apply the saved professional guidance to
each invoice; leave ambiguities as concrete questions for Francesco. Link the
populated HTML review. No posting follows from this route.

## Optional mapping and registration after acquisition

CR-42 supplies operator-reported accounting steps, not executable live locators.
For an explicitly authorized processing batch, pass `processing` to the same
`collectEconsReview` call. Every browser phase still runs through the existing
capability executor. The read-only mode remains available without this option.
The phase files are validated before any browser actions. Each selected client
gets a separate immutable JSON/HTML report alongside the batch report, saved
after each invoice and before any mapping or registration attempt. The returned
`client_reviews` links identify those files. Keep later human checks and linked
corrections through `batch_review.py`; never rewrite completed postings.

`processing` contains `profile`, `classifyInvoices`, `reviewRedException`,
`reviewInvoice`, `reviewJournal` and `approvePosting`. Vera implements these callbacks using the current host model
and available authorization; they are not an invitation for the professional
to write code or an automatic source of approval. No helper calls a second LLM.

The private profile has `schema_version: "econs-processing-profile/v1"`,
`complete_status` and `non_posted_view` with the exact observed state labels,
and `phases: {select, map, journal, post, verify, exit}`. Every phase is a
reviewed `browser-capability/v2`, with the same authorized origins as acquisition
and the actual observed frame path. Do not invent a selector, a discovery hash
or a status label from this reference. Preserve each phase's real start and end
state. All inputs are required text except `checked`, which is boolean.

| Phase | Inputs available | Required observed result |
| --- | --- | --- |
| select | company-code, invoice-id, invoice-number, supplier, line-id, checked | One `set_checked` using `checked`; a visible selection-state output |
| map | company-code, invoice-id, invoice-number, supplier, anchor-line-id, checked | Open Mappature on the associated anchor; `associate-all` uses `set_checked`, then distinct `confirm-mapping` clicks the popup confirmation; output showing return to the invoice |
| journal | company-code, invoice-id, invoice-number, supplier | `journal` record with those four identity fields plus account, net, cost, vat, total, debit, credit |
| post | company-code, invoice-id, invoice-number, supplier | Exactly one consequential `confirm-registration` click with `action_time` confirmation; `posting` record with company-code, invoice-id, protocol |
| verify | company-code, invoice-id, invoice-number, supplier | `company` record with company-code and view; complete `invoices` record set with invoice-id; independent `invoice-count` scalar |
| exit | company-code, invoice-id, invoice-number, supplier | Reviewed reversible return to a known list and visible-state output; a failure stops the batch |

Declare only inputs a phase uses. All required outputs must use
`model_and_artifact`; record fields are text. Amount fields are exact Italian
amount text (for example `1.234,56`), with no currency decoration. Acquire the
actual source value or keep a format gap; do not silently reinterpret a decimal
dot. Zero remaining invoices requires the observed no-result branch and an
independent zero count, not a missing table or unavailable iframe.

`classifyInvoices({company, invoices})` returns `company_code`,
`red_invoice_ids` and a reason from the model's interpretation of the observed
indicator and saved professional guidance. Green and orange items stay in the
processing population and report. The queue reads the complete details of the first two consecutive red invoices
before deciding whether the taught mapping exception applies.
`reviewRedException({company, invoice, detail})` returns `{eligible, reason}`
from the model's review of those observed lines. A true result still requires
at least two concordant existing associations, missing accounts to fill, and
the existing complete-population/VAT checks. Unsupported or unapproved red
exceptions remain in the report without posting. More than two consecutive reds
suspends the remaining client. A tail of reds must not bypass exception review.
The studio exclusion list is unchanged. Colours never approve accounting.

`reviewInvoice({invoice, detail, detail_sha256})` returns `approved`,
`descriptions_complete`, `company_code`, `invoice_id`, `detail_sha256` and `reason`.
The model must read every full description in this invoice before it approves
the review. Non-empty extracted text and a remembered rule do not establish
completeness. A truncated description must be recovered from an observed full
value; if unavailable, return false with the precise gap. Never use a constant
true callback or reuse another invoice's review. Code checks the exact identity
and evidence hash, saves this review alongside the acquired descriptions, and
only then permits mapping or opening the journal. This applies independently
to every invoice, including the second invoice and already mapped invoices.

Before writing mappings, the executor rereads the invoice and requires its
identity and complete lines to match acquisition. At least two existing lines
must share the same account before filling missing associations; every selected
line must have the same VAT code. Discordant accounts, mixed VAT, incomplete
populations and missing descriptions stop the document. A virtualized grid must
use its observed complete-selection or paging path and reconcile against the
independent count; visible rows alone do not pass. The executor selects every
line with `checked: true`, opens the associated anchor, sets the association
checkbox to true (never toggles it blindly), and confirms the popup. A fresh
complete reread must show the expected account on every unchanged line and the
profile's observed complete status. Otherwise the document is saved as an
exception and exited; it is never registered automatically.

`reviewJournal({invoice, detail, journal})` returns `approved`, `reason`,
`company_code`, `treatment_source`, `vat_nondeductible_percent`, and an optional
`rounding_explanation`. The model must read the actual client's treatment,
including pro rata, and review the displayed journal. The reason and source
must identify the client-specific basis. No treatment is inferred from colour
or applied from another client. The supported journal has one concordant cost
account: debit equals credit and total, cost plus VAT equals total, and 100%
non-deductible VAT requires cost equal to total with no separate VAT amount.
Other journal shapes remain exceptions for professional review. A discrepancy
between invoice-line sum and displayed net needs an explicit explanation; the
helper never generates an unexplained balancing adjustment.

`Contabilizza` opens the displayed journal in the observed procedure. It is not
the final registration: bind `Conferma reg.` to the separate consequential
`confirm-registration` action after reviewing its actual screen behavior.
The executor saves the displayed journal values before calling `reviewJournal`,
so an interrupted review retains those values without claiming completion.
Do not bypass this per-invoice sequence with freehand clicks after loading the
rules, and do not call a report complete merely because its file exists.

`approvePosting({invoice, journal, journal_sha256, action})` returns true only
when the exact current registration is authorized under the host's rules.
The report is saved as unverified before dispatch. Completion requires the
captured protocol and invoice absence from the complete Non contab. population
of the same client, in the profile's exact list view. Ambiguous outcomes remain
unverified and must be reconciled before retrying. Inspect phase receipts and
private outputs to resolve the specific gap. Mapping confirmation and
registration confirmation are separate phases and approvals. Link the current
per-client reports in the final response, including completed registrations,
exceptions and uncertain attempts; preserve previous completions when a later
invoice stops. Subsequent professional corrections remain separate linked entries.

Save two clean sets of phase receipts on the actual ECONS environment, with no
locator changes or recovery, before calling the process locally validated.
Use the existing capability finalizer per phase; retain the batch and per-client
reports as outcome evidence. A source release or two synthetic runs do not prove
live compatibility. Announce the beginning and end of guided observation
windows, bind missing structured controls explicitly, and append checkpoint
increments before continuing. Control metadata never stands in for accounting
values or verified results.

## What data reaches the model

The selected Claude model can read authorized company and invoice identities,
supplier, invoice state, complete descriptions, existing accounts, VAT codes
and amount text, plus client-specific pro rata, proposed/displayed journals,
registration protocol, review decisions and exceptions. Optional processing
changes mappings and posts only through the authorized ECONS browser session. These values are not
automatically anonymized; model processing is not local-only. Private JSON and
offline HTML stay in the selected local run directory and must not enter Git,
a developer pack or a public package. Login secrets, cookies, session URLs,
full page HTML and screenshots are not collected by this route.
Vera also reads the selected local setup's studio label, exclusions, inspected
screen bindings, incomplete setup notes and prior report path to start a new
conversation. Those files remain in Vera's private user-local setup store; they
are not transmitted as change requests or copied into developer packs. Reading
them in the selected host model is not offline inference or saved authorization.
