from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "plugins" / "attribute-reporting" / "scripts" / "browser_qa.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "attribute_reporting_browser_qa_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qa = _load_module()


def _metrics() -> dict[str, object]:
    return {
        "horizontalOverflow": False,
        "document": {
            "clientWidth": 390,
            "scrollWidth": 390,
            "clientHeight": 844,
            "scrollHeight": 2400,
        },
        "brokenImages": [],
        "unsafeAssets": [],
        "uncontainedWideTables": [],
        "missingRequiredElements": [],
        "unsafeProductLinks": [],
    }


def test_assess_browser_metrics_passes_mechanical_report_contract() -> None:
    findings = qa.assess_browser_metrics(_metrics(), viewport_name="mobile")

    assert len(findings) == 7
    assert {item["status"] for item in findings} == {"pass"}
    assert {item["code"] for item in findings} == {
        "browser.mobile.horizontal_overflow",
        "browser.mobile.local_images",
        "browser.mobile.asset_locality",
        "browser.mobile.table_scrolling",
        "browser.mobile.required_elements",
        "browser.mobile.product_links",
        "browser.mobile.runtime",
    }


def test_assess_browser_metrics_materializes_every_failure() -> None:
    metrics = _metrics()
    metrics.update(
        {
            "horizontalOverflow": True,
            "brokenImages": ["assets/products/missing.png"],
            "unsafeAssets": [
                {"kind": "image", "value": "https://cdn.example.test/image.png"}
            ],
            "uncontainedWideTables": [{"index": 1, "reason": "missing"}],
            "missingRequiredElements": [".verdict-slot"],
            "unsafeProductLinks": [{"href": "javascript:void(0)"}],
        }
    )

    findings = qa.assess_browser_metrics(
        metrics,
        viewport_name="desktop",
        console_errors=["console failed"],
        page_errors=["page failed"],
    )

    assert {item["status"] for item in findings} == {"fail"}
    assert findings[-1]["details"] == ["console failed", "page failed"]


def test_assess_browser_metrics_allows_normal_vertical_document_scroll() -> None:
    metrics = _metrics()
    metrics["document"] = {
        "clientWidth": 1440,
        "scrollWidth": 1440,
        "clientHeight": 1000,
        "scrollHeight": 9000,
    }

    findings = qa.assess_browser_metrics(metrics, viewport_name="desktop")

    horizontal = next(
        item for item in findings if item["code"].endswith("horizontal_overflow")
    )
    assert horizontal["status"] == "pass"
