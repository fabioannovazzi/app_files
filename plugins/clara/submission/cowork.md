# Clara · Cowork directory submission

## Listing

- **Name:** Clara
- **Compatibility target:** Cowork
- **Developer:** Mparanza
- **Category:** Productivity
- **Website:** https://mparanza.com/static/shared/clara/index.html?lang=en
- **Privacy policy:** https://mparanza.com/privacy
- **Terms:** https://mparanza.com/terms
- **Support:** https://mparanza.com/support
- **License:** AGPL-3.0-only
- **Contact:** fabio@mparanza.com

**Public description**

> AI companion for consultants. Clara plans advisory assignments as reviewable
> contracts, then directs the living case: she states the current answer,
> maintains its evidence and assumptions, chooses the next decision-relevant
> work, and revises the position when new evidence or partner judgement changes
> it. She routes bounded contributions to the right specialist and validates
> completed deliverables against the contract and available evidence. During
> Clara-created work she carries evidence receipts, stable claims, dependencies,
> calculations, quotations, and output appearances forward from the step where
> they arise. She organizes evidence from documents and data, highlights gaps and contradictions,
> analyzes markets, customers, products, competitors, and operations, and
> prepares presentations, reports, charts, and reviewable workpapers. Sources,
> assumptions, and open questions remain visible; the consultant keeps
> professional judgement.

## Example use cases

1. Plan this advisory assignment, preserve its material facts and constraints,
   and prepare the reviewable contract for the right Clara workflow.
2. Validate this completed advisory deliverable against its contract and the
   available evidence, preserving the original and identifying corrections.
3. Direct this case from its current answer: preserve the cumulative evidence,
   surface the assumption most likely to change the decision, and choose the
   next research, interview, data, or deliverable branch.
4. Profile this dataset, document its business semantics, calculate the requested
   analysis, and render a source-backed business chart.
5. Turn these reviewed materials into a source-faithful standalone HTML
   presentation with an evidence ledger and validation report.

## Cowork boundary

The Claude package is generated from canonical `plugins/clara` source. It omits
voice interviews, transcription, hosted deck capture, plugin feedback, custom
updates, developer privacy tooling, hooks, OpenAI agent descriptors, and
Beautify Deck. It does not claim image-generation capability.

Cowork follows the same `evidence -> claim -> inference -> recommendation ->
decision` review model. Semantic claim selection and support, reasoning,
recommendation, and correction judgement remain model-led. When packaged local
helpers can execute, use the canonical evidence and claim registers, bounded
coverage-unit assessments, authoritative format results, and corrected-artifact
second review. When they cannot execute, state that hash/schema/package closure
is partial; do not claim an equivalent verified package. The validator does not
silently browse, rerun calculations, or treat a generic `passed` JSON file as a
specialist result.

The marketplace source path is:

`plugin_packages/clara/claude/clara`

The local smoke-test archive is:

`plugin_packages/clara/clara-claude-plugin.zip`

## Release candidate

- **Version:** 0.1.140
- **Files:** 856
- **Bytes:** 4,440,276
- **SHA-256:** `03348df76f213aadfac14eca41e5f6b59a7c352c74e79336b2e474ddbaffaecd`
- **ZIP integrity:** clean

The generated directory and exact archive above pass the repository's package
drift, layout, and ZIP-integrity checks. An end-to-end Cowork installation smoke
test remains required before submitting this release candidate to Anthropic.
