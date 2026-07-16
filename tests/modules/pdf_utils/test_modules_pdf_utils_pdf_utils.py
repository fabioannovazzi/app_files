import sys
import types
from io import BytesIO

import pytest
from PIL import Image


def _make_dummy_image(size=(16, 16), color=(255, 255, 255)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_ocr_page_uses_paddle_helper(monkeypatch):
    import modules.pdf_utils.pdf_utils as pdf_utils

    captured = {}

    def fake_extract(img, lang="eng"):
        captured["image"] = img
        captured["lang"] = lang
        return "Hello World"

    monkeypatch.setattr(pdf_utils, "_extract_paddle_ocr_text", fake_extract)

    img = _make_dummy_image()
    out = pdf_utils.ocr_page(img, lang="eng")

    assert out == "Hello World"
    assert captured["image"] is img
    assert captured["lang"] == "eng"


def test_extract_pdf_rich_formatting_and_normalization(monkeypatch):
    import modules.pdf_utils.pdf_utils as pdf_utils

    # Avoid link injection requiring PyMuPDF
    monkeypatch.setattr(pdf_utils, "_merge_links", lambda _b, lines: lines)

    class _DummyPage:
        def extract_words(self, **_kwargs):
            # Two visual lines distinguished by "top" (y)
            line1 = [
                {"text": "Heading", "x0": 10, "top": 10, "size": 10, "fontname": "Regular"},
                {"text": "Line", "x0": 50, "top": 10, "size": 15, "fontname": "Regular"},
            ]
            # Bold line with HTML entity, NBSP and superscript digit
            filler = [
                {"text": "loremipsumdolor", "x0": 10 + i * 8, "top": 30, "size": 12, "fontname": "Bold"}
                for i in range(12)
            ]
            line2 = [
                {"text": "AT&amp;T\u00a0Corp", "x0": 10, "top": 30, "size": 12, "fontname": "Bold"},
                {"text": "a¹b", "x0": 40, "top": 30, "size": 12, "fontname": "Bold"},
            ] + filler
            return line1 + line2

    class _DummyPDF:
        def __init__(self):
            self.pages = [_DummyPage()]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pdf_utils.pdfplumber, "open", lambda _io: _DummyPDF())

    # Act
    out = pdf_utils.extract_pdf_rich(BytesIO(b"%PDF-1.4 dummy"))

    # Assert: first non-empty line is a level-2 heading, second is bold
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) >= 2
    assert lines[0].startswith("## ")
    assert lines[1].startswith("**") and lines[1].endswith("**")
    assert "AT&T Corp" in lines[1]  # html entity + NBSP normalized
    assert "a [1] b" in lines[1]    # superscript digit mapped
    # Ensure we didn't trigger pdfminer fallback (content should be long enough)
    assert len(out) >= 100


def test_extract_pdf_rich_fallback_uses_pdfminer_when_text_short(monkeypatch):
    import modules.pdf_utils.pdf_utils as pdf_utils

    # Avoid link injection requiring PyMuPDF
    monkeypatch.setattr(pdf_utils, "_merge_links", lambda _b, lines: lines)

    class _SmallPage:
        def extract_words(self, **_kwargs):
            # Very short content to trigger fallback
            return [{"text": "Hi", "x0": 0, "top": 0, "size": 10, "fontname": "Regular"}]

    class _DummyPDF:
        def __init__(self):
            self.pages = [_SmallPage()]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pdf_utils.pdfplumber, "open", lambda _io: _DummyPDF())

    # Inject a stub pdfminer.high_level.extract_text
    hl = types.ModuleType("pdfminer.high_level")
    hl.extract_text = lambda *_a, **_k: "FROM_PDFMINER"
    pkg = types.ModuleType("pdfminer")
    pkg.high_level = hl
    monkeypatch.setitem(sys.modules, "pdfminer", pkg)
    monkeypatch.setitem(sys.modules, "pdfminer.high_level", hl)

    # Act
    out = pdf_utils.extract_pdf_rich(BytesIO(b"%PDF-1.4 short"))

    # Assert: fallback text is returned
    assert out == "FROM_PDFMINER"


def test_extract_pdf_text_with_ocr_once_uses_paddle_fallback(monkeypatch):
    import modules.pdf_utils.pdf_utils as pdf_utils

    class _EmptyPage:
        def extract_text(self):
            return ""

    class _PlumberDoc:
        pages = [_EmptyPage()]

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    class _FitzPage:
        @staticmethod
        def get_text():
            return ""

    class _FitzDoc(list):
        def close(self):
            return None

    monkeypatch.setattr(pdf_utils.pdfplumber, "open", lambda _io: _PlumberDoc())
    monkeypatch.setattr(
        pdf_utils.fitz,
        "open",
        lambda **_kwargs: _FitzDoc([_FitzPage()]),
        raising=False,
    )
    monkeypatch.setattr(
        pdf_utils,
        "_render_pdf_pages_with_fitz",
        lambda *_args, **_kwargs: [_make_dummy_image()],
    )
    monkeypatch.setattr(
        pdf_utils,
        "convert_from_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("pdf2image fallback should not be used")
        ),
    )
    monkeypatch.setattr(pdf_utils, "ocr_page", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(
        pdf_utils,
        "_extract_paddle_ocr_text",
        lambda *_args, **_kwargs: "fattura numero 93658",
    )

    result = pdf_utils._extract_pdf_text_with_ocr_once(
        b"%PDF-1.4",
        llm_wrapper=object(),
        lang="ita",
    )

    assert result.method == "paddle_ocr"
    assert "fattura numero 93658" in result.text
    attempts = [(a.method, a.success) for a in result.attempts]
    assert ("fitz_raster", True) in attempts
    assert ("paddle_ocr", True) in attempts
    assert all(method != "llm_ocr" for method, _success in attempts)


def test_extract_pdf_text_with_ocr_once_retries_with_pdf2image_when_fitz_ocr_empty(
    monkeypatch,
):
    import modules.pdf_utils.pdf_utils as pdf_utils

    class _EmptyPage:
        def extract_text(self):
            return ""

    class _PlumberDoc:
        pages = [_EmptyPage()]

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    class _FitzPage:
        @staticmethod
        def get_text():
            return ""

    class _FitzDoc(list):
        def close(self):
            return None

    fitz_img = _make_dummy_image(size=(16, 16))
    pdf2image_img = _make_dummy_image(size=(32, 32))

    monkeypatch.setattr(pdf_utils.pdfplumber, "open", lambda _io: _PlumberDoc())
    monkeypatch.setattr(
        pdf_utils.fitz,
        "open",
        lambda **_kwargs: _FitzDoc([_FitzPage()]),
        raising=False,
    )
    monkeypatch.setattr(
        pdf_utils,
        "_render_pdf_pages_with_fitz",
        lambda *_args, **_kwargs: [fitz_img],
    )
    monkeypatch.setattr(
        pdf_utils,
        "convert_from_bytes",
        lambda *_args, **_kwargs: [pdf2image_img],
    )
    monkeypatch.setattr(
        pdf_utils,
        "_extract_paddle_ocr_text",
        lambda img, **_kwargs: "" if img.size == (16, 16) else "fattura 93658",
    )

    result = pdf_utils._extract_pdf_text_with_ocr_once(b"%PDF-1.4", lang="ita")

    assert result.method == "paddle_ocr"
    assert "fattura 93658" in result.text
    attempts = [(a.method, a.success) for a in result.attempts]
    assert ("fitz_raster", True) in attempts
    assert ("pdf2image_raster", True) in attempts
    assert ("paddle_ocr", True) in attempts


def test_extract_pdf_text_with_ocr_once_sets_error_when_all_ocr_empty(monkeypatch):
    import modules.pdf_utils.pdf_utils as pdf_utils

    class _EmptyPage:
        def extract_text(self):
            return ""

    class _PlumberDoc:
        pages = [_EmptyPage()]

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    class _FitzPage:
        @staticmethod
        def get_text():
            return ""

    class _FitzDoc(list):
        def close(self):
            return None

    monkeypatch.setattr(pdf_utils.pdfplumber, "open", lambda _io: _PlumberDoc())
    monkeypatch.setattr(
        pdf_utils.fitz,
        "open",
        lambda **_kwargs: _FitzDoc([_FitzPage()]),
        raising=False,
    )
    monkeypatch.setattr(
        pdf_utils,
        "_render_pdf_pages_with_fitz",
        lambda *_args, **_kwargs: [_make_dummy_image()],
    )
    monkeypatch.setattr(pdf_utils, "ocr_page", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(
        pdf_utils,
        "_extract_paddle_ocr_text",
        lambda *_args, **_kwargs: "",
    )

    result = pdf_utils._extract_pdf_text_with_ocr_once(b"%PDF-1.4", lang="ita")

    assert result.method == "error"
    assert result.text == ""
    assert result.step_failed == "paddle_ocr"
