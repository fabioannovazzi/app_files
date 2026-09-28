---
name: localize-vera
description: Assess or implement adaptations of Vera's existing functions for a new country, canton, region or jurisdiction. Use for questions about which Vera functions transfer and how to localize them while retaining one common core. Excludes discovery of new services and distribution planning.
---

# Localize Vera

Start from the actual Vera product. For each existing function, establish whether
its professional purpose makes sense in the target jurisdiction. Where it does,
retain the common function and adapt the differences. Where it does not, leave it
outside that jurisdiction's scope.

Services that might be useful locally but are absent from Vera are outside this
work. Do not count their absence as a localization gap, add them to a roadmap, or
build a separate catalogue of jurisdiction-only functions. The user's explicit
scope is authoritative; this skill does not turn localization into market entry,
distribution, or a survey of everything the local profession does.

This is a product-development workflow. Read Vera's professional skills as product
evidence; inspecting them does not itself invoke a client workflow, create a
client case, or authorize sending product feedback.

## Establish the product and target

Resolve the Vera source from the user's workspace, repository or installed plugin.
In the app_files repository, start with `plugins/vera/skills/vera/SKILL.md`,
`plugins/vera/skills/*/SKILL.md`, the plugin manifest and referenced shared modules.
Follow wrappers to their actual implementations. Do not assume a repository file
matches an installed or published version. If source is unavailable, use inspected
product documentation provisionally and identify what cannot be verified.

Record the product version or commit, any relevant working-tree changes, source
paths and assessment date. Establish the target jurisdiction at the necessary
level, the intended professional user and the working/output languages. Language,
currency and governing jurisdiction are independent choices. Use settled context;
ask only for missing information that materially changes the assessment and
continue independent inspection while waiting.

Assess each target jurisdiction separately, including relevant subnational levels.
Switzerland / Geneva and France are separate targets even when both use French;
Switzerland / Zurich and Germany are separate targets even when both use German.
Language never selects the governing rules, authorities, document formats or
professional requirements. Translation coverage does not establish jurisdiction
coverage.

For each function, identify which differences attach to the country, canton or
other relevant territorial level, and which attach to language, currency or the
client's source system. Reuse shared national or language adaptations only where
the evidence supports the same behavior. Geneva and Zurich may share Swiss
elements while requiring different cantonal elements; do not assume either that
all behavior is common or that every function needs a cantonal variant. Record
the applicability and evidence for each difference without imposing a particular
code-inheritance architecture.

Keep an existing assessment as the starting record. Refresh the product baseline
when needed and identify actual catalogue changes rather than silently replacing
the prior scope.

## Inventory before selecting

Account for the complete current catalogue before recommending a subset, unless
the user explicitly limited the task to named functions. Reconcile router entries,
skill directories and wrappers. Use stable existing function IDs and names.

Distinguish user-facing functions from routers, shared helpers and internal
controls. Map helpers to the functions that use them rather than presenting every
technical skill as a separate professional service. Grouping for readability must
leave each function's disposition traceable. Supporting functions such as client
archives and planning deserve the same inspection as accounting or legal work;
do not restrict the inventory to the stereotypical duties of the local profession.

For each function, establish its current professional purpose, inputs, method,
deliverable, responsibilities and dependencies from inspected evidence. Read the
implementation or relevant tests before asserting concrete currency, language,
format or jurisdiction support. A title, translated prompt or generic description
does not establish runtime capability. Document extraction does not imply return
preparation; producing a dossier does not imply filing it.

## Judge transfer of the existing purpose

Start with the hypothesis that comparable firms serving comparable clients share
recurring professional work. For each Vera function, state that work in ordinary
terms before examining local rules: what evidence is used, what the professional
does with it, and what useful deliverable results. Test transfer of this purpose;
do not assume a foreign jurisdiction requires rebuilding the function. The
hypothesis does not establish that every firm offers every service, that every
method transfers, or that any existing implementation is ready locally.

Keep three questions separate: which professional work is shared; what the target
jurisdiction changes; and what depends on the individual firm's clients, software
or mandate. Routine source mapping or choosing an already supported language is
configuration or qualification, not automatically a product change. Record a
required adaptation only when the current function has an evidenced gap.

Use model-led professional reasoning, not keywords, scores or a rule that assumes
all accounting functions transfer and all legal functions do not. Where a local
fact matters, research it through current authoritative sources, with its scope
and effective date. Research questions should arise from an existing Vera function.
Do not start with a list of local services and map Vera against it.

Ask whether a professional in the target jurisdiction would use the same core
work to reach a recognizably equivalent deliverable. Explain the concrete local
use and its evidence. Separate inferred usefulness from observed demand or field
validation; do not invent adoption or savings.

Assign one disposition to every function in scope:

| Disposition | Meaning |
| --- | --- |
| Use | The purpose applies and no necessary adaptation has been identified in the inspected scope. State remaining verification limits. |
| Adapt | The purpose applies, with concrete changes inside the existing function. |
| Unresolved | Evidence is insufficient to establish usefulness or the adaptation. Record the missing evidence and how to resolve it. |
| Ignore for this target | Evidence supports that the existing purpose or supported source has no relevant application in the target scope. Retain the function elsewhere. |

A function's disposition and required adaptations may differ between targets.
Qualification for Geneva does not qualify France, Zurich or Germany. When adding
a target, reuse the inspected Vera baseline and relevant verified adaptations,
then assess the remaining differences explicitly; preserve earlier target results.

Lack of evidence is not evidence of irrelevance. An expensive adaptation is not
automatically a new function or a reason to ignore it. Conversely, sharing a name
or using similar documents is insufficient to establish an equivalent purpose.
Consider relevant cross-border uses when supported by the mandate; do not invent
them to keep every function in scope.

## Specify adaptations within the common core

For each `Adapt` function, identify what remains common and what actually differs:

- **Inputs:** document layouts, accounting exports, identifiers, dates, decimal
  conventions, payment references and source-system meanings.
- **Method and requirements:** applicable frameworks, authoritative sources,
  account mappings, calculations, professional responsibilities and applicability.
- **Outputs:** language, terminology, templates, disclosures, currency, units and
  the recipient's evidenced requirements.
- **Operation:** dependencies, software procedures or data-handling requirements
  only where inspection establishes a relevant difference.

Replace vague instructions such as "make it Swiss" with the affected input,
behavior or output, its supporting evidence and an acceptance example. Distinguish
configuration or source-content changes from parser, calculation or workflow work.
Specify reporting currency and any conversion basis; changing a symbol does not
establish currency support. Check French labels and report generation separately
from the model's ability to write French prose.

Keep one function identity and shared professional method. Use configuration,
source collections, templates or adapters where appropriate to the implementation;
do not prescribe a new abstraction layer without a concrete need. Localized names
may change, but must map to the existing function. Preserve behavior in already
supported jurisdictions and prevent their assumptions from leaking into the new
one. New supporting code is allowed when it serves the same existing function;
an unrelated professional service is not an adaptation.

Treat examples as questions to inspect, not a frozen capability list: business
planning calls for checking currency, report language and actual financing
assumptions; an archive calls for checking identity, retrieval and document
language; annual accounts may require substantial framework changes while
retaining the accounts-preparation purpose. Never assume these functions' current
support from an earlier assessment.

## Maintain one reviewable assessment

Save the assessment in the user's chosen location or an appropriate local task
artifact. Keep client material out of product source and public folders. Include:

1. The product baseline, target, user scope and evidence limits.
2. A complete matrix: existing function ID/name, current purpose, local use and
   basis, disposition, common elements, necessary adaptations, verification status
   and source references. Split wide tables into linked detail when useful.
3. Concrete changes and acceptance examples for functions marked `Adapt`;
   unresolved evidence and reasons for ignored functions remain visible.

Key each assessment entry by existing function and explicit target jurisdiction.
For multiple targets, use separate target columns or linked records with their
own evidence and verification status. Keep shared adaptations traceable across
them without merging distinct jurisdictions into a French or German edition.

Use `scripts/catalogue.py` to snapshot all existing skill IDs and check complete
coverage of a full-catalogue assessment. It checks file identities and exact set
membership only; purpose, role, relevance and adaptations remain model judgments.
For an explicitly limited assessment, record that narrower scope visibly rather
than claiming the full-catalogue check passed.

```bash
python scripts/catalogue.py inventory --root /absolute/path/to/vera --output /task/catalogue.json
python scripts/catalogue.py check --inventory /task/catalogue.json --assessment /task/assessment.json --root /absolute/path/to/vera
```

The assessment JSON contains `catalogue_fingerprint` copied from the snapshot,
`target` with an explicit `id`, and `rows`, each with one existing `function_id`.
Additional evidence and judgment fields are authored for the actual assessment.
The snapshot records the manifest and skill-entrypoint hashes, not a full source
tree or a runtime certification. Read shared modules separately for capability
claims. A successful coverage check proves neither usefulness nor legal accuracy.

For a worked example, read [the Geneva assessment](../../../plugins/vera/skills/vera/references/localization/geneva/assessment.md)
when useful. It is a dated assessment of its recorded Vera baseline, not the
current catalogue or a reusable statement of Swiss law.

Keep disposition separate from implementation and validation status. Inspected
instructions, inspected code, synthetic checks and reviewed local professional
cases establish different things. "Use" never means "production verified" by
itself. Give a useful bounded conclusion when validation is incomplete.

Conversational summaries must agree with this record. A shortlist is explicitly
a shortlist, not the whole catalogue. On a follow-up about a function, consult its
existing row, add findings there and explain any changed disposition or adaptation
with the new evidence or user constraint. Record substantive changes with date,
previous conclusion and reason. Correct earlier mistakes directly; do not preserve
them for apparent consistency or silently add functions only after reminders.

Recommend implementation order only when requested or needed to execute the task,
using confirmed relevance, dependencies and verified gaps. Do not introduce a
launch timetable, distribution plan or unsupported effort estimate.

## Implement when requested

An assessment request calls for the evidence and adaptation specification. When
the user requests implementation, proceed with the authorized changes through the
repository's normal instructions; do not demand a second authorization for the
same work. Creating this skill alone does not request localization of the product.

Make the smallest coherent changes within existing functions. Use appropriate
tests for changed behavior: representative target inputs and expected reviewed
outputs, explicit handling of unsupported cases, and relevant regression checks
for the shared method and existing jurisdictions. Synthetic checks do not prove
professional acceptance on real client material. Do not create tests that merely
repeat instruction wording.

Where jurisdiction selection affects behavior, verify that two targets sharing
a language receive their own applicable sources, rules and outputs. Also verify
that changing output language alone does not change the governing jurisdiction.

Update the same assessment with implemented changes, actual checks, remaining
unknowns and available artifacts. Distinguish source changes, packaged releases,
publication, installation and validated professional use. Follow applicable
release instructions and the user's authorization; localization does not imply
permission to publish a new product or communicate externally.
