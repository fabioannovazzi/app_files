from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import plotly.graph_objects as go
from PIL import Image

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "set-overlap-analysis"
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"


def load_plugin_module(module_name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        while str(SCRIPT_DIR) in sys.path:
            sys.path.remove(str(SCRIPT_DIR))
    return module


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the Set Overlap MCP server.")
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def sample_overlap_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "Period": ["AC", "AC", "AC", "AC", "AC", "AC", "AC", "PY"],
            "SKU": ["sku1", "sku1", "sku2", "sku3", "sku3", "sku4", "sku5", "sku1"],
            "Retailer": ["A", "B", "A", "B", "C", "C", "A", "A"],
            "Region": [
                "North",
                "North",
                "North",
                "North",
                "North",
                "North",
                "South",
                "North",
            ],
        }
    )


def explicit_recipe() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "plugin": "set-overlap-analysis",
        "mappings": {
            "item_column": "SKU",
            "set_column": "Retailer",
            "period_column": "Period",
            "dimensions": ["Region"],
        },
        "options": {
            "charts": ["venn"],
            "selected_period": "AC",
            "set_values": ["A", "B", "C"],
            "max_sets": 3,
            "min_intersection_size": 1,
            "highlighted_sets": [],
            "write_html": False,
        },
    }


def test_chart_title_uses_reporting_entity_three_line_contract() -> None:
    core = load_plugin_module("set_overlap_core_title", "set_overlap_core.py")
    recipe = explicit_recipe()
    recipe["source_file"] = "/tmp/overlap.csv"
    recipe["options"]["reporting_entity_label"] = "Mexico hair color"

    title = core._chart_title(recipe, chart_name="UpSet", html=True)

    assert title == ("Mexico hair color" "<br>UpSet: SKU overlap by Retailer" "<br>AC")


def test_chart_title_puts_recipe_filter_on_first_row() -> None:
    core = load_plugin_module("set_overlap_core_filter_title", "set_overlap_core.py")
    recipe = explicit_recipe()
    recipe["source_file"] = "/tmp/overlap.csv"
    recipe["options"]["reporting_entity_label"] = "Mexico hair color"
    recipe["options"]["recipe_filter_audit"] = {
        "status": "written",
        "filters": [{"column": "Company", "include": ["All Other Manufacturers"]}],
    }

    title = core._chart_title(recipe, chart_name="Venn", html=True)

    assert (
        core.reporting_subject_label_from_recipe(recipe)
        == "Mexico hair color | Company = All Other Manufacturers"
    )
    assert title == (
        "Mexico hair color | Company = All Other Manufacturers"
        "<br>Venn: SKU overlap by Retailer"
        "<br>AC"
    )


def test_upset_reporting_title_uses_chart_font_size() -> None:
    core = load_plugin_module(
        "set_overlap_core_upset_title_layout", "set_overlap_core.py"
    )
    fig = go.Figure()
    fig.update_layout(font={"size": 12}, margin={"t": 30})

    core._apply_upset_reporting_title(
        fig,
        "Mexico hair color<br>UpSet: SKU overlap by Retailer<br>AC",
    )

    assert fig.layout.title.font.size == 12
    assert fig.layout.title.y == 0.94
    assert fig.layout.margin.t == 96


def test_resolve_chart_palette_uses_legacy_bain_default() -> None:
    core = load_plugin_module("set_overlap_core_palette", "set_overlap_core.py")
    recipe = explicit_recipe()

    palette_name, colors = core._resolve_chart_palette(recipe, 3)

    assert palette_name == "bain"
    assert colors == ("#343434", "#999A9A", "#818284")


def test_build_overlap_tables_returns_exact_intersections() -> None:
    core = load_plugin_module("set_overlap_core_tables", "set_overlap_core.py")
    frame = sample_overlap_frame()
    recipe = core.validate_recipe(frame, explicit_recipe())

    canonical = core.prepare_canonical_frame(frame, recipe)
    (
        ranked_canonical,
        set_summary,
        item_sets,
        intersections,
        selected_sets,
        ranking_audit,
    ) = core.build_overlap_tables(canonical, recipe)

    intersection_counts = {
        row["intersection"]: row["item_count"] for row in intersections.to_dicts()
    }
    set_counts = {row["set"]: row["item_count"] for row in set_summary.to_dicts()}

    assert selected_sets == ["A", "B", "C"]
    assert ranked_canonical.height == canonical.height
    assert ranking_audit["aggregated_sets"] == []
    assert set_counts == {"A": 3, "B": 2, "C": 2}
    assert intersection_counts == {"A & B": 1, "A": 2, "B & C": 1, "C": 1}
    assert item_sets.height == 5


def test_build_overlap_tables_aggregates_lower_ranked_sets_as_other() -> None:
    core = load_plugin_module("set_overlap_core_other_rank", "set_overlap_core.py")
    frame = pl.DataFrame(
        {
            "SKU": ["p1", "p1", "p1", "p2", "p3", "p4", "p5", "p6"],
            "Retailer": ["A", "B", "D", "A", "B", "C", "D", "E"],
        }
    )
    recipe = {
        "mappings": {
            "item_column": "SKU",
            "set_column": "Retailer",
            "period_column": None,
            "dimensions": [],
        },
        "options": {
            "charts": ["upset"],
            "selected_period": None,
            "set_values": [],
            "max_sets": 2,
            "min_intersection_size": 1,
            "highlighted_sets": [],
            "aggregate_other_sets": True,
            "write_html": False,
        },
    }

    canonical = core.prepare_canonical_frame(frame, core.validate_recipe(frame, recipe))
    (
        ranked_canonical,
        set_summary,
        _item_sets,
        intersections,
        selected_sets,
        ranking_audit,
    ) = core.build_overlap_tables(canonical, recipe)

    assert selected_sets == ["A", "B", "Other rank >2"]
    assert ranking_audit["aggregated_sets"] == ["D", "C", "E"]
    assert "Other rank >2" in ranked_canonical["set"].to_list()
    set_counts = {row["set"]: row["item_count"] for row in set_summary.to_dicts()}
    intersection_counts = {
        row["intersection"]: row["item_count"] for row in intersections.to_dicts()
    }
    assert set_counts == {"A": 2, "B": 2, "Other rank >2": 4}
    assert intersection_counts["Other rank >2"] == 3
    assert intersection_counts["A & B & Other rank >2"] == 1


def test_run_set_overlap_applies_filters_and_records_title_scope(
    tmp_path: Path,
) -> None:
    core = load_plugin_module("set_overlap_core_filtered", "set_overlap_core.py")
    input_path = tmp_path / "overlap.csv"
    recipe_path = tmp_path / "recipe.json"
    output_dir = tmp_path / "set_overlap"
    sample_overlap_frame().write_csv(input_path)
    recipe = explicit_recipe()
    recipe["options"]["set_values"] = ["A", "B"]
    recipe["options"]["filters"] = {"Region": {"include": ["North"]}}
    recipe["options"]["reporting_entity_label"] = "Mexico hair color"
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    result = core.run_set_overlap(input_path, output_dir, recipe_path)

    assert result.context["row_counts"]["filtered"] == 7
    assert result.context["row_counts"]["canonical_memberships"] == 6
    assert result.context["selected_sets"] == ["A", "B"]
    assert result.context["chart_audits"]["venn"]["status"] == "written"
    assert (
        result.context["chart_audits"]["venn"]["title"].splitlines()[0]
        == "Mexico hair color | Region = North"
    )
    assert (output_dir / "set_overlap_context.json").exists()
    assert (output_dir / "venn.png").exists()
    assert result.context["chart_audits"]["venn"]["palette"] == "bain"
    assert result.context["chart_audits"]["venn"]["colors"] == [
        "#343434",
        "#999A9A",
    ]
    assert result.context["chart_audits"]["venn"]["chart_font_size"] == 12
    assert result.context["chart_audits"]["venn"]["dimensions"] == {
        "width": 1400,
        "height": 900,
    }
    with Image.open(output_dir / "venn.png") as image:
        assert image.size == (1400, 900)
    run_intake = json.loads((output_dir / "run_intake.json").read_text())
    review_payload = json.loads((output_dir / "review_payload.json").read_text())
    ui_decisions = json.loads((output_dir / "ui_decisions.json").read_text())
    final_artifacts = json.loads((output_dir / "final_artifacts.json").read_text())
    audit = json.loads((output_dir / "set_overlap_audit.json").read_text())
    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    assert used_recipe["options"]["reporting_entity_label"] == "Mexico hair color"
    assert result.review_session == audit["review_session"]
    assert review_payload["plugin"] == "set-overlap-analysis"
    assert review_payload["workflow"] == "set-overlap-analysis"
    assert review_payload["run_id"] == run_intake["run_id"]
    assert review_payload["review_type"] == "set_overlap_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert "set_summary" in item_types
    assert "overlap_intersection" in item_types
    assert "pair_overlap" in item_types
    assert "chart_artifact" in item_types
    assert "context_artifact" in item_types
    assert review_payload["summary"]["selected_set_count"] == 2
    assert review_payload["summary"]["intersection_count"] >= 1
    assert ui_decisions["status"] == "pending_review"
    assert ui_decisions["decision_count"] == 0
    assert final_artifacts["status"] == "written_pending_review"
    contract_report = validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
    )
    assert contract_report.ok, contract_report.as_dict()




def test_run_set_overlap_skips_venn_when_more_than_three_sets_selected(
    tmp_path: Path,
) -> None:
    core = load_plugin_module("set_overlap_core_venn_skip", "set_overlap_core.py")
    input_path = tmp_path / "overlap.csv"
    recipe_path = tmp_path / "recipe.json"
    output_dir = tmp_path / "set_overlap"
    frame = pl.DataFrame(
        {
            "SKU": ["sku1", "sku1", "sku1", "sku1"],
            "Retailer": ["A", "B", "C", "D"],
        }
    )
    frame.write_csv(input_path)
    recipe = {
        "mappings": {
            "item_column": "SKU",
            "set_column": "Retailer",
            "period_column": None,
            "dimensions": [],
        },
        "options": {
            "charts": ["venn"],
            "selected_period": None,
            "set_values": ["A", "B", "C", "D"],
            "max_sets": 4,
            "min_intersection_size": 1,
            "highlighted_sets": [],
            "write_html": False,
        },
    }
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    result = core.run_set_overlap(input_path, output_dir, recipe_path)

    venn_audit = result.context["chart_audits"]["venn"]
    assert venn_audit["status"] == "not_written_unsupported_set_count"
    assert venn_audit["selected_set_count"] == 4
    assert not (output_dir / "venn.png").exists()


def test_run_set_overlap_writes_per_panel_ranked_upset_small_multiples(
    tmp_path: Path,
) -> None:
    core = load_plugin_module("set_overlap_core_upset_sm", "set_overlap_core.py")
    input_path = tmp_path / "category_market.csv"
    recipe_path = tmp_path / "recipe.json"
    output_dir = tmp_path / "set_overlap"
    frame = pl.DataFrame(
        {
            "Category": [
                "Furniture",
                "Furniture",
                "Furniture",
                "Furniture",
                "Furniture",
                "Furniture",
                "Furniture",
                "Technology",
                "Technology",
                "Technology",
                "Technology",
                "Technology",
                "Technology",
            ],
            "Product_Id": [
                "f1",
                "f2",
                "f3",
                "f4",
                "f5",
                "f6",
                "f6",
                "t1",
                "t2",
                "t3",
                "t4",
                "t5",
                "t6",
            ],
            "Market": [
                "Apac",
                "Apac",
                "Emea",
                "Eu",
                "Latam",
                "Apac",
                "Latam",
                "Us",
                "Us",
                "Eu",
                "Africa",
                "Africa",
                "Africa",
            ],
        }
    )
    frame.write_csv(input_path)
    recipe = {
        "mappings": {
            "item_column": "Product_Id",
            "set_column": "Market",
            "period_column": None,
            "dimensions": ["Category"],
        },
        "options": {
            "charts": ["upset_small_multiples"],
            "selected_period": None,
            "set_values": [],
            "max_sets": 2,
            "min_intersection_size": 1,
            "highlighted_sets": [],
            "aggregate_other_sets": True,
            "small_multiples_dimension": "Category",
            "small_multiples_max_panels": 4,
            "write_html": True,
        },
    }
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    result = core.run_set_overlap(input_path, output_dir, recipe_path)

    audit = result.context["chart_audits"]["upset_small_multiples"]
    assert audit["status"] == "written"
    assert audit["small_multiples_dimension"] == "Category"
    assert audit["panel_count"] == 2
    panel_sets = {row["facet"]: row["selected_sets"] for row in audit["facets"]}
    assert panel_sets["Furniture"] == ["Apac", "Latam", "Other rank >2"]
    assert panel_sets["Technology"] == ["Africa", "Us", "Other rank >2"]
    html = (output_dir / "upset_small_multiples.html").read_text(encoding="utf-8")
    assert 'class="upset-small-multiples" data-gallery-screenshot' in html
    assert html.count('class="upset-panel"') == 2
    summary_rows = (
        output_dir / "set_overlap_small_multiples_set_summary.csv"
    ).read_text(encoding="utf-8")
    assert "Furniture,Other rank >2" in summary_rows
    assert "Technology,Other rank >2" in summary_rows


def test_explicit_missing_set_value_fails() -> None:
    core = load_plugin_module("set_overlap_core_missing_set", "set_overlap_core.py")
    frame = sample_overlap_frame()
    recipe = explicit_recipe()
    recipe["options"]["set_values"] = ["A", "Missing"]
    canonical = core.prepare_canonical_frame(frame, core.validate_recipe(frame, recipe))

    with pytest.raises(ValueError, match="Requested set_values not found"):
        core.build_overlap_tables(canonical, recipe)


def test_skill_manifest_and_mcp_review_contract_are_wired() -> None:
    skill_text = (
        PLUGIN_ROOT / "skills" / "set-overlap-analysis" / "SKILL.md"
    ).read_text(encoding="utf-8")
    readme_text = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["mcpServers"] == "./.mcp.json"
    assert "validate_set_overlap_review" in skill_text
    assert "render_set_overlap_review" in skill_text
    assert "ui://widget/set-overlap-review.html" in skill_text
    assert "Plan-mode choices" in skill_text
    assert "one visible font size" in " ".join(skill_text.split())
    assert "one font size" in readme_text


def test_mcp_review_server_validates_and_renders_set_overlap_payload() -> None:
    review_payload = {
        "schema_version": "1.0",
        "plugin": "set-overlap-analysis",
        "workflow": "set-overlap-analysis",
        "run_id": "set-overlap-test-run",
        "review_type": "set_overlap_review",
        "item_count": 3,
        "items": [
            {
                "id": "set-summary-1",
                "item_type": "set_summary",
                "title": "A: 3 items",
                "output_path": "set_overlap_set_summary.csv",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [{"kind": "set_summary", "set": "A"}],
                "data": {},
                "status": "needs_review",
            },
            {
                "id": "intersection-1",
                "item_type": "overlap_intersection",
                "title": "A & B: 1 items",
                "output_path": "set_overlap_intersections.csv",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [{"kind": "exact_intersection"}],
                "data": {},
                "status": "needs_review",
            },
            {
                "id": "chart-1",
                "item_type": "chart_artifact",
                "title": "venn: written",
                "output_path": "venn.png",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [{"kind": "chart_audit", "status": "written"}],
                "data": {},
                "status": "needs_review",
            },
        ],
    }
    run_intake = {
        "schema_version": "1.0",
        "plugin": "set-overlap-analysis",
        "workflow": "set-overlap-analysis",
        "run_id": "set-overlap-test-run",
    }
    ui_decisions = {
        "schema_version": "1.0",
        "plugin": "set-overlap-analysis",
        "workflow": "set-overlap-analysis",
        "run_id": "set-overlap-test-run",
        "decisions": [],
        "status": "pending_review",
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": "set-overlap-analysis",
        "workflow": "set-overlap-analysis",
        "run_id": "set-overlap-test-run",
        "outputs": [],
        "status": "written_pending_review",
    }
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_set_overlap_review",
                "arguments": {
                    "review_payload": review_payload,
                    "run_intake": run_intake,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": final_artifacts,
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "render_set_overlap_review",
                "arguments": {
                    "review_payload": review_payload,
                    "run_intake": run_intake,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": final_artifacts,
                },
            },
        },
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "ui://widget/set-overlap-review.html"},
        },
    ]

    responses = _call_mcp_server(messages)
    by_id = {response["id"]: response["result"] for response in responses}
    tool_names = {tool["name"] for tool in by_id[1]["tools"]}
    assert "validate_set_overlap_review" in tool_names
    assert "render_set_overlap_review" in tool_names
    validation = json.loads(by_id[2]["content"][0]["text"])
    rendered = json.loads(by_id[3]["content"][0]["text"])
    assert validation["ok"] is True
    assert validation["item_count"] == 3
    assert rendered["widget_type"] == "set_overlap_review"
    assert (
        by_id[3]["_meta"]["openai/outputTemplate"]
        == "ui://widget/set-overlap-review.html"
    )
    assert any(
        resource["uri"] == "ui://widget/set-overlap-review.html"
        for resource in by_id[4]["resources"]
    )
    assert "Set Overlap Review" in by_id[5]["contents"][0]["text"]
