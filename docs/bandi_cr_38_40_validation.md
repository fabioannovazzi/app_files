# CR-38–40: local correction and validation

Date: 2026-09-05. Component: `bandi-agevolazioni` 0.3.5, bundled in the
current Vera 0.1.195 source. These are local changes, not a deployment,
Marketplace publication or CR closure.

## Observed defects and changes

The full server records for CR-38, CR-39 and CR-40 remain open and unresolved.
CR-40 explicitly says ChatGPT was an acceptance requirement, not an observed
reproduction environment. The existing component already had reviewed source
plans, query-scoped selections, direct-before-semantic ordering, source checks,
review hashes, scan snapshots and a completion gate.

- CR-38: those checks did not require an issue inventory. Gazette checks now
  carry official index URLs, enumeration time/window, every declared issue's
  URL, publication date, check status/time, relevant act URLs and notes.
  `checked` rejects absent/incomplete inventories, skipped issues, duplicate
  IDs, inconsistent windows and later-than-check observation times. Empty
  inventories require an evidenced rationale. Inventory changes invalidate
  source-check reviews; terminal scans retain the exact inventory. Programming
  and no-operating-calendar lifecycle states are supported and unmatched
  opportunities are visible in the report.
- CR-39: the shared method now requires reasoned coverage of EU, national,
  regional, local and sectoral institutions, official-directory/link discovery,
  append-only source additions/replacements, provenance, exclusions and gaps.
  It reuses the existing source registry rather than adding a parallel system.
  Reports expose source URLs, relevance, selection rationales, issue evidence
  and unmatched findings. Code checks evidence structure; the model and
  professional select relevant institutions and interpret acts.
- CR-40: the component, Vera wrapper and Marketplace instructions explicitly
  point to the same source-first and institutional-discovery references.
  Current package-builder changes already preserve Vera source skills in the
  ChatGPT ZIP. With browsing but no local execution the same research method
  produces a visible registry and issue ledger and discloses absent local
  validation, hash-bound review, workspace isolation and persistence. Without
  browsing current coverage stays partial. Application dossiers still require
  their Studio Archive boundary. Privacy engineering records and the five
  localized public model-data explanations describe these distinctions.

## Public reference

The official [Gazzetta summary for Serie Generale 200, 29 August 2026](https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio/home?dataPubblicazioneGazzetta=2026-08-29&numeroGazzetta=200)
and [act 26A04448](https://www.gazzettaufficiale.it/atto/serie_generale/caricaDettaglioAtto/originario?atto.codiceRedazionale=26A04448&atto.dataPubblicazioneGazzetta=2026-08-29&elenco30giorni=false)
confirm the reported 28 July programming decree. This targeted lookup verifies
the reported reference; it is not a full-window discovery acceptance run.

## Validation

- 144 Bandi tests pass, including 16 new institutional-discovery regressions.
- Scoped Bandi script coverage: 81.45%; opportunity radar: 85%.
- Black, Isort, scoped Mypy and Bandit pass; privacy register validation passes.
- 28 privacy tests and 20 update-notification/icon tests pass.
- The package suite completed 372 passing tests and one whole-Vera drift
  failure. Subsequent exact rebuild/check commands passed for Codex, ChatGPT
  and Cowork; later unrelated edits in the shared checkout caused whole-package
  drift again. Do not treat these bundles as an isolated release candidate.
- Scoped comparison against each builder's expected projection passes with no
  Bandi differences: Codex 48 files, ChatGPT 49, Cowork 45. Cowork legitimately
  projects instructions and excludes evaluation files; byte equality to raw
  component source is not its package contract.
- Packaged MCP check initialized and listed tools for all 18 Vera servers.

Source: `plugins/bandi-agevolazioni/` and `plugins/vera/skills/bandi-agevolazioni/`.
Generated ZIPs: `plugin_packages/vera/vera-plugin.zip`,
`plugin_packages/vera/vera-chatgpt-upload.zip`, and
`plugin_packages/vera/vera-claude-plugin.zip`.

## Remaining acceptance and release evidence

Run the same ordinary recent-PMI research prompt with the actual candidate
package in Codex and ChatGPT. Preserve package hash/version, normal answer,
capabilities, official issue inventory covering the requested window, dynamic
institutional registry, blocked-source behavior, and lifecycle distinctions.
The issue ledger is operator-attested and professionally reviewed; code cannot
prove that a page was read or that the publisher's archive is complete. Tests
and shared instructions do not establish model execution consistency.

No server code, publication state or CR disposition was changed. Deployment,
publication and closure remain separate steps. Existing unrelated work was
preserved; no branch, worktree or stash was created for this task. Observed
repository counts: 3 local branches, 2 origin branches (excluding symbolic HEAD),
3 registered worktrees and 0 stashes.

## Isolated deployment candidate

The user subsequently authorized deployment. The candidate is prepared from
`origin/main` at `da1f6dcc`, in one temporary release worktree, as Vera 0.1.201
with Bandi 0.3.5. Only the Bandi changes and their generated release artifacts
are included. Codex, ChatGPT and Cowork ZIP rebuilds and full drift checks pass
in this isolated checkout. The 144 Bandi tests pass again with 81.45% coverage.
The `bandi-source-first` CI job enforces these tests and focused code quality.
The published-version manifest stays at the actually published Vera 0.1.200;
server deployment does not establish Marketplace publication or live research
acceptance, so CR-38–40 remain open pending that evidence.
