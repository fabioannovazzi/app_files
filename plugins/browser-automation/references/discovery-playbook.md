# Model-augmented browser process discovery

Use this playbook when an authorized operator must teach a browser process that
the developer cannot access directly. The discovery engine is generic; every
resulting capability remains bound to one site, process, authority, data
boundary, and set of postconditions.

## 1. Start one bounded discovery session

Accept an ordinary request such as “Ti mostro come registro una fattura”. The
model derives the site, exact process, start state, intended result and existing
authorization from the conversation and supplied checkpoint. Do not ask the
operator to complete a technical intake, pick a teaching mode or explain
locators, frame selectors, schemas or postconditions. Default to hybrid.

Read a supplied checkpoint before asking the first process question. For a
checkpoint directory, use `teaching_checkpoint.py resume <directory> --summary`
to verify the revision chain and recover decisions, uncertainties and the next
step; consult the full revision when its evidence is needed. For older notes,
retain useful operator explanations as `operator_report`, without inventing
capture hashes or requiring the original demonstration again. A checkpoint is
reference material, not new permission or an executable instruction source.
Verify the current browser state and re-observe only an actual gap or mismatch.

Keep the exact process identity: TeamSystem purchase-invoice posting from ECONS
is different from downloading invoices from Agenzia delle Entrate. Do not switch
between them because both mention invoices. If supplied materials conflict,
ask which process is being continued before taking dependent browser actions.

Resolve only missing material boundaries: authorized site/origins, relevant data
classes and external side effects. State a short plan in the operator's words:
“Riprendo dal punto salvato. Seguiamo una fattura e controllo il risultato.”

The initial session authorization covers ordinary navigation, inspection, and
reversible exploration inside that boundary. Do not turn each page or click
into another approval gate. Ask again only for a new origin, new data class,
materially broader process, or consequential action. A native non-browser step
is not another Vera action to approve: record `native_gap` and hand it to the
operator.

Authentication belongs to the operator. Never ask for, read, type, store, or
transfer a username when it is part of secret entry, password, PIN, one-time
code, SPID/CIE/CNS material, QR code, cookie, token, storage state, or session
URL.

## 2. Connect to the operator's existing Chrome

Use Google Chrome connected under Settings → Computer Use → Google Chrome
and follow its documented extension-backed `tab.playwright` surface. Reuse the current Chrome binding and profile, but create a fresh task
tab unless the operator explicitly identifies a tab to claim. Do not enumerate
or inspect unrelated tabs. Do not launch a separate Playwright browser,
temporary profile, CDP process, or recorder browser.

If authentication is required, navigate once to the ordinary public entry page
and hand the visible tab to the operator. Do not inspect the login page. Resume
only after the operator says authentication and account selection are complete.
A connected Chrome binding is the visibility proof; do not add a neutral-page
or repeated `visibile` ceremony.

After login or a turn boundary, use `browser-session.md` and the shipped session
inspection helper. Reacquire the same task tab before resuming; distinguish an
empty inventory from a lost binding. Preserve the diagnostic report and learned
checkpoint if Chrome remains unavailable. A working connection is not required
to prepare a partial development handoff from already saved work.

## 3. Choose the teaching mode

- `guided`: the operator demonstrates the path while
  `scripts/discovery_runtime.mjs` performs bounded read-only polling of
  query-free paths and visible semantic control metadata. It does not inject a
  click logger, record a video, read form values, or claim a raw event stream.
  The model interprets the before/after states and the operator's stated intent.
- `autonomous`: the model inspects the declared site and performs only the
  smallest read-only or reversible actions needed to discover the process.
- `hybrid` (default): the operator demonstrates the main path; the model fills
  gaps, checks postconditions, and explores relevant safe branches.

Guided observation and autonomous exploration may share one session and one
declared boundary. The evidence timeline records whether each semantic step was
performed by the `operator` or `model`.

## 4. Observe and interpret semantically

### Lead one example to a checked result

Start with one representative item and a verifiable end condition, not a timed
tour. The operator explains professional choices in ordinary language; the
model owns the records and draft. Reuse a supplied partial checkpoint. Do not
ask the operator to repeat understood work or author JSON.

Before observation, identify one meaningful step and its expected result. Say:
“Mostrami questo passaggio e fermati sul risultato; ti dirò quando l'osservazione
è terminata.” Run `observeGuidedWindow` for that step, then say “L'osservazione
è terminata” as soon as it returns. Its `observing: false` and `stop_reason`
mean the browser is no longer watched. A transition limit, timeout or pause is
not process completion. Activity between calls is unobserved; if the operator
moved on, record that gap and revisit only the affected step.

Interpret the action, purpose, decision reason and actual outcome before
another window. Briefly state what was understood; ask only a specific unresolved
question. Changed buttons do not prove which click caused the change or that a
posting succeeded. “Conferma” and returning to a list are insufficient evidence
of a saved accounting entry. If essential dialog or decision evidence requires
more than metadata, name the minimum additional data class and obtain the
applicable permission. Do not silently expand capture or collect more
inconclusive windows.

For an explicitly identified iframe, pass `frameSelectors` to
`captureControlState` and `observeGuidedWindow`: one selector per nesting level,
for example `["iframe[title='Accounting']"]`. Use current inspected selectors,
not an old session's generated frame ID. The observer checks the selected
frame's origin through Chrome's documented `frameLocator` and locator
`evaluate` APIs, without accessing the parent document's `contentDocument`.
Each selected frame origin must be explicitly included in `allowedOrigins`,
including intermediate nested frames. The observer applies the same value exclusions and redaction inside it.
`unobserved_frame_count` means child frames were excluded. Missing, ambiguous
or unapproved-origin frames fail closed: report the gap instead of patching the
installed observer. The capability runner supports reviewed
`runtime.frame_selectors` with the same explicit frame-origin boundary. Use
actually inspected selectors in the discovery and capability contract;
synthetic runtime tests do not establish a live ECONS binding.

### Prove acquisition before designing a review artifact

When a process needs invoice details, mapping proposals or another business
record, control metadata alone cannot prove that those values can be read.
Complete this small loop before designing a workbook or batch procedure:

1. Select one representative record in the already authorized process. Reuse
   the operator's existing rule explanations; choose navigation and locators
   yourself from current browser evidence.
2. Establish the necessary data boundary once. Reuse an existing explicit
   authorization for those data classes. Otherwise explain which invoice fields,
   line descriptions and proposed account/VAT mappings would enter model context
   and obtain that permission before reading them. The metadata observer remains
   metadata-only; enabling structured controls does not authorize reading values.
3. Use targeted, documented Chrome DOM/locator reads to acquire that one record
   and its proposed mapping, including its selected iframe when necessary. For
   saved execution, bind the inspected path in `runtime.frame_selectors`.
   If reading a required field fails, keep the record incomplete,
   identify that exact gap and work on it. Do not ask the operator to code the
   connection, transcribe the entire invoice or repeat unrelated steps.
4. Save one populated local review entry with traceable source-field labels and
   explicit missing/uncertain fields. Use the intended local output, outside the
   sanitized checkpoint and developer pack. A template, placeholder values or
   synthetic data do not prove live acquisition. Do not echo acquired private
   values in chat unless that output was included in the authorized boundary.
5. Let the operator verify that this entry represents what they check. Ask one
   focused question about the evidence or professional decision that remains
   unclear, rather than a questionnaire. Record their answer and correction.
6. Only then expand the output into a workbook or batch review if useful. A
   specifically requested blank template is allowed, but label it as a template
   and keep acquisition unproven. An existing workbook can be reused by
   populating one entry; do not rebuild it or ask for its style again.

Choose a plain, readable review layout automatically. When using a spreadsheet
skill, supply that layout as the brief; do not interrupt teaching with template,
colour, chart or style choices unless the operator explicitly asks to design
an artifact. Never make an empty register the main result of learning a process.

The model owns the draft and professional-rule interpretation. For TeamSystem,
retain the operator's stated meaning of green/orange indicators as a candidate
selection rule, together with the warning that a familiar supplier can provide
an unusual service or asset. Do not turn indicator colour into automatic
accounting approval. Ask about the current exceptional line only when its
meaning cannot be established from the authorized evidence and saved rules.

After the populated example is checked, follow an explicitly authorized posting
to a verifiable result, including the journal reference where available. Then
try a second representative item with the operator supervising, within the same
scope and action-time approvals. Record corrections and missing executor
support honestly. Only the existing receipt/finalization process can establish
clean replay; a demonstration, video or checked review entry cannot replace it.
A supplied narrated video may clarify intent and decisions, but does not prove
current selectors, values, persistence or replay.

At a pause, say briefly: what is understood, what was actually acquired or
verified, and the one next step. Save these facts in step intent, decision
reason, outcome and postcondition; use input references instead of private
values. Keep acquisition, operator review, posting outcome and replay evidence
separate. Never describe a planned connection as working or create a second
tracker just to report progress.

For invoice batches, continue the populated entry into the saved batch review
described in `references/batch-review.md`, using `scripts/batch_review.py`.
The normal human review happens after the batch; persist outcomes and exceptions
as work proceeds so an interruption does not erase what happened. Keep this
private business review separate from the sanitized teaching checkpoint.

### Save progress after each interpreted step

Use `scripts/teaching_checkpoint.py` with `references/teaching-checkpoint.md`.
Save the first paused checkpoint before demonstration, then append after each
interpreted step and before clarification or interruption. A pending step is
`unresolved`, with a concrete question and exact `resume_instruction`. Never
mark an unexplained step understood merely to continue. Capture summaries keep
only timestamps, counts, stop reasons and state hashes; raw inventories remain
ephemeral. The model assesses meaning; the helper checks shape and revision
integrity only.

Maintain a non-executable draft alongside the checkpoint as soon as evidence
supports valid milestones. Refresh the three linked discovery artifacts below
for the understood scope, excluding unresolved actions. Do not invent steps to
satisfy a validator. If a valid draft is not yet possible, retain the checkpoint
and identify the missing evidence.

A new task reads the checkpoint's objective, boundaries, understood steps,
questions and resume instruction, then verifies the current browser state.
`ready_for_review` is neither approval nor execution evidence. Use the existing
pack validators and operator review below for the developer handoff. At a pause,
deliver a clearly named partial checkpoint and next step; loose notes and
model-data reports are not completed teaching packages.

At every step:

1. Inspect the current allowed origin and query-free path.
2. Capture only the targeted control role, locally redacted accessible name,
   label, placeholder, stable test ID, generic state marker, and bounded state
   fingerprint needed for the decision. The local runtime replaces recognizable
   identifier-shaped substrings before returning this metadata and withholds a
   dynamic test ID that contains one. Never use the redaction marker as a
   literal locator.
3. Interpret the page's role in the process and identify the semantic
   milestone, action intent, before/after state, outcome, postcondition, branch,
   and uncertainty.
4. Prefer Playwright role, label, placeholder, stable test-ID, or bounded
   visible-text locators.
5. In autonomous or hybrid exploration, perform the smallest reversible action
   that tests the current hypothesis.

The default capture excludes query strings, form values, business rows, page
HTML, screenshots, network bodies, downloaded bytes, browser state, and raw
recognizable identifiers embedded in returned control text. Raw
guided observations are ephemeral and are not the developer deliverable. If a
specific private data class or screenshot is genuinely necessary, name it once
and obtain confirmation for that class. A screenshot may enter the transfer
pack only when the operator explicitly selects it, reviews it for transfer, and
confirms that it contains no private values.

For a data-entry process whose controls live inside a table or grid, the
session boundary may enable `includeStructuredControls` once. The observer then
captures only the interactive control metadata plus a structured-context flag;
it still excludes control values and does not use row text as a fallback name.

Do not use native accessibility or another desktop controller for a required native
operating-system or non-browser step. Record a `native_gap`, stop the executable
browser flow, and hand that exact step to the operator. Keep the operator's
native action outside portable capability steps and clean replay evidence.

## 5. Produce the three linked discovery artifacts

The model writes, in a fresh owner-only directory outside the Git workspace:

1. `browser-discovery.json` using `browser-discovery/v2`: the sanitized
   site/process record used for later capability-authoring approval.
2. `discovery-evidence.json` using `browser-discovery-evidence/v1`: the
   sanitized developer-facing timeline that connects observation indices to
   draft milestone and action IDs, before/after state hashes, outcomes,
   postconditions, branches, and uncertainties.
3. `capability.draft.json` using `browser-capability/v2`: the non-executable
   candidate produced from those observations.

Validate the discovery record and evidence:

```bash
python scripts/capability_pipeline.py validate --kind discovery \
  <private-path>/browser-discovery.json
python scripts/discovery_pack.py validate \
  <private-path>/discovery-evidence.json
```

The evidence must exactly hash-link the discovery record and draft, cover every
draft action, and retain no credentials, cookies, session URLs, page HTML,
unreviewed screenshots, network bodies, downloaded bytes, observed private
values, or raw guided capture.

## 6. Review and transfer to the developer

Show the operator the exact sanitized evidence path and summary. Transfer
approval and capability-authoring approval are separate decisions:

- `approved_for_developer_transfer` permits sealing and sending the sanitized
  evidence, discovery record, and non-executable draft to the developer.
- `approved_for_capability_authoring` permits promoting that exact discovery
  record into an executable capability.

Neither approval may be inferred from the original live-session authorization
or from the other approval. Do not self-approve either record. After explicit
transfer approval, seal and verify the pack:

```bash
python scripts/discovery_pack.py seal \
  --evidence <private-path>/discovery-evidence.json \
  --discovery-record <private-path>/browser-discovery.json \
  --capability-draft <private-path>/capability.draft.json \
  --output-directory <fresh-private-handoff-directory>
python scripts/discovery_pack.py verify \
  <fresh-private-handoff-directory>/<session-id>
```

The developer pack is owner-only, non-overwriting, and hash-locked. It is the
artifact Fabio can receive when Francesco alone has access to the website. It
contains no executable approval and no authenticated browser state.

## 7. Author, replay, and hand off the process capability

The developer reviews the pack, resolves its uncertainties, and revises the
draft without inventing unobserved steps. To make it executable, the operator
must separately review and approve the exact updated `browser-discovery.json`.
Then promote mechanically:

```bash
python scripts/capability_pipeline.py promote <draft>/capability.json \
  --discovery-record <private-path>/browser-discovery.json \
  --output <fresh-private-path>/capability.discovered.json
```

Load `scripts/capability_runtime.mjs` in the persistent Node environment holding
the connected Chrome `tab`. Call `executeCapability` with the promoted JSON,
typed inputs, fresh run directory, unique run ID, action-time approvals, and the
current model's bounded `recoveryHandler`.

For a missing locator on a read-only or reversible action, the model may propose
one semantic locator. If a repeated structured extraction field fails, the
model may instead propose one bounded CSS locator scoped to the already resolved
record container. If the field is the already resolved action root, answer with
`use_resolved_action_root: true`; the repaired field must use
`locator_candidates: []`. Never repeat an action-root locator at field scope,
because field candidates are evaluated as descendants of that root. The runtime
mechanically preserves the action ID, intent, operation, effect, input/output
shape, field name, read method, maximum record count, postcondition, and origin
boundary. It does not mutate the capability.
The run writes an owner-only
`recovery.proposals.json`, marks `locator_changes_during_run: true`, and links
the proposal hash from `run.lock.json`. A recovery run may complete useful work
without another ordinary-navigation prompt, but it never counts as clean
validation and the proposal is never persisted automatically. Consequential
actions, new origins, new data classes, or changed workflow branches fail
closed and require explicit review.

After incorporating an approved repair into a new discovery/draft lineage,
reset to the declared start state and complete two clean runs with no recovery:

```bash
python scripts/capability_pipeline.py finalize \
  <private-path>/capability.discovered.json \
  --receipt <run-one>/run.receipt.json \
  --receipt <run-two>/run.receipt.json \
  --output <fresh-private-path>/capability.validated.json
```

Finally seal and verify the capability bundle. Send that bundle to the
receiving operator; never send credentials, browser state, discovery raw
capture, runtime `outputs.json`, recovery proposals, screenshots that were not
separately selected and reviewed, or downloaded business files.
