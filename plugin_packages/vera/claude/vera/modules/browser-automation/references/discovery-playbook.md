> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Model-augmented browser process discovery

Use this playbook when an authorized operator must teach a browser process that
the developer cannot access directly. The discovery engine is generic; every
resulting capability remains bound to one site, process, authority, data
boundary, and set of postconditions.

## 1. Start one bounded discovery session

The operator supplies one natural-language objective covering:

- the site and exact process to reproduce;
- the authenticated start state and verifiable end condition;
- the permitted origins;
- runtime inputs and intended outputs;
- actions that would submit, send, upload, alter, delete, sign, pay, publish, or
  otherwise create a material side effect; and
- any private data class that the model must inspect to understand the process.

Use this reusable prompt shape:

> Discover a reusable capability for `[process]` on `[site]`. I am authorized
> and I will authenticate personally. Mode: `hybrid`. I will demonstrate the
> main path; explore safe reversible branches when useful. Stop immediately
> before consequential actions unless I approve them. Produce a sanitized,
> reviewed developer pack and a non-executable capability draft.

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

Use the installed Chrome control skill and its extension-backed Playwright
surface. Reuse the current Chrome binding and profile, but create a fresh task
tab unless the operator explicitly identifies a tab to claim. Do not enumerate
or inspect unrelated tabs. Do not launch a separate Playwright browser,
temporary profile, CDP process, or recorder browser.

If authentication is required, navigate once to the ordinary public entry page
and hand the visible tab to the operator. Do not inspect the login page. Resume
only after the operator says authentication and account selection are complete.
A connected Chrome binding is the visibility proof; do not add a neutral-page
or repeated `visibile` ceremony.

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

Do not use Computer Use or another desktop controller for a required native
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
