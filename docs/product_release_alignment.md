# Product release alignment

Vera, Clara and Lucia each have one canonical version in
`plugins/<product>/.codex-plugin/plugin.json`. Codex, Cowork and Antigravity use that same
version. The OpenAI upload ZIP is a format of the Codex release, not another
product version.

From the activated repository environment, build all product distributions with:

```sh
python scripts/build_product_release.py
```

Pass `vera`, `clara` or `lucia` to build selected products. The command builds the
Codex install ZIP, its OpenAI upload ZIP, the Cowork ZIP and public download, and the Antigravity ZIP and version metadata.
Existing builders project the same canonical source into each host format.
Codex downloads and OpenAI upload ZIPs retain the source MCP registrations,
local server implementations, remote endpoints and associated app manifests,
including embedded components. The upload builder must not turn a plugin into
a skills-only product by deleting these capabilities. It checks local MCP
initialization and tool discovery before replacing the archive; remote endpoint
contract checks do not establish remote runtime availability. Marketplace
eligibility and publication remain separate from packaging.
The Cowork builder validates the candidate before replacing its public copy.
A failed overall build is not deployable; rerun the command after correcting
the failure.

The nine `plugin_packages/<product>/*.zip` files are local build outputs, ignored
by Git. A fresh checkout must run the build above before package tests or checks.
CI consumers download the `product-archives` artifact built from their own
workflow's commit by `.github/workflows/build-product-archives.yml`. The artifact
contains the three product directories; extract it into `plugin_packages/`.

Teaching CI always runs its native execution, compiler and code-quality checks.
Editorial verification runs when teaching sources, compiled courses or teaching
runtime change, and on manual runs. Packaging configuration and test-only changes
do not recertify unchanged lessons or refresh their historical review records.
An unavailable comparison base requires full editorial verification.

The reusable build rejects any changes to tracked generated files or public
downloads. This prevents rebuilding from hiding stale committed distributions.
The `Product release alignment` GitHub workflow runs on every PR and main push,
downloads those build outputs, then runs:

```sh
python scripts/build_product_release.py --check
```

Antigravity checks also start each packaged MCP server and request its tool list.
It rejects source drift, missing distributions, version mismatches, and a public
Cowork download that differs from the built ZIP even when the version matches.
Include the generated Claude directories and public website distributions in
the release PR, but do not add the nine ignored local archives. Merge and deploy
only after all checks pass. `make release-products` and `make check-product-releases` are
aliases for these commands.

`scripts/check_repository_archive_size.py` measures `git archive --format=tar.gz
HEAD` and fails above 230 MiB, leaving headroom below the Claude directory's
256 MiB compressed download limit. The target after removing the duplicate
archives is at most 200 MiB. Git history is not part of this measurement.
Do not use LFS, submodules or export-ignore attributes to reduce the download.

Cowork and Antigravity website ZIPs remain tracked at
`static/shared/<product>/downloads/`. Codex website ZIPs are deployment artifacts:
after CI passes, download `product-archives` from the exact tested commit into
`plugin_packages/`, then run `make stage-product-downloads`. This atomically stages
the three Codex ZIPs at `static/shared/<product>/downloads/<product>-plugin.zip`,
which the download page serves. These copies remain ignored by Git. Deploy them
alongside every release, including fresh server checkouts, and verify the public
download hashes against the tested artifacts. The old raw GitHub ZIP URLs no
longer work because those files are no longer tracked.

The Tesoreria PDF and PPTX remain tracked:
their presentation page links to both files. Both marketplace catalogs use
plugin directories, not the ignored ZIPs.

On a fresh server checkout, build the affected local Codex archive with
`python scripts/build_codex_plugin_zip.py <product>` before using
`scripts/manage_incidents.py` to validate an update remedy. A CI artifact from
that exact release commit is also valid. Read-only incident inspection does not
need archives. Cold-start acceptance likewise requires built or downloaded
archives before it clears PATH and provisions its isolated runtime.

Every custom skill in a Claude package uses the owned `mparanza-` prefix. The
builder applies it to future skills automatically, including shared component
instructions, and updates their folders, explicit links and bundled runtime
paths. Canonical Codex skill names, component IDs and course workflow IDs stay
unchanged. Public invocations also retain the host's product namespace, for
example `/vera:mparanza-journal-sampling`.

Before replacing a download, the builder reads the finished candidate ZIP and
rejects unprefixed names, invalid or provider-reserved words, name/folder
mismatches, duplicate members and broken explicit owned-skill links. The same
validation runs on both built and public archives during `--check` in CI. Course
hashes, privacy fingerprints and Vera's execution index bind the renamed bytes;
canonical localization provenance and passive course input data retain their
original identities. These checks enforce our naming contract and currently
documented Anthropic restrictions; they do not guarantee acceptance under a
future provider policy or prove an organization's successful upload.

This aligns release artifacts. It does not claim that an installed copy updated
itself or that a Marketplace submission is published. Keep the public update
notice tied to confirmed Marketplace publication. Native agent acceptance, when
performed, is recorded separately from these mechanical package checks.

For user acceptance, inspect the enabled installation with `codex plugin list
--json`, then run `scripts/check_installed_product.py` with the expected
published version and the exact skill path supplied by the current host catalog.
The command must pass in the conversation used for the behavioral test. It
rejects obsolete local marketplace installations, duplicates and a stale exposed
skill even when a newer package exists on disk. A repaired installation with an
old conversation is incomplete acceptance until a fresh conversation is checked.

Vera and Clara's OpenAI startup hooks check the public version manifest even when
optional onboarding is missing, unfinished or inaccessible. A stale-version
notice remains visible on subsequent sessions; only the public download is
cached. CR polling still excludes incomplete or active tutorials. The hook emits
one JSON response containing package identity, user-facing notices and optional
tutorial context. Their main skills provide a version-only fallback when startup
context is absent. These checks notify; they do not install updates, grant hook
trust, force a host reload, or verify professional output delivery.
