# Packaged renderer dependency finding

Status: corrected after the user's explicit “Yes you can correct”.

Added NumPy, psutil, python-dateutil and xlsxwriter to the five affected
components (Period, Distribution, Mix, Scatter and Set Overlap), including
dependency preflight imports and dateutil package-name mapping. Their vendored
helpers and Excel writer require these imports. Variance already declares them;
Funnel and Statement do not vendor that dependency path. Component versions
were incremented and Clara/Vera packages rebuilt from canonical source.

The two actual extracted-package render tests now pass. Distribution generated
valid PNGs rather than fallback HTML; corrected the test's HTML-only assumption
and decoded/verified both images. The retained small-multiples PNG was directly
inspected: title, panels, axes and legend are visible. Component suite: 311
passes, six conditional skips. Notification/Clara privacy checks: 30 passes.
Codex/Cowork source-drift checks pass for both families; Vera's 18 MCP servers
initialize successfully. No complete T01–T20 acceptance is implied.

Evidence: `corrected-component-render-final.xml`, `component-dependency-tests.xml`
and `dependency-final-notification-privacy.xml` under the evidence directory.
The component suite preceded the final xlsxwriter declaration; the actual
packaged rerun exercises that completed dependency set.

The diagnosis below is retained as history.

The approved network retry is terminal, exit 1. Both extracted-package render
tests fail because `modules.utilities.helpers` imports NumPy inside the new
component-managed interpreter. The component requirements for Period Comparison
and Distribution do not declare NumPy. The broader reporting-engine rendering
requirements are a separate file, owned by reporting-engine.

Correction to the initial diagnosis: this is not simply a missing optional-file
flag on the component launcher. Neither component owns `requirements-render.txt`.
The managed runtime correctly rejects requirement paths outside the selected
component root. Passing that filename or a parent-directory escape would be an
incorrect repair.

The implementation to review is to complete each affected component's declared
dependencies for its actual vendored imports, and update its dependency checker
where applicable. Preserve the managed launch boundary. Do not remove the NumPy
import merely to satisfy tests, install ad hoc packages, or borrow an unrelated
environment. Inspect other component runners reached by the same launcher before
limiting the correction to the two observed failures.

After approval: audit those import/dependency closures, apply only justified
declarations, rebuild canonical packages, and rerun the two normal extracted
render commands plus affected dependency/package checks. Preserve the original
failure evidence and verify material render artifacts, not only exit codes.

Evidence: `clara-source-network-render-check.xml` under
`/private/tmp/vera-remediation-01a07083/`. The Italian professional-review
worksheet remains a separate outstanding input.
