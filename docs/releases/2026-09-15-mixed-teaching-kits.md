# Interim teaching-kit release

The owner authorized 34 completed prepared kits and the existing published
lessons for 11 deferred replacements. The explicit selection lives in
`scripts/course_materials/release_plan.json`. Draft authoring remains available
for next week. No goal or automatic continuation was created.

The catalogue contains 45 owning-product entries and 205 language versions:
34 new kits / 162 versions and 11 retained lessons / 43 versions. Counts include
supporting intake tasks and shared workflows under each owning product.
Clara Brand Fit, Hosted Interview and Research Video remain unavailable locally.

`static/shared/courses/index.html` links every lesson and fictional input. All
three Impara process pages link to their product section. Shared fonts and CSS
are stored once. Public provenance contains no local execution requests or
absolute session paths. The underlying lessons remain local in the plugin;
profiles and progress are not published.

Both formats require live execution in the working chat while the native voice
chat explains and answers questions. Prepared files, including renamed copies
of retained specimens, cannot establish execution completion. Optional onboarding
from current main is preserved; ordinary work never waits for a tutorial.

## Release evidence

- `teaching-mixed-native-50.xml`: 366 passes and 32 conditional skips for deferred
  replacement exercises. All 324 required demo/practice cases for the 34 new kits
  are present, successful and bound to current course hashes.
- `verify_release.py`: 34 reviewed kits and 162 reviewed locales. Authored content
  and input bytes match the previously reviewed commit `312b51de`; original
  editorial/artifact reviews are retained with a separately attributed source
  integration refresh.
- The 43 retained lesson variants render and preserve the pinned published
  course content. The public catalogue has 205 linked pages with valid local
  links and no execution requests or absolute session paths.
- Browser policy blocked catalogue preview. Visual inspection of that catalogue,
  native voice and a live learner using paired windows remain unverified.

Final portability validation: all 324 required native cases passed again in
`teaching-mixed-native-64.xml` (365 successful tests, 32 deferred skips). A single
package/source comparison ran while the package was rebuilding and was rerun
successfully in `teaching-package-retest-66.xml`. The explicitly combined receipt
`teaching-mixed-native-66-composite.xml` retains those native results and replaces
only that one package check; the release gate passes 34 kits/162 locales.
Additional state checks passed (94 tests). Windows CI prompted real link-count
inspection with `os.lstat`, consistent stored path separators, a portable test
interpreter selection, and a local report typing correction. No authored lesson
content changed during those fixes. The final release must pass Windows CI too.

## Source and privacy review

Current main through `07689c38` was integrated, retaining its runtime, optional
onboarding, DATEV and ECONS updates. Reviewed teaching-workflow changes concern
local document/table rendering, language labels, checked output presentation,
reviewed client-email replacement and communication subjects. Existing source
mapping, independent/professional reviews, input/output hashes and transmission
boundaries remain required. The variance arithmetic repairs preserve signed
residual contributions; missing New Client risk scores remain unassessed rather
than being filled with sample values.

The reporting changes display already supplied source facts, source links,
review statuses and checked numeric cells. Report Builder's record now describes
its bounded reviewed numeric previews. Bandi's record distinguishes a model
reading the complete local dossier from its task-specific context packet.
Clara source maps may include local paths when read by the model. Mixed-course
privacy records describe prepared-file fingerprints, host-attested local
execution and the fictional public catalogue. No new teaching server, voice API,
feedback transport or profile synchronization service was added.

## Verified deployment

PR #640 merged as `306101b56ff88bb321068f3e7ae4161172fd17bb` on
2026-09-15 after all 29 required checks passed on `e217880d`. The final full
teaching job is GitHub Actions job `104363209802` in run `34963745313`.
Its multilingual lesson stage passed 815 tests, with 90 explicit conditional
skips; the release gate verified all 34 prepared kits / 162 locales. The
remaining integration, coverage, compiler and code-quality stages passed too.

Windows job `104363209881` passed 24 exact-file-capture checks, the real Vouching
example, 150 Vera lifecycle checks (two conditional skips), and 168 shared
Clara/Lucia teaching checks. Both measured lifecycle groups reached 88% coverage.
Vouching retains exact binary reads, hard-link rejection and mutation checks;
ctime is compared within the same filesystem API because Windows pathname and
descriptor APIs expose different ctime semantics. The complete Windows job has
a 30-minute limit; an earlier run had reached the former ten-minute limit.
An earlier full-suite run also hit a ten-second Concordato test deadline; the
unchanged test passed locally and the final complete CI run passed unchanged.

The server was updated through Git and restarted on the merged commit. Its
checkout was clean and Uvicorn was running. All 13 checked public files returned
HTTP 200 and matched the reviewed SHA-256: catalogue HTML/CSS, shared process-page
JavaScript, version registry, all three Impara wrappers, representative lessons
for every product, and all three Cowork downloads.

Catalogue: https://mparanza.com/static/shared/courses/index.html

Deployed canonical packages: Vera 0.1.258, Clara 0.1.208, Lucia 0.1.50.
Marketplace publication is recorded separately in `marketplace-publications.json`
only after the authoritative version list shows the exact version Published.

Clara 0.1.208 and Lucia 0.1.50 were directly verified Published on 2026-09-15.
The shared registry now advertises Clara 0.1.208. Its governed privacy
fingerprint and generated packages were refreshed; all package drift checks
passed, followed by 67 focused publication/package tests (one unavailable-cache
skip). The ledger preserves the exact uploaded hashes before this refresh.

Vera 0.1.258 is deployed and packaged but is not claimed Published. Its final
upload was blocked by automatic approval review of the browser upload controls;
the requested narrow approval remains pending. The complete archive is retained
at `/private/tmp/teaching-marketplace-final/vera-chatgpt-upload.zip`, SHA-256
`79eb655c7b9ef7e3ccc4b4ee74cf826d76ef209eb2c13ebe190e54b1f239b36f`.
The previous Vera 0.1.257 publication record remains unchanged.
