# Vera source acquisition acceptance — 6 September 2026

This records T04 source-acquisition behavior and related source identity checks.
It does not certify substantive legal conclusions or complete T17 professional
acceptance. Canonical code is in `plugins/deep-research-validator/scripts/`.

| Boundary | Implemented behavior | Current evidence |
| --- | --- | --- |
| Compressed PDF | Extracts page text instead of interpreting PDF bytes as UTF-8 text | Public source-inspection PDF regression |
| Scanned or mixed PDF | Keeps unreadable/partial coverage explicit; readable pages remain available | Scanned and mixed-page regressions |
| Unsupported encoding or file format | Records unreadable extraction and byte identity when bytes were acquired | Unreadable-source regressions |
| Short HTTP response | Declared Content-Length exceeding captured bytes remains incomplete_response | Socket-backed short HTTP 200 regression |
| HTTP 206 | Records partial_capture and partial_response even below the capture cap | Public 200/206 comparison with a BytesIO socket-layer double; no live TCP claim |
| Missing file or directory supplied as source | Keeps one unreadable source disposition; invents no byte hash | Two public inventory regressions |
| Source outside managed run | Rejects before reading bytes | Public inventory regression with forbidden read spy |
| DNS rebinding | Connects to the validated public numeric address; private rebinding rejected | Public transport regressions with socket-layer doubles; no live TCP claim |
| Case-sensitive source references | Resolves exact URL/path identity without merging /Rule and /rule | Public review-audit regression with both URLs |
| Downstream review | Exposes access status and observed text scope; passage presence does not decide semantic support | Inspected package_validation source observations and existing review tests |

Latest complete component test receipt: 69 tests passed, zero failures/errors/
skips (`/private/tmp/vera-remediation-01a07083/source-short-current.xml`). Node was
explicitly available for MCP cases. Earlier `http-partial-current.xml` had nine
skips and must not be used as complete MCP evidence; its Node-enabled successor
passed all 64 then-existing cases.

The configured plugin Mypy check passes all 20 files. Changed source and test
formatting checks pass. The full Vera privacy register passed after source hash
refresh. These are scoped checks; the wider repository gates are not green.

Codex, Cowork and Platform-upload ZIPs were rebuilt and checked after the latest
source-reference correction. All 18 packaged MCP servers initialized and listed
tools. Exact artifact hashes are retained in
`/private/tmp/vera-remediation-01a07083/source-short-package-hashes.json` and build
output in `source-short-build.log`. An earlier extracted-ZIP execution separately
verified the missing-source disposition; it predates the source-reference fix
and is not evidence of that later change.

The integrated suite started before these edits and remains an in-progress
baseline diagnostic. It cannot substitute for final qualification of a fixed
source snapshot. Current primary-source professional cases, independent outcome
review and supported-host acceptance remain governed by the original T01–T20
handoff. No deployment, merge or publication was performed.
