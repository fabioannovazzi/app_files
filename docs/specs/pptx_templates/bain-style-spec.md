# Bain Style Spec

## Purpose

Canonical Bain-style definition for:

- brief and deck prompting
- future PPTX template design
- style review when prompt text and rendered output drift

This spec replaces ad hoc prompt variations.

## Visual System

- Background: white only (`#FFFFFF`)
- Primary text: `#111827`
- Secondary text: `#4B5563`
- Accent color: Bain red (`#CB2026`)
- Accent usage: reserved for key messages and critical numbers only
- Non-critical elements: neutral only (`black`, `charcoal`, `grey`)
- Font family: `Inter` everywhere, fallback `Roboto`
- Title size: `32pt`
- Section header size: `22pt`
- Body size: `18pt`
- Line height: `1.28`
- Alignment: left-aligned
- Spacing: generous whitespace, consistent margins, consistent inter-block spacing

## Content Rules

- One clear takeaway per slide, stated in a short headline
- Max 5 concise bullets per slide
- Prefer decisions, implications, and actions over description
- Tables and charts must be minimal, clean, and easy to scan
- Use Bain red only to signal importance, such as one key callout, one risk, or one must-act insight

## Do Not

- No decorative icons
- No gradients
- No shadows
- No ornamental shapes
- No layout shifts between slides

## Notes for Direct PPTX Generation

- This spec is style-only. It does not include old NotebookLM-era chart handling instructions.
- Chart placement, chart asset references, and slide order belong in the brief JSON, not in the style definition.
- A future Bain PPTX template should be visually aligned with this spec, not necessarily pixel-identical to historical NotebookLM outputs.
