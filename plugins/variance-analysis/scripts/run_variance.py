"""Run deterministic sales variance analysis for Codex interpretation."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from variance_core import add_common_args, configure_logging, run_variance_analysis

LOGGER = logging.getLogger(__name__)


def parse_move_rows(values: list[str] | None) -> dict[int, list[int]]:
    """Parse legacy move-row CLI mappings such as ``1:1,2``."""

    result: dict[int, list[int]] = {}
    for value in values or []:
        main_text, separator, row_text = value.partition(":")
        if not separator:
            raise ValueError("Move-row mappings must use MAIN:DRILL[,DRILL...] syntax.")
        try:
            main_row = int(main_text)
        except ValueError as exc:
            raise ValueError(f"Invalid main row in move-row mapping: {value}") from exc
        if main_row <= 0:
            raise ValueError(f"Main row must be positive in move-row mapping: {value}")
        drilldown_rows: list[int] = []
        for item in row_text.split(","):
            try:
                drilldown_row = int(item)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid drilldown row in move-row mapping: {value}"
                ) from exc
            if drilldown_row <= 0:
                raise ValueError(
                    f"Drilldown row must be positive in move-row mapping: {value}"
                )
            if drilldown_row not in drilldown_rows:
                drilldown_rows.append(drilldown_row)
        if drilldown_rows:
            result[main_row] = drilldown_rows
    return result


def main() -> int:
    """Run deterministic variance calculations."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path, help="CSV/XLSX sales file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where variance outputs will be written.",
    )
    parser.add_argument("--recipe", type=Path, help="Recipe JSON from inspection.")
    parser.add_argument(
        "--root-cause-bridge",
        action="store_true",
        help=(
            "Compatibility flag; root-cause variance runs by default when the "
            "mapped data supports it."
        ),
    )
    parser.add_argument(
        "--root-cause-bridge-alternative-result",
        type=int,
        help="Legacy alternativeResult value for the root-cause bridge.",
    )
    parser.add_argument(
        "--root-cause-bridge-drilldown-row",
        action="append",
        type=int,
        default=[],
        help="1-based main bridge row to drill down. Repeat to select multiple rows.",
    )
    parser.add_argument(
        "--root-cause-bridge-drilldown-all",
        action="store_true",
        help="Run legacy drilldown for every selected root-cause bridge row.",
    )
    parser.add_argument(
        "--root-cause-bridge-move-row",
        action="append",
        default=[],
        help="Move drilldown rows into the main bridge, using MAIN:DRILL[,DRILL...].",
    )
    parser.add_argument(
        "--root-cause-bridge-alternative-sweep",
        action="store_true",
        help="Run root-cause alternativeResult values as a sweep.",
    )
    parser.add_argument(
        "--root-cause-bridge-alternative-sweep-start",
        type=int,
        help="First alternativeResult value for the root-cause sweep.",
    )
    parser.add_argument(
        "--root-cause-bridge-alternative-sweep-end",
        type=int,
        help="Last alternativeResult value for the root-cause sweep.",
    )
    parser.add_argument(
        "--root-cause-bridge-auto-drilldown",
        choices=["none", "single-row", "dominant-row", "all-selected"],
        help="Automatically drill down selected rows during the sweep.",
    )
    parser.add_argument(
        "--root-cause-bridge-auto-drilldown-min-share",
        type=float,
        help="Minimum absolute-variance share for dominant-row auto drilldown.",
    )
    parser.add_argument(
        "--root-cause-component-bridge",
        action="store_true",
        help=(
            "Also write the second-order component-by-dimension root-cause "
            "bridge. This is separate from the default total-variance bridge."
        ),
    )
    parser.add_argument(
        "--root-cause-component-bridge-alternative-result",
        type=int,
        help="Legacy alternativeResult value for the component root-cause bridge.",
    )
    parser.add_argument(
        "--no-waterfall-chart",
        action="store_true",
        help="Skip the default waterfall.png chart output.",
    )
    parser.add_argument(
        "--waterfall-small-multiples",
        action="store_true",
        help="Render waterfall.png as small multiples for a reporting dimension.",
    )
    parser.add_argument(
        "--waterfall-small-multiples-dimension",
        help="Dimension column to use when rendering waterfall small multiples.",
    )
    parser.add_argument(
        "--total-by-dimension-bridge",
        action="store_true",
        help=(
            "Render the total variance split by one fixed dimension, with row "
            "baseline/comparison value bars and percent pins."
        ),
    )
    parser.add_argument(
        "--no-total-by-dimension-bridge",
        action="store_true",
        help="Skip the total variance by fixed dimension bridge output.",
    )
    parser.add_argument(
        "--total-by-dimension-bridge-dimension",
        help="Dimension column to use for the total variance bridge rows.",
    )
    parser.add_argument(
        "--total-by-dimension-bridge-top-n",
        type=int,
        help="Maximum member rows before aggregating the remaining members as Other.",
    )
    parser.add_argument(
        "--exploded-variance-bridge",
        action="store_true",
        help=(
            "Render the one-page parent bridge with up to two child drilldown "
            "panels."
        ),
    )
    parser.add_argument(
        "--no-exploded-variance-bridge",
        action="store_true",
        help="Skip the exploded parent/child variance bridge output.",
    )
    parser.add_argument(
        "--exploded-variance-bridge-parent-dimension",
        help="Parent dimension column for the exploded bridge.",
    )
    parser.add_argument(
        "--exploded-variance-bridge-child-dimension",
        help="Child drilldown dimension column for the exploded bridge.",
    )
    parser.add_argument(
        "--exploded-variance-bridge-parent-top-n",
        type=int,
        help="Maximum parent rows before aggregating remaining members as Other.",
    )
    parser.add_argument(
        "--exploded-variance-bridge-child-top-n",
        type=int,
        help="Maximum child rows per drilldown before aggregating as Other.",
    )
    parser.add_argument(
        "--exploded-variance-bridge-max-drilldowns",
        type=int,
        help="Maximum expanded parent rows; capped at two.",
    )
    parser.add_argument(
        "--currency",
        help="Currency code for monetary outputs. Defaults to EUR when omitted.",
    )
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    result = run_variance_analysis(
        args.input_file,
        args.output_dir,
        args.recipe,
        root_cause_bridge=(
            args.root_cause_bridge or args.root_cause_bridge_alternative_sweep or None
        ),
        root_cause_bridge_alternative_result=(
            args.root_cause_bridge_alternative_result
        ),
        root_cause_bridge_drilldown_rows=(args.root_cause_bridge_drilldown_row or None),
        root_cause_bridge_drilldown_all=args.root_cause_bridge_drilldown_all or None,
        root_cause_bridge_move_rows=parse_move_rows(args.root_cause_bridge_move_row)
        or None,
        root_cause_bridge_alternative_sweep=(
            args.root_cause_bridge_alternative_sweep or None
        ),
        root_cause_bridge_alternative_sweep_start=(
            args.root_cause_bridge_alternative_sweep_start
        ),
        root_cause_bridge_alternative_sweep_end=(
            args.root_cause_bridge_alternative_sweep_end
        ),
        root_cause_bridge_auto_drilldown=(
            args.root_cause_bridge_auto_drilldown.replace("-", "_")
            if args.root_cause_bridge_auto_drilldown
            else None
        ),
        root_cause_bridge_auto_drilldown_min_share=(
            args.root_cause_bridge_auto_drilldown_min_share
        ),
        root_cause_component_bridge=args.root_cause_component_bridge or None,
        root_cause_component_bridge_alternative_result=(
            args.root_cause_component_bridge_alternative_result
        ),
        waterfall_chart=False if args.no_waterfall_chart else None,
        waterfall_small_multiples=args.waterfall_small_multiples or None,
        waterfall_small_multiples_dimension=args.waterfall_small_multiples_dimension,
        total_by_dimension_bridge=(
            False
            if args.no_total_by_dimension_bridge
            else args.total_by_dimension_bridge or None
        ),
        total_by_dimension_bridge_dimension=(args.total_by_dimension_bridge_dimension),
        total_by_dimension_bridge_top_n=args.total_by_dimension_bridge_top_n,
        exploded_variance_bridge=(
            False
            if args.no_exploded_variance_bridge
            else args.exploded_variance_bridge or None
        ),
        exploded_variance_bridge_parent_dimension=(
            args.exploded_variance_bridge_parent_dimension
        ),
        exploded_variance_bridge_child_dimension=(
            args.exploded_variance_bridge_child_dimension
        ),
        exploded_variance_bridge_parent_top_n=(
            args.exploded_variance_bridge_parent_top_n
        ),
        exploded_variance_bridge_child_top_n=args.exploded_variance_bridge_child_top_n,
        exploded_variance_bridge_max_drilldowns=(
            args.exploded_variance_bridge_max_drilldowns
        ),
        currency=args.currency,
        language=args.language,
        artifact_mode=args.artifact_mode,
    )
    LOGGER.info("result_rows=%s", result.frame.height)
    LOGGER.info("outputs=%s", sorted(result.audit["outputs"]))
    LOGGER.info("wrote %s", args.output_dir / "variance_results.csv")
    LOGGER.info("wrote %s", args.output_dir / "variance_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
