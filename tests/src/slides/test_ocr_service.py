from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from src.slides import ocr_service
from src.slides.models import Deck, Slide
from src.slides.ocr_service import (
    OCR_STRATEGY_LAYOUT_GUIDED,
    SlideOcrOpenAIError,
    build_deck_ocr_payload,
    build_filtered_deck_ocr_inputs,
    ensure_deck_ocr_payload,
)

__all__ = [
    "test_build_deck_ocr_payload_uses_layout_guided_text_blocks_only",
    "test_build_filtered_deck_ocr_inputs_keeps_requested_slides",
    "test_build_deck_ocr_payload_reads_enriched_semantic_layout_types",
    "test_build_deck_ocr_payload_expands_title_crops_before_ocr",
    "test_build_deck_ocr_payload_applies_deterministic_text_cleanup",
    "test_build_deck_ocr_payload_applies_llm_correction_to_editable_blocks",
    "test_build_deck_ocr_payload_fails_on_openai_correction_failures",
    "test_build_deck_ocr_payload_rejects_llm_correction_that_changes_numbers",
    "test_build_deck_ocr_payload_adds_residual_audit_metadata_without_changing_text",
    "test_build_deck_ocr_payload_applies_vlm_correction_to_suspicious_blocks",
    "test_build_deck_ocr_payload_applies_vlm_correction_that_splits_fused_words",
    "test_build_deck_ocr_payload_keeps_visual_suggestion_when_confidence_is_low",
    "test_build_deck_ocr_payload_builds_table_model_for_simple_tables",
    "test_build_deck_ocr_payload_prefers_vlm_table_structure_for_complex_tables",
    "test_build_deck_ocr_payload_uses_table_fallback_for_low_confidence_tables",
    "test_build_deck_ocr_payload_does_not_ocr_image_only_regions",
    "test_build_deck_ocr_payload_promotes_definition_blocks_to_lists",
    "test_build_deck_ocr_payload_promotes_stacked_text_cards_to_lists",
    "test_build_deck_ocr_payload_recovers_callout_heading_from_decorative_block",
    "test_ensure_deck_ocr_payload_fills_missing_image_slides",
    "test_ensure_deck_ocr_payload_pdf_uses_import_raster_scale",
]


def _disable_llm_correction(monkeypatch) -> None:
    monkeypatch.setattr("src.slides.ocr_service._build_local_llm_wrapper", lambda: None)


def test_build_deck_ocr_payload_uses_layout_guided_text_blocks_only(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-layout-guided"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (20, 10), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    ocr_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "eng",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-title",
                            "type": "title",
                            "bbox": {"x": 0.0, "y": 0.0, "w": 8.0, "h": 10.0},
                            "confidence": 0.95,
                        },
                        {
                            "block_id": "block-figure",
                            "type": "figure",
                            "bbox": {"x": 8.0, "y": 0.0, "w": 12.0, "h": 10.0},
                        },
                    ],
                    "title_text": "Legacy title",
                    "bullet_texts": [],
                    "figure_regions": [{"x": 8.0, "y": 0.0, "w": 12.0, "h": 10.0}],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda image_bytes, lang, **kwargs: ocr_calls.append(
            {"image_bytes": image_bytes, "lang": lang, "kwargs": kwargs}
        )
        or [
            [
                [[0.0, 0.0], [8.0, 0.0], [8.0, 4.0], [0.0, 4.0]],
                ["Hello title block", 0.9],
            ]
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Hello title block",
                "bbox": {"x": 0.0, "y": 0.0, "w": 8.0, "h": 4.0},
                "confidence": 0.9,
            }
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "Hello title block",
    )

    payload = build_deck_ocr_payload(deck, deck_path, lang="eng", include_bboxes=True)

    assert payload["ocr_strategy"] == OCR_STRATEGY_LAYOUT_GUIDED
    assert len(ocr_calls) == 1
    assert ocr_calls[0]["lang"] == "eng"
    assert ocr_calls[0]["kwargs"]["preprocess_profile"] == "document_scan"
    assert ocr_calls[0]["kwargs"]["allow_preprocess_fallback"] is True
    assert (
        ocr_calls[0]["kwargs"]["text_recognition_model_name"] == "PP-OCRv5_server_rec"
    )
    slide_payload = payload["slides"][0]
    assert slide_payload["ocr_text"] == "Hello title block"
    assert slide_payload["title_text"] == "Hello title block"
    assert slide_payload["blocks"][0]["text"] == "Hello title block"
    assert slide_payload["blocks"][1]["type"] == "figure"
    assert slide_payload["blocks"][1]["text"] == ""
    assert "visual_text" not in slide_payload["blocks"][1]
    assert "visual_items" not in slide_payload["blocks"][1]
    assert "visual_lines" not in slide_payload["blocks"][1]
    assert slide_payload["figure_regions"] == [
        {"x": 8.0, "y": 0.0, "w": 12.0, "h": 10.0}
    ]


def test_build_filtered_deck_ocr_inputs_keeps_requested_slides() -> None:
    deck = Deck(
        deck_id="deck-filtered",
        prompt_style="uniform",
        slides=[
            Slide(id="slide-1.html", title_html="", body_html=""),
            Slide(id="slide-2.html", title_html="", body_html=""),
            Slide(id="slide-3.html", title_html="", body_html=""),
        ],
    )
    layout_payload = {
        "deck_id": "deck-filtered",
        "lang": "eng",
        "slides": [
            {
                "slide_id": "slide-1.html",
                "slide_number": 1,
                "page_number": 1,
                "blocks": [],
            },
            {
                "slide_id": "slide-2.html",
                "slide_number": 2,
                "page_number": 2,
                "blocks": [],
            },
            {
                "slide_id": "slide-3.html",
                "slide_number": 3,
                "page_number": 3,
                "blocks": [],
            },
        ],
    }

    filtered_deck, filtered_layout = build_filtered_deck_ocr_inputs(
        deck,
        layout_payload,
        deck_id="deck-filtered",
        lang="eng",
        slide_ids=["slide-3.html", "slide-1.html"],
    )

    assert [slide.id for slide in filtered_deck.slides] == [
        "slide-1.html",
        "slide-3.html",
    ]
    assert [slide["slide_id"] for slide in filtered_layout["slides"]] == [
        "slide-1.html",
        "slide-3.html",
    ]
    assert filtered_deck.prompt_style == "uniform"


def test_build_deck_ocr_payload_reads_enriched_semantic_layout_types(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-layout-guided-semantic-types"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (140, 100), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-title",
                            "type": "title",
                            "detected_type": "unknown",
                            "bbox": {"x": 6.0, "y": 6.0, "w": 90.0, "h": 14.0},
                            "confidence": 0.75,
                        },
                        {
                            "block_id": "block-bullet",
                            "type": "bullet_item",
                            "bbox": {"x": 8.0, "y": 28.0, "w": 85.0, "h": 12.0},
                            "confidence": 0.95,
                        },
                        {
                            "block_id": "block-metric",
                            "type": "metric",
                            "bbox": {"x": 102.0, "y": 18.0, "w": 28.0, "h": 40.0},
                            "confidence": 0.92,
                        },
                        {
                            "block_id": "block-label",
                            "type": "exhibit_label",
                            "bbox": {"x": 100.0, "y": 64.0, "w": 34.0, "h": 10.0},
                            "confidence": 0.88,
                        },
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda image_bytes, lang, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Titolo recuperato",
                "bbox": {"x": 6.0, "y": 6.0, "w": 90.0, "h": 14.0},
                "confidence": 0.96,
            },
            {
                "line_id": "line-1",
                "text": "Primo punto chiave",
                "bbox": {"x": 8.0, "y": 28.0, "w": 85.0, "h": 12.0},
                "confidence": 0.94,
            },
            {
                "line_id": "line-2",
                "text": "448M",
                "bbox": {"x": 102.0, "y": 18.0, "w": 28.0, "h": 40.0},
                "confidence": 0.98,
            },
            {
                "line_id": "line-3",
                "text": "Popolazione Totale",
                "bbox": {"x": 100.0, "y": 64.0, "w": 34.0, "h": 10.0},
                "confidence": 0.95,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "Titolo recuperato\nPrimo punto chiave\n448M\nPopolazione Totale",
    )

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    slide_payload = payload["slides"][0]
    assert slide_payload["title_text"] == "Titolo recuperato"
    assert slide_payload["ocr_text"].startswith("Titolo recuperato")
    assert slide_payload["blocks"][0]["type"] == "title"
    assert slide_payload["blocks"][0]["text"] == "Titolo recuperato"
    assert slide_payload["blocks"][1]["type"] == "bullet_item"
    assert slide_payload["blocks"][1]["text"] == "Primo punto chiave"
    assert slide_payload["blocks"][1]["items"] == ["Primo punto chiave"]
    assert slide_payload["blocks"][2]["type"] == "metric"
    assert slide_payload["blocks"][2]["text"] == "448M"
    assert slide_payload["blocks"][3]["type"] == "exhibit_label"
    assert slide_payload["blocks"][3]["text"] == "Popolazione Totale"


def test_build_deck_ocr_payload_expands_title_crops_before_ocr(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-layout-guided-padding"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (100, 80), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    observed_crop_sizes: list[tuple[int, int]] = []

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-title",
                            "type": "title",
                            "bbox": {"x": 30.0, "y": 20.0, "w": 30.0, "h": 20.0},
                            "confidence": 0.5,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )

    def _fake_extract_raw_ocr_from_image_bytes(image_bytes, lang, **kwargs):
        if kwargs.get("preprocess_profile") != "document_scan":
            return []
        with Image.open(io.BytesIO(image_bytes)) as crop:
            observed_crop_sizes.append(crop.size)
        return [[[[0.0, 0.0], [8.0, 0.0], [8.0, 4.0], [0.0, 4.0]], ["Titolo", 0.9]]]

    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        _fake_extract_raw_ocr_from_image_bytes,
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Titolo",
                "bbox": {"x": 0.0, "y": 0.0, "w": 8.0, "h": 4.0},
                "confidence": 0.9,
            }
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "Titolo",
    )

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    assert observed_crop_sizes == [(78, 64), (78, 64)]
    slide_payload = payload["slides"][0]
    assert slide_payload["title_text"] == "Titolo"
    assert slide_payload["blocks"][0]["text"] == "Titolo"


def test_build_deck_ocr_payload_applies_deterministic_text_cleanup(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-layout-guided-cleanup"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (120, 90), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-title",
                            "type": "title",
                            "bbox": {"x": 0.0, "y": 0.0, "w": 100.0, "h": 20.0},
                            "confidence": 0.95,
                        },
                        {
                            "block_id": "block-list",
                            "type": "list",
                            "bbox": {"x": 0.0, "y": 24.0, "w": 100.0, "h": 24.0},
                            "confidence": 0.95,
                        },
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Titolo.Panorama",
                "bbox": {"x": 4.0, "y": 4.0, "w": 70.0, "h": 10.0},
                "confidence": 0.91,
            },
            {
                "line_id": "line-1",
                "text": "gliUPSx e I'ERP. Potenza a ≤ 250w e latenza fino a 25 ms",
                "bbox": {"x": 4.0, "y": 28.0, "w": 90.0, "h": 10.0},
                "confidence": 0.89,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: (
            "Titolo.Panorama\n"
            "gliUPSx e I'ERP. Potenza a ≤ 250w e latenza fino a 25 ms"
        ),
    )

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    slide_payload = payload["slides"][0]
    assert slide_payload["title_text"] == "Titolo. Panorama"
    assert slide_payload["blocks"][0]["text"] == "Titolo. Panorama"
    assert slide_payload["blocks"][1]["text"] == (
        "gli UPSX e l'ERP. Potenza ≤ 250W e latenza fino a 25 ms"
    )
    assert slide_payload["blocks"][1]["items"] == [
        "gli UPSX e l'ERP. Potenza ≤ 250W e latenza fino a 25 ms"
    ]
    assert slide_payload["bullet_texts"] == [
        "gli UPSX e l'ERP. Potenza ≤ 250W e latenza fino a 25 ms"
    ]
    assert slide_payload["ocr_text"] == (
        "Titolo. Panorama\ngli UPSX e l'ERP. Potenza ≤ 250W e latenza fino a 25 ms"
    )


def test_build_deck_ocr_payload_applies_llm_correction_to_editable_blocks(
    monkeypatch, tmp_path: Path
) -> None:
    deck_id = "deck-layout-guided-llm"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (140, 90), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-title",
                            "type": "title",
                            "bbox": {"x": 0.0, "y": 0.0, "w": 120.0, "h": 18.0},
                            "confidence": 0.95,
                        },
                        {
                            "block_id": "block-list",
                            "type": "list",
                            "bbox": {"x": 0.0, "y": 24.0, "w": 120.0, "h": 22.0},
                            "confidence": 0.95,
                        },
                        {
                            "block_id": "block-text",
                            "type": "text",
                            "bbox": {"x": 0.0, "y": 52.0, "w": 120.0, "h": 18.0},
                            "confidence": 0.95,
                        },
                        {
                            "block_id": "block-figure",
                            "type": "figure",
                            "bbox": {"x": 122.0, "y": 0.0, "w": 18.0, "h": 60.0},
                            "confidence": 0.95,
                        },
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [{"x": 122.0, "y": 0.0, "w": 18.0, "h": 60.0}],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Regole di Conservazione: II Glossario Operativo",
                "bbox": {"x": 2.0, "y": 2.0, "w": 110.0, "h": 10.0},
                "confidence": 0.91,
            },
            {
                "line_id": "line-1",
                "text": (
                    "Replica: Copia sincronizzata dei dati, che include gli snapshot e, "
                    "inviaccezionale, speciiche retentioninoa 500 TB."
                ),
                "bbox": {"x": 2.0, "y": 28.0, "w": 110.0, "h": 10.0},
                "confidence": 0.89,
            },
            {
                "line_id": "line-2",
                "text": "Nota finate di supporto.",
                "bbox": {"x": 2.0, "y": 56.0, "w": 80.0, "h": 10.0},
                "confidence": 0.88,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: (
            "Regole di Conservazione: II Glossario Operativo\n"
            "Replica: Copia sincronizzata dei dati, che include gli snapshot e, inviaccezionale, speciiche retentioninoa 500 TB.\n"
            "Nota finate di supporto."
        ),
    )

    def _fake_init_llm_wrapper(_user_text, session, notifier=None) -> None:
        session.state["llm_wrapper"] = object()

    monkeypatch.setattr(
        "src.slides.ocr_service.init_llm_wrapper", _fake_init_llm_wrapper
    )

    captured: dict[str, object] = {}

    def _fake_run_step_text(
        llm_wrapper, step, system_prompt, prompts, *, tools=None, tool_choice="auto"
    ):
        captured["llm_wrapper"] = llm_wrapper
        captured["step"] = step
        captured["system_prompt"] = system_prompt
        captured["prompts"] = list(prompts)
        return [
            "Regole di Conservazione: Il Glossario Operativo",
            (
                "Replica: Copia sincronizzata dei dati, che include gli snapshot e, "
                "in via eccezionale, specifiche retention fino a 500 TB."
            ),
            "Nota finale di supporto.",
        ]

    monkeypatch.setattr("src.slides.ocr_service.run_step_text", _fake_run_step_text)

    def _fake_run_step_json(llm_wrapper, step, system_prompt, prompts, **kwargs):
        if step == "slideOcrResidualAuditQuery":
            return [
                {"status": "ok", "reason": "", "suggested_text": ""},
                {"status": "ok", "reason": "", "suggested_text": ""},
                {"status": "ok", "reason": "", "suggested_text": ""},
            ]
        if step == "slideOcrVisualCorrectionQuery":
            return [
                {"status": "ok", "reason": "", "corrected_text": "", "confidence": 0.0},
                {"status": "ok", "reason": "", "corrected_text": "", "confidence": 0.0},
                {"status": "ok", "reason": "", "corrected_text": "", "confidence": 0.0},
            ]
        raise AssertionError(step)

    monkeypatch.setattr("src.slides.ocr_service.run_step_json", _fake_run_step_json)

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    slide_payload = payload["slides"][0]
    assert captured["step"] == "slideOcrSemanticQuery"
    assert captured["system_prompt"] == (
        "You are correcting OCR transcriptions from presentation slides. Return corrected text only."
    )
    assert len(captured["prompts"]) == 3
    assert slide_payload["title_text"] == (
        "Regole di Conservazione: Il Glossario Operativo"
    )
    assert slide_payload["blocks"][0]["text"] == (
        "Regole di Conservazione: Il Glossario Operativo"
    )
    assert slide_payload["blocks"][1]["type"] == "bullet_item"
    assert slide_payload["blocks"][1]["text"] == (
        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB."
    )
    assert slide_payload["blocks"][1]["items"] == [
        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB."
    ]
    assert slide_payload["blocks"][2]["text"] == "Nota finale di supporto."
    assert slide_payload["blocks"][3]["text"] == ""
    assert slide_payload["ocr_text"] == (
        "Regole di Conservazione: Il Glossario Operativo\n"
        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB.\n"
        "Nota finale di supporto."
    )


def test_build_deck_ocr_payload_rejects_llm_correction_that_changes_numbers(
    monkeypatch, tmp_path: Path
) -> None:
    deck_id = "deck-layout-guided-llm-guard"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (120, 90), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-list",
                            "type": "list",
                            "bbox": {"x": 0.0, "y": 24.0, "w": 100.0, "h": 24.0},
                            "confidence": 0.95,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Capacità fino a 500 TB.",
                "bbox": {"x": 4.0, "y": 28.0, "w": 90.0, "h": 10.0},
                "confidence": 0.89,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "Capacità fino a 500 TB.",
    )

    def _fake_init_llm_wrapper(_user_text, session, notifier=None) -> None:
        session.state["llm_wrapper"] = object()

    monkeypatch.setattr(
        "src.slides.ocr_service.init_llm_wrapper", _fake_init_llm_wrapper
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.run_step_text",
        lambda *args, **kwargs: ["Capacità fino a 900 TB."],
    )

    def _fake_run_step_json(llm_wrapper, step, system_prompt, prompts, **kwargs):
        if step == "slideOcrResidualAuditQuery":
            return [{"status": "ok", "reason": "", "suggested_text": ""}]
        if step == "slideOcrVisualCorrectionQuery":
            return [
                {"status": "ok", "reason": "", "corrected_text": "", "confidence": 0.0}
            ]
        raise AssertionError(step)

    monkeypatch.setattr("src.slides.ocr_service.run_step_json", _fake_run_step_json)

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    slide_payload = payload["slides"][0]
    assert slide_payload["blocks"][0]["text"] == "Capacità fino a 500 TB."
    assert slide_payload["blocks"][0]["items"] == ["Capacità fino a 500 TB."]
    assert slide_payload["bullet_texts"] == ["Capacità fino a 500 TB."]
    assert slide_payload["ocr_text"] == "Capacità fino a 500 TB."


def test_build_deck_ocr_payload_fails_on_openai_correction_failures(
    monkeypatch, tmp_path: Path
) -> None:
    deck_id = "deck-layout-guided-openai-failure"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (120, 90), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-list",
                            "type": "list",
                            "bbox": {"x": 0.0, "y": 24.0, "w": 100.0, "h": 24.0},
                            "confidence": 0.95,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Capacità fino a 500 TB.",
                "bbox": {"x": 4.0, "y": 28.0, "w": 90.0, "h": 10.0},
                "confidence": 0.89,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "Capacità fino a 500 TB.",
    )

    def _fake_init_llm_wrapper(_user_text, session, notifier=None) -> None:
        session.state["llm_wrapper"] = object()

    class OcrCorrectionConnectionError(ocr_service.OpenAIError):
        pass

    def _raise_openai_error(*args, **kwargs):
        raise OcrCorrectionConnectionError("connection failed")

    monkeypatch.setattr(
        "src.slides.ocr_service.init_llm_wrapper", _fake_init_llm_wrapper
    )
    monkeypatch.setattr("src.slides.ocr_service.run_step_text", _raise_openai_error)

    with pytest.raises(
        SlideOcrOpenAIError,
        match="OpenAI call failed during slide OCR semantic correction",
    ):
        build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)


def test_build_deck_ocr_payload_adds_residual_audit_metadata_without_changing_text(
    monkeypatch, tmp_path: Path
) -> None:
    deck_id = "deck-layout-guided-residual-audit"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (120, 90), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-list",
                            "type": "list",
                            "bbox": {"x": 0.0, "y": 24.0, "w": 100.0, "h": 24.0},
                            "confidence": 0.95,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specie retention fino a 500 TB.",
                "bbox": {"x": 4.0, "y": 28.0, "w": 90.0, "h": 10.0},
                "confidence": 0.89,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: (
            "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specie retention fino a 500 TB."
        ),
    )

    def _fake_init_llm_wrapper(_user_text, session, notifier=None) -> None:
        session.state["llm_wrapper"] = object()

    monkeypatch.setattr(
        "src.slides.ocr_service.init_llm_wrapper", _fake_init_llm_wrapper
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.run_step_text",
        lambda *args, **kwargs: [
            "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specie retention fino a 500 TB."
        ],
    )
    captured: dict[str, object] = {"steps": []}

    def _fake_run_step_json(llm_wrapper, step, system_prompt, prompts, **kwargs):
        captured["llm_wrapper"] = llm_wrapper
        captured["steps"].append(step)
        captured[f"{step}_system_prompt"] = system_prompt
        captured[f"{step}_prompts"] = list(prompts)
        if step == "slideOcrResidualAuditQuery":
            return [
                {
                    "status": "suspicious",
                    "reason": "The phrase 'specie retention' looks suspicious in Italian.",
                    "suggested_text": (
                        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB."
                    ),
                }
            ]
        if step == "slideOcrVisualCorrectionQuery":
            return [
                {
                    "status": "ok",
                    "reason": "",
                    "corrected_text": "",
                    "confidence": 0.0,
                }
            ]
        raise AssertionError(step)

    monkeypatch.setattr("src.slides.ocr_service.run_step_json", _fake_run_step_json)

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    slide_payload = payload["slides"][0]
    block = slide_payload["blocks"][0]
    assert captured["steps"] == [
        "slideOcrResidualAuditQuery",
        "slideOcrVisualCorrectionQuery",
    ]
    assert block["text"] == (
        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specie retention fino a 500 TB."
    )
    assert block["items"] == [
        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specie retention fino a 500 TB."
    ]
    assert block["audit_status"] == "suspicious"
    assert (
        block["audit_reason"]
        == "The phrase 'specie retention' looks suspicious in Italian."
    )
    assert block["audit_suggested_text"] == (
        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB."
    )


def test_build_deck_ocr_payload_applies_vlm_correction_to_suspicious_blocks(
    monkeypatch, tmp_path: Path
) -> None:
    deck_id = "deck-layout-guided-visual-correction"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (120, 90), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-list",
                            "type": "list",
                            "bbox": {"x": 0.0, "y": 24.0, "w": 100.0, "h": 24.0},
                            "confidence": 0.95,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specie retention fino a 500 TB.",
                "bbox": {"x": 4.0, "y": 28.0, "w": 90.0, "h": 10.0},
                "confidence": 0.89,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: (
            "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specie retention fino a 500 TB."
        ),
    )

    def _fake_init_llm_wrapper(_user_text, session, notifier=None) -> None:
        session.state["llm_wrapper"] = object()

    monkeypatch.setattr(
        "src.slides.ocr_service.init_llm_wrapper", _fake_init_llm_wrapper
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.run_step_text",
        lambda *args, **kwargs: [
            "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specie retention fino a 500 TB."
        ],
    )
    captured: dict[str, object] = {}

    def _fake_run_step_json(llm_wrapper, step, system_prompt, prompts, **kwargs):
        if step == "slideOcrResidualAuditQuery":
            return [
                {
                    "status": "suspicious",
                    "reason": "The phrase 'specie retention' looks suspicious in Italian.",
                    "suggested_text": (
                        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB."
                    ),
                }
            ]
        if step == "slideOcrVisualCorrectionQuery":
            captured["prompts"] = list(prompts)
            return [
                {
                    "status": "corrected",
                    "reason": "The image clearly shows 'specifiche'.",
                    "corrected_text": (
                        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB."
                    ),
                    "confidence": 0.96,
                }
            ]
        raise AssertionError(step)

    monkeypatch.setattr("src.slides.ocr_service.run_step_json", _fake_run_step_json)

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    slide_payload = payload["slides"][0]
    block = slide_payload["blocks"][0]
    assert block["text"] == (
        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB."
    )
    assert block["items"] == [
        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB."
    ]
    assert block["audit_status"] == "suspicious"
    assert block["visual_status"] == "corrected"
    assert block["visual_reason"] == "The image clearly shows 'specifiche'."
    assert block["visual_suggested_text"] == (
        "Replica: Copia sincronizzata dei dati, che include gli snapshot e, in via eccezionale, specifiche retention fino a 500 TB."
    )
    assert block["visual_confidence"] == 0.96
    visual_prompt = captured["prompts"][0]["user_content"]
    assert visual_prompt[0]["type"] == "input_text"
    assert visual_prompt[1]["type"] == "input_image"


def test_build_deck_ocr_payload_applies_vlm_correction_that_splits_fused_words(
    monkeypatch, tmp_path: Path
) -> None:
    deck_id = "deck-layout-guided-visual-fused-words"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (160, 100), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "eng",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-list",
                            "type": "list",
                            "bbox": {"x": 0.0, "y": 24.0, "w": 140.0, "h": 30.0},
                            "confidence": 0.95,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": 'Atightervariantadding"repair"claims captures 13.2% of top sellers.',
                "bbox": {"x": 4.0, "y": 28.0, "w": 120.0, "h": 12.0},
                "confidence": 0.89,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: 'Atightervariantadding"repair"claims captures 13.2% of top sellers.',
    )

    def _fake_init_llm_wrapper(_user_text, session, notifier=None) -> None:
        session.state["llm_wrapper"] = object()

    monkeypatch.setattr(
        "src.slides.ocr_service.init_llm_wrapper", _fake_init_llm_wrapper
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.run_step_text",
        lambda *args, **kwargs: [
            'Atightervariantadding"repair"claims captures 13.2% of top sellers.'
        ],
    )

    def _fake_run_step_json(llm_wrapper, step, system_prompt, prompts, **kwargs):
        if step == "slideOcrResidualAuditQuery":
            return [
                {
                    "status": "suspicious",
                    "reason": "Merged words and misplaced quotation marks.",
                    "suggested_text": (
                        "A tighter variant adding 'repair' claims captures 13.2% of top sellers."
                    ),
                }
            ]
        if step == "slideOcrVisualCorrectionQuery":
            return [
                {
                    "status": "corrected",
                    "reason": "The image clearly shows the spaced words.",
                    "corrected_text": (
                        'A tighter variant adding "repair" claims captures 13.2% of top sellers.'
                    ),
                    "confidence": 0.96,
                }
            ]
        raise AssertionError(step)

    monkeypatch.setattr("src.slides.ocr_service.run_step_json", _fake_run_step_json)

    payload = build_deck_ocr_payload(deck, deck_path, lang="eng", include_bboxes=True)

    block = payload["slides"][0]["blocks"][0]
    assert block["text"] == (
        'A tighter variant adding "repair" claims captures 13.2% of top sellers.'
    )
    assert block["items"] == [
        'A tighter variant adding "repair" claims captures 13.2% of top sellers.'
    ]
    assert payload["slides"][0]["ocr_text"] == (
        'A tighter variant adding "repair" claims captures 13.2% of top sellers.'
    )
    assert block["visual_status"] == "corrected"
    assert block["visual_confidence"] == 0.96


def test_build_deck_ocr_payload_keeps_visual_suggestion_when_confidence_is_low(
    monkeypatch, tmp_path: Path
) -> None:
    deck_id = "deck-layout-guided-visual-low-confidence"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (120, 90), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-text",
                            "type": "text",
                            "bbox": {"x": 0.0, "y": 24.0, "w": 100.0, "h": 24.0},
                            "confidence": 0.95,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Nota finate di supporto.",
                "bbox": {"x": 4.0, "y": 28.0, "w": 90.0, "h": 10.0},
                "confidence": 0.89,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "Nota finate di supporto.",
    )

    def _fake_init_llm_wrapper(_user_text, session, notifier=None) -> None:
        session.state["llm_wrapper"] = object()

    monkeypatch.setattr(
        "src.slides.ocr_service.init_llm_wrapper", _fake_init_llm_wrapper
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.run_step_text",
        lambda *args, **kwargs: ["Nota finate di supporto."],
    )

    def _fake_run_step_json(llm_wrapper, step, system_prompt, prompts, **kwargs):
        if step == "slideOcrResidualAuditQuery":
            return [
                {
                    "status": "suspicious",
                    "reason": "The word 'finate' may be wrong.",
                    "suggested_text": "Nota finale di supporto.",
                }
            ]
        if step == "slideOcrVisualCorrectionQuery":
            return [
                {
                    "status": "corrected",
                    "reason": "Possibly 'finale', but the crop is not sharp enough.",
                    "corrected_text": "Nota finale di supporto.",
                    "confidence": 0.42,
                }
            ]
        raise AssertionError(step)

    monkeypatch.setattr("src.slides.ocr_service.run_step_json", _fake_run_step_json)

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    block = payload["slides"][0]["blocks"][0]
    assert block["text"] == "Nota finate di supporto."
    assert block["audit_status"] == "suspicious"
    assert block["visual_status"] == "corrected"
    assert block["visual_suggested_text"] == "Nota finale di supporto."
    assert block["visual_confidence"] == 0.42


def test_build_deck_ocr_payload_builds_table_model_for_simple_tables(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-layout-guided-table"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (220, 160), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "eng",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-table",
                            "type": "table",
                            "bbox": {"x": 20.0, "y": 30.0, "w": 180.0, "h": 100.0},
                            "confidence": 0.95,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [{"x": 20.0, "y": 30.0, "w": 180.0, "h": 100.0}],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Country",
                "bbox": {"x": 32.0, "y": 42.0, "w": 54.0, "h": 12.0},
                "confidence": 0.94,
            },
            {
                "line_id": "line-1",
                "text": "Revenue",
                "bbox": {"x": 118.0, "y": 42.0, "w": 58.0, "h": 12.0},
                "confidence": 0.94,
            },
            {
                "line_id": "line-2",
                "text": "Italy",
                "bbox": {"x": 32.0, "y": 70.0, "w": 42.0, "h": 12.0},
                "confidence": 0.93,
            },
            {
                "line_id": "line-3",
                "text": "25",
                "bbox": {"x": 140.0, "y": 70.0, "w": 18.0, "h": 12.0},
                "confidence": 0.93,
            },
            {
                "line_id": "line-4",
                "text": "France",
                "bbox": {"x": 32.0, "y": 96.0, "w": 50.0, "h": 12.0},
                "confidence": 0.92,
            },
            {
                "line_id": "line-5",
                "text": "31",
                "bbox": {"x": 140.0, "y": 96.0, "w": 18.0, "h": 12.0},
                "confidence": 0.92,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "Country Revenue\nItaly 25\nFrance 31",
    )

    payload = build_deck_ocr_payload(deck, deck_path, lang="eng", include_bboxes=True)

    table_block = payload["slides"][0]["blocks"][0]
    assert table_block["table_model"] is not None
    assert table_block["table_model"]["source"] == "deterministic_simple"
    assert table_block["table_model"]["column_count"] == 2
    assert table_block["table_model"]["row_count"] == 3
    assert table_block["table_model"]["header_rows"] == 1
    assert table_block["table_model"]["rows"][1]["cells"][0]["text"] == "Italy"
    assert table_block["table_model"]["rows"][1]["cells"][1]["align"] == "right"


def test_build_deck_ocr_payload_uses_table_fallback_for_low_confidence_tables(
    monkeypatch, tmp_path: Path
) -> None:
    deck_id = "deck-layout-guided-table-fallback"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (220, 160), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "eng",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-table",
                            "type": "table",
                            "bbox": {"x": 20.0, "y": 30.0, "w": 180.0, "h": 100.0},
                            "confidence": 0.95,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [{"x": 20.0, "y": 30.0, "w": 180.0, "h": 100.0}],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "Country Revenue Italy 25 France 31",
                "bbox": {"x": 28.0, "y": 54.0, "w": 160.0, "h": 16.0},
                "confidence": 0.81,
            }
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "Country Revenue Italy 25 France 31",
    )

    def _fake_init_llm_wrapper(_user_text, session, notifier=None) -> None:
        session.state["llm_wrapper"] = object()

    monkeypatch.setattr(
        "src.slides.ocr_service.init_llm_wrapper", _fake_init_llm_wrapper
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.run_step_text",
        lambda *args, **kwargs: ["Country Revenue Italy 25 France 31"],
    )

    captured_steps: list[str] = []

    def _fake_run_step_json(llm_wrapper, step, system_prompt, prompts, **kwargs):
        captured_steps.append(step)
        if step == "slideOcrResidualAuditQuery":
            return [{"status": "ok", "reason": "", "suggested_text": ""}]
        if step == "slideOcrVisualCorrectionQuery":
            return [
                {
                    "status": "ok",
                    "reason": "",
                    "corrected_text": "",
                    "confidence": 0.0,
                }
            ]
        if step == "readImageTableStructureQuery":
            return [
                {
                    "status": "uncertain",
                    "reason": "The crop is too small to recover table structure confidently.",
                    "confidence": 0.2,
                    "table_bounds": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                    "header": [],
                    "rows": [],
                }
            ]
        if step == "readImageTableQuery":
            assert prompts[0]["user_content"][0]["type"] == "input_text"
            assert prompts[0]["user_content"][1]["type"] == "input_image"
            return [
                {
                    "status": "ok",
                    "reason": "Simple two-column table is legible.",
                    "confidence": 0.93,
                    "header": ["Country", "Revenue"],
                    "rows": [["Italy", "25"], ["France", "31"]],
                }
            ]
        raise AssertionError(step)

    monkeypatch.setattr("src.slides.ocr_service.run_step_json", _fake_run_step_json)

    payload = build_deck_ocr_payload(deck, deck_path, lang="eng", include_bboxes=True)

    table_block = payload["slides"][0]["blocks"][0]
    assert captured_steps == [
        "slideOcrResidualAuditQuery",
        "readImageTableStructureQuery",
        "readImageTableQuery",
    ]
    assert table_block["table_model"] is not None
    assert table_block["table_model"]["source"] == "vlm_simple"
    assert table_block["table_model"]["confidence"] == 0.93
    assert table_block["table_model"]["rows"][0]["cells"][0]["text"] == "Country"
    assert table_block["table_model"]["rows"][2]["cells"][1]["text"] == "31"


def test_build_deck_ocr_payload_prefers_vlm_table_structure_for_complex_tables(
    monkeypatch, tmp_path: Path
) -> None:
    deck_id = "deck-layout-guided-table-structure"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (240, 160), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service._build_local_llm_wrapper", lambda: object()
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.run_step_text",
        lambda llm_wrapper, step, system_prompt, prompts, **kwargs: [
            "" for _ in prompts
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-body",
                            "type": "text",
                            "bbox": {"x": 20.0, "y": 28.0, "w": 200.0, "h": 22.0},
                            "confidence": 0.9,
                        },
                        {
                            "block_id": "block-table",
                            "type": "table",
                            "bbox": {"x": 20.0, "y": 58.0, "w": 200.0, "h": 88.0},
                            "confidence": 0.97,
                        },
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [{"x": 20.0, "y": 58.0, "w": 200.0, "h": 88.0}],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": "line-0",
                "text": "La tabella riassume i livelli di servizio.",
                "bbox": {"x": 20.0, "y": 32.0, "w": 180.0, "h": 12.0},
                "confidence": 0.95,
            },
            {
                "line_id": "line-1",
                "text": "Segmento",
                "bbox": {"x": 22.0, "y": 70.0, "w": 24.0, "h": 9.0},
                "confidence": 0.98,
            },
            {
                "line_id": "line-2",
                "text": "Classe (livello alto,",
                "bbox": {"x": 55.0, "y": 70.0, "w": 68.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-3",
                "text": "Soglia Dati",
                "bbox": {"x": 132.0, "y": 70.0, "w": 46.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-4",
                "text": "Requisiti Operativi Chiave",
                "bbox": {"x": 181.0, "y": 72.0, "w": 44.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-5",
                "text": "risposta ≤4 ore)",
                "bbox": {"x": 56.0, "y": 82.0, "w": 32.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-6",
                "text": "Applicabile",
                "bbox": {"x": 132.0, "y": 82.0, "w": 28.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-7",
                "text": "Segmento A",
                "bbox": {"x": 22.0, "y": 98.0, "w": 22.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-8",
                "text": "Servizio standard",
                "bbox": {"x": 55.0, "y": 98.0, "w": 76.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-9",
                "text": "Si",
                "bbox": {"x": 132.0, "y": 98.0, "w": 10.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-10",
                "text": "Nessuna configurazione aggiuntiva",
                "bbox": {"x": 150.0, "y": 98.0, "w": 74.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-11",
                "text": "Segmento B",
                "bbox": {"x": 22.0, "y": 112.0, "w": 24.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-12",
                "text": "Servizio premium",
                "bbox": {"x": 55.0, "y": 112.0, "w": 69.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-13",
                "text": "Su richiesta",
                "bbox": {"x": 132.0, "y": 112.0, "w": 42.0, "h": 9.0},
                "confidence": 0.97,
            },
            {
                "line_id": "line-14",
                "text": "Approvazione richiesta per l'attivazione",
                "bbox": {"x": 150.0, "y": 112.0, "w": 74.0, "h": 9.0},
                "confidence": 0.97,
            },
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: (
            "La tabella riassume i livelli di servizio.\n"
            "Segmento Classe (livello alto, risposta ≤4 ore) Soglia Dati Applicabile Requisiti Operativi Chiave\n"
            "Segmento A Servizio standard Sì Nessuna configurazione aggiuntiva\n"
            "Segmento B Servizio premium Su richiesta Approvazione richiesta per l'attivazione"
        ),
    )

    captured_steps: list[str] = []

    def _fake_run_step_json(llm_wrapper, step, system_prompt, prompts, **kwargs):
        captured_steps.append(step)
        if step == "slideOcrResidualAuditQuery":
            return [{"status": "ok", "reason": "", "suggested_text": ""}]
        if step == "readImageTableStructureQuery":
            return [
                {
                    "status": "ok",
                    "reason": "The table starts below the paragraph and has four columns with wrapped headers.",
                    "confidence": 0.91,
                    "table_bounds": {"x": 0.0, "y": 0.12, "w": 1.0, "h": 0.88},
                    "header": [
                        "Segmento",
                        "Classe (livello alto, risposta ≤4 ore)",
                        "Soglia Dati Applicabile",
                        "Requisiti Operativi Chiave",
                    ],
                    "rows": [
                        [
                            "Segmento A",
                            "Servizio standard (fino a 500 richieste)",
                            "Sì",
                            "Nessuna configurazione aggiuntiva",
                        ],
                        [
                            "Segmento B",
                            "Servizio premium (fino a 1000 richieste)",
                            "Su richiesta",
                            "Approvazione richiesta per l'attivazione",
                        ],
                    ],
                }
            ]
        if step == "readImageTableQuery":
            raise AssertionError(
                "simple table fallback should not run when structured table VLM succeeds"
            )
        raise AssertionError(step)

    monkeypatch.setattr("src.slides.ocr_service.run_step_json", _fake_run_step_json)

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    table_block = payload["slides"][0]["blocks"][1]
    assert captured_steps == [
        "slideOcrResidualAuditQuery",
        "readImageTableStructureQuery",
    ]
    assert table_block["table_model"] is not None
    assert table_block["table_model"]["source"] == "vlm_structured"
    assert table_block["table_model"]["column_count"] == 4
    assert table_block["table_model"]["row_count"] == 3
    assert table_block["table_model"]["rows"][0]["cells"][0]["text"] == "Segmento"
    assert (
        table_block["table_model"]["rows"][0]["cells"][1]["text"]
        == "Classe (livello alto, risposta ≤4 ore)"
    )
    assert table_block["table_model"]["rows"][1]["cells"][0]["text"] == "Segmento A"
    assert "La tabella riassume" not in json.dumps(
        table_block["table_model"], ensure_ascii=False
    )


def test_build_deck_ocr_payload_does_not_ocr_image_only_regions(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-layout-guided-image-only"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (100, 80), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    ocr_calls = {"count": 0}

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "eng",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-image",
                            "type": "figure",
                            "bbox": {"x": 10.0, "y": 10.0, "w": 70.0, "h": 55.0},
                            "confidence": 0.95,
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [{"x": 10.0, "y": 10.0, "w": 70.0, "h": 55.0}],
                }
            ],
        },
    )

    def _record_unexpected_ocr_call(*args, **kwargs):
        ocr_calls["count"] += 1
        return []

    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        _record_unexpected_ocr_call,
    )

    payload = build_deck_ocr_payload(deck, deck_path, lang="eng", include_bboxes=True)

    slide_payload = payload["slides"][0]
    assert ocr_calls["count"] == 0
    assert slide_payload["ocr_text"] == ""
    assert slide_payload["title_text"] == ""
    assert slide_payload["lines"] == []
    assert slide_payload["blocks"][0]["type"] == "figure"
    assert slide_payload["blocks"][0]["text"] == ""
    assert "visual_text" not in slide_payload["blocks"][0]
    assert slide_payload["figure_regions"] == [
        {"x": 10.0, "y": 10.0, "w": 70.0, "h": 55.0}
    ]


def test_build_deck_ocr_payload_promotes_definition_blocks_to_lists(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-list-promotion"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (80, 80), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-0",
                            "type": "text",
                            "bbox": {"x": 5.0, "y": 10.0, "w": 60.0, "h": 10.0},
                        },
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "bbox": {"x": 6.0, "y": 24.0, "w": 61.0, "h": 10.0},
                        },
                        {
                            "block_id": "block-2",
                            "type": "text",
                            "bbox": {"x": 5.0, "y": 38.0, "w": 62.0, "h": 10.0},
                        },
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )

    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": f"line-{index}",
                "text": text,
                "bbox": {
                    "x": bbox[0],
                    "y": bbox[1],
                    "w": bbox[2],
                    "h": bbox[3],
                },
                "confidence": 0.9,
            }
            for index, (text, bbox) in enumerate(
                [
                    (
                        "SLA (Service Level Agreement): standard service target",
                        (8.0, 12.0, 40.0, 3.0),
                    ),
                    (
                        "RTO (Recovery Time Objective): recovery target",
                        (9.0, 26.0, 40.0, 3.0),
                    ),
                    (
                        "Retention: archive duration",
                        (8.0, 40.0, 40.0, 3.0),
                    ),
                ]
            )
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "\n".join(
            [
                "SLA (Service Level Agreement): standard service target",
                "RTO (Recovery Time Objective): recovery target",
                "Retention: archive duration",
            ]
        ),
    )

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    slide_payload = payload["slides"][0]
    assert [block["type"] for block in slide_payload["blocks"]] == [
        "bullet_item",
        "bullet_item",
        "bullet_item",
    ]
    assert slide_payload["blocks"][0]["items"] == [
        "SLA (Service Level Agreement): standard service target"
    ]
    assert slide_payload["bullet_texts"] == [
        "SLA (Service Level Agreement): standard service target",
        "RTO (Recovery Time Objective): recovery target",
        "Retention: archive duration",
    ]


def test_build_deck_ocr_payload_promotes_stacked_text_cards_to_lists(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-stacked-card-promotion"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (80, 80), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "ita",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-0",
                            "type": "text",
                            "bbox": {"x": 5.0, "y": 10.0, "w": 60.0, "h": 10.0},
                        },
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "bbox": {"x": 6.0, "y": 24.0, "w": 61.0, "h": 11.0},
                        },
                        {
                            "block_id": "block-2",
                            "type": "text",
                            "bbox": {"x": 5.0, "y": 39.0, "w": 62.0, "h": 10.0},
                        },
                        {
                            "block_id": "block-3",
                            "type": "text",
                            "bbox": {"x": 6.0, "y": 54.0, "w": 61.0, "h": 11.0},
                        },
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )

    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        lambda raw, **kwargs: [
            {
                "line_id": f"line-{index}",
                "text": text,
                "bbox": {
                    "x": bbox[0],
                    "y": bbox[1],
                    "w": bbox[2],
                    "h": bbox[3],
                },
                "confidence": 0.9,
            }
            for index, (text, bbox) in enumerate(
                [
                    (
                        "Questo servizio richiede approvazione iniziale.",
                        (8.0, 12.0, 40.0, 3.0),
                    ),
                    (
                        "Il piano standard copre il perimetro operativo.",
                        (9.0, 27.0, 40.0, 3.0),
                    ),
                    (
                        "Il piano avanzato aumenta la capacità con controlli dedicati.",
                        (8.0, 42.0, 40.0, 3.0),
                    ),
                    (
                        "Il piano archivio adotta limiti più alti per la conservazione.",
                        (9.0, 57.0, 40.0, 3.0),
                    ),
                ]
            )
        ],
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        lambda raw: "\n".join(
            [
                "Questo servizio richiede approvazione iniziale.",
                "Il piano standard copre il perimetro operativo.",
                "Il piano avanzato aumenta la capacità con controlli dedicati.",
                "Il piano archivio adotta limiti più alti per la conservazione.",
            ]
        ),
    )

    payload = build_deck_ocr_payload(deck, deck_path, lang="ita", include_bboxes=True)

    slide_payload = payload["slides"][0]
    assert [block["type"] for block in slide_payload["blocks"]] == [
        "bullet_item",
        "bullet_item",
        "bullet_item",
        "bullet_item",
    ]
    assert slide_payload["bullet_texts"] == [
        "Questo servizio richiede approvazione iniziale.",
        "Il piano standard copre il perimetro operativo.",
        "Il piano avanzato aumenta la capacità con controlli dedicati.",
        "Il piano archivio adotta limiti più alti per la conservazione.",
    ]


def test_build_deck_ocr_payload_recovers_callout_heading_from_decorative_block(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-callout-heading"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (260, 200), color=(255, 255, 255)).save(image_path)
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{image_path.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "eng",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [
                        {
                            "block_id": "block-callout-title",
                            "type": "decorative",
                            "bbox": {"x": 72.0, "y": 88.0, "w": 124.0, "h": 20.0},
                            "confidence": 0.92,
                        },
                        {
                            "block_id": "block-callout-body",
                            "type": "callout_banner",
                            "bbox": {"x": 28.0, "y": 116.0, "w": 204.0, "h": 42.0},
                            "confidence": 0.95,
                        },
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                }
            ],
        },
    )

    def _fake_extract_raw_ocr_from_image_bytes(
        image_bytes: bytes,
        lang: str,
        **kwargs,
    ) -> list[dict[str, object]]:
        _ = lang
        _ = kwargs
        with Image.open(io.BytesIO(image_bytes)) as rendered:
            width, height = rendered.size
        if width <= 180 and height <= 60:
            return [{"mode": "callout-title"}]
        return [{"mode": "full-slide"}]

    def _fake_extract_lines_from_raw_ocr_result(raw, **kwargs):
        _ = kwargs
        mode = raw[0]["mode"]
        if mode == "callout-title":
            return [
                {
                    "line_id": "line-title",
                    "text": "Central Synthesis / The Gap",
                    "bbox": {"x": 8.0, "y": 6.0, "w": 150.0, "h": 18.0},
                    "confidence": 0.96,
                }
            ]
        return [
            {
                "line_id": "line-0",
                "text": "Review teams need modular,",
                "bbox": {"x": 32.0, "y": 120.0, "w": 168.0, "h": 12.0},
                "confidence": 0.93,
            },
            {
                "line_id": "line-1",
                "text": "repairable systems with open APIs.",
                "bbox": {"x": 32.0, "y": 136.0, "w": 174.0, "h": 12.0},
                "confidence": 0.92,
            },
        ]

    def _fake_extract_text_from_raw_ocr_result(raw):
        mode = raw[0]["mode"]
        if mode == "callout-title":
            return "Central Synthesis / The Gap"
        return "Review teams need modular,\nrepairable systems with open APIs."

    monkeypatch.setattr(
        "src.slides.ocr_service.extract_raw_ocr_from_image_bytes",
        _fake_extract_raw_ocr_from_image_bytes,
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_lines_from_raw_ocr_result",
        _fake_extract_lines_from_raw_ocr_result,
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_text_from_raw_ocr_result",
        _fake_extract_text_from_raw_ocr_result,
    )

    payload = build_deck_ocr_payload(deck, deck_path, lang="eng", include_bboxes=True)

    slide_payload = payload["slides"][0]
    blocks = {block["block_id"]: block for block in slide_payload["blocks"]}
    heading_block = blocks["block-callout-title"]
    body_block = blocks["block-callout-body"]

    assert heading_block["type"] == "body_text"
    assert heading_block["group_kind"] == "callout"
    assert heading_block["parent_id"] == "block-callout-body"
    assert heading_block["render_mode"] == "native"
    assert heading_block["text"] == "Central Synthesis / The Gap"
    assert body_block["type"] == "callout_banner"
    assert body_block["items"][0] == "Review teams need modular,"
    assert "repairable systems with open API" in body_block["items"][1]


def test_ensure_deck_ocr_payload_fills_missing_image_slides(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-ocr"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True)
    first_image = assets_path / "slide-1.png"
    second_image = assets_path / "slide-2.png"
    Image.new("RGB", (8, 8), color=(255, 255, 255)).save(first_image)
    Image.new("RGB", (8, 8), color=(255, 255, 255)).save(second_image)
    slide_one = Slide(
        id="slide-1.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{first_image.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    slide_two = Slide(
        id="slide-2.html",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/{second_image.name}" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide_one, slide_two])
    cached_payload = {
        "deck_id": deck_id,
        "lang": "eng",
        "generated_at": datetime.now(UTC).isoformat(),
        "slides": [
            {
                "slide_id": slide_one.id,
                "slide_number": 1,
                "page_number": 1,
                "ocr_text": "Existing text",
                "lines": [
                    {"line_id": "line-0", "text": "Existing text", "confidence": 0.91}
                ],
            }
        ],
    }

    captured: dict[str, object] = {}

    def _fake_build_structured_ocr_from_layout_slide(
        image: Image.Image,
        layout_slide: dict[str, object],
        lang: str,
        *,
        slide_id: str,
        slide_number: int,
    ) -> dict[str, object]:
        captured["image_size"] = image.size
        captured["lang"] = lang
        captured["slide_id"] = slide_id
        captured["slide_number"] = slide_number
        captured["layout_slide"] = layout_slide
        return {
            "raw_ocr": [
                [
                    [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
                    ["New OCR text", 0.88],
                ]
            ],
            "raw_layout": [
                {
                    "type": "title",
                    "bbox": [0.0, 0.0, 1.0, 1.0],
                    "res": [["New OCR text", 0.88]],
                }
            ],
            "lines": [
                {
                    "line_id": "line-0",
                    "text": "New OCR text",
                    "confidence": 0.88,
                    "bbox": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                }
            ],
            "blocks": [
                {
                    "block_id": "block-0",
                    "type": "title",
                    "text": "New OCR text",
                    "items": [],
                    "bbox": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                    "confidence": 0.88,
                }
            ],
            "title_text": "New OCR text",
            "bullet_texts": [],
            "figure_regions": [],
        }

    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_layout_payload",
        lambda *args, **kwargs: {
            "deck_id": deck_id,
            "lang": "eng",
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": [
                {
                    "slide_id": slide_one.id,
                    "slide_number": 1,
                    "page_number": 1,
                    "asset_path": "assets/slide-1.png",
                    "blocks": [],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                },
                {
                    "slide_id": slide_two.id,
                    "slide_number": 2,
                    "page_number": 2,
                    "asset_path": "assets/slide-2.png",
                    "blocks": [
                        {
                            "block_id": "block-0",
                            "type": "title",
                            "bbox": {"x": 0.0, "y": 0.0, "w": 8.0, "h": 8.0},
                        }
                    ],
                    "title_text": "",
                    "bullet_texts": [],
                    "figure_regions": [],
                },
            ],
        },
    )
    monkeypatch.setattr(
        "src.slides.ocr_service._build_structured_ocr_from_layout_slide",
        _fake_build_structured_ocr_from_layout_slide,
    )

    result = ensure_deck_ocr_payload(
        deck,
        deck_path,
        cached_payload=cached_payload,
        lang="eng",
        include_bboxes=True,
    )

    assert result is not None
    slides = {slide["slide_id"]: slide for slide in result["slides"]}
    assert slides[slide_one.id]["ocr_text"] == "Existing text"
    assert slides[slide_two.id]["ocr_text"] == "New OCR text"
    assert slides[slide_two.id]["raw_ocr"] is None
    assert slides[slide_two.id]["raw_layout"] is None
    assert slides[slide_one.id]["slide_number"] == 1
    assert slides[slide_two.id]["slide_number"] == 2
    assert captured["slide_id"] == slide_two.id
    assert captured["image_size"] == (8, 8)
    assert captured["layout_slide"]["slide_id"] == slide_two.id


def test_ensure_deck_ocr_payload_pdf_uses_import_raster_scale(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_llm_correction(monkeypatch)
    deck_id = "deck-ocr-pdf-scale"
    deck_path = tmp_path / deck_id
    deck_path.mkdir(parents=True)
    (deck_path / "source.pdf").write_bytes(b"%PDF-1.4\n")
    slide = Slide(
        id="slide-1.html",
        title_html="",
        body_html="",
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, slides=[slide])

    captured: dict[str, object] = {}

    class _FakePixmap:
        def __init__(self, width: int, height: int) -> None:
            self.width = width
            self.height = height
            self.samples = bytes([255]) * (width * height * 4)

    class _FakePage:
        def get_pixmap(self, *, matrix, alpha: bool) -> _FakePixmap:
            captured["matrix"] = matrix
            captured["alpha"] = alpha
            scale = int(round(float(getattr(matrix, "a", 1.0))))
            return _FakePixmap(width=10 * scale, height=6 * scale)

    class _FakeDoc:
        page_count = 1

        def __enter__(self) -> _FakeDoc:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            _ = exc_type
            _ = exc
            _ = tb
            return None

        def load_page(self, index: int) -> _FakePage:
            captured["page_index"] = index
            return _FakePage()

    def _fake_extract_structured_ocr_from_image_bytes(
        image_bytes: bytes,
        lang: str,
        *,
        slide_id: str,
        slide_number: int,
        style_hint: dict[str, object] | None = None,
        include_layout: bool = True,
        preprocess_profile: str = "none",
        allow_preprocess_fallback: bool = False,
        step_callback: object | None = None,
    ) -> dict[str, object]:
        with Image.open(io.BytesIO(image_bytes)) as rendered:
            captured["rendered_size"] = rendered.size
        captured["lang"] = lang
        captured["slide_id"] = slide_id
        captured["slide_number"] = slide_number
        captured["style_hint"] = style_hint
        captured["include_layout"] = include_layout
        captured["preprocess_profile"] = preprocess_profile
        captured["allow_preprocess_fallback"] = allow_preprocess_fallback
        return {
            "raw_ocr": [],
            "raw_layout": [],
            "lines": [],
            "blocks": [],
            "title_text": "",
            "bullet_texts": [],
            "figure_regions": [],
        }

    monkeypatch.setattr("src.slides.ocr_service._SLIDES_PDF_OCR_RASTER_SCALE", 2.0)
    monkeypatch.setattr("src.slides.ocr_service.fitz.open", lambda _path: _FakeDoc())
    monkeypatch.setattr(
        "src.slides.ocr_service.extract_structured_ocr_from_image_bytes",
        _fake_extract_structured_ocr_from_image_bytes,
    )

    result = ensure_deck_ocr_payload(deck, deck_path, lang="eng", include_bboxes=True)

    assert result is not None
    assert captured["rendered_size"] == (20, 12)
    assert captured["slide_id"] == slide.id
    assert captured["slide_number"] == 1
    assert captured["alpha"] is True
    assert captured["include_layout"] is False
    assert captured["preprocess_profile"] == "none"
    assert captured["allow_preprocess_fallback"] is False
