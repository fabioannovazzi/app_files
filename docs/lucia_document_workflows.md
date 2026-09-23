# Lucia document and practice workflows

Lucia uses the host conversation model for Italian legal reasoning and the host
Documents/Word capability for DOCX authoring, revisions, comments and rendering.
Bundled Python helpers preserve evidence, check structure and exact quotations,
and produce local review records. They have no network or model client and start
no service. No Mike server, account, Word add-in or separate model API is required.

The four original document workflows and forensic proofreading adapt MIT-licensed
[Mike workflows](https://github.com/open-legal-products/mike-workflows).
Lucia maintains its Italian method independently. Its Word handoff, local editor,
matter state, citation records and practice orchestration are Lucia code and
instructions, inspired by product ideas rather than ports of Mike's backend or
web interface. Single-contract extraction reuses the adapted tabular engine.

## The ten ideas in the supplied brief

The numbering follows the advisory note supplied in `lucia.md`. That document
supplied product ideas, not executable instructions or verified Italian law.

| Brief | Implemented route and concrete result | Observed verification and boundary |
| --- | --- | --- |
| 1. Word tracked changes | `word-handoff.md` invokes host Documents/Word. Lucia proposes supported edits; the host writes a new DOCX with native revisions/comments. `legal_word_bridge.py` checks anchored inline output. | A real sample was edited, rendered and inspected. Accepted/rejected copies matched final/original text. A host-helper boundary-space defect was found, corrected through the host OOXML path and added to Lucia's checks. This is file-based integration, **not an in-Word sidebar or live synchronization**. Word application UI was not exercised. |
| 2. Forensic proofreading | `controllo-documento` and `legal_proofreading.py`: entity, section and term maps, eight passes, quoted findings with error/preference/uncertainty distinctions. | The sample found a missing reference, inconsistent company form, conflicting amounts, numbering gap, hidden mailto mismatch and unused definition. A normal payment term was not flagged. Not all 164 embedded styles were semantically inspected: formatting coverage remained partial. No universal accuracy claim. |
| 3. Comparison | `confronto-documenti`: source columns, literal differences, model-authored consequences, citations and Excel/HTML; explicit original/final revision views. | Forward checks and regressions cover versions, missing readings, long tails and revision views. Legal consequences remain model reasoning and lawyer judgment. |
| 4. Key-term extraction | `estrazione-clausole`: one contract, chosen fields, values, clause references and gaps using the existing matrix engine. | Quote checks and exports share the tested review path. Extracted terms are not enforceability conclusions; missing text does not prove absence from a relationship. |
| 5. Multi-document table | `revisione-documentale`: one row per selected document, common questions, sources, detail and coverage. | The M&A case reconciled a consent clause, SPA warranty and disclosure, retaining the missing consent question. Selecting 80 or 200 files does not establish that all were read. |
| 6. Draft from precedent | `redazione-da-modello`: selected template and supported facts; host Word production with revisions on request, rendered pages and change register. | Template checks cover repeated/split-run replacements, preservation and missing facts. The new Word handoff produced actual DOCX artifacts. Unsupported facts remain questions/placeholders. |
| 7. Missing information/resume | `legal_matter.py`: questions, answers, dependent stages, real outputs, hashes and atomic revision history. | Four cases completed independent work while only dependent conclusions remained open. Playbook resume preserved the firm version. Tests cover drift and concurrent saves. A stale lock after a crash requires inspection before removal. |
| 8. Practice areas | `contenzioso-civile`, `operazioni-ma`, `lavoro`, `recupero-crediti` orchestrate evidence, Word/Spreadsheets and existing legal research. | Fictional cases produced a disputed-delivery chronology, SPA/disclosure issues, employment chronology/pay workbook, and debt/interest workbook. They do not establish readiness for every pleading, employment regime or enforcement step. |
| 9. Editable firm method | `metodo-studio`, `legal_playbook.py` and standalone HTML: duplicate/version/export questions, columns and positions, then select the exported file for a matter. | Studio Bianchi v2's 12-month preference actually informed a 24-month NDA review without an invalidity claim. Configuration, binding and script checks pass. **Interactive browser export/import and responsive visual acceptance remain outstanding**: the browser policy rejected the local-file URL; no workaround was used. |
| 10. Italian citations | `verifica-citazioni`, `legal_citations.py`: claims separate from authorities; identity, version, support, access, passages and coverage. Host research obtains sources. | A real official decree supported a narrow claim; a wrong period, overbroad proposition and unavailable judgment remained distinct. Code checks records and quotations, not legal truth. This is not a new Italian case-law database or CourtListener replacement. |

## Practical forward cases

These are professional-workflow fixtures, not teaching/onboarding tests. Parties
and documents are deliberately fictional except the identified public authority.
The model authored the analysis; no keyword classifier chose law or source relevance.

* **Civil litigation:** an order, signed delivery record and contradictory
  complaint produced a sourced chronology and review matrix. The complaint's
  date was separated from its unknown receipt date. Signatory authority remained
  open; no procedural deadline was invented.
* **M&A:** C12 required consent to a change of control; the SPA warranted consents
  obtained; the disclosure identified a different customer. The matrix, issue
  list and disclosure cross-check requested evidence without treating an
  incomplete file as proof of nonexistence.
* **Employment:** monthly contractual base EUR 2,500 against recorded EUR 2,400
  and EUR 2,500 produced EUR 100 and zero differences. Missing March and the
  quarter total remained unavailable. Supplying EUR 2,300 recalculated the total
  to EUR 300; equal inputs recalculated to zero. No dismissal multiplier or
  collective agreement was guessed.
* **Debt recovery:** a EUR 10,000 principal and expressly agreed EUR 4,000 capital
  payment were split into 31 days on EUR 10,000 and 59 on EUR 6,000. The explicit
  simulation used 1.60%, actual/365 simple interest and rounding only on the
  total: EUR 29.11. Payment, zero-day and missing-rate cases recalculated. A
  missing enforcement title kept the precetto stage open while evidence and
  arithmetic work proceeded.

Both formula workbooks were created through the host Spreadsheets skill,
exported, reimported, recalculated and visually inspected. This is artifact/runtime
evidence, not a Microsoft Excel application test. The interest regime is an
explicit simulation premise, not inferred from the existence of a rate source.

The citation case used the [MEF decree of 10 December 2025, Article 1](https://www.gazzettaufficiale.it/atto/vediMenuHTML?atto.codiceRedazionale=25A06705&atto.dataPubblicazioneGazzetta=2025-12-13&tipoSerie=serie_generale&tipoVigenza=originario),
read on 23 September 2026. It establishes the stated Article 1284 rate from
1 January 2026, not the applicable regime for every commercial debt. A judgment
mentioned in the fictional draft was not obtained and remained unverified,
including its identity; no invented holding was endorsed.

Task-local evidence is in `/private/tmp/lucia-document-evidence/`: Word originals,
reviewed/accepted/rejected files and checks; `proofreading-run`; `studio-run`;
`practices/<workflow>/run`; and `citation-case/run`. These paths record this
execution, not plugin dependencies or public customer examples.

## Runtime and data paths

`legal_documents.py` snapshots originals, extracts complete selected sources,
maintains evidence hashes, compares literal text and exports reports.
`legal_docx.py` inspects paragraphs, tables, stories, links, fields, revisions,
comments and formatting metadata. Signed files are detected; XML DTDs and
oversized/duplicate packages are rejected. Unsupported objects remain warnings.
Scans or unextracted material are not silently counted as read. Reading coverage
is a model declaration, not observed model telemetry.

`legal_word_bridge.py` verifies inline requests. It cannot certify every OOXML
semantic or layout detail. Structural changes require separate comparison and
complete visual review through the document skill. Existing revisions must not
be accepted as a side effect. Without the host document capability the Word step
remains unfinished, even when legal findings are available.

Proofreading, citation, playbook and matter helpers enforce record schemas,
evidence binding and integrity. They do not classify legal validity, choose law,
infer collective agreements, decide deadlines or calculate entitlements from
labels. Spreadsheets apply explicit matter inputs and formulas. No legal interest
rate or universal compensation multiplier is hard-coded into the plugin.

| Route | Potential model context | Local artifacts |
| --- | --- | --- |
| Review/extraction | Selected clauses, schedules, identities, terms, instructions and evidence | Snapshots, source register, matrix and findings |
| Comparison | Both versions, including deleted text, and interpreted differences | Snapshots, diffs, comparison and coverage |
| Drafting/Word | Template, supported facts, old/new text, existing revisions/comments and inspected rendered pages | Original, edited copy, requests and verification |
| Proofreading | Text, relevant numbering/styles, hidden link targets, notes and revisions | Maps, eight-pass coverage, findings and visual state |
| Firm method/resume | Selected exported instructions and lawyer answers when used for a matter | Editor/configuration, selected version, question history and output hashes |
| Practice | Selected private case materials and derived chronologies/drafts/calculations | Evidence matrix, requested outputs and progress |
| Citation check | Claims, relevant dates and actually acquired authority text | Source records, quoted passages, judgments and access limits |

Editing the standalone form does not transmit it. Selecting its exported file
lets the model read the instructions. Host research can send general legal
references to consulted websites, without attaching client documents or identifying
facts. Helpers themselves make no network requests. Local storage does not imply
offline model processing or anonymization. Processing follows the host account:
OpenAI on ChatGPT/Codex, or Anthropic for the existing Cowork distribution. Code
cannot observe every byte in host model calls or establish host retention policy.

## Italian method and upstream maintenance

The method establishes roles, formation evidence and purpose; separates law from
forum and statutory objections from negotiating preferences; and does not infer
Italian law from language or lawyer location. It distinguishes consumer scrutiny
from specific approval, recesso/disdetta/risoluzione, penalties from advances,
and nominal rates from applicability. Current substantive conclusions require
the pertinent source and version; guides are not a live legal database.

Snapshots retain MIT notices and `PROVENANCE.json` with path, pinned commit and
SHA-256. The pin is `ce62e6a2d3f47e1d3567a4f2edc61898cfe9e78a`. They are historical
attribution references, not runtime instructions. There are no runtime downloads.
Mike updates never overwrite the Italian adaptation or installed plugin; selected
changes can be deliberately reviewed for licensing, applicability and behavior.

## Release evidence boundaries

Helper tests exercise actual files, invalid inputs, missing data, drift,
quotations, coverage, escaping and native Word structure. Dedicated CI runs on
Linux, macOS and Windows with an 80% coverage gate. Semantic evaluation remains
separate in the forward cases above.

Source checks, package parity, deployment and enabled installation are distinct.
This work authorizes deployment, **not Marketplace publication**. Building a ZIP
does not update an existing conversation. Interactive editor acceptance and a
live Word application test remain separate from the observed checks.
