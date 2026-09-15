# Prepared teaching kits for Clara

## Read the installed lesson format first

This interim release combines new prepared teaching kits with retained published
lessons. The workflow-specific notes below describe the new kit format only.
Check `show` before using them: `mparanza.teaching_kit.v2` supplies the new
demonstration and practice files; `mparanza.course.v1` supplies its original
`teacher.md`, `case.json`, `input.csv`, `source.md` and optional supporting files.
For a retained lesson, follow its actual outline and inputs with the current
own-product workflow. Do not refer to absent new-kit files or exercises. Its
`example.html` is a prepared specimen, never evidence of the current execution.
Both formats require live execution in the working chat and explanation in the
paired voice chat. Neither rendering nor a specimen completes the lesson.

## New kit instructions

The native package contains one kit per supported teaching entry, with plain
localized titles, a stated purpose, fictional input files, a lesson outline,
checkpoints during execution, a short practice and repeat-use guidance. The
catalogue distinguishes main workflows from supporting tasks. Select relevance
with the native model from this product's own current catalogue.

Use the same installed root returned by the active worker contract:

```text
python scripts/local_courses.py list
python scripts/local_courses.py show --workflow <exact-id> --language <supported-language>
python scripts/local_courses.py render --workflow <exact-id> --language <supported-language> --output-dir <fresh-local-lesson-files>/kit
```

`show` and `render` verify product identity, supported language, input bytes and
current workflow sources. An unavailable language requires a supported choice;
a missing or stale kit needs refresh. Never borrow another product's kit.
`render` preserves an existing destination and writes:

- `course.html`: the first-use guide, with links to real fictional input files;
- `teacher.md`: prepared voice outline and concrete workflow checkpoints;
- `execution-request.json`: exact own-product skill, input paths and teaching
  intentions for the paired worker, explicitly not an execution receipt;
- `files/input/`: the demonstration inputs in the pipeline's supported formats;
- `files/practice/`: inputs for the learner's fresh practice attempt;
- `course-provenance.json`: kit revision, source identity and unexecuted state.

Read the current specialist and all delegated procedures. Prepare the actual
portable tutorial case using the returned `source_files`; keep the original
filenames associated with the bound paths returned by that adapter. Supply only
appropriate files to each helper: a case brief informs model interpretation,
while a tabular calculation receives the bound table, not every file blindly.
Complete required semantic review from the fictional facts without fabricating
professional approval. Execute in the user-visible working chat and return
actual artifacts and status to the voice teacher. The kit creates no final
workflow output, approval, receipt, user answer or completion checkpoint.

Open actual new results as they arrive. Point the learner to the starting section,
the detailed evidence and the useful next action. Use checkpoints at the right
moment and adapt the spoken explanation. The practice uses `practice_files` for a new attempt initiated by the learner.
When the specialist updates an existing case, continue that same teaching case
and preserve the prior run or workpaper; otherwise prepare a fresh teaching
case. Never replace a required predecessor with a fabricated saved result.
Never mark onboarding practice or understanding from an automated fixture test.

A custom example is allowed when helpful: state the changed facts, use valid
inputs for the same own-product workflow and execute it afresh. If a required
host capability is missing, state which step is pending. A local preparation of
a hosted workflow is a preparation step, not a completed hosted demonstration.

The helper uses local file operations only. Profile, progress and tutorial files
are not sent to Mparanza; native OpenAI voice/model processing still applies to
what is discussed or read in chat. Cowork excludes this native teaching system.

Release checks validate kit files and source currency and run relevant pipeline
checks from the packaged kit inputs. Editorial review asks whether a beginner
can supply files, make the request, recognize progress, use the deliverable and
repeat the workflow. Hashes and successful rendering do not answer that question.

## Assortment report from a supplied package

The Attribute Reporting kit starts with an existing fictional evidence package
and a short brief. It teaches the current supported local package-to-report
path. Explain what the supplied assortment, new-arrival and best-seller groups
mean, then use the native safe extraction, intake, evidence tables, model-led
narrative, rendering, independent semantic review and browser checks. Open the
new report and its correctness verdict. Explain the conclusion, the supporting
comparison and the next useful question; then repeat with the practice package.

Preserve the ZIP's internal filenames when the tutorial adapter copies the
archive to a bound input path. The archive contains source comparisons computed
by the current native package builder, not a completed report. The products and
cohorts are expressly fictional, with no sales quantities, images or consumer
reviews. Do not describe them as observed retailer data. This local lesson does
not perform a fresh scrape, central mapping, hosted package build or Brand Fit
analysis. Those require their own current workflow and chosen data path.

## Presentations and corrections

`html-deck` starts from the ordinary workshop brief and teaches a standalone
internal talk, not an advisory case or a quantitative report. Read the current
HTML Deck skill, author the storyline and speaker notes, compose through the
registered layouts, build and run static and browser QA. Open the actual
presentation and demonstrate arrows and notes. The exercise adapts the talk
for new colleagues using the supplied example; preserve the first output.
These qualitative notes do not justify adding savings, percentages or charts.

`deck-correction` supplies an existing fictional HTML presentation, its editable
work archive and feedback. The original is an input to this workflow, never a
claimed correction result. Open the HTML for the learner; inspect the bound
archive and reconstruct its ordinary work files in the private tutorial folder
without flattening or renaming the internal files. Before extracting, verify
the expected regular file list and reject links or paths outside that folder.
The tutorial adapter's copied filenames are not the internal work structure.

Read and interpret the feedback, inspect the baseline and create the current
hash-bound revision map before editing a copy. Update the affected content and
its source records; preserve all other slides and source references. Compare,
build, browser-check and visually inspect the actual correction. The demo
changes the proposed intake owner; the independent practice starts from the
original and changes only the closing next step. Neither is professional
approval of the proposed procedure. Use native voice or supplied text here;
do not launch hosted voice capture during the local tutorial.

## Business Planning execution

The business-planning kit uses Clara's registered shared Business Planning
workflow. Read the proposal, economics and operating notes; prepare the normal
Clara advisory case workspace, then author the current business-planning case
and run `run_strategic_plan.py`. The tutorial's private working directory alone
is not a complete advisory workspace. Register the actual selected sources and
place the case file at the workspace root and outputs beneath `business-plan`.

Open the actual `business_plan_review.html`. Explain its recommendation,
economic assumptions, sources, missing cash information and next test. Keep
professional reviews pending unless the learner actually supplies them; a
provisional report is not an approved investment or financing decision.

For practice, continue the same workspace and planning case ID. Register the
new operating note and the actual previous `business_plan.json`, reconsider
the carried conclusions and run a new linked cycle in a separate output
directory. The changed vehicle availability does not supply revised volumes,
prices or costs. Preserve the first report and compare what changed in the
recommendation. The learner provides the evidence and question; Clara authors
the technical case and handles its provenance.
