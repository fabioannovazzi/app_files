# Bilancio performance evidence

Evidence recorded on 2026-08-05 with the production deterministic engine and a
synthetic balanced 20,000-row signed-balance CSV.

## Reproducible command

```bash
python scripts/benchmark_performance.py \
  --output-dir <new-empty-output-directory>
```

The runner creates unique source accounts, verifies the source checksum,
executes the actual generic CSV parser, confirms the progressive convention,
applies reviewed mapping records, computes statements twice, proves the two
statement payloads identical after excluding the timestamp, runs the complete
local validation engine, and saves the case plus a checksum-addressed manifest.

## Observed run

- Environment: Python 3.12.13, macOS 26.5.2 arm64.
- Rows: 20,000.
- Source size: 850,111 bytes.
- Source SHA-256:
  `407a1767e6a8b681dac5bb7da4e83f3eee474f57577fe2b6e7950a3ee8943eb6`.
- Parse: 2.5224 seconds; target 60 seconds; `PASS`.
- Mapping application: 1.7611 seconds; recorded without a separate target.
- Statement recomputation: 3.2057 seconds; target 10 seconds; `PASS`.
- Deterministic repeat: 3.3514 seconds; matching statement SHA-256
  `e016a6b520d9c3e75cd08501bc8132f710975e1ebb38097251990b9778971f1b`.
- Local validation: 2.1589 seconds; target 60 seconds; `PASS` for execution
  time. The deliberately incomplete synthetic case correctly returned a domain
  validation result of `FAIL`; performance success does not convert blockers
  into accounting acceptance.
- Evidence manifest SHA-256:
  `cfddd7f35bf5a0930e8fa66eed63779629ccc60065c5a31b5afe85a2f249b841`.

The run exposed and closed a quadratic audit-hashing path: mapping decisions
now calculate the immutable post-mutation hash once and reuse it across the
per-account audit events. Tests prove every event retains the same exact
post-mutation hash and only the first event carries the prior-state hash.

## Remaining boundary

This is one controlled local-machine result, not a production SLO or capacity
guarantee. The 120-second provider-backed narrative target and keyboard/screen-
reader-responsive 10,000-row production review grid remain unmeasured because
the production model route and structured workflow UI are not deployed.
