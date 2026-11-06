> **SUPERSEDED:** The deep audit found defects in these candidates. Use [the final audit](lucia-distribution-deep-audit-2026-11-06.md) and its exact ZIP hashes. These earlier files are historical evidence.

# Lucia current-code distribution candidates — 6 November 2026

Status: both exact candidates built and CLI-tested; six reduced-edition workflows
completed in an installed native Codex session. Full-edition review/comparison
completed and a native MCP check passed after explicit test-environment configuration.
**Not released; full native UI/Word acceptance remains incomplete.** A separate
synthetic live-reporting run has a verified receipt. The first full native probe
delivered a technical incident despite its local-only instruction; this remains
recorded as a failed reporting boundary, distinct from document outcomes.
Source base: `c918bee5f` on `codex/lucia-distribution-editions`. Both editions use
canonical Lucia 0.1.210; these are staged review candidates, not a newly reserved
published version. No Marketplace upload, listing change, support email, merge,
website/server deployment or replacement of the active Lucia installation.

## Edition contract

The normal builder remains the complete Website/Codex distribution. Explicit
`--edition marketplace --chatgpt-upload PATH` selects only Lucia's reduced
**desktop document edition**. Vera and Clara reject this reduced selection;
their ordinary build behavior is unchanged. No web-compatibility claim follows
from removing bundled MCP registrations.

| Function | Full edition | Marketplace candidate | Basis / limit |
| --- | --- | --- | --- |
| Contract review | Retained | Retained | Current `legal_documents.py`; source quotations, context and proposals; no independent legal research |
| Document checking | Retained | Retained | Current proofreading engine; visible eight-pass coverage and rendering limits |
| Version comparison | Retained | Retained | Two selected documents, literal diff plus model interpretation |
| Collection review | Retained | Retained | Source/topic matrix, HTML and Excel |
| Clause extraction | Retained | Retained | Existing collection-review engine, narrow extraction instructions |
| Draft from template | Retained | Retained | Local TXT/Markdown replacements; Word authoring conditional on host Documents/Word |
| Local document questions/progress | Retained | Retained internally | Current `legal_matter.py`; saved state, history and reopen; not an Archive replacement |
| Firm-method editor/application | Retained | Excluded | Native editor contract and version-selection lifecycle not retained; supplied chat instructions remain usable |
| Studio Archive | Retained | Excluded | A real shared CLI fallback exists in `lucia_studio_archive.py`; exclusion is scope, not proof that Archive requires MCP |
| Matter opening | Retained | Excluded | Shared Archive lifecycle and separate intake/review/apply contracts; chat fallback exists, but this candidate does not rebuild or accept that larger pipeline |
| Legal/tax question, planner, research, review, adversarial opinion | Retained | Excluded | Canonical multi-component assurance/lifecycle not part of the six selected-file pipelines |
| Civil/tax litigation, M&A, employment, debt collection | Retained | Excluded | Practice methods depend on additional research/progress contracts beyond the retained document methods |
| Citation verification; negotiation-position tables | Retained | Excluded | Separate specialist workflows not offered or routed by this candidate |
| Communications and firm website | Retained | Excluded | Additional component execution/review/publication paths not retained |
| Paired teaching/onboarding | Retained | Excluded | Current native voice/second-chat/course pairing contract; no fabricated chat-only substitute |
| Usage, incidents, model-data report | Native tools plus CLI | CLI plus documented recovery | Same maintained scripts and service identity/outbox contracts; reporting failure stays separate from document result |
| MCP panels/registrations | Retained | None | All root/nested registrations and native wrapper scripts excluded; review is HTML/Excel and conversation |

The retained engine bytes come from current maintained source. Projection changes
only edition routing, metadata, dependency entrypoint, reporting transport instructions
and unused references. No fork of the document parsing/review/drafting engines.
The mechanically checked file/skill inventory is justified by exact package
integrity and dangling-route prevention; it does not classify legal intent.

## Reproduce

Activate the primary checkout's `.venv` while working in this worktree.

```sh
python scripts/build_codex_plugin_zip.py lucia
python scripts/build_codex_plugin_zip.py lucia --check
python scripts/build_codex_plugin_zip.py lucia --edition marketplace --chatgpt-upload /private/tmp/lucia-candidates/lucia-marketplace.zip
python scripts/build_codex_plugin_zip.py lucia --edition marketplace --chatgpt-upload /private/tmp/lucia-candidates/lucia-marketplace.zip --check
LUCIA_ACCEPTANCE_ZIP=/absolute/candidate.zip LUCIA_ACCEPTANCE_PYTHON=/absolute/clean-runtime/venv/bin/python python -m pytest tests/plugins/test_lucia_distribution_acceptance.py
```

Exact-ZIP tests extract a fresh package for each case and verify every execution-index
hash before invoking its scripts. Model-authored fixture interpretations are explicit
synthetic text observations; they are not a legal-quality benchmark or a native chat.
The driver may use the repository test environment while all candidate subprocesses
use `LUCIA_ACCEPTANCE_PYTHON` from the separately provisioned shared recipe.

## Evidence boundaries

- Source/unit regressions, exact package execution, clean dependency setup, MCP
  protocol startup, installed host discovery and host-visible delivery are distinct.
- CLI model-data report test writes and reopens the real schema-2 report and retained
  privacy contract offline, with `not_measurable` and `not_assessed` evidence. It
  explicitly requests local-only delivery for that transport-absence test: **no
  signed receipt, server/Computer ID link or native report delivery is claimed**.
- Source privacy contracts are retained as source declarations. The package registry,
  usage catalogue and installed fingerprints cover only the retained workflows.
  `distribution-review.json` records reviewed omissions. On-demand MCP and course-file
  services are omitted. The shared packaging-file fingerprint change requires updated
  Vera/Clara privacy metadata; it does not change their workflow source.
- The native CLI is `0.167.0-alpha.3.2`. Ephemeral per-invocation discovery probes
  were attempted without modifying saved configuration. Failed discovery is not
  repaired by reading the candidate skill from disk and calling it installed.

## Encountered blocks and recovery

| Block | Effect | Recovery / justification |
| --- | --- | --- |
| Source privacy review stale after builder change | Build refused | Reviewed unchanged full-route transport and refreshed the governed packaging fingerprint/contracts |
| Installed privacy validation expected a component directory | Reduced package initially failed | Explicit empty `modules/README.md` declares no embedded workflows; no fake component registration |
| Reviewed package omissions initially absent | Build refused | Inspected explicit retained/excluded paths and stored the reviewed omission map; final builds compare exact maps |
| Three existing shipped-helper tests lacked generated ZIPs | Test setup failures | Built full Codex/upload/Cowork packages in this clean worktree; rerun passed |
| Missing-input acceptance test incorrectly expected a saved evidence pack | Harness assertion failed | Corrected test to check explicit missing-file error and absence of fabricated output; separate unreadable-PDF test checks retained gaps |
| Sandbox could not resolve PyPI | Fresh setup failed before dependencies | Same isolated setup retried through host network approval; no alternate index or permission bypass |
| New reduced dependency checker re-entered install during `--managed-verify` | Fresh environment failed readiness after install | Added actual import-only verification; rebuilt and reran fresh setup plus exact-package regression successfully |
| Native CLI could not initialize in sandbox | No host session | Retried same ephemeral probe through normal execution approval |
| Quoted dotted plugin override became a literal invalid plugin key | Candidate not exposed | Corrected per-invocation syntax; first result retained as failed discovery |
| Corrected native override reported candidate not installed in host cache | Candidate still not exposed | Subsequently installed under two separate temporary candidate IDs through supported plugin add; actual catalog discovery and workflows succeeded |
| Automatic approval review initially rejected live reporting egress | First remote synthetic report attempt did not run | After the user's continuation, the specifically scoped retry passed normal approval and completed; verified receipt below |
| Git restore initially lacked index-lock permission | Generated-diff cleanup did not run | Retried the exact scoped restore through normal approval; source edits and candidate ZIPs preserved |
| Broader suite lacked Vera/Clara generated fixtures | 26 failures/errors | Built declared fixtures from current source; all 26 passed on rerun |
| Deliberately fabricated quotation | Renderer correctly refused unsupported finding | Corrected quote from original evidence and rerendered; verified useful output |
| Deliberately missing source / blank PDF | Missing source rejected; unreadable material visible | Kept concrete error/gap; never converted missing text into an absent clause |

## Final staged artifacts and checks

Durable staging directory:
`/Users/fabio/Documents/GitHub/app_files/build/lucia-distribution-candidates-2026-11-06/`

| Candidate | Bytes | SHA-256 |
| --- | ---: | --- |
| `lucia-full-codex.zip` | 2,921,370 | `3c11b5afbbcd48207b9771ae8274d6fb9f2092c2711d032ff4e90a84d3a9da48` |
| `lucia-marketplace.zip` | 1,067,501 | `da1c6e94065ce69b363b6a86d92ca6970397076fa6088297768878961eb7db1a` |

`candidate-hashes.json` and `package-inventory.json` provide machine-readable
identities. Full: 26 exposed skills, five root/nested MCP registration files and
seven native service owners. Reduced: seven skills (router plus six workflows),
zero registration files and zero native service owners. Default full packages
retain MCP behavior and native interfaces; their installed-host use remains a
separate acceptance item.

Observed validation:

- 13 exact-ZIP CLI checks per edition passed in a newly provisioned, separate
  Python 3.12 environment using the published shared recipe: 26 checks total.
  Inputs/outputs persist under `/private/tmp/lucia-candidates/final-*-clean/`.
  The proofreading case records all eight text/structure passes and keeps visual
  inspection incomplete; template drafting preserves the original and unresolved
  fee placeholder. No Word-application or native-redline acceptance is claimed.
- 89 existing document/inspection/progress regressions and six edition boundary
  tests passed. Edition projection coverage: 97.83% (92 statements, two missed).
- Shared package/icon/update suite: 423 collected. Initial run had 395 passes,
  two skips and 26 missing-generated-fixture failures/errors. After building
  current Vera/Clara/full-Lucia fixtures, all 26 affected tests passed on rerun:
  combined result **421 passed, two skipped**. This is not a claim that the entire
  repository test suite or repository-wide 80% coverage gate ran.
- Full and Marketplace source-drift checks pass; complete execution-file hashes
  are verified on every extraction. Full package build/check exercises local MCP
  startup; separate Cowork fixture build reported seven MCP startup checks passing.
- Privacy contract generation and shared runtime synchronization checks pass.
- Black/Isort checks pass; Mypy passes for four changed/new production files.
  Bandit reports zero medium/high findings and three existing low-severity
  subprocess notices in the shared builder. `git diff --check` passes.
- Candidate downloads and evidence logs are staged only. Incidental generated
  Cowork/download diffs were restored in this isolated worktree; no website copy
  is changed for release. The two candidate ZIPs remain intact in staging.

## Resumed installed-host evidence

Supported `codex plugin add` installed the exact ZIP contents under separate local
IDs `lucia@lucia-acceptance-document` and `lucia@lucia-acceptance-full`. Installed
execution-index hashes matched all 137 and 543 files respectively. Native catalogs
resolved each candidate's installed skill path. The active `lucia@mp-lucia` was
not replaced. These are Codex CLI native sessions, not Desktop panel or Word tests.

The reduced candidate completed all six selected-file workflows with substantive
HTML/Excel/Markdown results, source quotations, preserved originals and local
model-data reports. Five Excel files reopened; the draft made exactly two supported
replacements and retained fee/date placeholders. This is synthetic agent acceptance,
not professional/legal-quality acceptance. Native evidence and detailed limits:
`/private/tmp/lucia-candidates/native-marketplace-final/acceptance-result.md`.

The full candidate completed review and comparison through its installed CLI
helpers; 13 citations matched the supplied text and both Excel files reopened.
Its native catalog exposed 60 tools, not all executed. The first native
`check_studio_import_sources` failed because the default shared runtime attempted
setup from a managed interpreter. The test's parent-process environment settings
had not taken effect at the MCP boundary: diagnostics used the default state path,
not the isolated test path. The package MCP declaration has no environment forwarding
list. OpenAI documents explicit `env`/`env_vars` for MCP stdio configuration:
<https://learn.chatgpt.com/docs/extend/mcp>.

The original failure diagnostic reported `delivered`. Local receipt state matches
report `707eb8ca-412f-4de7-a4a4-03fc4c0a6df5` to incident
`9f82e25e-89b0-4f85-b16c-af7e36d1960c`. Its inspected report contains technical error
metadata and measurements; this does not establish all network traffic or server
retention. The first test did **not** meet its no-transmission condition. No server
receipt verification was performed for this incidental diagnostic.

A narrowly scoped retry configured the existing exact installed MCP command/cwd
explicitly with `mcp_servers.lucia.env`: `MPARANZA_RUNTIME_ROOT` set to the clean
test runtime, `MPARANZA_INCIDENT_DELIVERY=local-only`, and separate test state/device
directories. The native call then returned `ready: true`, both files reachable,
and `archive_records_created: false`. This proves the tool works with the configured
runtime; it does not prove unmodified default-environment acceptance or repair the
original transmission. No package bytes changed for this retry.

Additional recovered native blocks are retained in the per-run reports:

- Pre-created run directories were correctly refused to protect existing evidence;
  preparation recovered into new child directories using the same task UUIDs.
- The resulting first proofreading scaffold lacked evidence; it was rerun after
  successful preparation, then populated and rendered.
- Six report inputs used an unsupported counting basis; rejected inputs were
  preserved, corrected to `attested` with `host_attested` evidence, and validated.
- The native agent skipped usage start/record because those commands lack a
  `--local-only` flag. Afterward, the existing environment-level local-only control
  was verified with the installed helper: all six same-UUID lifecycle records were
  saved, with two queued/unacknowledged events per task and no remote status.
  These are explicitly post-run reconciliation timestamps, not contemporaneous
  workflow-start evidence. Original local registries and reports remain intact.
- Wrong-working-directory/missing generic contract reads, truncated reads, and one
  malformed local evidence-save patch were recovered; exact records remain in the
  native reports. None are silently omitted from the acceptance record.

No native Word editing, redlines, visual panel operation, entire Archive lifecycle,
or other excluded specialist pipeline was accepted in these probes.

Both temporary candidate registrations were removed through supported
`codex plugin remove`. Saved plugin and marketplace settings exactly match the
pre-install snapshot; candidate version caches were removed (empty parent
directories remain). Active Lucia settings are unchanged. Synthetic inputs,
outputs and transcripts remain in the test directories and staged evidence pack.

## Separate live-reporting verification

The scoped synthetic live run completed with UUID
`0d956e4a-7501-44c3-88e5-f6c921ff4895`, sample kind `agent_test`, zero queued events,
one linked receipt, verified Computer ID linkage and no outstanding next steps.
Report ID: `model_data_3ac3dafac009e0a9de5fe5dc`; SHA-256:
`c9206bb436e73a07d3fd7e0abd6dc52b46ba51ae788a2c80f778dc2bcb7f8f04`.
Receipt `f8133fee-9fb9-4f2d-a160-3f062f516b1c` verified `valid` for that exact hash.
The sandbox verification request initially could not reach the service; the same
verification succeeded through normal network approval. This separately authorized
run contains synthetic reporting evidence, not client documents or conversation text.

[Verify the exact report receipt](https://mparanza.com/verify/lucia-run-receipt/f8133fee-9fb9-4f2d-a160-3f062f516b1c?sha256=c9206bb436e73a07d3fd7e0abd6dc52b46ba51ae788a2c80f778dc2bcb7f8f04).
Safe evidence: `/private/tmp/lucia-candidates/reporting-live/verified-summary.json`.
Raw identity/credential-bearing reporting responses are not copied into the review pack.

Repository lifecycle: this task created exactly one local branch and one worktree;
no remote branch or stash. The user explicitly requested preserving implementation
for review. Final inventory: nine local branches, eight live remote branches,
nine registered worktrees, zero stashes. The seven other task branches/worktrees
pre-existed and were preserved. Source is retained in
`/private/tmp/lucia-distribution-editions` on `codex/lucia-distribution-editions`,
uncommitted for review. Candidate implementation/validation and its explicitly
bounded evidence are complete; comprehensive host acceptance and release are not
claimed or performed.

