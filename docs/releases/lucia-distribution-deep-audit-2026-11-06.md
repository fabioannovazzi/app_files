# Lucia two-distribution deep audit — 6 November 2026

## Observed result and limits

The final candidates pass the defined isolated tests below. This is not a claim
that all Lucia workflows, native interfaces, operating systems or legal outputs
have professional acceptance. No deployment, merge, Marketplace operation, external
message or active-plugin replacement was performed in this audit.

- **Full MCP:** 26 exposed skills preserved, 539 indexed files, 185 Python modules.
  Root MCP discovery exposes 63 tools. All seven specialist owners initialize and
  return tool names matching their packaged catalogue in the separate runtime,
  including from a read-only extraction. The six document workflows and their
  adverse cases run from the exact ZIP. The wider specialist journeys and native
  UIs were not exercised end to end.
- **Reduced non-MCP:** six document workflows plus the router, 137 indexed files,
  32 Python modules, no MCP registrations/wrappers, component workflows, hooks or
  native panels. All six retained workflows run from this exact ZIP without the
  repository or a full Lucia installation providing files. Local desktop execution
  remains required; removing MCP does not establish web-only compatibility.
- **Live Mparanza download:** does **not** contain the tested fixes. It changed during the audit from
  0.1.210 to 0.1.211; both snapshots were retained. Content comparison and
  targeted regressions distinguish the newest retrieved download from the candidate.
  It retains the stale-success Word report behavior, the local-only receipt-retry
  gap, the untranslated proofreading context, and the four removed development/
  Vera-only files. No live file was changed.

## Exact identities and provenance

Maintained source: `/private/tmp/lucia-distribution-editions`, branch
`codex/lucia-distribution-editions`, base commit
`c918bee5f97c39691fa6fc355671c8eb915364f3`, with retained uncommitted implementation
and audit fixes. The review pack records the dirty-source file hashes and patch.
Both packages use canonical Lucia **0.1.215**, an unpublished local candidate.
The synchronized shared receipt fix also increments local Vera to 0.1.588 and
Clara to 0.1.391. These numbers exceed inspected concurrent worktree candidates;
GitHub PR lookup was unavailable. Reconcile concurrent source and version choices
before any future release. This audit does not authorize that release.

| ZIP | Bytes | SHA-256 |
| --- | ---: | --- |
| Full candidate | 2,910,486 | `10139878f1fc303570fe1b8ac210f5404fb2dc2cdfcb8d19c82d7da40aa682d1` |
| Reduced candidate | 1,068,557 | `7a75a5dd091fe2d74af4716079aa9c22f42f3a94d95217b45b4f2c097014f9f5` |
| Initial live download 0.1.210 | recorded in inventory | `2fc25c3cdf92a6041ff57f446385d2114dff06d7aa4c04f410a489c86eccbf30` |
| Latest retrieved live download 0.1.211 | 2921503 | `d28ac2cc2d217032651c61adc24ab8704283b56989b7172d12894d1bfb99788c` |

Final staging directory:
`/Users/fabio/Documents/GitHub/app_files/build/lucia-distribution-deep-audit-2026-11-06/`.
Final filenames: `lucia-full-codex.zip`, `lucia-marketplace.zip`.
The live URL inspected is
<https://mparanza.com/static/shared/lucia/downloads/lucia-plugin.zip>.
`inventory-final.json` records every package-relative file hash; the live comparison
lists actual additions/removals/changes. ZIP timestamp/version equality is not the
comparison method. Both final source-parity checks passed.

The previously delivered full hash `3c11b5afbbcd48207b9771ae8274d6fb9f2092c2711d032ff4e90a84d3a9da48`
and reduced hash `da1c6e94065ce69b363b6a86d92ca6970397076fa6088297768878961eb7db1a`
are **superseded**. Their original files remain as historical evidence, not current
candidates. Intermediate audit builds and failing transcripts likewise do not
establish acceptance of the final bytes.

## Workflow inventory

| Workflow or support | Full | Reduced | Tested boundary |
| --- | --- | --- | --- |
| revisione-contratti | Retained | Retained | Source-linked HTML/CSV/XLSX, perspective and unknowns |
| controllo-documento | Retained | Retained | Eight-pass scaffold, maps, cited finding, visible visual gap |
| confronto-documenti | Retained | Retained | Literal diff, source-specific cells and authored comparison |
| revisione-documentale | Retained | Retained | Multi-document/topic matrix and source register |
| estrazione-clausole | Retained | Adapted through retained collection-review engine | No separate absent extractor is promised |
| redazione-da-modello | Retained | Retained | Exact TXT/Markdown changes; DOCX verification bridge; host authoring conditional |
| Questions/progress | Retained | Internal document support | Persist, save revision, reject stale update, reopen |
| Usage, incidents, model-data report | Native tools and CLI | CLI and documented recovery | Local-only lifecycle and report validation; no receipt/linkage claim |
| legal-tax-answer-planner, deep-research, legal-tax-answer-review, quesito-legale-fiscale, adversarial-opinion | Retained | Excluded | Full imports/configuration preserved; complete research journey not retested |
| apertura-pratica, studio-archive, metodo-studio | Retained | Excluded | Full owner startup/discovery only; no replacement chat workflow |
| contenzioso-civile, contenzioso-tributario, operazioni-ma, lavoro, recupero-crediti | Retained | Excluded | Instructions/dependencies preserved, professional scenarios not accepted here |
| verifica-citazioni, posizioni-negoziali | Retained | Excluded | No reduced routing to them |
| comunicazione-professionale, presenza-digitale-studio, learn-with-lucia | Retained | Excluded | No external sending, publishing or paired teaching performed |
| privacy-surface-review | Retained developer workflow | Excluded | Governance declarations retained/projected by package builder |
| lucia router | Retained | Adapted to exactly six workflows | No generic substitute offered for omitted journeys |

The full catalogue, component registrations and MCP catalogue are preserved
byte-for-byte relative to the earlier full candidate. Four files removed from the
full package are two `apertura-pratica/tests/` files requiring undeclared pytest,
and `studio-archive/scripts/{reconcile_open_items,open_items_source_preflight}.py`.
The latter are Vera-only reconciliation drivers; they are not referenced by Lucia's
skill routing or exposed tools and depend on an absent `audit_assurance` component.
Lucia's Archive entrypoint and all seven native owners remain packaged.

## Dependency and instruction audit

All Python imports, including function-local imports, were inventoried through
AST inspection. Dynamic loader/subprocess/read-path call sites were recorded.
Each packaged Python module was then loaded in a separate `python -I -B` process.
Package imports use their real package identity; only the extracted package's
script and vendor directories are added. Network and subprocess actions during
module import are rejected. Final result: **185/185 full, 32/32 reduced** load.

Retained document dependencies resolve to bundled legal_docx, schemas, localized
labels, evidence/progress/Word helpers and the declared jsonschema/lxml/pypdf/
openpyxl/python-docx dependencies. Runtime execution also needs the shared
verification, environment, diagnostics, reporting and receipt helpers. These were
retained; deleting every `archive_*` file would break the shared runtime/report
import chain. Shared Vera-only schema/Archive branches do not advertise a reduced
Archive workflow. No repository fallback was available in the isolated children.

The reduced ZIP intentionally keeps the published shared runtime recipe rather
than inventing a smaller unreviewed dependency set. Its broad recipe is not a claim
that every library is needed by each document case. Provisioning used that exact
recipe in `/private/tmp/lucia deep audit è/runtime`, independently of the active
runtime. `runtime-packages.json`, recipe hashes and `runtime-facts.json` record
what was installed. This is a **fresh virtual environment on this macOS host**,
not clean-OS acceptance: an existing base Python, operating system, network and
installer cache were available. No OCR was installed or used.

Retained instructions, fenced commands, schemas, asset references, relative links
and workflow handoffs were inspected. The lexical audit checked 38 reduced and
226 full explicit path references. Apparent full missing links resolve through
explicit component-root or skill-root instructions, or are conditional Vera-only
sections in shared developer guidance. Upstream snapshots, including their
historical schema links, are attribution rather than active workflow instructions.
There is no active reduced instruction to call a removed MCP tool or excluded
workflow. The internal shared reporting `startup_context` text mentions native
reporting, but is not a CLI command or retained hook and has no reduced caller.

CLI coverage: **103 entrypoint invocations (87 full, 16 reduced)** completed with
expected results after correcting the harness protocols. Most broad full-entrypoint
checks are startup/help checks, not end-to-end professional journeys. Internal
stdin/positional helpers were given their actual protocols. Course invitation
validation was an intentional invalid-operation case, not successful paired-course
acceptance. Retained user-facing document and reporting commands additionally have
substantive tests below. The managed runtime launcher itself ran the packaged
document helper using the separate provisioned runtime.

## Tests and substantive evidence

Final exact-package suites:

- Reduced: **40 passed**, comprising 32 isolated package cases and eight edition/
  source-boundary regressions.
- Full: **121 passed**, comprising the same 32 isolated cases and 89 existing
  document, inspection and progress regressions.
- Shared receipt behavior: **18 passed** with in-memory/injected transports,
  including synthetic outage recovery and the new no-transmission regression.
- Focused measured coverage for the projection, Word bridge and proofreading
  modules: **87.70%** (335/382 statements). This is not repository-wide coverage.
- Package-wide and quality results are recorded in the final check summary.

Every exact-package case extracts a fresh ZIP, checks all execution-index hashes,
uses an installation path with spaces and accents, sets files read-only/directories
non-writable, and saves outputs/reporting state outside the installation. The test
harness uses the repository's development environment to orchestrate and create
fixtures; **candidate subprocesses use the separate declared runtime**, isolated
from repository imports and other installed plugins. These are different roles.

Cases cover all six retained workflows; TXT/Markdown (including UTF-8 BOM), text
PDF and DOCX; immutable originals; no OCR for blank/image-like PDF; corrupt DOCX,
PDF and encoding; missing source; fabricated quotation and invalid anchor; altered
evidence and snapshot; repeated prepare refusal; revised render with archived
previous output; failed rerender without stale current output; template replacement
with unresolved fee placeholder; progress reopening and stale revision rejection;
clean Word verification, missing edit and failed subsequent verification.

A richer two-version maintenance contract uses four topics/eight cells. The output
preserves the +20% price change, 30→60 day payment period, new renewal/disnotice,
EUR 10000→2000 liability cap **and both exceptions**, plus the missing Article 9
in A versus supplied service description in B. The liability exception for
confidentiality is not lost. Source quotations, HTML and spreadsheet cells were
checked. These are agent-authored synthetic interpretations, not a benchmark of
legal correctness, independent lawyer acceptance or exhaustive semantic quality.

Visual checks: actual comparison/proofreading HTML rendered in Chromium; comparison
also inspected at a narrow viewport (wide tables use horizontal scrolling). A
synthetic DOCX rendered to PDF with an isolated LibreOffice profile and inspected
as an image. The corrected Italian proofreading display is rerendered in the final
visual pack. Excel files were reopened and their substantive cells inspected;
Microsoft Excel application behavior was not tested. The simple DOCX check does
not establish complex Word layout or native tracked-change acceptance.

## Reporting outcomes, separate from pipeline outcomes

All accepted audit cases use local-only reporting. Start, repeated start, status
and completion persist one task UUID and two unacknowledged events; repeated start
does not duplicate the task. Queued events are not delivered acknowledgements.
The actual report builder writes readable Markdown, schema-2 JSON and a retained
privacy contract; `show` reopens without rerunning professional work. `validate`
rejects altered report content and altered referenced evidence. Invalid receipt
input and deliberately failed/suppressed delivery leave professional deliverables
unchanged. In-memory outage tests preserve the same minimal request for retry.

A new exact-CLI regression proved that direct receipt retry originally ignored
`MPARANZA_INCIDENT_DELIVERY=local-only`: the network-denial audit hook stopped it
before DNS/connection. The maintained shared `notarized_run_receipt.py` now returns
`not_requested/local_only` before making a request or writing request artifacts.
It is synchronized to all three products because this runtime has one source;
corresponding privacy fingerprints/contracts were regenerated. No other Vera/Clara
professional behavior was changed or deployed. The unchanged ordinary receipt
path remains covered by injected-transport tests.

No server receipt, userID/Computer ID linkage, measured provider/model exposure,
training policy, retention or compliance conclusion is claimed by this audit.
The earlier separately authorized live receipt belongs to the previous task and
is not evidence of local-only delivery in these new tests.

## Blocks, causes and recoveries

| Encountered block | Effect and recovery / conclusion |
| --- | --- |
| Initial package loader bypassed normal parent-package initialization | Circular-import-looking failures were harness artifacts; corrected to normal package import, then reran every module |
| Shipped full-edition development tests required pytest | Removed two unused test files from Lucia packaging; did not add development dependencies to the product runtime |
| Full Archive preflight imported absent audit_assurance | Removed the two unused Vera-only reconciliation drivers; retained actual Lucia Archive workflows and tools |
| Incorrect generic `--help`/`--managed-verify` probes | Internal positional/stdin helpers and component checkers use different contracts; reran with their actual arguments/protocols, retained failed probe record |
| One manual `managed ... run --help` probe treated --help as a script path | Not a supported help form; preparation failed. It was inadvertently invoked without test environment settings; default diagnostic state saving failed in the sandbox (`local-state-unavailable`), with no delivered status. Subsequent probes set explicit local-only/test state and use `run scripts/legal_documents.py --help`; no packet-trace claim is made for the failed probe |
| Read-only full extraction rejected test state inside its nested installation | Harness path bug; moved all lifecycle state to the external test directory and reran both ZIPs |
| Report test attempted to overwrite a different existing report | Correct immutable-report protection; moved new report to a separate output directory |
| Later Word verification failed but prior success remained current | Product defect fixed: archive exact previous report before reading new inputs; failure no longer leaves stale success at the current path |
| Italian proofreading displayed raw internal keys/English warning | Product presentation defect fixed using maintained localized labels; rendering regression added |
| Local-only receipt retry attempted network access | Network guard stopped before transmission; shared helper now honors the explicit mode before request creation; exact ZIP and shared-library regressions pass |
| Privacy fingerprints/contracts became stale after owned source changes | Build correctly refused; reviewed changed data paths and regenerated only affected governance records before rebuilding |
| An initial build chain continued after contract generation failed | Tests caught old candidate bytes and stale source parity; switched to fail-fast build sequence and reran final exact ZIPs; failed runs are not included as passes |
| Repository MCP checker created an empty runtime and fell back to system Python | Missing jsonschema in that checker invocation; direct extracted ServiceClient test supplied the separately provisioned runtime and passed all seven owners from read-only files. No repo modules supplied missing code |
| Chromium/LibreOffice startup blocked by macOS sandbox | Retried normal host-approved rendering with isolated profiles; local HTML external requests blocked; visual files retained |
| Process inventory denied by sandbox | Read-only process-name/elapsed-time inspection approved; no other process altered |
| One test patch context no longer matched after formatting | No source mutation from failed patch; reapplied against the current text |
| Deliberately missing/corrupt sources, altered snapshots, bad quote/anchor/report, stale revision, repeated prepare | Expected evidence-preservation protections; errors and recoveries retained, no false professional success or missing-report pipeline failure |

| Broader package test detected unchanged versions after shared source edits | Incremented local candidate manifests, refreshed manifest-dependent privacy fingerprints, rebuilt and reran exact-package checks |
| GitHub PR listing failed to connect | Used all nine local worktree manifests for candidate version selection; remote PR version reservation remains unverified |
| Live download changed during the audit | Retained both snapshots and reran targeted regressions against 0.1.211; current live Archive code differs from this older-base candidate |

## Unknowns and release boundary

No new installation, native Desktop panel test or fresh host conversation was used
for the final revised hashes. Prior native conversations tested superseded bytes.
Protocol startup/discovery is not UI acceptance, and file-format rendering is not
Microsoft Word acceptance. Windows/Linux, clean macOS provisioning, credentials,
external research/subscription journeys, full Archive lifecycle, paired courses,
real client use and professional legal approval remain unverified.

The newer live ZIP contains a concurrent Archive change that is absent from this
branch’s base. The final candidate is a review artifact, not a drop-in replacement
for newer production source. Integration and retesting are required before release.

Implementation and evidence remain for review. No branch, worktree or stash from
another task was removed. Final repository counts and final broad-check results
are recorded in `audit-summary.json` and the completion note below.

## Completion checks

The broader package/update suite before the final manifest-only rebuild returned
415 passed, two conditional skips (curated marketplace installation unavailable),
and one failure: changed plugin source without a manifest version increment.
The version regression passed after incrementing the affected manifests.
The full 418-case suite was not repeated for metadata-only changes; final exact
ZIP suites, all module loads/entrypoints, MCP discovery and source parity were
repeated against 0.1.215. The earlier failure log is retained.

Black and Isort checks passed; Mypy passed for five changed source modules.
Bandit reported zero medium/high findings and three low findings. Focused coverage
is 87.70%; no whole-repository coverage, complete make check or required CI-green
claim is made. The final visual proofreading report shows localized context labels
and the explicit incomplete visual-review limitation. The version-only rebuild
did not change those rendering bytes.

Repository inventory: **9 local branches, 8 remote branches, 9 registered worktrees,
0 stashes**. This exceeds repository steady state because concurrent work exists.
The owned branch/worktree and all review evidence remain as explicitly requested;
no unrelated work was cleaned or overwritten.
