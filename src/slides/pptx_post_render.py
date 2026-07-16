from __future__ import annotations

import base64
import io
import json
import logging
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from bs4 import BeautifulSoup  # type: ignore[import]
from PIL import Image

import modules.utilities.config as config_module
from modules.llm.batch_runner import run_step_json
from modules.llm.llm_call_wrapper import init_llm_wrapper
from modules.utilities.session_context import SessionContext
from src.slides.models import Deck, Slide
from src.slides.pptx_rasterizer import (
    SofficeNotFoundError,
    rasterize_presentation_to_pngs,
)
from src.slides.semantic_pptx import (
    SlidesPptxSlide,
    SlidesPptxSpec,
    render_slides_pptx_from_template,
    write_slides_pptx_spec,
)

__all__ = [
    "PPTX_POST_RENDER_DIRNAME",
    "apply_post_render_compare_loop",
]

LOGGER = logging.getLogger(__name__)

PPTX_POST_RENDER_DIRNAME = "pptx_post_render"
_REPORT_FILENAME = "report.json"
_MAX_IMAGE_SIDE = 1600
_VALID_STATUSES = {"ok", "repairable", "manual_review", "skipped"}
_VALID_ISSUES = {
    "title_overflow",
    "title_too_large",
    "body_overflow",
    "body_too_dense",
    "implication_missing",
    "implication_misplaced",
    "visual_too_small",
    "visual_crop_tight",
    "visual_misaligned",
    "text_missing",
    "duplicate_text",
    "table_title_missing",
    "intro_missing",
    "footer_misplaced",
    "other",
}
_COMPARE_SYSTEM_PROMPT = (
    "You compare a source slide image against a screenshot of the rendered PPTX slide. "
    "Focus on layout fidelity and missing or duplicated content, not tiny styling differences. "
    "Return JSON only with: status, summary, issues, and repairs. "
    "status must be one of ok, repairable, or manual_review. "
    "issues must be a list chosen from: "
    "title_overflow, title_too_large, body_overflow, body_too_dense, implication_missing, implication_misplaced, "
    "visual_too_small, visual_crop_tight, visual_misaligned, text_missing, duplicate_text, table_title_missing, "
    "intro_missing, footer_misplaced, other. "
    "repairs must only use this vocabulary: "
    "layoutVariantOverride, titleScale, bodyScale, visualScale, visualAnchor, bannerScale, "
    "promoteTrailingImplication, promoteTrailingFooter. "
    "Only propose repairs that this vocabulary can execute safely. "
    "Use layoutVariantOverride only when one of the allowed variants would clearly improve the slide. "
    "Use promoteTrailingImplication only when the last body paragraph or last bullet should move into the bottom banner. "
    "Use promoteTrailingFooter only when the last body paragraph should move into footer metadata."
)


def _build_local_llm_wrapper() -> object:
    session = SessionContext.from_state({})
    init_llm_wrapper("", session=session)
    return session.state["llm_wrapper"]


def _encode_image_path_to_data_uri(image_path: Path) -> str:
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        max_side = max(rgb.size)
        if max_side > _MAX_IMAGE_SIDE:
            scale = _MAX_IMAGE_SIDE / float(max_side)
            rgb = rgb.resize(
                (
                    max(1, int(round(rgb.width * scale))),
                    max(1, int(round(rgb.height * scale))),
                )
            )
        buffer = io.BytesIO()
        rgb.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _resolve_source_slide_image_path(deck: Deck, deck_path: Path, slide: Slide) -> Path | None:
    html_sources = [slide.body_html or "", slide.full_html or ""]
    for source_html in html_sources:
        if not source_html:
            continue
        soup = BeautifulSoup(source_html, "html.parser")
        image = soup.find("img")
        if image is None:
            continue
        src = str(image.get("src") or image.get("data-src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        prefix = f"/slides/deck/{deck.deck_id}/assets/"
        if src.startswith(prefix):
            relative = src[len(prefix) :]
        else:
            relative = src
        relative = relative.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if relative.startswith("assets/"):
            relative = relative[len("assets/") :]
        candidate = (deck_path / "assets" / relative).resolve()
        assets_root = (deck_path / "assets").resolve()
        try:
            candidate.relative_to(assets_root)
        except ValueError:
            continue
        if candidate.exists():
            return candidate
    return None


def _allowed_layout_variant_overrides(slide_spec: SlidesPptxSlide) -> list[str]:
    variant = slide_spec.layout_variant
    if variant in {"text_visual_right", "text_visual_bottom"}:
        return ["same", "text_visual_right", "text_visual_bottom"]
    if variant in {"bullets_visual_right", "bullets_visual_bottom"}:
        return ["same", "bullets_visual_right", "bullets_visual_bottom"]
    return ["same"]


def _split_body_paragraphs(body: str) -> list[str]:
    return [part.strip() for part in body.split("\n\n") if part.strip()]


def _implication_candidate_available(slide_spec: SlidesPptxSlide) -> bool:
    if slide_spec.implication:
        return False
    if slide_spec.bullets:
        return True
    return len(_split_body_paragraphs(slide_spec.body)) >= 2


def _footer_candidate_available(slide_spec: SlidesPptxSlide) -> bool:
    if slide_spec.footer_text:
        return False
    return len(_split_body_paragraphs(slide_spec.body)) >= 2


def _slide_prompt_summary(slide_spec: SlidesPptxSlide) -> dict[str, object]:
    return {
        "slideId": slide_spec.slide_id,
        "kind": slide_spec.kind,
        "layoutVariant": slide_spec.layout_variant,
        "title": slide_spec.title,
        "body": slide_spec.body[:700],
        "bullets": slide_spec.bullets[:8],
        "visualType": slide_spec.visual_type,
        "hasVisual": bool(slide_spec.visual_path),
        "implication": slide_spec.implication,
        "footerText": slide_spec.footer_text,
        "tableTitle": slide_spec.table_title,
        "calloutTitle": slide_spec.callout_title,
        "calloutBody": slide_spec.callout_body[:300],
        "comparisonColumns": slide_spec.comparison_columns[:2],
        "allowedLayoutVariantOverrides": _allowed_layout_variant_overrides(slide_spec),
        "canPromoteTrailingImplication": _implication_candidate_available(slide_spec),
        "canPromoteTrailingFooter": _footer_candidate_available(slide_spec),
    }


def _build_compare_prompt(
    *,
    slide_number: int,
    slide_spec: SlidesPptxSlide,
) -> str:
    summary = _slide_prompt_summary(slide_spec)
    return (
        "Image 1 is the source slide. Image 2 is the rendered PPTX slide screenshot.\n"
        f"Slide number: {slide_number}\n"
        "Current semantic PPTX summary:\n"
        f"{json.dumps(summary, ensure_ascii=False)}"
    )


def _normalize_status(value: object) -> str:
    status = str(value or "").strip().lower()
    return status if status in _VALID_STATUSES else "repairable"


def _normalize_issues(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    issues: list[str] = []
    for item in value:
        issue = str(item or "").strip().lower().replace("-", "_").replace(" ", "_")
        if issue in _VALID_ISSUES and issue not in issues:
            issues.append(issue)
    return issues


def _normalize_float(
    value: object,
    *,
    minimum: float,
    maximum: float,
    default: float,
) -> float:
    if not isinstance(value, (int, float)):
        return default
    return min(maximum, max(minimum, float(value)))


def _normalize_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _normalize_repair_response(
    response: object,
    *,
    slide_spec: SlidesPptxSlide,
) -> dict[str, object]:
    if not isinstance(response, Mapping):
        return {
            "status": "manual_review",
            "summary": "Invalid compare response.",
            "issues": ["other"],
            "repairs": {},
        }
    raw_repairs = response.get("repairs") if isinstance(response.get("repairs"), Mapping) else {}
    allowed_variants = set(_allowed_layout_variant_overrides(slide_spec))
    layout_variant = str(
        raw_repairs.get("layoutVariantOverride")
        or raw_repairs.get("layout_variant_override")
        or "same"
    ).strip()
    if layout_variant not in allowed_variants:
        layout_variant = "same"
    visual_anchor = str(
        raw_repairs.get("visualAnchor") or raw_repairs.get("visual_anchor") or "center"
    ).strip().lower()
    if visual_anchor not in {"same", "top", "center", "bottom"}:
        visual_anchor = "center"
    repairs = {
        "layout_variant_override": layout_variant,
        "title_scale": _normalize_float(
            raw_repairs.get("titleScale") or raw_repairs.get("title_scale"),
            minimum=0.72,
            maximum=1.0,
            default=1.0,
        ),
        "body_scale": _normalize_float(
            raw_repairs.get("bodyScale") or raw_repairs.get("body_scale"),
            minimum=0.82,
            maximum=1.0,
            default=1.0,
        ),
        "visual_scale": _normalize_float(
            raw_repairs.get("visualScale") or raw_repairs.get("visual_scale"),
            minimum=0.85,
            maximum=1.2,
            default=1.0,
        ),
        "visual_anchor": "center" if visual_anchor == "same" else visual_anchor,
        "banner_scale": _normalize_float(
            raw_repairs.get("bannerScale") or raw_repairs.get("banner_scale"),
            minimum=0.9,
            maximum=1.3,
            default=1.0,
        ),
        "promote_trailing_implication": _normalize_bool(
            raw_repairs.get("promoteTrailingImplication")
            or raw_repairs.get("promote_trailing_implication")
        ),
        "promote_trailing_footer": _normalize_bool(
            raw_repairs.get("promoteTrailingFooter")
            or raw_repairs.get("promote_trailing_footer")
        ),
    }
    return {
        "status": _normalize_status(response.get("status")),
        "summary": str(response.get("summary") or response.get("reason") or "").strip(),
        "issues": _normalize_issues(response.get("issues")),
        "repairs": repairs,
    }


def _promote_trailing_implication(slide_spec: SlidesPptxSlide) -> SlidesPptxSlide:
    if slide_spec.implication:
        return slide_spec
    body_parts = _split_body_paragraphs(slide_spec.body)
    if len(body_parts) >= 2:
        implication = body_parts[-1]
        return replace(
            slide_spec,
            body="\n\n".join(body_parts[:-1]),
            implication=implication,
        )
    if slide_spec.bullets:
        bullets = list(slide_spec.bullets)
        implication = bullets.pop()
        return replace(slide_spec, bullets=bullets, implication=implication)
    return slide_spec


def _promote_trailing_footer(slide_spec: SlidesPptxSlide) -> SlidesPptxSlide:
    if slide_spec.footer_text:
        return slide_spec
    body_parts = _split_body_paragraphs(slide_spec.body)
    if len(body_parts) < 2:
        return slide_spec
    footer_text = body_parts[-1]
    return replace(
        slide_spec,
        body="\n\n".join(body_parts[:-1]),
        footer_text=footer_text,
    )


def _apply_single_repair(
    slide_spec: SlidesPptxSlide,
    *,
    repair: Mapping[str, object],
) -> SlidesPptxSlide:
    updated = slide_spec
    if _normalize_bool(repair.get("promote_trailing_footer")):
        updated = _promote_trailing_footer(updated)
    if _normalize_bool(repair.get("promote_trailing_implication")):
        updated = _promote_trailing_implication(updated)
    layout_variant_override = str(repair.get("layout_variant_override") or "same").strip()
    if layout_variant_override and layout_variant_override != "same":
        updated = replace(updated, layout_variant=layout_variant_override)
    repair_hints = dict(updated.repair_hints)
    for key in ("title_scale", "body_scale", "visual_scale", "visual_anchor", "banner_scale"):
        value = repair.get(key)
        if value is None:
            continue
        repair_hints[key] = value
    return replace(updated, repair_hints=repair_hints)


def _apply_repairs_to_spec(
    spec: SlidesPptxSpec,
    evaluations: list[dict[str, object]],
) -> tuple[SlidesPptxSpec, list[dict[str, object]]]:
    evaluation_by_slide_id = {
        str(item.get("slideId") or ""): item for item in evaluations if str(item.get("slideId") or "")
    }
    applied: list[dict[str, object]] = []
    repaired_slides: list[SlidesPptxSlide] = []
    for slide_spec in spec.slides:
        evaluation = evaluation_by_slide_id.get(slide_spec.slide_id)
        if evaluation is None:
            repaired_slides.append(slide_spec)
            continue
        repair = evaluation.get("repairs") if isinstance(evaluation.get("repairs"), Mapping) else {}
        updated_slide = _apply_single_repair(slide_spec, repair=repair)
        repaired_slides.append(updated_slide)
        if updated_slide != slide_spec:
            applied.append(
                {
                    "slideId": slide_spec.slide_id,
                    "repairs": dict(repair),
                    "issues": evaluation.get("issues"),
                    "summary": evaluation.get("summary"),
                }
            )
    return replace(spec, slides=repaired_slides), applied


def _evaluate_rendered_slides(
    *,
    deck: Deck,
    deck_path: Path,
    spec: SlidesPptxSpec,
    rendered_dir: Path,
    llm_wrapper: object,
) -> list[dict[str, object]]:
    prompts: list[dict[str, object]] = []
    references: list[dict[str, object]] = []
    for slide_number, (slide, slide_spec) in enumerate(zip(deck.slides, spec.slides, strict=False), start=1):
        source_path = _resolve_source_slide_image_path(deck, deck_path, slide)
        rendered_path = rendered_dir / f"slide-{slide_number}.png"
        if source_path is None or not rendered_path.exists():
            references.append(
                {
                    "slideId": slide_spec.slide_id,
                    "slideNumber": slide_number,
                    "status": "skipped",
                    "summary": "Source or rendered slide image unavailable for post-render compare.",
                    "issues": [],
                    "repairs": {},
                    "sourceImagePath": str(source_path) if source_path is not None else "",
                    "renderedImagePath": str(rendered_path),
                }
            )
            continue
        prompts.append(
            {
                "user_content": [
                    {"type": "input_text", "text": _build_compare_prompt(slide_number=slide_number, slide_spec=slide_spec)},
                    {"type": "input_image", "image_url": _encode_image_path_to_data_uri(source_path)},
                    {"type": "input_image", "image_url": _encode_image_path_to_data_uri(rendered_path)},
                ]
            }
        )
        references.append(
            {
                "slideId": slide_spec.slide_id,
                "slideNumber": slide_number,
                "sourceImagePath": str(source_path),
                "renderedImagePath": str(rendered_path),
                "slideSpec": slide_spec,
            }
        )
    if not prompts:
        return references

    naming_params = config_module.get_naming_params()
    query_step = naming_params["slidesPptxRepairQuery"]
    prompt_responses = run_step_json(
        llm_wrapper,
        query_step,
        _COMPARE_SYSTEM_PROMPT,
        prompts,
        retry_missing=1,
    )

    evaluated: list[dict[str, object]] = []
    response_index = 0
    for entry in references:
        slide_spec = entry.pop("slideSpec", None)
        if slide_spec is None:
            evaluated.append(entry)
            continue
        response = prompt_responses[response_index] if response_index < len(prompt_responses) else {}
        response_index += 1
        normalized = _normalize_repair_response(response, slide_spec=slide_spec)
        evaluated.append(
            {
                **entry,
                **normalized,
            }
        )
    return evaluated


def _write_report(report_path: Path, report: Mapping[str, object]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def apply_post_render_compare_loop(
    *,
    deck: Deck,
    deck_path: Path,
    spec: SlidesPptxSpec,
    pptx_path: Path,
    job_id: str,
) -> tuple[SlidesPptxSpec, dict[str, object]]:
    compare_root = (deck_path / PPTX_POST_RENDER_DIRNAME / job_id).resolve()
    initial_dir = compare_root / "initial"
    final_dir = compare_root / "final"
    report_path = compare_root / _REPORT_FILENAME
    report: dict[str, object] = {
        "jobId": job_id,
        "createdAt": datetime.now(UTC).isoformat(),
        "pptxPath": str(pptx_path),
        "iterations": [],
        "appliedRepairs": [],
    }
    try:
        llm_wrapper = _build_local_llm_wrapper()
        rasterize_presentation_to_pngs(pptx_path, initial_dir)
        initial_evaluation = _evaluate_rendered_slides(
            deck=deck,
            deck_path=deck_path,
            spec=spec,
            rendered_dir=initial_dir,
            llm_wrapper=llm_wrapper,
        )
        report["iterations"].append(
            {
                "name": "initial",
                "renderedDir": str(initial_dir),
                "slides": initial_evaluation,
            }
        )
        repaired_spec, applied_repairs = _apply_repairs_to_spec(spec, initial_evaluation)
        report["appliedRepairs"] = applied_repairs
        if not applied_repairs:
            _write_report(report_path, report)
            return spec, report

        write_slides_pptx_spec(deck_path, repaired_spec)
        buffer = render_slides_pptx_from_template(deck_path)
        pptx_path.write_bytes(buffer.getvalue())
        rasterize_presentation_to_pngs(pptx_path, final_dir)
        final_evaluation = _evaluate_rendered_slides(
            deck=deck,
            deck_path=deck_path,
            spec=repaired_spec,
            rendered_dir=final_dir,
            llm_wrapper=llm_wrapper,
        )
        report["iterations"].append(
            {
                "name": "final",
                "renderedDir": str(final_dir),
                "slides": final_evaluation,
            }
        )
        _write_report(report_path, report)
        return repaired_spec, report
    except (FileNotFoundError, OSError, RuntimeError, SofficeNotFoundError, ValueError, TypeError) as exc:
        LOGGER.warning("Skipping PPTX post-render compare loop after failure: %s", exc)
        report["error"] = str(exc)
        _write_report(report_path, report)
        return spec, report
