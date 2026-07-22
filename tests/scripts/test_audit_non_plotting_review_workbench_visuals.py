from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "audit_non_plotting_review_workbench_visuals.py"


spec = importlib.util.spec_from_file_location(
    "audit_non_plotting_review_workbench_visuals", SCRIPT_PATH
)
assert spec is not None
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def test_discover_targets_finds_workbench_html_and_item_count(tmp_path: Path) -> None:
    asset_dir = tmp_path / "plugins" / "demo-review" / "assets"
    asset_dir.mkdir(parents=True)
    (asset_dir / "review-workbench-adapter.json").write_text(
        json.dumps(
            {
                "plugin": "demo-review",
                "demo": {
                    "items": [
                        {"id": "row-1"},
                        {"id": "row-2"},
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (asset_dir / "demo-review-widget.html").write_text(
        "<!doctype html><title>Demo</title>",
        encoding="utf-8",
    )

    targets = audit.discover_targets(tmp_path)

    assert len(targets) == 1
    assert targets[0].plugin == "demo-review"
    assert targets[0].item_count == 2
    assert targets[0].adapter["plugin"] == "demo-review"
    assert targets[0].html_path.name == "demo-review-widget.html"


def test_visual_report_marks_horizontal_overflow_as_failure() -> None:
    viewport = audit.VisualViewportReport(
        viewport="mobile",
        language="en",
        width=390,
        height=844,
        row_count=2,
        decision_count=4,
        body_text_length=2000,
        document_scroll_width=640,
        viewport_width=390,
        issues=[
            audit.VisualIssue(
                severity="high",
                code="horizontal_overflow",
                message="Page has horizontal overflow.",
            )
        ],
    )
    report = audit.VisualPluginReport(
        plugin="demo-review",
        html_path="plugins/demo-review/assets/demo-review-widget.html",
        item_count=2,
        viewports=[viewport],
    )

    assert viewport.status == "needs_attention"
    assert report.status == "needs_attention"
    assert audit._has_failure([report], "high") is True


def test_parse_languages_accepts_supported_comma_list() -> None:
    assert audit._parse_languages("en,it,fr,de,es") == (
        "en",
        "it",
        "fr",
        "de",
        "es",
    )


def test_localized_payload_sets_run_language(tmp_path: Path) -> None:
    asset_dir = tmp_path / "plugins" / "demo-review" / "assets"
    asset_dir.mkdir(parents=True)
    adapter = {
        "plugin": "demo-review",
        "widgetType": "demo_review",
        "reviewTitle": "Demo Review",
        "saveTool": "save_demo",
        "applyTool": "apply_demo",
        "demo": {
            "review_type": "demo_review",
            "items": [{"id": "row-1", "recommended_action": "accept"}],
        },
    }
    adapter_path = asset_dir / "review-workbench-adapter.json"
    adapter_path.write_text(json.dumps(adapter) + "\n", encoding="utf-8")
    html_path = asset_dir / "demo-review-widget.html"
    html_path.write_text("<!doctype html><title>Demo</title>", encoding="utf-8")
    target = audit.discover_targets(tmp_path)[0]

    payload = audit._localized_payload(target, "it")

    assert payload["widget_type"] == "demo_review"
    assert payload["run_intake"]["language"] == "it"
    assert payload["review_payload"]["summary"]["language"] == "it"
    assert payload["review_payload"]["item_count"] == 1
    assert payload["decision_policy"]["save_tool"] == "save_demo"
