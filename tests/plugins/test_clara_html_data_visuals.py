from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT / "plugins" / "clara" / "skills" / "html-deck" / "scripts" / "data_visuals.py"
)


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_html_data_visuals", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def base_spec(visual_type: str) -> dict[str, Any]:
    result = {
        "schema_version": "clara.html_deck_visual.v1",
        "type": visual_type,
        "id": f"visual-{visual_type}",
        "title": "Decision evidence",
        "aria_label": "Decision evidence chart",
        "source_ids": ["source-a"],
        "source_note": "Source: approved workpaper.",
    }
    if visual_type in {"scatter", "bubble"}:
        result.update(
            {
                "x_axis_label": "Sales (USD)",
                "y_axis_label": "Margin (%)",
            }
        )
    if visual_type == "bubble":
        result["size_axis_label"] = "Customers"
    return result


@pytest.mark.parametrize(
    ("visual_type", "payload", "expected"),
    [
        (
            "bar",
            {"data": [{"label": "A", "value": 10}, {"label": "B", "value": -2}]},
            "data-visual--bar",
        ),
        (
            "line",
            {"data": [{"label": "T0", "value": 10}, {"label": "T1", "value": 14}]},
            "data-visual--line",
        ),
        ("scatter", {"data": [{"label": "A", "x": 1, "y": 4}]}, "data-visual--scatter"),
        (
            "bubble",
            {"data": [{"label": "A", "x": 1, "y": 4, "size": 8}]},
            "data-visual--bubble",
        ),
        (
            "waterfall",
            {"data": [{"label": "Base", "value": 10}, {"label": "Risk", "value": -3}]},
            "data-visual--waterfall",
        ),
        (
            "timeline",
            {
                "data": [
                    {"date": "Q1", "label": "Scope"},
                    {"date": "Q2", "label": "Pilot"},
                ]
            },
            "data-visual--timeline",
        ),
        (
            "table",
            {"columns": ["Option", "Impact"], "rows": [["A", "High"]]},
            "data-visual--table",
        ),
    ],
)
def test_render_visual_supported_types_escape_and_trace_sources(
    visual_type: str,
    payload: dict[str, Any],
    expected: str,
) -> None:
    module = load_module()
    spec = base_spec(visual_type)
    spec.update(payload)
    spec["title"] = "Evidence <unsafe>"

    rendered = module.render_visual(spec)

    assert expected in rendered
    assert "Evidence &lt;unsafe&gt;" in rendered
    assert 'data-source-ids="source-a"' in rendered
    assert 'data-qa-role="data-visual"' in rendered
    assert "<unsafe>" not in rendered


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"source_ids": []}, "source_ids"),
        ({"source_ids": [None]}, "source_ids"),
        ({"id": None}, "visual.id"),
        ({"type": "pie"}, "unsupported visual type"),
        ({"data": [{"label": "A", "value": float("nan")}]}, "finite"),
    ],
)
def test_render_visual_rejects_invalid_mechanical_contracts(
    mutation: dict[str, Any],
    message: str,
) -> None:
    module = load_module()
    spec = base_spec("bar")
    spec["data"] = [{"label": "A", "value": 2}]
    spec.update(mutation)

    with pytest.raises(ValueError, match=message):
        module.render_visual(spec)


def test_render_visual_does_not_select_or_filter_bubble_periods() -> None:
    module = load_module()
    spec = base_spec("bubble")
    spec["data"] = [
        {"label": "2025 / A", "x": 1, "y": 2, "size": 3},
        {"label": "2026 / A", "x": 2, "y": 3, "size": 4},
    ]

    rendered = module.render_visual(spec)

    assert "2025 / A" in rendered
    assert "2026 / A" in rendered


def test_null_optional_copy_falls_back_without_rendering_none() -> None:
    module = load_module()
    spec = base_spec("line")
    spec.update(
        {
            "aria_label": None,
            "description": None,
            "source_note": None,
            "data": [{"label": "T0", "value": 1}, {"label": "T1", "value": 2}],
        }
    )

    rendered = module.render_visual(spec)

    assert 'aria-label="Decision evidence"' in rendered
    assert "None" not in rendered


def test_scatter_renders_explicit_axes_and_numeric_ticks() -> None:
    module = load_module()
    spec = base_spec("scatter")
    spec["data"] = [
        {"label": "A", "x": 10, "y": 100},
        {"label": "B", "x": 30, "y": 300},
    ]

    rendered = module.render_visual(spec)

    assert "Sales (USD)" in rendered
    assert "Margin (%)" in rendered
    assert 'class="data-axis-tick"' in rendered
    assert ">10<" in rendered
    assert ">300<" in rendered


def test_bubble_uses_area_scaling_and_identifies_size() -> None:
    module = load_module()
    spec = base_spec("bubble")
    spec["data"] = [
        {"label": "Small", "x": 1, "y": 2, "size": 1},
        {"label": "Large", "x": 2, "y": 3, "size": 4},
    ]

    rendered = module.render_visual(spec)

    assert "Customers" in rendered
    assert 'data-size="1"' in rendered
    assert 'data-size="4"' in rendered
    assert 'r="10.00"' in rendered
    assert 'r="20.00"' in rendered


@pytest.mark.parametrize("field", ["title", "x_axis_label", "y_axis_label"])
def test_scatter_rejects_missing_or_null_required_labels(field: str) -> None:
    module = load_module()
    spec = base_spec("scatter")
    spec["data"] = [{"label": "A", "x": 1, "y": 2}]
    spec[field] = None

    with pytest.raises(ValueError, match=field):
        module.render_visual(spec)


@pytest.mark.parametrize(
    ("visual_type", "payload", "message"),
    [
        (
            "bar",
            {
                "data": [
                    {"label": f"Item {index}", "value": index} for index in range(9)
                ]
            },
            "8-item budget",
        ),
        (
            "timeline",
            {
                "data": [
                    {"date": f"Q{index}", "label": f"Step {index}"}
                    for index in range(7)
                ]
            },
            "6-item budget",
        ),
        (
            "table",
            {
                "columns": ["A", "B"],
                "rows": [[f"Row {index}", "Value"] for index in range(9)],
            },
            "8-item budget",
        ),
    ],
)
def test_visual_density_budgets_reject_unreadable_cardinality(
    visual_type: str,
    payload: dict[str, Any],
    message: str,
) -> None:
    module = load_module()
    spec = base_spec(visual_type)
    spec.update(payload)

    with pytest.raises(ValueError, match=message):
        module.render_visual(spec)


@pytest.mark.parametrize(
    ("visual_type", "data", "label"),
    [
        (
            "bar",
            [{"label": "A label wider than gutter", "value": 1}],
            "label",
        ),
        (
            "line",
            [{"label": "123456789", "value": index} for index in range(10)],
            "label",
        ),
        (
            "waterfall",
            [{"label": "1234567890", "value": 1} for _ in range(8)],
            "label",
        ),
    ],
)
def test_visual_label_budgets_account_for_available_spacing(
    visual_type: str,
    data: list[dict[str, Any]],
    label: str,
) -> None:
    module = load_module()
    spec = base_spec(visual_type)
    spec["data"] = data

    with pytest.raises(ValueError, match=label):
        module.render_visual(spec)


def test_composer_extension_uses_stable_slide_context_and_explicit_sources() -> None:
    module = load_module()
    slide = SimpleNamespace(slide_id="evidence", source_refs=("source-a",))
    value = {
        "renderer": "data_visual",
        "spec": {
            "type": "line",
            "title": "Observed path",
            "data": [
                {"label": "T0", "value": 2},
                {"label": "T1", "value": 4},
            ],
        },
    }

    rendered = module.RENDERERS["data_visual"](
        slot_name="visual",
        value=value,
        slot_schema={"type": "extension"},
        slide=slide,
    )

    assert 'data-component-id="evidence-visual"' in rendered
    assert 'data-source-ids="source-a"' in rendered
