import React, { useMemo, useState } from "react";
import ReactDOM from "react-dom";
import { NOTEBOOKLM_STYLE as NOTEBOOKLM_STYLE_SOURCE } from "../shared/notebooklmStyle";

const apiBase = `${window.location.origin.replace(/\/$/, "")}/review`;

const NOTEBOOKLM_PROMPT_PRESETS_BASE = [
  {
    key: "uniform",
    label: "Uniform",
    description: "Minimal black-on-white slides with strict layout rules that merge cleanly across decks.",
    deckPrompt: `Use a uniform, minimalist, consulting-style slide layout.
Constraints:
– White background only.
– Black text only; no color accents.
– Use Inter (fallback Roboto) for all text.
– Title: 32pt, body bullets: 18pt, line height 1.25.
– Uniform title style and hierarchy across slides.
– Consistent left-aligned text blocks with identical spacing.
– Avoid icons, borders, and decorative shapes.
– Place product images, when present, on the right side at consistent size.
– Limit each slide to max 5 short bullets.
– No agenda slide, no divider slide, no colored banners.
– Maintain continuity of style across all slides.`,
    infographicPrompt: `Create a single-page infographic with a minimalist consulting style.

Layout & style:
- Pure white background (#FFFFFF) only — no texture, gradient, vignette, or paper effect.
- Black text only (#000000); no color accents.
- Use Inter (fallback Roboto) for all text.
- Clear hierarchy: Title 32pt, section headers 22pt, body bullets 18pt, line height 1.25.
- Left-aligned text blocks with consistent spacing.
- No icons, borders, or decorative shapes.

Content structure:
- Title at top.
- 3–5 sections, each with a short heading and up to 3 bullets.
- Use a compact table or list only if it improves clarity.

If images are included:
- Place on the right side at consistent size.
- Keep monochrome or grayscale only.

Output:
- Single static infographic image.`,
  },
  {
    key: "editorial",
    label: "Editorial",
    description: "Serif titles and generous spacing for a report-like narrative style.",
    deckPrompt: `Use a uniform editorial report style across all slides.

Design system (strict):
- Background: off-white only (#FAFAF7).
- Text: near-black only (#111111). No other colors.
- Fonts: titles in "Source Serif 4", body in "Inter" (fallbacks: Georgia, Roboto).
- Type scale: Title 34pt, section header 22pt, body 18pt, line height 1.35.
- Layout: left-aligned text, wide margins, consistent spacing on every slide.
- Density: one idea per slide, max 5 bullets, each bullet ≤ 10 words.

Content rules:
- Prefer short headings + tight bullets over paragraphs.
- Tables/charts must be monochrome grayscale only.

Do not:
- No icons, gradients, shadows, decorative shapes, banners, or divider slides.

Maintain identical typography, spacing, and hierarchy across all slides.`,
    infographicPrompt: `Create a single-page infographic using the Editorial style.

Design system (strict):
- Background: off-white only (#FAFAF7).
- Text: near-black only (#111111). No other colors.
- Fonts: title in "Source Serif 4", all other text in "Inter" (fallbacks: Georgia, Roboto).
- Type scale: Title 34pt, section headers 22pt, body 18pt, line height 1.35.
- Layout: left-aligned blocks with generous margins and consistent spacing.

Structure:
- Title at top.
- 3–5 sections, each with a short heading and up to 3 bullets.
- Use tables/lists only if they improve clarity.
- Charts must be grayscale only.

Do not:
- No icons, gradients, shadows, decorative shapes, or color accents.

Output:
- Single static infographic image.`,
  },
  {
    key: "institutional",
    label: "Institutional",
    description: "Formal, diplomatic slides designed for official bodies and policy briefings.",
    deckPrompt: `Use a uniform institutional briefing style across all slides.

Overall direction (strict):
- Aim for a quiet, senior-level briefing aesthetic: formal, calm, edited, and credible.
- The deck should feel like a board, policy, or research briefing, not a marketing presentation.
- Every slide should look like part of the same document family.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: deep charcoal only (#111827); secondary text #4B5563.
- Accent: one subdued blue only (#1E3A8A), used sparingly.
- Font: "IBM Plex Sans" everywhere (fallback: Inter, Roboto).
- Type scale: Title 32pt, section header 21pt, body 18pt, caption 13pt, line height 1.3.
- Weight strategy: semibold for titles and section headers; regular for body; medium only for small labels where needed.
- Alignment: left-aligned text only.
- Margins: generous and consistent on every slide.
- Spacing: use visible whitespace to create hierarchy; do not crowd the page.

Layout system (strict):
- Use one stable grid across the whole deck.
- Keep titles in the same position on every slide.
- Keep body text, tables, and visuals aligned to the same left edge.
- Prefer one dominant content block per slide: a concise text block, a chart with brief commentary, or a simple table.
- Use at most 2-3 repeatable slide archetypes so the deck feels uniform, not templated.
- Keep the visual center of gravity quiet and balanced; avoid crowded or overly filled slides.

Typography and composition:
- Titles should be short, factual, and written as briefing headlines, not slogans.
- Keep line lengths controlled; avoid wide text blocks stretching across the slide.
- Max 5 concise bullets per slide; each bullet should contain one clear point.
- No sub-bullets, long sentences, or paragraph-style text.
- If a slide is text-only, keep the text in a narrow, well-spaced block rather than spanning the full width.
- Use section divider slides sparingly; they should be minimal and typographic, not decorative.

Visual treatment:
- Tables and charts must be simple, monochrome, or accent-only.
- When a chart or table is present, let it be the visual focus and keep the supporting text secondary.
- Use thin rules or subtle separators only if they improve structure.
- Small page numbers or source notes may appear discreetly if needed.

Do not:
- No icons, gradients, decorative shapes, photos, illustrations, or textured backgrounds.
- No cards, pill labels, dashboard panels, oversized banners, or ornamental dividers.
- No center-aligned layouts, no full-width paragraphs, and no dense multi-column bullet walls.
- No heavy color blocking, no multiple accent colors, and no decorative emphasis.
- No layout shifts between slides.
- No visual gimmicks intended to make the deck feel "creative."

Maintain the same typography, spacing, grid, and hierarchy across all slides. The result should feel polished, restrained, and institutionally credible.`,
    infographicPrompt: `Create a single-page infographic using the Institutional style.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: deep charcoal only (#111827); secondary text #4B5563.
- Accent: one subdued blue only (#1E3A8A), minimal use.
- Font: "IBM Plex Sans" everywhere (fallback: Inter, Roboto).
- Type scale: Title 32pt, section headers 21pt, body 18pt, line height 1.3.
- Layout: left-aligned blocks with generous margins and consistent spacing.

Structure:
- Title at top.
- 3–5 sections, each with a short heading and up to 3 bullets.
- Use compact tables/lists only if they improve clarity.

Do not:
- No icons, gradients, decorative shapes, or photos.

Output:
- Single static infographic image.`,
  },
  {
    key: "dashboard",
    label: "Dashboard",
    description: "A consistent two-column grid that pairs takeaways with evidence on every slide.",
    deckPrompt: `Use a uniform data-dashboard slide style.

Design system (strict):
- Background: white only (#FFFFFF).
- Text colors: primary #0F172A, secondary #475569.
- Accent: one color only (#2563EB), used sparingly.
- Font: Inter everywhere (fallback: Roboto).
- Type scale: Title 30pt, labels 14pt uppercase, body 18pt, line height 1.25.
- Layout grid: consistent 2-column layout on every slide:
  left column = takeaway, right column = evidence (chart/table/image).

Content rules:
- Each slide must include one explicit takeaway sentence at top-left.
- Emphasize 1–2 key numbers visually (bold, larger size).

Do not:
- No icons, illustrations, decorative shapes, or gradients.
- Do not change the grid or alignment between slides.

Keep spacing, alignment, and component placement consistent across all slides.`,
    infographicPrompt: `Create a single-page infographic using the Dashboard style.

Design system (strict):
- Background: white only (#FFFFFF).
- Text colors: primary #0F172A, secondary #475569.
- Accent: one color only (#2563EB), minimal use.
- Font: Inter everywhere (fallback: Roboto).
- Type scale: Title 30pt, section labels 14pt uppercase, body 18pt, line height 1.25.
- Layout: consistent grid with clear blocks for takeaway and evidence.

Structure:
- Title at top-left plus one takeaway sentence beneath it.
- 3–5 sections with short headings and up to 3 bullets each.
- Include compact evidence blocks (mini tables, key numbers, simple charts).

Do not:
- No icons, gradients, decorative shapes, or layout shifts.

Output:
- Single static infographic image.`,
  },
  {
    key: "consulting",
    label: "Consulting",
    description: "A white-background boutique consulting style with editorial typography and restrained evidence framing.",
    deckPrompt: `Use a uniform boutique consulting style across all slides.

Overall direction (strict):
- Aim for a premium strategy-report aesthetic: refined, calm, and highly edited.
- The deck should feel like a top-tier marketing consulting boutique document, not a startup deck or government memo.
- Each slide should look authored, deliberate, and visually disciplined.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: primary #111827, secondary #6B7280.
- Accent: one restrained ink-blue only (#274690), used sparingly.
- Fonts: titles in "Source Serif 4"; body, labels, and captions in "IBM Plex Sans" (fallbacks: Georgia, Inter, Roboto).
- Type scale: Title 32pt, section header 20pt, body 18pt, caption 12pt, line height 1.28.
- Weight strategy: semibold for titles, medium for section labels, regular for body text, medium for captions and source notes only when needed.
- Alignment: left-aligned text only.
- Margins: generous and consistent on every slide.
- Spacing: use whitespace to create hierarchy; keep the page composed, never crowded.

Layout system (strict):
- Use one stable layout language across the whole deck.
- Keep titles in the same position on every slide.
- Keep charts, tables, and supporting commentary aligned to the same text grid.
- Prefer one clear narrative focal point per slide: a headline with evidence, a chart with brief interpretation, or a tightly edited summary block.
- Use at most 2-3 repeatable slide archetypes so the deck feels cohesive rather than varied for its own sake.
- Preserve a calm page silhouette with strong alignment and controlled density.

Typography and composition:
- Titles should read like consulting headlines: specific, concise, and evidence-led.
- Keep title line breaks balanced and avoid long, soft, sentence-like headings.
- Keep text blocks narrow enough to feel editorial rather than document-like.
- Max 4-5 concise bullets per slide; each bullet should express one idea cleanly.
- No sub-bullets, no long prose blocks, and no slide-filling paragraphs.
- Captions, source notes, and small labels should be discreet and typographically consistent.

Visual treatment:
- Tables and charts must be simple, elegant, and easy to scan.
- Use monochrome or accent-only charts; let the evidence carry the slide.
- Use thin dividers or subtle rules only when they improve reading order.
- Small section labels, page numbers, and source notes are acceptable if they remain understated.

Do not:
- No dark backgrounds, gradients, photos, icons, illustrations, or decorative shapes.
- No glossy cards, dashboard widgets, oversized banners, or ornamental callouts.
- No center-aligned text, no full-width body copy, and no dense multi-column bullet walls.
- No loud accent colors, no heavy color fills, and no visual tricks meant to feel premium.
- No layout shifts between slides.

Maintain the same typography, spacing, and alignment system across all slides. The result should feel premium, editorial, and consulting-grade without becoming decorative.`,
    infographicPrompt: `Create a single-page infographic using the Consulting style.

Overall direction (strict):
- Aim for a premium boutique consulting look: refined, calm, and highly edited.
- The page should feel like a top-tier marketing consulting summary, not a poster or dashboard.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: primary #111827, secondary #6B7280.
- Accent: one restrained ink-blue only (#274690), minimal use.
- Fonts: title in "Source Serif 4"; all supporting text in "IBM Plex Sans" (fallbacks: Georgia, Inter, Roboto).
- Type scale: Title 32pt, section headers 20pt, body 18pt, caption 12pt, line height 1.28.
- Layout: left-aligned blocks with generous margins and consistent spacing.

Structure:
- Title at top.
- 3-5 sections, each with a short heading and up to 3 bullets.
- Use compact tables or evidence blocks only where they clarify the point.
- Keep one clear focal area and avoid overfilling the page.

Do not:
- No dark backgrounds, gradients, photos, icons, decorative shapes, or glossy panels.
- No dense layouts or overly wide text blocks.

Output:
- Single static infographic image.`,
  },
  {
    key: "cards",
    label: "Cards",
    description: "A modular card grid that keeps decks easy to combine slide by slide.",
    deckPrompt: `Use a uniform modular card-based layout across all slides.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: #111827 primary, #4B5563 secondary.
- Font: Inter everywhere (fallback: Roboto).
- Type scale: Title 30pt, card header 20pt, body 18pt, line height 1.25.
- Layout: every slide uses 2–4 rectangular cards on a fixed grid.
- Cards: equal padding, equal gaps, consistent card sizes on every slide.
- Card styling: no shadows; optional 1px border only (#E5E7EB).

Content rules:
- Each card has a short heading and up to 3 bullets.
- Keep bullets compact and parallel in structure.

Do not:
- No decorative shapes, icons, gradients, or grid-breaking layouts.

All slides must reuse the exact same card grid and spacing system.`,
    infographicPrompt: `Create a single-page infographic using the Cards style.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: #111827 primary, #4B5563 secondary.
- Font: Inter everywhere (fallback: Roboto).
- Type scale: Title 30pt, card header 20pt, body 18pt, line height 1.25.
- Layout: fixed grid of 3–6 cards with equal padding and equal gaps.
- Card styling: flat cards with no shadows; optional 1px border (#E5E7EB).

Structure:
- Title at top.
- A grid of cards, each with a short heading and up to 3 bullets.

Do not:
- No icons, gradients, decorative shapes, or uneven card sizing.

Output:
- Single static infographic image.`,
  },
  {
    key: "bain",
    label: "Bain",
    description: "A clean strategy-deck style with restrained accents and punchy, outcome-oriented messaging.",
    deckPrompt: `Use a uniform Bain-style consulting layout across all slides.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: primary #111827, secondary #4B5563.
- Accent color: Bain red (#CB2026), reserved for key messages and critical numbers only.
- Keep all non-critical elements neutral (black/charcoal/grey).
- Font: Inter everywhere (fallback: Roboto).
- Type scale: Title 32pt, section header 22pt, body 18pt, line height 1.28.
- Layout: left-aligned, generous whitespace, consistent margins and spacing.

Content rules:
- One clear takeaway per slide, stated in a short headline.
- Max 5 concise bullets per slide; avoid long paragraphs.
- Prioritize decisions, implications, and actions over description.
- Tables/charts must be minimal, clean, and easy to scan.
- Use red only to signal importance (for example one key callout, one risk, or one must-act insight).

Do not:
- No decorative icons, gradients, shadows, or ornamental shapes.
- No layout shifts between slides.

Maintain the same typography, hierarchy, and spacing across all slides.`,
    infographicPrompt: `Create a single-page infographic using the Bain style.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: primary #111827, secondary #4B5563.
- Accent color: Bain red (#CB2026), reserved for key messages and critical numbers only.
- Keep all non-critical elements neutral (black/charcoal/grey).
- Font: Inter everywhere (fallback: Roboto).
- Type scale: Title 32pt, section headers 22pt, body 18pt, line height 1.28.
- Layout: left-aligned blocks, clear spacing, strong visual hierarchy.

Structure:
- Title at top with one concise executive takeaway.
- 3–5 sections with short headings and up to 3 bullets each.
- Use compact evidence blocks (mini table, key figures, simple chart) only where useful.
- Tables/charts must be minimal, clean, and easy to scan.
- Use red only to signal importance (for example one key callout, one risk, or one must-act insight).

Do not:
- No gradients, shadows, decorative icons, or noisy visual effects.

Output:
- Single static infographic image.`,
  },
  {
    key: "band",
    label: "Band",
    description: "Adds a single accent band while keeping the rest of the deck minimal.",
    deckPrompt: `Use a uniform minimalist style with a single accent band.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: black only (#000000).
- Accent: one color only (#0EA5E9).
- Font: Inter everywhere (fallback: Roboto).
- Type scale: Title 32pt, section header 22pt, body 18pt, line height 1.25.
- Signature element: a thin accent band (4–6px tall) at the very top of every slide.
- Layout: left-aligned, consistent margins, identical spacing across slides.

Content rules:
- Max 5 bullets per slide.
- Images, if present, go on the right at consistent size.

Do not:
- No icons, gradients, extra accent elements, or decorative shapes.

Maintain the same band, typography, and spacing on every slide.`,
    infographicPrompt: `Create a single-page infographic using the Band style.

Design system (strict):
- Background: white only (#FFFFFF).
- Text: black only (#000000).
- Accent: one color only (#0EA5E9).
- Font: Inter everywhere (fallback: Roboto).
- Type scale: Title 32pt, section headers 22pt, body 18pt, line height 1.25.
- Signature element: a thin accent band (4–6px tall) at the very top.

Structure:
- Title just below the band.
- 3–5 sections with short headings and up to 3 bullets each.

Do not:
- No icons, gradients, extra accent shapes, or decorative elements.

Output:
- Single static infographic image.`,
  },
  {
    key: "blueprint",
    label: "Blueprint",
    description: "A technical grid-first look that favors precision and simple evidence blocks.",
    deckPrompt: `Use a uniform technical blueprint style across all slides.

Design system (strict):
- Background: very light gray only (#F8FAFC).
- Text: deep navy only (#0F172A).
- Accent: one color only (#0EA5E9), minimal use.
- Font: "IBM Plex Sans" everywhere (fallback: Inter, Roboto).
- Type scale: Title 31pt, section header 21pt, body 18pt, line height 1.28.
- Layout: consistent margins and a simple grid; all elements snap to the grid.

Content rules:
- Use short, precise headings and compact bullets.
- Diagrams and tables should be simple, flat, and monochrome or accent-only.

Do not:
- No photos, icons, gradients, shadows, or decorative shapes.
- No layout shifts between slides.

Keep the grid, alignment, and type scale identical across all slides.`,
    infographicPrompt: `Create a single-page infographic using the Blueprint style.

Design system (strict):
- Background: very light gray only (#F8FAFC).
- Text: deep navy only (#0F172A).
- Accent: one color only (#0EA5E9), minimal use.
- Font: "IBM Plex Sans" everywhere (fallback: Inter, Roboto).
- Type scale: Title 31pt, section headers 21pt, body 18pt, line height 1.28.
- Layout: strict grid with consistent spacing and alignment.

Structure:
- Title at top.
- 3–5 sections with short headings and up to 3 bullets each.
- Use flat tables/lists/mini diagrams only when helpful.

Do not:
- No photos, icons, gradients, shadows, or decorative elements.

Output:
- Single static infographic image.`,
  },
];

const NOTEBOOKLM_SHARED_CHART_PROMPT_BLOCK = `Chart handling:
- Please use attached PNG chart images as chart visuals.

Analytical stance (strict):
- Present findings only.
- Do not give recommendations, implications, action points, or strategic advice.
- Do not include “what this means for brands,” “what marketers should do,” or similar sections.
- Do not speculate beyond the evidence provided.
- If the evidence is modest, state the modest conclusion plainly.
- Prefer descriptive statements over interpretive or prescriptive ones.
- Final slides must remain factual and evidence-led, not advisory.

Slide content rules:
- Focus on what changed, what did not change, and what repeated.
- It is acceptable to state that no strong category-wide shift is visible.
- If including examples, use them only as proof points, not as models to follow.
- Do not end with recommendations; end with a concise factual summary.`;

function withSharedChartPromptBlock(text) {
  const base = (text || "").trim();
  if (!base) return NOTEBOOKLM_SHARED_CHART_PROMPT_BLOCK;
  return `${base}\n\n${NOTEBOOKLM_SHARED_CHART_PROMPT_BLOCK}`;
}

const NOTEBOOKLM_PROMPT_PRESETS = NOTEBOOKLM_PROMPT_PRESETS_BASE.map((preset) => ({
  ...preset,
  deckPrompt: withSharedChartPromptBlock(preset.deckPrompt),
  infographicPrompt: withSharedChartPromptBlock(preset.infographicPrompt),
}));

const NOTEBOOKLM_STYLE = NOTEBOOKLM_STYLE_SOURCE;
const NOTEBOOKLM_STYLE_EXAMPLE_ROOT = "/notebooklm-styles";

function copyToClipboard(text) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text);
  } else {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
  }
}

function App() {
  const [promptPresetKey, setPromptPresetKey] = useState(NOTEBOOKLM_PROMPT_PRESETS[0].key);

  const promptPreset = useMemo(
    () => NOTEBOOKLM_PROMPT_PRESETS.find((preset) => preset.key === promptPresetKey) || NOTEBOOKLM_PROMPT_PRESETS[0],
    [promptPresetKey],
  );
  const promptStyleExampleUrl = useMemo(
    () => `${NOTEBOOKLM_STYLE_EXAMPLE_ROOT}/${encodeURIComponent(promptPreset.label)}.pdf`,
    [promptPreset.label],
  );
  const hasExampleDeck = promptPreset.hasExampleDeck !== false;
  return (
    <div>
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, background: "#fff", marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Settings</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "stretch" }}>
            <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, background: "#f9fafb", minWidth: 320, flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Deck template</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {NOTEBOOKLM_PROMPT_PRESETS.map((preset) => {
                  const active = preset.key === promptPreset.key;
                  return (
                    <button
                      key={preset.key}
                      type="button"
                      onClick={() => setPromptPresetKey(preset.key)}
                      aria-pressed={active}
                      style={{
                        border: "1px solid #e5e7eb",
                        borderRadius: 999,
                        padding: "6px 10px",
                        background: active ? "#111827" : "#fff",
                        color: active ? "#fff" : "#111827",
                        fontFamily: "var(--mparanza-pill-font-family)",
                        fontSize: "var(--mparanza-pill-font-size, 14px)",
                        fontWeight: "var(--mparanza-pill-font-weight, 400)",
                        lineHeight: "var(--mparanza-pill-line-height, 1.2)",
                        cursor: "pointer",
                      }}
                    >
                      {preset.label}
                    </button>
                  );
                })}
              </div>
              <div style={{ fontSize: 12, color: "#4b5563", marginTop: 8 }}>{promptPreset.description}</div>
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 6 }}>Example deck</div>
                {hasExampleDeck ? (
                  <>
                    <div style={{ fontSize: 12, marginBottom: 8 }}>
                      <a href={promptStyleExampleUrl} target="_blank" rel="noreferrer">
                        Open {promptPreset.label} PDF
                      </a>
                    </div>
                    <iframe
                      title={`${promptPreset.label} example deck`}
                      src={promptStyleExampleUrl}
                      style={{ width: "100%", height: 220, borderRadius: 10, border: "1px solid #e5e7eb" }}
                      loading="lazy"
                    />
                  </>
                ) : (
                  <div style={{ fontSize: 12, color: "#6b7280" }}>
                    Example deck preview is not available yet for this style.
                  </div>
                )}
              </div>
            </div>

            <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, background: "#f9fafb", minWidth: 320, flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginBottom: 8 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#111827" }}>NotebookLM deck prompt</div>
                <button
                  type="button"
                  onClick={() => copyToClipboard(promptPreset.deckPrompt)}
                  style={{
                    border: "1px solid #e5e7eb",
                    borderRadius: 10,
                    padding: "6px 10px",
                    background: "#fff",
                    cursor: "pointer",
                  }}
                >
                  Copy
                </button>
              </div>
              <textarea
                value={promptPreset.deckPrompt}
                readOnly
                rows={14}
                style={{ width: "100%", borderRadius: 10, border: "1px solid #e5e7eb", padding: 10, fontSize: 12 }}
              />
            </div>

            <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, background: "#f9fafb", minWidth: 320, flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginBottom: 8 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#111827" }}>NotebookLM infographic prompt</div>
                <button
                  type="button"
                  onClick={() => copyToClipboard(promptPreset.infographicPrompt)}
                  style={{
                    border: "1px solid #e5e7eb",
                    borderRadius: 10,
                    padding: "6px 10px",
                    background: "#fff",
                    cursor: "pointer",
                  }}
                >
                  Copy
                </button>
              </div>
              <textarea
                value={promptPreset.infographicPrompt}
                readOnly
                rows={18}
                style={{ width: "100%", borderRadius: 10, border: "1px solid #e5e7eb", padding: 10, fontSize: 12 }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

ReactDOM.render(<App />, document.getElementById("reactBriefApp"));
