from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.build_launch_report_pptx import (
    _looks_like_brief,
    _looks_like_insights,
    main,
)


def test_looks_like_brief_detects_brief_payload() -> None:
    payload = {
        "version": "launch_brief/1",
        "slides": [{"role": "cover", "title": "Title", "body": "Body"}],
    }

    assert _looks_like_brief(payload) is True


def test_looks_like_insights_detects_insights_payload() -> None:
    payload = {
        "version": "category_insights/1",
        "thesis": "Hydration survives audit.",
        "evidenceExamples": [
            {"product": "Hydrating Lip Stick"},
            {"product": "Daily Lip Tint"},
        ],
    }

    assert _looks_like_insights(payload) is True


def test_main_compiles_launch_brief_and_writes_outputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "launch_brief.json"
    output_dir = tmp_path / "out"
    input_path.write_text(
        json.dumps(
            {
                "version": "launch_brief/1",
                "deckName": "Launch Brief Script Test",
                "slides": [
                    {
                        "role": "cover",
                        "title": "Launch signal test",
                        "body": "A compact cover slide for a smoke test.",
                        "footerText": "Ulta | April 2026",
                    },
                    {
                        "role": "launch_tiles",
                        "title": "Included launches",
                        "body": "Two launch tiles are enough for a smoke test.",
                        "products": [
                            {
                                "brand": "Brand A",
                                "product": "Hydrating Lip Stick",
                                "body": "Hydrating stick launch.",
                                "tags": ["Hydrating"],
                            },
                            {
                                "brand": "Brand B",
                                "product": "Daily Lip Tint",
                                "body": "Tint launch.",
                                "tags": ["Tint"],
                            },
                        ],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.build_launch_report_pptx._parse_args",
        lambda: argparse.Namespace(
            input_path=input_path,
            input_format="auto",
            output_dir=output_dir,
            output_name="",
            source_package_dir=None,
            render_pngs=False,
            max_width=1600,
            max_height=900,
            log_level="INFO",
        ),
    )

    exit_code = main()

    assert exit_code == 0
    assert (output_dir / "launch_brief.json").exists()
    assert (output_dir / "report_payload.json").exists()
    assert (output_dir / "slides_pptx_spec.json").exists()
    assert (output_dir / "launch-brief-script-test.pptx").exists()


def test_main_writes_source_package_manifest_when_package_dir_is_provided(
    monkeypatch,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "launch_brief.json"
    output_dir = tmp_path / "out"
    package_dir = tmp_path / "packages" / "launch" / "ulta" / "blush"
    package_dir.mkdir(parents=True)
    (package_dir / "pack_manifest.json").write_text(
        json.dumps(
            {
                "retailer": "ulta",
                "category_key": "blush",
                "category_label": "blush",
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "summary.json").write_text(
        json.dumps({"retailer": "ulta", "category_label": "blush"}),
        encoding="utf-8",
    )
    (package_dir / "top_seller_pairs.csv").write_text(
        "bundle_label,pct_top_seller,pct_other\npink + powder,0.25,0.10\n",
        encoding="utf-8",
    )
    input_path.write_text(
        json.dumps(
            {
                "version": "launch_brief/1",
                "deckName": "Blush Source Manifest Test",
                "slides": [
                    {
                        "role": "cover",
                        "title": "Launch signal test",
                        "body": "A compact cover slide for a smoke test.",
                    },
                    {
                        "role": "launch_tiles",
                        "title": "Included launches",
                        "body": "Two launch tiles are enough for a smoke test.",
                        "products": [
                            {
                                "brand": "Brand A",
                                "product": "Blush A",
                                "body": "Powder blush.",
                            },
                            {
                                "brand": "Brand B",
                                "product": "Blush B",
                                "body": "Cream blush.",
                            },
                        ],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.build_launch_report_pptx._parse_args",
        lambda: argparse.Namespace(
            input_path=input_path,
            input_format="auto",
            output_dir=output_dir,
            output_name="",
            source_package_dir=package_dir,
            render_pngs=False,
            max_width=1600,
            max_height=900,
            log_level="INFO",
        ),
    )

    exit_code = main()

    assert exit_code == 0
    report_payload = json.loads((output_dir / "report_payload.json").read_text())
    source_package = report_payload["sourcePackage"]
    assert source_package["package_dir"] == str(package_dir.resolve())
    assert source_package["retailer"] == "ulta"
    assert source_package["category_key"] == "blush"
    assert len(source_package["content_fingerprint"]["content_sha256"]) == 64
    source_manifest = json.loads(
        (
            output_dir / "blush-source-manifest-test.launch_report_source.json"
        ).read_text()
    )
    assert source_manifest["source_package"] == source_package


def test_main_compiles_category_insights_and_writes_outputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "category_insights.json"
    output_dir = tmp_path / "out"
    input_path.write_text(
        json.dumps(
            {
                "version": "category_insights/1",
                "deckName": "Insights Script Test",
                "retailer": "Ulta",
                "category": "Lipstick",
                "thesis": "Hydration survives audit as the clearest launch signal.",
                "summary": "The cohort still leans comfort-led rather than novelty-led.",
                "evidenceExamples": [
                    {
                        "brand": "Brand A",
                        "product": "Hydrating Lip Stick",
                        "body": "Hydrating stick launch.",
                        "tags": ["Hydrating"],
                    },
                    {
                        "brand": "Brand B",
                        "product": "Daily Lip Tint",
                        "body": "Tint launch.",
                        "tags": ["Tint"],
                    },
                ],
                "survivingSignals": ["Hydrating over-indexes."],
                "droppedSignals": ["Refillable does not survive audit."],
                "bottomLine": "The signal is real, but smaller than the first read implied.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.build_launch_report_pptx._parse_args",
        lambda: argparse.Namespace(
            input_path=input_path,
            input_format="auto",
            output_dir=output_dir,
            output_name="",
            source_package_dir=None,
            render_pngs=False,
            max_width=1600,
            max_height=900,
            log_level="INFO",
        ),
    )

    exit_code = main()

    assert exit_code == 0
    assert (output_dir / "category_insights.json").exists()
    assert (output_dir / "launch_brief.json").exists()
    assert (output_dir / "report_payload.json").exists()
    assert (output_dir / "slides_pptx_spec.json").exists()
    assert (output_dir / "insights-script-test.pptx").exists()
