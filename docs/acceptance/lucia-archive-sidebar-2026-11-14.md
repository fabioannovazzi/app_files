# Lucia Archive sidebar acceptance — 2026-11-14

## Scope

Release 0.1.251 isolates the accepted Lucia Archive panel from the unfinished
Vera work in PR #998. It adds the panel, local fonts, packaging, product-specific
Archive defaults and regressions. It excludes Vera incarico, receipt, guidance
and navigation changes. Vera’s independent checkout and installed outputs remain
untouched. Marketplace publication is not authorized.

## Native acceptance already observed

With local Archive runtime 0.1.250, Fabio confirmed the selected practice appeared
in the global sidebar after restarting Codex. Selecting synthetic client
`client_a3f981a962cdd0a7806be4aa` and practice
`eng_d60da1a3c7a41a37092a558f` opened fresh chat
`01a1db58-fd83-7070-84e9-d8316e378202`. Its initial prompt contained those exact
IDs; the receiving agent listed the records and confirmed their relationship.
The user subsequently used that chat to save and read a synthetic support note.
This proves the observed sidebar handoff, not a full curated-plugin upgrade.
The released panel HTML is byte-identical to the accepted panel. Release 0.1.251
uses current main’s shared Archive rather than the unfinished Vera branch.

## Recovered blocks and limits

- Old processes retained the earlier local runtime until Codex restarted.
- The sidebar retained old HTML under a fixed resource URI. A content-derived URI
  fixes invalidation; a regression verifies changed HTML changes the URI.
- Backend errors originally prevented app display. The panel now receives a
  renderable generic error; private worker text is excluded.
- The fresh release checkout initially lacked build ZIPs required by runtime
  tests. Building the source packages supplies that prerequisite.
- Shared-source edits stale course hashes and privacy fingerprints. Maintained
  generators refresh those records without importing Vera’s unfinished changes.
- CI initially expected three Lucia HTML shells. The new Archive is the fourth;
  the projection regression now explicitly checks it is retained.
- Windows CI exposed locale-default decoding in the new test harness. Its Node
  subprocess output and HTML fixture edits now explicitly use UTF-8; production
  already specifies UTF-8.
- Local update-notification tests detect an unrelated Clara discrepancy: public
  manifest 0.1.248 versus installed curated 0.1.407. This release does not change
  published-version claims or Marketplace state.
- App-only projection tests cover private identities, source metadata and raw
  errors. No readable signed privacy report for the later synthetic note workflow
  has been verified; that reporting acceptance remains separate and open.

## Validation

The new panel/default tests pass (10); broader Archive adoption, concurrency and
MCP continuity selection passes (38 total including those 10). Lucia Codex package
checks pass (36), packaged Archive runtime tests pass (17), and the shared
recovery selection passes 453 tests at 89.04% coverage. Targeted Black, Isort,
Mypy and Bandit checks pass. CI and final
production artifact checks are recorded in the release PR.
