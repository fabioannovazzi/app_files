# Prepared teaching kits

Teach the complete first use of a real product workflow: what it does, when to
use it, which files to supply, what to ask, how execution proceeds, what is
delivered, what to review and how to repeat it. Use plain function names. The
kit supplies fictional inputs and a prepared outline; the current pipeline
produces the actual demonstration and practice results in the working chat.
The native voice teacher follows verified progress in the paired teaching chat.

Five to eight minutes is a pacing target for explanation and a short attempt.
Processing and questions can extend it. Select 3–4 relevant onboarding workflows
and personalize pace, explanations and useful example variations. A subsequent
visit starts with the work the user wants to do today. The catalogue is also an
editorial review surface; show purpose and grouping, not an inflated lesson count.

## Inventory and grouping

The deck-correction kit intentionally includes a prepared original presentation
as an input, together with editable source files and feedback. It includes no
corrected result. Edit `presentation_sources/<language>/` and rebuild those
inputs with `python scripts/course_materials/build_presentation_baselines.py`.
This runs the current Clara composer and builder in a temporary directory and
writes reproducible work ZIPs and the original HTML into `inputs/presentations`.
Run its `--check` form during release; a changed deck engine requires rebuilding
and visually reviewing these affected input decks as well as checking lessons.
Never edit the generated ZIPs directly.

`kits.json` explicitly lists exact owning-product workflow IDs. Match the current
own-product catalogue and skill files; never resolve another installed plugin.
Vera’s invoice XML, fiscal-field extraction and client email are supporting
intake tasks under new-client work, and are labelled accordingly. They remain
individually teachable when requested. Internal legal assurance and developer
privacy governance are not main lessons. Shared functions exposed by multiple
products remain bound to each owning product; translations are not workflows.

Clara’s planning, case direction and deliverable review are teachable because
their current specialist contracts accept direct professional requests. They
were omitted by the previous blanket exclusion of planners and validators.
Cross-cutting claim-basis-map remains part of its parent workflow’s explanation.
Studio Archive in Lucia is a supporting lifecycle adapter, not a separate
legal matter-opening workflow. Vera’s explicitly registered archive function
is directly teachable as its own client-workspace journey.

## Concordato source workbook

`concordato_sources.json` contains the localized fictional source narratives.
`build_concordato_inputs.mjs` uses the spreadsheet authoring tool to create the
three-sheet demonstration and updated-practice workbooks. Run a copy in the
spreadsheet skill's temporary dependency workspace, passing the absolute
course-materials directory and a separate preview directory. Review every
sheet and the changed financing assumption. These are source plans, not
precomputed workflow reviews or approved case models.

The author's XLSX exporter omits the optional worksheet dimension element;
the current Concordato reader requires it. After export, run
`python scripts/course_materials/finalize_workbook_dimensions.py scripts/course_materials/inputs/concordato`.
This adds the exact bounds of stored cells while preserving every value,
formula, style and other package part. The regression checks cover that
preservation and idempotence. Keep exporter inspection sidecars in the preview
directory. Recompile kit fingerprints only after this authoring step.

## Language policy and inspected evidence

Conversation language, output language and jurisdiction are distinct. The
library follows the specialist's declared output language where it is narrower
than the product's conversation policy. Website translation is not evidence of
engine support. No locale is translated at teaching time.

| Course scope | Languages | Source of the restriction |
| --- | --- | --- |
| Vera `bilancio-oic` | Italian, English | `plugins/bilancio-xbrl-it/skills/bilancio-oic/SKILL.md`: Italian default, wholly English when explicitly requested |
| Vera and Clara `business-planning` | Italian, English | `plugins/business-planning/scripts/planning_presentation.py`: supported renderer languages `it`, `en` |
| Vera `management-control-pack` | Italian, English | `plugins/management-control-pack/skills/management-control-pack/SKILL.md`: current reporting language contract |
| Vera `centrale-rischi-review` | Italian | Current Italian report in `plugins/centrale-rischi-review/scripts/` |
| Vera `treasury-forecast` | Italian | Current Italian report in `plugins/treasury-forecast/scripts/` |
| Other operational courses | Italian, English, French, German, Spanish | Own specialist narrative, plus product conversation policy in `plugins/vera/skills/vera/SKILL.md`, `plugins/clara/skills/clara/SKILL.md` and `plugins/lucia/skills/lucia/SKILL.md` |

Several specialist contracts explicitly list all five languages, including
journal qualification/reconciliation, Vouching, open-item review, financial
report building, variance, concordato, INPS, SARI, document intake and Clara's
Hosted Interview and Research Video. The other kits localize conversation,
case explanation and live narrative guidance; they do not promise translation of
machine field names or a new country-specific professional method. Italian
practice examples remain Italian practice in every language. Input field names retain the format expected by the actual pipeline.

## Authoring and release checks

1. Inspect the current owning-product specialist and delegated procedures,
   including real intake formats, required review points and expected outputs.
2. Put valid fictional inputs in `inputs/` and declare their exact path, role and
   supported languages in `kits.json`. Supply demonstration and practice inputs.
   Case notes declare meanings and assumptions; they do not pre-approve a recipe.
3. Write `kits_<locale>*.json`: a plain title, purpose, ordinary complete case,
   input explanation, natural request, actual execution steps, deliverables and
   their use, checkpoints during the work, practice, success criteria and repeat
   guidance. Do not author result values or a result page as a substitute for
   execution. Translate the complete outline, preserving the case facts.
4. Run the actual current pipeline from the packaged kit inputs. Inspect its
   artifacts and review whether the outline follows that run and would let a
   first-time user repeat it. Use realistic native evaluation where available;
   fixtures never prove human understanding, native voice or window visibility.
5. Run `python scripts/course_materials/build_catalog.py` after editorial review,
   then `python scripts/course_materials/build_catalog.py --check`. The latter is
   read-only and fails on stale source, input or compiled content. An incomplete
   `--authoring-preview` is for local review only and cannot pass release checks.
6. Run affected kit execution tests, source/isolation/local-state/privacy checks
   and package checks. Rebuild every affected native archive from source. Verify
   exact current source/input bytes in both native formats and Cowork exclusion.
7. With each workflow update, review its affected kit inputs, outline, practice,
   language coverage and execution evidence as part of the release. A successful
   render or hash refresh alone does not constitute editorial review.

The compiler pins method documents, component code, schemas, rule packs,
taxonomy, templates, assets and requirements. It uses the actual package
builder's vendor selection, including overlays, to pin bundled dependencies.
For native product-root helpers it also follows same-directory Python imports. Grouping,
professional meaning and teaching quality remain native-model/editorial work;
the code checks mechanical identity and integrity only.

## Runtime and privacy

`local_courses.py list/show/render` performs local file operations only. It
creates a fresh kit folder containing the guide, voice outline, exact fictional
inputs, a working-thread execution request and provenance marked unexecuted.
It does not write a profile, progress, professional approval or an output specimen.
HTML uses bundled fonts, escaped text and a restrictive CSP.

The worker prepares a real bound tutorial case and reads the current specialist.
It executes one authorized step at a time and returns actual artifacts. The
teacher opens those outputs, explains their use and listens to real answers.
A prepared file or old result cannot complete a demonstration; onboarding also
requires real participation in the practice and confirmed understanding.

Profile, progress and tutorial files stay local, with no Mparanza telemetry.
Native OpenAI voice/model processing still applies to material discussed in chat.
A normally hosted step requires a separately chosen normal professional handoff;
local preparation never counts as its execution. Cowork excludes native teaching.

## Attribute Reporting inputs

`build_attribute_inputs.py` creates the ten fictional existing-package inputs
with the current package builder's comparison and integrity helpers. Run its
`--check` form to compare the exact reproducible archives. The authored product
matrix assigns fictional new-arrival and best-seller groups; it contains no
sales quantities, fresh web collection, central mappings or server receipts.
These are valid inputs to the existing-package report path. The current native
Attribute Reporting pipeline must still author, render and independently review
the report and run its browser checks. The source package is not that result.

## Release review evidence

`verify_release.py --junit <fresh-native-test-report.xml>` runs after the full
compiler check in CI. It requires a separate review in
`release_reviews/<product>/<workflow>.json` for every compiled kit. Rebuilding
the catalogue never writes these reviews. Pin the exact `course.json` SHA-256,
the reviewer and ISO review time. Each supported language needs an accepted
editorial review explaining purpose/first use, files/request, execution and
checkpoints, deliverable/use, practice/repeat and language/pacing.

Each language also records separate demo and practice test identities, an
explanation of the actual result review, and basenames/SHA-256 values of the
artifacts visually or substantively inspected. Retain the actual outputs locally;
do not commit client data or local absolute paths. The review schema is
`mparanza.teaching_release_review.v1`; exact fields are in `verify_release.py`.
Missing, pending, incomplete, stale or foreign reviews block publication.

Native integration tests call `tests.plugins._teaching_release.record_native_check`
only after their actual pipeline/output assertions. The JUnit properties bind
the owning product, workflow, language, phase and current kit hash. A skipped
test, lifecycle-only fixture, prepared output or another product's run cannot
stand in for a native demo/practice execution. The release gate matches the
review's `test_case` to JUnit `classname::name`, and rejects failures and stale
or mismatched bindings. CI creates this report afresh in the runner's temporary
directory; it is not a committed historical test receipt.

These are review attestations and fresh regression evidence, not cryptographic
proof of a human review, native voice quality or learner understanding. Never
generate accepted records merely to satisfy the gate. This rebuild remains
unreleasable until the real output reviews and all required runs are complete.
