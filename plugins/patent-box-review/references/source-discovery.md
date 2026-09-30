# Public source discovery and coverage

This adapter is implemented in `scripts/patent_box_sources.py`,
`patent_box/source_acquisition.py` and `patent_box/source_transport.py`.
It is independently testable while the complete Patent Box workflow is unfinished.
It does not activate a rule, authenticate a professional, run a scheduler, send
an external notification or change a client case.

## Host sequence

1. The host model prepares `source-plan.schema.json`: named review, rationale,
   exact public entry URLs/hostnames, authority/topic, search window, byte/page,
   timeout and request-spacing limits. Use public queries only, with no client
   facts or credentials. Choosing domains and legal research scope is model-led.
2. Run `patent_box_sources.py open --plan <selected-json> --output-root <public-sources>`.
   Keep the returned scan directory. The host works with its immutable plan;
   changes require a new scan.
3. Run `acquire --scan <scan> --scope-id <id> --url <entry> --kind LISTING`.
   The result includes observed links. The host reads the original/text and
   decides which links are pagination, candidate documents, navigation or outside
   the declared scope. No keyword classifier decides legal relevance.
4. Follow an observed link using `acquire ... --parent-receipt-id <receipt>`
   and `--kind LISTING` or `DOCUMENT`. A non-entry URL must exist in that exact
   parent's captured links and within the same declared host scope.
5. HTML/text extraction is built in. For PDF or OCR, use the host's existing
   document reader on the retained original; record UTF-8 text with `attach-text
   --scan <scan> --receipt-id <id> --text <selected-text> --extractor <name/version>`.
   This is explicitly a host extraction attestation. It is not cryptographic
   proof that an OCR result is correct. Never install a parser during a case.
6. Prepare `source-coverage-review.schema.json`. Give every observed link a
   reasoned disposition. Select or exclude every acquired document. Preserve
   metadata, publication and effective dates separately, affected periods and
   partial-update relationships as proposals. Do not claim a complete research
   window or pagination without reading the relevant pages.
7. Run `finish --scan <scan> --review <selected-json>`. Failed requests,
   unfetched pages/documents, unsupported listing extraction and unresolved
   dispositions yield `PARTIAL_SCAN`. Successful closure means only
   `COMPLETE_DECLARED_SCOPE`, never exhaustive legal monitoring. This record and
   every original, receipt and text version are preserved; final scans reject edits.
8. Run `compare --before <old-scan> --after <new-scan>`. Different bytes with
   unchanged extracted text still require visual review: figures or layout can
   contain relevant information. Changed text is not automatically changed law.
   Extractor-version changes remain non-comparable. Legal effect stays UNREVIEWED.
9. `impact --before ... --after ... --private-case-index <selected-index>
   --private-output <new-file>` writes the existing conservative review queue.
   The index and output must remain outside public scan directories. Use opaque
   case IDs, and retain the approved case hash. Approved cases receive only a
   reopening proposal; previous decisions and amounts are not overwritten.

## Network and persistence boundary

HTTPS only, exact configured hosts, port 443, no URL credentials, no cookies,
no authorization headers, no inherited HTTP proxy. Every redirect is checked.
All resolved IPs must be public; the TLS connection pins a checked numeric IP
while verifying the original hostname. A separate isolated Python process gives
the complete request a bounded wall-clock lifetime, including DNS and slow reads.
Requests have byte/redirect limits and per-scan minimum spacing. No source content
is executed. These fixed rules exist for security and integrity, not source ranking.

Bandit reports the subprocess import and invocation at low severity. The invoked
program is the running Python executable with `-I` and this bundled transport
file; URL data is a JSON argument, not shell code. No shell is used. Keep these
findings visible; do not weaken the total timeout or disable scanner checks.

Public request URLs and ordinary connection metadata reach the selected source
hosts/DNS resolver. Original public documents, extracted text and review records
remain in the selected local scan directory. The host model can receive the public
texts it reads. The private case index is read only for local impact calculation;
this adapter never sends it to source websites. The host must report actual model
context separately; there is no token-telemetry claim.

## Evidence from 29 September 2026

33 isolated source tests passed, including discovery beyond supplied URLs,
private/mixed DNS rejection, redirects, sizes, timeout, request spacing, preserved
originals/text, partial coverage and controlled reopening proposals. Three changed
source modules passed Mypy; Bandit reported 0 medium/high and 2 low notices.

The actual adapter fetched an official Agenzia delle Entrate information page,
extracted 43 links, followed the newly discovered 2026 Redditi PF instruction links,
and preserved originals and pypdf/6.11.0 text for all three fascicoli. The complete
page-specific scan has no coverage gaps. A separately frozen partial scan retains
its two unfetched-document gaps. These are live acquisition results, not professional
approval, automatic legal classification, full monitor acceptance or release proof.

The host-scheduler coordinator is described in `monitor-service.md`. It is disabled
by default and its tests use synthetic schedule receipts; live host activation and
notification delivery have not been accepted. Professional applicability and
false-positive/false-negative acceptance across the full scope remain required.
