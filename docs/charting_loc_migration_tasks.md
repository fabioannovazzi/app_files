# Charting Module: Pandas `.loc` Migration Tasks

This document lists incremental tasks for migrating any remaining pandas-style
``.loc`` expressions in the charting module to Polars. The code base now uses
Polars exclusively, but some comments still referenced the old pandas syntax.

The checklist below tracks the migration work. Items marked as completed no
longer require attention.

1. [x] Remove outdated comments referencing pandas ``.loc`` in ``chart_primitives.py``.
2. [x] Reword ``plot_charts.py`` comments that still mention ``.loc`` semantics.
3. [x] Clean up the helper in ``draw_charts_utils.py`` that referenced ``.loc``.
4. [x] Ensure ``chart_primitives.py`` explains Polars logic without quoting pandas code.
5. [x] Review ``draw_multitier.py`` for any stray pandas terminology.
6. [x] Add a regression test asserting that no source file in ``modules/charting`` contains ``.loc[``.
7. [x] Confirm ``chart_primitives`` functions operate on ``LazyFrame`` inputs without collection.
8. [x] Check ``plot_charts`` small multiples logic for eager DataFrame usage and migrate to lazy.
9. [x] Verify ``add_forecast_bars_to_multitier_column`` behaves correctly on a small ``LazyFrame``.
10. [x] Update documentation examples to showcase Polars equivalents exclusively.
11. [ ] Remove any ``.loc`` references from comments in ``modules/charting`` and ``modules/data``.
12. [ ] Add tests ensuring docstrings across the codebase do not mention pandas ``.loc``.
