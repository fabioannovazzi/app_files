# Shared Vera / Clara Business Planning — local implementation evidence

Date: 2026-09-05. This is implementation and synthetic evaluation evidence, not a
client business plan or a release approval.

## Observed starting point

The canonical module was `plugins/business-planning/`. Its financial and strategic
entry points used different v1 cases, renderers and optional counterpart files.
The counterpart checks compared identity, shared context and assumption text;
they did not enforce financial-number equality across narratives. The existing
source records did not contain the requested file-level provenance manifest.
The original focused suite passed all 35 tests before implementation.

No evidence establishes that the previous Wine report used those registered
commands. This task did not open or patch that report or use any client documents.
The fixture reproduces the contradiction classes in the request using invented
figures, names, text files and explicit synthetic review attestations.

## Implemented behavior

Both registered commands now invoke `planning_cli.py`, `planning_workflow.py` and
`planning_report.py`. Vera retains its exact Studio Archive receipt boundary;
Clara retains its case-workspace boundary. Owner changes the visible product,
not the financial authority or case register. Strategic contributions are
model-authored reviewed sections of the shared case, obtained internally by the
invoking workflow. The compiler does not initiate a second model API request.

The shared v2 contract provides:

- Every selected file's hash, version, role, review status, audience and
  confidentiality restrictions, rechecked before compilation.
- Separate facts, assumptions, labelled hypotheses, source observations,
  professional decisions and canonical calculations, with input-level references.
- Visible source comparisons and explicit reviewed resolutions. Accepted-value
  disagreement blocks readiness; unresolved material conflicts remain partial.
- Vera's existing linked-statement arithmetic plus the requested margins, funding,
  runway, revenue break-even, debt service/DSCR and sources-and-uses calculations.
- Identical financial calculation registers for both owners. Clara's numerical
  narrative claims bind exact calculation IDs and expected values.
- Rejection of unbound numbers, unsupported rubric-based claims, and precise
  funding recommendations when required inputs or material reviews are incomplete.
- A single HTML compiler, optional PDF solely from validated HTML, canonical
  JSON/CSV, source manifest, reconciliation, validation and hashed output receipts.
- Audience releases bound to the exact source hash. `internal_only` material
  cannot be exported to another audience merely by changing an audience list.
- Canonical-data EBITDA comparisons/scenarios, cash before/after financing,
  funding gaps and sources-and-uses waterfalls. Optional channel unit economics
  first reconcile channel revenue and variable costs to the aggregate model.

Legacy v1 cases and separate counterpart files cannot finalize reports. Their
migration requires actual provenance and review; the software does not fabricate
an upgrade. The old arithmetic helpers remain for inspected calculation behavior.

## Regression evidence

Fixture: `tests/fixtures/business_planning/case.json`, with three synthetic text
files in its `sources/` folder. No original client names or documents are included.

The base scenario contains reported EBITDA **+200**, accepted adjusted EBITDA
**-100**, monthly operating cash flow **-110**, opening cash **50**, equity **500**
arriving in the second month, and a second-month principal repayment of **50**.
The model yields closing cash **-60, 280, 170**, pre-financing funding requirement
**330**, and residual timing gap **60**. These are test values, not professional
recommendations. Optional synthetic channel calculations give contributions per
unit of **20** and **10** after aggregate reconciliation.

Tests cover restoration of positive EBITDA, stale Clara claims, unresolved
conflicts, missing debt repayment, unconfirmed assumptions, unsupported scores,
benchmarks and KPIs, valid reviewed rubric support, audience release and bypass
attempts, source/hash/ID/reference tampering, chart and statement tampering,
output receipts, undefined ratios, optional PDF failure persistence, all company
stages, channel reconciliation and both actual registered CLI entry points.

## Exact focused checks

All Python commands used the repository `.venv`.

```bash
source .venv/bin/activate
pytest -o addopts='' -q tests/plugins/test_business_planning.py \
  tests/plugins/test_business_planning_shared.py \
  --cov=planning_workflow --cov=planning_report --cov-report=term-missing
```

Observed: **77 passed in 11.98 seconds**. Coverage of the two new calculation/report
modules: **94%** (workflow 97%, report 91%; 569 statements, 34 missed). This is not
whole-repository coverage. The actual optional browser/PDF run below exercises the
renderer outside pytest's coverage collection.

```bash
pytest -o addopts='' -q tests/plugins/test_codex_plugin_packages.py \
  tests/plugins/test_vera_client_workflow_filesystem.py \
  -k 'business_planning or business-planning or material_choice_intake or codex_native_run_ux_contract' \
  tests/plugins/test_plugin_icon_theme.py
pytest -o addopts='' -q tests/plugins/test_plugin_icon_theme.py
```

Observed: **5 passed, 518 deselected** in the targeted run; **3 icon tests passed**
in the separate unfiltered icon run. Black and Isort checks passed for all nine
changed Python files. Mypy (`--follow-imports=skip`) reported no issues in the three
new production modules. Bandit found no issues there. `git diff --check` passed.

Full logs are under `/private/tmp/business-planning-validation/`, notably
`focused-tests-final.log`, `targeted-plugin-tests.log`, `package-tests-final.log`,
`privacy-tests.log`, `filesystem-tests.log`, and `package-check.json`.

## Packaging and broader checks

The canonical package builder's `build_package` and `verify_package` APIs were run
with only `output_zip` redirected to temporary paths. This preserves the already
modified release artifacts in the primary checkout. Both resulting ZIPs verified
against current canonical source with **zero errors**:

- `/private/tmp/business-planning-validation/packages/vera-plugin.zip`
- `/private/tmp/business-planning-validation/packages/clara-plugin.zip`

Vera's packaged MCP check initialized all **18 servers** and listed their tools.
The bundled Node runtime was put on PATH for this check. No manifest versions,
Marketplace state, published-version registry or deployment were changed by this
task. The temporary ZIPs are validation artifacts, not published releases.

The two Business Planning privacy records were substantively updated and their
fingerprints refreshed. Vera's complete privacy validator passed. Clara's
validator reports two stale **unrelated hosted-service** records:
`plugin-update-check` and `research-video-voice`; these were not blindly refreshed.
The full privacy test run had **40 passed, 1 failed** (Clara register freshness).

The broader package/update test run had **379 passed, 11 failed**. These failures
must not be described as a green release gate:

- `test_configured_plugin_zips_match_repo_source`
- `test_chatgpt_upload_entries_put_each_plugin_manifest_at_zip_root[vera]`
- `test_committed_chatgpt_upload_uses_approved_card_copy[vera]`
- `test_configured_bundle_zip_matches_repo_source`
- `test_changed_plugin_sources_bump_manifest_version`
- `test_extracted_clara_renders_known_period_comparison`
- `test_extracted_clara_renders_distribution_with_variant`
- `test_all_dependency_checkers_accept_explicit_requirements_files`
- `test_standard_family_plugin_manifests_use_family_homepages`
- `test_homepage_is_one_semantic_story_with_all_three_plugins`
- `test_published_manifest_is_not_behind_installed_marketplace[plugin_root0]`

These include deliberately untouched committed package/version gates and unrelated
repository failures. In particular, the dependency-checker failure identifies
`check-entries`' implementation file-count contract, not Business Planning.
Other tasks were working in the checkout during this run, so these results record
the exact sampled runs rather than asserting a frozen global repository state.

The final full `test_vera_client_workflow_filesystem.py` run had **119 passed,
22 skipped, 6 failed**. The failures are the two `aml-review` inventory/CLI
classification checks and four `check-entries` / `journal-bank-reconciliation`
review-writer preflight checks reporting their implementation file-count contracts.
Business Planning's managed-context test passes. See `filesystem-tests.log` for
the exact parametrized failure names and command output.

## Visual and PDF inspection

The compiled synthetic report was rendered in local Chromium with network
requests disabled. The sandbox initially prevented Chromium startup; the permitted
local rendering retry succeeded. No client data or network destination was used.

Report:
`/private/tmp/business-planning-validation/final-preview-v2/report/business_plan_review.html`

PDF:
`/private/tmp/business-planning-validation/final-preview-v2/report/business_plan.pdf`

Observed: **8 charts**, **307 authoritative calculation records**, no JavaScript
page errors and no page overflow at desktop **1280 × 1000** or mobile **390 × 844**.
Visual inspection covered the header, negative EBITDA scenarios with a labelled
zero line, reported/adjusted EBITDA, financing-timing cash chart, waterfall,
provenance table and mobile layout. The separate supported-channel chart was also
rendered and visually inspected (`final-preview-v2/channel.png`).

The PDF is **45 pages / 474,408 bytes**, including the complete calculation and
provenance appendices. Text extraction found the title, provenance section and
all three source hashes. The final production compiler reproduces the inspected
HTML byte for byte, and every output hash in its execution receipt verifies.

## Remaining limits and workspace preservation

- No live client/Wine-case execution or historical run attribution was performed.
- The model and professional must select sources, extract/align observations,
  assess completeness/materiality and review strategic meaning. Hashes and ID
  closure cannot prove truth or detect a material claim omitted at intake.
- Review metadata records an operator's attestation; it does not authenticate a
  professional's identity or replace professional review.
- Periods are monthly. Intramonth liquidity, deferred tax, leases, asset disposals
  and lender-specific DSCR definitions are outside this financial contract.
- Revenue break-even assumes the accepted variable/fixed cost split. Beyond-horizon
  runway remains unknown. Missing required financial inputs withhold calculations
  and precise funding recommendations rather than being converted to zero.
- Optional PDF needs the declared Playwright dependency and a provisioned Chromium
  browser. The workflow does not install a browser or arbitrary runtime packages.
- This task edited no path that was dirty at its start: scope overlap **zero**,
  recorded in `change-scope.json`. It created no branch, worktree or stash and
  preserved unrelated work. Other tasks cleaned up their own temporary branches.
- Final observed lifecycle counts: **1 local branch, 1 live remote branch,
  1 registered worktree, 0 stashes**. The remote count came from `git ls-remote
  --heads origin`, not a stale remote-tracking list.
- No deployment, publication, merge, PR or Marketplace-version update was performed
  by this task. The requested implementation remains local for review.

## Authorized deployment validation

The subsequent explicit deployment request was validated in an isolated worktree
on `4f4cd88e` (current origin/main), preserving the primary checkout. Release
source versions: Business Planning 0.2.3, Vera 0.1.194, Clara 0.1.165.
Marketplace published-version records are unchanged.

- Focused regression command above: **77 passed in 9.14s**, **94% coverage**.
- Black/Isort on nine changed Python files; Mypy (`--follow-imports=skip`) and
  Bandit on three new production modules; `git diff --check`: passed.
- `build_codex_plugin_zip.py vera clara --check` and
  `build_claude_plugin_zip.py vera clara --check`: passed; Vera's 18 packaged
  MCP servers initialized and listed tools. Both OpenAI upload ZIPs rebuilt.
- Wider suite: `test_codex_plugin_packages.py`,
  `test_plugin_update_notifications.py`, `test_claude_plugin_packages.py`,
  `test_vera_client_workflow_filesystem.py`, `test_vera_privacy_surfaces.py`,
  `test_clara_privacy_surfaces.py`: **597 passed, 8 failed**. The upload-card
  check ran before its rebuild completed; its rerun passed (3 card checks).
- All seven remaining failures reproduced on a clean `git archive origin/main`
  snapshot: Clara period and distribution PNG expectations, old homepage
  structure expectation, Clara installed/published-registry drift, generated
  Cowork catalog drift, and two AML CLI inventory assertions. They are baseline
  issues, not Business Planning regressions; this is not a green full suite.
- Both privacy surface validators report complete and current. Version-only
  fingerprints and the shared page-file fingerprint were refreshed after
  inspecting their governed changes; service runtime code is unchanged.

Exact session logs and offline visual artifacts are retained under
`/private/tmp/business-planning-validation/deploy-*` on the development machine.
