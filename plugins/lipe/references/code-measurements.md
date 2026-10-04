# Recognition and professional-change measurements

These are private local observations, not a tax-accuracy certificate. The model
interprets evidence and proposes a class; the professional confirms or changes
that proposal. Deterministic logic preserves snapshots, compares explicit class
fields, deduplicates units and computes reproducible counts. It never decides
which tax interpretation is correct.

## Capture before case confirmation

Use the selected studio catalog and a source-backed case whose mappings are
still PROPOSED. The population is every distinct `(register side, code)` found
in its registers or liquidation sections, including unmatched/unknown codes.
Prepare a JSON packet with exactly:

```json
{
  "timing_declaration": "BEFORE_PROFESSIONAL_REVIEW",
  "model_proposals": []
}
```

For each model proposal, add an object with `side`, `code`, `tax_class`,
`confidence` and `evidence`, using those fields' exact catalog-entry schema.
The quoted evidence must include that exact code and exist in the case sources.
An empty array means there are no model proposals; it does not remove unknown
codes from the denominator. Catalog candidates are checked over all relevant
validity boundaries within the quarter. A recorded model proposal takes
precedence for the measurement when supplied; the catalog result is retained
separately. No mapping or calculation changes as a result of this command.

Read catalog history for the exact current head, then:

```bash
python scripts/lipe_metrics.py first-pass --catalog /absolute/studio/lipe.sqlite3 --case /absolute/run/inputs/case.json --proposals /absolute/run/inputs/proposals.json --source-root /absolute/run/inputs --client-engagement /absolute/client_engagement.json --expected-head EXACT_HEAD --output /absolute/run/output/first-pass-01.json
```

For real cases, the command verifies the existing Studio Archive run and input
receipts and requires its output receipt inside that run's output directory.
Only wholly fictional cases may omit `--client-engagement`. Do not mark real
or anonymized real cases SYNTHETIC. The case's `catalog_context` must match the
selected catalog. The original case sources are retained in the catalog's
private evidence vault as well as the selected case archive. This can include
complete register pages and client identifiers; it is not aggregate telemetry.

Each unit is keyed by client, engagement, year, quarter, declared real/synthetic
origin, software/version, side and code. A new filename, run or case ID cannot
reset it. Repeated captures leave existing units unchanged; newly discovered
codes add new units. Never change engagement/vendor identifiers to inflate a
measurement. A newly measured code already marked CONFIRMED is rejected. This
does not prove that review never occurred elsewhere: capture timing remains an
attributed declaration, not an authenticated observation.

## Record the actual professional response

Prepare a decision with exactly `unit_id`, `outcome`, `tax_class`, `sources`,
`evidence` and `review`. `unit_id` comes from the saved first-pass event.
`sources`, `evidence`, `tax_class` and `review` use the catalog-entry structures;
the review must be an actual CONFIRMED professional response with name, date
and reason. Code/source/page quotations are verified and original bytes retained.
Private client evidence stays labelled PRIVATE_CASE.

- CONFIRMED: the full class is identical to the first proposal.
- CORRECTED: the professional supplied a different full class.
- RESOLVED_NEW: there was no initial proposal and a class is now supplied.
- UNRESOLVED: the class remains null; this is not counted as successful review.

```bash
python scripts/lipe_metrics.py review --catalog /absolute/studio/lipe.sqlite3 --decision /absolute/run/inputs/code-review.json --source-root /absolute/run/inputs --expected-head EXACT_HEAD --output /absolute/run/output/code-review-01.json
```

A later decision must pass `--supersedes` with that unit's exact latest review
event hash. Earlier decisions remain present. This ledger does not authenticate
a professional, update the case or publish a catalog class. Apply any actual
case/catalog correction separately with the required evidence and review, then
recalculate. Never manufacture confirmations to improve a rate.

## Read the counts with their denominators

```bash
python scripts/lipe_metrics.py report --catalog /absolute/studio/lipe.sqlite3 --output /absolute/studio/measurements-01.json
```

The JSON groups by exact software/version and separates REAL from SYNTHETIC.
It reports numerators, denominators and two-decimal percentages:

- Recognition: units with a stable catalog candidate, or a model proposal with
  a known treatment meeting the studio's declared confidence cutoff and no
  unresolved catalog block (such as a dispute, conflict or revocation), divided
  by all captured units. Confidence is not calibrated by these counts.
- Catalog availability: consistent catalog candidates divided by all units,
  including cases where the model proposed a different class.
- First-resolution coverage: units with a resolved professional response
  divided by all units. The current unresolved count is also shown.
- Professional class change: changes in the first resolved response divided
  by reviewed units that had an initial proposal. Newly resolved unknowns are
  counted separately, not treated as corrected predictions.

An empty correction denominator produces null, never 0% or 100% accuracy.
A later reversal or reopening does not erase the first resolved response;
current unresolved cases remain visible. Full-class equality is literal and
includes textual fields such as legal basis. A wording-only edit therefore
counts as a class change; the measure must not be called a tax-error rate.

Only recorded populations are measured. Missing cases, incomplete extraction,
false timing declarations, changed identity labels and professional selection
bias cannot be eliminated by this local ledger. Present sample sizes and review
coverage, and do not extrapolate to other software or unseen cases. No real
performance rate is established by the synthetic engineering tests.

## Data handling and retention

No telemetry or remote sharing occurs. The report omits client IDs and source
content, but small cohorts and custom software labels are not guaranteed
anonymous. The underlying catalog history contains private case evidence,
proposals, first-pass timing declarations and attributed review records. Read
only the authorized scope and document the actual model exposure. Preserve
catalog database and adjacent source vault together. Receipts use new private
paths; after an output failure, inspect history before retrying a mutation.
