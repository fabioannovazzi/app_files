import polars as pl
import polars.expr.expr as expr_mod
from modules.utilities.ui_notifier import ui

if not hasattr(expr_mod.Expr, "map_dict"):

    def map_dict(self, mapping: dict, *, default=None):
        """Map values using a dictionary, inferring ``return_dtype``."""

        values = list(mapping.values())
        if default is not None:
            values.append(default)
        non_null_values = [v for v in values if v is not None]
        return_dtype = pl.Series(non_null_values).dtype if non_null_values else pl.Null
        return self.map_elements(
            lambda v: mapping.get(v, default), return_dtype=return_dtype
        )

    setattr(expr_mod.Expr, "map_dict", map_dict)

if not hasattr(pl.DataFrame, "frame_equal"):

    def frame_equal(self: pl.DataFrame, other: pl.DataFrame) -> bool:
        """Return ``True`` if ``self`` and ``other`` contain the same data."""

        try:
            pl.testing.assert_frame_equal(self, other)
            return True
        except AssertionError as e:
            ui.write("frame_equal mismatch:", e)
            return False

    setattr(pl.DataFrame, "frame_equal", frame_equal)
