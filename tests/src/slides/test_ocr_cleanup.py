from __future__ import annotations

from src.slides.ocr_cleanup import clean_ocr_text


def test_clean_ocr_text_applies_safe_symbol_and_token_normalizations() -> None:
    raw_text = "EPAc I'UE Potenza a ≤ 250w bikeinoa500W 25km/h"

    cleaned = clean_ocr_text(raw_text)

    assert cleaned == "EPAC l'UE Potenza ≤ 250W bikeinoa 500W 25 km/h"
