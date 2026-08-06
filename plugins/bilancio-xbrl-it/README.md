# Bilancio intelligente

Vera specialist module for making the existing preparation of individual
Italian OIC annual accounts intelligent. Vera participates across source
understanding, mapping, ambiguity recognition, missing-information requests,
prior-year reuse, schedule and note preparation, inconsistency resolution, and
professional review. Exact arithmetic, statutory rules, reconciliations, and
XBRL rendering remain deterministic and auditable.

`bilancio-xbrl-it` is the stable internal technical identifier. XBRL is one
export adapter for the approved canonical bilancio; it is not the product
identity or the intelligence layer. See the skill references for the fixed
product thesis and current implementation evidence.

## Controlled service configuration

The MCP bridge fails closed unless the host provides authenticated tenant,
actor, role, and storage settings. Imports and returned external reports are
read only below `VERA_XBRL_INPUT_ROOT`; the model cannot choose an arbitrary
host path. The official taxonomy inputs are deployment configuration rather
than request fields:

- `VERA_XBRL_STORAGE_ROOT`
- `VERA_XBRL_INPUT_ROOT`
- `VERA_XBRL_TENANT_ID`
- `VERA_XBRL_ACTOR_ID`
- `VERA_XBRL_ROLES`
- `VERA_XBRL_TAXONOMY_CATALOGUE`
- `VERA_XBRL_TAXONOMY_PACKAGE`
- `VERA_XBRL_TAXONOMY_REGISTRY`
- `VERA_XBRL_STATUTORY_RULE_PACK` (optional host override; the bundled
  effective-dated form pack is the default)
- `VERA_XBRL_DISCLOSURE_RULE_PACK` (optional host override; the bundled
  effective-dated disclosure pack is the default)
- `VERA_XBRL_STATUTORY_PRESENTATION_RULE_PACK` (optional host override; the
  bundled versioned pack is the default)
- `VERA_XBRL_SCHEDULE_TAXONOMY_RULE_PACK` (optional host override; the bundled
  effective-dated note-table adapter pack is the default)
- `VERA_XBRL_SCANNER_COMMAND_JSON`
- `VERA_XBRL_SCANNER_ENGINE`
- `VERA_XBRL_SCANNER_SIGNATURE_VERSION`
- `VERA_XBRL_ARTIFACT_SIGNING_SECRET`
- `VERA_XBRL_ARTIFACT_DOWNLOAD_BASE_URL`
- `VERA_XBRL_RETENTION_DAYS`
- `VERA_XBRL_INTELLIGENCE_COMMAND_JSON`
- `VERA_XBRL_INTELLIGENCE_TIMEOUT_SECONDS`

The configured catalogue and package are required for the pre-approval local
XBRL review. The catalogue alone is required for export. TEBENI remains a
separate, user-controlled external check.

Conversational and background-worker file ingestion requires a host scanner
command encoded as a JSON argument array. Vera appends the controlled absolute
file path as one argument, never invokes a shell, and proceeds only after a
clean verdict; the scanner engine and signature version are stored in a receipt
bound to the imported document checksum. Production must supply a real scanner;
the library-level injection seam exists so tests can exercise clean and rejected
verdicts without external infrastructure.

When both artifact-delivery settings are present, a reviewer or read-only
auditor may issue an idempotent 30–900 second download grant. The bearer token is
HMAC-signed, contains no storage path, is bound to tenant, case, file and
approved checksum, requires canonical Base64URL encoding, and rechecks the
artifact before returning bytes. Grant and redemption events enter the case
audit trail. The signing secret must be held by the deployment secrets service,
not committed or sent to a model.

No retention duration is assumed. When the host supplies an explicit value from
1 to 3,650 days, a studio administrator may archive a case with a reason. The
approved snapshot and artifacts remain intact and downloadable during that
window. Deletion is studio-admin-only, revision-bound, and rejected before the
recorded cutoff; after the cutoff it purges the exact tenant/case directory and
leaves a checksum-protected, idempotent tombstone containing hashes and deletion
accountability rather than source content.

The canonical `case.json` is written with `case.json.sha256` and is never read
before that sidecar verifies. A missing, malformed, mismatched, or symlinked
record/checksum pair fails closed instead of allowing a partially written or
tampered case to enter a new mutation.

Every case locks its statutory, OIC, filing-instruction, disclosure, and
taxonomy versions. Statutory, disclosure, presentation, and schedule-taxonomy
packs on the MCP and HTTP surfaces come only from deployment configuration;
request-selected packs are rejected.
A non-first-year case must provide the exact comparative start and end dates;
the renderer does not infer a conventional prior year. The selected OIC pack
adds its effective professional-review questions to the live questionnaire and
workpaper rather than acting as metadata only.
A different pack cannot be passed silently to an existing case. A studio
administrator may explicitly migrate an open case through
`migrate_regulatory_versions` (or the
`/regulatory-migrations` HTTP resource). Migration targets are controlled pack
identifiers, never caller-supplied rule-pack objects. The migration verifies
effective dates and checksums, produces a bounded change report, retains source evidence,
invalidates every regulated derived output, and requires full recomputation and
revalidation. Approved, exported, archived, and unsupported cases cannot be
migrated.

Major parser, eligibility, mapping-candidate, statement, schedule, disclosure,
note, intelligence, preview, validation, and local-XBRL outputs carry a common
computation context: case/revision, input-manifest hash, mapping hash, locked
rule versions, regulatory pack checksums, filing campaign, taxonomy checksum,
model/template version, and time. This is lineage metadata; it does not make
semantic classifications authoritative.

Before validation, the case state is derived from controlled coverage rather
than conversational judgment: missing or unreconciled structured schedules and
answers produce `DATA_GAPS`; once those are complete, the case moves to
`NOTE_DRAFT`. Missing narrative remains visible as note work and is not
misreported as missing accounting evidence.

Every complete non-cash schedule entering an official-taxonomy workflow must
also pass `record-schedule-taxonomy-adapter`. The professional binds schedule
cells to concepts below the configured official note-table roots. Vera derives
the output value from those exact cells, reconciles reused primary facts,
rejects concepts outside the table, and requires every remaining cell to carry
an explicit reviewed omission reason. A table policy cannot omit every cell.
The payable template includes a separately evidenced `secured_amount`, which
must be from zero through the row closing balance.

Cases default to Italian output (`output_language: "it"`) and may explicitly
select English (`"en"`). Accepted narrative blocks and taxonomy text facts must
all use that one case language; mixed-language approved output is rejected, and
rendered XBRL text facts carry the matching `xml:lang`. The comparative HTML
preview uses semantic regions, labelled tables, a skip link, visible keyboard
focus, and keyboard-scrollable table regions. These controls do not replace
production UI accessibility and screen-reader verification.

## Revision-bound background work

Vera may enqueue the declared long-running case operations through
`xbrl_case_enqueue_job` and inspect them through `xbrl_case_job_get`. The job
identifier is the queue idempotency key. Each record is checksum-verified,
tenant-scoped, and bound to the exact source `revision_id`; a result cannot be
applied after a newer case revision exists.

Execution is deliberately absent from the conversational tool surface. A host
worker with the internal `SERVICE_WORKER` role runs one queued item with:

```bash
python scripts/run_background_job.py \
  --storage-root <controlled-storage-root> \
  --tenant-id <tenant-id> \
  --case-id <case-id> \
  --job-id <job-id> \
  [--input-root <controlled-input-root>] \
  [--taxonomy-catalogue <catalogue.json>] \
  [--taxonomy-package <official-taxonomy.zip>] \
  [--taxonomy-registry <registry.json>] \
  [--intelligence-command-json '<json-argument-array>']
```

A failed attempt does not mutate the case. A replay uses the existing mutation
idempotency ledger, including recovery when the case mutation completed before
the worker could mark the job successful.

`taxonomy_catalogue_build` accepts no request-selected paths or entry points;
the worker reads the deployment-controlled registry and package, verifies both
against the case lock, and stores a checksum-bound case catalogue receipt.
`invoke_intelligence` accepts only a task and subject identifiers. It builds the
minimum-context packet from the submitted revision, calls the host command over
JSON stdin without a shell, stores the exact response inside the protected job
for retry recovery, and applies it only if the revision still matches. A
concurrent professional edit makes the result `STALE`, and a successful result
remains `MODEL_SUGGESTED`.

## Professional review data contracts

`xbrl_case_get_review_view` exposes the ten specification review surfaces:
case dashboard, source review, mapping grid, statements, schedules,
questionnaire, notes editor, issues panel, preview, and approval/export.
Account-, anchor-, fact-, schedule-, question-, and issue-heavy views are
bounded to at most 500 items per request and include explicit pagination
metadata. The approval view never returns the immutable snapshot payload, and
preview/export views return resource identifiers and checksums rather than file
bytes or arbitrary host paths.

Approved export writes the XBRL instance, accessible HTML preview, standalone
mapping, issue, and validation reports, the complete workpaper, and a final
checksum manifest. The workpaper embeds the checksums of every peer artifact;
its own checksum and the manifest checksum remain in the final manifest to
avoid recursive self-hashing.

## Optional HTTP adapter

`scripts/http_api.py` exposes the section 18 REST resources around the same
`CaseService`. It is optional and declares its extra dependency separately in
`api-requirements.txt`; normal Vera/MCP operation does not require FastAPI.

The host must place an authenticated `RequestContext` in
`request.state.vera_request_context` or inject an equivalent trusted provider
when constructing the app. Tenant or role headers and JSON fields are never
accepted as authentication. Every mutating route requires `Idempotency-Key`;
every post-creation mutation also requires the current `revision_id` in
`If-Match`. Stale mutations return HTTP 409.

## Controlled taxonomy regression

Run the checked-in 24-case synthetic suite with:

```bash
python scripts/run_golden_cases.py \
  --catalogue <generated-catalogue.json> \
  --taxonomy-package <official-taxonomy.zip> \
  --output-dir <new-empty-output-directory>
```

The runner verifies checksums, renders twenty scenario instances, validates
them with offline Arelle, exercises four guarded boundary cases, and writes an
artifact manifest. Each XBRL case traverses the public create, ingest, parser,
form, mapping, statement, presentation, schedule, schedule-taxonomy, disclosure,
narrative, validation, local-XBRL-review, approval, and export lifecycle. It does not
transmit files to TEBENI.

The scenario suite is complemented by a complete primary-presentation audit:

```bash
python scripts/audit_statutory_presentation.py \
  --catalogue <generated-catalogue.json> \
  --rule-pack rulepacks/it/statutory-presentation-2026.1.json \
  --taxonomy-package <official-taxonomy.zip> \
  --instance-output-dir <new-empty-output-directory> \
  --output <audit-report.json>
```

For ordinary, abbreviated, and micro forms, this derives the exact required
leaf and total inventories from the official presentation/calculation networks,
applies explicit controlled zero confirmations, renders every resolved primary
fact, and requires each instance to pass the pinned offline Arelle validator.
The zero-coverage scenario is structural test evidence only; it is not an
accounting judgment for a real entity.

Audit the selected-form schedule table roots independently with:

```bash
python scripts/audit_schedule_taxonomy.py \
  --catalogue <generated-catalogue.json> \
  --rule-pack rulepacks/it/schedule-taxonomy-2026.1.json \
  --output <audit-report.json>
```

This verifies the effective adapter pack against the official presentation
graph for fixed assets, receivables, payables, equity, provisions, TFR, taxes,
and guarantees/commitments. Reportable item descendants retain their exact
role, root, and tuple path so repeated table rows are not flattened into
duplicate facts. It proves structural concept eligibility, not the professional
classification of an arbitrary client schedule.

## Controlled performance regression

Run the maximum supported synthetic trial balance through the production
parser, mapping, statement, deterministic-repeat, and validation paths with:

```bash
python scripts/benchmark_performance.py \
  --output-dir <new-empty-output-directory>
```

The manifest distinguishes execution-time success from accounting-validation
success and leaves provider-backed narrative latency and production review-grid
responsiveness explicitly unmeasured.

## Official XBRL 2.1 conformance

With the checksum-locked official suite available locally, run:

```bash
python scripts/run_xbrl_conformance.py \
  --suite-package <XBRL-CONF-2025-07-16.zip> \
  --expected-sha256 00462b833fd064108d0781c601bf2b186db9b85ef950030df9db3ef2f68455e9 \
  --output-dir <new-empty-output-directory>
```

The same `--calc xbrl21` mode is mandatory in the production local validator.
The official suite and its generated reports remain controlled run inputs and
outputs rather than bundled plugin files.
