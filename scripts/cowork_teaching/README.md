# Written teaching in Cowork

Vera, Clara and Lucia reuse their reviewed prepared courses in a single written
Cowork conversation. The host-specific skill explains the task, invokes the
installed specialist procedure, opens its real output, pauses for questions and
runs a fresh practice attempt. There is no voice setup, second chat, mandatory
interview or automatic onboarding.

## Packaging and source review

`projection.py` is called after each Cowork workflow projection. It first verifies
the canonical course and source hashes, then binds the course to the actual
projected procedure. It includes only courses whose own-product specialist skill
is packaged. Clara's Deck Correction and Transcribe courses therefore remain
absent; the existing hosted-course exclusions also remain. The native course
renderer is reused with the Claude manifest path and written, localized UI copy.
The Codex lesson runtime remains unchanged.

Never edit generated package files. Rebuild with `scripts/build_product_release.py`.
A changed canonical procedure with stale course fingerprints fails the Cowork
build. Changed projected procedure bytes invalidate the installed course at load.
After pipeline updates, review affected lesson content as well as these checks;
a hash does not establish professional correctness.

## Data and persistence review

The helper uses the standard library and no network client. It prepares fictional
files in a fresh user-selected connected folder and creates `lesson-progress.md`.
It does not write the native global onboarding profile or mark a lesson complete.
The teaching skill records real output references and actual user responses there
for resumption; it must inspect those files again before treating work as complete.
Existing destinations are rejected, preserving a paused lesson.

Claude processes chat and files through the user's Anthropic account. A connected
folder is not an offline-processing or host-retention guarantee. No course data,
answers or progress are sent to Mparanza. The skill forbids hosted feedback,
interviews and receipt stamping; Vera's existing directory marker also suppresses
receipt transmission on direct helper retries. Public research required by an
installed procedure retains that procedure's normal boundaries. Real client work
is a separate explicit transition.

## Checks

`tests/plugins/test_cowork_teaching.py` extracts the installable archives and
prepares all supported course/language variants, rejects changed or unavailable
workflows, and verifies pause-file preservation. These checks validate packaging,
prepared materials and runtime boundaries. They do not certify a live human
Cowork lesson or replace each specialist's execution and professional review.
