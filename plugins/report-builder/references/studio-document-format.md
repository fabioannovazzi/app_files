# Studio document formatting coverage

The approved standard is the existing communications workspace's
`studio_profile.json`. Explicit studio workspace ID/name checks prevent reuse
from a different selected studio; no automatic per-client/global lookup exists.
Vera must select the correct studio before applying it to a client engagement.
There is no automatic organization-level link between Studio Archive client
identity and the communications workspace. Local selection is an operator
assertion, not identity authentication.

`profile.document.layout` supplies A4 margins and baseline font sizes/leading.
`profile.document.font_family` remains the PDF renderer's existing controlled
font family. Optional `profile.document.docx` supplies Word overrides:

- `font_family`, `body_font_size_pt`, `line_spacing_pt`,
  `paragraph_before_pt`, `paragraph_after_pt`;
- `heading_1_size_pt`, `heading_2_size_pt`, `heading_color` (six hex digits);
- `table_font_size_pt`, `table_header_fill`, `table_header_color`,
  `table_alternate_fill` (six hex digits). Financial total cells align right;
  table headers repeat and rows expand to fit content. Rows stay together when
  they fit on one page; a row taller than the page may still continue;
- `header_text`, `footer_text`, `page_numbers`, `use_logo`, `logo_width_mm`,
  `header_distance_mm`, `footer_distance_mm`. Logo is persisted PNG/JPEG,
  digest-checked, and bounded to the available header height;
- `number_format`: `canonical`, `decimal_comma`, `decimal_point`. Only reviewed
  totals change their display (e.g. `1234.50` to `1.234,50`), with no rounding,
  precision change, or currency/scale change. Source previews, Markdown, Excel
  and financial analysis remain canonical. Numeric closure checks the exact
  expected displayed text and records the unchanged canonical value;
- `date_format`: `iso`, `dmy`, `mdy`, applied only to an explicitly supplied
  `recipe.report_date` in ISO format. Free-text reporting periods, source dates,
  and narrative are not rewritten;
- `signature_lines`: plain text attribution before the audit appendix, never
  cryptographic signing, a signature image, or professional approval.

Example DOCX preferences (proposed settings, requiring studio review):

```json
{
  "font_family": "Arial",
  "body_font_size_pt": 11,
  "line_spacing_pt": 14,
  "paragraph_after_pt": 6,
  "heading_1_size_pt": 18,
  "heading_2_size_pt": 13,
  "header_text": "Selected studio name",
  "footer_text": "Selected studio contact text",
  "page_numbers": true,
  "use_logo": false,
  "number_format": "decimal_comma",
  "date_format": "dmy",
  "signature_lines": []
}
```

## Generator coverage inspected in source

| Generator | Reusable studio formatting in this change |
| --- | --- |
| financial-report-builder `report_builder_core.py:write_report_docx` | Supported DOCX build, review regeneration, deterministic replay |
| communications `render_visuals.py` and `package_communications.py` | Existing PDF geometry/fonts/logo and email/web/social standard preserved; DOCX overrides do not affect them |
| concordato `concordato_plan_core.py` and `concordato_semantic.py` DOCX summaries | Unsupported; their existing styles remain |
| deep-research-validator `package_validation.py` and `adversarial_opinion.py` DOCX export | Unsupported |
| variance-analysis `root_cause_client_report.py` DOCX report | Unsupported |
| business-planning `planning_report.py` HTML/PDF | Unsupported |
| report-builder Excel, Markdown, JSON and receipts | Canonical content preserved; no studio typography/layout applied |
| other workstreams producing spreadsheets, JSON, Markdown, HTML or host-authored documents | No general profile injection; use their actual output-specific workflow |

This is not arbitrary Word-template replication. There is no font download,
font embedding, full-page scanned letterhead, signed PDF/DOCX, or automatic
reformatting of existing source files. Different renderers may substitute a
missing font. Always inspect the final renderer's output before delivering a
formatted file, and disclose unsupported settings or font substitutions.
