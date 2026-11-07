# Reduced Clara dependency repair

A [second independent audit](clara-reduced-second-audit.md) subsequently tested
a newly provisioned temporary runtime, reporting lifecycle, recovery and a read-only
installation. The corrected ZIP hash is unchanged.

The initial reduced candidate contained broken unused case machinery. Local happy-path
acceptance did not establish dependency completeness. It is superseded; do not distribute
`clara-marketplace.zip`. The corrected staged candidate is
`output/clara-distribution-candidates-2026-11-06/clara-marketplace-fixed.zip`.

SHA-256: `f86dbc35ca5274e6c55dab43aa83b7fc087d56a1e9352f4317411cb29cc21af0`.
The machine-readable `corrected-manifest.json` records source hashes and evidence paths.
The existing full website ZIP has its original hash and was not changed.

## Findings and changes

- The shipped `advisor_case_core.py` imported absent `decision_narrative.py`;
  importing it reproduced `ModuleNotFoundError`. Its bundled legacy-PowerPoint
  normalizer depended on that module. Neither is called or offered by the three
  retained workflows. Both are now omitted. The reduced privacy projection records
  the exact omitted governed path; full Clara retains its source unchanged.
- Retained diagnostic context hydration lazily imports `vera_assurance` from a
  shared vendor directory. That library was absent. The corrected ZIP includes
  its maintained library and internal dependencies, without adding Archive routing
  or MCP. Regression checks exercise legacy context loading and rejection of an
  invalid portable context through the actual validator, rather than an import error.
- A claim-map instruction still described an omitted advisory validator as its
  consumer. The reduced instruction now describes its standalone audit output.
- Added exact-package import-presence checks and isolated startup tests for 13
  documented entrypoints. These checks mechanically detect missing modules; they
  do not judge the semantic quality of professional advice.
- Expanded the reusable acceptance runner with isolated Python execution, an explicit
  helper interpreter option, standalone revision acceptance/rejection, revised-deck
  browser QA, and invalid privacy-report validation with unchanged deliverable hashes.

## Final exact-package evidence

Evidence root: `output/clara-distribution-candidates-2026-11-06/`.

- **22 packaging tests passed**, including full-edition preservation, source-engine
  parity, missing local imports, absent unused case helpers, dependency verification,
  integrity rejection, 13 isolated CLI startups and lazy diagnostic dependencies.
- **171 engine tests passed, 4 browser tests skipped** in
  `/private/tmp/clara-reduced-corrected-isolated`. Only the corrected ZIP was extracted
  under `plugins/clara`; tests and their synthetic fixtures were copied separately.
  No complete source plugin or sibling plugin was present there. Python used `-I`
  and empty `PYTHONPATH`. The test interpreter retains its existing third-party
  packages (including the repository's unrelated editable privacy-filter package);
  this is not proof of fresh dependency installation.
- **27 CLI calls matched expected outcomes** in `marketplace-corrected-final/acceptance.json`.
  They used the shared Python runtime with `-I`; its observed import path contained
  only standard Python paths and shared site-packages, with no repository source.
- Assignment contract creation passed; changing a supplied amount was rejected.
- Source-bound HTML composition/build passed; modifying the underlying CSV was rejected.
- A declared slide revision passed inspection, map validation and comparison;
  changing revenue on an untouched slide was rejected.
- Original and revised HTML each passed **151 browser checks** over four viewport
  sizes, with eight screenshots each. One fragment check per run was inapplicable.
  Actual browser QA ran outside the sandbox that prevented Chromium startup.
  Representative revised desktop and mobile screenshots were inspected; desktop
  wording fits, while mobile remains a small scaled presentation with a rotate hint.
- Existing PowerPoint claim checking passed; altered claim text was rejected.
- Each workflow's local privacy report was built, validated and reopened unchanged.
  Invalid report validation returned the expected error while the canonical report
  and professional deliverable hashes remained unchanged. No pipeline rerun was used
  to recover reporting. Provider payload extent remains unknown/host-attested.
- Source-to-ZIP verification returned no drift. Black/Isort, changed-code Mypy and
  Bandit checks passed; no medium/high Bandit findings. `git diff --check` passed.
  Update-notification checks also passed (17 passed, 2 skipped).

## Encountered blocks and recovery

1. The revised omission list initially had the wrong order for the existing exact
   contract comparison. Sorted the declaration to match its actual generated paths;
   the package then built without relaxing validation.
2. Isolated test collection initially lacked its test-only `tests._plugin_cli` helper.
   Copied the helper and package markers, without adding production files.
3. One isolated engine case lacked its AdventureWorks CSV fixture. Copied the existing
   synthetic test fixture and reran; 171 passed and 4 browser cases skipped.
4. Sandbox browser startup failed. Retained that failed attempt and repeated the
   synthetic local acceptance with approved normal browser access; both final browser
   runs passed. No failed browser attempt is counted as acceptance.
5. The extra lazy diagnostic-library omission was found after an initial repaired ZIP
   passed its happy paths. Rebuilt with the library, then repeated packaging tests,
   isolated engine tests and all workflow/reporting checks against the final hash.
6. Sandbox DNS prevented the remote-ref inventory; a read-only escalated query succeeded.

## Remaining limits

No fresh native chat or Marketplace installation was tested. No active installation
was replaced. Clean-OS dependency provisioning and live server receipts/Computer ID
verification remain untested. Local CLI acceptance does not prove host skill discovery,
autonomous routing, professional correctness or Marketplace eligibility. Historical
Archive readers and receipt compatibility code are not advertised workflows and were
not accepted as an Archive product in this test.

No publication, deployment, merge or external message occurred. Changes are retained
for review. Repository inventory: 9 local branches, 8 remote branches, 9 registered
worktrees, 0 stashes; this repair created none and preserved concurrent work.

## Reproduction

```sh
source .venv/bin/activate
python scripts/build_codex_plugin_zip.py clara --edition marketplace \
  --chatgpt-upload /tmp/clara-corrected.zip
pytest -q tests/plugins/test_clara_distribution_editions.py
python scripts/acceptance_clara_distribution.py \
  --package /tmp/clara-corrected.zip --output /tmp/clara-corrected-acceptance \
  --helper-python /Users/fabio/.local/share/mparanza/runtime/venv/bin/python
```

The browser portion requires working local Chromium access. Choose a new output
folder for each run. Preserve failed attempts and separate privacy-report outcomes.
