# Vera Financial Analysis

This Vera workflow establishes the case-level control layer for nine runnable
financial-analysis packs.

Accounting and planning preparation:

- monthly P&L;
- working capital;
- customer concentration;
- reviewed Actual-to-Plan sales scenarios.

Fixed financial due-diligence calculations:

- Quality of Earnings and adjusted EBITDA;
- net debt and reviewed debt-like classifications;
- normalized working capital and the selected target;
- Capex by reviewed measurement basis and classification;
- EBITDA-to-cash and Enterprise-to-Equity bridges.

It validates source identities, dataset semantics, cross-dataset relationships,
reviewed crosswalks, an explicit pack request, reconciliation results, and the
prepared-evidence manifest. The due-diligence recipes run exact calculations
only over reviewed prepared inputs and decisions bound to that contract stack.
They do not infer accounting classifications, assume fixed reporting years,
or turn prepared evidence into a professional conclusion.

FDD monetary inputs and calculated outputs are canonical Decimal strings
limited to 38 digits and six decimal places; out-of-domain results fail closed
rather than being rounded. A selected working-capital target includes an explicit reviewed
economic-effect identity, so its contribution remains traceable in downstream
bridge receipts even when there is no separate normalization adjustment.

The module exposes nine registered recipes through the single named
dispatcher `scripts/run_pack.py`. The engines preserve the exact
calculation logic and fail-closed behavior of the evaluated preparation
workflows while emitting Vera-owned reconciliation and evidence-manifest
schemas. A due-diligence result keeps `source_tie_out.status=not_assessed` and
every prepared-evidence manifest keeps `report_ready=false`.

The `sales_plan` recipe applies reviewed unit, price, gross-sales, discount,
COGS, and FX-rate assumptions to a canonical monthly sales dataset. It keeps
conversational interpretation outside the calculation engine, requires exact
scope and period mappings, rejects ambiguous overlaps or unmatched
assumptions, and emits an Actual/Plan scenario table, assumption ledger,
summary, reconciliation, manifest, and replay receipt. Its v1 time profile
preserves the mapped actual-period shape; it does not forecast demand or infer
assumptions.

Two additional reviewed contracts support the due-diligence workflow:

- a contingent-liability register, anchored to a validated case and reviewed
  evidence and decisions;
- a financial-issue register, linking reviewed issues to evidence, pack
  metrics, owners, open questions, and deal implications.

Both registers keep completeness `not_assessed` and `report_ready=false`.
Validation proves canonical structure, reference closure, and reproducibility;
it does not prove that every liability or issue has been found.
