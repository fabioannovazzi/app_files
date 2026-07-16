from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

CHART_REVIEW_SERVERS = [
    (
        "variance-analysis",
        "render_variance_analysis_review",
        "save_variance_analysis_decisions",
        "apply_variance_analysis_decisions",
        "variance_driver",
        "variance_analysis_review",
    ),
    (
        "period-comparison",
        "render_period_comparison_review",
        "save_period_comparison_decisions",
        "apply_period_comparison_decisions",
        "period_movement",
        "period_comparison_review",
    ),
    (
        "mix-contribution-analysis",
        "render_mix_contribution_review",
        "save_mix_contribution_decisions",
        "apply_mix_contribution_decisions",
        "contribution_driver",
        "mix_contribution_review",
    ),
    (
        "scatter-bubble-analysis",
        "render_scatter_bubble_review",
        "save_scatter_bubble_decisions",
        "apply_scatter_bubble_decisions",
        "relationship_driver",
        "scatter_bubble_review",
    ),
    (
        "distribution-analysis",
        "render_distribution_review",
        "save_distribution_decisions",
        "apply_distribution_decisions",
        "distribution_summary",
        "distribution_review",
    ),
    (
        "set-overlap-analysis",
        "render_set_overlap_review",
        "save_set_overlap_decisions",
        "apply_set_overlap_decisions",
        "set_summary",
        "set_overlap_review",
    ),
]

CHART_REVIEW_ITEM_LIMIT = 2500


def _assert_widget_resource_meta(meta: dict[str, object], uri: str) -> None:
    description = meta.get("openai/widgetDescription")
    assert isinstance(description, str)
    assert len(description.strip()) >= 20
    assert meta["openai/widgetPrefersBorder"] is False

    csp = meta["openai/widgetCSP"]
    assert isinstance(csp, dict)
    assert csp["connect_domains"] == []
    assert csp["resource_domains"] == []

    ui = meta.get("ui")
    if isinstance(ui, dict) and "resourceUri" in ui:
        assert ui["resourceUri"] == uri
    if "openai/widgetDomain" in meta:
        assert meta["openai/widgetDomain"] == "https://chatgpt.com"


def _assert_review_tool_annotations(
    tools: list[dict[str, object]],
    *,
    validate_tool: str,
    render_tool: str,
    save_tool: str,
    apply_tool: str,
) -> None:
    tools_by_name = {tool["name"]: tool for tool in tools}
    expected_tools = {validate_tool, render_tool, save_tool, apply_tool}
    assert expected_tools <= set(tools_by_name)

    render_meta = tools_by_name[render_tool]["_meta"]
    template = render_meta["openai/outputTemplate"]
    assert isinstance(template, str)
    assert template.startswith("ui://widget/")
    assert template.endswith(".html")
    assert render_meta["openai/widgetAccessible"] is True
    assert render_meta["ui/resourceUri"] == template
    assert render_meta["ui"] == {
        "resourceUri": template,
        "visibility": ["model"],
    }
    invoking = render_meta["openai/toolInvocation/invoking"]
    invoked = render_meta["openai/toolInvocation/invoked"]
    assert isinstance(invoking, str)
    assert invoking.startswith("Rendering ")
    assert len(invoking.strip()) >= 20
    assert isinstance(invoked, str)
    assert invoked.startswith("Rendered ")
    assert len(invoked.strip()) >= 19

    for tool_name in (validate_tool, render_tool):
        annotations = tools_by_name[tool_name]["annotations"]
        assert annotations == {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }

    for tool_name in (save_tool, apply_tool):
        annotations = tools_by_name[tool_name]["annotations"]
        assert annotations == {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }


def _call_mcp_server(plugin: str, messages: list[dict[str, object]]) -> list[dict]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise chart MCP review tools.")
    server_path = ROOT / "plugins" / plugin / "mcp" / "server.cjs"
    completed = subprocess.run(
        [node, str(server_path), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


@pytest.mark.parametrize(
    (
        "plugin",
        "_render_tool",
        "_save_tool",
        "_apply_tool",
        "_item_type",
        "_widget_type",
    ),
    CHART_REVIEW_SERVERS,
)
def test_chart_review_resources_declare_local_widget_metadata(
    plugin: str,
    _render_tool: str,
    _save_tool: str,
    _apply_tool: str,
    _item_type: str,
    _widget_type: str,
) -> None:
    responses = {
        response["id"]: response
        for response in _call_mcp_server(
            plugin,
            [{"jsonrpc": "2.0", "id": 1, "method": "resources/list"}],
        )
    }
    resources = responses[1]["result"]["resources"]
    assert len(resources) == 1
    resource = resources[0]
    uri = resource["uri"]
    assert uri.startswith("ui://widget/")
    assert uri.endswith(".html")
    assert resource["mimeType"] == "text/html;profile=mcp-app"
    _assert_widget_resource_meta(resource["_meta"], uri)

    read_responses = {
        response["id"]: response
        for response in _call_mcp_server(
            plugin,
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "resources/read",
                    "params": {"uri": uri},
                }
            ],
        )
    }
    contents = read_responses[1]["result"]["contents"]
    assert len(contents) == 1
    content = contents[0]
    assert content["uri"] == uri
    assert content["mimeType"] == "text/html;profile=mcp-app"
    assert "<html" in content["text"]
    _assert_widget_resource_meta(content["_meta"], uri)


@pytest.mark.parametrize(
    ("plugin", "render_tool", "save_tool", "apply_tool", "_item_type", "_widget_type"),
    CHART_REVIEW_SERVERS,
)
def test_chart_review_tools_declare_safe_intent_annotations(
    plugin: str,
    render_tool: str,
    save_tool: str,
    apply_tool: str,
    _item_type: str,
    _widget_type: str,
) -> None:
    responses = {
        response["id"]: response
        for response in _call_mcp_server(
            plugin,
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}],
        )
    }
    _assert_review_tool_annotations(
        responses[1]["result"]["tools"],
        validate_tool=render_tool.replace("render_", "validate_"),
        render_tool=render_tool,
        save_tool=save_tool,
        apply_tool=apply_tool,
    )


def _minimal_review_payload(plugin: str, item_type: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": f"{plugin}-render-test",
        "review_type": f"{plugin.replace('-', '_')}_review",
        "items": [
            {
                "id": "item-1",
                "item_type": item_type,
                "title": "Review item",
                "source_path": "source.xlsx",
                "output_path": "chart.png",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "status": "needs_review",
                "data": {"status": "ready", "metric": "net_sales"},
                "source_records": [{"kind": "chart_audit", "status": "written"}],
            }
        ],
        "item_count": 1,
        "status": "ready_for_review",
        "summary": {},
    }


def _review_payload_with_items(
    plugin: str, item_type: str, item_count: int
) -> dict[str, object]:
    payload = _minimal_review_payload(plugin, item_type)
    template = payload["items"][0]
    payload["items"] = [
        {
            **template,
            "id": f"item-{index}",
            "title": f"Review item {index}",
        }
        for index in range(item_count)
    ]
    payload["item_count"] = item_count
    return payload


@pytest.mark.parametrize(
    ("plugin", "render_tool", "_save_tool", "apply_tool", "item_type", "widget_type"),
    CHART_REVIEW_SERVERS,
)
def test_chart_review_render_tools_validate_payload_before_rendering(
    plugin: str,
    render_tool: str,
    _save_tool: str,
    apply_tool: str,
    item_type: str,
    widget_type: str,
) -> None:
    review_payload = _minimal_review_payload(plugin, item_type)
    invalid_payload = {
        **review_payload,
        "item_count": review_payload["item_count"] + 1,
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": render_tool,
                "arguments": {"review_payload": review_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": render_tool,
                "arguments": {"review_payload": invalid_payload},
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    valid_result = responses[1]["result"]
    valid_payload = valid_result["structuredContent"]
    assert valid_payload["widget_type"] == widget_type
    assert valid_payload["review_payload"]["plugin"] == plugin
    assert valid_payload["review_payload"]["item_count"] == 1
    assert valid_payload["decision_policy"]["apply_tool"] == apply_tool
    assert valid_result["_meta"]["openai/outputTemplate"].startswith("ui://widget/")
    assert valid_result["_meta"]["openai/outputTemplate"].endswith(".html")
    assert valid_result["_meta"]["openai/widgetAccessible"] is True

    invalid_result = responses[2]["result"]
    assert invalid_result["isError"] is True
    assert "item_count must equal" in invalid_result["structuredContent"]["error"]


@pytest.mark.parametrize(
    (
        "plugin",
        "render_tool",
        "_save_tool",
        "_apply_tool",
        "item_type",
        "_widget_type",
    ),
    CHART_REVIEW_SERVERS,
)
def test_chart_review_render_tools_enforce_bounded_payload_policy(
    plugin: str,
    render_tool: str,
    _save_tool: str,
    _apply_tool: str,
    item_type: str,
    _widget_type: str,
) -> None:
    too_many_items_payload = _review_payload_with_items(
        plugin,
        item_type,
        CHART_REVIEW_ITEM_LIMIT + 1,
    )
    oversized_payload = _minimal_review_payload(plugin, item_type)
    oversized_payload["items"][0]["data"] = {
        "status": "ready",
        "oversized_note": "x" * 2_100_000,
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": render_tool,
                "arguments": {"review_payload": too_many_items_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": render_tool,
                "arguments": {"review_payload": oversized_payload},
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    too_many_items_result = responses[1]["result"]
    assert too_many_items_result["isError"] is True
    assert (
        "review_payload.items exceeds"
        in too_many_items_result["structuredContent"]["error"]
    )

    oversized_result = responses[2]["result"]
    assert oversized_result["isError"] is True
    assert "widget payload exceeds" in oversized_result["structuredContent"]["error"]


def _two_item_review_payload(plugin: str, item_type: str) -> dict[str, object]:
    payload = _minimal_review_payload(plugin, item_type)
    payload["items"] = [
        payload["items"][0],
        {
            **payload["items"][0],
            "id": "item-2",
            "title": "Review item 2",
            "data": {"status": "needs_source_data", "metric": "net_sales"},
            "source_records": [
                {"kind": "chart_audit", "status": "needs_source_data"}
            ],
        },
    ]
    payload["item_count"] = 2
    return payload


def _editable_review_payload(
    plugin: str, item_type: str, target_artifact: str = "chart_note.md"
) -> dict[str, object]:
    payload = _minimal_review_payload(plugin, item_type)
    payload["items"][0] = {
        **payload["items"][0],
        "id": "editable-1",
        "title": "Editable chart note",
        "output_path": target_artifact,
        "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
        "data": {"target_artifact": target_artifact, "status": "ready"},
    }
    return payload


@pytest.mark.parametrize(
    ("plugin", "_render_tool", "save_tool", "apply_tool", "item_type", "_widget_type"),
    CHART_REVIEW_SERVERS,
)
def test_chart_review_save_and_apply_tools_persist_review_results(
    tmp_path: Path,
    plugin: str,
    _render_tool: str,
    save_tool: str,
    apply_tool: str,
    item_type: str,
    _widget_type: str,
) -> None:
    output_dir = tmp_path / plugin
    review_payload = _minimal_review_payload(plugin, item_type)
    run_intake = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
    }
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": save_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": [
                        {
                            "item_id": "item-1",
                            "action": "accept",
                            "reviewer_note": "Reviewed in chart widget.",
                        }
                    ],
                    "decision_source": "chart_mcp_widget_test",
                    "reviewer": "pytest",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": {
                        "schema_version": "1.0",
                        "plugin": plugin,
                        "workflow": plugin,
                        "run_id": review_payload["run_id"],
                        "outputs": [
                            {"path": "chart.png", "kind": "png", "status": "written"}
                        ],
                        "caveats": ["Chart gallery caveat."],
                        "next_actions": ["Chart gallery next action."],
                        "status": "written_pending_review",
                    },
                    "decisions": [
                        {
                            "item_id": "item-1",
                            "action": "accept",
                            "reviewer_note": "Reviewed in chart widget.",
                        }
                    ],
                    "decision_source": "chart_mcp_widget_test",
                    "reviewer": "pytest",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": save_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": [{"item_id": "missing", "action": "accept"}],
                },
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert save_tool in tool_names
    assert apply_tool in tool_names

    save_result = responses[2]["result"]["structuredContent"]
    assert save_result["ok"] is True
    assert save_result["persisted"] is True
    assert save_result["decision_count"] == 1
    assert save_result["status"] == "reviewed"

    written = json.loads((output_dir / "ui_decisions.json").read_text(encoding="utf-8"))
    assert written["plugin"] == plugin
    assert written["decision_source"] == "chart_mcp_widget_test"
    assert written["reviewer"] == "pytest"
    assert written["decisions"][0]["item_id"] == "item-1"
    assert written["decisions"][0]["action"] == "accept"

    apply_result = responses[3]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["persisted"] is True
    assert apply_result["decision_count"] == 1
    assert apply_result["blocker_count"] == 0
    assert apply_result["application_status"] == "final_ready"

    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["plugin"] == plugin
    assert applied["application_status"] == "final_ready"
    assert applied["effects"][0]["item_id"] == "item-1"
    assert applied["effects"][0]["target_artifact"] == "chart.png"
    assert applied["effects"][0]["artifact_update"] == "decision_manifest_only"

    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert final_artifacts["status"] == "final_ready"
    assert final_artifacts["review_status"] == "final_ready"
    assert final_artifacts["caveats"] == ["Chart gallery caveat."]
    assert final_artifacts["blockers"] == []
    assert final_artifacts["next_actions"] == [
        "Chart gallery next action.",
        "Use final_artifacts.json as the reviewed artifact gallery for handoff.",
    ]
    output_paths = {output["path"] for output in final_artifacts["outputs"]}
    assert {"ui_decisions.json", "applied_decisions.json"} <= output_paths

    invalid_result = responses[4]["result"]
    assert invalid_result["isError"] is True
    assert "not in review_payload.items" in invalid_result["structuredContent"]["error"]


@pytest.mark.parametrize(
    ("plugin", "_render_tool", "save_tool", "apply_tool", "item_type", "_widget_type"),
    CHART_REVIEW_SERVERS,
)
def test_chart_review_save_and_apply_tools_handle_partial_and_blocked_states(
    tmp_path: Path,
    plugin: str,
    _render_tool: str,
    save_tool: str,
    apply_tool: str,
    item_type: str,
    _widget_type: str,
) -> None:
    partial_dir = tmp_path / plugin / "partial"
    blocked_dir = tmp_path / plugin / "blocked"
    review_payload = _two_item_review_payload(plugin, item_type)
    run_intake_partial = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(partial_dir),
    }
    run_intake_blocked = {**run_intake_partial, "output_dir": str(blocked_dir)}
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "outputs": [{"path": "chart.png", "kind": "png", "status": "written"}],
        "caveats": ["The chart payload is bounded."],
        "next_actions": ["Review remaining chart items."],
        "status": "written_pending_review",
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": save_tool,
                "arguments": {
                    "run_intake": run_intake_partial,
                    "review_payload": review_payload,
                    "decisions": [{"item_id": "item-1", "action": "accept"}],
                    "decision_source": "chart_partial_review_test",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake_partial,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [{"item_id": "item-1", "action": "accept"}],
                    "decision_source": "chart_partial_review_test",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake_blocked,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {"item_id": "item-1", "action": "accept"},
                        {
                            "item_id": "item-2",
                            "action": "mark_unclear",
                            "reviewer_note": "Chart source data is insufficient.",
                        },
                    ],
                    "decision_source": "chart_blocked_review_test",
                },
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    partial_save = responses[1]["result"]["structuredContent"]
    assert partial_save["ok"] is True
    assert partial_save["status"] == "partial_review"
    assert partial_save["decision_count"] == 1
    partial_ui_decisions = json.loads(
        (partial_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    assert partial_ui_decisions["status"] == "partial_review"
    assert partial_ui_decisions["item_count"] == 2

    partial_apply = responses[2]["result"]["structuredContent"]
    assert partial_apply["ok"] is True
    assert partial_apply["application_status"] == "partial_review_applied"
    assert partial_apply["blocker_count"] == 0
    partial_final = json.loads(
        (partial_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert partial_final["status"] == "partial_review_applied"
    assert partial_final["review_status"] == "partial_review_applied"
    assert partial_final["caveats"] == ["The chart payload is bounded."]
    assert partial_final["blockers"] == []
    assert partial_final["next_actions"] == [
        "Review remaining chart items.",
        "Complete remaining review decisions before final handoff.",
    ]

    blocked_apply = responses[3]["result"]["structuredContent"]
    assert blocked_apply["ok"] is True
    assert blocked_apply["application_status"] == "blocked"
    assert blocked_apply["blocker_count"] == 1
    blocked_applied = json.loads(
        (blocked_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert blocked_applied["application_status"] == "blocked"
    assert blocked_applied["effects"][1]["requires_followup"] is True
    assert (
        blocked_applied["effects"][1]["reviewer_note"]
        == "Chart source data is insufficient."
    )
    blocked_final = json.loads(
        (blocked_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert blocked_final["status"] == "blocked"
    assert blocked_final["review_status"] == "blocked"
    assert blocked_final["review_application"]["blocker_count"] == 1
    assert blocked_final["blockers"] == [
        {
            "item_id": "item-2",
            "item_type": item_type,
            "title": "Review item 2",
            "action": "mark_unclear",
            "status": "needs_source_data",
            "reviewer_note": "Chart source data is insufficient.",
            "requested_documents": [],
        }
    ]
    assert blocked_final["next_actions"] == [
        "Review remaining chart items.",
        "Resolve blocked review decisions before treating final artifacts as ready.",
    ]


@pytest.mark.parametrize(
    ("plugin", "_render_tool", "_save_tool", "apply_tool", "item_type", "_widget_type"),
    CHART_REVIEW_SERVERS,
)
def test_chart_review_apply_tools_update_safe_text_artifacts_for_edit_decisions(
    tmp_path: Path,
    plugin: str,
    _render_tool: str,
    _save_tool: str,
    apply_tool: str,
    item_type: str,
    _widget_type: str,
) -> None:
    output_dir = tmp_path / plugin / "edit"
    review_payload = _editable_review_payload(plugin, item_type)
    original_text = "Original chart note.\n"
    revised_text = "Revised chart note from the review UI.\nSecond line."
    output_dir.mkdir(parents=True)
    (output_dir / "chart_note.md").write_text(original_text, encoding="utf-8")
    run_intake = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "outputs": [{"path": "chart_note.md", "kind": "md", "status": "written"}],
        "status": "written_pending_review",
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {
                            "item_id": "editable-1",
                            "action": "edit",
                            "edit_value": revised_text,
                            "reviewer_note": "Replace with reviewer wording.",
                        }
                    ],
                    "decision_source": "chart_edit_revision_test",
                    "reviewer": "pytest",
                },
            },
        }
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    apply_result = responses[1]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["application_status"] == "final_ready"
    assert apply_result["revision_count"] == 1
    assert apply_result["target_update_count"] == 1
    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["target_update_count"] == 1
    assert applied["target_update_paths"] == ["chart_note.md"]
    assert applied["original_backup_paths"] == [
        "revisions/originals/chart_note__editable-1.md"
    ]
    effect = applied["effects"][0]
    assert effect["artifact_update"] == "target_artifact_updated"
    assert effect["original_artifact_backup"] == (
        "revisions/originals/chart_note__editable-1.md"
    )
    assert effect["revision_artifact"] == "revisions/chart_note__editable-1.md"
    assert effect["edit_value"] == revised_text
    assert (output_dir / "chart_note.md").read_text(encoding="utf-8") == revised_text
    assert (output_dir / "revisions/originals/chart_note__editable-1.md").read_text(
        encoding="utf-8"
    ) == original_text
    revision_path = output_dir / effect["revision_artifact"]
    assert revision_path.read_text(encoding="utf-8") == revised_text

    final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    output_paths = {output["path"] for output in final["outputs"]}
    assert {
        "chart_note.md",
        "revisions/chart_note__editable-1.md",
        "revisions/originals/chart_note__editable-1.md",
    } <= output_paths
    assert final["review_application"]["revision_count"] == 1
    assert final["review_application"]["target_update_count"] == 1
