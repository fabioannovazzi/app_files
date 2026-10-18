# Shared privacy architecture

This migration makes Vera, Clara and Lucia use the same privacy review skill,
schemas, runtime profiles, manifest validator, public explanation renderer and
run-report binding. It preserves product-specific data paths and existing signed
reports. It does not change user case files or reset usage/testing history.

## Completion evidence

- [ ] Register every top-level skill, embedded component and shared service.
- [ ] Review the governed implementation of every newly registered surface.
- [ ] Migrate Clara's Codex-only records and complete Lucia's register.
- [ ] Keep Studio Archive classified as infrastructure.
- [ ] Use one canonical source for the review skill, schemas and validators.
- [ ] Bind localized public explanations to reviewed product/workflow contracts.
- [ ] Bind new actual-run reports to those contracts without deriving observations
      from expected behavior; preserve old report bytes and receipt verification.
- [ ] Validate source freshness, registration coverage, translations, public
      bindings and every generated host package.
- [ ] Exercise real synthetic runs, readable delivery, saved-report reopening and
      signed receipts; record exactly which host/session was exercised.
- [ ] Pass required CI, deploy the exact merged commit and verify public bytes.
- [ ] Remove only this task's temporary branch/worktree and record repository counts.

## Judgment boundary

The agent reviews source and judges whether a description accurately explains
its data path. Code checks mechanically verifiable facts: schema, identifiers,
coverage, exact source hashes, registered references and package byte identity.
A matching hash is not evidence of professional correctness, model-provider
transmission, deployed server behavior or a completed semantic review.

Public contracts describe possible exposure. Run reports describe observed
exposure, including explicit unknowns. A report may disclose behavior outside its
contract; it must never be rewritten to make the expected and actual behavior
appear consistent. The receipt continues to attest only the exact report digest.

## Worktree boundary

Implementation starts from production commit
`556d8810f76c701155fcbf2eb1f25f91402e4f3d` in an isolated worktree. The dirty primary
checkout and concurrent Archive release remain untouched. Marketplace activity
is outside this task.

## Implementation and current validation

Canonical governance lives in `plugins/_shared/privacy-runtime/`; all three
products receive identical schemas, review skill, references and validator.
`privacy/registry.json` assigns every skill/component and workflow alias a single
owner. It records explicit host service/workstream/path omissions. Source review
fingerprints cover implementation files; rebuilding does not refresh them.

There are 104 registered workflow/infrastructure records and 89 product/page
bindings. Product service registers retain the original source-specific payload,
access and retention declarations. No new provider account or per-case privacy
questionnaire is introduced.

`build_privacy_contracts.py` produces retained JSON contracts and public catalogs.
The shared HTML renderer selects the product and page, supports localization,
keeps the section last, and displays an explicit placeholder when evidence is
missing or a host is unreviewed. Existing historical inline copy is no longer
consumed by the renderer; authoritative changes go into the manifests.

The product report builder emits schema 2 with exact source/installed contract
identities and an agent-authored comparison. Missing comparison stays unreviewed;
observations never come from the expected manifest. The saved contract accompanies
the local report. Schema-1 reports and signed receipt bytes remain unchanged.
A host-specific package cannot claim another runtime's installed review.

The package builders validate source freshness, preserve the source declarations,
project installed hashes after host transforms, check exact reviewed path omissions,
and seal the final execution manifests. The common release command checks shared
source synchronization and public contract drift before building all hosts.

Local release candidate: Vera 0.1.409, Clara 0.1.299, Lucia 0.1.122. All twelve
archives built. Shared privacy tests: 67 passed, binding module coverage 87.36%.
Renderer behavior tests: six passed. Black, Isort, Mypy and Bandit passed for the
new implementation. Final CI, deployment and live acceptance are pending.
