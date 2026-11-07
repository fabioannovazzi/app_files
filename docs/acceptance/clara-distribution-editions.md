# Clara distribution candidates

**Correction:** the original reduced ZIP below is superseded and must not be
distributed. See [the dependency repair and deeper acceptance](clara-reduced-dependency-repair.md)
for the corrected candidate, exact hash and remaining limits. The full ZIP is unchanged.

Status: staged implementation and exact-package local acceptance completed, with
native-host and remote-receipt acceptance gaps retained below. No publication,
deployment, active installation replacement or professional acceptance claimed.

## Scope decision and observed dependency inventory

The complete website/Codex edition keeps the maintained source workflows,
components, MCP registration, interfaces and lifecycle hooks. The reduced
candidate is a bounded local-file edition, not a claim of browser-only support.

| Source workflow/surface | Candidate | Source-backed reason and boundary |
| --- | --- | --- |
| advisory-brief-planner | Retain, bounded | `scripts/validate_advisory_contract.py` validates local JSON and supplied source anchors; actual installed skills constrain handoff. Limit handoffs to retained skills. |
| html-deck | Retain standalone | Skill-local initializer, evidence binding, composer, builder and browser QA operate on files. Case-bound delivery and hosted feedback are removed; source fidelity and browser/visual checks remain. |
| claim-basis-map | Retain standalone | Skill-local renderer reads claims JSON/PPTX, writes Markdown and audit JSON and detects drift. Optional case-register integration is omitted. Model review still owns semantic support. |
| advisory-case-director | Exclude | Durable spine, case store, evidence return and downstream branches are a coordinated lifecycle. Its skill routes into interviews, research, reporting and deliverable validation. A limited candidate must not offer that complete lifecycle with those branches absent. Local case helpers do exist; absence is not proof they inherently require MCP. |
| advisory-deliverable-validator | Exclude | Composes case-direction return, lineage, reporting, deck correction and format validation. The retained deck's format/source checks do not impersonate full advisory validation. |
| reporting-engine | Exclude | Has local dataset and chart engines, but its exposed contract covers many capabilities, semantic acceptance, nested components and native `clara_report_open`. Removing that tool alone does not establish acceptance for the advertised analysis system. |
| business-planning | Exclude | Delegates to the shared business-planning component and its full case/financial/reporting lifecycle. Not replaced by a generic chat plan. |
| attribute-reporting, brand-fit | Exclude | Delegate to attribute-reporting and its stored retailer/catalogue snapshot infrastructure. Live data access and review need separate service acceptance. |
| hosted-interview | Exclude | `manage_hosted_interview.py` prepares, publishes participant links and retrieves hosted sessions. Server/service and external-participant behavior cannot be established by a package-only test. |
| transcribe | Exclude | Hosted voice capture/upload/retrieval and case transcript integration. Not substituted with invented transcription or persistence. |
| research-video | Exclude | Authenticated Mparanza narration service, returned voice bundles and media QA. Local rendering alone is not narrated-video acceptance. |
| deck-correction | Exclude | Hosted voice feedback, case revision packets, approval provenance and verification form a separate pipeline. Written standalone HTML revision remains inside html-deck only. |
| learn-with-clara | Exclude | Native teacher/worker pairing and course chat bridge. Remove lessons, catalog entries and onboarding offers. |
| Studio Archive/case infrastructure | Not exposed | CLI routes exist, but this candidate's retained tasks use selected files and ordinary output folders. No simulated Archive identities, persistence or approvals. |
| reporting/recovery | Adapt | Retain maintained local reporting/receipt helpers, replace native tool instructions with real CLI paths; distinguish local result, authorized transmission and verified receipt. |
| host connectors | Conditional | Keep genuinely callable host document/browser/connected-file tools. No bundled service registration is required merely to read an already connected source. |

Evidence owners: `plugins/clara/skills/*/SKILL.md`,
`plugins/clara/skills/clara/references/workflow-catalog.md`,
`plugins/clara/components.json`, `plugins/clara/.mcp.json`,
`plugins/clara/scripts/{model_data_report,workflow_usage,operational_incidents}.py`.

## Evidence and blocks

Exact artifact hashes and per-pipeline results follow below. Local harness
evidence is distinct from installed-host and visible native UI acceptance.
Privacy/reporting has its own outcome, independent of pipeline output.

Initial checkout contains unrelated course and reconciliation edits; preserved.
Lucia work is isolated in `/private/tmp/lucia-distribution-editions`; no edits to
that worktree. Existing unrelated branches/worktrees are not this task's property.

## Final staged artifacts

Candidates are retained under `output/clara-distribution-candidates-2026-11-06/`
(ignored build output), with `manifest.json` recording ZIP and source hashes.
Both retain source version **0.1.384** as unreleased review candidates; they are
not an assertion that a new version was published or installed.

| Candidate | Bytes | SHA-256 |
| --- | ---: | --- |
| `clara-website.zip` | 7,301,960 | `9c51336fa8d5a04d79995b32507493302252253e073d70c173c3544f9eb5c4ea` |
| `clara-marketplace.zip` | 1,292,405 | `454caba7e4c8d5c07f24137a8bb53d342e787144abfcb8cbbf7f7223a03b9cf8` |

`verify_package()` and `verify_chatgpt_upload(..., edition="marketplace")`
returned no drift errors against final source. The website ZIP retains the
root MCP entry, all three worker services, full skills, embedded components and
hooks. The reduced ZIP exposes exactly `clara`, `advisory-brief-planner`,
`html-deck`, and `claim-basis-map`; no root/nested MCP registration, app binding,
hook, teaching assets or teaching usage entries remain. Removed workflow source
contracts are retained only as historical privacy declarations, not as routing.
The installed privacy register covers only retained processes and services.

Build the reduced artifact explicitly:

```sh
source .venv/bin/activate
python scripts/build_codex_plugin_zip.py clara --edition marketplace \
  --chatgpt-upload output/clara-distribution-candidates-2026-11-06/clara-marketplace.zip
```

The default edition remains `full`. The website ZIP was built with the existing
`build_package()` and a `dataclasses.replace(package, output_zip=...)` staging
path, without replacing the public download. The shared dispatcher preserves
Lucia's concurrent `marketplace_entries()` interface. Its Lucia implementation
remains in that task's worktree and must be integrated with the shared dispatcher
when the two changes are combined; it is not duplicated in this Clara change.

## Exact-package execution evidence

`marketplace-acceptance/acceptance.json` and
`website-acceptance/acceptance.json` record commands, actual exit codes and
separate pipeline/privacy outcomes. Each run extracted the exact ZIP into a new
folder and used its own script paths, fixtures, incident state and outputs.
The maintained shared Python 3.12 dependency environment was reused after the
packaged checker verified it; this is not a fresh-OS installation test.

Both packages completed these cases:

1. **Assignment planning:** preserved Aurora Foods/Delta Retail, EUR 12.5 million,
   dated conditions, France exclusion and the explicit customer-loss question in
   a reviewed standalone-presentation contract. A changed amount was rejected
   and no canonical invalid contract was produced. Agent-authored review is
   recorded as agent work, not professional approval.
2. **HTML presentation:** composed a source-bound quantitative deck from synthetic
   financial/customer CSVs, retaining exact input hashes, evidence ledger,
   editable sources, standalone HTML and ZIP. Strict browser QA passed at
   1280×720, 1920×1080, 1024×768 and 390×844: 151 checks passed, one fragment check
   was inapplicable because no fragments were declared. Eight screenshots and a
   print-preview PDF were emitted. A modified evidence CSV was rejected by hash.
3. **Claim map:** produced Markdown and audit JSON from a synthetic PPTX and
   recorded calculation basis. The current deck passed; changing the tracked
   claim to $99.9m failed the drift check. Pass and failure audit files are kept
   separately.

All eight screenshots from the corrected pre-final fixture were inspected;
there was no clipping after the renderer fix. Final QA also passed after the
chart title was clarified to identify fractions of revenue. The portrait phone
view is a scaled presentation stage with small chart text and a rotate hint;
it is not a mobile reading-layout acceptance claim. Print generation was checked
mechanically, not by a professional reader. Touch/fullscreen behavior on physical
presentation hardware remains untested.

The full ZIP's isolated MCP startup/discovery check returned 13 tools across
three services (`website-mcp-startup.json`). This tests JSON-RPC startup and
catalogue parity, not visible native panels or every full-edition workflow.
The actual enabled host installation was `clara@mp-clara` **0.1.382**, while these
candidates are **0.1.384**. No candidate was installed into Fabio's active plugin.
Fresh native-chat routing, visible native UI and clean-machine setup remain open.

## Privacy/reporting outcome

For each retained workflow in each final package, the real report CLI created
JSON, readable Markdown and a retained privacy contract; validation succeeded;
`show` reopened the same report with unchanged bytes. These are in each
acceptance folder's `privacy/<workflow>/`. The recorded outcome is
**not measurable / host-attested**: synthetic fixtures, source code and helper
results were visible to this agent, but provider-level payload extent was not
measured. Empty counts are unknown, not evidence of zero model exposure.

Tests deliberately used local-only reporting. No signed server receipt,
Computer ID/userID linkage or remote delivery is claimed. Report checks did not
change pipeline outcomes or require professional reruns. The recorded contract
comparison is agent review of this bounded test, not compliance certification.

## Checks and integration boundary

- Retained workflow/edition regressions: **146 passed, 3 skipped**. The skips
  are existing optional browser integration cases; the final exact-package
  browser runs above were performed separately.
- Additional full HTML-deck, icon and update-notification checks:
  **52 passed, 2 skipped**.
- Black, Isort and `git diff --check`: clean for changed code.
- Mypy: no issues in the two new scripts. Bandit: no medium/high findings in
  those scripts. No repository-wide coverage or green merge-CI claim is made.
- Clean integration snapshot: full and reduced Clara and Lucia upload ZIPs
  built and verified without drift. All **15 shared upload regressions passed**
  across the completed run and the final fixture-only retry. Results are retained
  in `logs/clara-cross-product-*.xml`.
- The primary checkout's unrelated Vera reconciliation/course edits remain
  untouched. Its stale reconciliation/onboarding privacy review and an unbuilt
  immutable course attachment prevented using that dirty checkout as cross-product
  baseline. The integration snapshot starts at `c918bee5f` and overlays this
  task's shared/Clara changes plus the concurrent Lucia projection. It does not
  establish acceptance of those unrelated pending edits.

## Encountered blocks and recoveries

| Observation | Effect | Recovery and justification |
| --- | --- | --- |
| Existing Clara course hashes made teaching/download privacy reviews stale; the shared builder edit invalidated transport fingerprints. | Initial package refused to build. | Inspected the hash-only course changes and builder behavior, refreshed affected declarations and regenerated contracts. No privacy failure was used to reject a professional output. |
| Reduced allowlist omitted shared local-helper files. | Privacy fingerprint construction failed. | Retained the actual helper files; no fabricated dependency or bypass. |
| Installed privacy declarations require a real modules directory. | Reduced tree failed declaration validation. | Included a README-only empty component directory; components remain explicitly empty. |
| Initial edition omissions differed from the full host contract. | Projection rejected the package. | Reviewed and recorded exact excluded workstreams, services and paths in the edition policy. |
| First reduced dependency wrapper ignored `--managed-verify` and recursively re-entered setup. | Checks stalled; test processes were stopped. | Reused Clara's maintained checker with only its component list projected; an exact-package timeout regression proves verification terminates. This was a new-wrapper defect, not evidence against MCP-free execution. |
| Sandboxed browser launch returned exit 2. | Browser acceptance was unavailable in that attempt. | Repeated authorized synthetic testing with normal local browser access; original report retained. |
| Longest bar value label exceeded its SVG canvas at all four sizes. | Strict QA failed. | Reserved glyph space outside bar ends in the maintained renderer; positive/negative/zero regressions and final strict browser QA passed. Deterministic geometry is justified by measurable canvas bounds, not semantic judgement. |
| Harness expected exit 1 for altered evidence; composer correctly returned 2. | Harness falsely stopped after the expected rejection. | Corrected the harness expectation, preserving the rejection evidence. |
| Existing planner privacy test referenced retired path/schema. | Source regression failed. | Updated only the test to current `workstreams`/service fields. |
| First report harness saved evidence outside the report directory. | Build passed but validate could not resolve relative evidence. | Copied frozen evidence into each report folder and reran reporting only; all reports then validated/reopened. |
| Formatting during an early cross-product run changed governed hashes. | That run saw stale fingerprints. | Discarded that run as acceptance, finalized formatting, refreshed hashes and reran against stable source. |
| Clean source archive lacked ignored prebuilt upload/install ZIPs. | Existing package tests could not open fixtures. | Built those artifacts inside the temporary integration snapshot before retrying; no public download was replaced. |
| A manual MCP probe omitted the repository virtual environment. | Catalogue worker could not import jsonschema. | Repeated the documented check from the activated environment; isolated startup/catalogue check passed. This is not fresh-machine dependency acceptance. |
| Sandbox denied process inspection and remote DNS access. | Diagnostic inventory/remote branch count unavailable initially. | Authorized read-only escalated checks succeeded; no active user process or branch was changed. |

No Marketplace upload, draft, submission, publication, review cancellation,
support message, deployment, PR merge or active installation replacement occurred.

## Retained work and repository lifecycle

This task created **no branch, worktree or stash**. Implementation and staged
candidates are retained for the explicitly requested review. At verification:
**9 local branches, 8 actual remote branches, 9 registered worktrees, 0 stashes**.
The extra branches/worktrees belong to concurrent tasks and were preserved;
the repository is not at its one-branch/one-worktree steady state.
