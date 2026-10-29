# Clara and Lucia neutral workflow UI release

Agent differential review on 2026-10-29, based on main e4fff2517bce87e64a4704f2ad99def88c4719e1.

## Inventory and implementation

The single palette, typography and control source remains
`plugins/_shared/ui/vera-theme.css`, with its approved Vera bytes unchanged.
The existing synchronizer now covers the union of the three product component
registries, and the host builder compiles that same CSS for all three products.
There is no second product palette or network dependency on host CSS.

| Surface | Owning source | Treatment |
| --- | --- | --- |
| Clara analytical MCP reviews | Distribution, mix, period, scatter, overlap and variance assets | Same canonical embedded theme; surface aliases use canonical tokens |
| Lucia local matter review and MCP widget | apertura-pratica assets | Embedded theme in both placements |
| Lucia firm-method editor | assets/playbook-editor.html | Embedded theme; hard-coded text/focus colours replaced by semantic tokens |
| Lucia prompt/model/research panels | prompt-optimizer and deep-research-validator assets | Already themed by #932; retained |
| Native course chat panel and compiled lessons | shared courseware assets in each product package | Chat theme compiled at build time; runtime lesson-only stylesheet link preserves report CSS |
| Public Clara/Lucia lesson shells | generated course.html and render_catalog.py | Canonical stylesheet after course CSS; only lesson pages receive it |
| Course launch controls | course-start.css | Semantic variables with original fallbacks; Vera public appearance retained |
| Hosted interview participant page | templates/hosted_interview.html | Embedded theme; same interview controls |
| Hosted recording/transcription/deck-feedback page | templates/case_notes_voice.html | Embedded theme; media preview and capture behavior retained |
| Hosted video narration page | templates/research_video_voice.html | Embedded theme; same upload controls |

Clara's case workspace is a durable file workspace, not a separately implemented
native HTML shell. Clara and Lucia's source app registrations are empty; their
on-demand MCP routes provide specialist review resources and course chat panels.
No new workspace or host capability is invented by this change. Host-owned
native choice dialogs and chat chrome cannot be restyled by plugin CSS.

Public product/function pages, seals/icons, presentation engines, professional
HTML/DOCX/XLSX reports, chart renderers and linked course input/output artifacts
are excluded. Course source/lesson text is unchanged; regenerated course metadata
changes only reviewed source bindings, including the new lesson-theme helper. Existing Claude listing fields and
product-specific document language rules are preserved.

## Differential data-boundary review

Every changed plugin/template HTML file was compared to the base after removing
style blocks: markup and scripts are identical. The theme is local CSS with no
imports, payload builder, tool argument, connector, activation rule or network
recipient. The playbook remains an inert JSON editor with explicit import/export
and no server connection. Its schema, tracked decisions and save behavior are
unchanged. Analytical review widgets read the same bounded tool outputs; their
source/output records, filters, bridge behavior and persistence are unchanged.
Matter review retains the same local review/decision routes and source hashes.

Hosted interview, voice and narration changes are restricted to inline styles.
Their microphone/screen/file controls, authorization and uploads are unchanged;
existing source font links are retained, with no new font service or recipient.
Template review is evidence about these presentation deltas, not proof that a
provider processed data or that an actual interview/recording completed.

The existing Vera course hash projection is retained before package integrity
hashes. Clara/Lucia course chat pages are projected the same way; their lesson
renderer copies the canonical offline stylesheet and links it only from
`course.html`. Their shared report/course CSS bytes are preserved. A missing
cosmetic stylesheet does not block lesson delivery. Source-course and index mismatches are still rejected. Only the public
lesson shell loads the new local stylesheet; linked reports and examples retain
their original CSS. The source manifest, selected exact-version bindings and
reviewed course hashes require fingerprint regeneration. This is an agent
engineering review, not invented human approval or a new professional gate.
Only records made stale by this reviewed diff are refreshed. The firm-method
editor asset is now explicitly governed by its owning metodo-studio record.
Where a teaching review already named an older digest on main, the exact Git
snapshot is recovered and compared excluding source bindings before carrying
forward its historical editorial judgment; the recovered commit is recorded. Historical missing
privacy reports, incomplete measurements and host-conversation delivery remain
separate open acceptance limits; this presentation release does not resolve them.

## Verification and rollout boundaries

Browser verification uses actual source HTML and rendered hosted templates with
synthetic context at 1440×1000 and 390×844. Hosted network/capture actions are not
invoked. Playbook exports are checked as JSON; course clipboard feedback and
analytical search/selection are exercised. These are browser UI checks, not an
installed plugin or a fresh Codex conversation acceptance claim.

Preparation blocks are retained in release evidence: sandboxed Chromium could
not register its Mach port and was rerun with the authorized browser execution
permission; an initial clipboard check read before its async feedback and was
corrected to await the state. The synchronizer initially assumed all output
files existed; its new generated stylesheet required an existence check before
comparison. The public link deduplicator normalizes relative links to absolute URLs; the
synchronizer now recognizes both representations. A broader test run first
encountered sandbox loopback restrictions, then three missing-ZIP checks while
archives were still building. A build predating the lesson/report separation
correctly rejected the newly stale course fingerprints; reviewed records and
archives were regenerated after the final source change. A per-archive inspection found the Lucia Cowork projection omitted the new
`ui/theme.css`; the explicit projection now retains it and a packaged regression
checks both its canonical bytes and the unchanged report stylesheet. All host
archives are rebuilt from that correction. No business pipeline or Test 4 was
run, cancelled or changed.

Vera 0.1.524, Clara 0.1.365 and Lucia 0.1.191 exceed main's release identities
and Clara 0.1.362 reserved by open PR927. All product/host packages are rebuilt.
Marketplace, installed caches and active chats are outside this deployment.


The final accounting/reporting CI run passed 252 regressions but found that the
matter asset generator still emitted the old appearance. Its output now passes
through the same central theme compiler. The shipped editable/widget bytes are
unchanged; a regression proves a future central edit survives regeneration in
both surfaces. This repairs a real regeneration path, not the test's drift
assertion. Final CI is repeated after this developer-generator correction.


Release-alignment CI later reached the Geneva snapshot check and found its
manifest digest still bound to0.1.523. The inventory is regenerated by its own
snapshot helper and the assessment is rebound to that exact fingerprint.
All55 entrypoint identities/bytes and every jurisdiction disposition row are
compared unchanged with the prior release. The historical0.1.523 review binding
is preserved; the new0.1.524 binding is separate. This is release provenance,
not new jurisdiction or professional acceptance. Affected packaged metadata
and privacy fingerprints are rebuilt before final CI.


A later accounting CI run completed its behavioral tests and failed in Mypy's
module discovery: the generator's package/CLI imports exposed the same theme
module under two names. The accounting quality command now uses explicit
package bases, retaining its imported-module checks. The exact corrected
command is verified locally; product code and package bytes are unchanged.
This is a test-harness correction, not a relaxation of product behavior.
