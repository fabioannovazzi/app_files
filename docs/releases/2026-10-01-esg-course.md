# Vera ESG evidence course

The prepared `esg-reporting-assurance` kit follows the current evidence foundation,
not a complete ESG reporting or assurance pipeline. It uses the existing native
Vera course catalogue, renderer, teacher/working-chat flow and Studio Archive.

## Start and materials

In a compatible desktop Codex installation containing this release, ask:
**Vera, insegnami il fascicolo ESG.** Onboarding is optional. Local Work requires
the native controls and local execution actually to be available. Cowork uses its established interactive written lesson in one conversation,
without native voice or teacher/worker chats.

Developer inspection from the repository's activated `.venv`:

```sh
python plugins/vera/scripts/local_courses.py show --workflow esg-reporting-assurance --language it
python plugins/vera/scripts/local_courses.py render --workflow esg-reporting-assurance --language it --output-dir /absolute/new/lesson/kit
```

Course source: `scripts/course_materials/kits_{it,en,fr,de,es}_esg.json`.
Fictional sources: `scripts/course_materials/inputs/esg/{demo,practice}/`.
Compiled kit: `plugins/vera/assets/courses/esg-reporting-assurance/`.
Static guides: `static/shared/courses/vera/esg-reporting-assurance/<language>/course.html`.
The public catalogue and ESG explanation page link to the guide.

## Exercise

Officina Selce is fictional. Read the brief and initial CSV before selecting the
correction. Run the ordinary ESG helper with a separate tutorial client, bind the
0 kWh cell, missing prior year and declared excluded-site observation, review an
actual participant decision and create a partial draft. Without a decision, leave
review open; never fabricate learner approval to demonstrate history.

Import the 15 kWh correction as a new immutable Archive input and start a successor
in the same engagement selecting historical and updated inputs. Carry the exact
previous context and reuse logical evidence ID `energy`. Show the current state:
the old evidence, dependent decision and draft are obsolete; original files and
history remain. Missing and non-applicable remain distinct null statuses.

A separate, less guided Laboratorio Quarzo practice begins with 8 kWh and updates
to 12 kWh within its own engagement. Preserve the demonstration. Check source
cells, units, period, scope, interpretation, sufficiency and decision dependencies.
Declared zero is not proof of actual zero consumption. A blank alone does not
establish non-applicability. New partial drafting does not renew old approval.

## Verification and boundaries

Ten native helper regressions execute both phases in five languages, with clearly
labelled synthetic operator decisions. They preserve the first finalized state,
source bytes and prior drafts, inspect stale dependencies and generate a new
partial draft without reusing obsolete approval. Both runs finalize ordinary
mechanical artifact declarations. Test automation performs no host model reads;
its no-model reports cannot serve as a live conversation's model-read reports.

The focused suite passes 60 tests with 88.72% ESG helper coverage. Black, Isort,
Mypy and Bandit pass for the ESG sources; the shared discovery policy passes its
format/type/security checks. Per-language editorial/output review is recorded in
`scripts/course_materials/release_reviews/vera/esg-reporting-assurance.json`.
Existing lesson content and files are unchanged; their prior reviews retain a
bounded refresh for the shared policy fingerprint that now allows ESG teaching.

Candidate product versions: Vera 0.1.329, Clara 0.1.239, Lucia 0.1.77;
ESG component 0.1.1. Shared courseware is bundled by all three products, so their
packages are rebuilt together. These are candidate versions, not evidence of
Marketplace publication or installed acceptance. Recheck concurrent releases and
Published versions before publication; rebuild if main advances.

The release gate validates all 50 kits / 226 locales from a transparent composite
of the complete broad run and successful targeted reruns: 1,511 successful unique
cases and three explicit skips. The isolated courseware gate passes 633 tests
(one skip) at 89.30% coverage. Rebuilt native and written host course/package checks
pass 75 tests (three skips); the environment-dependent rerun passes 28. Earlier
failures remain saved; this is not described as one fresh all-test run. Package
source parity is checked separately. Full receipts are in
`outputs/vera-esg-course/release-check-evidence.json`. No merge, deployment, Marketplace publication, installed-host, live
learner/native voice/window, independent professional or real-client acceptance
is claimed by this document. The six-stage guide targets 390 seconds; complete
processing and practice may take longer. No measured learner duration is claimed.

The ordinary function supports selected bounded CSV/text evidence, provenance,
versions, decisions and partial Markdown/JSON drafts. It provides no complete
VSME/ESRS report, taxonomy calculations, metric calculation or assurance opinion.
Actual model reads must follow the normal Vera model-data reporting contract.
Local files do not guarantee local model inference or automatic anonymisation.

## Deployment integration, 2026-10-02

Integrated current main without dropping Fusione, Scissione or studio document format lessons. The combined catalogue contains 53 kits / 241 locales. Rebuilt all product packages from the reconciled source. Publishing remains prohibited; server deployment is separately authorized.
