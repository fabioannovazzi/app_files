from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.slides.launch_brief import build_report_payload_from_launch_brief
from src.slides.category_insights import build_launch_brief_from_category_insights
from src.slides.launch_pdf_validator import build_launch_package_content_fingerprint
from src.slides.pptx_rasterizer import rasterize_presentation_to_pngs
from src.slides.semantic_pptx import (
    build_slides_pptx_spec_from_report_payload,
    render_slides_pptx_from_template,
    write_slides_pptx_spec,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compile either a model-authored launch brief or a richer launch-report "
            "AST JSON payload into an editable PPTX through the shared semantic slides "
            "renderer."
        )
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="Path to a JSON launch brief or compiled report payload.",
    )
    parser.add_argument(
        "--input-format",
        choices=("auto", "insights", "brief", "report"),
        default="auto",
        help="Interpret the input as category insights, a high-level brief, or a compiled report payload.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where the semantic spec and PPTX should be written.",
    )
    parser.add_argument(
        "--output-name",
        default="",
        help="Optional PPTX filename stem. Defaults to deckName/title/input filename.",
    )
    parser.add_argument(
        "--source-package-dir",
        type=Path,
        default=None,
        help=(
            "Launch package directory used to generate the report. When provided, "
            "the report payload and sidecar manifest record the package fingerprint."
        ),
    )
    parser.add_argument(
        "--render-pngs",
        action="store_true",
        help="Also rasterize the generated PPTX into per-slide PNGs.",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=1600,
        help="Maximum rasterized image width in pixels when --render-pngs is used.",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=900,
        help="Maximum rasterized image height in pixels when --render-pngs is used.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    return parser.parse_args()


def _read_payload(input_path: Path) -> dict[str, object]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Launch report payload must be a JSON object.")
    return payload


def _looks_like_brief(payload: dict[str, object]) -> bool:
    version = str(payload.get("version") or "").strip().lower()
    if version.startswith("launch_brief/"):
        return True
    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        return False
    first_slide = slides[0]
    return isinstance(first_slide, dict) and bool(
        str(first_slide.get("role") or "").strip()
    )


def _looks_like_insights(payload: dict[str, object]) -> bool:
    version = str(payload.get("version") or "").strip().lower()
    if version.startswith("category_insights/"):
        return True
    thesis = str(payload.get("thesis") or "").strip()
    examples = payload.get("evidenceExamples")
    if examples is None:
        examples = payload.get("evidence_examples")
    return bool(thesis) and isinstance(examples, list) and not payload.get("slides")


def _slugify_filename(text: str) -> str:
    normalized = _NON_ALNUM_RE.sub("-", text.strip().lower()).strip("-")
    return normalized or "launch-report"


def _output_stem(payload: dict[str, object], *, input_path: Path, override: str) -> str:
    if str(override or "").strip():
        return _slugify_filename(str(override))
    for key in ("deckName", "deck_name", "title"):
        candidate = str(payload.get(key) or "").strip()
        if candidate:
            return _slugify_filename(candidate)
    return _slugify_filename(input_path.stem)


def _read_optional_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _text_field(payload: dict[str, object], key: str) -> str:
    return str(payload.get(key) or "").strip()


def _source_package_from_payload(payload: dict[str, object]) -> dict[str, object]:
    for key in ("sourcePackage", "source_package"):
        source_package = payload.get(key)
        if isinstance(source_package, dict):
            return dict(source_package)
    return {}


def _source_package_metadata(package_dir: Path) -> dict[str, object]:
    package_dir = package_dir.expanduser().resolve()
    if not package_dir.is_dir():
        raise ValueError(f"Source package directory does not exist: {package_dir}")
    manifest = _read_optional_json_object(package_dir / "pack_manifest.json")
    summary = _read_optional_json_object(package_dir / "summary.json")
    return {
        "package_dir": str(package_dir),
        "retailer": _text_field(manifest, "retailer")
        or _text_field(summary, "retailer"),
        "category_key": _text_field(manifest, "category_key") or package_dir.name,
        "category_label": _text_field(manifest, "category_label")
        or _text_field(summary, "category_label")
        or package_dir.name,
        "content_fingerprint": build_launch_package_content_fingerprint(package_dir),
    }


def _attach_source_package(
    report_payload: dict[str, object],
    source_package: dict[str, object],
) -> dict[str, object]:
    if not source_package:
        return report_payload
    updated_payload = dict(report_payload)
    updated_payload["sourcePackage"] = source_package
    return updated_payload


def _write_report_source_manifest(
    *,
    output_dir: Path,
    pptx_path: Path,
    report_payload: dict[str, object],
) -> Path | None:
    source_package = _source_package_from_payload(report_payload)
    if not source_package:
        return None
    manifest = {
        "version": "launch_report_source/1",
        "pptx_file": pptx_path.name,
        "report_payload_file": "report_payload.json",
        "source_package": source_package,
    }
    manifest_path = output_dir / f"{pptx_path.stem}.launch_report_source.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO)
    )

    input_path = args.input_path.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        payload = _read_payload(input_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.error("Unable to load launch report payload: %s", exc)
        return 1
    input_format = str(args.input_format or "auto").strip().lower()
    is_insights = input_format == "insights" or (
        input_format == "auto" and _looks_like_insights(payload)
    )
    is_brief = input_format == "brief" or (
        input_format == "auto" and not is_insights and _looks_like_brief(payload)
    )
    if is_insights:
        try:
            launch_brief = build_launch_brief_from_category_insights(payload)
        except ValueError as exc:
            LOGGER.error("Category insights validation failed: %s", exc)
            return 1
        (output_dir / "category_insights.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output_dir / "launch_brief.json").write_text(
            json.dumps(launch_brief, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        try:
            report_payload = build_report_payload_from_launch_brief(launch_brief)
        except ValueError as exc:
            LOGGER.error("Launch brief validation failed: %s", exc)
            return 1
    elif is_brief:
        try:
            launch_brief = payload
            report_payload = build_report_payload_from_launch_brief(launch_brief)
        except ValueError as exc:
            LOGGER.error("Launch brief validation failed: %s", exc)
            return 1
        (output_dir / "launch_brief.json").write_text(
            json.dumps(launch_brief, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    else:
        report_payload = payload
    try:
        source_package = (
            _source_package_metadata(args.source_package_dir)
            if args.source_package_dir is not None
            else _source_package_from_payload(payload)
        )
    except ValueError as exc:
        LOGGER.error("Source package metadata failed: %s", exc)
        return 1
    report_payload = _attach_source_package(report_payload, source_package)
    try:
        spec = build_slides_pptx_spec_from_report_payload(
            report_payload, deck_path=output_dir
        )
    except ValueError as exc:
        LOGGER.error("Launch report payload validation failed: %s", exc)
        return 1
    write_slides_pptx_spec(output_dir, spec)

    output_stem = _output_stem(
        report_payload, input_path=input_path, override=args.output_name
    )
    pptx_path = output_dir / f"{output_stem}.pptx"
    pptx_path.write_bytes(render_slides_pptx_from_template(output_dir).getvalue())
    (output_dir / "report_payload.json").write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    source_manifest_path = _write_report_source_manifest(
        output_dir=output_dir,
        pptx_path=pptx_path,
        report_payload=report_payload,
    )

    LOGGER.info("Wrote semantic spec and PPTX to %s", output_dir)
    LOGGER.info("PPTX output: %s", pptx_path)
    if source_manifest_path is not None:
        LOGGER.info("Source manifest output: %s", source_manifest_path)

    if args.render_pngs:
        rendered_dir = output_dir / f"{pptx_path.stem}_rendered"
        image_paths = rasterize_presentation_to_pngs(
            pptx_path,
            rendered_dir,
            max_width_px=int(args.max_width),
            max_height_px=int(args.max_height),
        )
        LOGGER.info("Rendered %s slide PNG(s) into %s", len(image_paths), rendered_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
