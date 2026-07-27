# HTML Deck Quality Bar

Read this before authoring or revising a standalone presentation.

## 1. Narrative architecture

Build the talk around a tension the audience can recognize and a decision they
can make. A useful sequence is:

1. open on the contradiction or stakes;
2. make the mechanism visible;
3. show the evidence and uncertainty;
4. compare choices or scenarios;
5. define governance, controls, or conditions;
6. close on an action, principle, or question.

Use chapters only when they help the audience locate itself. A chapter title is
not a slide's argument. Make slide titles audience-facing claims or questions.

## 2. Source fidelity

Maintain a content ledger outside the published folder. For every slide, record
the authoritative wording, numbers, qualifications, and evidence basis.

- Distinguish actual, target, forecast, scenario, probability, estimate, and
  illustrative example.
- Preserve units, signs, timing, population, and comparison basis.
- If a claim is inferred, make the inference visible or remove it.
- If a number cannot be reconciled, stop and resolve it before visualizing.
- Never let generated prose explain an unverified number.

## 3. Visual grammar

Use a small coherent system:

- one editorial serif for large assertions;
- one neutral sans-serif for explanatory copy;
- one monospace face for labels, values, and controls;
- a warm or cool paper base, one dark interlude tone, one primary accent, one
  analytical accent, and one risk color;
- hairlines, restrained grids, and deliberate whitespace instead of generic
  drop-shadow cards.

Aim for a recognizable rhythm rather than identical slides. Alternate between:

- an oversized statement or chapter transition;
- a single quantitative visual;
- a structured comparison;
- a process, timeline, or causal flow;
- a scenario or decision surface;
- a quiet closing page.

Avoid stock photography, ornamental icons, decorative gradients, glassmorphism,
and fake dashboards unless the subject itself requires them.

## 4. Layout and projector legibility

- Keep the stage fixed at 16:9 and derive its width from both viewport width and
  height.
- Keep critical copy within a safe area of roughly 6% horizontally and 7%
  vertically.
- Use no more than two text sizes below the headline on a normal slide.
- Use a minimum equivalent of roughly 18 px body copy at a 1280×720 stage.
- Keep charts direct-labeled. Avoid legends when the marks can carry labels.
- Do not put speaker notes, sources, or caveats in microscopic footers. Move
  delivery detail to notes; keep only decision-relevant qualifications visible.
- Prefer fewer, larger marks over a dense replica of a spreadsheet.

Operator controls may overlay the letterbox or stage edge and auto-hide. They
must not be mistaken for slide content and must disappear in print.

## 5. Motion with meaning

Use motion to reveal causality, timing, sequence, or uncertainty:

- draw a path when explaining progression;
- move a marker when timing shifts;
- grow a bar from its real baseline;
- reveal scenarios in decision order;
- use fragments to pace a proof or comparison;
- use a restrained orbit or pulse only when it encodes monitoring or recurrence.

Keep transitions under about 800 ms and use one easing family. Avoid perpetual
movement that competes with the speaker. All essential meaning must remain
available with reduced motion enabled.

## 6. Interaction contract

Every finished deck must support:

- previous/next controls;
- Arrow keys, Page Up/Down, Space, Home, and End;
- hash-deep links for stable slide URLs;
- ordered fragments that resolve before slide advance;
- overview/map overlay;
- speaker notes toggle;
- fullscreen toggle;
- Escape to close overlays and notes;
- touch swipe;
- reduced motion;
- print output with one slide per page;
- Clara Voice Capture slide ID/title metadata.

## 7. Publication contract

- Store the published `index.html` under a lowercase 64-character hexadecimal
  directory.
- Keep the page self-contained and free of remote dependencies.
- Include `noindex,nofollow,noarchive` by default.
- Package the slug directory, not only the naked HTML file, so extraction
  preserves the difficult URL.
- Do not claim publication until an authorized upload succeeds and the remote
  URL has been opened and checked.

## 8. Final critique

Run two distinct passes.

Content pass:

- Does each slide add decision value?
- Is every claim true to the source and correctly qualified?
- Are the recommendation, evidence gaps, conditions, owners, and next steps
  explicit where relevant?
- Can the speaker deliver the argument without reading paragraphs?

Presentation pass:

- Is the title readable in one glance?
- Is the focal point obvious?
- Is anything clipped, crowded, faint, or decorative?
- Do light and dark slides form a deliberate rhythm?
- Does animation explain the slide rather than advertise the code?
- Does the deck still work at projector, tablet, and phone viewports?

Repeat until no material issue remains or a residual issue is explicitly
accepted with a concrete reason.
