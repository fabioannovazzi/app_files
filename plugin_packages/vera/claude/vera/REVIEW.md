# Directory reviewer notes: vera

## MCP servers
These servers run locally over stdio, exchanging data with local files and
helper processes on the user's machine.
This is their MCP transport, not an offline guarantee: browser acquisition
can access user-selected websites; incident identity/recovery can contact
the service below. Review widgets do not upload client documents.

- `agenziaAcquisition`: Review and run user-authorized browser acquisition tasks.
- `archiveOrganizationWidgets`: Review client-folder organization plans and decisions.
- `bilancioXbrlIt`: Prepare and review OIC accounts and XBRL workpapers.
- `checkEntriesWidgets`: Review sampled journal entries against supporting documents.
- `concordatoPlanReviewWidgets`: Review concordato plans and evidence.
- `deepResearchValidatorWidgets`: Review sourced legal/tax answers and research evidence.
- `financialAnalysisContracts`: Describe financial-analysis contracts and reviewed registers.
- `journalBankWidgets`: Review bank-to-journal reconciliation results.
- `journalSamplingWidgets`: Review qualified accounting journal samples.
- `newClientFilePreparation`: Review and apply client-file preparation decisions.
- `newClientProfessionalSetup`: Review new-client professional setup decisions.
- `openItemReconciliationWidgets`: Review open-item reconciliation results.
- `previdenzaInpsReview`: Review INPS evidence and workpapers.
- `promptOptimizerWidgets`: Review the legal/tax answer plan.
- `registroImpreseSariReview`: Review Registro Imprese practice guidance.
- `reportBuilderWidgets`: Review financial report inputs and outputs.
- `researchSources`: Manage local research subscription choices and review widgets.
- `studioWork`: Persist studio tasks, deadlines and external-action receipts locally.
- `varianceAnalysisWidgets`: Review accounting variance calculations and decisions.
- `veraIncidentHost`: Bind local installation/host identity for incident recovery.
- `veraNativeWorkspace`: Expose local client workspaces, source selection and review tools.
- `veraSalesPlan`: Describe the Actual-to-Plan workflow and its artifacts.
- `veraStudioArchive`: Manage registered local client folders and engagement records.

Remote: `veraIncidents` at https://mparanza.com/mcp/vera-incidents.
Receives technical incident metadata, reviewed diagnostics and recovery outcomes,
plus primary-task usage, outcome, receipt UUID/hash and actual 1-5-star ratings
with optional user-authored feedback. It authenticates with its own installation/
connection credentials. It does not automatically upload client documents, prompts
or professional output. Optional feedback is the user's chosen text. Diagnostics
exclude case text and passwords/API keys; credentials are authentication only.
Privacy policy: https://mparanza.com/privacy.

## Lesson downloads
Lesson data is fetched when the user starts or resumes a lesson, not installation.
Only data attachments, not helper code, are downloaded from
https://mparanza.com/static/shared/courses/vera/.
Each attachment must match the SHA-256 in assets/courses/remote.json and its
course manifest. Downloads are written to a temporary file; only verified bytes
are moved to the lesson destination. The cap is 25 MiB per file. HTTPS, the exact
mparanza.com host and the course path are checked, including every redirect.

## Font references (UNREAD_ASSET_REFERENCED)
- `mcp/workspace.cjs`: Base64-embeds Instrument Sans Regular in widget CSS @font-face.
- `mcp/studio-work-panel.cjs`: Base64-embeds Instrument Sans Regular in panel CSS @font-face.
- `modules/bilancio-xbrl-it/mcp/native-workspace.cjs`: Base64-embeds Instrument Sans Regular in widget CSS @font-face.
- `modules/browser-automation/mcp/server.cjs`: Base64-embeds Instrument Sans Regular/SemiBold in browser-review CSS @font-face.
- `scripts/research-sources.cjs`: Base64-embeds Instrument Sans Regular in research-choice CSS @font-face.
- `scripts/native_studio_work.py`: Hashes the Regular TTF as part of panel scope/version identity.
- `execution-files.json`: Records font SHA-256 hashes for package integrity, not execution.
- `modules/comunicazione-professionale/scripts/render_visuals.py`: Loads bundled Instrument Sans TTFs with Pillow/ReportLab for PNG/PDF text; fontTools checks glyph coverage.
- `modules/comunicazione-professionale/scripts/check_dependencies.py`: Checks that the three bundled TTF files exist.
- `modules/comunicazione-professionale/scripts/studio_document_format.py`: Reads/sets Word style font names and sizes; does not load TTF bytes.
- `modules/comunicazione-professionale/scripts/package_communications.py`: Names Instrument Sans in HTML CSS; does not load TTF bytes.

Fonts are typography data; none of these references executes a font as code.

## Package size
The package contains 53 top-level workflow/router skills and their
supporting methods, helpers and document/widget assets. This accounts for its
size; a scanner timeout does not establish that validation completed.

Contact: [fabio@mparanza.com](mailto:fabio@mparanza.com).
