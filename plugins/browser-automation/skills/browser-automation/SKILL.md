---
name: browser-automation
description: Use when an authorized operator or developer wants Vera to discover, build, validate, or run a repeatable process on a website through their existing Chrome session. The workflow is site-generic and process-specific: it uses model-led exploration plus Playwright mechanics to produce portable capabilities for Agenzia delle Entrate, TeamSystem, Gmail, or another browser-based gestionale. Do not use it for ordinary web research, credential handling, or desktop-only application automation.
---

# Automazione web

Discover an authorized browser process and turn it into a portable, intelligent
capability that another operator can run in their own Chrome session. The
deliverable is a working process capability, not a recording and not a browser
session.

Read `references/capability-contract.md` completely before building, changing,
validating, or running a capability. For a new or changed process, also read
`references/discovery-playbook.md` completely.

Before the first local contract helper in a run, execute
`python scripts/check_dependencies.py` from this module. The core uses only the
Python standard library; this check must not install packages or access the
network. `requirements.txt` therefore declares no third-party runtime package.

The local deterministic scripts own only dependency readiness, contract shape,
origin bounds, forbidden secret and capture fields, validation-receipt rules,
hashes, owner-only permissions, and non-overwriting bundle output. They do not
decide what a page means, which process matters, which branch to follow, whether
a locator is semantically correct, or whether a professional result is sound.

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

Use `computer-use:computer-use` only when a required step is genuinely outside
the browser or its DOM, such as a native operating-system dialog. Never use it
as an alternate browser controller when Chrome is selected.

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

Use the discovery playbook. The model actively navigates the authorized site,
interprets each page, tests reversible actions, identifies semantic milestones,
collects robust locator candidates, follows relevant branches, and verifies the
end state. It is not a passive demonstration recorder.

Keep live inspection bounded to the declared process and allowed origins. By
default, query only targeted control roles, accessible names, labels,
placeholders, headings outside tables or grids, query-free paths, and generic
state markers. Do not request a full authenticated-page snapshot, business-row
content, message or invoice content, form values, or screenshots. If a process
cannot be understood without a specific private data class or screenshot, stop
once, name exactly what would enter the selected model context and why, and get
the operator's confirmation before reading it. Do not persist raw page content.

Write the sanitized discovery record to a fresh owner-only directory outside
the Git workspace. Validate it mechanically, let the operator review it, then
author a process-specific `capability.json`. Replace observed values with input
references. The model chooses workflow meaning and recovery; the validator does
not.

### Run an existing capability

Load exactly one explicitly named capability from either:

- `capabilities/<capability-id>/capability.json` in this module; or
- a capability folder path supplied by the operator.

Do not scan unrelated folders for capabilities. Validate the file before using
it. Confirm that the requested process, allowed origins, inputs, and side effects
match the operator's request. A `scaffold` is not executable; start live
discovery. A `discovered` capability may be tested but is not a proven handoff.
A `validated_local` capability was proven only in its recorded environment and
must still verify every current milestone.

Execute each action through `tab.playwright` with fresh page state. Try the
declared semantic locators in order, verify the postcondition, and use model-led
recovery when the UI has changed. If recovery changes a locator or branch,
update the capability and reset before counting a validation run.

For a `wait_for` action, wait until the declared control is visible and enabled
and the surrounding single-page application has settled for a short bounded
interval. Do not replace readiness checks with a long blind delay.

### Validate and hand off

A capability becomes `validated_local` only after two complete clean runs from
the declared start state, with no locator edits during either run. Successful
execution on one account or machine is evidence, not a guarantee that another
account or UI variant will work.

Seal the reviewed capability into a fresh directory with
`scripts/capability_contract.py`. Send only that sealed capability folder. Never
send the discovery directory, cookies, browser state, login material, page
captures, private values, or downloaded business files. The receiving operator
authenticates in their own connected Chrome and performs their own validation.

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

Material choices are the authorized site and process, allowed origins, start and
end states, runtime inputs and outputs, permitted side effects, any private data
class that must enter model context, and whether the result is a scaffold,
discovered capability, or locally validated handoff. Derive them from the actual inputs,
the operator's request, and current browser evidence. Ask only for unresolved choices
that change the run; facts already established by the operator are not choices
to propose. Ask only those unresolved choices in chat. Do not offer automation
frameworks, browser launchers, or capture formats unless the facts cue them.

## Included capabilities

- `gmail-search-proof`: a local proof capability for a synthetic, no-result
  Gmail search that reads no message content and creates no side effect.
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
   replay, validation, and portable output.
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
   capability draft or sealed folder, and when useful `codex_run_review.md` with
   status, evidence, unknowns, and next action but no copied page content.
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
