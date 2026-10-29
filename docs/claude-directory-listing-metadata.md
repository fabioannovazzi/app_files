# Claude directory listing metadata

Reviewed 2026-10-29 for Vera 0.1.522, Lucia 0.1.189 and Clara 0.1.363.

The official manifest reference documents `icon`, `documentationUrl`,
`supportUrl`, `privacyPolicyUrl` and `termsOfServiceUrl` as directory fields:
https://code.claude.com/docs/en/plugins-reference#directory-listing-fields
The icon is a package-relative image path. The builder retains the existing SVG
bytes and all listing fields from each Claude template. Author and keywords
remain unchanged. Documentation points to each existing product homepage.
The support endpoint was verified with HTTP GET.

`shortDescription` is retained at the brief's request, using the Codex interface
value, but is not documented in that reference or the fetched SchemaStore
schema (generated 2026-04-23). Claude Code 2.1.312 reports it as unknown, so
`claude plugin validate --strict` fails. The other added fields are accepted.
This is an explicit validation limitation, not a claim that the directory reads
this field. No directory UI acceptance or submission-row refresh is proven.

The canonical versions are bumped for all host packages. Privacy source
fingerprints and generated contract bindings are refreshed because they cover
the canonical manifests and Claude projection builder. The reviewed delta is
version/listing metadata only: no model payload, recipient, runtime routing or
professional workflow behavior changes. This delta review does not claim a new
host-session privacy-report acceptance test.

Publishing these source packages and direct downloads does not submit a new
Marketplace version or prove changes to an existing directory listing.
