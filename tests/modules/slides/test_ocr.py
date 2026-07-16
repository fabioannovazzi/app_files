from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from modules.slides import ocr as slides_ocr


def _tiny_png_bytes() -> bytes:
    image = Image.new("RGB", (8, 8), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_configure_paddle_import_environment_defaults_to_project_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", raising=False)
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    monkeypatch.delenv("FLAGS_use_mkldnn", raising=False)

    slides_ocr._configure_paddle_import_environment()

    assert slides_ocr.os.environ["PADDLE_PDX_CACHE_HOME"] == str(
        slides_ocr._DEFAULT_PADDLEX_CACHE_HOME
    )
    assert slides_ocr.os.environ["MPLCONFIGDIR"] == str(
        slides_ocr._DEFAULT_MATPLOTLIB_CONFIG_HOME
    )
    assert slides_ocr.os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] == "True"
    assert slides_ocr.os.environ["FLAGS_use_mkldnn"] == "0"


def test_configure_paddle_import_environment_preserves_explicit_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    explicit_cache_home = tmp_path / "paddlex-cache"
    explicit_matplotlib_home = tmp_path / "matplotlib-cache"
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(explicit_cache_home))
    monkeypatch.setenv("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "False")
    monkeypatch.setenv("MPLCONFIGDIR", str(explicit_matplotlib_home))

    slides_ocr._configure_paddle_import_environment()

    assert slides_ocr.os.environ["PADDLE_PDX_CACHE_HOME"] == str(explicit_cache_home)
    assert slides_ocr.os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] == "False"
    assert slides_ocr.os.environ["MPLCONFIGDIR"] == str(explicit_matplotlib_home)


def test_extract_raw_ocr_from_image_bytes_uses_paddle_output_and_lang_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeEngine:
        def ocr(self, image, *, cls: bool = True):
            captured["shape"] = tuple(image.shape)
            captured["cls"] = cls
            return [
                [
                    [
                        [0.0, 0.0],
                        [10.0, 0.0],
                        [10.0, 6.0],
                        [0.0, 6.0],
                    ],
                    ("Hello world", 0.93),
                ]
            ]

    def _fake_get_paddle_ocr(lang: str, **_kwargs):
        captured["lang"] = lang
        return _FakeEngine()

    def _fail_if_layout_used(_lang: str):
        raise AssertionError("layout backend should not be used for raw OCR extraction")

    monkeypatch.setattr(slides_ocr, "_get_paddle_ocr", _fake_get_paddle_ocr)
    monkeypatch.setattr(slides_ocr, "_get_paddle_layout", _fail_if_layout_used)

    raw_ocr = slides_ocr.extract_raw_ocr_from_image_bytes(_tiny_png_bytes(), lang="eng")

    assert captured["lang"] == "en"
    assert captured["cls"] is True
    assert raw_ocr == [
        [
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 6.0],
                [0.0, 6.0],
            ],
            ["Hello world", 0.93],
        ]
    ]


def test_extract_text_from_raw_ocr_result_joins_detected_lines() -> None:
    raw_ocr = [
        [
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 6.0],
                [0.0, 6.0],
            ],
            ["Hello world", 0.93],
        ],
        [
            [
                [0.0, 8.0],
                [18.0, 8.0],
                [18.0, 14.0],
                [0.0, 14.0],
            ],
            ["Second line", 0.88],
        ],
    ]

    text = slides_ocr.extract_text_from_raw_ocr_result(raw_ocr)

    assert text == "Hello world\nSecond line"


def test_extract_lines_from_image_bytes_normalizes_percentage_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeEngine:
        def ocr(self, _image, *, cls: bool = True):
            assert cls is True
            return [
                [
                    [
                        [2.0, 3.0],
                        [8.0, 3.0],
                        [8.0, 9.0],
                        [2.0, 9.0],
                    ],
                    ("Value 42", 87.0),
                ]
            ]

    monkeypatch.setattr(
        slides_ocr, "_get_paddle_ocr", lambda _lang, **_kwargs: _FakeEngine()
    )
    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_layout",
        lambda _lang: (_ for _ in ()).throw(
            AssertionError("layout backend should not be used for line extraction")
        ),
    )

    lines = slides_ocr.extract_lines_from_image_bytes(_tiny_png_bytes(), lang="eng")

    assert len(lines) == 1
    assert lines[0]["confidence"] == 0.87


def test_extract_text_from_image_bytes_retries_with_document_preprocessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, int] = {"calls": 0}

    class _FakeEngine:
        def ocr(self, _image, *, cls: bool = True):
            assert cls is True
            captured["calls"] += 1
            if captured["calls"] == 1:
                return [
                    [
                        [
                            [1.0, 1.0],
                            [6.0, 1.0],
                            [6.0, 5.0],
                            [1.0, 5.0],
                        ],
                        ("x", 0.31),
                    ]
                ]
            return [
                [
                    [
                        [1.0, 1.0],
                        [30.0, 1.0],
                        [30.0, 8.0],
                        [1.0, 8.0],
                    ],
                    ("Invoice 12345 total 20.00", 0.94),
                ]
            ]

    monkeypatch.setattr(
        slides_ocr, "_get_paddle_ocr", lambda _lang, **_kwargs: _FakeEngine()
    )
    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_layout",
        lambda _lang: (_ for _ in ()).throw(
            AssertionError("layout backend should not be used for text extraction")
        ),
    )

    text = slides_ocr.extract_text_from_image_bytes(
        _tiny_png_bytes(),
        lang="eng",
        preprocess_profile="document_scan",
        allow_preprocess_fallback=True,
    )

    assert captured["calls"] == 2
    assert text == "Invoice 12345 total 20.00"


def test_extract_structured_ocr_from_image_bytes_returns_layout_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeEngine:
        def ocr(self, _image, *, cls: bool = True):
            assert cls is True
            return [
                [
                    [
                        [0.0, 0.0],
                        [12.0, 0.0],
                        [12.0, 6.0],
                        [0.0, 6.0],
                    ],
                    ("Main title", 0.91),
                ]
            ]

    class _FakeLayoutEngine:
        def __call__(self, _image):
            return [
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

    monkeypatch.setattr(
        slides_ocr, "_get_paddle_ocr", lambda _lang, **_kwargs: _FakeEngine()
    )
    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_layout",
        lambda _lang: _FakeLayoutEngine(),
    )

    structured = slides_ocr.extract_structured_ocr_from_image_bytes(
        _tiny_png_bytes(),
        lang="eng",
        slide_id="slide-1",
        slide_number=1,
    )

    assert structured["ocr_text"] == "Main title"
    assert structured["raw_ocr"] == [
        [
            [
                [0.0, 0.0],
                [12.0, 0.0],
                [12.0, 6.0],
                [0.0, 6.0],
            ],
            ["Main title", 0.91],
        ]
    ]
    assert structured["title_text"] == "Main title"
    assert structured["bullet_texts"] == ["First point", "Second point"]
    assert structured["figure_regions"] == [
        {"x": 120.0, "y": 30.0, "w": 240.0, "h": 190.0}
    ]
    assert structured["raw_layout"] == [
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
    assert len(structured["blocks"]) == 3


def test_extract_structured_ocr_from_image_bytes_supports_ppstructure_page_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeEngine:
        def ocr(self, _image, *, cls: bool = True):
            assert cls is True
            return [
                [
                    [
                        [0.0, 0.0],
                        [12.0, 0.0],
                        [12.0, 6.0],
                        [0.0, 6.0],
                    ],
                    ("Main title", 0.91),
                ]
            ]

    class _FakeLayoutEngine:
        def __call__(self, _image):
            return {
                "page_index": 0,
                "parsing_res_list": [
                    {
                        "block_label": "doc_title",
                        "block_content": "Main title",
                        "layout_bbox": [0.0, 0.0, 90.0, 20.0],
                        "score": 0.95,
                    },
                    {
                        "block_label": "list",
                        "block_content": ["• First point", "• Second point"],
                        "layout_bbox": [0.0, 24.0, 90.0, 60.0],
                        "score": 0.89,
                    },
                    {
                        "block_label": "chart",
                        "block_content": "",
                        "layout_bbox": [120.0, 30.0, 360.0, 220.0],
                        "score": 0.9,
                    },
                ],
                "layout_det_res": [
                    {
                        "label": "chart",
                        "coordinate": [120.0, 30.0, 360.0, 220.0],
                        "score": 0.9,
                    }
                ],
            }

    monkeypatch.setattr(
        slides_ocr, "_get_paddle_ocr", lambda _lang, **_kwargs: _FakeEngine()
    )
    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_layout",
        lambda _lang: _FakeLayoutEngine(),
    )

    structured = slides_ocr.extract_structured_ocr_from_image_bytes(
        _tiny_png_bytes(),
        lang="eng",
        slide_id="slide-1",
        slide_number=1,
    )

    assert structured["title_text"] == "Main title"
    assert structured["bullet_texts"] == ["First point", "Second point"]
    assert len(structured["blocks"]) >= 3
    assert any(block["type"] == "title" for block in structured["blocks"])
    assert any(block["type"] == "figure" for block in structured["blocks"])
    assert structured["figure_regions"]


def test_extract_structured_ocr_from_image_bytes_supports_mapping_like_layout_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeEngine:
        def ocr(self, _image, *, cls: bool = True):
            assert cls is True
            return []

    class _LayoutObject:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def items(self):
            return self._payload.items()

    class _FakeLayoutEngine:
        def __call__(self, _image):
            return _LayoutObject(
                {
                    "parsing_res_list": [
                        _LayoutObject(
                            {
                                "block_label": "doc_title",
                                "block_content": "Main title",
                                "layout_bbox": [0.0, 0.0, 90.0, 20.0],
                            }
                        ),
                        _LayoutObject(
                            {
                                "block_label": "chart",
                                "layout_bbox": [120.0, 30.0, 360.0, 220.0],
                            }
                        ),
                    ]
                }
            )

    monkeypatch.setattr(
        slides_ocr, "_get_paddle_ocr", lambda _lang, **_kwargs: _FakeEngine()
    )
    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_layout",
        lambda _lang: _FakeLayoutEngine(),
    )

    structured = slides_ocr.extract_structured_ocr_from_image_bytes(
        _tiny_png_bytes(),
        lang="eng",
        slide_id="slide-1",
        slide_number=1,
    )

    assert structured["title_text"] == "Main title"
    assert any(block["type"] == "figure" for block in structured["blocks"])
    assert structured["figure_regions"] == [
        {"x": 120.0, "y": 30.0, "w": 240.0, "h": 190.0}
    ]


def test_derive_layout_summary_uses_style_hint_for_title_selection() -> None:
    blocks = [
        {
            "type": "text",
            "text": "First body line",
            "bbox": {"x": 0.0, "y": 10.0, "w": 200.0, "h": 14.0},
            "items": [],
        },
        {
            "type": "text",
            "text": "Real visual title",
            "bbox": {"x": 0.0, "y": 2.0, "w": 200.0, "h": 28.0},
            "items": [],
        },
    ]
    title_text, _bullets, _figures = slides_ocr._derive_layout_summary(
        blocks,
        style_hint={"title_to_body_ratio": 1.8},
    )
    assert title_text == "Real visual title"


def test_derive_layout_summary_merges_split_title_blocks() -> None:
    blocks = [
        {
            "type": "title",
            "text": "Consumer preference flipped from",
            "bbox": {"x": 30.0, "y": 24.0, "w": 1000.0, "h": 60.0},
            "items": [],
        },
        {
            "type": "title",
            "text": "Natural/Dewy to Satin/Luminous finishes",
            "bbox": {"x": 34.0, "y": 90.0, "w": 980.0, "h": 60.0},
            "items": [],
        },
        {
            "type": "text",
            "text": "Body paragraph starts here",
            "bbox": {"x": 38.0, "y": 260.0, "w": 640.0, "h": 34.0},
            "items": [],
        },
    ]
    title_text, _bullets, _figures = slides_ocr._derive_layout_summary(
        blocks,
        style_hint={"title_to_body_ratio": 1.8},
    )
    assert title_text == (
        "Consumer preference flipped from\n" "Natural/Dewy to Satin/Luminous finishes"
    )


def test_get_paddle_layout_prefers_pure_layout_detector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeLayoutDetector:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    def _fail_if_ppstructure_used(**_kwargs):
        raise AssertionError("PPStructure fallback should not be used")

    slides_ocr._get_paddle_layout.cache_clear()
    monkeypatch.setattr(slides_ocr, "LayoutDetection", _FakeLayoutDetector)
    monkeypatch.setattr(slides_ocr, "PPStructure", _fail_if_ppstructure_used)

    detector = slides_ocr._get_paddle_layout("en")

    assert isinstance(detector, _FakeLayoutDetector)
    assert captured["kwargs"] == {"show_log": False, "enable_mkldnn": False}
    slides_ocr._get_paddle_layout.cache_clear()


def test_extract_layout_summary_from_raw_layout_supports_detector_output_without_text() -> (
    None
):
    raw_layout = [
        {
            "label": "doc_title",
            "coordinate": [0.0, 0.0, 90.0, 20.0],
            "score": 0.95,
        },
        {
            "label": "figure",
            "coordinate": [120.0, 30.0, 360.0, 220.0],
            "score": 0.9,
        },
    ]

    summary = slides_ocr.extract_layout_summary_from_raw_layout(
        raw_layout,
        slide_id="slide-1",
        slide_number=1,
    )

    assert summary["title_text"] == ""
    assert summary["bullet_texts"] == []
    assert summary["blocks"] == [
        {
            "id": "block-0",
            "block_id": "block-0",
            "type": "title",
            "text": "",
            "items": [],
            "bbox": {"x": 0.0, "y": 0.0, "w": 90.0, "h": 20.0},
            "confidence": 0.95,
            "slide_id": "slide-1",
            "slide_number": 1,
        },
        {
            "id": "block-1",
            "block_id": "block-1",
            "type": "figure",
            "text": "",
            "items": [],
            "bbox": {"x": 120.0, "y": 30.0, "w": 240.0, "h": 190.0},
            "confidence": 0.9,
            "slide_id": "slide-1",
            "slide_number": 1,
        },
    ]
    assert summary["figure_regions"] == [
        {"x": 120.0, "y": 30.0, "w": 240.0, "h": 190.0}
    ]


def test_get_paddle_ocr_raises_when_package_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slides_ocr._get_paddle_ocr.cache_clear()
    monkeypatch.setattr(slides_ocr, "PaddleOCR", None)
    monkeypatch.setattr(
        slides_ocr,
        "_PADDLEOCR_IMPORT_ERROR",
        ImportError("No module named 'paddleocr'"),
    )

    with pytest.raises(slides_ocr.SlideOcrEngineUnavailableError):
        slides_ocr._get_paddle_ocr("en")


def test_get_paddle_ocr_passes_explicit_text_recognition_model_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakePaddleOcr:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    slides_ocr._get_paddle_ocr.cache_clear()
    monkeypatch.setattr(slides_ocr, "PaddleOCR", _FakePaddleOcr)

    engine = slides_ocr._get_paddle_ocr(
        "it",
        text_recognition_model_name="PP-OCRv5_server_rec",
    )

    assert isinstance(engine, _FakePaddleOcr)
    assert captured["kwargs"] == {
        "lang": "it",
        "enable_mkldnn": False,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "text_recognition_model_name": "PP-OCRv5_server_rec",
    }
    slides_ocr._get_paddle_ocr.cache_clear()


def test_get_paddle_ocr_omits_text_recognition_model_name_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakePaddleOcr:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    slides_ocr._get_paddle_ocr.cache_clear()
    monkeypatch.setattr(slides_ocr, "PaddleOCR", _FakePaddleOcr)

    engine = slides_ocr._get_paddle_ocr("it")

    assert isinstance(engine, _FakePaddleOcr)
    assert captured["kwargs"] == {
        "lang": "it",
        "enable_mkldnn": False,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }
    slides_ocr._get_paddle_ocr.cache_clear()


def test_extract_structured_ocr_from_image_bytes_raises_when_layout_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeEngine:
        def ocr(self, _image, *, cls: bool = True):
            assert cls is True
            return [
                [
                    [
                        [0.0, 0.0],
                        [24.0, 0.0],
                        [24.0, 8.0],
                        [0.0, 8.0],
                    ],
                    ("Slide title", 0.92),
                ],
                [
                    [
                        [0.0, 12.0],
                        [36.0, 12.0],
                        [36.0, 20.0],
                        [0.0, 20.0],
                    ],
                    ("• Bullet one", 0.89),
                ],
            ]

    def _raise_layout(_lang: str):
        raise slides_ocr.SlideOcrEngineUnavailableError("layout backend unavailable")

    monkeypatch.setattr(
        slides_ocr, "_get_paddle_ocr", lambda _lang, **_kwargs: _FakeEngine()
    )
    monkeypatch.setattr(slides_ocr, "_get_paddle_layout", _raise_layout)

    with pytest.raises(slides_ocr.SlideOcrEngineUnavailableError):
        slides_ocr.extract_structured_ocr_from_image_bytes(
            _tiny_png_bytes(),
            lang="eng",
        )


def test_extract_lines_from_image_bytes_supports_predict_dict_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _PredictOnlyEngine:
        def predict(self, _image):
            return [
                {
                    "dt_polys": [
                        [[1.0, 1.0], [15.0, 1.0], [15.0, 7.0], [1.0, 7.0]],
                        [[2.0, 10.0], [20.0, 10.0], [20.0, 16.0], [2.0, 16.0]],
                    ],
                    "rec_texts": ["Header", "Line two"],
                    "rec_scores": [0.96, 0.87],
                }
            ]

    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_ocr",
        lambda _lang, **_kwargs: _PredictOnlyEngine(),
    )
    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_layout",
        lambda _lang: (_ for _ in ()).throw(
            AssertionError("layout backend should not be used for line extraction")
        ),
    )

    lines = slides_ocr.extract_lines_from_image_bytes(_tiny_png_bytes(), lang="eng")

    assert [line["text"] for line in lines] == ["Header", "Line two"]
    assert lines[0]["confidence"] == 0.96
    assert lines[1]["confidence"] == 0.87


def test_extract_lines_from_image_bytes_supports_predict_numpy_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _PredictOnlyEngine:
        def predict(self, _image):
            return [
                {
                    "dt_polys": np.array(
                        [
                            [[1, 1], [15, 1], [15, 7], [1, 7]],
                            [[2, 10], [20, 10], [20, 16], [2, 16]],
                        ],
                        dtype=np.int64,
                    ),
                    "rec_texts": np.array(["Header", "Line two"], dtype=object),
                    "rec_scores": np.array([0.96, 0.87], dtype=np.float32),
                }
            ]

    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_ocr",
        lambda _lang, **_kwargs: _PredictOnlyEngine(),
    )
    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_layout",
        lambda _lang: (_ for _ in ()).throw(
            AssertionError("layout backend should not be used for line extraction")
        ),
    )

    lines = slides_ocr.extract_lines_from_image_bytes(_tiny_png_bytes(), lang="eng")

    assert [line["text"] for line in lines] == ["Header", "Line two"]
    assert lines[0]["confidence"] == pytest.approx(0.96)
    assert lines[1]["confidence"] == pytest.approx(0.87)


def test_extract_structured_ocr_from_image_bytes_supports_numpy_layout_bbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeEngine:
        def ocr(self, _image, *, cls: bool = True):
            assert cls is True
            return [
                [
                    [
                        [0.0, 0.0],
                        [12.0, 0.0],
                        [12.0, 6.0],
                        [0.0, 6.0],
                    ],
                    ("Main title", 0.91),
                ]
            ]

    class _FakeLayoutEngine:
        def __call__(self, _image):
            return [
                {
                    "type": "title",
                    "bbox": np.array([0, 0, 90, 20], dtype=np.int64),
                    "res": [["Main title", 0.95]],
                },
                {
                    "type": "figure",
                    "bbox": np.array([120, 30, 360, 220], dtype=np.int64),
                    "res": [],
                },
            ]

    monkeypatch.setattr(
        slides_ocr, "_get_paddle_ocr", lambda _lang, **_kwargs: _FakeEngine()
    )
    monkeypatch.setattr(
        slides_ocr,
        "_get_paddle_layout",
        lambda _lang: _FakeLayoutEngine(),
    )

    structured = slides_ocr.extract_structured_ocr_from_image_bytes(
        _tiny_png_bytes(),
        lang="eng",
        slide_id="slide-1",
        slide_number=1,
    )

    assert structured["title_text"] == "Main title"
    assert structured["figure_regions"] == [
        {"x": 120.0, "y": 30.0, "w": 240.0, "h": 190.0}
    ]


def test_extract_structured_ocr_from_image_bytes_can_skip_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeEngine:
        def ocr(self, _image, *, cls: bool = True):
            assert cls is True
            return [
                [
                    [
                        [0.0, 0.0],
                        [12.0, 0.0],
                        [12.0, 6.0],
                        [0.0, 6.0],
                    ],
                    ("Main title", 0.91),
                ]
            ]

    def _fail_if_layout_used(_lang: str):
        raise AssertionError(
            "layout backend should not be used when include_layout=False"
        )

    monkeypatch.setattr(
        slides_ocr, "_get_paddle_ocr", lambda _lang, **_kwargs: _FakeEngine()
    )
    monkeypatch.setattr(slides_ocr, "_get_paddle_layout", _fail_if_layout_used)

    structured = slides_ocr.extract_structured_ocr_from_image_bytes(
        _tiny_png_bytes(),
        lang="eng",
        slide_id="slide-1",
        slide_number=1,
        include_layout=False,
    )

    assert structured["ocr_text"] == "Main title"
    assert structured["raw_layout"] is None
    assert structured["blocks"] == []
    assert structured["title_text"] == ""
    assert structured["bullet_texts"] == []
    assert structured["figure_regions"] == []
