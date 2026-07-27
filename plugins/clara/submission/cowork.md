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

`plugin_packages/clara/clara-cowork-plugin.zip`

## Release candidate

- **Version:** 0.1.119
- **Files:** 829
- **Bytes:** 4,320,490
- **SHA-256:** `d1d47ed3dffeec0e0847b3ce59840d97ddce89ca38f5a6fe65e368cd7d9aa5bc`
- **ZIP integrity:** clean

The exact archive above was installed as a local plugin in Claude Cowork. Cowork
recognized Clara and all six reviewed skills, invoked Clara from a natural
language task, read a synthetic evidence file from the connected folder, and
created `clara-workpaper.md` in that folder. The workpaper preserved source
references, separated supported facts from unsupported management claims,
surfaced tensions and diligence questions, stated a bounded advisory position,
and marked the output as a draft for professional review. No web search,
connector, browser control, image generation, or external service was used.
