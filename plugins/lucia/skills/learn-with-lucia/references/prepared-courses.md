# Prepared teaching kits for Lucia

The `comunicazione-professionale` kit starts with a fictional law-firm brief
and an attributed official source. Use Lucia's current communications
workflow in its private studio workspace: draft, independent claim and
editorial review, normal professional review and actual packaging. Practice
adds a covering email to a new version. The supplied brief does not approve
generated text or the proposed studio profile. Do not substitute a client
ledger or send the communication from a tutorial.

The `quesito-legale-fiscale` kit starts with a fictional request for an
informational briefing. Follow Lucia's complete question journey, including
the per-answer research choice and answer validation. Source files are
starting evidence; check their currency. Source language does not determine
answer language or jurisdiction. Practice changes the audience and question
scope. Do not invent an opposing position for this informational request, a
ready-made answer, or completed validation.

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

## Website workspace route

`presenza-digitale-studio` uses `execution.route: local_website_workspace`.
The tutorial adapter stages the selected files and a private output directory;
it does not invent a ledger context for this standalone website specialist.
After the learner selects the fictional material for this website exercise,
initialize the specialist's normal owner-controlled workspace under that output
directory and prepare its intake with all external routes unselected. Follow
the exact current specialist, including the owning product's professional profile.

Build and validate the real local HTML/CSS, review its rendered desktop and phone
versions and record actual screenshots. Do not generate blank screenshots or
claim visual review from a file/dimension check. Local preparation is not
`preview_ready`, `release_ready` or `published` without the actual corresponding
package/reviews. Explain publication using the current procedure; a local lesson
does not select external preview or final publication. Practice updates the local
site in a new run/version, preserving the demonstration and rechecking the new
bytes. Never reuse approvals from the old site.
