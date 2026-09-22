---
name: browser-automation
description: Use when an authorized operator or developer wants Vera to teach, discover, build, validate, or repair a repeatable process on Agenzia delle Entrate, TeamSystem, Gmail, or another website through the operator's existing Chrome session, including when the developer cannot access the target system.
---

<!-- VERA_OPENAI_ONBOARDING_BEGIN -->
Onboarding is optional. Continue ordinary professional work immediately,
including direct specialist invocation, without checking or completing a local
onboarding profile. Missing, unfinished, inaccessible or corrupt onboarding state,
or unavailable voice/window controls, must never block ordinary work. Do not
automatically start, resume or repeatedly offer onboarding.
Only for a user-requested tutorial or a native teaching handoff, read
`../vera/references/local-onboarding.md`. A verified paired lesson worker
executes only its bound lesson and token; never bypass tutorial validation.
Tutorial profiles, progress, examples and feedback remain local; never send a
change request, stamp a tutorial receipt or call hosted interviews for a tutorial.
Current user requests take precedence over saved preferences.
<!-- VERA_OPENAI_ONBOARDING_END -->

# Automazione web

<!-- VERA_OPENAI_DATEV_BEGIN -->
For DATEV installed as a native Windows application, route instead to
`../datev-invoice-start/SKILL.md` before any browser setup. That explicit native
route reuses the known invoice procedure and local reports, not this executor.
<!-- VERA_OPENAI_DATEV_END -->

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

In Codex Desktop, resolve `../../modules/browser-automation` from this skill
directory when it exists; otherwise resolve `../../../browser-automation` in
the repository. Read that module's `skills/browser-automation/SKILL.md`
completely and follow it. Treat the resolved module root as the plugin working
directory for its contracts, example capabilities, references, and validation
commands.

For development, teaching, testing and repair, read the module's
`references/process-lifecycle.md`. Recover the development catalog and preserve
process/attempt identities and actual CR evidence across conversations.
For routine work, use the installed named operation skill. Do not select an
ordinary-use procedure from the development catalog. If no released skill covers
it, explain the missing operation; start development only within the user's scope.
To turn a developed procedure into a release, follow `references/production-skills.md`.
The named skill owns its inputs, result checks and exact executable binding;
the browser module remains the shared runner. The following legacy specialist
routes retain their existing startup and acceptance boundaries.

For TeamSystem ECONS, start from a new conversation using the module reference's
`New-conversation startup` section. Read the shipped invoice procedure and call
`loadEconsSetup` in the existing host Node runtime before Python setup or browser
discovery. The operator supplies an ordinary work request, not a CR number,
previous conversation, saved-profile path or instruction to continue. Reuse the
automatically found setup; when absent, bind the current screen from the installed
procedure and save partial bindings with their next step. Never require the
operator to reteach the procedure or manually assemble its technical inputs.
Registration requests select the processing route and its model callbacks.
Read-only review is a separate user intent, not a fallback for missing setup.

When learning is requested, follow the module's start-recording protocol before
acting: create/recover the persistent process, start a teaching attempt and use
`process_lifecycle.py teach` for the existing `teaching_checkpoint.py` start/save
implementation, verified resume and a linked report at completion or interruption.
Do not substitute a CR or a chat
recap for recorded teaching. The checkpoint format serves different processes;
keep the actual process boundary and provenance explicit. For an older unrecorded
conversation, prepare the partial development request from available attributed
notes rather than inventing observations or restarting the demonstration.

During teaching, the operator explains the work, and Vera owns its technical
translation. Resume supplied checkpoints and saved decisions before asking new
questions. Keep TeamSystem posting and Agenzia invoice download distinct.
For record review, acquire one real record and its proposed mapping within the
authorized data boundary, then produce one populated review entry before
expanding a workbook. Choose a plain layout yourself; do not ask the operator to
select spreadsheet styles, write code or reconstruct understood steps. Ask only
one unresolved process question at a time. A template is not working extraction;
a checked example is not a validated replay. Follow the module's acquisition
loop and persist a precise next step.

This connects generic process development with separately qualified ordinary use. The
model leads one example, interprets each demonstrated step and saves a resumable
teaching checkpoint before continuing. It announces when observation stops;
unexplained button changes are not a learned procedure. A paused checkpoint is
distinct from a completed reviewed developer pack. The
operator may demonstrate the process (`guided`), let the model explore safe
reversible paths (`autonomous`), or combine both (`hybrid`). A reviewed
sanitized developer pack lets another person understand and implement the
process without receiving credentials or browser state. A later, separately
approved capability is the executable handoff.

The live route uses Google Chrome managed under Settings → Computer Use →
Google Chrome and the user's connected Chrome extension. Follow the current
connection's browser API documentation and reuse its `tab.playwright` surface
and existing Chrome profile. A separate Chrome plugin is not required. Before
yielding for login, operator input or unfinished work, preserve the actual task
tab with the module's `preserveBrowserHandoff` helper and save the result. Repeat
the handoff mark in each turn that must retain the live tab. After resuming or
on an error, follow `references/browser-session.md` and its same-tab inspection.
A missing tab or empty inventory does not establish an extension disconnection;
do not repeatedly send the operator to Settings without diagnostic evidence.
Continue useful checkpoint review and partial development exports while the
browser is unavailable. Never claim execution or validation without evidence.

For the individual Agenzia invoice downloader supplied with CR-43, follow the
module's `references/agenzia-download.md` and use `scripts/agenzia_download.mjs`.
Vera reads the authorized filters and expected population counts and reconciles
the saved files. Preserve partial results on interruption. Every result remains
a prototype until target-site validation. Simulated tests and earlier manual
downloads do not validate this module; declare the actual execution mode.

For CR-49 category/year acquisition, follow the module's
`references/agenzia-acquisition.md` and use `scripts/agenzia_acquisition.mjs`.
Vera reviews the explicit category plan against current authorized portal
evidence, preserves XML/P7M originals, extracts and hash-links encapsulated
FatturaPA XML without claiming signature validation, records unavailable formats,
and resumes only after verifying retained state and artifact hashes. Print to
PDF is an operator-owned `native_gap`; it is verified from the saved bytes but
does not count as a clean browser replay. Do not close CR-49 from simulated runs
or publication alone; the exact released version still needs two clean target
repetitions meeting the request's count, page, category, and resume criteria.

Local filesystem verification of browser downloads in the normal Downloads
folder is part of the runtime, like writing receipts; it is not desktop control.
The runtime handles it automatically without a documented download `path()` API.

This workflow has no native desktop-control fallback. A required
native or non-browser step is a `native_gap`: hand that exact step to the
operator and exclude it from capability execution and clean replay evidence.

Never look for runtime scripts inside this wrapper directory. The executable
runtime and deterministic capability pipeline live in the resolved module and
have no third-party dependency.
For acceptance testing, run the resolved module's
`scripts/check_installation.py` and use the version returned from that active
manifest as the version under test. Never reject a newer installed Vera because
an old test prompt names a historical version; an exact-version check applies
only when the operator explicitly asks to test that exact release.
For cross-platform acceptance, use the resolved module's shipped
`scripts/acceptance_fixture.py`; do not improvise a local server. Follow the
module skill's exact self-probe and committed-navigation checks before treating
a connected-Chrome `goto` timeout as a terminal fixture failure.
Authentication is always performed by the operator; never request, inspect,
enter, retain, or transfer login secrets or reusable browser state.

Detect compatible browser control, persistent Node and local files from actual
callable host tools. On a surface without them, preserve useful reported evidence
and state which operation is unavailable; never claim that a local helper ran or
that a saved record exists without evidence. The host product name alone does
not establish browser support or explain an earlier failure.

When asked to download Agenzia invoices and remember passwords, explain both
parts of the request and continue the supported post-login work. Reuse a
confirmed authorized session; request operator login only when it is needed.
Do not require a special prompt, a separate enterprise RPA system or a
credential vault for this route. Remembering the procedure does not retain
authentication or guarantee unattended future access. Name any actual browser
or process blocker and preserve the prototype/target-validation boundary.
For example, adapt this explanation to the observed runtime and user request:
“Per scaricare le fatture posso usare la sessione Chrome collegata dopo che hai
effettuato l'accesso e selezionato il profilo corretto. Non posso inserire o
conservare le tue credenziali: se il portale richiede un nuovo accesso, lo
effettui tu. Posso conservare la procedura senza salvare password o sessioni.
Verifico il percorso disponibile e i conteggi dei file scaricati; se incontro
un blocco ti indico il passaggio preciso.”

For invoice batches, follow the module’s `references/batch-review.md` and use
`scripts/batch_review.py`. Save a durable local report for review after processing,
with exceptions first, proposed and actual treatment, reasons and source evidence.
Francesco need not watch Vera work. Record his later checks and correction requests;
never silently replace a posted entry or mistake a request for a completed fix.

For automatic ECONS review preparation, use the module's
`references/econs-review.md` and `scripts/econs_review.mjs`. Reuse the saved
reviewed Playwright profile; on first use Vera fills only missing live screen
bindings. Collect full invoice lines and existing account/VAT mappings into the
populated local review, then add model-led proposals. This route does not post.
For a small trial or selected client, use the reference's `invoiceSelection`
argument with observed company/invoice IDs. `maxInvoices` is a safety limit on
the selected work, not a request to take the first few invoices. State whether
Vera will acquire a review or perform authorized registration before starting;
do not substitute a read-only review for a request to register invoices.

When asked to prepare the saved work for Fabio or a developer, follow the module’s
`references/development-request.md`. Vera locates saved evidence in the known run,
prepares a sanitized development request with results, gaps and acceptance checks,
shows the exact contents for review and exports one approved ZIP. Do not ask the
operator to locate code, reconstruct known steps or zip files. A working local
process can be handed off without calling it broken. CR registration uses the
existing explicit submission route only when transmission is authorized.

## Complete ECONS mappings and registrations

When authorized to process ECONS purchase invoices, read the processing section
of `references/econs-review.md` in the resolved browser-automation module. Reuse
the acquisition profile and add the reviewed processing phases. Run
`collectEconsReview` with its `processing` option. Vera supplies the model-led
queue classification, red-exception review, complete-invoice review, journal review and posting-approval callbacks in the host
Node session; no separate model API is configured. Preserve the exact client's
tax treatment and complete report, including green and orange invoices. A
per-invoice review must confirm and save the full descriptions before opening
the journal. `Contabilizza` alone never completes registration: require the
separate final confirmation, protocol and checked absence from Non contab.
Link the current client reports, including exceptions and uncertain outcomes. A
missing binding is a local setup gap to resolve from the actual screen, not a
reason to ask the operator to rewrite selectors or repeat the whole lesson.
Report this as implemented workflow support until two clean runs on the target
ECONS environment have been recorded; synthetic tests cannot establish that.
