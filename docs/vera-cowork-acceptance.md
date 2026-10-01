# Course-based Vera acceptance in Cowork

This maintainer procedure uses the shipped courses and their synthetic demo and
practice inputs. It does not add a second curriculum. Existing `teaching-kits`
CI executes workflow code locally with reviewed test inputs; that establishes
mechanical compatibility, not native Cowork routing, delivery or recovery.

The first cohort is Italian, one synthetic case per workflow:

| Case | Existing course | Demo → practice | Required inspection |
| --- | --- | --- | --- |
| bank | journal-bank-reconciliation | March → cumulative April | Two → three reference-backed pairs, exact signed amounts, Excel, notes, saved review |
| fiscal | dati-fiscali-strutturati | CU + first F24 → add second F24 | Field/source/period accuracy, extraction CSV and readable summary, no payment attestation |
| report | financial-report-builder | January–February → January–March | Word pages and tables, source-cell trace, subtotals counted once, unsupported sections explicit |
| fiscal-scan | Same fiscal course, declared transport variant | Rasterized first F24 + CU → add second F24 | Image-only PDF, OCR capability and visual tie-out; blocked if capability unavailable |

The bank case has exact references; it does **not** exercise ambiguous matching.
Reject any amount/date-only certainty encountered, but report that limitation.
The earlier requested-versus-received intake issue is not covered by these
fixtures; fiscal F24 status is covered without claiming a new-client intake pass.

Each case has **two independent routes** with identical inputs: `guided` follows
the installed written course; `ordinary` starts from its ordinary Vera request,
without course steps, command recipes, expected answers or pre-made decisions.
Each route has `demo`, `practice` and `resume` outcomes. Guided success cannot
certify ordinary routing. Both routes must finish before a core release pass.
The scan variant is reported separately and cannot certify the unmodified course.

## Prepare an exact package

Use a newly downloaded official website ZIP, not an extracted source tree. Record
the URL, retrieval time and hash. Compare against the candidate build separately;
when testing an unreleased candidate, clearly label its provenance instead of
calling it the public download. Use a new isolated folder for every package/run.

```bash
source /Users/fabio/Documents/GitHub/app_files/.venv/bin/activate
python scripts/cowork_acceptance/cowork_acceptance.py prepare \
  --package /private/tmp/vera-cowork-public.zip \
  --package-url https://mparanza.com/static/shared/vera/downloads/vera-cowork-plugin.zip \
  --output /private/tmp/vera-cowork-run-NEW
```

Preparation reads the archive without executing its code. It selects the
shipped course fixtures and verifies hashes against the same source/practice
revision. Cowork-specific teaching prose is projected by the package builder;
both the repository course hash and projected course hash are recorded.
The scan uses PyMuPDF in the existing declared environment to rasterize the
authored first F24. It removes the readable original from that variant's
connected folder and records both derivation hashes outside it. No OCR package
is installed by this tool.

`run.json`, `cases.json`, `courses/`, `derivations/` and `reviews/` are maintainer
evidence. **Connect only one `workspaces/CASE/ROUTE` folder to Cowork.** Never
connect the bundle root or reviewer answer catalog. This keeps expected solutions
out of the ordinary request. The workspace contains sources and plain requests;
it contains no finished outputs or maintainer review. Practice sources are
available but must not enter a demo cutoff. Preparing this folder records all 24
steps as `not_run` and cannot satisfy acceptance.

## Run and inspect

1. In Claude Desktop, inspect installed Vera version and enabled status. Update
   the existing installation using the exact downloaded ZIP through supported UI.
   Preserve old customer folders and lessons. Record installation UI evidence;
   upload alone is not installation evidence. Respect permission prompts; do not
   approve new unexpected security-sensitive access on the user's behalf.
2. Start a fresh **Cowork** session with the isolated route folder. Record session
   URL/ID, date with timezone, device/OS, execution environment, model, loaded
   plugin version/path and package SHA-256. Do not substitute a shell run on the
   Mac, a mocked host or ZIP inventory for this execution.
3. Submit `request-demo.txt`. In guided mode request the installed course and
   let its normal preparation and checkpoints run. In ordinary mode do not add
   course instructions or disclose oracle values. Respond to genuine mapping,
   scope and policy questions from the source evidence, recording every response.
   If intervention supplies missing engineering setup, record it as assisted;
   it cannot count as an independent routing success.
4. Inspect actual native records and open each promised deliverable. Trace pairs,
   fiscal fields or report cells against the sources. For bank outputs record
   `audit` and `matches`; fiscal outputs `fields`; report outputs `numeric_ledger`
   in `mechanical_files`. Use bundle-relative paths. These are the native files
   `reconciliation_audit.json`, `reconciliation_matches.csv`,
   `structured_fiscal_fields.csv` and `numeric_evidence_ledger.json` respectively.
   Counts/sums/selected fiscal fields are checked mechanically; all fields,
   relationship semantics, limitations and document layout require inspection.
5. Open links **from the Cowork delivery** to source and output files, including
   course source links on the guided route. A file existing on disk does not prove
   a working link. Capture the visible opening or exact error (including 404).
   Inspect Word pages in an available viewer; ZIP/XML readability is insufficient.
6. Save a real review note/decision using the workflow's normal persistence
   contract. Bank: TRN-001 inspected against both originals; fiscal: F24 is not a
   payment receipt; report: commercial causes need source evidence. Preserve the
   client manifest, engagement/run IDs, imports, source receipts, reviewed mappings
   and decisions, output registry, finalized native receipts and review trail where
   the workflow promises them. Do not fake receipts if archive writing is blocked.
7. Freeze/hash March, first extraction or February artifacts and records. Submit
   `request-practice.txt` in the same route with the new sources. Use a new native
   run/output directory; do not overwrite preceding work. Inspect changed findings
   and open the original deliverables and saved review again. Hashes must survive.
8. Start a **new Cowork session** connected to that same route folder, with no old
   conversation context. Submit `request-resume.txt`. Recover actual saved source,
   output and review links, IDs and unresolved items without recalculating them.
   Compare original hashes, inspect the durable review and record the distinct
   session ID. A claim that "the files are there" cannot certify recovery.
9. Repeat the complete sequence independently for the other route and cases. For
   the scan, inspect capabilities first; install optional OCR only after explicit
   user approval. Record unavailable OCR or unsupported scan as `blocked` with a
   diagnostic. Never substitute a readable source and call that a scan pass.

## Maintainer evidence and release gate

Edit the scoped files under `reviews/`, using the generated templates. Keep all
evidence inside the bundle; store screenshots, transcript/tool observations and
review notes under `evidence/`. Use `{ "path": "relative/path", "sha256": "..." }`
for each evidence, artifact and durable record. Outputs/records must belong to
their own route workspace. Every executed, failed or blocked observation needs
reviewer, ISO date, session ID, reason and actual evidence hashes. Keep unattempted
steps as `not_run`; dependencies of a failed demo are not presumed failures.

A passed review needs exact `host` identity and all six named `checks`, each with
`outcome: "passed"`, a specific `note` and nonempty `evidence_paths` referencing
the hashed observations. Name which links/pages/rows/records were actually opened.
Hash actual native output files in `artifacts` and saved review/registry files in
`durable_records`. Do not use prepared course files as execution results.

```bash
python scripts/cowork_acceptance/cowork_acceptance.py verify /private/tmp/vera-cowork-run-NEW
make check-cowork-acceptance COWORK_ACCEPTANCE_RUN=/private/tmp/vera-cowork-run-NEW
```

`verify` reports every outcome without making incomplete runs green. The Make
target exits nonzero unless all 18 core route/phase steps pass and the recorded
package version matches the current candidate. It rejects changed packages,
fixtures, runtime sources, outputs and evidence; missing routes; copied sources;
wrong native results; missing inspection; reused route sessions; and resume in
the previous session. Six scan steps remain visible even if blocked/not run.
The full result includes `all_passed` separately from `core_passed`; never describe
a core pass as including scans. The verifier cannot authenticate a human's UI
attestation or determine prose quality. A successful schema/hash check alone is
not real Cowork success. Tests using synthetic attestations are only verifier tests.

Keep the immutable bundle outside the learner workspace and retain it with the
release review. A reviewer may publish a concise course statement only after
inspecting accepted guided demo, practice **and fresh-session resume** evidence
for that exact package/course revision: "Questo esercizio è stato completato in
Cowork con Vera VERSION il DATE (italiano)." Link maintainer evidence separately;
do not put engineering details in the ordinary lesson. This implementation adds
no public claim and modifies no course lesson, privacy policy or formatting rule.
Any later statement must specify if it covers only one route or a scan variant.

Run the new verifier regression CI along with existing `teaching-kits` and
package alignment gates. CI does not manufacture host receipts and has no Cowork
pass badge. Until the host gate passes, releases can have technical checks green
but **Cowork acceptance outstanding**; preserve that boundary in release evidence.
