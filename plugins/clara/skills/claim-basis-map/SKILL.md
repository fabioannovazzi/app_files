---
name: claim-basis-map
description: "Use when Clara or Codex generates, revises, or audits a clean PPTX/deck and needs a fully automatic readable sidecar that maps each slide claim to its basis and checks whether current deck text has drifted from the generation-time claim snapshot. Use for AI-generated decks where visible citations, claim IDs, reviewer attestations, hashes, thumbnails, and HTML are explicitly not wanted."
---

# Claim Basis Map

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

Create a clean companion file for a deck:

```text
deck.pptx
deck.claims.json
deck.claims.md
```

The PPTX stays visually clean. Do not add visible claim IDs, footnotes,
speaker-note dumps, thumbnails, HTML, reviewers, certifications, or file hashes.
Internal `claim_key` values are allowed in JSON when they make cross-slide
references more robust, but never show them in the PPTX.

## Core Rule

Track claim basis during deck generation whenever possible. Do not reconstruct
the "source of origin" after the deck is complete unless the user explicitly
accepts that the result is only matched support.

For each slide, emit `deck.claims.json` as the generation-time record. Treat the
exact normalized claim text in that JSON as the snapshot for later edit checks.
Then render `deck.claims.md` deterministically from that record with:

```bash
python plugins/clara/skills/claim-basis-map/scripts/render_claim_basis_map.py \
  deck.claims.json \
  --output deck.claims.md
```

This is not tamper-proofing and does not certify the PPTX. It is a text-drift
check: if the deck changes later, rerun the renderer against the current PPTX.
Changed, missing, untracked, or broken-reference claims fail closed and are
surfaced as requiring refresh.

## JSON Contract

Use this minimal shape:

```json
{
  "deck": "deck.pptx",
  "slides": [
    {
      "slide_number": 4,
      "slide_title": "Market direction",
      "claims": [
        {
          "claim": "The market grew 12% in 2025.",
          "source_refs": [
            {
              "title": "Example Market Research Category Report 2025",
              "locator": "p. 14, table 2",
              "url": "https://example.com/report"
            }
          ]
        },
        {
          "claim": "Premium SKUs contributed 62% of growth.",
          "calculation_ref": {
            "inputs": ["sell-out extract rows 114-189"],
            "method": "premium growth / total category growth"
          }
        },
        {
          "claim": "Premiumization is likely to remain the main growth vector.",
          "claim_key": "claim-4",
          "reasoning_inputs": [
            {
              "label": "Example Market Research category growth table",
              "locator": "p. 14"
            },
            {
              "label": "Company sell-out extract",
              "locator": "rows 114-189"
            }
          ],
          "reasoning": "Premium formats show stronger growth and higher launch density."
        },
        {
          "claim": "Retailers will increasingly favor discovery-led merchandising."
        }
      ]
    },
    {
      "slide_number": 6,
      "slide_title": "Retail implications",
      "claims": [
        {
          "claim": "Retailers will prioritize premium discovery space.",
          "claim_refs": [
            {
              "slide_number": 4,
              "claim": "Premiumization is likely to remain the main growth vector."
            }
          ],
          "reasoning": "Retailers typically allocate discovery space toward the growth vector they need to defend."
        }
      ]
    }
  ]
}
```

When the deck generator can control PPTX shape metadata, set the invisible
PowerPoint shape name for the textbox that carries a claim to:

```text
clara-claim:<claim_key>
```

This is not visible on the slide and is not a hash. It simply lets the check
mode distinguish "same claim edited in place" from "old claim deleted or moved"
more accurately. If hidden shape names are unavailable, the check mode falls
back to exact normalized text matching across slides.

## Deterministic Classification

Classify each claim from fields only:

```text
if source_refs is non-empty -> source-backed
elif calculation_ref is non-empty -> calculated
elif claim_refs is non-empty -> claim-linked
elif reasoning_inputs is non-empty -> reasoned
elif assumption_basis is non-empty -> assumption
else -> ungrounded
```

This deterministic rule is justified because it validates and renders explicit
generation metadata. It does not decide whether a source semantically supports a
claim, which remains model-led during generation.

Fail closed: when a claim lacks a captured basis, surface it as ungrounded.
Reasoned claims are grounded only when `reasoning_inputs` are present.

`claim_refs` may point to a prior slide claim by exact `slide_number` + `claim`
text, or by an internal `claim_key`. Prefer prior-slide references so the claim
graph is acyclic and deterministic. If a claim points to a missing, future, or
ungrounded prior claim, surface that dependency in the top `Ungrounded Claims`
section. Do not invent an upstream source to make the dependency look grounded.

## Current Deck Check

To check a PPTX after normal editing, compare the current deck text layer with
the generation-time JSON:

```bash
python plugins/clara/skills/claim-basis-map/scripts/render_claim_basis_map.py \
  deck.claims.json \
  --current-pptx deck.pptx \
  --output deck.claims.md
```

Use `--snapshot-output current-deck.snapshot.json` when a local debug snapshot
is useful. Use `--current-claims-json` only when another deck builder has
already extracted the current visible claims/text.

Check statuses:

- `unchanged`: exact claim text is still on the same slide.
- `moved`: exact claim text appears on a different slide.
- `edited`: a hidden `clara-claim:<claim_key>` shape still exists but its text
  no longer contains the original claim.
- `missing-or-edited`: the original claim text is not found and no hidden key
  identifies an edited shape.
- `untracked-current-text`: current deck text looks like a claim but was not in
  the generation-time snapshot.
- `reference-broken`: a claim depends on another claim whose current deck text
  drifted.

Do not use deterministic code to decide whether a new or edited claim is
semantically supported. Re-run the model-led generation/matching step for those
claims, then emit an updated `deck.claims.json`.

## Markdown Output

The readable file must start with `Ungrounded Claims` and then list slides:

```md
# Claim Basis Map

Deck: deck.pptx

## Ungrounded Claims

- Slide 4: "Retailers will increasingly favor discovery-led merchandising."
  Basis: no captured source, calculation, reasoning input, or assumption

## Slide 4 - Market direction

### Source-backed
- "The market grew 12% in 2025."
  Source: Example Market Research Category Report 2025, p. 14, table 2, https://example.com/report

### Calculated
- "Premium SKUs contributed 62% of growth."
  Inputs: sell-out extract rows 114-189
  Method: premium growth / total category growth

### Reasoned
- "Premiumization is likely to remain the main growth vector."
  Inputs: Example Market Research category growth table, p. 14; Company sell-out extract, rows 114-189
  Reasoning: Premium formats show stronger growth and higher launch density.

### Ungrounded
- "Retailers will increasingly favor discovery-led merchandising."
  Basis: no captured source, calculation, reasoning input, or assumption

## Slide 6 - Retail implications

### Claim-Linked
- "Retailers will prioritize premium discovery space."
  Based on claim: Slide 4 - "Premiumization is likely to remain the main growth vector."
  Reasoning: Retailers typically allocate discovery space toward the growth vector they need to defend.
```

## Existing Decks

For an existing PPTX with no generation record, be explicit that the sidecar is
not the original source map. Produce a `deck.claims.json` where each basis is
only captured if the support was actually found or inferred during the current
run. Leave unsupported items ungrounded rather than inventing a source.

When an existing deck later gets a real generation-time snapshot, prefer that
snapshot over any reconstructed map. The reconstructed map is matched support;
the generated map is the authority for drift checks.

## Codex-Native Run UX

Use a short checklist for the run: identify the deck, locate or create
`deck.claims.json`, decide whether this is generation-time capture or current
PPTX check mode, run deterministic rendering, and report `deck.claims.md`.

Before running the script, show a compact Run Intake table with the PPTX path,
claims JSON path, output Markdown path, whether this is generation-time capture
or existing-deck matching, whether current-deck check mode is enabled, and
whether cross-slide `claim_refs` are present.

Use a Decision Table only for unresolved material choices, such as whether the
user wants matched support for an existing deck. Default output policy: create
`deck.claims.json` and `deck.claims.md`; these are not choices to propose when
the user asked for the normal claim-basis sidecar.

Before write-heavy or externally visible work, use an execution checkpoint that
names the command, input file, output file, and expected artifacts. Never edit
generated ZIPs by hand; plugin release artifacts are rebuilt from source.

End with an Artifact Card listing generated paths, ungrounded claim count,
unresolved claim-reference count, current-deck drift issue count when checked,
and any failed validation. Create
`codex_run_review.md` only when the run needs a local note about blocked
inputs, schema gaps, or repeated manual cleanup.

## Boundaries

- Do not put source labels on the slide unless the user asks.
- Do not use speaker notes as the primary source map.
- Do not create HTML or thumbnails unless the user asks later.
- Do not add a reviewer, certification, signature, or hash.
- Do not let deterministic code make semantic support decisions.
