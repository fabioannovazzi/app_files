> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Visual system

Produce an editorial explainer, not an AI illustration. The default social
format is a 1080 × 1350 pixel portrait carousel. Use a white or warm-white
canvas, strong live typography, generous negative space, thin rules, restrained
neutral text, and one primary/accent color pair from the approved studio brand
profile. Default to Vera navy `#002060` and cyan `#00B0F0` only when no studio
profile was supplied.

Use Instrument Sans from the bundled OFL assets. Build hierarchy through scale,
weight, alignment, and spacing. Do not use gradients, glossy cards, shadows,
generic AI symbols, fake screenshots, decorative dashboards, or embedded
photorealistic imagery.

Compose the story as an editorial sequence, not as one repeated text template.
Select `layout_variant` slide by slide from the contribution schema so a
comparison looks like a comparison, a two-condition test looks like a sequence,
an exclusion list looks like a register, and a material threshold can carry
deliberate emphasis. Layout selection remains a model judgment: do not infer it
from keywords or numbers in the copy. The renderer only executes and
mechanically validates the selected structure.

Do not create a carousel merely because a visual was requested. It must add
useful detail, structure, comparison, sequence, or a bounded decision aid beyond
the post. A slide-by-slide paraphrase is a loss of the reader's time and must be
omitted or redesigned. Large numbers are not decoration; emphasize one only
when it materially helps the reader understand or decide something.

Each slide has one job:

- `cover`: the change and why the audience should care;
- `change`: the material difference, not a paraphrased headline;
- `audience`: who may be affected and the applicability caveat;
- `timeline`: dates and sequence;
- `action`: a short practical checklist;
- `caveat`: exceptions, uncertainty, or professional review boundary;
- `close`: restrained next step and studio identity.

Place a concise human-readable source note in the footer of substantive slides,
for example `MCC — Circolare n. 3/2026 del 10 luglio 2026`. Internal source IDs
belong only in the technical basis and manifest. Never expose them to the
reader. Studio identity placement comes from the accepted social profile. When
no approved convention exists, show the Studio name only on the closing slide;
never repeat the same name in header and footer. Generate a self-contained HTML gallery
beside the PNGs for visual inspection. Inspect every slide before delivery for
clipping, awkward wrapping, illegible footers, empty space caused by failed
layout, and divergence from the accepted story. Also reject a slide whose title,
highlight, body, and bullets merely repeat one proposition, a checklist that
implies sufficiency beyond its evidence, or a carousel whose information is not
incremental to the post. Long unbroken tokens must wrap
within the safe width; if all accepted copy cannot fit inside the declared safe
geometry at the minimum type size, rendering fails instead of clipping or
silently dropping content. A PDF or carousel is not package-ready until the
professional accepts the exact rendered manifest.

Use `--qa-preview` when an exact render is needed to conduct the review. The
preview has its own directory and manifest and cannot satisfy packaging or
delivery gates. Only a post-review `accepted_semantics` render can become a
release candidate.

When the professional explicitly selected Creative Production, use it before
final rendering to compare four to six genuinely different art directions.
Its board is a design workbench, not the rendering engine: references may
explore composition, hierarchy, rhythm, rules, shapes, brand-constrained color
balance, and non-factual texture, while leaving safe areas for exact live type.
Do not publish a board image or trust rasterized text, numbers, sources, or
logos from it. Vera must translate the chosen direction into supported layout
and profile choices, render all exact content deterministically, and run the
same model-led and professional visual checks. If the board cannot be used,
continue with the internal visual system without lowering the review standard.
Record the exact board result and human selection before rendering. Translate
the chosen direction only into the supported `frame_style`, `accent_geometry`,
`rule_style`, `row_marker`, `spacing_rhythm`, and `header_treatment` tokens.
The manifest must bind the handoff, decision, translation, board and selected
item digests. If the route cannot complete, record an explicit fallback; never
claim Creative Production influenced a render whose bytes ignore the selection.
Every supported token must control its named visual property: `row_marker`
changes row markers and `spacing_rhythm` changes spatial rhythm, not an
unrelated stroke width. Record the exact applied-token set in the manifest and
list any selected token with no visible target as not applicable; never claim
that a token influenced bytes when it could not do so.

For a circular PDF, measure header, footer, contact rail, and long unbroken
tokens before release. Preserve the exact reviewed source notes, closing, and
signature. Verify extractable text and page coverage from the completed PDF;
fail instead of slicing, clipping, or silently dropping copy.

The manifest must say whether the format is an unreviewed run proposal, an
accepted run profile, or a stored approved profile, and whether an official logo
asset is present. Never describe a history-derived typographic proposal as the
Studio's official format before acceptance. A model-led visual assessment bound
to the exact manifest is required in addition to mechanical checks and the
professional's final rendered-output decision.
