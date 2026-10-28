# Directory review packaging changes — 28 October 2026

The release removes embedded fonts from the apertura-pratica editable page and
read-only widget, and the archive-organization, new-client and
open-item-reconciliation widgets. Their builders use the requested local system
font fallback. JSON constants are expanded without changing their parsed values;
the remaining JavaScript is byte-identical to the previous revision. Maximum
source line lengths are respectively 940, 940, 778, 778 and 824 characters.
No network font dependency is added.

## Download/execution findings

- `plugins/vera/mcp/workspace.cjs`, `bridge()` (lines 693–709): its two
  `spawnSync` calls execute bundled `scripts/native_workspace_runtime.py` and
  `scripts/native_workspace.py`. The resolver calls `activate_runtime`, which
  selects a previously prepared environment and does not install dependencies.
- `plugins/_shared/vendor/modules/data/common_data_utils.py`, `get_table_download_link()`
  (lines 3357–3387): creates data-URL download links from local Excel, CSV or
  HTML bytes. The three flagged Clara vendor copies match these source bytes. The
  inspected file contains no network fetch, package runner or process launch.
- The separate `scripts/_python_bootstrap.py` does retrieve a pinned `uv`
  0.12.10 wheel and checks its SHA-256 before extracting or running it; `uv`
  then provisions CPython 3.12. That existing setup behavior is retained.

Generated REVIEW.md files identify every present flagged path individually and
also describe the separate verified bootstrap. No runtime command was removed
or disguised. The directory scanner's exact matching rule is unavailable, so
these findings do not establish its internal trigger or clearance of a hold.

## Privacy review scope

Agent review compared the changed generated JavaScript/data with the previous
source, inspected the renderer, runtime resolver and export helper, and reviewed
the affected privacy records. Changes are font CSS, JSON whitespace, reviewer
documentation, release versions and their dependent course/integrity hashes.
No model-context fields, recipients, network operations, review decisions or
receipt behavior changed. Only affected review fingerprints and generated
contracts were refreshed; existing data-path explanations remain unchanged.
This is source-level review, not a new professional pipeline acceptance run or
verification of model-provider transmission.

## Validation and limits

Source/widget/runtime tests, built-archive checks, release drift checks and the
repository archive-size guard are required for this release. The browser preview
uses synthetic data and the built Cowork HTML; it is not native Cowork acceptance.
The enabled Cowork installation and directory rescanning remain separate from
the downloadable release. No Marketplace submission is part of this change.

Recovered checks: the first focused test invocation excluded the root fixture
directory; the normal fixture configuration passed. Release preparation detected
stale privacy and course-source fingerprints after the asset/version changes;
the affected records were reviewed and regenerated. The sandbox denied a
headless browser process and loopback listener; the visual preview uses the
existing Chrome surface and an approved loopback-only server.
CI also detected that Vera's localization catalogue still bound version 0.1.513.
The release snapshot was rebound to 0.1.515 after proving all 55 skill entrypoint
IDs and hashes unchanged; existing jurisdiction judgments were retained.
