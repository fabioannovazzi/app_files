# Shared privacy architecture

This migration makes Vera, Clara and Lucia use the same privacy review skill,
schemas, runtime profiles, manifest validator, public explanation renderer and
run-report binding. It preserves product-specific data paths and existing signed
reports. It does not change user case files or reset usage/testing history.

## Completion evidence

- [x] Register every top-level skill, embedded component and shared service.
- [x] Review the governed implementation of every newly registered surface.
- [x] Migrate Clara's Codex-only records and complete Lucia's register.
- [x] Keep Studio Archive classified as infrastructure.
- [x] Use one canonical source for the review skill, schemas and validators.
- [x] Bind localized public explanations to reviewed product/workflow contracts.
- [x] Bind new actual-run reports to those contracts without deriving observations
      from expected behavior; preserve old report bytes and receipt verification.
- [ ] Validate source freshness, registration coverage, translations, public
      bindings and every generated host package.
- [x] Exercise real synthetic runs, readable delivery, saved-report reopening and
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

There are 104 registered workflow/infrastructure records and 98 product/page
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
archives built. Shared privacy tests: 74 passed, binding module coverage 87.36%.
Renderer behavior tests: six passed. Black, Isort, Mypy and Bandit passed for the
new implementation. Signed-receipt acceptance passed for all three products. Final CI and deployment are pending.

Every user-facing workflow now requires a registered explanation page. Five missing pages were added with five-language source-reviewed descriptions; existing planner, research-validator and transformation pages are now bound for Vera as well. Internal engines remain explicitly separate.

## Controlled acceptance

On 18 October 2026, built Codex-format release packages ran the following synthetic
operations in the local Python environment. This is packaged-CLI evidence, not a
fresh installed Codex, Cowork, ChatGPT or Antigravity conversation acceptance.

| Product | Observed operation | Report and receipt |
| --- | --- | --- |
| Vera 0.1.409 | Three source rows normalized; two systematic sample rows generated | Schema 2, public contract matched; saved report reopened unchanged; server signature verified |
| Clara 0.1.299 | Current one-slide PPTX claim matched its retained source map | Schema 2, public contract matched; saved report reopened unchanged; server signature verified |
| Lucia 0.1.122 | Three-line document rendered with the 100-versus-90 inconsistency and unresolved correct amount | Schema 2, public contract matched; saved report reopened unchanged; server signature verified |

The Vera technical test deliberately inspected the complete tiny normalized
population as well as its sample. Its report retains `divergence`, documenting
that extra exposure rather than presenting it as the ordinary minimized review.
Clara and Lucia record an agent-authored `consistent` comparison for the inspected
phases. These judgments do not attest provider-side delivery or legal correctness.

The actual receipt requests contained four fields for Vera and five for Clara
and Lucia (adding product). No source content or full report was sent. Existing
receipt protocols remain unchanged. No usage reset, rating, user completion,
recovery claim or external message was created by these acceptance operations.

Private evidence, exact package/report/contract hashes, report files and signed
receipts are retained in
`outputs/shared-privacy-acceptance/2026-10-18/public-candidate/`, with preceding
candidate evidence retained separately in `final/` and `verified-release/`. The local review also covered
Clara's Italian explanation, Lucia's English explanation and Vera's nested
integration page. Thirty-six public-page tests passed; six renderer tests cover
product separation, language and unavailable-review behavior.

The integration pass also exercises LIPE approval/export and native Archive
closure with the new report. They validate the recorded report and its evidence
without rebuilding it against the current installation. Legacy disclosures still
reopen; changed evidence, invalid execution fields and mismatched readable copies
remain rejected. Packaged closure retains the separate privacy contract artifact.

Repository review file lists are sorted before packaging so filesystem enumeration
cannot change a package's retained review or integrity hashes. A regression reverses
that enumeration and requires identical projected package bytes.

Public entry pages use versioned URLs for the shared renderer, function data and
navigation. The template renderer passes the same release identity to its loaded
scripts so a previously cached script cannot replace the updated contract reader.

The updated teaching bindings change only source inventories: the eighteen changed
course payloads were compared with commit `32f7e7e0d90a3191e4c1ea80489eb0b750b76b16`
after excluding `sources` and `retained_from`, and their authored content was identical.
Only the current course digest in each release review was advanced; all dated
editorial and output judgments remain historical. Fresh CI execution is still required.
