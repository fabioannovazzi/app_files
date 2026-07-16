from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "plugins" / "clara" / "skills" / "html-deck"
GALLERY_SCRIPT = SKILL_ROOT / "scripts" / "build_layout_gallery.py"
LEDGER_SCRIPT = SKILL_ROOT / "scripts" / "content_ledger.py"
REGISTRY_PATH = SKILL_ROOT / "assets" / "layout-library" / "registry.json"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gallery = load_module(GALLERY_SCRIPT, "clara_html_deck_layout_gallery_test")
content_ledger = load_module(LEDGER_SCRIPT, "clara_html_deck_gallery_ledger_test")


def test_gallery_fixture_covers_every_layout_at_representative_density() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    plan = gallery.gallery_deck_plan()
    slides = plan["slides"]
    slides_by_layout = {slide["layout_id"]: slide for slide in slides}

    registered_ids = [layout["id"] for layout in registry["layouts"]]
    assert [slide["layout_id"] for slide in slides] == registered_ids
    assert len(slides_by_layout) == 15
    for layout in registry["layouts"]:
        slide = slides_by_layout[layout["id"]]
        assert slide["title"] == slide["slots"][layout["headline_slot"]]
        assert slide["source_refs"] == [gallery.SOURCE_ID]
        assert slide["claim_refs"] == [f"claim-gallery-{layout['id']}"]
        for slot_name, slot_schema in layout["slots"].items():
            if slot_schema["type"] == "items":
                assert len(slide["slots"][slot_name]) == slot_schema["max_items"]

    visual = slides_by_layout["visual-takeaway"]["slots"]["visual"]
    assert visual["renderer"] == "data_visual"
    assert visual["spec"]["type"] == "line"
    assert slides_by_layout["image-led"]["slots"]["image_src"].startswith(
        "data:image/svg+xml;base64,"
    )


def test_gallery_content_ledger_matches_every_slide_and_claim() -> None:
    plan = gallery.gallery_deck_plan()
    ledger = gallery.gallery_content_ledger(plan)

    normalized = content_ledger.validate_content_ledger(
        ledger,
        slide_ids=[slide["id"] for slide in plan["slides"]],
    )

    claim_ids = {
        claim["id"] for slide in normalized["slides"] for claim in slide["claims"]
    }
    assert len(normalized["slides"]) == 15
    assert claim_ids == {
        claim_id for slide in plan["slides"] for claim_id in slide["claim_refs"]
    }
    assert normalized["sources"][0]["publish_locator"] is False


def test_gallery_composes_and_builds_every_layout_to_standalone_html(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "layout-gallery"

    manifest = gallery.build_layout_gallery(output_dir, run_browser=False)

    index_path = output_dir / manifest["files"]["index_html"]
    html_text = index_path.read_text(encoding="utf-8")
    build_report = json.loads(
        (output_dir / manifest["files"]["build_report"]).read_text(encoding="utf-8")
    )
    written_manifest = json.loads(
        (output_dir / "layout-previews.json").read_text(encoding="utf-8")
    )
    assert manifest["result"] == "pass"
    assert manifest["static_build"]["result"] == "pass"
    assert manifest["compose"]["slide_count"] == 15
    assert build_report["result"] == "pass"
    assert html_text.count("data-layout-id=") == 15
    assert 'data-qa-role="data-visual"' in html_text
    assert "data:image/svg+xml;base64," in html_text
    assert 'id="claraContentLedger"' in html_text
    assert set(manifest["layouts"]) == set(manifest["registered_layout_ids"])
    assert all(not item["previews"] for item in manifest["layouts"].values())
    assert written_manifest == manifest
    assert (output_dir / manifest["files"]["package"]).stat().st_size > 1_000


def test_gallery_browser_qa_maps_all_three_previews_when_chromium_is_available(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "browser-layout-gallery"

    manifest = gallery.build_layout_gallery(output_dir, run_browser=True)

    if manifest["result"] == "blocked":
        pytest.skip("No runnable Chrome or Playwright Chromium is available.")
    assert manifest["result"] == "pass", json.dumps(manifest, indent=2)
    assert manifest["browser_qa"]["viewports"] == list(gallery.GALLERY_VIEWPORTS)
    assert all(
        set(item["previews"]) == {"presentation", "compact", "mobile"}
        for item in manifest["layouts"].values()
    )
    assert all(
        (output_dir / screenshot).is_file()
        for item in manifest["layouts"].values()
        for screenshot in item["previews"].values()
    )
    assert (output_dir / manifest["files"]["screenshot_index"]).is_file()
