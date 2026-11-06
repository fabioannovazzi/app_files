# Blocked course repairs, 6 November 2026

This batch addresses four independently reproduced defects from the autonomous course acceptance campaign:

- INPS inventory filtered all files when an explicitly selected input root was below a hidden ancestor such as `.local`. Hidden filtering now applies only below the selected root. Hidden descendants remain excluded.
- Bilancio's MCP bridge used the host bootstrap Python directly, missing component dependencies. The bridge now invokes the owning product's managed runtime; an explicit `VERA_XBRL_PYTHON` override and standalone fallback remain supported.
- Fusione authored course inputs omitted the planned transaction date, while the test helper supplied it invisibly. The fictional date is now explicit in both input branches and all five localized dossiers, and the test uses that input.
- Treasury reports listed flows in source order. Markdown, HTML and workbook flow tables now present dated events chronologically, with undated events last. Canonical record order and calculations remain unchanged.

## Validation

The INPS, Bilancio bridge and Fusione focused batch passed 111 tests; Treasury passed 33. The separate Bilancio service/native-workspace batch passed 30 tests in the sandbox, and its loopback-server test passed when rerun with the required host permission. All 17 required Bilancio invariant probes passed. Package checks passed after building the missing foreign-product upload prerequisites; the three affected upload checks then passed. Black, isort and `git diff --check` passed.

Vera 0.1.582 Codex, Cowork and Antigravity packages were rebuilt and source-parity checks passed. Version-bound catalogue and governed source fingerprints were refreshed without changing jurisdiction judgments. Historical course editorial judgments remain preserved, with a bounded review of the source changes and explicit fictional input date; final-head teaching CI remains required.

Actual source-candidate replays were retained in the onboarding workspace under `source-retests-20261106`: INPS now reads four course documents under `.local`; Bilancio MCP creates and idempotently reopens a draft using the actual system Python 3.9 bootstrap; the original Treasury case produces a chronological workbook with unchanged amounts and forecast. These checks do not prove an enabled installation or an existing chat updated.

Journal Sampling demo and April practice additionally succeeded through native artifact writes and completion, using the separate Archive binding candidate. March: 13 population rows; April cumulative: 15; both samples: 5 rows, seed 42. All normalized and sampled source dates, IDs and amounts were checked. Source totals are 4,392 and 4,880 EUR per debit/credit side. Professional sampling adequacy was not asserted. Remaining defects: readable Archive projection still reports an unavailable selected client; workbook monetary cells are text. These are not repaired by this batch.

## Release limits

This candidate starts at c918bee5f. Integrate the independent Archive, Variance and parallel course-remediation changes before the final combined release, then regenerate packages and repeat relevant checks. No Marketplace publication, learner completion, professional approval, voice acceptance or fresh installed-session acceptance is claimed here.
