# Vera Plan

`sales-plan` is Vera's standalone planning workflow. It starts from reviewed
monthly Actual sales and applies only confirmed commercial and FX assumptions
to produce a forward-looking Plan scenario.

The reviewed v2 case contract makes three material choices explicit:

- same-driver overlaps either use the highest reviewed priority or compound all
  reviewed percentage effects;
- explicit discount and COGS assumptions apply either to the Actual amount or
  to the amount after the sales effect;
- sparse Actual grains preserve observed rows without inventing zero-sales
  customer-months.

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
