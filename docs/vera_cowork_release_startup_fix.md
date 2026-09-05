# Vera Cowork startup repair — 2026-09-05

## Outcome

The public Cowork 0.1.142 ZIP reproduced the reported 12 missing-manifest
crashes. Five other configured servers failed implementation-tree checks;
only INPS initialized. The repaired local Cowork 0.1.143 and full Codex
0.1.192 install ZIPs each passed initialization and tool discovery for all 18
registered servers.

The release check reads the configured server list rather than a fixed module
allow-list, so newly registered servers are exercised too. Coverage tests
compare the packaged registrations with the source registrations.

## Changes

- Preserve nested component manifests in Cowork. Servers consume these files
  as runtime metadata and integrity-receipt inputs; the Cowork plugin still has
  only its Claude manifest at the root. Lucia's shared components retain the
  same required metadata.
- Declare `injectLocalServer: false` in the five exact implementation adapters.
  The install builders omit the undeclared generic review server. Integrity
  checks remain active; the separate ChatGPT upload keeps its review bridge.
- Resolve Journal-Bank's shared implementation from its packaged vendor folder,
  falling back to the source-checkout layout when running from source.
- Require real `initialize` and `tools/list` responses from clean ZIP
  extractions before install builders replace distributable artifacts. Missing
  Node.js, missing configuration, crashes, invalid replies, tool-list failures,
  unexpected implementation files, and timeouts fail the check.
- Repeat runtime verification during package `--check`; add the
  `Packaged plugin runtime` CI workflow. No remote branch-protection settings
  were changed, and the new CI workflow has not yet run on GitHub.

## Local artifacts

| Artifact | Version | SHA-256 |
| --- | --- | --- |
| `plugin_packages/vera/vera-claude-plugin.zip` | 0.1.143 | `e52badb5aa88217c302146ee06387659e3b1029577a6da407a64f685d1d0fe7d` |
| `static/shared/vera/downloads/vera-cowork-plugin.zip` | 0.1.143 | `e52badb5aa88217c302146ee06387659e3b1029577a6da407a64f685d1d0fe7d` |
| `plugin_packages/vera/vera-plugin.zip` | 0.1.192 | `31deed9de690ade766d68a2903333d824931049b55d81499dd39fa533315b3f9` |
| `plugin_packages/vera/vera-chatgpt-upload.zip` | 0.1.192 | `b05a36f29079b5857125fcad507b87a1bcb86cc025991080bde058c952372900` |

Cowork directory, private ZIP, public ZIP, and marketplace-catalog source-drift
checks passed. Vera and Lucia Codex install-package checks and Vera ChatGPT
upload checks passed. The build also regenerated the affected Lucia packages.
The public server was not changed.

## Validation and limits

- 70 tests passed across packaged MCP startup, Cowork packaging, privacy
  fingerprints, and Cowork privacy boundaries; the subsequently added
  missing-configuration regression also passed.
- Eight focused implementation-integrity/runtime tests passed across the five
  affected workflow modules. An earlier broad workflow run was stopped after
  118 passing tests because most of its accounting scenarios were outside this
  packaging change; it was not a complete workflow-suite pass.
- 412 package, update-checker, Lucia, and icon tests passed in the isolated
  snapshot, with six known failures explicitly excluded: two Clara PNG render
  tests, an existing homepage CSS-selector assertion, Lucia's existing
  matter-opening privacy fingerprint, and two public-version-versus-installed-
  marketplace checks. The Lucia fingerprint mismatch was reproduced with the
  unchanged validator. This is not a claim that the full repository suite is
  green.
- Black, Isort, Mypy for both builders, Node syntax checking, and Bandit with
  medium/high severity reporting passed for the checked files.
- Runtime checks ran locally with Node.js 24 on macOS. The new CI workflow
  specifies Node.js 22 on Linux; that remote run remains unobserved. No new
  full Claude Cowork desktop acceptance or professional-workflow acceptance was
  performed.

Another task began adding AML to the primary checkout during validation. Final
checks used a temporary source snapshot excluding the unfinished AML additions
while preserving the already-present Report Builder changes. The artifacts
above match that tested snapshot. The later combined checkout must be rebuilt
and checked after the AML work is complete; these results do not validate that
unfinished feature. Other tasks' files were preserved.

No deployment, publication, PR, or commit was performed by this repair task.
Git topology remained one local branch, one remote branch, one registered
worktree, and no stashes.


## Desktop upload acceptance follow-up

On 2026-09-05, a fresh public ZIP upload in Claude Desktop failed with
`Plugin description must be at most 500 characters.` This is a separate
installation failure from the MCP startup failures covered above. Cowork
0.1.145 shortens Vera's description; the shared builder rejects invalid
descriptions before replacing artifacts. Boundary tests cover 500 versus 501
characters, missing values, and empty values, for templates and fallback
projection. Lucia Cowork 0.1.17 applies the same description constraint.

All 18 Vera packaged servers pass initialization and tool discovery. The
corrected archive preview displays in Claude, but installation and an actual
Cowork workflow remain pending explicit user approval of the candidate install.
