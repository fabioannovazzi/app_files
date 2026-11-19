# Lucia 0.1.258: explicit internal runtime settings

Scope: Lucia packages only. The shared reporter, receipt and bootstrap sources and
source projections for Vera and Clara change together; their released packages and
versions are not updated. No OpenAI Marketplace submission or publication.

## Implementation and boundaries

- `operational_incidents.configure_settings` accepts server-owned host/session/task,
  plugin root, private state/device directories, delivery mode and recovery guard.
  The CLI accepts an explicit JSON `--settings` file. UUID and symlink-path checks
  remain. Native identity files, endpoints, outbox entries and receipts retain their
  existing formats and locations.
- The on-demand server passes a private session settings file to the incident host,
  which passes JSON arguments to its Python bridge. Workflow calls bind their task
  UUID explicitly. Normal shutdown removes the session file; a killed process can
  leave an orphan settings file containing internal paths and random IDs, no keys.
- Fixed recovery children inherit the normal environment. Extra internal values
  are arguments, preserved across a base-Python handoff. This avoids explicit
  environment reads in the reporter; it does not claim credentials are absent
  from the inherited process environment or predict Anthropic's scanner verdict.
- Receipt endpoints and local-only overrides are explicit test parameters, never
  environment reads. Production defaults and redirect/endpoint validation remain.
- The pinned uv 0.12.10 wheel still requires its SHA-256. `--install-dir`,
  `--cache-dir`, `--no-bin` and `--no-registry` select private installation without
  environment copying. This uv version has no `--bin-dir`, and `python find` has
  no install-directory flag. The helper inspects only its private installation
  tree and probes CPython 3.12, SSL, venv and ensurepip. Proxy/CA values reach uv by
  normal inheritance. uv's CPython download uses Astral's GitHub releases, so a
  claim that the whole installation contacts only PyPI would be inaccurate.
- No userConfig fields: no user-supplied secret or production endpoint was added.
  The unsupported Claude `shortDescription` field is removed from Lucia's Claude
  manifest; its full description and Codex metadata remain.

## Observed verification

- Incident CI suite: 610 passed, 8 platform-dependent skips; coverage 83.41%.
- Workflow usage, receipt service and on-demand MCP suite: 287 passed.
- Receipt and Python bootstrap focused suite: 40 passed.
- Shared runtime/launcher suite: 243 passed, 9 all-product archive comparisons
  excluded locally; the release builds Lucia only. Mypy: 30 source files passed.
- Real cold bootstrap on macOS arm64 installed private CPython 3.12.14 and passed
  the capability probe. No global Python installation was changed.
- Lucia package build: all host versions aligned at 0.1.258. Claude Code 2.1.328
  strict validation passed. The three generated helpers contain no `os.environ`
  or `getenv(` references. Repository archive: 127.82 MiB, below the 230 MiB guard.
- Native Archive reporting fixture tests: 12 passed. Reduced-edition privacy and
  packaging tests for Clara and Lucia: 33 passed.
- Lucia Codex package tests: 36 passed. Native execution tests: 41 passed.
- Scoped CI artifact drift guard: seven regressions passed. CI still builds all
  products for testing; it rejects every source drift and artifact drift for any
  product whose version or packaged files changed in the PR. Unreleased siblings
  are build-only previews. Their generated public ZIPs travel in the CI artifact
  so downstream parity checks compare the same build, without committing them.
- New tests cover explicit settings files, identity reuse, ignored environment
  overrides, UUID/path rejection, native on-demand forwarding/session cleanup and
  recovery settings across base-Python reentry.

## Encountered blocks and their disposition

- Native process-control and nested macOS sandbox tests cannot run inside the
  chat sandbox: the host-context rerun passed all 59 focused tests.
- Sandbox denied localhost listeners: reran the same isolated integration tests
  with the required host permission; no production endpoint substitution.
- Sandbox denied the initial pinned-wheel download: permitted the fixed download
  and verified its SHA-256 before the real bootstrap test.
- Source changes invalidated privacy fingerprints and course source inventories:
  reviewed changed data paths, corrected inherited-environment claims, refreshed
  the selected records and regenerated inventories. Lesson content is unchanged.
- Claude Code 2.1.328 strict validation initially rejected the pre-existing
  `shortDescription` field as unknown. Removed it from Lucia's source template.
- A local all-product archive test cannot compare missing/unrebuilt Vera and Clara
  ZIPs. Local release parity targets Lucia; CI builds its own test archives.

- Initial Windows/macOS CI native execution tests still supplied task/delivery
  settings through the environment. The native host and detached workers now
  propagate explicit settings, and their fixtures use isolated directories.
- Initial CI required committing all three rebuilt packages. Its drift guard now
  distinguishes released products from build-only sibling previews while retaining
  source and released-artifact checks.

- Native Archive mocks assumed the last worker argument was its job directory;
  they now read the explicit `--execute` value. No production change was needed.
- Reduced editions omit the native MCP server. Their privacy projections now
  explicitly disclose omission of the new server-owned settings control.
- CI artifact extraction over old tracked Cowork trees retained two obsolete
  top-level environment helpers in unreleased sibling directories. Consumers now
  remove only generated Cowork trees before extracting this commit's artifact;
  strict package verification remains enabled.

- The optional local update-notification cache check fails for unchanged Clara:
  public manifest 0.1.248 versus installed curated cache 0.1.407 (17 tests passed,
  one skipped). No Clara publication or public-version change is part of this task.

- Before all fixtures were migrated, the first integrity-test run used default
  local diagnostic state. Eight receipts matching the synthetic fixture hashes
  were subsequently observed there (five Codex, three Cowork). They are retained;
  no unrelated local history was deleted. Captured logs do not establish every
  possible remote delivery from that initial run. The affected fixtures now pass
  explicit isolated settings. Preflight and launcher delivery messages now use the
  same explicit settings as the reporter, including base-Python reentry.

Strict manifest validation is not the directory's safety scan or policy review.
Fabio must select **Check for new commits** on Lucia's directory page after merge.
These results do not certify installation in an existing customer chat.
