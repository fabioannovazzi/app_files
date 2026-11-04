# Vera bank CSV acquisition — 4 November 2026

Vera candidate 0.1.568 includes `bank-csv-download` directly. The ordinary
request “Vera, scarica i CSV della banca” selects that skill before generic
browser teaching or reconciliation. The operator does not download a separate
pilot, open a project, write JSON or supply technical paths. The skill resolves
its helper from the installed Vera root.

The current host model drives the documented computer-use surface. Terra 6.1 is
an operator choice, not a version/model requirement. The existing 1Password
extension performs Autofill directly into the bank; the operator unlocks the
vault and completes MFA. The route uses no bank API aggregator, second model
API, recorded browser capability or newly configured credential service.

Initial public-entry references cover Intesa Sanpaolo, UniCredit, BNL, Sella and
BCC RelaxBanking. They are not authenticated export recipes or a bank allowlist.
The model establishes the actual account, date filters, export options and
coverage from the selected portal. Local code retains a unique new stable file
and its hash without interpreting bank/account meaning or deduplicating rows.
Coverage review and actual bank acceptance remain distinct from byte retention.

## Source and packaging evidence

- Root skill description, early routing, workflow catalog, ChatGPT cards,
  workflow inventory and usage inventory include the operation.
- The helper and bank references are packaged inside Vera. Source/package tests
  exercise the packaged helper outside the repository.
- The actual helper extracted from the final Codex ZIP completed `start` and
  `collect` under Python `-I`, with its working directory outside every project
  and one synthetic CSV. Its preserved bytes matched the downloaded fixture.
- The function has a five-language explanation page and an inspected privacy
  manifest/public contract. The Geneva inventory includes it with disposition
  Unresolved; existing jurisdiction judgments are retained. No teaching kit is
  claimed for this new ordinary-work route.
- Codex, ChatGPT-upload, Cowork and Antigravity packages built from the canonical
  Vera 0.1.568 source. Codex source/ZIP drift verification passed.
- Clara/Lucia packages were rebuilt with their existing canonical source
  versions because the shared builder's Vera routing map participates in their
  reviewed build declarations. Their runtime workflows were not extended.
- 24 local file-mechanics tests passed, with 82.93% coverage of the helper.
  The focused routing/package suite passed 25 tests including those mechanics.
- Privacy contracts, workflow-registry, helper and update-notification checks
  passed 100 tests with two platform/cache-dependent skips.
- The complete package/update suite passed **416 tests, two skips** in a clean
  source/package fixture containing this candidate's source and rebuilt archives.
  Four existing FastAPI lifespan-deprecation warnings remain. All four host
  archives contain the bank skill, references and byte-identical helper; Cowork
  uses its existing `mparanza-` skill namespace.
- Black, Isort, Mypy and Bandit passed for the changed Python implementation.
  Icon checks passed; the shared generator changed zero icons. Function-page
  metadata and reviewed privacy copy loaded in all five languages.

## Encountered build and test blocks

- Main advanced to Vera 0.1.567 through PR #951 during CI. The combined 0.1.568
  preserves its incident ordering, Archive declaration preview and dependency
  argument corrections. The changed implementation files match main exactly;
  the Vera router retains both its dependency guidance and the bank-download
  route. The combined bank/archive/incident/prerequisite suite passed 82 tests.
  Auto-review rejected a blanket conflict-selection command as risking main's
  fixes. Source JSON was instead resolved explicitly, preserving main's service
  descriptions and both localization bindings; generated artifacts were rebuilt
  from combined sources. No override of that rejection was used.
- A Windows rerun exposed intermittent rejection of an unchanged original:
  path stat and descriptor stat can report different ctime meanings on Windows
  ([CPython issue 157671](https://github.com/python/cpython/issues/157671)).
  Descriptor timestamps are now compared with their initial descriptor values;
  path identity/timestamps are still checked against the initial path snapshot.
  Regressions accept differing API baselines and reject descriptor changes.
  All 24 mechanics tests pass locally; current Windows/macOS CI remains required.
- CI release alignment downloaded the new ZIPs but compared them with generated
  Cowork directories left over from checkout, missing six newly generated bank
  files. The alignment job now restores those directories from the exact same
  commit's built archives before checking them. A regression executes that CI
  preparation with fresh/hidden files and a stale checkout file; all ten archive
  prerequisite tests passed. Generated directories are not added to Git.
- The same six-file gap then appeared in `vera-packaged-mcp`, another artifact
  consumer. The shared archive producer now uploads the generated Cowork trees
  including hidden metadata alongside ZIPs. A regression exercises the upload
  patterns with newly generated helper/skill files and hidden manifests for all
  three products. This fixes the common artifact boundary rather than adding
  generated files to Git. Eleven prerequisite tests passed locally.
- Coverage initially selected the file as a module and collected no data.
  Correcting the coverage configuration measured the same helper at 81.71%; no
  production behavior was changed for that harness issue.
- The new ChatGPT card initially lacked the required skill invocation and
  product explanation. Adding those and the explicit router target resolved
  package validation; ordinary users still invoke Vera naturally.
- Adding an operation changed the localization inventory and initially made it
  look like an authored teaching kit. The exact new function is registered as
  unresolved for Geneva and described separately from the tutorial list.
  The existing 58 workflow kits and 258 localized kits passed their checks.
- Source/routing edits invalidated privacy fingerprints. Inspected affected
  declarations were refreshed and contracts regenerated. These are source
  bindings, not professional or legal approval.
- Privacy-projection tests initially read the old Cowork archive before its
  rebuild and reported omissions. Rebuilding the archive resolved the mismatch;
  the subsequent 100-test run passed with the two unrelated skips above.
- The local plugin inventory could not query the remote marketplace over this
  sandbox's network. It did establish an enabled local `vera@mp-vera` 0.1.564.
  The candidate was not installed over that separately adopted local version.
- The first complete package run had 413 passes, three failures and two skips.
  One test assumed every Vera specialist wraps another module; its native-skill
  branch now verifies this operation's actual helper and reference. The other
  failures came from two ignored Clara ZIPs dated 25 October (a historical
  versioned upload and a removed public download) already on this machine.
  Those artifacts were not deleted. The final 416-pass run used a clean fixture
  with tracked/current task source and the configured freshly built archives.
  No registered Git worktree, branch, stash or production behavior was changed
  to hide those environmental failures.

## Pipeline, privacy and distribution limits

No authenticated bank session was used for development. For **each** of the five
banks, download outcome, account/period/content acceptance, extension interaction
and MFA/resumption are **not tested**. Fabrizio can supply those details and
perform the first trial in his own ordinary Vera conversation after receiving
the integrated version. Fabio needs neither credentials nor client/account data.

The file helper has no network calls and does not emit CSV contents or unrelated
download names. Computer-use screenshots/text may contain banking information
in the selected host model context. The helper does not measure that host-tool
exposure; complete actual exposure measurement/report delivery remains open.
The existing fixed automatic-reporting pipeline list was not broadened. The
skill requires honest exposure gaps in the local coverage report and separates
reporting failure from useful CSV acquisition/delivery.

These are source and package results, not installed-host or professional
acceptance. No message was sent to Fabrizio, no account was accessed, and no
server deployment, Marketplace upload/draft/submission/publication or update of
his installation was performed. The candidate is based on main `acb88b4c5`;
intervening source and separately adopted local candidates must be reconciled
before distribution rather than overwritten by a version-number-only update.
