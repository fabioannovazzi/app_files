# Course HTML browser preview — review candidate

Date: 2026-09-17. Base: `6764372eff1bc77494b951592fa9b5ba0ba7153f`.

The teaching instructions asked the worker to open `course.html` without choosing
an HTML browser surface. During the reported Vera 0.1.258 voice lesson, the file
panel showed unreadable content; the learner confirmed that a loopback HTTP
browser preview rendered correctly. An `open_in_codex` response of `queued` did
not prove that the learner could see the page.

## Change

- `local_courses.py serve --output-dir <rendered-kit>` now serves the kit on
  `127.0.0.1`, using an OS-selected free port. Its JSON readiness record supplies
  the exact URL and explicitly says the browser has not been requested.
- CSS, fonts and linked inputs retain their relative paths. Resolved paths
  outside the kit and directory inventories are rejected. The process remains
  attached to the managed terminal and stops on interruption.
- The canonical teaching skills require a browser target, with available browser
  controls or a clickable HTTP link as fallbacks. They distinguish queued,
  opened and confirmed visibility and specify process lifetime and handoff.
- Clara and Lucia use the same library and had the same ambiguous instruction,
  so the same bounded correction applies to their native teaching paths.
- Course source fingerprints and privacy records were regenerated. The test
  setup restores the vendor import path after repository test isolation so that
  retained lessons can resolve their lazy imports.

Candidate versions: Vera 0.1.265, Clara 0.1.210, Lucia 0.1.51. The one open release
PR (#641) proposed Vera 0.1.263 when checked. These are local review candidates,
not published versions; recheck release ordering before any eventual publication.
Codex, ChatGPT-upload and Cowork packages were rebuilt from source. Cowork still
excludes native teaching. Public published-version announcements were not changed.

## Verification

- Loopback integration tests: 9 passed, including independent ports, HTML/CSS,
  font/input responses, directory rejection and symlink escape rejection.
- Prepared course tests: 291 passed.
- Native archive, retained/public course, general package, update notification
  and icon suites: 455 passed, 1 skipped, 4 deprecation warnings.
- Codex and Cowork package parity: all three products passed.
- Catalog checks: 45 workflows, 205 localized kits, no missing translations;
  public catalog check passed for 1,693 files.
- Black and Isort checks passed for changed Python files; `git diff --check`
  passed. The full repository test/coverage gate was not run for this draft.
- A fresh Italian `fatture-xml-check` kit was rendered under
  `/private/tmp/mparanza-course-preview-review/kit`, served through the new CLI,
  and inspected in the Codex in-app browser. The screenshot showed the styled,
  readable lesson and the accessibility tree included the relative XML links.
  This proves the tested browser rendering, not another user's visibility.
  The temporary tab and its server were closed after verification.

No installed plugin, original lesson material or process on port 8769 was edited
or stopped. No onboarding-profile change, merge, deployment, publication, commit
or PR creation was performed. The requested reviewable changes remain in this
worktree. Existing branch/worktree cleanup was outside this task.

Final inventory: 3 local branches, 2 remote branches excluding `origin/HEAD`,
4 registered worktrees, 0 stashes. No branch or extra worktree was created by this
task. The originating teaching task was archived when the progress message was
attempted, and the app rejected delivery.

## Deployment follow-up

Fabio authorized deployment on 2026-09-17 and explicitly excluded Marketplace
publication because publishing is broken. Rebased onto origin/main 19399a8c;
release candidates are Vera 0.1.267, Clara 0.1.210 and Lucia 0.1.52.
The public published-version registry remains unchanged.
