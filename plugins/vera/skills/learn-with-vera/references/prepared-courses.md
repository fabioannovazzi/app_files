# Prepared teaching kits for Vera

## Read the installed lesson format first

This interim release combines new prepared teaching kits with retained published
lessons. The workflow-specific notes below describe the new kit format only.
Check `show` before using them: `mparanza.teaching_kit.v2` supplies the new
demonstration and practice files; `mparanza.course.v1` supplies its original
`teacher.md`, `case.json`, `input.csv`, `source.md` and optional supporting files.
For a retained lesson, follow its actual outline and inputs with the current
own-product workflow. Do not refer to absent new-kit files or exercises. Its
`example.html` is a prepared specimen, never evidence of the current execution.
Both formats require live execution in the working chat and explanation in the
paired voice chat. Neither rendering nor a specimen completes the lesson.

## New kit instructions

The `browser-automation` kit uses the component's shipped
`scripts/acceptance_fixture.py`, started with `--port 0`; keep the process alive
and use the exact loopback URL from its ready record. The source brief provides
fictional runtime values. Do not build a substitute website or distribute a
preapproved capability. Follow the current browser skill's installation,
checkpoint, discovery and connected-Chrome runtime instructions. Keep the
checkpoint, discovery record, evidence and draft inside the lesson's private
output directory. Explain the page's English labels in the selected language.

The learner sees the ordinary journey from a demonstrated task to a reviewed
procedure and tested reuse. The fixture's `Reviewed` checkbox is explicitly a
simulated page control; it supplies no real professional or capability approval.
Retain the separate exact-procedure authoring review. Only the normal runtime
can write replay receipts. Two clean live runs are required before describing a
capability as locally validated. Practice changes the document type; observe
and review any change to the saved procedure rather than guessing it works.
Do not transfer a developer pack or use a real portal from this local tutorial.
Stop the fixture after the session unless a current browser handoff needs it.

Check the actual browser REPL before declaring the persistent runtime missing.
When the host supports module imports, load `scripts/process_runtime.mjs` in
that same supported browser session and verify its `executeProcess` export;
the absence of a separately named Node tool does not establish a blocker.
Keep all browser interactions in the host's permitted controller. Importing
the module proves availability only; replay still needs the actual connected
tab and fresh machine-written execution records.

Create the initial teaching checkpoint from the registered process descriptor:
copy its exact objective, start state and end condition, and use the checkpoint
schema's `resume_instruction` and empty `steps`. Do not paraphrase these bound
fields or substitute an informal `boundaries`/`next_step` note. Preserve a
rejected payload, correct it and retry the same still-empty attempt rather than
creating a second process or asking the learner to repeat setup.

Lead the result viewer with a short procedure in the lesson language: supplied
inputs, observed steps, checked result, present review/replay status and the
ordinary request for reuse. Explain the fixture's English labels there. Keep
the native checkpoint report available afterwards for detail; its identifiers
and hashes must not become the learner's main explanation. Derive this readable
summary from the actual saved steps and receipts, preserving any missing checks.

The `bilancio-oic` kit starts with a fictional first-year company and a small
trial balance. Read the current `bilancio-xbrl-it` entry point, import and review
the source, determine the applicable form, review proposed account mappings,
and prepare statements with the current official taxonomy and disclosure pack.
Open the actual HTML draft and its validation findings together. The supplied
year-end declaration includes taxes from an external fictional workpaper and
the supporting disclosures; review those exact inputs rather than treating them
as missing or recalculating the tax. Any information actually absent remains a
question for the professional. Never imply that a draft is approved or ready
to file. Practice uses a revised trial balance in a new run and preserves the
first result. No approved mappings, negative confirmations or output are shipped
in the teaching kit.

Prepare the managed Bilancio case once and retain its returned client,
engagement, run and case locations. To resume, resolve that existing run; do
not repeat the new-case adapter to recover a missing return value. Both the
company Markdown and the year-end text are supported evidence attachments.
Keep final drafts and check reports under that run's outputs directory.

The year-end declaration states the completeness of the account population
and gives explicit absence statements. Review each applicable category, then
record the required per-concept presentation decisions with its specific
source and reason. A missing balance alone is not evidence of zero. Complete
the triggered supporting schedules, selected-form disclosures and local
candidate check before presenting the final result. Do not turn technical
payload entry into an extra learner exercise after the learner has reviewed
the source-backed proposal. Rebuild the preview after changing the case, and
show the current draft together with the actual check report; an earlier
preview is not evidence of the revised result.

For the update exercise, review fresh bounded packets from the replacement
inputs. Check amounts in the explanation as well as the proposed account
classifications: copying an earlier rationale can preserve an obsolete amount
even when the classification still fits. Return such a proposal for correction
before applying it. Retain the old version as history, and cite the replacement
year-end declaration for the updated disclosures.

The `registro-imprese-sari` kit prepares a fictional company PEC change through
the current case inventory, official-source selection, plan and review package.
Use the public references as starting points, verify current guidance, and keep
source applicability and missing activation evidence open. It contains no SARI
card selection, approved filing route, credentials or prewritten practice plan.
Practice changes the request; make a new run and preserve the original result.
For this follow-up, import the practice files into the demonstration's existing
client and engagement, then prepare a new native ledger run there. The isolated
tutorial-case adapter creates a fresh client even when its phase is `practice`;
do not use it as a resume operation for this changed request.
If the host does not expose the review tools, use the workflow’s native local
browser review transport. Open its loopback URL in Codex and exercise the actual
Save/Apply controls; scripted test decisions are not browser acceptance.

The `comunicazione-professionale` kit starts with a fictional studio brief and
an attributed official source. Run the current communications workflow in its
private studio workspace: draft, independent claim and editorial review, the
normal professional review, and actual packaging. Practice adds a covering
email to a new version. The supplied brief is not approval of generated text
or the proposed studio profile. Do not use a client-ledger substitute or send
the communication from a tutorial.

The `quesito-legale-fiscale` kit starts with a fictional request for an
informational briefing. Follow the ordinary own-product question journey,
including the per-answer research choice and answer validation. Source files
are starting evidence; check their currency. Keep source language separate
from answer language and jurisdiction. Practice changes the audience and
question scope. Do not invent an opposing position for this informational
request, a ready-made answer, or completed validation.
The real archive journey starts with `prompt-optimizer`; its closed preparation
artifacts feed a `deep-research-validator` run in the same engagement. The named
question lesson is not a third ledger stage. Generate Word through the current
packager and verify the requested length and source links; a hand-edited output
does not establish that the workflow exports correctly. Keep the useful answer
prominent and the complete verification record available for inspection.

The native package contains one kit per supported teaching entry, with plain
localized titles, a stated purpose, fictional input files, a lesson outline,
checkpoints during execution, a short practice and repeat-use guidance. The
catalogue distinguishes main workflows from supporting tasks. Select relevance
with the native model from this product's own current catalogue.

Use the same installed root returned by the active worker contract:

```text
python scripts/local_courses.py list
python scripts/local_courses.py show --workflow <exact-id> --language <supported-language>
python scripts/local_courses.py render --workflow <exact-id> --language <supported-language> --output-dir <fresh-local-lesson-files>/kit
```

`show` and `render` verify product identity, supported language, input bytes and
current workflow sources. An unavailable language requires a supported choice;
a missing or stale kit needs refresh. Never borrow another product's kit.
`render` preserves an existing destination and writes:

- `course.html`: the first-use guide, with links to real fictional input files;
- `teacher.md`: prepared voice outline and concrete workflow checkpoints;
- `execution-request.json`: exact own-product skill, input paths and teaching
  intentions for the paired worker, explicitly not an execution receipt;
- `files/input/`: the demonstration inputs in the pipeline's supported formats;
- `files/practice/`: inputs for the learner's fresh practice attempt;
- `course-provenance.json`: kit revision, source identity and unexecuted state.

Read the current specialist and all delegated procedures. Prepare the actual
tutorial case using the returned `source_files`. For `studio-archive`, use the
isolated local-search route in `../../vera/references/tutorial-cases.md`, not a
ledger workflow input view. For other workflows, keep the original
filenames associated with the bound paths returned by that adapter. Supply only
appropriate files to each helper: a case brief informs model interpretation,
while a tabular calculation receives the bound table, not every file blindly.
Complete required semantic review from the fictional facts without fabricating
professional approval. Execute in the user-visible working chat and return
actual artifacts and status to the voice teacher. The kit creates no final
workflow output, approval, receipt, user answer or completion checkpoint.

Open actual new results as they arrive. Point the learner to the starting section,
the detailed evidence and the useful next action. Use checkpoints at the right
moment and adapt the spoken explanation. The practice uses `practice_files` for a new attempt initiated by the learner.
When the specialist updates an existing case, continue that same teaching case
and preserve the prior run or workpaper; otherwise prepare a fresh teaching
case. Never replace a required predecessor with a fabricated saved result.
Never mark onboarding practice or understanding from an automated fixture test.

A custom example is allowed when helpful: state the changed facts, use valid
inputs for the same own-product workflow and execute it afresh. If a required
host capability is missing, state which step is pending. A local preparation of
a hosted workflow is a preparation step, not a completed hosted demonstration.

Listing, inspection and rendering use local file operations only; browser
preview separately serves the kit on loopback as described below. Profile, progress and tutorial files
are not sent to Mparanza; native OpenAI voice/model processing still applies to
what is discussed or read in chat. Cowork excludes this native teaching system.

Release checks validate kit files and source currency and run relevant pipeline
checks from the packaged kit inputs. Editorial review asks whether a beginner
can supply files, make the request, recognize progress, use the deliverable and
repeat the workflow. Hashes and successful rendering do not answer that question.

## Website workspace route

`presenza-digitale-studio` uses `execution.route: local_website_workspace`.
The tutorial adapter stages the selected files and a private output directory;
it does not invent a ledger context for this standalone website specialist.
After the learner selects the fictional material for this website exercise,
initialize the specialist's normal owner-controlled workspace under that output
directory and prepare its intake with all external routes unselected. Follow
the exact current specialist, including the owning product's professional profile.

Build and validate the real local HTML/CSS, review its rendered desktop and phone
versions and record actual screenshots. Do not generate blank screenshots or
claim visual review from a file/dimension check. Local preparation is not
`preview_ready`, `release_ready` or `published` without the actual corresponding
package/reviews. Explain publication using the current procedure; a local lesson
does not select external preview or final publication. Practice updates the local
site in a new run/version, preserving the demonstration and rechecking the new
bytes. Never reuse approvals from the old site.

Open website results through the normal `local_courses.py results` command,
including `site_validation.json` among the native records and every authored
HTML page among the outputs. The result view opens the exact validated site
with its local asset paths intact; the passive report reader is not a website
preview. Reused styles, fonts, images and licences remain hash-checked dependencies
in the native site inventory, not proof that a new workflow ran. Keep the site
on loopback, inspect its actual layout and use the input links to explain its
sources. Save screenshots with the extension matching their actual image
format, and verify the captured width before claiming a phone review. If a
host's viewport control has no effect, report that limitation and use an
available supported browser for responsive inspection without claiming the
in-app resize worked.

## AML review and subsequent evidence

The initial AML lesson starts a normal `aml-review` run with the fictional
client, ownership declaration and shareholder-loan documents. Read these
originals and the current specialist method. Research current relevant official
sources using generic topics, without client details. Prepare the actual
source-bound assessment and memo, retaining missing identity/control/screening
evidence and the coherent loan evidence. No New Client score or professional
decision is supplied by the kit; do not invent one.

Practice adds the new ownership declaration to the **same** teaching client and
engagement. Revalidate the active worker handoff, complete the first run's normal
declarations, and import its actual immutable AML record plus the selected
practice files using the existing local ledger. Prepare and start a new
`aml-review` run in that engagement. Bind the imported record through `previous`
and its actual record digest, then explain changes against the old scope. Never
call the new-attempt adapter to create a different client for this follow-up.
Preserve the first memo and record byte for byte. Completion means delivery;
the teacher records understanding only from the learner's actual response.

## Company arrangements and follow-up

`adeguati-assetti` supplies company context, a monthly procedure and a dated
operating example. Teach the whole assessment journey: agree scope, examine
responsibilities and actual information use, discuss findings, review actions
and understand the limits of the conclusion. The first successful cycle is
evidence for that cycle only. Do not infer every weekly review or future cash
sufficiency from it.

The April practice continues in the same client and engagement using the actual
first record, as in the AML follow-up above. Import the new evidence and prior
immutable record, start a new `adeguati-assetti` run and bind `previous`. Address
every earlier action in `prior_action_review`. The update documents late dispatch
and report delivery after an absence; it does not support marking the proposed
substitution action complete. Include the current intelligent-assessment
extension and perform the specialist's factual challenge before delivery.
Explain proposed responsibilities and timing as proposals; never record an
accepted commitment or professional approval on the learner's behalf.

## Concordato plan review

`concordato-plan-review` supplies one fictional three-sheet source workbook:
case background, declared creditors and the company's annual cash plan. Stage
the selected file in the normal tutorial engagement, then read the current
specialist and its complete review methodology. The first inspection produces
an unreviewed case template. Reconstruct the case from the workbook, obtain
the required real review of interpretations and assumptions, and use the
current semantic-review and execution commands. Never treat the workbook's
company-proposed class, funding or liquidation estimates as professional
approval. Do not make the optional amount-matching appendix the lesson.

Explain the actual report and workpaper, including document gaps and next
actions. Practice supplies a revised source plan for a new review; preserve
the first output and reconsider the whole case. The kit includes neither a
reviewed case model nor a reviewer receipt. No filing, attestation or feasibility
approval can be inferred from successful execution.

## INPS case review

The `previdenza-inps` kit supplies a question, employment statement, fictional
contribution table and explicit record context. Teach question and period
confirmation, source inventory, evidence review, current official research,
the actual Word memo, chronology and document requests. The table is a teaching
input, never an official portal capture or evidence of non-payment. Read the
current specialist and retain all real review requirements; no approvals,
legal conclusion or arithmetic recipe is bundled in this kit.

Read the answer and next document request before the detailed fact list. Include
the employment and contribution-table period boundaries in the authored
chronology, each anchored to its own source; document creation dates alone do
not explain the period being reviewed. Trace one observation through the memo's
fact and document locator to the evidence matrix and original lesson input.

The practice starts a fresh review of the updated fictional table. Explain
which document comparison changes and which questions still need evidence;
preserve the first lesson result. Do not claim to have corrected the official
record, used a portal, submitted a request or established pension entitlement.

## Sales plan

The `sales-plan` kit supplies actual sales and a clearly hypothetical units-growth
request. Read back the source-to-target months, product scope, units versus price
meaning, unchanged prices, proportional discounts/COGS and EUR currency. The
learner must actually confirm or correct this table before a reviewed-assumptions
receipt is authored. Never ship or infer that confirmation from the kit note.
Use the normal current case and registered Plan CLI; keep any required exact
source copy under this run's output beside the case JSON. Open the actual summary,
scenario and applied-assumption ledger. Practice creates a separate scenario
from the same actuals with the new requested growth, preserving the first run.
Do not invent missing forecast months, market evidence or unsupported charts.

## Business Planning

For Business Planning, read the registered `business-planning` skill and its
shared case contract. The prepared kit supplies a proposal, operating notes and
economic assumptions, not an accepted case or a finished report. Author the
current case from those files, keep reviews pending until actually given, and
use the normal entry point to produce `business_plan_review.html`. A provisional
business assessment with calculated partial economics is a useful first result;
missing cash and funding evidence must remain visible.

The practice continues the same planning case and Studio Archive engagement.
Import the new operating note and the actual first `business_plan.json` as the
prior plan, start a fresh run, reconsider the recommendation and every carried
conclusion, and produce a new linked cycle without overwriting the first one.
The updated note supplies no new figures: do not invent new volumes or prices.
Keep the supplied EUR currency and the original dated commercial assumptions
available as an explicitly labelled previous hypothesis, with a source-bound
table. They are not a forecast for Saturday. A changed operating constraint does
not make the known source currency disappear; revise the recommendation and
identify what must be tested before preparing updated figures. Preserve source
versions for unchanged files and keep all professional reviews pending.
Show both reports and explain what the evidence changed. The learner does not
author technical case JSON, approval records or source hashes.

## Financial analysis and report preparation

`financial-analysis` uses a complete first net-debt analysis to teach choosing an
analysis, supplying dated balances, reviewing classifications and reading results.
It does not turn eight registered calculations into eight onboarding workflows.
Read the note and the CSV before proposing the definition. Build the actual
reviewed case and contract stack during the lesson, using current builders.
Keep an exact, verified copy of the bound source beside the run-local case JSON
when its contract requires relative source paths. Execute the current `net_debt`
pack in a fresh `prepared` child. Open its actual result and line items, explain
the controls, and deliver the normal artifact card and review note. A passed
calculation leaves source tie-out unassessed and professional review pending.
Never distribute a reviewed case, decision receipt or calculated result as an input.

`financial-report-builder` starts the existing `report-builder` ledger workflow.
Its workbook is the calculation input; the separate note supplies scope and
source meanings. Inspect under `<run-output>/inspection`, create the actual
reviewed recipe beside that directory, and build under `<run-output>/report`.
The report has a closed physical output set: do not put extra inspection files
inside it. Use supported canonical period notation such as `2026-01-01 to
2026-02-28`. Review the sheets, measures and supplied subtotal rows, then author
source-supported commentary in the chosen language. Open the generated Word
report and review package. The prepared lesson contains neither final narrative
nor approved source mappings. Practice creates a new version from the March
workbook and preserves the first report.

## Journal sampling intake

The journal-sampling kit includes one CSV journal and a context note. Bind the
CSV as the journal and the note as supporting source context. Read the note to
explain the source columns, period and teaching sample choices; it is not a
second journal. Use the actual inspection, reviewed mapping, normalization and
sampling commands. The learner reviews the column meanings and the resulting
sample; no mapping receipt, sample or approval is precomputed in the kit.

## Vouching and its live prerequisite

The Vouching kit uses `live_journal_sample_then_support_checks`. The tutorial
adapter starts a real `journal-sampling` prerequisite in an isolated client
folder and returns its exact context, `support_input_ids` and a private
`archive_state_dir`. Invoice receipts have the support role and do not enter
the journal normalization run. No sample or check result exists at this point.

Run the current Journal Sampling method on that bound CSV, using the kit's
account filter and teaching sample size after the learner reviews them. Finalize
and complete that actual sampling run with its normal disclosure and artifact
declarations. Then use Studio Archive's normal
`start-check-entries-from-sample` command with this exact sample run ID, the
returned support receipt IDs and the explicit private archive state directory.
Set `VERA_STUDIO_ARCHIVE_STATE_DIR` to the returned directory for that component
CLI invocation only. Its Python API accepts the equivalent explicit `state_dir`.
Never change the user's archive configuration or route the tutorial through
their default archive.

The returned Check Entries context is the authority for executing Vouching.
Follow that workflow's actual inspection, checks, review and finalization.
The voice teacher explains the sampled rows and the comparison with their
documents. This prerequisite is part of the Vouching lesson; do not count it as
another completed onboarding lesson or record an unperformed learner review.
For practice, generate the new sample and its own check run; preserve the
demonstration and never replace the predecessor with a prepared specimen.

## Purchase-invoice review

Use the `review_mapping_then_native_invoice_audit` route with the kit's actual
ledger and XML invoices. The context note declares the source column meanings;
review them during the lesson and save the exact ledger mapping under the
current run's output directory. Bind the supplied documents through the normal
managed intake, then run the current audit with its own native reviewer.
Do not distribute a preapproved mapping or substitute a teacher-authored answer
for the native audit's semantic output.

The current workflow's runtime qualification also applies to fictional teaching
data. If host qualification or the native review fails, preserve the resumable
job and explain that the review has not completed. A mechanically matched batch
or an exception workbook containing processing failures is not a completed
demonstration. Do not replace the native worker, alter its qualification profile
or switch to a separate API to finish the lesson.

## Selected call and grant dossier

`bandi-agevolazioni` starts its dossier stage with the supplied simulated call,
company declaration and itemised quotation. The brief explicitly states that
no authority published this call and no funding is available. The current
Opportunity Radar is a separate starting stage of the same function; this
lesson does not claim to search for a current opportunity.

Bind the files to the actual tutorial case, register each exact source with
its role, and follow the current bounded intelligence packets. Requirements,
evidence mapping, cost classifications and drafting remain model proposals
until the ordinary reviews occur. Never treat a test fixture's decisions as
the learner's approval. The source documents do not establish professional
verification, eligibility, a completed declaration or a funding award.

Open the current dossier, trace a proposed conclusion to the relevant source,
review the costs and document list, and explain what remains open. Practice
uses the revised quotation in a new run, preserving the demonstration. The
native dossier, validation audit and manifest are actual outputs; do not
replace them with a prepared result or claim portal preparation, signing or
submission during this local exercise.


## Open-item reconciliation execution handoff

Use the normal managed archive context and its linked input manifest. Build the
execution settings from the reviewed lesson request and actual source mapping;
do not reuse an enriched output record as an execution request. Store generated
assumptions and review-row configuration under the owning run's `outputs/`,
outside its strict `outputs/reconciliation/` package, and keep that same native
subdirectory on regeneration. Preserve the demo while running the April update.

## Management-control results

The management-control dashboard has live month selectors. After native
`finalize_pack.py`, use that module's `scripts/preview_report.py` with the exact
client context and reviewed dashboard path. Open the printed HTTP URL in the
working chat and verify the cumulative view and one month. Do not pass this
interactive HTML to the passive course result reader, which deliberately rejects
active documents. Use a document result view for the workbook and Markdown
report and keep the dashboard in its native preview. Record all displayed files
and retain the normal complete archive inventory. A completed run can be reopened
read-only with the same native preview command.

## Concordato revision practice

The `concordato-plan-review` practice revises the same fictional case. After
recording the demonstration, reuse its returned `client_root`, `client_id` and
`engagement_id`. Do not call `local_onboarding_case.py --phase practice` for this
update: that adapter creates an independent client and engagement.

Use the ordinary portable `client_ledger` methods: `import_document` for each
replacement practice source, `prepare_run` for `concordato-plan-review` with
exactly those returned input IDs, then `start_run`. Save the full returned
context and run paths before execution. Run a fresh inspection, author and
review the revised case model, and execute the current pipeline in the new
run. Preserve the demonstration's source snapshots and outputs. Changed
amounts require fresh source references and updated explanations as well as
recalculated schedules.

## Browser preview

The kit's XML, Markdown and text links open escaped reading pages in the
browser, with a return link to the relevant lesson step. PDF links show locally
rendered page images and offer the original download, so an unavailable embedded
PDF viewer does not leave the learner on a blank page. Run rendering with the
ready managed Python, which includes the declared PyMuPDF dependency. The original files
remain unchanged and are still the inputs in `execution-request.json`.

For actual CSV, Markdown, text or document results, use the verified result view when the
native file panel is unavailable, queued or hard to read:

```text
python scripts/local_courses.py results --workflow <exact-id> --language <language> --lesson-dir <lesson-files> --execution-record <demo-or-practice-execution.json> --output-dir <fresh-local-result-view>
```

This checks the actual execution record and source/output hashes before creating
a reading view outside the sealed run. It does not run the workflow or record
lesson completion. Serve that new directory with the `serve` command below and
inspect the rendered result in Codex's browser. For invoice summaries, add
`--columns invoice_number invoice_date total_amount currency anomalies file_name`
to start with useful columns. The complete original CSV text remains accessible
under each table. Explain the actual empty anomaly or duplicate files; do not
infer that invoices are booked, paid or professionally approved.

Keep the original output links in the working chat. The reading view is a
presentation of those results, never a substitute execution artifact. Word and Excel results open a local reading view of the actual stored text,
tables and visible sheets, with a return link and byte-verified original file.
These views do not reproduce document layout or recalculate spreadsheet formulas.
Open the relevant sheets and source references with the learner. PDF results
provide byte-verified original downloads; this page does not
pretend to render their contents. Show those documents in their native viewer
and verify the download or opening before claiming that it succeeded. Use actual visible browser evidence
before saying that the result is shown; do not stop at a queued panel request.

For local archive search, retain the complete native search and source-open
responses. The answer must address the requested facts, not just identify a
document or supplier. Cite the opened source with its actual locator and an
absolute Markdown file link (use angle brackets around paths with spaces).
Include that source among the execution record's inputs. The result reader
opens citations to recorded Markdown, text, CSV and XML inputs in local reading
pages with the verified original bytes; unrecorded paths and network links
remain plain text. Click the citation and inspect its content before recording
the checkpoint. After the practice update, refresh the same index, open both
the initial agreement and update, and preserve the demo answer.

For `course.html` and a retained kit's `example.html`, serve the rendered kit
with the installed product helper, using the same configured Python runtime:

```text
python scripts/local_courses.py serve --output-dir <absolute-rendered-kit-directory>
```

Keep this foreground command alive in a managed terminal session. It binds only
`127.0.0.1` on an OS-selected free port and emits a JSON `url` after binding.
Use that exact URL; do not assume a fixed port or interrupt another server.
The root is the kit directory, preserving relative CSS, fonts and linked inputs.
Do not serve the client workspace, copy just the HTML, or publish the kit online.
For `example.html`, replace only the final `course.html` URL component.

Prefer `open_in_codex` with `target: {type: "browser", url: <returned-url>}` in
the working task. Never use its `type: "file"` route to present HTML: that may
show source. If that control is unavailable, use an available browser control
to open the exact loopback URL in a visible tab. If no browser control is
available, provide a clickable HTTP link for the learner to open. If the local
server cannot run, report the preview as pending; a source tab is not a preview.

Report the actual tool state: `queued` means the opening request is queued,
not that the page is visible. For a hidden working task, tell the learner to
select that task and provide the same HTTP link. An `opened` response confirms
the tool action only; verify rendered content and asset loading with browser
inspection when available, or await the learner's confirmation before claiming
that they can see the page. Do not claim visibility from successful rendering,
an HTTP response or an opening request alone.

Keep the preview process running while the learner needs its links. Stop only
that process when the lesson is finished and no handoff needs the preview.
The helper serves local files on loopback; it does not upload them or record
lesson completion. Native model processing of content read in chat still applies.


## Notice intake

For `avviso-intake`, follow the delegated notice skill's source review and normal
reviewed note delivery. A letter mentioning F24 is not an F24 form. Record a
text-bound document-kind correction when needed; do not present candidate fiscal
fields as verified data. Show the actually reviewed `07_scheda_codex_per_studio.md`
as the operational note, with `avviso/avviso_intake_memo.md` and its CSV as the
extraction references. The practice adds a client's statement; documents said
to be recovered remain unreceived until their actual files are supplied. Keep
the explanation about the request, dates, evidence and next action.

## Scissione guidata

The fictional Arco mandate and allocation CSV exercise the Italian OIC partial
proportional route into a new beneficiary. Start without approvals. The missing
lease, unexamined contingent liabilities and null shareholder tax costs remain
visible; a calculation does not close those gaps. The teacher explains actual
Italian dossier headings and stable machine fields in the learner's language.
The learner reviews the displayed exact revision in ordinary professional terms;
never copy the test-only reviewer or manufacture participation.

Practice imports the updated mandate and CSV in a fresh run of the same tutorial
engagement, with the exact finalized prior revision as an upstream artifact.
Changed allocation evidence reopens its dependent reviews; unchanged route and
ownership evidence can retain theirs. Preserve the demo outputs. Codex uses its
teacher/worker pair; Cowork uses the packaged written single-conversation lesson.
Both keep tutorial state local and require actual learner confirmation.
