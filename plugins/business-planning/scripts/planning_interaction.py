"""Switch between author-selected, checked tables without browser arithmetic.

ID/shape checks and shared scales are mechanical; period comparability, scenario
meaning and the explanation remain the report author's professional judgment.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Callable

from planning_workflow import indexed, require

__all__ = ["validate_groups", "render_group", "interaction_assets"]


def validate_groups(presentation: dict[str, Any], tables: dict[str, Any]) -> None:
    """Require unambiguous views bound to existing monetary comparison tables."""
    groups = indexed(presentation.get("comparison_groups", []), "comparison group")
    assigned: set[str] = set()
    for group in groups.values():
        require(
            set(group) == {"id", "title", "views"}, "Unexpected comparison group fields"
        )
        require(
            isinstance(group["title"], str) and bool(group["title"].strip()),
            "Comparison group needs a title",
        )
        views = group["views"]
        require(
            isinstance(views, list) and len(views) >= 2,
            "Comparison group needs at least two views",
        )
        choices: set[tuple[str, str]] = set()
        sections: set[str] = set()
        for view in views:
            require(
                isinstance(view, dict)
                and set(view) == {"table_id", "period", "scenario"},
                "Unexpected comparison view fields",
            )
            require(
                all(isinstance(view[k], str) and view[k].strip() for k in view),
                "Comparison view labels must be nonempty text",
            )
            tid = view["table_id"]
            require(
                tid in tables and "comparison" in tables[tid],
                "Comparison view needs a monetary comparison table",
            )
            require(tid not in assigned, "Comparison table is assigned more than once")
            assigned.add(tid)
            choice = (view["period"], view["scenario"])
            require(choice not in choices, "Duplicate period and scenario choice")
            choices.add(choice)
            sections.add(tables[tid]["section"])
        require(len(sections) == 1, "Comparison group must stay in one report section")


def render_group(
    group: dict[str, Any],
    tables: dict[str, Any],
    lang: str,
    render_table: Callable[[dict[str, Any], list[dict[str, Any]]], str],
    rows_for: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> str:
    """Retain every checked view in HTML; JavaScript only selects visibility."""
    from planning_presentation import label

    e = html.escape
    scales = [
        row for view in group["views"] for row in rows_for(tables[view["table_id"]])
    ]
    controls = []
    for key, title in (("period", "Period"), ("scenario", "Comparison")):
        values = dict.fromkeys(view[key] for view in group["views"])
        options = "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in values)
        controls.append(
            f"<label>{e(label(title, lang))}<select data-report-{key} disabled>{options}</select></label>"
        )
    panels = []
    for view in group["views"]:
        panels.append(
            f'<div data-comparison-panel data-period="{e(view["period"])}" data-scenario="{e(view["scenario"])}">{render_table(tables[view["table_id"]], scales)}</div>'
        )
    return (
        f'<div class="comparison-explorer" id="comparison-{e(group["id"])}" data-comparison-group>'
        f'<h3>{e(group["title"])}</h3><div class="report-controls">{"".join(controls)}</div>'
        f'<p class="comparison-selection" aria-live="polite"></p>{"".join(panels)}</div>'
    )


def interaction_assets() -> tuple[str, str]:
    """Inline the packaged first-party assets for an offline-capable report."""
    assets = Path(__file__).resolve().parents[1] / "assets"
    return (
        (assets / "report-interaction.css").read_text(encoding="utf-8"),
        (assets / "report-interaction.js").read_text(encoding="utf-8"),
    )
