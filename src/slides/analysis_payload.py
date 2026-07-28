from __future__ import annotations

from datetime import UTC, datetime

from .ocr_payload import normalize_ocr_payload

__all__ = ["build_slide_analysis_payload", "normalize_layout_payload"]


def _normalize_layout_slide_payload(
    slide_payload: dict[str, object],
) -> dict[str, object] | None:
    slide_id = str(
        slide_payload.get("slide_id") or slide_payload.get("slideId") or ""
    ).strip()
    if not slide_id:
        return None
    raw_blocks = (
        slide_payload.get("blocks")
        if isinstance(slide_payload.get("blocks"), list)
        else []
    )
    normalized_blocks: list[dict[str, object]] = []
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict):
            continue
        normalized_block: dict[str, object] = {
            "blockId": str(
                raw_block.get("block_id")
                or raw_block.get("blockId")
                or raw_block.get("id")
                or ""
            ),
            "type": str(raw_block.get("type") or "unknown"),
            "detectedType": str(
                raw_block.get("detected_type") or raw_block.get("detectedType") or ""
            ).strip(),
            "text": str(raw_block.get("text") or ""),
            "items": [
                str(item).strip()
                for item in (
                    raw_block.get("items")
                    if isinstance(raw_block.get("items"), list)
                    else []
                )
                if str(item).strip()
            ],
        }
        group_id = str(
            raw_block.get("group_id") or raw_block.get("groupId") or ""
        ).strip()
        if group_id:
            normalized_block["groupId"] = group_id
        group_kind = str(
            raw_block.get("group_kind") or raw_block.get("groupKind") or ""
        ).strip()
        if group_kind:
            normalized_block["groupKind"] = group_kind
        parent_id = str(
            raw_block.get("parent_id") or raw_block.get("parentId") or ""
        ).strip()
        if parent_id:
            normalized_block["parentId"] = parent_id
        list_level = raw_block.get("list_level")
        if list_level is None:
            list_level = raw_block.get("listLevel")
        if isinstance(list_level, int) and list_level >= 0:
            normalized_block["listLevel"] = list_level
        reading_order = raw_block.get("reading_order")
        if reading_order is None:
            reading_order = raw_block.get("readingOrder")
        if isinstance(reading_order, int) and reading_order >= 0:
            normalized_block["readingOrder"] = reading_order
        render_mode = str(
            raw_block.get("render_mode") or raw_block.get("renderMode") or ""
        ).strip()
        if render_mode:
            normalized_block["renderMode"] = render_mode
        visual_text = str(
            raw_block.get("visual_text") or raw_block.get("visualText") or ""
        ).strip()
        if visual_text:
            normalized_block["visualText"] = visual_text
        visual_items = [
            str(item).strip()
            for item in (
                raw_block.get("visual_items")
                if isinstance(raw_block.get("visual_items"), list)
                else (
                    raw_block.get("visualItems")
                    if isinstance(raw_block.get("visualItems"), list)
                    else []
                )
            )
            if str(item).strip()
        ]
        if visual_items:
            normalized_block["visualItems"] = visual_items
        visual_lines = [
            line
            for line in (
                raw_block.get("visual_lines")
                if isinstance(raw_block.get("visual_lines"), list)
                else (
                    raw_block.get("visualLines")
                    if isinstance(raw_block.get("visualLines"), list)
                    else []
                )
            )
            if isinstance(line, dict) and str(line.get("text") or "").strip()
        ]
        if visual_lines:
            normalized_block["visualLines"] = visual_lines
        bbox = raw_block.get("bbox")
        if isinstance(bbox, dict):
            normalized_block["bbox"] = bbox
        confidence = raw_block.get("confidence")
        if isinstance(confidence, (int, float)):
            normalized_block["confidence"] = float(confidence)
        table_model = raw_block.get("table_model") or raw_block.get("tableModel")
        if isinstance(table_model, dict):
            normalized_block["tableModel"] = table_model
        normalized_blocks.append(normalized_block)
    raw_figure_regions = (
        slide_payload.get("figure_regions")
        if isinstance(slide_payload.get("figure_regions"), list)
        else (
            slide_payload.get("figureRegions")
            if isinstance(slide_payload.get("figureRegions"), list)
            else []
        )
    )
    figure_regions = [
        region
        for region in raw_figure_regions
        if isinstance(region, dict)
        and all(
            isinstance(region.get(key), (int, float)) for key in ("x", "y", "w", "h")
        )
    ]
    return {
        "slideId": slide_id,
        "slideNumber": int(
            slide_payload.get("slide_number") or slide_payload.get("slideNumber") or 0
        ),
        "pageNumber": int(
            slide_payload.get("page_number") or slide_payload.get("pageNumber") or 0
        ),
        "assetPath": str(
            slide_payload.get("asset_path") or slide_payload.get("assetPath") or ""
        ),
        "blocks": normalized_blocks,
        "titleText": str(
            slide_payload.get("title_text") or slide_payload.get("titleText") or ""
        ),
        "bulletTexts": [
            str(item).strip()
            for item in (
                slide_payload.get("bullet_texts")
                if isinstance(slide_payload.get("bullet_texts"), list)
                else (
                    slide_payload.get("bulletTexts")
                    if isinstance(slide_payload.get("bulletTexts"), list)
                    else []
                )
            )
            if str(item).strip()
        ],
        "figureRegions": figure_regions,
    }


def normalize_layout_payload(
    payload: dict[str, object],
    *,
    deck_id: str,
    lang: str,
) -> dict[str, object]:
    raw_slides = (
        payload.get("slides") if isinstance(payload.get("slides"), list) else []
    )
    normalized_slides = [
        normalized
        for raw_slide in raw_slides
        if isinstance(raw_slide, dict)
        for normalized in [_normalize_layout_slide_payload(raw_slide)]
        if normalized is not None
    ]
    return {
        "deckId": deck_id,
        "lang": str(payload.get("lang") or lang or "eng"),
        "generatedAt": str(
            payload.get("generated_at")
            or payload.get("generatedAt")
            or datetime.now(UTC).isoformat()
        ),
        "slides": normalized_slides,
    }


def _merge_layout_slide_with_ocr(
    layout_slide: dict[str, object],
    ocr_slide: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(ocr_slide, dict):
        return layout_slide
    ocr_blocks = (
        ocr_slide.get("blocks") if isinstance(ocr_slide.get("blocks"), list) else []
    )
    ocr_blocks_by_id: dict[str, dict[str, object]] = {}
    for raw_block in ocr_blocks:
        if not isinstance(raw_block, dict):
            continue
        block_id = str(
            raw_block.get("block_id")
            or raw_block.get("blockId")
            or raw_block.get("id")
            or ""
        ).strip()
        if block_id:
            ocr_blocks_by_id[block_id] = raw_block

    merged_blocks: list[dict[str, object]] = []
    for raw_block in (
        layout_slide.get("blocks")
        if isinstance(layout_slide.get("blocks"), list)
        else []
    ):
        if not isinstance(raw_block, dict):
            continue
        merged_block = dict(raw_block)
        block_id = str(
            raw_block.get("blockId")
            or raw_block.get("block_id")
            or raw_block.get("id")
            or ""
        ).strip()
        matching_block = ocr_blocks_by_id.get(block_id)
        if isinstance(matching_block, dict):
            matching_type = str(
                matching_block.get("type") or matching_block.get("blockType") or ""
            ).strip()
            if matching_type:
                merged_block["type"] = matching_type
            matching_detected_type = str(
                matching_block.get("detected_type")
                or matching_block.get("detectedType")
                or ""
            ).strip()
            if matching_detected_type:
                merged_block["detectedType"] = matching_detected_type
            text = str(matching_block.get("text") or "").strip()
            if text:
                merged_block["text"] = text
            items = [
                str(item).strip()
                for item in (
                    matching_block.get("items")
                    if isinstance(matching_block.get("items"), list)
                    else []
                )
                if str(item).strip()
            ]
            if items:
                merged_block["items"] = items
            confidence = matching_block.get("confidence")
            if isinstance(confidence, (int, float)):
                merged_block["confidence"] = float(confidence)
            table_model = matching_block.get("table_model")
            if not isinstance(table_model, dict):
                table_model = matching_block.get("tableModel")
            if isinstance(table_model, dict):
                merged_block["tableModel"] = table_model
            audit_status = str(
                matching_block.get("audit_status")
                or matching_block.get("auditStatus")
                or ""
            ).strip()
            if audit_status:
                merged_block["auditStatus"] = audit_status
            audit_reason = str(
                matching_block.get("audit_reason")
                or matching_block.get("auditReason")
                or ""
            ).strip()
            if audit_reason:
                merged_block["auditReason"] = audit_reason
            audit_suggested_text = str(
                matching_block.get("audit_suggested_text")
                or matching_block.get("auditSuggestedText")
                or ""
            ).strip()
            if audit_suggested_text:
                merged_block["auditSuggestedText"] = audit_suggested_text
            visual_status = str(
                matching_block.get("visual_status")
                or matching_block.get("visualStatus")
                or ""
            ).strip()
            if visual_status:
                merged_block["visualStatus"] = visual_status
            visual_reason = str(
                matching_block.get("visual_reason")
                or matching_block.get("visualReason")
                or ""
            ).strip()
            if visual_reason:
                merged_block["visualReason"] = visual_reason
            visual_suggested_text = str(
                matching_block.get("visual_suggested_text")
                or matching_block.get("visualSuggestedText")
                or ""
            ).strip()
            if visual_suggested_text:
                merged_block["visualSuggestedText"] = visual_suggested_text
            visual_confidence = matching_block.get("visual_confidence")
            if not isinstance(visual_confidence, (int, float)):
                visual_confidence = matching_block.get("visualConfidence")
            if isinstance(visual_confidence, (int, float)):
                merged_block["visualConfidence"] = float(visual_confidence)
            visual_text = str(
                matching_block.get("visual_text")
                or matching_block.get("visualText")
                or ""
            ).strip()
            if visual_text:
                merged_block["visualText"] = visual_text
            visual_items = [
                str(item).strip()
                for item in (
                    matching_block.get("visual_items")
                    if isinstance(matching_block.get("visual_items"), list)
                    else (
                        matching_block.get("visualItems")
                        if isinstance(matching_block.get("visualItems"), list)
                        else []
                    )
                )
                if str(item).strip()
            ]
            if visual_items:
                merged_block["visualItems"] = visual_items
            visual_lines = [
                line
                for line in (
                    matching_block.get("visual_lines")
                    if isinstance(matching_block.get("visual_lines"), list)
                    else (
                        matching_block.get("visualLines")
                        if isinstance(matching_block.get("visualLines"), list)
                        else []
                    )
                )
                if isinstance(line, dict) and str(line.get("text") or "").strip()
            ]
            if visual_lines:
                merged_block["visualLines"] = visual_lines
            group_id = str(
                matching_block.get("group_id") or matching_block.get("groupId") or ""
            ).strip()
            if group_id:
                merged_block["groupId"] = group_id
            group_kind = str(
                matching_block.get("group_kind")
                or matching_block.get("groupKind")
                or ""
            ).strip()
            if group_kind:
                merged_block["groupKind"] = group_kind
            parent_id = str(
                matching_block.get("parent_id") or matching_block.get("parentId") or ""
            ).strip()
            if parent_id:
                merged_block["parentId"] = parent_id
            list_level = matching_block.get("list_level")
            if list_level is None:
                list_level = matching_block.get("listLevel")
            if isinstance(list_level, int) and list_level >= 0:
                merged_block["listLevel"] = list_level
            reading_order = matching_block.get("reading_order")
            if reading_order is None:
                reading_order = matching_block.get("readingOrder")
            if isinstance(reading_order, int) and reading_order >= 0:
                merged_block["readingOrder"] = reading_order
            render_mode = str(
                matching_block.get("render_mode")
                or matching_block.get("renderMode")
                or ""
            ).strip()
            if render_mode:
                merged_block["renderMode"] = render_mode
        merged_blocks.append(merged_block)

    merged_slide = dict(layout_slide)
    merged_slide["blocks"] = merged_blocks
    title_text = str(
        ocr_slide.get("title_text") or ocr_slide.get("titleText") or ""
    ).strip()
    if title_text:
        merged_slide["titleText"] = title_text
    bullet_texts = [
        str(item).strip()
        for item in (
            ocr_slide.get("bullet_texts")
            if isinstance(ocr_slide.get("bullet_texts"), list)
            else (
                ocr_slide.get("bulletTexts")
                if isinstance(ocr_slide.get("bulletTexts"), list)
                else []
            )
        )
        if str(item).strip()
    ]
    if bullet_texts:
        merged_slide["bulletTexts"] = bullet_texts
    return merged_slide


def _merge_layout_payload_with_ocr(
    layout_payload: dict[str, object],
    ocr_payload: dict[str, object] | None,
    *,
    deck_id: str,
    lang: str,
) -> dict[str, object]:
    normalized_layout = normalize_layout_payload(
        layout_payload, deck_id=deck_id, lang=lang
    )
    if not isinstance(ocr_payload, dict):
        return normalized_layout
    normalized_ocr = normalize_ocr_payload(ocr_payload, deck_id=deck_id, lang=lang)
    ocr_slides = (
        normalized_ocr.get("slides")
        if isinstance(normalized_ocr.get("slides"), list)
        else []
    )
    ocr_by_slide_id = {
        str(slide.get("slide_id") or slide.get("slideId") or "").strip(): slide
        for slide in ocr_slides
        if isinstance(slide, dict)
    }
    merged_slides = [
        _merge_layout_slide_with_ocr(
            slide,
            ocr_by_slide_id.get(
                str(slide.get("slideId") or slide.get("slide_id") or "").strip()
            ),
        )
        for slide in normalized_layout.get("slides", [])
        if isinstance(slide, dict)
    ]
    merged_payload = dict(normalized_layout)
    merged_payload["slides"] = merged_slides
    return merged_payload


def build_slide_analysis_payload(
    layout_payload: dict[str, object] | None,
    ocr_payload: dict[str, object] | None,
    *,
    deck_id: str,
    lang: str,
) -> dict[str, object] | None:
    if not isinstance(layout_payload, dict):
        return None
    return _merge_layout_payload_with_ocr(
        layout_payload,
        ocr_payload,
        deck_id=deck_id,
        lang=lang,
    )
