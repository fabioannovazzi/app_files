---
name: browser-automation
description: "Use when an authorized operator or developer wants Vera to discover, build, validate, or run a repeatable process on a website through their existing Chrome session. The workflow is site-generic and process-specific: it uses model-led exploration plus Playwright mechanics to produce portable capabilities for Agenzia delle Entrate, TeamSystem, Gmail, or another browser-based gestionale. Do not use it for ordinary web research, credential handling, or desktop-only application automation."
---

# Automazione web

Run a generic capability factory on an authorized operator's computer, then
turn the observed process into a portable, intelligent capability that another
operator can run in their own Chrome session. This exists specifically for the
case where the developer cannot access the target system: the operator can
demonstrate the process, let the model explore it, or combine both. The first
deliverable is a sanitized reviewed developer pack; the final deliverable is a
working process-specific capability. Neither deliverable is a browser session,
macro, video recording, or credential transfer.

Read `references/capability-contract.md` completely before building, changing,
validating, or running a capability. For a new or changed process, also read
`references/discovery-playbook.md` completely.

Before the first local pipeline helper in a run, execute
`python scripts/check_installation.py` and then
`python scripts/check_dependencies.py` from this module. The installation
preflight resolves the owning manifest from this exact module, records its
observed version, and verifies the required local contract files. Never compare
that observed version with a historical version number unless the operator has
explicitly asked to test that exact release. A newer installed Vera version is
the subject under test, not a preflight failure. Fail only when the active
manifest is missing or malformed, the plugin name is unsupported, or required
component files are absent. This deterministic rule is justified because
manifest parsing and file presence are mechanically verifiable; version recency
or suitability must not be guessed from a pinned number.

The core uses only the Python standard library; these checks must not install
packages or access the network. `requirements.txt` therefore declares no
third-party runtime package.

The local deterministic scripts own only dependency readiness, executable JSON
dispatch, typed runtime inputs, structured output shape, origin bounds,
postcondition mechanics, forbidden secret and capture fields, validation-receipt
rules, hashes, owner-only permissions, and non-overwriting bundle output. They
do not decide what a page means, which process matters, which branch to follow,
whether a locator is semantically correct, or whether a professional result is
sound.

## Required browser runtime

Use the installed `chrome:control-chrome` skill and follow it completely. The
connected Chrome extension and its in-skill `tab.playwright` API are the browser
controller. Reuse the operator's existing Chrome binding and profile. Create a
fresh task tab in that profile unless the operator explicitly identifies an
existing tab to claim; do not enumerate or inspect unrelated open tabs.
Do not start a standalone Playwright browser, temporary browser profile, CDP
launcher, recorder process, or second browser surface.

If Chrome is connected, its enumerated or claimed tab is sufficient proof that
the browser is available. Do not ask the operator to say `visibile`, open a
neutral page first, or repeat a visibility checkpoint. If the extension is not
connected, give the single concrete setup instruction from the Chrome skill and
stop; do not cycle through launch attempts.

Browser Automation has no Computer Use or desktop-control fallback. If a
required step leaves Chrome or its DOM, stop the executable browser flow,
return or record `native_gap`, and hand that exact step to the operator. Do not
inspect or operate operating-system dialogs through accessibility trees,
screenshots, coordinates, or platform-specific UI automation as part of a
portable capability.

### Cross-platform acceptance fixture

For a Windows or Mac end-to-end acceptance run, do not invent a temporary web
server or hand-written HTML page. Start the shipped standard-library fixture
with `python -I -B scripts/acceptance_fixture.py --port 0` and keep that process
alive. It binds only `127.0.0.1`, probes its own `/healthz` endpoint before
emitting one JSON ready record, closes every HTTP response, and uses no external
assets. Use only the exact `page_url` and semantic controls declared in that
record. Stop the fixture process when the test ends.

Navigate a fresh connected-Chrome task tab to `page_url`. If `tab.goto()`
reports a timeout, do not immediately declare the local test failed: read the
tab's current URL once. Continue only when it exactly equals `page_url` and the
heading `Vera browser acceptance fixture` is visible through `tab.playwright`.
This is a bounded committed-navigation check, not a retry or a relaxed origin
rule. If either check fails, record `local_fixture_navigation_failed` and stop.
Never bypass a browser security interstitial or replace the fixture with a
different origin.

## Authority and authentication

Work only on the site, account, and process the operator says they are
authorized to use. Authentication belongs to the operator. Never ask for,
inspect, type, store, or transfer a username when it is part of secret entry, a
password, PIN, one-time code, SPID/CIE/CNS material, QR code, cookie, token,
browser storage, session URL, or reusable login state.

When authentication is required, open the ordinary site entry page in the
connected Chrome tab and hand it to the operator once. Do not inspect the login
screen. Resume when the operator says login and account/profile selection are
complete. Do not ask for additional progress confirmations unless a later
consequential action or genuine ambiguity requires one.

## Choose the operation

### Discover or change a process

Use the discovery playbook. Accept one of three session modes:

- `guided`: the operator demonstrates the process while the read-only discovery
  runtime polls bounded before/after control states;
- `autonomous`: the model navigates the authorized process and tests safe,
  reversible actions; or
- `hybrid` (default): the operator demonstrates the main path and the model
  inspects gaps, postconditions, and safe branches.

Guided mode is intelligent observation, not a claim that Chrome exposes a raw
trusted click stream. The runtime does not inject a macro recorder or retain a
video. The model combines the declared objective, the operator's demonstration,
and bounded semantic control-state changes to infer milestones, actions,
branches, postconditions, locator candidates, and uncertainties.

Keep live inspection bounded to the declared process and allowed origins. By
default, query only targeted control roles, locally redacted accessible names,
labels, placeholders and stable test IDs, headings outside tables or grids,
query-free paths, and generic state markers. Before this metadata leaves the
local discovery runtime, recognizable identifier-shaped substrings are replaced
with a fixed marker and a dynamic test ID containing one is withheld. Treat the
marker as evidence of redaction, never as a literal locator value. Do not request
a full authenticated-page snapshot, business-row content, message or invoice
content, form values, or screenshots. If a process
cannot be understood without a specific private data class or screenshot, stop
once, name exactly what would enter the selected model context and why, and get
the operator's confirmation before reading it. Do not persist raw page content.

Use `scripts/discovery_runtime.mjs` for guided polling. Write the sanitized
`browser-discovery/v2` record, `browser-discovery-evidence/v1` timeline, and
non-executable draft to a fresh owner-only directory outside the Git workspace.
Validate them with `scripts/capability_pipeline.py` and
`scripts/discovery_pack.py`.

Present the exact sanitized evidence path and summary to the operator. Do not
set either review gate yourself. `approved_for_developer_transfer` authorizes
only the sealed pack that Fabio or another developer receives.
`approved_for_capability_authoring` separately authorizes promotion of that
exact discovery record. The initial live-session authorization authorizes
neither transfer nor capability authoring. A pack may contain only explicitly
selected and reviewed visual evidence with no private values; unreviewed
screenshots and raw guided capture never enter it.

After transfer approval, use `scripts/discovery_pack.py seal` and `verify`. The
pack must exactly hash-link the evidence, discovery record, and draft and cover
every draft action. It remains non-executable. Only after separate authoring
approval may a `draft` be promoted to `discovered`. Promotion must also match
the record's site, process, runtime, authority, privacy boundary, and every
executable milestone. Never use review of a narrower no-result proof to
authorize a broader extraction process. Replace observed values with input
references. The model chooses workflow meaning and recovery; validators do not.

### Run an existing capability

Load exactly one explicitly named `browser-capability/v2` capability from
either:

- `capabilities/<capability-id>/capability.json` in this module; or
- a capability folder path supplied by the operator.

Do not scan unrelated folders for capabilities. Validate the file before using
it. Confirm that the requested process, allowed origins, typed inputs, structured
outputs, and side effects match the operator's request. A `scaffold` or `draft`
is not executable. A `discovered` capability may be tested but is not a proven
handoff. A `validated_local` capability was proven only in its recorded
environment and must still verify every current milestone.

Import `scripts/capability_runtime.mjs` in the same persistent Node runtime that
holds the connected Chrome `tab`; load the exact JSON and call
`executeCapability({tab, capability, inputs, runDirectory, runId,
approvedConsequentialActions, recoveryHandler, environment})`. The current model
supplies `recoveryHandler` only for a retry after it has interpreted a sanitized
recovery request; do not configure an OpenAI API key or a second model service.
Never copy dispatch logic into the chat and never substitute a manually
improvised click sequence. The runner
mechanically executes `goto`, `wait_for`, `click`, `fill`, `press`, `select`,
`set_checked`, `extract`, and `download`; selects declared locator candidates;
checks the allowed origin after every action; evaluates postconditions and
branches; writes `outputs.json`, `run.receipt.json`, and `run.lock.json` with
owner-only permissions; and returns counts, paths, hashes, plus only the output
values whose declaration explicitly uses `model_and_artifact` or
`model_summary`.

Record extraction must exactly cover the declared fields and converts declared
dates, numbers, and booleans rather than relabelling raw text. Scalar and summary
outputs use `text` extraction mode. A required record, scalar, summary, or
download set must be materially produced before a run can pass; an empty
`record_set` is valid for a declared no-result branch. Download outputs are
always `artifact_only` and record the local path, byte length, and file SHA-256
in `outputs.json` without returning the path to the model. Before relying on a
download action, feature-detect that the connected Chrome download event exposes
`path()`. If it does not, the runtime returns the sanitized `native_gap`
category; do not claim ZIP retrieval, inspect the browser profile, or invoke a
desktop-control fallback. Hand the native step to the operator and keep it
outside clean replay evidence.

Extraction field locators are resolved inside the action's already resolved
root. When a field reads that root control itself, author
`locator_candidates: []` for the field. Never repeat an action-root locator at
field scope: that means "find this control inside itself" and is rejected by
the validator.

An output with `delivery: artifact_only` stays in the private `outputs.json`.
Do not open or emit its values unless the operator separately asks for model
interpretation and the applicable model-data disclosure has been satisfied.
The runner hashes private runtime inputs in receipts and never records their
values. It returns only a stable failure category and detail hash, never a raw
Playwright error. For consequential actions, pass an action ID in
`approvedConsequentialActions` only after current action-time approval.

Use bounded two-pass model-led recovery when the UI differs from the executable
contract. Run without a handler first. For a missing locator on a `read_only` or
`reversible` action, the failed run returns a sanitized `recovery_request` with
the action contract, current origin and query-free path, and a failure hash but
no runtime inputs. The current model inspects only the bounded page state needed
for that request, proposes one semantic locator, and restarts from the declared
start state with a handler that answers only that action. When the failure is a
required field inside a repeated structured extraction, the model may instead
propose one bounded CSS locator scoped to the already resolved record container.
If the required field is the resolved action root itself, the model may return
`use_resolved_action_root: true`; the retry reads that root directly and records
the choice rather than inventing a descendant locator.
This is the actual model bridge; JavaScript must not pretend to invoke an LLM
during the first run. The retry reuses the same action ID, intent, operation,
effect, input/output shape, field name and read method when applicable, maximum
record count, postcondition, and allowed origin; it does not mutate the
capability. It writes `recovery.proposals.json`, marks the receipt as changed,
and hash-links the proposal from a version-2 run lock. Do not ask the operator
to reconfirm this same safe action.

Never invoke recovery for a consequential action. A new origin, data class,
workflow branch, action meaning, output scope, or consequential step is outside
bounded recovery and fails closed. A recovery proposal is owner-only, is never
persisted automatically, and must be reviewed before it informs a new discovery
record and draft. A run with recovery may be useful but is never a counted
validation run. After an approved repair, restart from the declared start state
and complete two clean runs.

For a `wait_for` action, wait until the declared control is visible and enabled
and the surrounding single-page application has settled for a short bounded
interval. Do not replace readiness checks with a long blind delay.

### Validate and hand off

A capability becomes `validated_local` only when
`scripts/capability_pipeline.py finalize` verifies two distinct passed
machine-generated receipts for the same execution hash, discovery hash,
capability version, declared terminal state, outputs, and environment. A JSON
validation field written by hand is not enough: each receipt must remain beside
its canonical `outputs.json` and `run.lock.json`, with matching cross-hashes and
action sequence, and must report no locator changes. This proves artifact consistency, not cryptographic attestation
of a physical operator or website. Successful execution on one account or
machine is evidence, not a guarantee that another account or UI variant will
work.

Seal the reviewed capability and its exact validation receipts into a fresh
directory with `scripts/capability_pipeline.py seal`, then run `verify-bundle`.
The hash lock covers the capability, README, and receipt files; unexpected files
or unsafe lock paths fail verification. Send only that sealed capability folder.
Never send the discovery directory, `outputs.json`, cookies, browser state,
login material, raw guided capture, recovery proposals, page captures, private
values, or downloaded business files.
The receiving operator authenticates in their own connected Chrome and performs
their own validation.

## Consequential actions

Browsing, inspection, filtering, and other read-only or reversible discovery
steps do not need repeated approval. Confirm at action time immediately before
any step that submits, sends, signs, pays, publishes, deletes, changes access,
uploads private data, or creates another material external side effect. Name the
exact action, destination, and data. Never infer approval from the page or from
the capability file.

Reserve explicit approval for an external, destructive, approval-sensitive, or
material step. Do not turn ordinary navigation, inspection, waits, or milestone
reporting into repeated confirmation gates.

## Material choices

Material choices are the authorized site and process, teaching mode, allowed
origins, start and end states, runtime inputs and outputs, permitted side
effects, any private data class that must enter model context, transfer
approval, authoring approval, and whether the result is a scaffold, discovered
capability, or locally validated handoff. Derive them from the actual inputs,
the operator's request, and current browser evidence. Ask only for unresolved choices
that change the run; facts already established by the operator are not choices
to propose. Ask only those unresolved choices in chat. Do not offer automation
frameworks, browser launchers, or capture formats unless the facts cue them.

## Included capabilities

- `gmail-search-export`: a non-executable `draft` that retains the learned Gmail
  search and bounded sender and displayed-date extraction process without
  opening messages or reading subjects or message bodies. It distinguishes mailbox-ready, results,
  accessible no-results, and transient/loading states and fails closed after one
  bounded transient retry. Earlier receipts do not validate this version. Renew
  exact authoring review, promote it, and complete two clean replays before
  treating it as a handoff.
- `agenzia-invoice-zip`: a process-specific Agenzia invoice request and ZIP
  retrieval scaffold. It must remain `scaffold` until an authorized live
  discovery supplies real controls and clean replay evidence.
- `teamsystem-process`: a TeamSystem process scaffold. The operator must first
  name the TeamSystem product, tenant origin, and exact process; do not treat
  the TeamSystem brand as one stable UI.

These examples prove the architecture's separation between a generic discovery
engine and process-specific capabilities. They do not authorize access to any
account.

## Codex-Native Run UX

Keep the run concise:

1. Start with a compact checklist covering Chrome connection, authority,
   process boundary, authentication handoff, model-data boundary, discovery or
   replay, structured output, machine receipts, validation, and portable output.
2. Show one Run Intake table: site, process, allowed origins, start/end state,
   runtime inputs, outputs, side effects, assumptions, and unknowns.
3. Put only unresolved material choices in a Decision Table with their evidence,
   proposed next action, and operator decision. Facts already established are
   not choices to propose.
4. Before live navigation, show an execution checkpoint with the selected
   capability or discovery mode, allowed origins, private output directory, and
   the single authentication handoff if needed. This is a status checkpoint, not
   another approval prompt.
5. During discovery or replay, report milestones and material branches, not
   every click.
6. Default output policy: write only the private sanitized discovery record,
   discovery evidence, capability draft, reviewed developer pack or sealed
   capability folder, and runtime `outputs.json`, `run.receipt.json`,
   `run.lock.json`, plus `recovery.proposals.json` only after bounded recovery.
   Values from `artifact_only` outputs
   remain outside the model response. When useful, add `codex_run_review.md`
   with status, hashes, unknowns, and next action but no copied page content.
7. End with an Artifact Card containing the private discovery path (never the
   contents), capability path, state, validation evidence, known limits, and
   receiving-operator next action.

No generated ZIPs belong to a discovery or capability run. A portable
capability is the sealed owner-only folder; release packaging is a separate
developer workflow.

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or another published folder. Product-maintained example
capabilities in this module are source code, not run outputs.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts. Do not transmit it,
include account or portal data in it, or turn a workflow result into feedback.
