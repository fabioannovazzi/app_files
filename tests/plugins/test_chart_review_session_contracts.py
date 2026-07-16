from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.validate_plugin_review_contract import validate_contract

PLUGIN_REVIEW_MODULES = {
    "variance-analysis": Path("plugins/variance-analysis/scripts/review_session.py"),
    "period-comparison": Path("plugins/period-comparison/scripts/review_session.py"),
    "scatter-bubble-analysis": Path(
        "plugins/scatter-bubble-analysis/scripts/review_session.py"
    ),
    "distribution-analysis": Path(
        "plugins/distribution-analysis/scripts/review_session.py"
    ),
    "set-overlap-analysis": Path(
        "plugins/set-overlap-analysis/scripts/review_session.py"
    ),
    "mix-contribution-analysis": Path(
        "plugins/mix-contribution-analysis/scripts/review_session.py"
    ),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_review_session(plugin: str) -> Any:
    path = _repo_root() / PLUGIN_REVIEW_MODULES[plugin]
    module_name = f"{plugin.replace('-', '_')}_review_session_contract_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_common_files(
    output_dir: Path, context_name: str, context: dict[str, Any]
) -> Path:
    recipe_path = output_dir / "recipe.json"
    _write_json(recipe_path, {"seed": True})
    (output_dir / "chart.html").write_text("<html>chart</html>\n", encoding="utf-8")
    _write_json(
        output_dir / "final_artifacts.json",
        {
            "outputs": [
                {
                    "path": "chart.html",
                    "kind": "html",
                    "status": "written",
                }
            ]
        },
    )
    _write_json(output_dir / context_name, context)
    return recipe_path


def _build_chart_review_contract(plugin: str, tmp_path: Path) -> Path:
    module = _load_review_session(plugin)
    output_dir = tmp_path / plugin
    output_dir.mkdir()
    input_path = tmp_path / f"{plugin}.csv"
    input_path.write_text("name,value\nA,10\n", encoding="utf-8")

    if plugin == "variance-analysis":
        recipe = {"language": "en", "mappings": {"sku": "name"}, "options": {}}
        recipe_path = _seed_common_files(
            output_dir,
            "standard_variance_context.json",
            {"totals": {"total_delta": 10}, "dominant_component": {"name": "price"}},
        )
        run_intake = module.write_run_intake(
            output_dir,
            input_path,
            recipe_path=recipe_path,
            recipe=recipe,
            source_row_count=1,
        )
        module.write_review_session_artifacts(
            output_dir,
            input_path,
            run_id=run_intake.run_id,
            run_intake_path=run_intake.path,
            recipe_path=recipe_path,
            recipe=recipe,
            result_rows=[
                {
                    "sku": "A",
                    "amount_baseline": 100,
                    "amount_comparison": 110,
                    "total_delta": 10,
                    "price_variance": 6,
                    "volume_variance": 3,
                    "mix_variance": 1,
                    "component_reconciliation_delta": 0,
                }
            ],
            audit={},
        )
        return output_dir

    if plugin == "period-comparison":
        recipe = {"language": "en", "mappings": {}, "options": {}}
        recipe_path = _seed_common_files(
            output_dir,
            "period_comparison_context.json",
            {
                "comparison": {
                    "current": {"year": "2026"},
                    "previous": {"year": "2025"},
                },
                "totals": {"current": 110, "previous": 100, "delta": 10},
                "small_multiples_selection": {},
            },
        )
        run_intake = module.write_run_intake(
            output_dir,
            input_path,
            recipe_path=recipe_path,
            recipe=recipe,
            source_row_count=1,
        )
        module.write_review_session_artifacts(
            output_dir,
            input_path,
            run_id=run_intake.run_id,
            run_intake_path=run_intake.path,
            recipe_path=recipe_path,
            recipe=recipe,
            monthly_rows=[{"Date": "2026-01", "AC": 110, "PY": 100}],
            by_period_rows=[
                {"window": "FY", "current": 110, "previous": 100, "delta": 10}
            ],
            audit={},
        )
        return output_dir

    if plugin == "scatter-bubble-analysis":
        recipe = {
            "language": "en",
            "mappings": {
                "dot_dimension": "name",
                "x_metric_column": "x",
                "y_metric_column": "y",
                "bubble_size_metric_column": "size",
            },
            "options": {},
        }
        recipe_path = _seed_common_files(
            output_dir,
            "scatter_bubble_context.json",
            {"relationship": {"x_metric": "x", "y_metric": "y"}},
        )
        run_intake = module.write_run_intake(
            output_dir,
            input_path,
            recipe_path=recipe_path,
            recipe=recipe,
            source_row_count=1,
        )
        module.write_review_session_artifacts(
            output_dir,
            input_path,
            run_id=run_intake.run_id,
            run_intake_path=run_intake.path,
            recipe_path=recipe_path,
            recipe=recipe,
            summary_rows=[{"name": "A", "x": 1, "y": 2, "size": 3}],
            audit={},
        )
        return output_dir

    if plugin == "distribution-analysis":
        recipe = {
            "language": "en",
            "mappings": {"metric_column": "value", "distribution_dimension": "period"},
            "options": {},
        }
        recipe_path = _seed_common_files(
            output_dir,
            "distribution_context.json",
            {"metric": "value", "periods": ["2026"]},
        )
        run_intake = module.write_run_intake(
            output_dir,
            input_path,
            recipe_path=recipe_path,
            recipe=recipe,
            source_row_count=1,
        )
        module.write_review_session_artifacts(
            output_dir,
            input_path,
            run_id=run_intake.run_id,
            run_intake_path=run_intake.path,
            recipe_path=recipe_path,
            recipe=recipe,
            summary_rows=[
                {
                    "Period": "2026",
                    "rows": 1,
                    "mean": 10,
                    "median": 10,
                    "min": 9,
                    "max": 11,
                }
            ],
            audit={},
        )
        return output_dir

    if plugin == "set-overlap-analysis":
        recipe = {"language": "en", "mappings": {}, "options": {}}
        recipe_path = _seed_common_files(
            output_dir,
            "set_overlap_context.json",
            {"selected_sets": ["A", "B"]},
        )
        context = {
            "selected_sets": ["A", "B"],
            "set_summary": [{"set": "A", "item_count": 2, "selected": True}],
            "intersections": [{"intersection": "A+B", "set_count": 2, "item_count": 1}],
            "pairwise_overlap": [{"left_set": "A", "right_set": "B", "item_count": 1}],
            "row_counts": {
                "intersection_count": 1,
                "item_count": 2,
                "canonical_memberships": 3,
            },
            "mappings": {"item_column": "sku", "set_column": "retailer"},
            "options": {},
            "chart_audits": {
                "upset": {"status": "written", "artifacts": ["chart.html"]}
            },
        }
        run_intake = module.write_run_intake(
            output_dir,
            input_path,
            recipe_path=recipe_path,
            recipe=recipe,
            source_row_count=1,
        )
        module.write_review_session_artifacts(
            output_dir,
            input_path,
            run_id=run_intake.run_id,
            run_intake_path=run_intake.path,
            recipe_path=recipe_path,
            recipe=recipe,
            context=context,
            audit={},
        )
        return output_dir

    if plugin == "mix-contribution-analysis":
        recipe = {
            "language": "en",
            "mappings": {"amount_column": "amount", "dimension": "name"},
            "options": {},
        }
        recipe_path = _seed_common_files(
            output_dir,
            "mix_contribution_context.json",
            {
                "contribution": {
                    "metric": "amount",
                    "total": 10,
                    "top_items": [{"item": "A", "share_of_total": 1.0}],
                }
            },
        )
        run_intake = module.write_run_intake(
            output_dir,
            input_path,
            recipe_path=recipe_path,
            recipe=recipe,
            source_row_count=1,
        )
        module.write_review_session_artifacts(
            output_dir,
            input_path,
            run_id=run_intake.run_id,
            run_intake_path=run_intake.path,
            recipe_path=recipe_path,
            recipe=recipe,
            summary_rows=[{"name": "A", "amount": 10, "share_of_total": 1.0}],
            audit={"charts": {}},
        )
        return output_dir

    raise AssertionError(f"unhandled plugin fixture: {plugin}")


@pytest.mark.parametrize("plugin", sorted(PLUGIN_REVIEW_MODULES))
def test_chart_review_session_contract_declares_local_data_posture(
    plugin: str, tmp_path: Path
) -> None:
    output_dir = _build_chart_review_contract(plugin, tmp_path)

    report = validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
    )

    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    data_posture = run_intake["data_posture"]
    assert report.ok, report.as_dict()
    assert data_posture["local_files_read"]
    assert data_posture["model_excerpts_sent"] == []
    assert data_posture["external_connectors_used"] == []
    assert data_posture["upload_paths_used"] == []
    assert data_posture["calculation_mode"] == "local_deterministic_scripts"
