> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Model-led browser process discovery

Use this playbook only for a website and process that the operator is authorized
to inspect and automate.

## 1. Define the process boundary

Capture the target site, start state, objective, end condition, allowed origins,
runtime inputs, expected outputs, and any action that would submit, send, alter,
delete, sign, pay, publish, or otherwise create a material side effect. Ask only
for unresolved facts that change that boundary.

State once that the operator handles authentication. Never ask for, read, type,
store, or transfer a password, PIN, one-time code, cookie, token, QR code,
storage state, or session URL.

## 2. Connect to the existing browser

Use the installed Chrome control skill and its browser-extension runtime. Reuse
the current Chrome binding and profile, but create a fresh task tab unless the
operator explicitly identifies an existing tab to claim. Do not enumerate or
inspect unrelated tabs. Do not launch a separate Playwright browser or temporary
profile. A connected Chrome binding is the visibility proof; do not add a
repeated `visibile` checkpoint.

If the requested site needs authentication, navigate to the ordinary public
entry page and hand the visible tab to the operator once. Mark the tab as a
handoff while waiting. Resume only after the operator says authentication is
complete and no secret-entry screen is visible. Do not inspect the login page.

## 3. Explore semantically

At every step:

1. Inspect the current origin and query-free path, then query only the targeted
   control and state metadata needed for the next decision.
2. Interpret the page's role in the process and identify the next milestone.
3. Prefer Playwright role, label, placeholder, test-ID, or visible-text
   locators grounded in the current page.
4. Perform the smallest reversible action that tests the hypothesis.
5. Inspect the resulting state and record the transition, alternative branch,
   success evidence, and uncertainty.

Do not request full authenticated-page snapshots, table or grid rows, form
values, message or invoice content, or screenshots by default. If one specific
private data class or screenshot is necessary to understand the process, pause
once, identify the exact data and purpose, and obtain operator confirmation
before reading it. Never save it in discovery or capability artifacts. Use
Computer Use only when the next required step is genuinely outside the browser
DOM or Chrome runtime.

Pause immediately before a consequential action and identify the exact action,
destination, and data involved. Authentication is an operator handoff, not an
action for the model.

## 4. Write a private discovery record

Write `browser-discovery.json` to a fresh owner-only directory outside the Git
workspace and validate it with:

```bash
python scripts/capability_contract.py validate <private-path>/browser-discovery.json --kind discovery
```

The record contains semantic control descriptions, query-free paths,
transitions, branches, download shape, and uncertainties. It does not contain
page HTML, screenshots, credentials, private values, business records, message
content, browser state, network bodies, or downloaded bytes.

Ask the operator to review the private record before using it to author a
portable capability. This review concerns the sanitized record; the operator's
initial authorization already permitted live model inspection of the selected
post-login process.

## 5. Author and validate the capability

Create a draft `capability.json` from the reviewed record. Replace observed
values with declared input references, include multiple semantic locator
candidates where the evidence supports them, and retain unresolved branches as
known limits.

Run the capability from its declared start state. Repair failures with fresh
model interpretation, update the capability, reset, and then complete two clean
runs without locator changes. Only then mark it `validated_local` and add the
two bounded validation receipts.

Validate and seal it to a fresh handoff directory:

```bash
python scripts/capability_contract.py validate <draft>/capability.json --kind capability
python scripts/capability_contract.py seal <draft>/capability.json --output-directory <fresh-handoff-directory>
```

Never copy the private discovery directory into the handoff directory.
