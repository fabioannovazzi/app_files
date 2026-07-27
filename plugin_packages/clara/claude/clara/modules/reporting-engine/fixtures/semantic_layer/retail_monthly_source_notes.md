# Retail Monthly Fixture Source Notes

This file is the canonical semantic source for the synthetic
`retail_monthly` dataset contract. Its CSV files are recurring snapshots of the
same invented data asset. They are not customer data and make no real-world
business claim.

## Grain And Scope

Each row is one SKU-brand observation for one calendar month. `Date` is the
first day of the represented calendar month, not a transaction date. Snapshot
row counts, values, available dates, and dimension members may change without
changing this meaning.

The stable period rules are: all available calendar months, current calendar
YTD through the latest available month, and aligned current YTD versus prior
YTD. Concrete dates are resolved from each snapshot. Any chart that uses `AC`
or `PY` must display or carry the resolved date boundaries. All-available data
must remain an explicit rule, not the accidental result of omitting a filter.

## Metrics

- `Sales` is net invoiced sales in US dollars at the row grain. It is additive
  across rows, brands, categories, regions, SKUs, and months.
- `Units` is sold unit volume at the row grain. It is additive across the same
  dimensions and periods.
- `MarginRate` is gross margin divided by sales for the row. It is not additive.
  Across rows it must be calculated as a sales-weighted mean; summing or taking
  an unweighted mean is invalid.
- Average selling price is a derived metric calculated as `sum(Sales) /
  sum(Units)` for the selected scope. It must not be calculated as a sum or as an
  unweighted mean of row-level ratios.

Higher sales, units, margin rate, and average selling price are descriptive
increases in this fixture; the fixture does not assert that every increase is a
business improvement.

## Dimensions

- `Brand` is a reporting dimension and the parent entity for `SKU`.
- `Category` groups brands into Color and Care.
- `Region` is a reporting geography. It cross-classifies Category in this
  fixture, so Category and Region may support two-dimensional composition.
- `SKU` identifies the observation entity. It may be used for points or detail,
  but one SKU per brand in this fixture means Brand and SKU are redundant for a
  two-dimensional decomposition.

## Reviewed Analysis Rules

The dataset contract supports monthly sales trajectory, current-versus-prior
monthly gaps, brand ranking for current YTD, category sales mix over time,
sales-versus-margin relationship by brand, sales/units/margin bubble analysis,
margin-rate distribution across brand-month observations, and price-volume-mix
decomposition between aligned current and prior YTD windows.

Relationship plots require one point per reviewed entity and scope. The data
must be aggregated to Brand for Brand relationship questions; plotting all raw
rows as unrelated points would answer a different question.

The fixture does not establish a funnel, statement structure, set membership,
cohort lifecycle, or root-cause hierarchy. Those analysis families are outside
the semantic coverage even though a generic mechanical profile may find
columns that could fit some numeric or categorical roles.
