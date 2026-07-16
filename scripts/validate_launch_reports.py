from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.slides.launch_pdf_validator import (
    DEFAULT_LAUNCH_BRIEF_ROOTS,
    DEFAULT_LAUNCH_PACKAGE_ROOTS,
    LaunchValidationOpenAIError,
    validate_launch_report_batch,
    validate_launch_report_pdf,
    write_launch_report_batch_artifacts,
    write_launch_report_validation_artifacts,
)
from src.slides.layout_service import SlideLayoutOpenAIError
from src.slides.ocr_service import SlideOcrOpenAIError

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
OPENAI_FAILURES = (
    LaunchValidationOpenAIError,
    SlideLayoutOpenAIError,
    SlideOcrOpenAIError,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate launch-report PDFs against their source packages."
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=None,
        help="Validate one PDF instead of the whole launch_reports directory.",
    )
    parser.add_argument(
        "--launch-reports-dir",
        type=Path,
        default=Path("launch_reports"),
        help="Directory containing the final launch-report PDFs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("launch_reports/validation"),
        help="Directory where validation artifacts should be written.",
    )
    parser.add_argument(
        "--package-root",
        action="append",
        type=Path,
        default=None,
        help="Additional package root to scan. Can be provided multiple times.",
    )
    parser.add_argument(
        "--brief-root",
        action="append",
        type=Path,
        default=None,
        help="Child markdown brief root for parent summary reports. Can be provided multiple times.",
    )
    parser.add_argument(
        "--lang",
        default="eng",
        help="OCR language label. Defaults to eng.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any validated report fails.",
    )
    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument(
        "--llm-review",
        dest="llm_review",
        action="store_true",
        default=True,
        help=(
            "Attach a non-authoritative LLM advisory review for unresolved "
            "and warning items. Enabled by default; deterministic status is unchanged."
        ),
    )
    llm_group.add_argument(
        "--no-llm-review",
        dest="llm_review",
        action="store_false",
        help="Skip the non-authoritative LLM advisory review.",
    )
    parser.add_argument(
        "--llm-review-max-items",
        type=int,
        default=24,
        help="Maximum deterministic leftover items to send to the LLM review.",
    )
    parser.add_argument(
        "--refresh-reading-cache",
        action="store_true",
        help="Rebuild cached slide reading artifacts before validation.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    return parser.parse_args()


def _package_roots(args: argparse.Namespace) -> tuple[Path, ...]:
    if args.package_root:
        return tuple(args.package_root)
    return tuple(DEFAULT_LAUNCH_PACKAGE_ROOTS)


def _brief_roots(args: argparse.Namespace) -> tuple[Path, ...]:
    brief_root = getattr(args, "brief_root", None)
    if brief_root:
        return tuple(brief_root)
    return tuple(DEFAULT_LAUNCH_BRIEF_ROOTS)


def _report_paths(args: argparse.Namespace) -> list[Path]:
    if args.pdf is not None:
        return [args.pdf.expanduser().resolve()]
    root = args.launch_reports_dir.expanduser().resolve()
    return sorted(path for path in root.glob("*.pdf") if path.is_file())


def _stale_validation_artifacts(
    output_dir: Path, current_stems: set[str]
) -> list[Path]:
    """Return old per-report validation artifacts outside the current run."""

    stale_paths: list[Path] = []
    for path in sorted(output_dir.glob("*.validation.*")):
        artifact_stem = path.name.split(".validation.", 1)[0]
        if artifact_stem == "batch" or artifact_stem in current_stems:
            continue
        stale_paths.append(path)
    return stale_paths


def _log_stale_validation_artifacts(output_dir: Path, pdf_paths: list[Path]) -> None:
    stale_paths = _stale_validation_artifacts(
        output_dir,
        {path.stem for path in pdf_paths},
    )
    if not stale_paths:
        return
    examples = ", ".join(path.name for path in stale_paths[:5])
    LOGGER.warning(
        "Validation output directory contains %s stale per-report artifact(s) "
        "for PDFs outside this run: %s%s. The current batch.validation.json is "
        "the source of truth for this run.",
        len(stale_paths),
        examples,
        "..." if len(stale_paths) > 5 else "",
    )


def _previous_output_dir(output_dir: Path) -> Path:
    return output_dir.with_name(f"{output_dir.name}_previous")


def _rotate_existing_output_dir(output_dir: Path) -> Path | None:
    """Move a non-empty output folder aside as the previous validation run."""

    if not output_dir.exists():
        return None
    if output_dir.is_dir() and not any(output_dir.iterdir()):
        return None

    previous_dir = _previous_output_dir(output_dir)
    if previous_dir.exists():
        if previous_dir.is_dir():
            shutil.rmtree(previous_dir)
        else:
            previous_dir.unlink()
    output_dir.rename(previous_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return previous_dir


def _llm_wrapper(args: argparse.Namespace) -> object | None:
    if not args.llm_review:
        return None
    from modules.llm.llm_call_wrapper import init_llm_wrapper
    from modules.utilities.session_context import SessionContext

    session = SessionContext.from_state({})
    try:
        init_llm_wrapper("", session=session)
    except Exception as exc:
        raise LaunchValidationOpenAIError(
            "OpenAI wrapper initialization failed before launch validation."
        ) from exc
    return session.state["llm_wrapper"]


def _truncate_log_text(value: object, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _summary_int(report: dict[str, object], key: str) -> int:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return 0
    value = summary.get(key)
    return int(value) if isinstance(value, int) else 0


def _report_package_content_hash(report: dict[str, object]) -> str:
    package = report.get("package")
    if not isinstance(package, dict):
        return ""
    fingerprint = package.get("content_fingerprint")
    if not isinstance(fingerprint, dict):
        return ""
    value = fingerprint.get("content_sha256")
    return str(value or "").strip()


def _load_previous_report_payload(
    previous_output_dir: Path | None,
    report: dict[str, object],
) -> dict[str, object] | None:
    if previous_output_dir is None:
        return None
    pdf_path = report.get("pdf_path")
    if not isinstance(pdf_path, str) or not pdf_path:
        return None
    previous_path = previous_output_dir / f"{Path(pdf_path).stem}.validation.json"
    if not previous_path.exists():
        return None
    try:
        payload = json.loads(previous_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning(
            "Could not read previous validation artifact %s: %s",
            previous_path,
            exc,
        )
        return None
    return payload if isinstance(payload, dict) else None


def _log_package_fingerprint_drift(
    report: dict[str, object],
    previous_output_dir: Path | None,
) -> None:
    current_hash = _report_package_content_hash(report)
    if not current_hash:
        return
    previous_report = _load_previous_report_payload(previous_output_dir, report)
    if previous_report is None:
        return
    previous_hash = _report_package_content_hash(previous_report)
    if not previous_hash or previous_hash == current_hash:
        return
    pdf_name = Path(str(report.get("pdf_path") or "unknown")).name
    LOGGER.warning(
        "%s package fingerprint changed since previous validation: previous=%s "
        "current=%s. Numeric contradictions may reflect package/report drift.",
        pdf_name,
        previous_hash,
        current_hash,
    )


def _log_generation_package_fingerprint_mismatch(report: dict[str, object]) -> None:
    generation_source = report.get("generation_source")
    if not isinstance(generation_source, dict):
        return
    if generation_source.get("status") != "package_mismatch":
        return
    pdf_name = Path(str(report.get("pdf_path") or "unknown")).name
    LOGGER.warning(
        "%s was generated from package hash %s but validated against current "
        "package hash %s. Rebuild either the report or the package set before "
        "treating numeric contradictions as report errors.",
        pdf_name,
        generation_source.get("generation_package_content_sha256", "unknown"),
        generation_source.get("current_package_content_sha256", "unknown"),
    )


def _log_report_diagnostics(report: dict[str, object]) -> None:
    _log_generation_package_fingerprint_mismatch(report)
    status = str(report.get("status") or "unknown")
    if status == "pass":
        return
    pdf_name = Path(str(report.get("pdf_path") or "unknown")).name
    resolver = (
        report.get("resolver") if isinstance(report.get("resolver"), dict) else {}
    )
    reading_quality = report.get("reading_quality")
    reading_status = (
        str(reading_quality.get("status") or "unknown")
        if isinstance(reading_quality, dict)
        else "unknown"
    )
    LOGGER.warning(
        "%s -> %s: verified=%s contradicted=%s unresolved=%s images=%s reading_quality=%s "
        "resolver=%s",
        pdf_name,
        status,
        _summary_int(report, "verified_count"),
        _summary_int(report, "contradicted_count"),
        _summary_int(report, "unresolved_count"),
        _summary_int(report, "image_region_count"),
        reading_status,
        resolver.get("status", "unknown"),
    )
    if isinstance(reading_quality, dict) and reading_status != "read_ok":
        flagged_slides = (
            reading_quality.get("flagged_slides")
            if isinstance(reading_quality.get("flagged_slides"), list)
            else []
        )
        for slide in flagged_slides[:3]:
            if not isinstance(slide, dict):
                continue
            reasons = (
                slide.get("reasons") if isinstance(slide.get("reasons"), list) else []
            )
            LOGGER.warning(
                "%s reading issue slide %s: %s",
                pdf_name,
                slide.get("slide_number", "?"),
                "; ".join(str(reason) for reason in reasons) or "no reason recorded",
            )

    if reading_status == "not_run" and resolver:
        root_details = (
            resolver.get("package_roots")
            if isinstance(resolver.get("package_roots"), list)
            else []
        )
        root_summary = ", ".join(
            (
                f"{root.get('path')} exists={root.get('exists')}"
                if isinstance(root, dict)
                else str(root)
            )
            for root in root_details[:3]
        )
        LOGGER.warning(
            "%s reading skipped before OCR: resolver=%s reason=%s normalized_key=%s "
            "retailer_hint=%s discovered_packages=%s%s",
            pdf_name,
            resolver.get("status", "unknown"),
            resolver.get("reason", "unknown"),
            resolver.get("normalized_key", ""),
            resolver.get("retailer_hint", ""),
            resolver.get("discovered_package_count", ""),
            f" roots=[{root_summary}]" if root_summary else "",
        )
        discovered_packages = (
            resolver.get("discovered_packages")
            if isinstance(resolver.get("discovered_packages"), list)
            else []
        )
        for package in discovered_packages[:5]:
            if not isinstance(package, dict):
                continue
            LOGGER.warning(
                "%s discovered package: retailer=%s category_key=%s "
                "category_label=%s path=%s",
                pdf_name,
                package.get("retailer", ""),
                package.get("category_key", ""),
                package.get("category_label", ""),
                package.get("path", ""),
            )

    unresolved = (
        report.get("unresolved") if isinstance(report.get("unresolved"), list) else []
    )
    for item in unresolved[:2]:
        if not isinstance(item, dict):
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        LOGGER.warning(
            "%s unresolved %s: %s",
            pdf_name,
            item.get("claim_family", "unknown"),
            _truncate_log_text(details.get("message") or item.get("claim_text")),
        )

    claims = report.get("claims") if isinstance(report.get("claims"), list) else []
    contradicted = [
        claim
        for claim in claims
        if isinstance(claim, dict) and claim.get("status") == "contradicted"
    ]
    for claim in contradicted[:3]:
        details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
        reasons = (
            details.get("reasons") if isinstance(details.get("reasons"), list) else []
        )
        LOGGER.warning(
            "%s contradiction slide %s %s: %s%s",
            pdf_name,
            claim.get("slide_number", "?"),
            claim.get("claim_family", "unknown"),
            _truncate_log_text(claim.get("claim_text")),
            (
                f" | reasons: {'; '.join(str(reason) for reason in reasons)}"
                if reasons
                else ""
            ),
        )


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO)
    )

    pdf_paths = _report_paths(args)
    if not pdf_paths:
        LOGGER.error("No PDFs found to validate.")
        return 1

    output_dir = args.output_dir.expanduser().resolve()
    previous_output_dir = _rotate_existing_output_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    package_roots = _package_roots(args)
    brief_roots = _brief_roots(args)
    if previous_output_dir is not None:
        LOGGER.info(
            "Moved previous validation output from %s to %s",
            output_dir,
            previous_output_dir,
        )
    LOGGER.info(
        "Validating %s launch report PDF(s); output_dir=%s",
        len(pdf_paths),
        output_dir,
    )
    _log_stale_validation_artifacts(output_dir, pdf_paths)

    try:
        llm_wrapper = _llm_wrapper(args)
        if len(pdf_paths) == 1:
            payload = validate_launch_report_pdf(
                pdf_paths[0],
                package_roots=package_roots,
                brief_roots=brief_roots,
                lang=str(args.lang or "eng"),
                llm_review=bool(args.llm_review),
                llm_wrapper=llm_wrapper,
                llm_review_max_items=int(args.llm_review_max_items),
                refresh_reading_cache=bool(args.refresh_reading_cache),
            )
            write_launch_report_validation_artifacts(
                payload=payload,
                output_prefix=output_dir / pdf_paths[0].stem,
            )
            _log_package_fingerprint_drift(payload, previous_output_dir)
            LOGGER.info(
                "Validated %s -> %s",
                pdf_paths[0].name,
                payload["status"],
            )
            _log_report_diagnostics(payload)
            if args.strict and payload["status"] == "fail":
                return 1
            return 0

        batch_payload = validate_launch_report_batch(
            pdf_paths,
            package_roots=package_roots,
            brief_roots=brief_roots,
            lang=str(args.lang or "eng"),
            llm_review=bool(args.llm_review),
            llm_wrapper=llm_wrapper,
            llm_review_max_items=int(args.llm_review_max_items),
            refresh_reading_cache=bool(args.refresh_reading_cache),
        )
    except OPENAI_FAILURES as exc:
        LOGGER.error("OpenAI validation step failed: %s", exc)
        return 2

    for report in batch_payload["reports"]:
        write_launch_report_validation_artifacts(
            payload=report,
            output_prefix=output_dir / Path(report["pdf_path"]).stem,
        )
        _log_package_fingerprint_drift(report, previous_output_dir)
        _log_report_diagnostics(report)
    write_launch_report_batch_artifacts(
        payload=batch_payload,
        output_prefix=output_dir / "batch",
    )
    LOGGER.info(
        "Wrote batch validation artifacts under %s; batch.validation.json is "
        "the source of truth for this run.",
        output_dir,
    )

    LOGGER.info(
        "Validated %s report(s): %s pass, %s pass_with_warnings, %s fail, %s not_validated",
        batch_payload["summary"]["report_count"],
        batch_payload["summary"]["pass_count"],
        batch_payload["summary"]["pass_with_warnings_count"],
        batch_payload["summary"]["fail_count"],
        batch_payload["summary"].get("not_validated_count", 0),
    )
    if args.strict and batch_payload["summary"]["fail_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
