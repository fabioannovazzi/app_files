from __future__ import annotations

from src.slides.ocr_payload import normalize_ocr_payload


def test_normalize_ocr_payload_derives_text_and_layout_summary_from_raw_outputs() -> (
    None
):
    raw_ocr = [
        [
            [
                [0.0, 0.0],
                [12.0, 0.0],
                [12.0, 6.0],
                [0.0, 6.0],
            ],
            ["Main title", 0.91],
        ],
        [
            [
                [0.0, 10.0],
                [20.0, 10.0],
                [20.0, 16.0],
                [0.0, 16.0],
            ],
            ["• First point", 0.89],
        ],
    ]
    raw_layout = [
        {
            "type": "title",
            "bbox": [0.0, 0.0, 90.0, 20.0],
            "res": [["Main title", 0.95]],
        },
        {
            "type": "list",
            "bbox": [0.0, 24.0, 90.0, 60.0],
            "res": [["• First point", 0.9], ["• Second point", 0.88]],
        },
        {
            "type": "figure",
            "bbox": [120.0, 30.0, 360.0, 220.0],
            "res": [],
        },
    ]
    payload = {
        "deck_id": "deck-raw",
        "lang": "eng",
        "generated_at": "2026-03-13T00:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "rawOcr": raw_ocr,
                "rawLayout": raw_layout,
            }
        ],
    }

    normalized = normalize_ocr_payload(payload, deck_id="deck-raw", lang="eng")

    slide = normalized["slides"][0]
    assert slide["raw_ocr"] is None
    assert slide["raw_layout"] is None
    assert slide["ocr_text"] == "Main title\n• First point"
    assert slide["title_text"] == "Main title"
    assert slide["bullet_texts"] == ["First point • Second point"]
    assert slide["figure_regions"] == [{"x": 120.0, "y": 30.0, "w": 240.0, "h": 190.0}]


def test_normalize_ocr_payload_preserves_empty_raw_outputs() -> None:
    payload = {
        "deck_id": "deck-empty",
        "lang": "eng",
        "generated_at": "2026-03-13T00:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "rawOcr": [],
                "rawLayout": [],
                "ocrText": "",
            }
        ],
    }

    normalized = normalize_ocr_payload(payload, deck_id="deck-empty", lang="eng")

    slide = normalized["slides"][0]
    assert slide["raw_ocr"] is None
    assert slide["raw_layout"] is None


def test_normalize_ocr_payload_compacts_wrapped_list_blocks_into_single_bullets() -> (
    None
):
    payload = {
        "deck_id": "deck-list-wrap",
        "lang": "ita",
        "generated_at": "2026-03-15T00:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": "block-0",
                        "type": "list",
                        "text": (
                            "SLA (Service Level Agreement): Accordo operativo standard.\n"
                            "Disponibilità ≥ 99,9%, risposta entro 4 ore. Applicabile\n"
                            "a tutti i servizi del catalogo."
                        ),
                        "items": [
                            "SLA (Service Level Agreement): Accordo operativo standard.",
                            "Disponibilità ≥ 99,9%, risposta entro 4 ore. Applicabile",
                            "a tutti i servizi del catalogo.",
                        ],
                    }
                ],
            }
        ],
    }

    normalized = normalize_ocr_payload(payload, deck_id="deck-list-wrap", lang="ita")

    slide = normalized["slides"][0]
    assert slide["blocks"][0]["items"] == [
        "SLA (Service Level Agreement): Accordo operativo standard. Disponibilità ≥ 99,9%, risposta entro 4 ore. Applicabile a tutti i servizi del catalogo."
    ]
    assert slide["bullet_texts"] == [
        "SLA (Service Level Agreement): Accordo operativo standard. Disponibilità ≥ 99,9%, risposta entro 4 ore. Applicabile a tutti i servizi del catalogo."
    ]


def test_normalize_ocr_payload_orders_bullets_by_bbox_and_strips_leading_markers() -> (
    None
):
    payload = {
        "deck_id": "deck-bullet-order",
        "lang": "ita",
        "generated_at": "2026-03-19T00:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "bulletTexts": [
                    "Batch: Elaborazioni pianificate",
                    "• Streaming: Elaborazioni continue",
                    "Interactive: Query esplorative",
                    "Archive: Conservazione a lungo termine",
                ],
                "blocks": [
                    {
                        "block_id": "block-0",
                        "type": "list",
                        "text": "Batch: Elaborazioni pianificate",
                        "bbox": {"x": 90.0, "y": 480.0, "w": 200.0, "h": 40.0},
                    },
                    {
                        "block_id": "block-1",
                        "type": "list",
                        "text": "• Streaming: Elaborazioni continue",
                        "bbox": {"x": 90.0, "y": 230.0, "w": 200.0, "h": 40.0},
                    },
                    {
                        "block_id": "block-2",
                        "type": "list",
                        "text": "Interactive: Query esplorative",
                        "bbox": {"x": 90.0, "y": 330.0, "w": 200.0, "h": 40.0},
                    },
                    {
                        "block_id": "block-3",
                        "type": "list",
                        "text": "Archive: Conservazione a lungo termine",
                        "bbox": {"x": 90.0, "y": 580.0, "w": 200.0, "h": 40.0},
                    },
                ],
            }
        ],
    }

    normalized = normalize_ocr_payload(payload, deck_id="deck-bullet-order", lang="ita")

    slide = normalized["slides"][0]
    assert slide["bullet_texts"] == [
        "Streaming: Elaborazioni continue",
        "Interactive: Query esplorative",
        "Batch: Elaborazioni pianificate",
        "Archive: Conservazione a lungo termine",
    ]


def test_normalize_ocr_payload_applies_deterministic_text_cleanup() -> None:
    payload = {
        "deck_id": "deck-cleanup",
        "lang": "ita",
        "generated_at": "2026-03-15T00:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "ocrText": (
                    "Titolo.Panorama\n"
                    "gliUPSx e I'ERP. Potenza a ≤ 250w e latenza fino a 25 ms"
                ),
                "lines": [
                    {"line_id": "line-0", "text": "Titolo.Panorama"},
                    {
                        "line_id": "line-1",
                        "text": (
                            "gliUPSx e I'ERP. Potenza a ≤ 250w e latenza fino a 25 ms"
                        ),
                    },
                ],
                "blocks": [
                    {
                        "block_id": "block-0",
                        "type": "title",
                        "text": "Titolo.Panorama",
                    },
                    {
                        "block_id": "block-1",
                        "type": "list",
                        "text": (
                            "gliUPSx e I'ERP. Potenza a ≤ 250w e latenza fino a 25 ms"
                        ),
                        "items": [
                            "gliUPSx e I'ERP. Potenza a ≤ 250w e latenza fino a 25 ms"
                        ],
                    },
                ],
                "titleText": "Titolo.Panorama",
                "bulletTexts": [
                    "gliUPSx e I'ERP. Potenza a ≤ 250w e latenza fino a 25 ms"
                ],
            }
        ],
    }

    normalized = normalize_ocr_payload(payload, deck_id="deck-cleanup", lang="ita")

    slide = normalized["slides"][0]
    assert slide["ocr_text"] == (
        "Titolo. Panorama\ngli UPSX e l'ERP. Potenza ≤ 250W e latenza fino a 25 ms"
    )
    assert slide["lines"][0]["text"] == "Titolo. Panorama"
    assert slide["lines"][1]["text"] == (
        "gli UPSX e l'ERP. Potenza ≤ 250W e latenza fino a 25 ms"
    )
    assert slide["blocks"][0]["text"] == "Titolo. Panorama"
    assert slide["blocks"][1]["text"] == (
        "gli UPSX e l'ERP. Potenza ≤ 250W e latenza fino a 25 ms"
    )
    assert slide["blocks"][1]["items"] == [
        "gli UPSX e l'ERP. Potenza ≤ 250W e latenza fino a 25 ms"
    ]
    assert slide["title_text"] == "Titolo. Panorama"
    assert slide["bullet_texts"] == [
        "gli UPSX e l'ERP. Potenza ≤ 250W e latenza fino a 25 ms"
    ]


def test_normalize_ocr_payload_preserves_residual_audit_metadata() -> None:
    payload = {
        "deck_id": "deck-audit",
        "lang": "ita",
        "generated_at": "2026-03-16T00:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": "block-0",
                        "type": "text",
                        "text": "Testo corretto.",
                        "auditStatus": "suspicious",
                        "auditReason": "Residual OCR issue remains.",
                        "auditSuggestedText": "Testo corretto meglio.",
                    }
                ],
            }
        ],
    }

    normalized = normalize_ocr_payload(payload, deck_id="deck-audit", lang="ita")

    block = normalized["slides"][0]["blocks"][0]
    assert block["audit_status"] == "suspicious"
    assert block["audit_reason"] == "Residual OCR issue remains."
    assert block["audit_suggested_text"] == "Testo corretto meglio."


def test_normalize_ocr_payload_preserves_visual_review_metadata() -> None:
    payload = {
        "deck_id": "deck-visual-audit",
        "lang": "ita",
        "generated_at": "2026-03-17T00:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": "block-0",
                        "type": "text",
                        "text": "Nota finate di supporto.",
                        "visualStatus": "uncertain",
                        "visualReason": "The crop is too soft to confirm the last word.",
                        "visualSuggestedText": "Nota finale di supporto.",
                        "visualConfidence": 0.42,
                    }
                ],
            }
        ],
    }

    normalized = normalize_ocr_payload(payload, deck_id="deck-visual-audit", lang="ita")

    block = normalized["slides"][0]["blocks"][0]
    assert block["visual_status"] == "uncertain"
    assert block["visual_reason"] == "The crop is too soft to confirm the last word."
    assert block["visual_suggested_text"] == "Nota finale di supporto."
    assert block["visual_confidence"] == 0.42


def test_normalize_ocr_payload_preserves_table_model_metadata() -> None:
    payload = {
        "deck_id": "deck-table-model",
        "lang": "eng",
        "generated_at": "2026-03-18T00:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": "block-0",
                        "type": "table",
                        "text": "Country Revenue",
                        "tableModel": {
                            "source": "deterministic_simple",
                            "confidence": 0.84,
                            "rowCount": 3,
                            "columnCount": 2,
                            "headerRows": 1,
                            "columnWidths": [0.6, 0.4],
                            "rows": [
                                {
                                    "cells": [
                                        {
                                            "text": "Country",
                                            "rowSpan": 1,
                                            "colSpan": 1,
                                            "isHeader": True,
                                            "align": "center",
                                        },
                                        {
                                            "text": "Revenue",
                                            "rowSpan": 1,
                                            "colSpan": 1,
                                            "isHeader": True,
                                            "align": "center",
                                        },
                                    ]
                                },
                                {
                                    "cells": [
                                        {
                                            "text": "Italy",
                                            "rowSpan": 1,
                                            "colSpan": 1,
                                            "isHeader": False,
                                            "align": "left",
                                        },
                                        {
                                            "text": "25",
                                            "rowSpan": 1,
                                            "colSpan": 1,
                                            "isHeader": False,
                                            "align": "right",
                                        },
                                    ]
                                },
                            ],
                        },
                    }
                ],
            }
        ],
    }

    normalized = normalize_ocr_payload(payload, deck_id="deck-table-model", lang="eng")

    block = normalized["slides"][0]["blocks"][0]
    assert block["table_model"] is not None
    assert block["table_model"]["column_count"] == 2
    assert block["table_model"]["row_count"] == 3
    assert block["table_model"]["header_rows"] == 1
    assert block["table_model"]["rows"][0]["cells"][0]["text"] == "Country"
