# Vera Plan

`sales-plan` is Vera's standalone planning workflow. It starts from reviewed
monthly Actual sales and applies only confirmed commercial and FX assumptions
to produce a forward-looking Plan scenario.

It is not a financial-analysis pack. Historical analysis and financial due
diligence remain in `financial-analysis`.

## Run

```bash
python scripts/check_dependencies.py
python scripts/run_plan.py \
  --case evals/synthetic/case.json \
  --output-dir /private/path/to/plan-output
```

The output directory must be fresh and outside the repository. The normal
package contains the scenario, assumption ledger, summary, reconciliation,
prepared-evidence manifest, and deterministic execution receipt.
