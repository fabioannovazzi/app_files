# Lucia document workflows

Lucia includes four native workflows derived from the MIT-licensed
[Mike workflow collection](https://github.com/open-legal-products/mike-workflows):
contract review, document comparison, structured multi-document review and drafting
from a supplied template. The upstream questions are adapted to the represented
party and applicable jurisdiction; they are not legal rules or an automatic
legal classifier.

## Runtime and evidence

The host conversation model reads selected documents and authors findings,
interpretation and proposed wording. `plugins/lucia/scripts/legal_documents.py`
performs local extraction, original snapshots, evidence hashing, literal text
comparison, quote-occurrence checks, report generation and exact template edits.
It has no network or model client and starts no service. The four skills do not
require Studio Archive or Mike's application, database, provider APIs or server.
Other Lucia workflows retain their existing runtime contracts.

PDF pages and DOCX XML-part/paragraph anchors identify evidence. DOCX extraction
includes table paragraphs, headers, footers, notes and comments; tracked changes
and unextracted objects remain warnings. Image-only pages and missing schedules
are not evidence of absent terms. Nothing silently clips long sources. Review
coverage is an explicit model declaration, not observed model telemetry. A quote
match proves that text occurs at an anchor, not semantic or legal support.

HTML, CSV and XLSX retain review perspective and coverage limits. Comparison adds
one document column per source and an explicit model-authored difference for each
topic. Spreadsheet formula-like text is escaped. Reports make no remote asset
requests. Failed rerenders retire prior outputs instead of leaving them current.

Drafting keeps the original and edits a copy of a DOCX/TXT/Markdown template.
DOCX replacements preserve untouched ZIP parts and surrounding run formatting;
replacement text inherits the first affected run's formatting. Changes requiring
structure, tracked changes, fields or embedded objects need a document editor and
visual inspection. Exact replacement validation does not validate facts or law.

## Data-path review

Reviewed against the four skills and local helper on 2026-09-22:

| Workflow | Potential model-context content | Local outputs |
| --- | --- | --- |
| Contract review | Selected clauses and schedules, parties, negotiation objectives, commercial terms, quoted passages and proposed wording | Original snapshots, evidence pack, issue report, review table |
| Comparison | Selected versions, including text removed in later versions, literal differences and their interpretation | Snapshots, text diffs, comparison and source tables |
| Structured review | Selected files and names, questions, amendments/schedule relationships, extracted terms and evidence cells | Evidence pack, matrix, detailed findings, coverage and source register |
| Drafting | Supplied template including examples, selected supporting facts, instructions, changes and the resulting draft; rendered pages when inspected | Original snapshot, edited copy, change register with factual basis |

No new external boundary is introduced by the helpers. Model processing follows
the host account: OpenAI on ChatGPT/Codex, Anthropic when the existing Cowork
distribution is used. Local extraction and storage do not make model processing
offline, automatically anonymize data or establish the host's retention policy.
The helpers cannot observe which bytes the host actually includes in a model call.
The public pages explain the distinct content of each workflow in five languages.

## Upstream maintenance

Every source snapshot has its original MIT notice and a `PROVENANCE.json` with
upstream path, pinned commit and SHA-256. The pinned commit is
`ce62e6a2d3f47e1d3567a4f2edc61898cfe9e78a`. There are no runtime downloads.

To take upstream improvements: compare the recorded files against a chosen newer
commit; review legal assumptions, instructions and licences; update the snapshots
and provenance; adapt Lucia's instructions deliberately; exercise realistic legal
document cases and regression tests; bump Lucia and rebuild all three host
distributions. Updating Mike does not silently change an installed Lucia version.

## Verification

`tests/plugins/test_lucia_legal_documents.py` covers preservation, long-document
tails, invalid PDFs, source drift, exact citations, incomplete coverage, report
context, comparison exports, formula/HTML escaping, Word replacements, upstream
attribution and execution of the packaged helper. Its network guard rejects socket
connections in the in-process workflows. The dedicated CI job runs on Linux,
macOS and Windows with Python 3.12 and an 80% coverage gate.

Independent synthetic forward tests exercised all four workflows, including an
image-only PDF, multiple versions and split-run DOCX placeholders. Fixes from that
evaluation preserve detailed limits and context, add the explicit comparison
column and retire stale reports. Mechanical checks do not establish legal quality
on all matters or acceptance in an already-open installed-plugin conversation.
