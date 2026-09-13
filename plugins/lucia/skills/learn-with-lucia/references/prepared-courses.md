# Prepared Lucia courses

The course library is bundled with native Codex/local Work teaching only.
Resolve the same installed product root returned by the active worker contract.
There is no network request, runtime model call or remote course fetch.

```bash
python scripts/local_courses.py list
python scripts/local_courses.py show --workflow <exact-current-id> --language <supported-language>
python scripts/local_courses.py render --workflow <exact-current-id> --language <supported-language> --output-dir <fresh-local-lesson-files>/course
```

`list` reports exact IDs, available authored languages and duration. `show` checks
product membership, course identity, content and workflow fingerprints. `render`
performs the same checks and preserves any existing destination rather than
overwriting it. A missing language requires a supported-language selection;
missing or stale source content requires editorial refresh, not silent fallback.

The output includes:

- `course.html`: six short stages, source preview, worked example and answer reveal;
- `example.html`: an inspectable full-page authored specimen;
- `teacher.md`: prepared facts, explanation and listening cues for native voice;
- `case.json`: the declared synthetic facts, not a runtime recipe;
- `course-provenance.json`: source/version identity and explicit non-execution state;
- `files/`, when present: packaged source fixtures or separately evidenced outputs.

Keep the six stages at approximately 45, 60, 75, 90, 75 and 45 seconds. Let the
user inspect the second window and answer the professional-check question before
revealing the worked answer. These are pacing targets, never a timer that stops
questions or claims measured completion. A brief script plus inspection and
conversation makes the lesson; do not read every visible table aloud.

Use the existing local session checkpoint for actual progress. Rendering never
changes onboarding state, grants approvals, records understanding or creates
execution receipts. Keep the same user-visible teacher/worker pair. Select
specific section anchors in the working window as the conversation advances.
The current specialist remains authoritative for real execution and professional
review. Preparation-stage examples of hosted work do not authorize a hosted call.

Course data and personal progress stay local. Native OpenAI voice/model processing
still applies to what the user and assistant discuss or read. The library is
omitted from Cowork packages along with native teaching.
