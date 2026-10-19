# CI and release checks

`plugin-runtime.yml` runs product correctness, file and privacy boundaries,
accounting and reporting regressions, coverage, and code quality for every pull
request and push to `main`. Package/source alignment and the other dedicated
product workflows remain independent release checks.

`teaching-kits.yml` owns lesson execution, local teaching on Linux/macOS/Windows,
course compilation, and editorial acceptance. It runs for changes to authored
course materials, teaching runtime, teaching instructions, or teaching tests.
It can also be run manually with `workflow_dispatch`.

Generated course inventories, product manifests, privacy fingerprints and ZIPs
do not trigger teaching acceptance. For example, a journal parser fix that
refreshes `assets/courses/*/course.json` source hashes runs the product checks
without requiring a new editorial review of the lessons.

Teaching failures block acceptance of the affected teaching materials. They are
not a merge or deployment gate for unrelated product fixes. Do not add the
path-filtered teaching checks as unconditional required checks on `main`, or
make product release jobs depend on them. For teaching changes, report their
actual results; do not suppress errors or manufacture editorial approvals.

The teaching job previously contained general accounting and reporting checks.
Those remain in the normal runtime workflow under `workflow-regressions`.
File identity, privacy reports, update notices and the Journal Sampling to
Vouching handoff remain under `client-file-boundaries` on all three platforms.
