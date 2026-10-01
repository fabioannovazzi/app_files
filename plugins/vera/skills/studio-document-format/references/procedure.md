# Internal mechanics and supported output

All paths below are absolute when executing. The studio sees proposals and
actual files; Vera supplies technical artifacts. No script infers style,
contacts a model service, downloads a font or publishes a document.

```text
python <vera-root>/scripts/studio_document_format.py inspect --sample <selected.docx> --output <fresh-evidence.json>
python <vera-root>/scripts/studio_document_format.py prepare --workspace <private-studio-workspace> --review-id <fresh-id> --settings <model-proposal.json> --sample <selected.docx> --brand <first-run-brand.json> --language <it|en|fr|de|es>
python <vera-root>/scripts/studio_document_format.py approve --review-dir <workspace/runs/id> --review-digest <exact-digest> --reviewer <actual-reviewer> --confirmed-by-user
python <vera-root>/scripts/studio_document_format.py report-case --tutorial-case <bound-tutorial_case.json> --source <generated-financial-source.csv> --studio-workspace <approved-workspace>
python <vera-root>/scripts/studio_document_format.py practice-materials --spec <course-spec.json> --output-dir <fresh-bound-folder>
```

Repeat `--sample` for every selected example; a logo is supplied as the brand's
`logo_path`. First-run brand data requires `studio_name`, `primary_color`,
`accent_color`, `background_color`, `text_color`, `contact_line`; six-digit
colors include `#`. `logo_path` is optional. `--brand` is omitted when a profile
exists. The existing studio identity, channel settings and logo are authoritative.
Changing the shared logo/identity requires the communications profile procedure;
this route can enable or disable its use in Word.

The DOCX proposal is an object matching the report component's
`assets/studio-docx-format.schema.json`. Supported fields include requested
font, body/heading/table sizes, point line spacing, paragraph spacing, heading
color, A4 `margins_mm` (`top`, `bottom`, `left`, `right`), header/footer text and
distances, page numbering, logo use/width, table header and alternating fills,
number/date display and plain signature lines. Values are validated, including
header/footer clearance. No macros, arbitrary Word XML, fixed row heights,
embedded fonts, custom page sizes or exact template import. Signature lines do
not sign the report. Renderer font availability remains a separate check.

Use `font_family` for an observed or chosen Word font, not the communications
PDF font. Word `margins_mm` overrides only the Word layout. For revisions,
load `studio_profile.json`, copy its `profile.document.docx`, merge the user's
changes, then submit the complete resulting object. New setup labels all
unobserved voice/email/web/social conventions as Vera defaults in the complete
proposal. Explain those defaults and their adoption boundary; do not claim the
Word examples taught other channels.

`prepare` snapshots the exact examples and selected logo, records a digest-bound
proposal, and produces `preview-short.docx`, `preview-long.docx` and
`preview_manifest.json`. Approval rejects missing, edited or cross-proposal
previews, changed examples, and stale prior standards. The reviewer confirmation
is an assertion, not authenticated identity or proof that the person saw pixels.

Financial-report-builder currently consumes the accepted standard at report
construction and review regeneration. It freezes presentation settings and logo
bytes in the report recipe for reproducible replay; examples, their text,
communications history and other clients are not included. Numbers retain
canonical precision, currency and scale. Other Vera DOCX generators, arbitrary
existing Word documents and exact studio templates do not yet consume this
standard. Communications PDF/email/web/social retain their separate settings.

Model context may contain selected formatting metadata, studio identity,
preferences, the selected logo, proposals, rendered synthetic previews and user
review decisions. No example text is emitted by `inspect`, but direct visual
inspection of a selected document can expose its text to the selected model.
Additional text interpretation follows the isolated communications route.
Local storage does not make Codex/Cowork model processing offline or automatically
anonymous. There is no automatic upload to Mparanza, archive scan or external
send in this workflow. The later client report has its own model-data boundary.
