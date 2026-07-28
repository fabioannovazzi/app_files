# Vera Financial Analysis

This Vera workflow establishes the case-level control layer for three
source-bound financial-analysis preparation packs:

- monthly P&L;
- working capital;
- customer concentration.

It validates source identities, dataset semantics, cross-dataset relationships,
reviewed crosswalks, an explicit pack request, reconciliation results, and the
prepared-evidence manifest. It does not infer accounting classifications or
turn prepared evidence into a professional conclusion.

The module includes three runnable v1 recipe engines under `scripts/` and a
single named dispatcher, `scripts/run_pack.py`. The engines preserve the exact
calculation logic and fail-closed behavior of the earlier evaluated preparation
prototypes while emitting Vera-owned reconciliation and evidence-manifest
schemas.
