from __future__ import annotations

import json
import logging
from argparse import Namespace
from pathlib import Path

from scripts import validate_launch_reports as cli


def test_parse_args_enables_llm_review_by_default(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["validate_launch_reports.py"])

    args = cli._parse_args()

    assert args.llm_review is True


def test_parse_args_can_disable_llm_review(monkeypatch) -> None:
    monkeypatch.setattr(
        cli.sys, "argv", ["validate_launch_reports.py", "--no-llm-review"]
    )

    args = cli._parse_args()

    assert args.llm_review is False


def test_parse_args_can_refresh_reading_cache(monkeypatch) -> None:
    monkeypatch.setattr(
        cli.sys, "argv", ["validate_launch_reports.py", "--refresh-reading-cache"]
    )

    args = cli._parse_args()

    assert args.refresh_reading_cache is True


def test_stale_validation_artifacts_ignore_batch_and_current_outputs(
    tmp_path: Path,
) -> None:
    for name in [
        "batch.validation.json",
        "current_report.validation.json",
        "old_report.validation.json",
        "old_report.validation.md",
    ]:
        (tmp_path / name).write_text("{}", encoding="utf-8")

    stale_paths = cli._stale_validation_artifacts(tmp_path, {"current_report"})

    assert [path.name for path in stale_paths] == [
        "old_report.validation.json",
        "old_report.validation.md",
    ]


def test_rotate_existing_output_dir_moves_current_run_to_previous(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "validation"
    output_dir.mkdir()
    (output_dir / "batch.validation.json").write_text("current", encoding="utf-8")
    previous_dir = tmp_path / "validation_previous"
    previous_dir.mkdir()
    (previous_dir / "batch.validation.json").write_text("older", encoding="utf-8")

    rotated_dir = cli._rotate_existing_output_dir(output_dir)

    assert rotated_dir == previous_dir
    assert output_dir.exists()
    assert list(output_dir.iterdir()) == []
    assert (previous_dir / "batch.validation.json").read_text() == "current"


def test_rotate_existing_output_dir_keeps_previous_when_current_is_empty(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "validation"
    output_dir.mkdir()
    previous_dir = tmp_path / "validation_previous"
    previous_dir.mkdir()
    (previous_dir / "batch.validation.json").write_text("baseline", encoding="utf-8")

    rotated_dir = cli._rotate_existing_output_dir(output_dir)

    assert rotated_dir is None
    assert output_dir.exists()
    assert (previous_dir / "batch.validation.json").read_text() == "baseline"


def test_main_validates_single_pdf_and_writes_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "validation"

    monkeypatch.setattr(
        cli,
        "_parse_args",
        lambda: Namespace(
            pdf=pdf_path,
            launch_reports_dir=tmp_path,
            output_dir=output_dir,
            package_root=[],
            lang="eng",
            strict=False,
            llm_review=False,
            llm_review_max_items=24,
            refresh_reading_cache=False,
            log_level="INFO",
        ),
    )
    monkeypatch.setattr(
        cli,
        "validate_launch_report_pdf",
        lambda *args, **kwargs: {
            "status": "pass_with_warnings",
            "pdf_path": str(pdf_path.resolve()),
            "package_dir": str((tmp_path / "pack").resolve()),
            "resolver": {"status": "manual"},
            "summary": {
                "verified_count": 3,
                "contradicted_count": 0,
                "partially_backed_count": 0,
                "weakly_backed_count": 0,
                "unresolved_count": 2,
                "claim_count": 3,
                "slide_count": 2,
            },
            "claims": [],
            "unresolved": [],
            "scope_note": "scope",
        },
    )

    exit_code = cli.main()

    assert exit_code == 0
    assert (
        json.loads((output_dir / "lipstick.validation.json").read_text())["status"]
        == "pass_with_warnings"
    )
    assert "Launch Report Validation" in (
        output_dir / "lipstick.validation.md"
    ).read_text(encoding="utf-8")


def test_main_warns_when_package_fingerprint_changes_since_previous(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "validation"
    output_dir.mkdir()
    old_hash = "a" * 64
    new_hash = "b" * 64
    (output_dir / "bronzer.validation.json").write_text(
        json.dumps(
            {
                "pdf_path": str(pdf_path.resolve()),
                "package": {"content_fingerprint": {"content_sha256": old_hash}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_parse_args",
        lambda: Namespace(
            pdf=pdf_path,
            launch_reports_dir=tmp_path,
            output_dir=output_dir,
            package_root=[],
            brief_root=[],
            lang="eng",
            strict=False,
            llm_review=False,
            llm_review_max_items=24,
            refresh_reading_cache=False,
            log_level="INFO",
        ),
    )
    monkeypatch.setattr(
        cli,
        "validate_launch_report_pdf",
        lambda *args, **kwargs: {
            "status": "pass",
            "pdf_path": str(pdf_path.resolve()),
            "package_dir": str((tmp_path / "pack").resolve()),
            "package": {
                "retailer": "ulta",
                "category_key": "bronzer",
                "category_label": "bronzer",
                "content_fingerprint": {"content_sha256": new_hash},
            },
            "resolver": {"status": "matched"},
            "summary": {
                "verified_count": 1,
                "contradicted_count": 0,
                "partially_backed_count": 0,
                "weakly_backed_count": 0,
                "unresolved_count": 0,
                "claim_count": 1,
                "slide_count": 1,
            },
            "reading_quality": {"status": "read_ok"},
            "claims": [],
            "unresolved": [],
            "scope_note": "scope",
        },
    )

    caplog.set_level(logging.WARNING)
    exit_code = cli.main()

    assert exit_code == 0
    assert "bronzer.pdf package fingerprint changed" in caplog.text
    assert old_hash in caplog.text
    assert new_hash in caplog.text


def test_log_report_diagnostics_warns_on_generation_package_mismatch(caplog) -> None:
    caplog.set_level(logging.WARNING)
    old_hash = "c" * 64
    new_hash = "d" * 64

    cli._log_report_diagnostics(
        {
            "status": "pass",
            "pdf_path": "/tmp/bronzer.pdf",
            "generation_source": {
                "status": "package_mismatch",
                "generation_package_content_sha256": old_hash,
                "current_package_content_sha256": new_hash,
            },
        }
    )

    assert "bronzer.pdf was generated from package hash" in caplog.text
    assert old_hash in caplog.text
    assert new_hash in caplog.text


def test_main_validates_batch_and_writes_batch_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_dir = tmp_path / "launch_reports"
    report_dir.mkdir()
    for stem in ("example_brand_a", "example_brand_b", "example_brand_c"):
        (report_dir / f"{stem}.pdf").write_bytes(b"%PDF-1.4\n")
    (report_dir / "notes.txt").write_text("not a report", encoding="utf-8")
    nested_dir = report_dir / "validation"
    nested_dir.mkdir()
    (nested_dir / "old_report.pdf").write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "validation"

    monkeypatch.setattr(
        cli,
        "_parse_args",
        lambda: Namespace(
            pdf=None,
            launch_reports_dir=report_dir,
            output_dir=output_dir,
            package_root=[],
            lang="eng",
            strict=False,
            llm_review=False,
            llm_review_max_items=24,
            refresh_reading_cache=False,
            log_level="INFO",
        ),
    )
    captured_names: list[str] = []

    def _fake_validate_launch_report_batch(pdf_paths, *args, **kwargs):
        paths = list(pdf_paths)
        captured_names.extend(path.name for path in paths)
        return {
            "summary": {
                "report_count": len(paths),
                "pass_count": len(paths) - 1,
                "pass_with_warnings_count": 0,
                "fail_count": 1,
                "unresolved_package_count": 0,
            },
            "reports": [
                {
                    "status": "fail" if index == len(paths) - 1 else "pass",
                    "pdf_path": str(path.resolve()),
                    "package_dir": str((tmp_path / f"pack{index}").resolve()),
                    "resolver": {"status": "matched"},
                    "summary": {
                        "verified_count": 2,
                        "contradicted_count": 1 if index == len(paths) - 1 else 0,
                        "partially_backed_count": 0,
                        "weakly_backed_count": 0,
                        "unresolved_count": 0,
                        "claim_count": 3 if index == len(paths) - 1 else 2,
                        "slide_count": 1,
                    },
                    "claims": [],
                    "unresolved": [],
                    "scope_note": "scope",
                }
                for index, path in enumerate(paths)
            ],
        }

    monkeypatch.setattr(
        cli, "validate_launch_report_batch", _fake_validate_launch_report_batch
    )

    exit_code = cli.main()

    assert exit_code == 0
    assert captured_names == [
        "example_brand_a.pdf",
        "example_brand_b.pdf",
        "example_brand_c.pdf",
    ]
    batch_payload = json.loads((output_dir / "batch.validation.json").read_text())
    assert batch_payload["summary"]["report_count"] == 3
    assert (output_dir / "example_brand_a.validation.json").exists()
    assert (output_dir / "example_brand_b.validation.json").exists()
    assert (output_dir / "example_brand_c.validation.json").exists()
    assert not (output_dir / "old_report.validation.json").exists()


def test_main_stops_when_openai_reading_step_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "validation"

    monkeypatch.setattr(
        cli,
        "_parse_args",
        lambda: Namespace(
            pdf=pdf_path,
            launch_reports_dir=tmp_path,
            output_dir=output_dir,
            package_root=[],
            brief_root=[],
            lang="eng",
            strict=False,
            llm_review=False,
            llm_review_max_items=24,
            refresh_reading_cache=False,
            log_level="INFO",
        ),
    )

    def _raise_openai_failure(*args, **kwargs):
        raise cli.SlideOcrOpenAIError(
            "OpenAI call failed during slide OCR semantic correction."
        )

    monkeypatch.setattr(cli, "validate_launch_report_pdf", _raise_openai_failure)

    exit_code = cli.main()

    assert exit_code == 2
    assert not (output_dir / "bronzer.validation.json").exists()


def test_main_stops_when_openai_wrapper_initialization_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "serum.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "validation"

    monkeypatch.setattr(
        cli,
        "_parse_args",
        lambda: Namespace(
            pdf=pdf_path,
            launch_reports_dir=tmp_path,
            output_dir=output_dir,
            package_root=[],
            brief_root=[],
            lang="eng",
            strict=False,
            llm_review=True,
            llm_review_max_items=24,
            refresh_reading_cache=False,
            log_level="INFO",
        ),
    )

    def _raise_openai_failure(*args, **kwargs):
        raise cli.LaunchValidationOpenAIError(
            "OpenAI wrapper initialization failed before launch validation."
        )

    monkeypatch.setattr(cli, "_llm_wrapper", _raise_openai_failure)

    exit_code = cli.main()

    assert exit_code == 2
    assert not (output_dir / "serum.validation.json").exists()
