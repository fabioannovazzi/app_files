"""Local, page-oriented OCR adapter shared by Vera plugin components.

The adapter never lets PaddleOCR resolve models itself. Both model directories
must come from explicit arguments, the ``VERA_OCR_*_MODEL_DIR`` environment
variables, an existing PaddleX ``official_models`` cache, or a Hugging Face
snapshot resolved here. Hugging Face lookup is local-only unless
``allow_model_download=True`` is passed by the caller.
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path

__all__ = ["OcrResult", "extract_text_from_image_bytes", "ocr_available"]

_ENGINE_NAME = "paddleocr"
_DETECTION_MODEL_NAME = "PP-OCRv5_server_det"
_DEFAULT_LANGUAGE = "it"
_DETECTION_MODEL_ENV = "VERA_OCR_DETECTION_MODEL_DIR"
_RECOGNITION_MODEL_ENV = "VERA_OCR_RECOGNITION_MODEL_DIR"
_LANGUAGE_ALIASES = {
    "deu": "de",
    "eng": "en",
    "fra": "fr",
    "fre": "fr",
    "ger": "de",
    "ita": "it",
}
_RECOGNITION_MODEL_BY_LANGUAGE = {
    "de": "latin_PP-OCRv5_mobile_rec",
    "en": "en_PP-OCRv5_mobile_rec",
    "fr": "latin_PP-OCRv5_mobile_rec",
    "it": "latin_PP-OCRv5_mobile_rec",
}
_MODEL_REVISION_BY_NAME = {
    "PP-OCRv5_server_det": "ca867c897ecbca8873081573a802ad70d499cb94",
    "en_PP-OCRv5_mobile_rec": "267c36e24c331595590fe7bd72bde2436fd286f2",
    "latin_PP-OCRv5_mobile_rec": "ab2cd5cc5fa6309be2e5acdfe66eca2c2c127d57",
}


@dataclass(frozen=True)
class OcrResult:
    """Structured outcome from one local OCR inference request."""

    text: str
    status: str
    engine: str
    language: str
    line_count: int
    warnings: tuple[str, ...]
    model_source: str
    network_used: bool
    runtime_versions: tuple[str, ...]
    model_names: tuple[str, ...]
    model_revisions: tuple[str, ...]


@dataclass(frozen=True)
class _ResolvedModel:
    path: Path | None
    source: str
    network_used: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _ResolvedModels:
    detection_path: Path | None
    recognition_path: Path | None
    source: str
    network_used: bool
    warnings: tuple[str, ...]


def ocr_available() -> bool:
    """Return whether the optional local OCR runtime packages are importable."""

    for module_name in ("numpy", "paddle", "paddleocr", "PIL"):
        try:
            if find_spec(module_name) is None:
                return False
        except (ImportError, AttributeError, ValueError):
            return False
    return True


def _normalize_language(language: str) -> tuple[str, tuple[str, ...]]:
    normalized = str(language or "").strip().lower().replace("_", "-")
    base = normalized.split("-", 1)[0]
    base = _LANGUAGE_ALIASES.get(base, base)
    if base in _RECOGNITION_MODEL_BY_LANGUAGE:
        return base, ()
    return _DEFAULT_LANGUAGE, (f"unsupported_language_fallback:{_DEFAULT_LANGUAGE}",)


def _is_model_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _snapshot_download(
    *, repo_id: str, cache_dir: Path | None, local_files_only: bool
) -> Path:
    from huggingface_hub import snapshot_download  # type: ignore

    model_name = repo_id.rsplit("/", 1)[-1]
    return Path(
        snapshot_download(
            repo_id=repo_id,
            revision=_MODEL_REVISION_BY_NAME[model_name],
            cache_dir=str(cache_dir) if cache_dir is not None else None,
            local_files_only=local_files_only,
        )
    )


def _resolve_huggingface_model(
    model_name: str,
    *,
    label: str,
    cache_dir: Path | None,
    allow_model_download: bool,
) -> _ResolvedModel:
    repo_id = f"PaddlePaddle/{model_name}"
    try:
        local_path = _snapshot_download(
            repo_id=repo_id,
            cache_dir=cache_dir,
            local_files_only=True,
        )
        if not _is_model_directory(local_path):
            raise FileNotFoundError(local_path)
        return _ResolvedModel(local_path, "huggingface_cache", False, ())
    except (ImportError, ModuleNotFoundError):
        return _ResolvedModel(
            None,
            "unavailable",
            False,
            ("model_resolver_unavailable:huggingface_hub",),
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        if not allow_model_download:
            return _ResolvedModel(
                None,
                "unavailable",
                False,
                (f"{label}_model_not_found_in_local_cache",),
            )

    try:
        downloaded_path = _snapshot_download(
            repo_id=repo_id,
            cache_dir=cache_dir,
            local_files_only=False,
        )
        if not _is_model_directory(downloaded_path):
            raise FileNotFoundError(downloaded_path)
        return _ResolvedModel(
            downloaded_path,
            "huggingface_download",
            True,
            (f"{label}_model_downloaded",),
        )
    except (ImportError, ModuleNotFoundError):
        return _ResolvedModel(
            None,
            "unavailable",
            False,
            ("model_resolver_unavailable:huggingface_hub",),
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return _ResolvedModel(
            None,
            "unavailable",
            True,
            (f"{label}_model_download_failed",),
        )


def _resolve_one_model(
    explicit_path: Path | None,
    *,
    environment_variable: str,
    model_name: str,
    label: str,
    cache_dir: Path | None,
    allow_model_download: bool,
) -> _ResolvedModel:
    source = "explicit"
    selected_path = explicit_path
    if selected_path is None:
        environment_value = os.environ.get(environment_variable, "").strip()
        if environment_value:
            selected_path = Path(environment_value).expanduser()
            source = "environment"
    if selected_path is not None:
        selected_path = Path(selected_path).expanduser()
        if _is_model_directory(selected_path):
            return _ResolvedModel(selected_path, source, False, ())
        return _ResolvedModel(
            None,
            "unavailable",
            False,
            (f"{label}_model_dir_unavailable:{source}",),
        )

    paddlex_cache_value = os.environ.get("PADDLE_PDX_CACHE_HOME", "").strip()
    paddlex_cache_home = (
        Path(paddlex_cache_value).expanduser()
        if paddlex_cache_value
        else Path.home() / ".paddlex"
    )
    paddlex_model_path = paddlex_cache_home / "official_models" / model_name
    if _is_model_directory(paddlex_model_path):
        return _ResolvedModel(paddlex_model_path, "paddlex_cache", False, ())

    return _resolve_huggingface_model(
        model_name,
        label=label,
        cache_dir=cache_dir,
        allow_model_download=allow_model_download,
    )


def _combined_model_source(detection_source: str, recognition_source: str) -> str:
    if detection_source == "unavailable" or recognition_source == "unavailable":
        return "unavailable"
    if detection_source == recognition_source:
        return detection_source
    return "mixed"


def _resolve_models(
    language: str,
    *,
    cache_dir: Path | None,
    allow_model_download: bool,
    detection_model_dir: Path | None,
    recognition_model_dir: Path | None,
) -> _ResolvedModels:
    detection = _resolve_one_model(
        detection_model_dir,
        environment_variable=_DETECTION_MODEL_ENV,
        model_name=_DETECTION_MODEL_NAME,
        label="detection",
        cache_dir=cache_dir,
        allow_model_download=allow_model_download,
    )
    if detection.path is None:
        return _ResolvedModels(
            None,
            None,
            "unavailable",
            detection.network_used,
            detection.warnings,
        )

    recognition_model_name = _RECOGNITION_MODEL_BY_LANGUAGE[language]
    recognition = _resolve_one_model(
        recognition_model_dir,
        environment_variable=_RECOGNITION_MODEL_ENV,
        model_name=recognition_model_name,
        label="recognition",
        cache_dir=cache_dir,
        allow_model_download=allow_model_download,
    )
    return _ResolvedModels(
        detection.path,
        recognition.path,
        _combined_model_source(detection.source, recognition.source),
        detection.network_used or recognition.network_used,
        detection.warnings + recognition.warnings,
    )


@lru_cache(maxsize=8)
def _get_engine(
    language: str,
    detection_model_path: str,
    recognition_model_path: str,
    recognition_model_name: str,
) -> object:
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    from paddleocr import PaddleOCR  # type: ignore

    modern_kwargs: dict[str, object] = {
        "lang": language,
        "text_detection_model_name": _DETECTION_MODEL_NAME,
        "text_detection_model_dir": detection_model_path,
        "text_recognition_model_name": recognition_model_name,
        "text_recognition_model_dir": recognition_model_path,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "enable_mkldnn": False,
    }
    try:
        return PaddleOCR(**modern_kwargs)
    except TypeError:
        legacy_kwargs: dict[str, object] = {
            "lang": language,
            "det_model_dir": detection_model_path,
            "rec_model_dir": recognition_model_path,
            "show_log": False,
            "use_angle_cls": False,
            "enable_mkldnn": False,
        }
        return PaddleOCR(**legacy_kwargs)


def _decode_image(image_bytes: bytes) -> object:
    import numpy as np  # type: ignore
    from PIL import Image  # type: ignore

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return np.asarray(image.convert("RGB"))
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Unsupported or invalid OCR image") from exc


def _clean_line(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _raw_ocr_lines(raw: object) -> list[str]:
    lines: list[str] = []

    def collect(value: object) -> None:
        if value is None:
            return
        if isinstance(value, Mapping):
            for key in ("rec_texts", "texts"):
                nested = value.get(key)
                if isinstance(nested, Sequence) and not isinstance(
                    nested, (str, bytes, bytearray)
                ):
                    for item in nested:
                        line = _clean_line(item)
                        if line:
                            lines.append(line)
                    return
            direct_text = _clean_line(value.get("text"))
            if direct_text:
                lines.append(direct_text)
                return
            for nested in value.values():
                collect(nested)
            return
        if isinstance(value, Iterator):
            for nested in value:
                collect(nested)
            return
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            if (
                len(value) >= 2
                and isinstance(value[1], Sequence)
                and not isinstance(value[1], (str, bytes, bytearray))
                and value[1]
            ):
                legacy_text = _clean_line(value[1][0])
                if legacy_text:
                    lines.append(legacy_text)
                    return
            for nested in value:
                collect(nested)

    collect(raw)
    return lines


def _run_inference(engine: object, image_array: object) -> object:
    predict = getattr(engine, "predict", None)
    if callable(predict):
        return predict(image_array)
    ocr = getattr(engine, "ocr", None)
    if callable(ocr):
        return ocr(image_array, cls=False)
    raise RuntimeError("No compatible PaddleOCR inference method is available")


@lru_cache(maxsize=1)
def _runtime_versions() -> tuple[str, ...]:
    versions: list[str] = []
    for distribution in ("paddleocr", "paddlepaddle", "paddlex"):
        try:
            installed = version(distribution)
        except PackageNotFoundError:
            installed = "unavailable"
        versions.append(f"{distribution}={installed}")
    return tuple(versions)


def _result(
    *,
    status: str,
    language: str,
    warnings: Sequence[str],
    model_source: str,
    network_used: bool,
    lines: Sequence[str] = (),
) -> OcrResult:
    model_names = (
        _DETECTION_MODEL_NAME,
        _RECOGNITION_MODEL_BY_LANGUAGE[language],
    )
    model_revisions = (
        tuple(_MODEL_REVISION_BY_NAME[name] for name in model_names)
        if model_source in {"huggingface_cache", "huggingface_download"}
        else ()
    )
    return OcrResult(
        text="\n".join(lines),
        status=status,
        engine=_ENGINE_NAME,
        language=language,
        line_count=len(lines),
        warnings=tuple(warnings),
        model_source=model_source,
        network_used=network_used,
        runtime_versions=_runtime_versions(),
        model_names=model_names,
        model_revisions=model_revisions,
    )


def extract_text_from_image_bytes(
    image_bytes: bytes,
    *,
    language: str = "it",
    cache_dir: Path | None = None,
    allow_model_download: bool = False,
    detection_model_dir: Path | None = None,
    recognition_model_dir: Path | None = None,
) -> OcrResult:
    """Extract text locally, returning a structured result instead of raising.

    Network access is possible only when ``allow_model_download`` is true and a
    required model is absent from the local Hugging Face cache.
    """

    normalized_language, language_warnings = _normalize_language(language)
    if not ocr_available():
        return _result(
            status="runtime_unavailable",
            language=normalized_language,
            warnings=language_warnings + ("runtime_dependencies_unavailable",),
            model_source="unresolved",
            network_used=False,
        )

    models = _resolve_models(
        normalized_language,
        cache_dir=Path(cache_dir).expanduser() if cache_dir is not None else None,
        allow_model_download=allow_model_download,
        detection_model_dir=detection_model_dir,
        recognition_model_dir=recognition_model_dir,
    )
    warnings = language_warnings + models.warnings
    if models.detection_path is None or models.recognition_path is None:
        return _result(
            status="models_unavailable",
            language=normalized_language,
            warnings=warnings,
            model_source=models.source,
            network_used=models.network_used,
        )

    try:
        image_array = _decode_image(image_bytes)
    except (ImportError, ModuleNotFoundError):
        return _result(
            status="runtime_unavailable",
            language=normalized_language,
            warnings=warnings + ("image_runtime_unavailable",),
            model_source=models.source,
            network_used=models.network_used,
        )
    except (OSError, TypeError, ValueError):
        return _result(
            status="inference_failed",
            language=normalized_language,
            warnings=warnings + ("invalid_image",),
            model_source=models.source,
            network_used=models.network_used,
        )

    recognition_model_name = _RECOGNITION_MODEL_BY_LANGUAGE[normalized_language]
    try:
        engine = _get_engine(
            normalized_language,
            str(models.detection_path),
            str(models.recognition_path),
            recognition_model_name,
        )
    except (ImportError, ModuleNotFoundError):
        return _result(
            status="runtime_unavailable",
            language=normalized_language,
            warnings=warnings + ("paddleocr_import_failed",),
            model_source=models.source,
            network_used=models.network_used,
        )
    except (
        AssertionError,
        AttributeError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return _result(
            status="models_unavailable",
            language=normalized_language,
            warnings=warnings + ("model_initialization_failed",),
            model_source=models.source,
            network_used=models.network_used,
        )

    try:
        lines = _raw_ocr_lines(_run_inference(engine, image_array))
    except (
        AssertionError,
        AttributeError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return _result(
            status="inference_failed",
            language=normalized_language,
            warnings=warnings + ("paddleocr_inference_failed",),
            model_source=models.source,
            network_used=models.network_used,
        )
    if not lines:
        warnings += ("no_text_detected",)
    return _result(
        status="ok",
        language=normalized_language,
        warnings=warnings,
        model_source=models.source,
        network_used=models.network_used,
        lines=lines,
    )
