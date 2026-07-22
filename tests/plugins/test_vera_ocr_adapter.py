from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = (
    ROOT / "plugins" / "_shared" / "vendor" / "modules" / "vera_ocr" / "__init__.py"
)


def _load_adapter() -> ModuleType:
    module_name = "vera_ocr_adapter_under_test"
    spec = importlib.util.spec_from_file_location(module_name, ADAPTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def adapter() -> ModuleType:
    return _load_adapter()


def _model_directories(tmp_path: Path) -> tuple[Path, Path]:
    detection = tmp_path / "detection"
    recognition = tmp_path / "recognition"
    detection.mkdir()
    recognition.mkdir()
    return detection, recognition


@pytest.mark.parametrize(
    "language", ("es", "es-ES", "spa", "esp", "español", "spanish")
)
def test_spanish_language_uses_the_latin_recognition_model(
    adapter: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    language: str,
) -> None:
    detection, recognition = _model_directories(tmp_path)
    engine_calls: list[tuple[str, str, str, str]] = []

    class FakeEngine:
        def predict(self, _image: object) -> list[dict[str, object]]:
            return [{"rec_texts": ["texto en español"]}]

    def fake_engine(
        normalized_language: str,
        detection_path: str,
        recognition_path: str,
        recognition_model_name: str,
    ) -> FakeEngine:
        engine_calls.append(
            (
                normalized_language,
                detection_path,
                recognition_path,
                recognition_model_name,
            )
        )
        return FakeEngine()

    monkeypatch.setattr(adapter, "ocr_available", lambda: True)
    monkeypatch.setattr(adapter, "_decode_image", lambda _value: object())
    monkeypatch.setattr(adapter, "_get_engine", fake_engine)

    result = adapter.extract_text_from_image_bytes(
        b"image",
        language=language,
        detection_model_dir=detection,
        recognition_model_dir=recognition,
    )

    assert result.status == "ok"
    assert result.language == "es"
    assert result.model_names == (
        "PP-OCRv5_server_det",
        "latin_PP-OCRv5_mobile_rec",
    )
    assert engine_calls == [
        (
            "es",
            str(detection),
            str(recognition),
            "latin_PP-OCRv5_mobile_rec",
        )
    ]


def test_vera_vendors_only_shared_ocr_module() -> None:
    config_path = ROOT / "scripts" / "plugin_vendor_modules.json"

    payload = json.loads(config_path.read_text(encoding="utf-8"))

    assert payload["plugins"]["vera"]["module_roots"] == ["vera_ocr"]


def test_extract_text_runtime_missing_returns_structured_status(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adapter, "ocr_available", lambda: False)

    result = adapter.extract_text_from_image_bytes(b"image")

    assert result.status == "runtime_unavailable"
    assert result.engine == "paddleocr"
    assert result.network_used is False
    assert result.warnings == ("runtime_dependencies_unavailable",)


def test_extract_text_normalizes_paddleocr_v3_result(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    detection, recognition = _model_directories(tmp_path)

    class FakeEngine:
        def predict(self, _image: object) -> list[dict[str, object]]:
            return [{"res": {"rec_texts": [" Riga uno ", "Riga due"]}}]

    monkeypatch.setattr(adapter, "ocr_available", lambda: True)
    monkeypatch.setattr(adapter, "_decode_image", lambda _value: object())
    monkeypatch.setattr(adapter, "_get_engine", lambda *_args: FakeEngine())
    monkeypatch.setattr(
        adapter,
        "_snapshot_download",
        lambda **_kwargs: pytest.fail("explicit model paths must skip cache lookup"),
    )

    result = adapter.extract_text_from_image_bytes(
        b"image",
        detection_model_dir=detection,
        recognition_model_dir=recognition,
    )

    assert result.status == "ok"
    assert result.text == "Riga uno\nRiga due"
    assert result.line_count == 2
    assert result.model_source == "explicit"
    assert result.network_used is False
    assert result.model_names == (
        "PP-OCRv5_server_det",
        "latin_PP-OCRv5_mobile_rec",
    )
    assert result.model_revisions == ()
    assert any(item.startswith("paddleocr=") for item in result.runtime_versions)


def test_extract_text_normalizes_paddleocr_v2_result(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    detection, recognition = _model_directories(tmp_path)

    class FakeLegacyEngine:
        def ocr(self, _image: object, *, cls: bool) -> list[list[object]]:
            assert cls is False
            return [
                [
                    ([[0, 0], [1, 0], [1, 1], [0, 1]], ("Prima", 0.99)),
                    ([[0, 2], [1, 2], [1, 3], [0, 3]], ("Seconda", 0.98)),
                ]
            ]

    monkeypatch.setattr(adapter, "ocr_available", lambda: True)
    monkeypatch.setattr(adapter, "_decode_image", lambda _value: object())
    monkeypatch.setattr(adapter, "_get_engine", lambda *_args: FakeLegacyEngine())

    result = adapter.extract_text_from_image_bytes(
        b"image",
        detection_model_dir=detection,
        recognition_model_dir=recognition,
    )

    assert result.status == "ok"
    assert result.text == "Prima\nSeconda"
    assert result.line_count == 2


def test_extract_text_never_uses_remote_lookup_without_opt_in(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_only_calls: list[bool] = []

    def missing_snapshot(
        *, repo_id: str, cache_dir: Path | None, local_files_only: bool
    ) -> Path:
        assert repo_id == "PaddlePaddle/PP-OCRv5_server_det"
        assert cache_dir == tmp_path
        local_only_calls.append(local_files_only)
        raise FileNotFoundError(repo_id)

    monkeypatch.setattr(adapter, "ocr_available", lambda: True)
    monkeypatch.setattr(adapter, "_snapshot_download", missing_snapshot)
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(tmp_path / "empty-paddlex-cache"))

    result = adapter.extract_text_from_image_bytes(b"image", cache_dir=tmp_path)

    assert result.status == "models_unavailable"
    assert result.network_used is False
    assert local_only_calls == [True]
    assert result.warnings == ("detection_model_not_found_in_local_cache",)


def test_extract_text_reuses_paddlex_cache_without_huggingface_lookup(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paddlex_cache = tmp_path / "paddlex"
    official_models = paddlex_cache / "official_models"
    (official_models / "PP-OCRv5_server_det").mkdir(parents=True)
    (official_models / "latin_PP-OCRv5_mobile_rec").mkdir()

    class FakeEngine:
        def predict(self, _image: object) -> list[dict[str, object]]:
            return [{"rec_texts": ["testo locale"]}]

    monkeypatch.delenv("VERA_OCR_DETECTION_MODEL_DIR", raising=False)
    monkeypatch.delenv("VERA_OCR_RECOGNITION_MODEL_DIR", raising=False)
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(paddlex_cache))
    monkeypatch.setattr(adapter, "ocr_available", lambda: True)
    monkeypatch.setattr(adapter, "_decode_image", lambda _value: object())
    monkeypatch.setattr(adapter, "_get_engine", lambda *_args: FakeEngine())
    monkeypatch.setattr(
        adapter,
        "_snapshot_download",
        lambda **_kwargs: pytest.fail("PaddleX cache hit must skip Hugging Face"),
    )

    result = adapter.extract_text_from_image_bytes(b"image")

    assert result.status == "ok"
    assert result.text == "testo locale"
    assert result.model_source == "paddlex_cache"
    assert result.network_used is False


def test_extract_text_downloads_only_after_local_cache_miss_and_opt_in(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, bool]] = []

    def snapshot(
        *, repo_id: str, cache_dir: Path | None, local_files_only: bool
    ) -> Path:
        assert cache_dir == tmp_path
        calls.append((repo_id, local_files_only))
        if local_files_only:
            raise FileNotFoundError(repo_id)
        model_path = tmp_path / repo_id.rsplit("/", 1)[-1]
        model_path.mkdir(exist_ok=True)
        return model_path

    class FakeEngine:
        def predict(self, _image: object) -> list[dict[str, object]]:
            return [{"rec_texts": ["testo"]}]

    monkeypatch.setattr(adapter, "ocr_available", lambda: True)
    monkeypatch.setattr(adapter, "_snapshot_download", snapshot)
    monkeypatch.setattr(adapter, "_decode_image", lambda _value: object())
    monkeypatch.setattr(adapter, "_get_engine", lambda *_args: FakeEngine())
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(tmp_path / "empty-paddlex-cache"))

    result = adapter.extract_text_from_image_bytes(
        b"image",
        cache_dir=tmp_path,
        allow_model_download=True,
    )

    assert result.status == "ok"
    assert result.text == "testo"
    assert result.model_source == "huggingface_download"
    assert result.network_used is True
    assert result.model_revisions == (
        "ca867c897ecbca8873081573a802ad70d499cb94",
        "ab2cd5cc5fa6309be2e5acdfe66eca2c2c127d57",
    )
    assert calls == [
        ("PaddlePaddle/PP-OCRv5_server_det", True),
        ("PaddlePaddle/PP-OCRv5_server_det", False),
        ("PaddlePaddle/latin_PP-OCRv5_mobile_rec", True),
        ("PaddlePaddle/latin_PP-OCRv5_mobile_rec", False),
    ]
