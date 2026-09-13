> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# XBRL 2.1 conformance evidence

Evidence recorded on 2026-08-05 against the official XBRL International suite
identified by the current XBRL 2.1 specification index.

## Suite lock

- Official index:
  `https://specifications.xbrl.org/work-product-index-group-base-spec-base-spec.html`
- Official package:
  `https://www.xbrl.org/2025/XBRL-CONF-2025-07-16.zip`
- Published suite date: 2025-07-16.
- Package SHA-256:
  `00462b833fd064108d0781c601bf2b186db9b85ef950030df9db3ef2f68455e9`.
- Processor: `arelle-release==2.42.1`.
- Mode: XBRL 2.1 structural and calculation validation, offline.

The repository records this metadata but does not bundle the official suite.

## Reproducible command

```bash
python scripts/run_xbrl_conformance.py \
  --suite-package <controlled/XBRL-CONF-2025-07-16.zip> \
  --expected-sha256 00462b833fd064108d0781c601bf2b186db9b85ef950030df9db3ef2f68455e9 \
  --output-dir <new-empty-output-directory>
```

The runner performs bounded traversal-safe extraction, invokes Arelle with
`--validate --calc xbrl21 --internetConnectivity offline`, parses every
variation result, and checksum-records the report and log.

## Observed result

- Variations: 606.
- Passed: 606.
- Failed: 0.
- Status: `PASS`.
- CSV report SHA-256:
  `413bc110079705aa0c3ed8babe6a9b865ef1f36974c5476e855876c2b9da0af9`.
- Log SHA-256:
  `c7555a3ee21d51c0fd709394d8a62e6a83ec02f90f2ec284cddddc3c1987c665`.
- Manifest SHA-256:
  `4b933dd3652900b15989e2184ea442b749a8dc6dcd5bd503f6e0f3d356bf25cb`.

The initial structural-only run passed 538 variations and failed 68 expected
calculation-inconsistency variations because calculation validation was not
enabled. That observation caused a production correction: Vera's validator now
always requests Arelle's XBRL 2.1 calculation mode. The official rerun then
passed all 606 variations.

This proves the pinned local processor configuration and suite behavior. It
does not prove complete Italian statutory content or TEBENI equivalence; those
remain separate acceptance boundaries.
