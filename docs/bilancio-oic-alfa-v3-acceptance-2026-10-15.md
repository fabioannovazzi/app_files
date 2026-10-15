# Bilancio OIC: Alfa v3 acceptance, 15 October 2026

The candidate is Vera **0.1.394**, with Bilancio component **0.1.20**. The
contributor's original synthetic files are retained byte for byte under
`tests/fixtures/bilancio_alfa_v3`; local Git attributes preserve their original
line endings. Provenance identifies the Discord message and original ZIP hash.

## Observed results

The full case passed **131/131 checks** through the stdio MCP server and Python
bridge extracted from the rebuilt Vera ZIP, using the normal persistent,
authenticated `CaseService` boundary. Reviewer P1 and preparer C1 are explicitly
simulated test identities. Every component Python script in that extracted
package matched its repository source hash.

| Case | Expected | Observed |
| --- | --- | --- |
| Document 01 | Debit/credit 807,800; comparative 727,200 | Exact match; missing closing entries remain a professional screening decision |
| Document 10 | Baseline + A1 + A2; 820,800; pre-tax result 48,600 | Exact per-account match and professional screening before form/mapping |
| E1, document 13 | Reject balanced unauthorized changes of 500 to receivables and revenue | Candidate retained; screening rejected atomically; original accounts and decisions retained |
| 20–22 January | A2 still effective but under reconsideration; affected checks suspended | A2 requires review; A1 remains valid; three areas, two mappings and overall validation remain suspended |
| After A2-bis, before document 12 | A2 replaced; reconsideration closed; dependent validations still suspended | Exact match; closing the decision review does not resume the validations |
| E2, document 14 | Reject A2 and A2-bis counted together; excess 1,000 on interest and accruals | Screening rejected; no D-SCR3; suspension unchanged |
| Document 12 | Baseline + A1 + A2-bis; 820,925; pre-tax result 48,475 | Exact match; D-SCR3 recorded; affected controls require repetition |
| Final state | Taxes and litigation remain open; no complete accounts | Existing validation remains blocked; no approval or export |

The register has 12 records on 22 January and 13 after D-SCR3. Earlier records
remain identical; current states are projections from later events. Tests also
check the exact event order, effective dates, authors/roles, documentary links,
proposal/version integrity, save/reopen, reviewer-only authority, distinct
preparer/approver, unchanged comparatives and account identity after row reorder.
Unchanged account mappings survive replacement; changed mappings need review.

The broader Bilancio suite passed **447 tests**, including all four existing
Italian/English course demonstration/practice cases, with **86.03%** coverage
over the declared Bilancio coverage scope. The closing module reached **88%**
in that run. All **17 mandatory implementation-review probes** passed. Black,
Isort, Mypy and the medium/high Bandit gate passed for the changed implementation.

## Reproduce

Activate the repository's Python environment, then run:

```sh
python scripts/run_bilancio_alfa_v3_acceptance.py \
  --transport mcp --output /private/tmp/alfa-v3-new-run
```

To test a generated package, safely extract its Vera tree and add
`--plugin-root <extracted-vera>/modules/bilancio-xbrl-it`. Use a fresh output
directory. The runner retains `acceptance.json`, a readable Italian comparison,
execution trace, checkpoint cases and hashes for every input. The MCP fixture
scanner accepts only the exact synthetic fixture hashes; it is explicitly not
a production malware assessment.

The JSON distinguishes observed behavior from scenario inputs and scope text.
The supplied professional decisions are not evidence of model interpretation
quality. The existing course now explicitly states that it starts from supplied
closing balances; it does not replace the separate Alfa adjustment test.

## Limits and unrelated baseline findings

This is source and packaged-MCP acceptance. The already-open chat, enabled
installation, native UI, real-client work, professional approval and external
filing have not been qualified by this run. Alfa deliberately leaves tax
computation, provision recognition, prior-XBRL reconciliation and notes outside
its scope. No client request or accounting posting is sent automatically.

Additional manual checks exposed three unrelated failures in unchanged main
inputs: the Studio Archive privacy manifest contains `workflow_conditions`
outside its published JSON schema, and the Second Brain integration link/page
fails two product-directory architecture assertions. These are separate from
the passing Bilancio, privacy-fingerprint and package gates; this change does
not modify those baseline inputs.

The Italian non-technical announcement was posted and read back at
<https://discord.com/channels/1550191335917625474/1560040735871336458/1560328362734391407>.
Marketplace publication is outside this implementation.

## Shared Clara fingerprint alignment

CI detected two Clara reviews whose governed paths include the shared product
page and course-material tree. Reviewed changes are limited to Bilancio model-data
copy and the Vera lesson scope/release bindings; Clara teaching and hosted voice
processing, access and retention source are unchanged. The two source fingerprints
were refreshed after that comparison. Clara packages are rebuilt together at
0.1.289 to retain source/package parity. Two further Clara fingerprints bind
the canonical manifest and are refreshed only for that patch-version change;
no Clara runtime behavior changes.

The release catalogue is rebound from Vera 0.1.393 to 0.1.394 after comparing
all 55 function IDs and entrypoint hashes. Only the existing `bilancio-oic`
entrypoint changed. The Geneva assessment retains its prior dispositions and
records the new work as Italian OIC acceptance only; it establishes no new
Swiss-framework or Geneva professional qualification.

The four generated public lesson files for Italian and English are rebuilt from
the same authored Bilancio scope and pass `build_public_catalog.py --check`.
Only the related onboarding privacy fingerprints are refreshed; lesson inputs,
worked outputs and Bilancio runtime behavior are unchanged.

The subsequent course-compiler formatting, typing and security commands pass
locally. The final four CI test groups also pass locally: Concordato 136 tests
at 89.75% coverage, Registry 61 at 85.82%, website evidence 71 at 80.65%, and
matter opening 13 at 83.63%. The full fresh native JUnit release verification
remains a CI gate; no replacement execution evidence is manufactured.
