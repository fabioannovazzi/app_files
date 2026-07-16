from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_png_example_artifacts as audit


def test_parse_args_honors_explicit_paths(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    output_json = tmp_path / "out.json"

    args = audit._parse_args(
        ["--source-root", str(source_root), "--output-json", str(output_json)]
    )

    assert args.source_root == source_root
    assert args.output_json == output_json


def test_classifies_current_legacy_plotly_png(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "period"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()
    (run_dir / "year_over_year_column.png").write_bytes(b"png")
    (run_dir / "period_comparison_audit.json").write_text(
        json.dumps(
            {
                "legacy_runtime": {
                    "chart_audits": {
                        "year_over_year_column": {
                            "status": "written",
                            "exports": [
                                {
                                    "artifact": "year_over_year_column.png",
                                    "renderer": "legacy_plotly+kaleido",
                                }
                            ],
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rows = audit.audit_png_example_artifacts(source_root, gallery_dir)

    assert len(rows) == 1
    assert rows[0].current_export_class == "legacy_plotly_png"
    assert rows[0].png_residue == "current_source_png"


def test_classifies_native_plugin_png(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "set_overlap"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()
    (run_dir / "venn.png").write_bytes(b"png")
    (run_dir / "set_overlap_audit.json").write_text(
        json.dumps(
            {
                "charts": {
                    "venn": {
                        "artifacts": ["venn.png"],
                        "renderer": "matplotlib_venn",
                        "status": "written",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rows = audit.audit_png_example_artifacts(source_root, gallery_dir)

    assert len(rows) == 1
    assert rows[0].current_export_class == "native_plugin_png"
    assert rows[0].png_residue == "current_source_png"


def test_classifies_html_only_with_stale_source_and_gallery_png(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "mix_comparison"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()
    (run_dir / "stacked_column.html").write_text("<html></html>", encoding="utf-8")
    (run_dir / "stacked_column.png").write_bytes(b"stale-source")
    (gallery_dir / "mix_comparison__stacked_column.png").write_bytes(b"gallery")
    (run_dir / "mix_contribution_audit.json").write_text(
        json.dumps(
            {
                "legacy_runtime": {
                    "chart_audits": {
                        "stacked_column": {
                            "status": "written",
                            "exports": [
                                {
                                    "artifact": "stacked_column.html",
                                    "renderer": "legacy_plotly+html_only",
                                    "plotly_export_error": "chrome failed",
                                    "screenshot_error": "screenshot failed",
                                }
                            ],
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rows = audit.audit_png_example_artifacts(source_root, gallery_dir)

    assert len(rows) == 1
    assert rows[0].current_export_class == "failed_html_only_output"
    assert rows[0].png_residue == "stale_source_png_and_gallery_png"
    assert rows[0].plotly_export_error == "chrome failed"
    assert rows[0].screenshot_error == "screenshot failed"


def test_classifies_html_only_without_any_png(tmp_path: Path) -> None:
    source_root = tmp_path / "runs" / "png_examples"
    run_dir = source_root / "scatter"
    gallery_dir = source_root / "png-gallery"
    run_dir.mkdir(parents=True)
    gallery_dir.mkdir()
    (run_dir / "scatter.html").write_text("<html></html>", encoding="utf-8")
    (run_dir / "scatter_bubble_audit.json").write_text(
        json.dumps(
            {
                "legacy_runtime": {
                    "chart_audits": {
                        "scatter": {
                            "status": "written",
                            "exports": [
                                {
                                    "artifact": "scatter.html",
                                    "renderer": "legacy_plotly+html_only",
                                }
                            ],
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rows = audit.audit_png_example_artifacts(source_root, gallery_dir)

    assert len(rows) == 1
    assert rows[0].current_export_class == "failed_html_only_output"
    assert rows[0].png_residue == "no_png"
