---
name: beautify-deck
description: "Use when Clara or Codex needs to turn a final editable PPTX or PDF deck into a beautified non-editable image PDF using the OpenAI Image2/gpt-image-2 image route, while preserving slide content exactly through repeated slide-by-slide fidelity checks, regeneration of failed pages, and final PDF verification."
---

# Beautify Deck

Use this only after the editable deck is structurally final enough to justify a
non-editable image treatment. The output is a polished raster-image PDF for
review or client use. It is not a replacement for the editable PPTX.

## Non-Negotiables

- Preserve the editable PPTX as the source of truth.
- Use the current OpenAI Image2/gpt-image-2 image generation or edit route when
  model selection is exposed. If only another image model is available, stop and
  say the required model is unavailable unless the user explicitly approves a
  fallback.
- Keep all user project outputs inside the user's project folder, normally
  `outputs/presentations`, and put scratch under the project folder, normally
  `work/codex_scratch/<run-slug>`. Do not use Downloads, the repo, app files, or
  system temp folders for case artifacts unless the user explicitly asks.
- Deliver the editable PPTX and the beautified image PDF. Do not send or present
  the intermediate image-only PPTX unless the user specifically asks for it.
- Treat content fidelity as the gating criterion: the beautified slide may
  change layout and visual style, but it must not change text, names, numbers,
  sequence, meaning, labels, titles, bullets, tables, charts, or advisory logic.

## Default Image2 Prompt

Use this prompt as the baseline for each page unless the user gives a better
style direction. Pass the source slide image as the authoritative reference.

```text
Use case: productivity-visual
Asset type: one page of a raster-image PDF consulting deck, 16:9 landscape
Primary request: Recompose the provided slide into a much more distinctive boutique strategy consulting page, while preserving all factual content exactly.
Input image: The source slide is the authoritative reference for all text, names, claims, sequence, tables, headings, and emphasis.
Creative direction: Make it feel like a top-tier independent advisory firm deck: editorial, confident, high-value, expensive, calm, and sharp. Use a stronger asymmetric composition, dramatic whitespace, oversized but elegant type, refined vertical rules, premium table/card treatments, subtle paper texture, precise hairlines, and selective deep green plus muted gold accents.
Composition/framing: Do not merely clean up the existing slide. Re-layout it with a more memorable visual system while retaining the same content hierarchy and legibility. Keep a 16:9 landscape page with disciplined margins and no clutter.
Text constraints: Preserve every word, name, number, accent, apostrophe, heading, bullet, and table meaning from the input slide. Do not translate, paraphrase, shorten, invent, omit, reorder in a misleading way, or correct the content. Keep Italian accents and names intact. All text must remain legible and spelled correctly.
Truth constraints: Do not add new evidence, claims, recommendations, numbers, dates, people, logos, photos, icons, diagrams, watermarks, or fake source labels. Do not change the advisory logic.
Visual constraints: White or warm-white background only. Cooler means stronger composition, richer typography, sharper hierarchy, refined consulting craft, not decorative gimmicks. Avoid dark backgrounds, gradients, blobs, stock imagery, 3D effects, fake branding, excessive shadows, and clutter.
Negative: no hallucinated words, no gibberish text, no lorem ipsum, no misspelled Italian, no altered company/person names.
```

For agenda, index, appendix, legal, or footnote-heavy slides, add:

```text
This is a fidelity-critical slide. Keep all labels, numbers, section titles, footers, page numbers, and agenda sequencing exactly as shown. Prefer a simpler composition over any text risk.
```

## Workflow

1. Establish paths and source truth.
   - Identify the editable PPTX and final PDF output path before generating.
   - Render the editable deck to source PNGs, one page per slide.
   - Extract source text from the PPTX where possible and keep a per-slide text
     ledger. For image-heavy slides, use visual inspection or OCR as an extra
     ledger, not as authority over the PPTX.
   - Save `beautify_prompt.txt`, `slide_fidelity_ledger.json`, and
     `slide_fidelity_review.md` in the project scratch folder.

2. Generate each beautified slide.
   - Send one source slide image at a time to Image2/gpt-image-2 with the
     default prompt plus any slide-specific fidelity warning.
   - Generate to a deterministic page filename such as `page-09.png`.
   - If a page contains dense text, tables, page markers, repeated labels, or
     diagrams, generate a second candidate and choose the one with stronger
     fidelity, not the one that is merely prettier.

3. Run Fidelity Loop A before assembling the PDF.
   - Check every slide against the source slide, slide by slide.
   - Compare visible text, titles, labels, bullets, numbers, names, table
     entries, agenda order, page numbers, and footer/legal text.
   - Check graphic semantics: arrows, steps, Venn sets, puzzle pieces, check
     marks, hierarchy, axis labels, and callout-to-shape relationships.
   - Record each slide as `pass`, `regenerate`, or `manual_patch`.
   - Regenerate failed slides with a stricter prompt naming the specific failure.
     Do not accept a slide with misspelled Italian, duplicated labels, missing
     labels, changed numbers, wrong sequence, or misleading geometry.

4. Assemble the non-editable deck and export PDF.
   - Use one full-bleed image per slide in a temporary image-only PPTX when that
     is the most reliable route to PDF export.
   - Export the image-only PPTX to PDF.
   - Keep the image-only PPTX as scratch/intermediate unless the user requests
     it as a deliverable.

5. Run Fidelity Loop B on the final PDF.
   - Render the final PDF back to PNGs.
   - Re-check every page against the editable source and against the accepted
     beautified page image.
   - Run this pass twice for high-stakes decks: first for text/content, second
     for layout defects such as clipping, off-center labels, repeated labels,
     warped boxes, wrong callout alignment, unreadable footers, or broken page
     numbers.
   - Any final-PDF failure reopens the loop: patch or regenerate the affected
     page, rebuild the image-only deck, re-export the PDF, and re-run Loop B on
     at least the affected page plus its neighboring pages.

## Regeneration Prompts

When a slide fails, do not reuse the same generic prompt. Add a terse correction:

```text
Regenerate this slide. Prior output failed because: <specific defects>.
Preserve these exact strings and labels: <critical strings>.
Do not duplicate, omit, translate, wrap incorrectly, or alter those strings.
Prefer a simpler layout if needed to keep fidelity.
```

For repeated failures, reduce creative freedom:

```text
Use a conservative premium consulting layout. Keep the same content blocks and
relative reading order as the source. Improve typography, spacing, margins, and
color only. Do not invent a new diagram.
```

## Final QA Standard

The deck is not deliverable until:

- every slide has passed two fidelity loops;
- every regenerated slide has been rechecked after assembly into the final PDF;
- the final PDF page count equals the editable PPTX slide count;
- no slide contains duplicated standalone labels, uncentered labels, broken
  words, unexplained English/Italian drift, hallucinated text, gibberish, or
  changed numbers;
- the final email or handoff clearly distinguishes the editable PPTX from the
  beautified non-editable PDF.

If the user asks to send the files, attach only the current editable PPTX and
the final beautified PDF unless they explicitly request additional artifacts.

## Codex-Native Run UX

Use a short checklist for the run: source deck, output paths, Image2 prompt,
first generation pass, Fidelity Loop A, PDF assembly, Fidelity Loop B, and
delivery.

Before generating, show a compact Run Intake table with the editable PPTX path,
source render path, scratch folder, final PDF path, model route, prompt file,
and whether the user asked for email delivery.

Use a Decision Table only for unresolved material choices, such as a missing
project folder, an unavailable Image2/gpt-image-2 route, or a user request to
send an intermediate image-only PPTX. Default output policy: produce the
current editable PPTX plus the beautified non-editable PDF; these are not
choices to propose when the user asked for the normal beautify-deck run.

Before long or write-heavy work, show an execution checkpoint naming the source
deck, output folder, expected image pages, final PDF, and QA ledger. Do not edit
generated ZIPs by hand; plugin release artifacts are rebuilt from source.

End with an Artifact Card listing the editable PPTX, beautified PDF, prompt
ledger, slide_fidelity_review.md, failed/regenerated page count, final page
count, and any accepted residual issue. Create `codex_run_review.md` only when
the run is blocked, a model fallback was accepted, or repeated slide failures
require a local note for the next run.
