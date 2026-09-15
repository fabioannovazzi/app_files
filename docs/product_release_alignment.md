# Product release alignment

Vera, Clara and Lucia each have one canonical version in
`plugins/<product>/.codex-plugin/plugin.json`. Codex and Cowork use that same
version. The OpenAI upload ZIP is a format of the Codex release, not another
product version.

From the activated repository environment, build all product distributions with:

```sh
python scripts/build_product_release.py
```

Pass `vera`, `clara` or `lucia` to build selected products. The command builds the
Codex install ZIP, its OpenAI upload ZIP, and the Cowork ZIP and public download.
Existing builders project the same canonical source into each host format.
The Cowork builder validates the candidate before replacing its public copy.
A failed overall build is not deployable; rerun the command after correcting
the failure.

The `Product release alignment` GitHub workflow runs on every PR and main push:

```sh
python scripts/build_product_release.py --check
```

It rejects source drift, missing distributions, version mismatches, and a public
Cowork download that differs from the built ZIP even when the version matches.
Include generated distributions in the release PR. Merge and deploy only after
all checks pass. `make release-products` and `make check-product-releases` are
aliases for these commands.

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
