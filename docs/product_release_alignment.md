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
