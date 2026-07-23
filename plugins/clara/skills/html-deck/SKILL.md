---
name: html-deck
description: Build or revise source-faithful, cinematic, animated standalone HTML slide decks for Clara or Codex from Word, PDF, Markdown, spreadsheet, case-workspace, or mixed source materials. Use for a premium HTML presentation, web deck, animated talk, responsive keynote-style deck, speaker notes, preservation-aware HTML deck changes, or an alternative to PPTX/PDF that must remain self-contained and browser-presentable.
---

# HTML Deck

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

Create a decision-ready HTML presentation with bespoke editorial craft and a
repeatable authoring, provenance, revision, and browser-QA system. Keep source
material authoritative. Use motion to clarify meaning, not decorate it.

## Non-negotiables

- Preserve names, numbers, periods, dates, qualifications, examples, and
  advisory logic. Never make a deck prettier by making it less true.
- For a Clara case, build only after the Advisory Intelligence Loop and from
  `advisory_workpaper.md`, `presentation_storyline.md`, relevant sources, and
  advisor judgement actually supplied. Keep material evidence gaps visible.
- Keep user data and outputs outside plugin source. Put the work folder and
  deliverables beside the user's project outputs or in the requested folder.
- Produce a dependency-free `index.html`: no CDN, web font, remote script,
  analytics, tracking, or required network request.
- Publish below a lowercase 64-character hexadecimal directory by default and
  include `noindex,nofollow,noarchive` unless discovery is requested.
- Use Clara's shared fixed 16:9 runtime. Letterbox rather than stretch. Every
  slide needs a stable ID, audience-facing title, and speaker notes.
- Keep operator chrome outside slide content. Persistent visual page numbers
  and decorative counters are prohibited; the auto-hiding HUD may show state.
- Preserve keyboard, touch, reduced-motion, accessibility, and print behavior.
- Treat a difficult URL as convenient obscurity, not access control.

## Decision boundary

The model owns semantic work: source interpretation, storyline, claims,
qualifications, layout choice, visual type, analytical filters and periods,
speaker notes, and editorial judgement.

Deterministic helpers own mechanically verifiable work: schema and ID checks,
safe text handling, density/fragment limits, numerical rendering from supplied records,
provenance links, content addressing, preservation fingerprints, browser
geometry/interactions, packaging, and report generation. A helper must never
invent a claim, choose a period, or decide which visual tells the story.

## Workflow

### 1. Check the runtime and establish source truth

From the Clara plugin root, run the dependency check before any helper:

```bash
python scripts/check_dependencies.py
```

Read source material with the appropriate document, spreadsheet, PDF, or
browser capability. For each intended slide, define:

- stable slide ID, audience-facing title, and purpose in the spoken argument;
- exact claims, values, periods, labels, units, and qualifications;
- whether each claim is fact, assumption, target, forecast, probability,
  illustrative output, judgement, or open question;
- source-backed or speaker-judgement basis;
- visual mechanism, notes intent, and evidence IDs.

Write the storyline as an argument, not a table of contents. Open with the real
tension, move through evidence and choices, and end with a decision, action, or
question. Delete pages that repeat or exist only because a layout is available.

### 2. Initialize editable work

```bash
python skills/html-deck/scripts/init_html_deck.py \
  --work-dir <project-output-folder>/html-deck-work \
  --title "<deck title>" \
  --subtitle "<one-line promise>" \
  --author "<speaker or firm>" \
  --eyebrow "<talk or engagement label>" \
  --language it
```

The initializer creates:

- `deck.json` — publication metadata;
- `deck-plan.json` — structured narrative/layout plan;
- `content-ledger.json` — slide, claim, and source provenance;
- `slides.html` — editable composed slide markup;
- `custom.css` — deck-specific styling.

The initial content is a guide, not a finished deck. Replace all `REPLACE THIS`
content and reconcile the plan and ledger before building.

### 3. Author through the layout registry

Read [references/quality-bar.md](references/quality-bar.md) and
[references/structured-authoring.md](references/structured-authoring.md).
For any production number, date, percentage, count, currency amount, table
cell, or chart mark, also read
[references/evidence-bindings.md](references/evidence-bindings.md) and use the
source-bound v2 plan/ledger contract. Do not copy business values into a v1
plan.
Inspect `assets/layout-library/registry.json`; choose layouts from their
narrative roles, not by keyword matching.

When layout selection is uncertain, generate the complete preview gallery:

```bash
python skills/html-deck/scripts/build_layout_gallery.py \
  --output-dir <project-output-folder>/layout-gallery
```

It renders all 15 layouts at 1280×720, 1024×768, and 390×844 and writes
`layout-previews.json` with screenshot paths. It is a mechanical preview, not a
layout recommendation.

Edit `deck-plan.json` and `content-ledger.json`, then compose:

```bash
python skills/html-deck/scripts/compose_html_deck.py \
  <project-output-folder>/html-deck-work/deck-plan.json \
  --output-dir <project-output-folder>/html-deck-work \
  --force
```

The composer emits stable QA roles, provenance attributes, fragments,
`slides.html`, and the shared layout CSS. Its bundled `data_visual` renderer
supports bar, line, scatter, bubble, waterfall, timeline, and table components.
Supply already-selected and correctly filtered data. The renderer deliberately
does not filter time, combine years, or make analytical choices.

For a v2 plan, first seal `evidence-bundle.json` with
`scripts/evidence_bindings.py seal`. Composition also writes
`resolved-deck-plan.json`, `resolved-content-ledger.json`, and
`evidence-ledger.json`. The same central binding can feed prose, claims, metric
cards, tables, and prepared visual data without numeric transcription.

Prefer registered layouts. Set `allow_bespoke_html: true` only when the required
mechanism genuinely cannot fit the library. Bespoke markup remains body-only
and is still subject to escaping, executable-attribute, and resource checks.

After composition, use `custom.css` only for deck-specific semantic needs. Do
not fork the shared engine for one deck. Keep one visual idea per slide, direct
label data, reserve warning color for actual risk, and keep delivery detail in
speaker notes.

### 4. Build and run static validation

```bash
python skills/html-deck/scripts/build_html_deck.py \
  <project-output-folder>/html-deck-work \
  --output-root <project-output-folder> \
  --package <project-output-folder>/<descriptive-name>.zip \
  --report <project-output-folder>/<descriptive-name>-validation.json
```

The builder recompiles a source-bound v2 deck and requires byte equality with
its editable HTML, generated/shared CSS, resolved documents, and evidence
ledger. It then compiles a standalone file, applies the runtime idempotently,
embeds the publication-safe content and evidence ledgers, computes SHA-256, writes
`<output-root>/<64-hex-sha256>/index.html`, validates those exact bytes, and
creates a canonical ZIP. Errors block delivery. Rebuild ZIPs from work sources;
never edit generated packages.

Legacy v1 quantitative content fails by default. The
`--allow-unverified-quantitative-content` flag exists only for explicit
illustrative galleries or legacy material; it leaves
`evidence.status: not_verified` and is never acceptable for a source-backed
report.

Run static validation alone while iterating:

```bash
python skills/html-deck/scripts/validate_html_deck.py \
  <64-hex-slug>/index.html
```

### 5. Run strict automated browser QA

```bash
python skills/html-deck/scripts/browser_qa_html_deck.py \
  <64-hex-slug>/index.html \
  --output-dir <project-output-folder>/browser-qa \
  --report <project-output-folder>/browser-qa.json \
  --warnings-as-errors
```

The default viewport set covers 1280×720, 1920×1080, 1024×768, and 390×844.
The report checks each slide's geometry, overflow, declared-role collisions,
console/page errors and warnings, navigation, fragments, overview, notes,
Escape, reduced motion, and print behavior. It emits full-slide screenshots, a
screenshot index, and print-preview PDF. Missing Playwright/browser support is
`blocked` with exit code 2, never a pass.

Review the complete screenshot index and print preview. The automated gate
cannot judge source fidelity, hierarchy, decision usefulness, meaningful
motion, or whether a chart communicates the intended mechanism. Fix every
clipping, collision, weak contrast, unreadable label, or decorative animation;
then rebuild and rerun both gates.

#### Narrow static-deck compatibility exception

The normal authoring and delivery contract remains the strict Clara stage
profile above. Use `--profile static` only when an external, already-specified
deck contract must remain linked/static, such as a controlled format benchmark
or a preservation-bound legacy import. It is not an authoring shortcut and does
not waive source fidelity or visual QA. Follow
[references/static-compatibility.md](references/static-compatibility.md) and run
both the static validator and browser QA in that profile.

### 6. Use revision mode for existing Clara HTML decks

For a requested deck change, read
[references/revision-workflow.md](references/revision-workflow.md). Inspect the
baseline, create a hash-bound revision map, classify every slide, give each edit
target a reason, validate the map, edit a copy, and compare before/after:

```bash
python skills/html-deck/scripts/inspect_html_deck.py \
  <baseline> --report <output>/baseline-inventory.json

python skills/html-deck/scripts/validate_revision_map.py \
  <baseline> <revision-map.json> \
  --report <output>/revision-map-validation.json

python skills/html-deck/scripts/compare_html_deck_revision.py \
  <baseline> <revised> \
  --revision-map <revision-map.json> \
  --report <output>/revision-comparison.json
```

The comparator enforces untouched/protected slide and component fidelity,
slide-local provenance, declared global resources, order, IDs, and actual
target changes. It applies only to Clara stage decks/work folders. After a pass,
build and browser-QA the revised deck exactly as above.

## Codex-Native Run UX

Before write-heavy work, show a compact Run Intake table with sources, audience,
language, work folder, output root, privacy, and notes requirement. Ask only for
material unresolved choices. Use a Decision Table only for choices that would
materially change the result. Use a short checklist for source truth, plan and
ledger, composition, build, browser QA, semantic review, and delivery.

Before building, show one execution checkpoint naming work folder, output root, slide
count, package, static report, and browser-QA report. Default to keeping the
editable work folder, plan, ledger, content-addressed HTML, ZIP, static report,
screenshots, and browser report. This Default output policy is the normal run;
these artifacts are not choices to propose when the user has already requested
a complete deck. Never edit generated ZIPs by hand; rebuild them from source.

## Delivery

Return an Artifact Card with:

- clickable `index.html` and ZIP package;
- editable work folder, `deck-plan.json`, and `content-ledger.json`;
- for quantitative work, the sealed evidence bundle, resolved plan/ledger, and
  `evidence-ledger.json`;
- static validation and browser-QA reports;
- screenshot index and print preview;
- revision inventory/map/comparison when revision mode was used;
- slide count and source materials used;
- deliberately accepted residual issues, if any.

Include this user-facing revision affordance in the delivery: **“Want to revise
this deck? Tell Clara: ‘Record feedback on this deck.’”** When the user invokes
it, route to `deck-correction`; do not ask them to open the hosted capture URL or
import its download manually.

State that the deck is ready to publish, not already published, unless an
authorized publishing step actually occurred. Create `codex_run_review.md` only
when a run is blocked, a fallback was accepted, or a repeated failure needs a
local handoff note.
