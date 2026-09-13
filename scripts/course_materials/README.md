# Prepared workflow courses

The native teaching library contains 44 operational workflows: 31 Vera, 9 Clara
and 4 Lucia. There are 200 authored language versions. Each has a fictional
case, a natural request, bounded sources, three method steps, a worked result,
a professional check, a question with a revealable answer, and optional practice.
The six stages target 390 seconds including observation and conversation.
These are pacing targets, not measured voice durations. Setup, computation and
optional real practice are outside the core. No timer ends the user's questions.

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
Hosted Interview and Research Video. The other lessons localize conversation,
case explanation and narrative specimens; they do not promise translation of
machine field names or a new country-specific professional method. Italian
practice examples remain Italian practice in every language. Supplementary
actual outputs retain the language and facts of the specific executed starter.

## Authoring and refresh

1. Read the exact current own-product catalog, specialist, required references
   and code. Internal planners and validators are not separate courses.
2. Edit the appropriate `lessons_<locale>*.json` entries. Translate the whole
   case, preserving numbers, source identities, limits and review state. Model
   judgment, not string matching, determines professional and language quality.
3. Keep `VISUALS` explicitly tied to the displayed result rows and exact authored
   values. Never infer business meaning from headers or translate at runtime.
4. For real starter attachments, execute the real supported helper with synthetic
   data. Store selected source/output files and provenance in that workflow's
   `files/`. Do not copy profiles, simulated understanding, credentials or real
   customer material. A starter is supplementary if its facts differ from the
   primary lesson. An authored specimen is not an execution receipt.
5. After editorial review, build with the repository virtual environment:

   ```bash
   python scripts/course_materials/build_catalog.py
   python scripts/course_materials/build_catalog.py --check
   ```

   The normal build rejects missing/extra workflows and unsupported/missing
   translations. `--check` compares compiled bytes without refreshing them.
   `--authoring-preview` permits temporary incomplete local drafts only.
6. Run course, onboarding, scope, privacy and package checks; inspect the rendered
   pages. Rebuild native ZIPs from source and verify all courses in both Codex and
   ChatGPT upload archives. Verify that all three Cowork archives omit the library.

The compiler records exact method/source and attachment fingerprints. Rebuilding
after a method change is an editorial action, not evidence that the old lesson
is still correct. CI checks current bytes; it does not refresh them automatically.
Installed courses cannot borrow another installation or component. A stale or
retired course cannot be reused until reviewed and rebuilt.

## Runtime and privacy

`local_courses.py list/show/render` is local stdlib-only code. It has no network,
model, API-key, profile-writing, session-completion or telemetry operation.
Rendering creates a fresh directory and does not overwrite notes. HTML uses
bundled fonts, escaped content, a restrictive CSP and no script or external asset.
The prepared pages and voice guide are opened in the existing visible worker
chat while the native voice conversation stays in the teacher chat. The actual
specialist contract still governs requested execution and real practice.

The user speaks through the standard selected OpenAI voice. Content discussed
with that native model follows the host's processing arrangement; local storage
does not mean offline inference. The tutorial adds no Mparanza transport. For
normally hosted workflows, the course reviews a local brief/specimen. A real
hosted assignment uses its ordinary separately selected workflow, not a tutorial
upload. Native teaching and this library are absent from Cowork.

Automated rendering and package tests do not establish native human voice or two
visible desktop windows. That remains a live host acceptance check. Rendering
alone does not complete the mandatory 3–4 onboarding demonstrations/practices or
confirm the user's understanding.
