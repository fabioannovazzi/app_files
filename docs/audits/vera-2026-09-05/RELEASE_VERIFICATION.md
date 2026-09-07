# Vera release verification — resumed 7 September 2026

The previous temporary release checkout and test logs were absent at restart. The candidate was reconstructed from the retained primary source and upstream commit `6ab8d520`, without copying unrelated Clara feature work. The earlier full-suite run cannot be certified from missing logs; the complete suite was rerun, with logs retained in the primary workspace under `outputs/vera-release-recovery`.

## Verified in this resumed run

| Check | Result |
| --- | --- |
| Input, XML and source correctness | 295 passed, 1 skipped; 84.52% coverage |
| Additional new-client and matter-opening component tests | 150 passed |
| Managed Python runtime | 51 passed; 83.81% coverage |
| Archive organization component | 68 passed |
| Fiscal document dispositions | 4 passed |
| Sales Plan | 29 passed; 86.06% coverage |
| Browser runtime | 46 passed, no skips |
| Official Banca d’Italia documents | 15 extraction controls and 10 numerical cases passed |
| Changed-kernel type checking | 24 files pass with error suppression disabled |
| Configured application type checking | 132 files pass; repository configuration retains `ignore_errors=True` |
| Security scan | No medium or high severity findings in scanned src and changed kernels |
| Generated Cowork startup | Vera 18 servers and Lucia 4 servers initialize and list tools |

The Banca d’Italia PDFs were downloaded again from the official URLs in `gold_official_cases.json`. Their acquisition receipt is saved with the current benchmark result. The benchmark's optional semantic commentary review is separate from the 25 extraction/numerical cases above.

## Full-suite status

The suite collected 9,749 cases across three disjoint file groups: 9,711 passed, eight failed and 30 were conditionally skipped. Combined global `src` coverage is **80.21765%** (17,396 of 21,686 statements), above the unchanged 80% gate. Four additional fiscal-disposition cases, recovered after collection, also pass.

One group was interrupted while pytest expanded a multi-megabyte binary assertion. All unfinished cases were resumed; 779 completed application cases were rerun to recover that group's coverage. Unique case identities, original failures, retries and combined coverage are retained in `full-results.json` and the group JUnit/coverage files. These results are not represented as a single uninterrupted green run.

The eight failures comprised a stale page-paragraph assertion, a stale reviewed privacy fingerprint, an unrelated Clara upload assertion, a browser-version assertion, three missing packaged ledger dependencies, and a test import-path setup error. Test-only corrections preserve the implemented behavior. The missing studio-archive model-data module and contract were restored to the declared package overlays; all packages were rebuilt. **Final regression: 574 passed, zero failures or skips**, covering all eight corrected cases and their package/privacy/architecture modules. The two final Lucia privacy checks also pass. Together with the four additional fiscal cases, the default-suite ledger is 9,723 passing cases after corrections and 30 conditional skips.

The 30 skips are: 23 opt-in fresh-runtime setup/render cases (executed by Linux CI on Python 3.10 and 3.12), three unavailable external Clara historical fixtures, two optional local bank-PDF fixtures, and two unexposed legacy scatter helpers. They do not establish host qualification.

Two test modules created incomplete placeholder Python packages at collection time, causing imports in other tests to fail depending on collection order. Their test setup now imports the real modules; production files were not modified for this problem. Initial collection failures and focused test results remain recorded. A Clara upload assertion from unrelated primary work was removed by restoring the upstream test function; its focused three-case retry passes.

## Release scope

Vera is the primary release. Clara and Lucia packages are rebuilt because they embed shared components. Their unrelated feature work is excluded. Clara’s current public Cowork download remains unchanged: upstream deliberately separates candidate builds from its independently accepted public release. Only Vera and Lucia use the automatic public ZIP routes in this release. The public update manifest records only versions visibly Published in OpenAI Platform: Clara 0.1.180 and Vera 0.1.205. Candidate ZIP creation does not publish a Marketplace version.

| Changed component | Candidate version |
| --- | --- |
| archive-organization | 0.1.4 |
| bandi-agevolazioni | 0.3.7 |
| bilancio-xbrl-it | 0.1.14 |
| browser-automation | 0.5.8 |
| business-planning | 0.2.10 |
| centrale-rischi-review | 0.1.8 |
| check-entries | 0.1.39 |
| clara | 0.1.182 |
| client-file-preparation | 0.1.40 |
| comunicazione-professionale | 0.1.10 |
| concordato-plan-review | 0.1.39 |
| deep-research-validator | 0.1.42 |
| journal-bank-reconciliation | 0.1.49 |
| journal-sampling | 0.1.41 |
| lucia | 0.1.31 |
| management-control-pack | 0.1.3 |
| new-client | 0.1.11 |
| open-item-reconciliation | 0.1.52 |
| passive-invoice-audit | 0.1.4 |
| presenza-digitale-studio | 0.1.7 |
| prompt-optimizer | 0.1.43 |
| registro-imprese-sari | 0.1.10 |
| report-builder | 0.1.40 |
| sales-plan | 0.1.7 |
| studio-archive | 0.1.34 |
| variance-analysis | 0.1.99 |
| vera | 0.1.211 |

## Remaining release steps

The full suite and coverage calculation are complete. Final formatting, privacy refresh, package rebuilding, drift checks, and packaged MCP startup checks pass. Final package regressions pass. Commit and open the authorized release PR; require green CI before merge; deploy through git on the server and verify the live page and package bytes.

The user excluded Windows and Mac-specific qualification from this task. No additional PDF, professional-qualification, or renewed authorization request is pending. No commit, deployment, or Marketplace publication has occurred in this resumed release phase.

## Final candidate archive identities

| Archive | SHA-256 |
| --- | --- |
| plugin_packages/vera/vera-chatgpt-upload.zip | `25b2de67e87c684d57f1e13040628e0f479e1cc734b394cda353161e2d2d4452` |
| plugin_packages/vera/vera-claude-plugin.zip | `d6ee5ba27277fd35bc230f79e729beabc40bd7e49c624bd4d6cf23a18824bdd5` |
| plugin_packages/vera/vera-plugin.zip | `93e765bed66f36d3bb705472aa70c0cfaa656c8bedc62d0ba724dacaa89a13b9` |
| plugin_packages/clara/clara-chatgpt-upload.zip | `884c42350ee60d33c8d3770a18c682ca239e81c195eccd351575b3716afcdaf2` |
| plugin_packages/clara/clara-claude-plugin.zip | `35396bf864f2ec0b0f7c95c5c8c89b2b886017ddd6230167891c5ff51c7458b9` |
| plugin_packages/clara/clara-plugin.zip | `ab9d25c72fc5a6f19ba771bd7831a02d6d8f104b95ec9ac59fc1541b3af259c2` |
| plugin_packages/lucia/lucia-chatgpt-upload.zip | `6f23be4140c16099bb1f3b933051796191ec4ca22771f8b31896a1c5a0a55fed` |
| plugin_packages/lucia/lucia-claude-plugin.zip | `f2042a074dd020111e8ab79f50c4e53fde85d766d5a09d7f02a56525d65d4b20` |
| plugin_packages/lucia/lucia-plugin.zip | `de880fd5e8b6d0f22b0393c49944d85a6e07bc90a7bfcad69eb1d512352aaed1` |
