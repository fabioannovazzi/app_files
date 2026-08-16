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
> contracts, routes them to the right specialist workflow, and validates
> completed deliverables against the contract and available evidence. She organizes
> evidence from documents and data, highlights gaps and contradictions,
> analyzes markets, customers, products, competitors, and operations, and
> prepares presentations, reports, charts, and reviewable workpapers. Sources,
> assumptions, and open questions remain visible; the consultant keeps
> professional judgement.

## Example use cases

1. Plan this advisory assignment, preserve its material facts and constraints,
   and prepare the reviewable contract for the right Clara workflow.
2. Validate this completed advisory deliverable against its contract and the
   available evidence, preserving the original and identifying corrections.
3. Organize these case files, separate evidence from judgement, surface gaps and
   contradictions, and prepare a reviewable advisory workpaper.
4. Profile this dataset, document its business semantics, calculate the requested
   analysis, and render a source-backed business chart.
5. Turn these reviewed materials into a source-faithful standalone HTML
   presentation with an evidence ledger and validation report.

## Cowork boundary

The Claude package is generated from canonical `plugins/clara` source. It omits
voice interviews, transcription, hosted deck capture, plugin feedback, custom
updates, developer privacy tooling, hooks, OpenAI agent descriptors, and
Beautify Deck. It does not claim image-generation capability.

The marketplace source path is:

`plugin_packages/clara/claude/clara`

The local smoke-test archive is:

`plugin_packages/clara/clara-claude-plugin.zip`

## Release candidate

- **Version:** 0.1.138
- **Files:** 850
- **Bytes:** 4,393,946
- **SHA-256:** `d42fe312896f1f96d49deb0ad946b1fb2a3fbdbaf40d03e118c6ddad8ea4996d`
- **ZIP integrity:** clean

The generated directory and exact archive above pass the repository's package
drift, layout, and ZIP-integrity checks. An end-to-end Cowork installation smoke
test remains required before submitting this release candidate to Anthropic.
