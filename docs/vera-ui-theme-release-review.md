# Shared Vera workflow theme: release review

Reviewed on 2026-10-29 against main `1437e06f2ad0ea9b21b030303de781799af3bdca`.
The requested change retains the neutral Vouching appearance and centralizes it
in `plugins/_shared/ui/vera-theme.css`.

## Source and data-boundary review

All changed workflow HTML was compared with main after removing its style block:
markup and scripts are identical. The standalone CSS and the browser-record
focus rule change presentation only. The generated widgets retain the latest
Vouching amount and MCP-bridge repairs from main. The theme has no imports,
remote font requests, connectors or model payload builders. Source previews
use the local system font stack; an unused embedded font was omitted from the
New Client style projection.

The package builder applies the same CSS to Vera's self-contained resources and
Vera-only copies of shared courseware before execution-integrity hashes are
computed. Lesson source/index hashes are projected onto those exact shipped UI
bytes while retaining original reviewed hashes; a stale source binding is
rejected, with focused positive and negative regressions. Other products' courseware is not themed. Shared specialist widgets
are included in Clara/Lucia packages, so those products are rebuilt as well.
No model-visible fields, app-private payload fields, tool arguments, recipients,
activation controls, reporting producers or save/apply behavior are changed.
Existing runtime profile and external-boundary descriptions remain applicable;
this is an agent differential engineering review, not human or legal approval.

Every changed-byte privacy fingerprint was compared with the main bytes first;
main's register validated before this diff. Staleness was attributable to the
reviewed CSS/package projection, canonical release identities and derived
metadata. The selected records were then dated/refreshed with the maintained
validator. Generated course JSON was compared recursively excluding SHA256
fields: the changes are only source-hash bindings, without lesson edits. This
also required updating Vera local-onboarding and Lucia prepared-course-files
source bindings. Public contracts are regenerated from those reviewed records.
This does not resolve the separate incomplete measurements in historical runs.

Vera's Geneva skill entrypoint IDs and bytes were checked unchanged. The
catalogue/assessment release binding was updated without new jurisdiction or
professional acceptance claims. Clara 0.1.362 is reserved by existing PR927;
this shared-component release therefore uses Clara 0.1.363, Vera 0.1.522 and
Lucia 0.1.189.

## Validation and recovered preparation blocks

The focused source suite passed all 147 checks. Theme synchronization, Black,
Isort, focused Mypy, Bandit and Geneva catalogue coverage checks passed. CI also
checks central-theme propagation and source synchronization. Package parity,
full required CI and public-download identity are separate release gates.

An initial port script had a test-helper import error; the port was rerun from
the correct package context. Two overlapping test processes initially wrote to
the same temporary log; verification was repeated after files stabilized in a
new log. Removing an unused embedded font required resynchronizing whitespace.
Initial builds stopped at changed source-review fingerprints and stale course
source hashes; these were reviewed/regenerated, not bypassed. A refresh command
used a Vera-only service name on Clara/Lucia and was rejected; their actual
registered records were then resolved with the validator. None of these
preparation attempts establishes a deployed or installed release.

## Rollout boundary

Marketplace publication is not authorized. Website branding, plugin icons and
report/chart styles are outside this workflow theme. Deploying server code and
public archives does not update an existing local installation or already-open
chat. Installed/fresh-session acceptance must be reported separately.
