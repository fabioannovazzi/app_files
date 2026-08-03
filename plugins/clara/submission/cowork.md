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
- **Contact:** hello@mparanza.com

**Public description**

> AI companion for consultants. Clara helps consultants prepare commercial due
> diligence and other advisory work. She organizes evidence from documents and
> data, highlights gaps and contradictions, analyzes markets, customers,
> products, competitors, and operations, and prepares presentations, reports,
> charts, and reviewable workpapers. Sources, assumptions, and open questions
> remain visible; the consultant keeps professional judgement.

## Example use cases

1. Organize these case files, separate evidence from judgement, surface gaps and
   contradictions, and prepare a reviewable advisory workpaper.
2. Profile this dataset, document its business semantics, calculate the requested
   analysis, and render a source-backed business chart.
3. Turn these reviewed materials into a source-faithful standalone HTML
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

- **Version:** 0.1.123
- **Files:** 821
- **Bytes:** 4,255,288
- **SHA-256:** `6ae738e4265c311320a18ae6af59f8e9340dc9f81fa654f49703dc4592ba6740`
- **ZIP integrity:** clean

The generated directory and exact archive above pass the repository's package
drift, layout, and ZIP-integrity checks. An end-to-end Cowork installation smoke
test remains required before submitting this release candidate to Anthropic.
