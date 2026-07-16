from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import shutil
import struct
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates

from modules.auth.dependencies import require_site_permission_for_request
from modules.auth.session import AuthenticatedUser
from modules.pdp.language import get_navigation_label, get_page_copy, resolve_language
from modules.projects.permissions import (
    PresentationDocumentInfo,
    PresentationListingItem,
    build_presentation_listing,
    get_brand_report_permissions,
    get_concept_permissions,
    get_launch_report_permissions,
    get_presentation_permissions,
    is_presentation_allowed,
)
from modules.utilities.cache import get_cache_dir
from src.slides import launch_pdf_validator as launch_report_validator

__all__ = ["router", "site_router"]

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/presentations", tags=["presentations"])
site_router = APIRouter()

LOGGER = logging.getLogger(__name__)

_DEFAULT_PRESENTATIONS_PDF_ROOT = Path("presentations")
_DEFAULT_LAUNCH_REPORTS_PDF_ROOT = Path("launch_reports")
_DEFAULT_BRAND_REPORTS_PDF_ROOT = Path("brand_reports")
_DEFAULT_LAUNCH_REPORTS_DOCUMENT_ROOT = Path("launch_report_documents")
_DEFAULT_LAUNCH_REPORTS_PODCAST_ROOT = Path("launch_report_podcasts")
_DEFAULT_LAUNCH_REPORTS_VIDEO_ROOT = Path("launch_report_videos")
_DEFAULT_BRAND_REPORTS_DOCUMENT_ROOT = Path("brand_report_documents")
_DEFAULT_BRAND_REPORTS_PODCAST_ROOT = Path("brand_report_podcasts")
_AI_ACCURACY_DISCLAIMER = "AI can be inaccurate; please double-check its responses."
_CONCEPT_SITE_IMAGE_OVERLAY_TEXT = (
    "Signal-informed hypothesis artifact \u00b7 non-operational"
)
_DEFAULT_CONCEPT_SITES_ROOT = Path("concept_sites")
_CONCEPT_SITE_IMAGE_SUFFIXES = frozenset(
    {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
)
_ENV_PDF_RENDER_SCALE = "PRESENTATIONS_PDF_RENDER_SCALE"
_DEFAULT_PDF_RENDER_SCALE = 4.0
_SUPPORTED_AUDIO_SUFFIXES = (".m4a", ".mp3", ".wav")
_SUPPORTED_VIDEO_SUFFIXES = (".mp4", ".m4v", ".mov", ".webm")
_AUDIO_MEDIA_TYPES = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}
_VIDEO_MEDIA_TYPES = {
    ".m4v": "video/x-m4v",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
_MEDIA_STREAM_CHUNK_SIZE = 1024 * 1024
_HTTP_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_LAUNCH_REPORT_LIST_GROUPS = (
    (
        "lips_ulta",
        (
            "lip_balm_ulta",
            "lip_gloss_ulta",
            "lip_liner_ulta",
            "lip_oil_ulta",
            "lip_plumping_ulta",
            "lip_stain_ulta",
            "lip_treatment_ulta",
            "lipstick_ulta",
        ),
    ),
    (
        "face_ulta",
        (
            "blush_ulta",
            "bronzer_ulta",
            "color_correct_ulta",
            "concealer_ulta",
            "contour_ulta",
            "cream_ulta",
            "face_primer_ulta",
            "foundation_ulta",
            "highlighter_ulta",
            "setting_spray_and_powder_ulta",
            "tinted_moisturizer_ulta",
        ),
    ),
    (
        "permanent",
        (
            "permanent_cosmoprof",
            "permanent_saloncentric",
        ),
    ),
)
_LAUNCH_REPORT_CHILD_IDS = frozenset(
    child_doc_id
    for _parent_doc_id, child_doc_ids in _LAUNCH_REPORT_LIST_GROUPS
    for child_doc_id in child_doc_ids
)
_LAUNCH_REPORT_VALIDATION_ARTIFACT_SUFFIX = ".validation.json"
_LAUNCH_REPORT_READING_CACHE_DIRNAME = ".launch_report_reading_cache"
_LAUNCH_REPORT_LOW_OCR_CONFIDENCE = 0.6
_LAUNCH_REPORT_VALIDATION_LABEL_KEYS = {
    "checked": "validation_status_checked",
    "noted": "validation_status_noted",
    "caution": "validation_status_caution",
    "unknown": "validation_status_unknown",
    "summary": "validation_status_summary",
    "pending": "validation_status_pending",
}
_LAUNCH_REPORT_VALIDATION_SHORT_LABEL_KEYS = {
    "unknown": "validation_status_unknown_short",
}
_LAUNCH_REPORT_VALIDATION_MIN_RESOLVED_RATIO = 0.8
_LAUNCH_REPORT_LAYER_STATE_LABELS = {
    "sure": "Sure",
    "not_sure": "Not sure",
    "failed": "Failed",
    "unknown": "Unresolved",
    "reading_issue": "Reading issue",
    "non_claim": "Non-claim",
}
_LAUNCH_REPORT_LAYER_STATE_DESCRIPTIONS = {
    "sure": "Matched deterministic package evidence.",
    "not_sure": (
        "Partially supported by the package, or supported with a weak/incomplete "
        "deterministic match."
    ),
    "failed": (
        "Deterministic package evidence disagrees with the report text. "
        "This may require report or source-package review."
    ),
    "unknown": (
        "No deterministic checker resolved this text unit, or the mapped text "
        "does not carry enough context for a deterministic decision."
    ),
    "reading_issue": "OCR/layout mapping made this text unit unreliable.",
    "non_claim": "Classified as report structure, label text, or other non-claim text.",
}
_LAUNCH_REPORT_LAYER_STATE_RANKS = {
    "failed": 6,
    "not_sure": 5,
    "unknown": 4,
    "sure": 3,
    "reading_issue": 2,
    "non_claim": 1,
}
_LAUNCH_REPORT_VALIDATION_RESULT_STATES = {
    "verified": "sure",
    "matched": "sure",
    "pass": "sure",
    "contradicted": "failed",
    "failed": "failed",
    "fail": "failed",
    "partially_backed": "not_sure",
    "weakly_backed": "not_sure",
    "warning": "not_sure",
    "unresolved": "unknown",
    "unknown": "unknown",
    "non_claim": "non_claim",
    "not_claim": "non_claim",
    "ocr_layout_mapping_issue": "reading_issue",
    "mapping_issue": "reading_issue",
    "reading_issue": "reading_issue",
}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class PdfDocument:
    doc_id: str
    title: str
    path: Path


class LaunchReportViewerVariant(str, Enum):
    REPORT = "report"
    DOCUMENT = "document"


@dataclass(frozen=True, slots=True)
class LaunchReportCompanionAssets:
    document: PdfDocument | None
    podcast: Path | None
    video: Path | None


@dataclass(frozen=True, slots=True)
class ConceptSiteDocument:
    doc_id: str
    title: str
    root: Path


def _pdf_root() -> Path:
    root = _DEFAULT_PRESENTATIONS_PDF_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _launch_reports_pdf_root() -> Path:
    root = _DEFAULT_LAUNCH_REPORTS_PDF_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _brand_reports_pdf_root() -> Path:
    root = _DEFAULT_BRAND_REPORTS_PDF_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _launch_report_documents_root() -> Path:
    root = _DEFAULT_LAUNCH_REPORTS_DOCUMENT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _launch_report_podcasts_root() -> Path:
    root = _DEFAULT_LAUNCH_REPORTS_PODCAST_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _launch_report_videos_root() -> Path:
    root = _DEFAULT_LAUNCH_REPORTS_VIDEO_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _brand_report_documents_root() -> Path:
    root = _DEFAULT_BRAND_REPORTS_DOCUMENT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _brand_report_podcasts_root() -> Path:
    root = _DEFAULT_BRAND_REPORTS_PODCAST_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _concept_sites_root() -> Path:
    root = _DEFAULT_CONCEPT_SITES_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass(frozen=True, slots=True)
class PdfLibrary:
    page_path: str
    viewer_base_path: str
    page_copy_key: str
    cache_namespace: str
    pdf_root_resolver: Callable[[], Path]
    permissions_loader: Callable[[], dict[str, set[str]]]


def _render_scale() -> float:
    raw = os.environ.get(_ENV_PDF_RENDER_SCALE)
    if not raw:
        return _DEFAULT_PDF_RENDER_SCALE
    try:
        scale = float(raw)
    except ValueError:
        LOGGER.warning(
            "Invalid %s=%r; falling back to %s.",
            _ENV_PDF_RENDER_SCALE,
            raw,
            _DEFAULT_PDF_RENDER_SCALE,
        )
        return _DEFAULT_PDF_RENDER_SCALE
    if scale <= 0:
        LOGGER.warning(
            "%s must be > 0; falling back to %s.",
            _ENV_PDF_RENDER_SCALE,
            _DEFAULT_PDF_RENDER_SCALE,
        )
        return _DEFAULT_PDF_RENDER_SCALE
    return scale


_DOC_ID_ALLOWED = re.compile(r"[^a-zA-Z0-9_-]+")


def _slugify(value: str) -> str:
    slug = _DOC_ID_ALLOWED.sub("_", value).strip("_").lower()
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        raise ValueError("Document id is empty after sanitization.")
    return slug


def _derive_title(path: Path) -> str:
    label = path.stem.replace("_", " ").replace("-", " ").strip()
    label = re.sub(r"\s+", " ", label)
    return label or path.stem


def _list_pdf_documents(root: Path) -> list[PdfDocument]:
    documents: list[PdfDocument] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*.pdf")):
        if not path.is_file():
            continue
        try:
            doc_id = _slugify(path.stem)
        except ValueError:
            continue
        if doc_id in seen:
            LOGGER.warning(
                "Duplicate PDF document id %s for %s; skipping.", doc_id, path
            )
            continue
        seen.add(doc_id)
        documents.append(
            PdfDocument(doc_id=doc_id, title=_derive_title(path), path=path)
        )
    return documents


def _list_concept_documents(root: Path) -> list[ConceptSiteDocument]:
    documents: list[ConceptSiteDocument] = []
    seen: set[str] = set()
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        index_path = path / "index.html"
        if not index_path.is_file():
            continue
        try:
            doc_id = _slugify(path.name)
        except ValueError:
            continue
        if doc_id in seen:
            LOGGER.warning(
                "Duplicate concept document id %s for %s; skipping.", doc_id, path
            )
            continue
        seen.add(doc_id)
        documents.append(
            ConceptSiteDocument(
                doc_id=doc_id,
                title=_derive_title(path),
                root=path,
            )
        )
    return documents


def _resolve_pdf_document(doc_id: str, root: Path) -> PdfDocument:
    doc_id = _slugify(doc_id)
    for document in _list_pdf_documents(root):
        if document.doc_id == doc_id:
            return document
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
    )


def _resolve_concept_document(doc_id: str, root: Path) -> ConceptSiteDocument:
    normalized_doc_id = _slugify(doc_id)
    for document in _list_concept_documents(root):
        if document.doc_id == normalized_doc_id:
            return document
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Document not found.",
    )


def _resolve_optional_pdf_document(doc_id: str, root: Path) -> PdfDocument | None:
    doc_id = _slugify(doc_id)
    for document in _list_pdf_documents(root):
        if document.doc_id == doc_id:
            return document
    return None


def _resolve_optional_audio_asset(doc_id: str, root: Path) -> Path | None:
    return _resolve_optional_media_asset(
        doc_id,
        root,
        supported_suffixes=_SUPPORTED_AUDIO_SUFFIXES,
    )


def _resolve_optional_video_asset(doc_id: str, root: Path) -> Path | None:
    return _resolve_optional_media_asset(
        doc_id,
        root,
        supported_suffixes=_SUPPORTED_VIDEO_SUFFIXES,
    )


def _resolve_optional_media_asset(
    doc_id: str,
    root: Path,
    *,
    supported_suffixes: tuple[str, ...],
) -> Path | None:
    normalized_doc_id = _slugify(doc_id)
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in supported_suffixes:
            continue
        try:
            candidate_doc_id = _slugify(path.stem)
        except ValueError:
            continue
        if candidate_doc_id == normalized_doc_id:
            return path
    return None


def _cache_dir_for(cache_namespace: str, doc_id: str) -> Path:
    return get_cache_dir(cache_namespace, "pdf_pages", doc_id)


def _meta_path(cache_dir: Path) -> Path:
    return cache_dir / "meta.json"


def _ensure_cache_fresh(
    pdf_path: Path, cache_dir: Path, *, scale: float
) -> dict[str, object]:
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - dependency is expected in production
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF rendering is not available on this deployment.",
        ) from exc

    pdf_path = pdf_path.resolve()
    stat = pdf_path.stat()
    with fitz.open(pdf_path) as doc:
        page_count = int(doc.page_count)

    expected = {
        "source": str(pdf_path),
        "mtime_ns": int(stat.st_mtime_ns),
        "size": int(stat.st_size),
        "page_count": page_count,
        "scale": float(scale),
    }

    meta_path = _meta_path(cache_dir)
    try:
        current = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        current = None

    if isinstance(current, dict) and all(
        current.get(key) == expected[key] for key in expected
    ):
        return expected

    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return expected


def _render_pdf_page(
    pdf_path: Path, *, page_number: int, scale: float, output_path: Path
) -> None:
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - dependency is expected in production
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF rendering is not available on this deployment.",
        ) from exc

    with fitz.open(pdf_path) as doc:
        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        png_bytes = pix.tobytes("png")

    tmp_path = output_path.with_suffix(".tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_bytes(png_bytes)
    tmp_path.replace(output_path)


def _presentations_library() -> PdfLibrary:
    return PdfLibrary(
        page_path="/presentations/page",
        viewer_base_path="/presentations/pdf",
        page_copy_key="presentations",
        cache_namespace="presentations",
        pdf_root_resolver=_pdf_root,
        permissions_loader=get_presentation_permissions,
    )


def _launch_reports_library() -> PdfLibrary:
    return PdfLibrary(
        page_path="/review/reports/page",
        viewer_base_path="/review/reports/pdf",
        page_copy_key="launch_reports",
        cache_namespace="launch_reports",
        pdf_root_resolver=_launch_reports_pdf_root,
        permissions_loader=get_launch_report_permissions,
    )


def _brand_reports_library() -> PdfLibrary:
    return PdfLibrary(
        page_path="/review/brand-reports/page",
        viewer_base_path="/review/brand-reports/pdf",
        page_copy_key="brand_reports",
        cache_namespace="brand_reports",
        pdf_root_resolver=_brand_reports_pdf_root,
        permissions_loader=get_brand_report_permissions,
    )


def _launch_report_listing_sort_key(document: PdfDocument) -> tuple[int, int, str]:
    for group_index, (parent_doc_id, child_doc_ids) in enumerate(
        _LAUNCH_REPORT_LIST_GROUPS
    ):
        if document.doc_id == parent_doc_id:
            return (group_index, 0, document.title.casefold())
        if document.doc_id in child_doc_ids:
            return (
                group_index,
                child_doc_ids.index(document.doc_id) + 1,
                document.title.casefold(),
            )
    return (len(_LAUNCH_REPORT_LIST_GROUPS), 0, document.title.casefold())


def _sort_library_documents(
    documents: list[PdfDocument],
    *,
    library: PdfLibrary,
) -> list[PdfDocument]:
    if library.page_path == "/review/reports/page":
        return sorted(documents, key=_launch_report_listing_sort_key)
    return documents


def _launch_report_validation_doc_id(path: Path) -> str | None:
    if not path.name.endswith(_LAUNCH_REPORT_VALIDATION_ARTIFACT_SUFFIX):
        return None
    raw_stem = path.name[: -len(_LAUNCH_REPORT_VALIDATION_ARTIFACT_SUFFIX)]
    if raw_stem == "batch":
        return None
    try:
        return _slugify(raw_stem)
    except ValueError:
        return None


def _launch_report_validation_state(payload: object) -> str:
    if not isinstance(payload, dict):
        return "pending"

    resolver = payload.get("resolver")
    resolver_status = resolver.get("status") if isinstance(resolver, dict) else None
    if resolver_status == "unresolved":
        return "pending"

    summary = payload.get("summary")
    if isinstance(summary, dict):
        unresolved_count = _value_as_int(summary.get("unresolved_count")) or 0
        claim_count = _value_as_int(summary.get("claim_count")) or 0
        non_claim_count = _value_as_int(summary.get("non_claim_count")) or 0
        mapping_issue_count = _value_as_int(summary.get("mapping_issue_count")) or 0
        resolved_count = claim_count + non_claim_count + mapping_issue_count
        total_classified_count = unresolved_count + resolved_count
        resolved_ratio = (
            resolved_count / total_classified_count if total_classified_count else 1.0
        )
        if resolved_ratio < _LAUNCH_REPORT_VALIDATION_MIN_RESOLVED_RATIO:
            return "unknown"

    status_value = payload.get("status")
    if status_value == "pass":
        return "checked"
    if status_value == "pass_with_warnings":
        return "noted"
    if status_value == "fail":
        return "caution"
    if (
        status_value == "not_validated"
        and payload.get("report_type") == "summary_report"
    ):
        return "summary"

    if resolver_status not in (None, "matched", "heuristic_match", "summary_report"):
        return "pending"
    return "pending"


def _load_launch_report_validation_states(pdf_root: Path) -> dict[str, dict[str, str]]:
    validation_root = pdf_root / "validation"
    if not validation_root.is_dir():
        return {}

    states: dict[str, dict[str, str]] = {}
    for path in sorted(
        validation_root.glob(f"*{_LAUNCH_REPORT_VALIDATION_ARTIFACT_SUFFIX}")
    ):
        doc_id = _launch_report_validation_doc_id(path)
        if doc_id is None:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            LOGGER.warning(
                "Could not read launch report validation artifact %s: %s", path, exc
            )
            continue
        except json.JSONDecodeError as exc:
            LOGGER.warning(
                "Invalid launch report validation artifact %s: %s", path, exc
            )
            continue
        state = _launch_report_validation_state(payload)
        states[doc_id] = _launch_report_validation_badge(state, payload)
    return states


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        LOGGER.warning("Could not read JSON artifact %s: %s", path, exc)
        return None
    except json.JSONDecodeError as exc:
        LOGGER.warning("Invalid JSON artifact %s: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        LOGGER.warning("Expected JSON object in %s.", path)
        return None
    return payload


def _launch_report_reading_cache_doc_id(doc_id: str) -> str:
    return _slugify(doc_id)


def _launch_report_reading_cache_path(pdf_root: Path, doc_id: str) -> Path:
    return (
        pdf_root
        / _LAUNCH_REPORT_READING_CACHE_DIRNAME
        / _launch_report_reading_cache_doc_id(doc_id)
        / "slide_analysis.json"
    )


def _launch_report_validation_path(
    pdf_root: Path, document: PdfDocument
) -> Path | None:
    validation_root = pdf_root / "validation"
    if not validation_root.is_dir():
        return None

    exact_path = (
        validation_root
        / f"{document.doc_id}{_LAUNCH_REPORT_VALIDATION_ARTIFACT_SUFFIX}"
    )
    if exact_path.is_file():
        return exact_path

    for path in sorted(
        validation_root.glob(f"*{_LAUNCH_REPORT_VALIDATION_ARTIFACT_SUFFIX}")
    ):
        if _launch_report_validation_doc_id(path) == document.doc_id:
            return path
    return None


def _value_as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _value_as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _slide_page_number(slide: dict[str, Any], fallback: int) -> int:
    for key in ("pageNumber", "page_number", "slideNumber", "slide_number"):
        page_number = _value_as_int(slide.get(key))
        if page_number is not None:
            return page_number
    return fallback


def _block_id(block: dict[str, Any], fallback: int) -> str:
    for key in ("blockId", "block_id", "id"):
        value = block.get(key)
        if isinstance(value, str) and value:
            return value
    return f"block-{fallback}"


def _block_text(block: dict[str, Any]) -> str:
    text = block.get("text")
    if isinstance(text, str):
        return text.strip()
    items = block.get("items")
    if isinstance(items, list):
        return "\n".join(item.strip() for item in items if isinstance(item, str))
    return ""


def _block_bbox(block: dict[str, Any]) -> dict[str, float] | None:
    raw_bbox = block.get("bbox")
    if not isinstance(raw_bbox, dict):
        return None

    x = _value_as_float(raw_bbox.get("x"))
    y = _value_as_float(raw_bbox.get("y"))
    width = _value_as_float(raw_bbox.get("w", raw_bbox.get("width")))
    height = _value_as_float(raw_bbox.get("h", raw_bbox.get("height")))
    if x is None or y is None or width is None or height is None:
        return None
    if width <= 0 or height <= 0:
        return None
    return {"x": x, "y": y, "w": width, "h": height}


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as file_obj:
            header = file_obj.read(24)
    except OSError as exc:
        LOGGER.warning("Could not read PNG dimensions for %s: %s", path, exc)
        return None
    if len(header) < 24 or not header.startswith(_PNG_SIGNATURE):
        return None
    if header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return int(width), int(height)


def _slide_asset_dimensions(
    reading_path: Path, slide: dict[str, Any]
) -> dict[str, int] | None:
    asset_path_value = slide.get("assetPath", slide.get("asset_path"))
    if not isinstance(asset_path_value, str) or not asset_path_value:
        return None
    asset_path = Path(asset_path_value)
    if not asset_path.is_absolute():
        asset_path = reading_path.parent / asset_path
    if asset_path.suffix.lower() != ".png" or not asset_path.is_file():
        return None
    dimensions = _png_dimensions(asset_path)
    if dimensions is None:
        return None
    return {"width": dimensions[0], "height": dimensions[1]}


def _validation_result_page_number(result: dict[str, Any]) -> int | None:
    for key in ("page_number", "pageNumber", "slide_number", "slideNumber"):
        page_number = _value_as_int(result.get(key))
        if page_number is not None:
            return page_number
    return None


def _validation_result_block_id(result: dict[str, Any]) -> str | None:
    for key in ("block_id", "blockId"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _validation_result_state(result: dict[str, Any]) -> str:
    status_value = result.get("status")
    status_key = status_value.strip().lower() if isinstance(status_value, str) else ""
    return _LAUNCH_REPORT_VALIDATION_RESULT_STATES.get(status_key, "unknown")


def _best_validation_layer_state(states: list[str]) -> str:
    if not states:
        return "unknown"
    return max(
        states,
        key=lambda state: _LAUNCH_REPORT_LAYER_STATE_RANKS.get(state, 0),
    )


def _validation_result_reason(result: dict[str, Any]) -> str:
    details = result.get("details")
    if isinstance(details, dict):
        message = details.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        reasons = details.get("reasons")
        if isinstance(reasons, list):
            for reason in reasons:
                if isinstance(reason, str) and reason.strip():
                    return reason.strip()

    state = _validation_result_state(result)
    if state == "sure":
        return "Deterministic checker verified this claim."
    if state == "failed":
        return "Deterministic checker found a mismatch."
    if state == "not_sure":
        return "Deterministic checker found only partial or weak support."
    if state == "non_claim":
        return "This text is classified as non-claim text."
    if state == "reading_issue":
        return "This text is classified as an OCR/layout mapping issue."
    return "No deterministic checker resolved this text."


def _compact_tooltip_text(value: object, *, max_length: int = 240) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _tooltip_value(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return _compact_tooltip_text(value, max_length=180)
    return ""


def _append_tooltip_detail(
    lines: list[str],
    *,
    label: str,
    value: object,
) -> None:
    formatted = _tooltip_value(value)
    if formatted:
        lines.append(f"{label}: {formatted}")


def _dedupe_tooltip_lines(lines: list[str], *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        text = line.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def _validation_result_tooltip_lines(result: dict[str, Any]) -> list[str]:
    state = _validation_result_state(result)
    lines: list[str] = []

    reason = _validation_result_reason(result)
    if reason:
        lines.append(_compact_tooltip_text(reason))

    details = result.get("details")
    if isinstance(details, dict):
        for key, label in (
            ("filter_reason", "Why"),
            ("comparison_outcome", "Outcome"),
            ("observed", "Observed"),
            ("expected", "Expected"),
            ("mapping_issue_type", "Mapping issue"),
        ):
            _append_tooltip_detail(lines, label=label, value=details.get(key))

        reasons = details.get("reasons")
        if isinstance(reasons, list):
            for extra_reason in reasons[:2]:
                formatted = _compact_tooltip_text(extra_reason)
                if formatted:
                    lines.append(formatted)

    for key, label in (
        ("observed", "Observed"),
        ("expected", "Expected"),
    ):
        _append_tooltip_detail(lines, label=label, value=result.get(key))

    if not lines:
        lines.append(_LAUNCH_REPORT_LAYER_STATE_DESCRIPTIONS.get(state, ""))

    return _dedupe_tooltip_lines(lines)


def _validation_item_tooltip(
    *,
    state: str,
    text: str,
    source_kind: object,
    reasons: list[str],
    results: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    for result in results[:2]:
        result_lines = _validation_result_tooltip_lines(result)
        lines.extend(result_lines)

    if not results:
        for reason in reasons[:4]:
            formatted = _compact_tooltip_text(reason)
            if formatted:
                lines.append(formatted)

    if not lines:
        lines.append(_LAUNCH_REPORT_LAYER_STATE_DESCRIPTIONS.get(state, ""))

    return "\n".join(_dedupe_tooltip_lines(lines, limit=5))


def _validation_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": result.get("status", ""),
        "state": _validation_result_state(result),
        "claim_family": result.get("claim_family", ""),
        "claim_text": result.get("claim_text", ""),
        "source_kind": result.get("source_kind", ""),
        "reason": _validation_result_reason(result),
        "tooltip": "\n".join(_validation_result_tooltip_lines(result)),
    }
    for key in ("entity", "file", "observed", "expected", "denominator", "tolerance"):
        if key in result:
            summary[key] = result[key]
    details = result.get("details")
    if isinstance(details, dict):
        summary["details"] = details
    return summary


def _validation_results_by_block(
    validation_payload: dict[str, Any] | None,
) -> dict[tuple[int, str], list[dict[str, Any]]]:
    if validation_payload is None:
        return {}

    by_block: dict[tuple[int, str], list[dict[str, Any]]] = {}
    result_groups = (
        validation_payload.get("claims"),
        validation_payload.get("unresolved"),
        validation_payload.get("non_claims"),
        validation_payload.get("mapping_issues"),
    )
    for results in result_groups:
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            page_number = _validation_result_page_number(result)
            block_id = _validation_result_block_id(result)
            if page_number is None or block_id is None:
                continue
            by_block.setdefault((page_number, block_id), []).append(result)
    return by_block


def _validation_results_by_claim_text(
    validation_payload: dict[str, Any] | None,
) -> dict[tuple[int, str], list[dict[str, Any]]]:
    if validation_payload is None:
        return {}

    by_claim_text: dict[tuple[int, str], list[dict[str, Any]]] = {}
    result_groups = (
        validation_payload.get("claims"),
        validation_payload.get("unresolved"),
        validation_payload.get("non_claims"),
        validation_payload.get("mapping_issues"),
    )
    for results in result_groups:
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            page_number = _validation_result_page_number(result)
            claim_text = result.get("claim_text")
            if page_number is None or not isinstance(claim_text, str) or not claim_text:
                continue
            by_claim_text.setdefault((page_number, claim_text.strip()), []).append(
                result
            )
    return by_claim_text


def _union_bboxes(boxes: list[dict[str, float]]) -> dict[str, float] | None:
    if not boxes:
        return None
    min_x = min(box["x"] for box in boxes)
    min_y = min(box["y"] for box in boxes)
    max_x = max(box["x"] + box["w"] for box in boxes)
    max_y = max(box["y"] + box["h"] for box in boxes)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0 or height <= 0:
        return None
    return {"x": min_x, "y": min_y, "w": width, "h": height}


def _reconstructed_validation_layer_items(
    *,
    slide: dict[str, Any],
    page_number: int,
    bbox_source: dict[str, int] | None,
    validation_results_by_claim_text: dict[tuple[int, str], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], set[str], dict[str, int]]:
    blocks = slide.get("blocks")
    if not isinstance(blocks, list):
        return [], set(), {state: 0 for state in _LAUNCH_REPORT_LAYER_STATE_LABELS}

    raw_blocks = [block for block in blocks if isinstance(block, dict)]
    raw_block_by_id = {
        _block_id(block, index): block
        for index, block in enumerate(raw_blocks)
        if _block_id(block, index)
    }
    canonical_slide = launch_report_validator._canonicalize_analysis_slide(slide)
    units = launch_report_validator._iter_slide_units(canonical_slide)

    items: list[dict[str, Any]] = []
    suppressed_block_ids: set[str] = set()
    reconstructed_group_ids: set[str] = set()
    summary = {state: 0 for state in _LAUNCH_REPORT_LAYER_STATE_LABELS}

    for index, unit in enumerate(units):
        if not unit.get("reconstructed_from_group_table_titles"):
            continue
        block_id = unit.get("block_id")
        if isinstance(block_id, str) and block_id:
            reconstructed_group_ids.add(block_id)
        source_block_ids = [
            block_id
            for block_id in unit.get("source_block_ids", [])
            if isinstance(block_id, str) and block_id
        ]
        if not source_block_ids:
            continue
        component_boxes = [
            _block_bbox(raw_block_by_id[block_id])
            for block_id in source_block_ids
            if raw_block_by_id.get(block_id) is not None
        ]
        component_boxes = [box for box in component_boxes if box is not None]
        bbox = _union_bboxes(component_boxes)
        if bbox is None:
            continue

        claim_text = _block_text({"text": unit.get("text", "")})
        matching_results = validation_results_by_claim_text.get(
            (page_number, claim_text),
            [],
        )
        result_states = [
            _validation_result_state(result) for result in matching_results
        ]
        state = (
            _best_validation_layer_state(result_states) if result_states else "unknown"
        )
        reasons = [_validation_result_reason(result) for result in matching_results]
        if not matching_results:
            reasons.append(
                "No deterministic validation result is attached to this reconstructed table row."
            )
        source_kind = unit.get("source_kind", "")

        suppressed_block_ids.update(source_block_ids)
        summary[state] += 1
        items.append(
            {
                "id": f"{page_number}:reconstructed:{index}",
                "slide_number": page_number,
                "block_id": unit.get("block_id", ""),
                "block_type": unit.get("block_type", ""),
                "detected_type": unit.get("block_type", ""),
                "source_kind": source_kind,
                "state": state,
                "state_label": _LAUNCH_REPORT_LAYER_STATE_LABELS[state],
                "text": claim_text,
                "bbox": bbox,
                "bbox_source": bbox_source,
                "confidence": None,
                "audit_status": "",
                "visual_status": "",
                "reasons": reasons,
                "results": [
                    _validation_result_summary(result) for result in matching_results
                ],
                "tooltip": _validation_item_tooltip(
                    state=state,
                    text=claim_text,
                    source_kind=source_kind,
                    reasons=reasons,
                    results=matching_results,
                ),
                "source_block_ids": source_block_ids,
            }
        )

    for block_id, block in raw_block_by_id.items():
        group_id = block.get("groupId", block.get("group_id"))
        block_type = block.get("type")
        if (
            isinstance(group_id, str)
            and group_id in reconstructed_group_ids
            and block_type == "table_title"
        ):
            suppressed_block_ids.add(block_id)

    return items, suppressed_block_ids, summary


def _table_model_validation_layer_items(
    *,
    blocks: list[dict[str, Any]],
    page_number: int,
    bbox_source: dict[str, int] | None,
    validation_results_by_claim_text: dict[tuple[int, str], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], set[str], dict[str, int]]:
    items: list[dict[str, Any]] = []
    suppressed_block_ids: set[str] = set()
    summary = {state: 0 for state in _LAUNCH_REPORT_LAYER_STATE_LABELS}

    for block_index, block in enumerate(blocks):
        table_model = block.get("tableModel", block.get("table_model"))
        if not isinstance(table_model, dict):
            continue
        block_bbox = _block_bbox(block)
        if block_bbox is None:
            continue
        row_texts = launch_report_validator._table_row_texts(table_model)
        if not row_texts:
            continue

        row_count = _value_as_int(
            table_model.get("row_count", table_model.get("rowCount"))
        )
        raw_rows = table_model.get("rows")
        raw_row_count = len(raw_rows) if isinstance(raw_rows, list) else 0
        header_rows = (
            _value_as_int(table_model.get("header_rows", table_model.get("headerRows")))
            or 0
        )
        total_rows = max(row_count or 0, raw_row_count, header_rows + len(row_texts))
        if total_rows <= 0:
            continue

        row_height = block_bbox["h"] / float(total_rows)
        block_id = _block_id(block, block_index)
        suppressed_block_ids.add(block_id)

        for row_offset, row_text in enumerate(row_texts):
            row_number = min(header_rows + row_offset, total_rows - 1)
            row_bbox = {
                "x": block_bbox["x"],
                "y": block_bbox["y"] + (row_height * row_number),
                "w": block_bbox["w"],
                "h": row_height,
            }
            matching_results = validation_results_by_claim_text.get(
                (page_number, row_text),
                [],
            )
            result_states = [
                _validation_result_state(result) for result in matching_results
            ]
            state = (
                _best_validation_layer_state(result_states)
                if result_states
                else "unknown"
            )
            reasons = [_validation_result_reason(result) for result in matching_results]
            if not matching_results:
                reasons.append(
                    "No deterministic validation result is attached to this table row."
                )
            source_kind = (
                matching_results[0].get("source_kind", "")
                if matching_results
                else "table_row"
            )

            summary[state] += 1
            items.append(
                {
                    "id": f"{page_number}:{block_id}:table-row:{row_offset}",
                    "slide_number": page_number,
                    "block_id": block_id,
                    "block_type": block.get("type", ""),
                    "detected_type": block.get("detectedType", ""),
                    "source_kind": source_kind,
                    "state": state,
                    "state_label": _LAUNCH_REPORT_LAYER_STATE_LABELS[state],
                    "text": row_text,
                    "bbox": row_bbox,
                    "bbox_source": bbox_source,
                    "confidence": block.get("confidence"),
                    "audit_status": block.get("auditStatus", ""),
                    "visual_status": block.get("visualStatus", ""),
                    "reasons": reasons,
                    "results": [
                        _validation_result_summary(result)
                        for result in matching_results
                    ],
                    "tooltip": _validation_item_tooltip(
                        state=state,
                        text=row_text,
                        source_kind=source_kind,
                        reasons=reasons,
                        results=matching_results,
                    ),
                    "row_index": row_offset,
                }
            )

    return items, suppressed_block_ids, summary


def _empty_validation_layer_summary() -> dict[str, int]:
    return {state: 0 for state in _LAUNCH_REPORT_LAYER_STATE_LABELS}


def _add_validation_layer_summary_counts(
    target: dict[str, int], source: dict[str, int]
) -> None:
    for state, count in source.items():
        if state in target:
            target[state] += count


def _launch_report_validation_layer_slide_items(
    *,
    slide: dict[str, Any],
    page_number: int,
    reading_path: Path,
    validation_payload: dict[str, Any] | None,
    results_by_block: dict[tuple[int, str], list[dict[str, Any]]],
    results_by_claim_text: dict[tuple[int, str], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    bbox_source = _slide_asset_dimensions(reading_path, slide)
    summary = _empty_validation_layer_summary()
    items: list[dict[str, Any]] = []

    reconstructed_items, suppressed_block_ids, reconstructed_summary = (
        _reconstructed_validation_layer_items(
            slide=slide,
            page_number=page_number,
            bbox_source=bbox_source,
            validation_results_by_claim_text=results_by_claim_text,
        )
    )
    items.extend(reconstructed_items)
    _add_validation_layer_summary_counts(summary, reconstructed_summary)

    blocks = slide.get("blocks")
    raw_blocks = (
        [block for block in blocks if isinstance(block, dict)]
        if isinstance(blocks, list)
        else []
    )
    table_items, table_suppressed_block_ids, table_summary = (
        _table_model_validation_layer_items(
            blocks=raw_blocks,
            page_number=page_number,
            bbox_source=bbox_source,
            validation_results_by_claim_text=results_by_claim_text,
        )
    )
    items.extend(table_items)
    suppressed_block_ids.update(table_suppressed_block_ids)
    _add_validation_layer_summary_counts(summary, table_summary)

    if not isinstance(blocks, list):
        return items, summary

    ordered_blocks = sorted(
        (block for block in blocks if isinstance(block, dict)),
        key=lambda block: _value_as_int(block.get("readingOrder")) or 0,
    )
    for block_index, block in enumerate(ordered_blocks):
        text = _block_text(block)
        bbox = _block_bbox(block)
        if bbox is None or not text:
            continue

        block_id = _block_id(block, block_index)
        if block_id in suppressed_block_ids:
            continue
        block_results = results_by_block.get((page_number, block_id), [])
        result_states = [_validation_result_state(result) for result in block_results]
        reading_reasons = _block_reading_reasons(block)
        if result_states:
            state = _best_validation_layer_state(result_states)
        elif reading_reasons:
            state = "reading_issue"
        elif validation_payload is None:
            state = "unknown"
        else:
            state = "unknown"

        reasons = [_validation_result_reason(result) for result in block_results]
        if not block_results:
            reasons.append(
                "No deterministic validation result is attached to this text unit."
            )
        reasons.extend(reading_reasons)
        source_kind = (
            block_results[0].get("source_kind", "")
            if block_results
            else block.get("type", "")
        )

        summary[state] += 1
        items.append(
            {
                "id": f"{page_number}:{block_id}",
                "slide_number": page_number,
                "block_id": block_id,
                "block_type": block.get("type", ""),
                "detected_type": block.get("detectedType", ""),
                "source_kind": source_kind,
                "state": state,
                "state_label": _LAUNCH_REPORT_LAYER_STATE_LABELS[state],
                "text": text,
                "bbox": bbox,
                "bbox_source": bbox_source,
                "confidence": block.get("confidence"),
                "audit_status": block.get("auditStatus", ""),
                "visual_status": block.get("visualStatus", ""),
                "reasons": reasons,
                "results": [
                    _validation_result_summary(result) for result in block_results
                ],
                "tooltip": _validation_item_tooltip(
                    state=state,
                    text=text,
                    source_kind=source_kind,
                    reasons=reasons,
                    results=block_results,
                ),
            }
        )

    return items, summary


def _block_reading_reasons(block: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    audit_status = block.get("auditStatus", block.get("audit_status"))
    visual_status = block.get("visualStatus", block.get("visual_status"))
    has_visual_review = isinstance(visual_status, str) and bool(visual_status.strip())
    if isinstance(visual_status, str) and visual_status not in {
        "ok",
        "corrected",
        "confirmed",
    }:
        visual_reason = block.get("visualReason", block.get("visual_reason"))
        if isinstance(visual_reason, str) and visual_reason.strip():
            reasons.append(visual_reason.strip())
        else:
            reasons.append(f"Visual correction status is {visual_status}.")

    if (
        not has_visual_review
        and isinstance(audit_status, str)
        and audit_status not in {"ok", "corrected"}
    ):
        audit_reason = block.get("auditReason", block.get("audit_reason"))
        if isinstance(audit_reason, str) and audit_reason.strip():
            reasons.append(audit_reason.strip())
        else:
            reasons.append(f"OCR audit status is {audit_status}.")

    return reasons


def _build_launch_report_validation_layer_payload(
    document: PdfDocument,
    *,
    page: int,
    pdf_root: Path,
) -> dict[str, Any]:
    reading_path = _launch_report_reading_cache_path(pdf_root, document.doc_id)
    reading_payload = (
        _load_json_object(reading_path) if reading_path.is_file() else None
    )
    if reading_payload is None:
        empty_summary = _empty_validation_layer_summary()
        return {
            "doc_id": document.doc_id,
            "page": page,
            "available": False,
            "validation_available": False,
            "reason": "Mapped slide analysis is not available.",
            "items": [],
            "summary": empty_summary,
            "document_summary": empty_summary,
            "page_summary": empty_summary,
            "state_labels": _LAUNCH_REPORT_LAYER_STATE_LABELS,
            "state_descriptions": _LAUNCH_REPORT_LAYER_STATE_DESCRIPTIONS,
        }

    validation_path = _launch_report_validation_path(pdf_root, document)
    validation_payload = (
        _load_json_object(validation_path)
        if validation_path is not None and validation_path.is_file()
        else None
    )
    results_by_block = _validation_results_by_block(validation_payload)
    results_by_claim_text = _validation_results_by_claim_text(validation_payload)

    slides = reading_payload.get("slides")
    if not isinstance(slides, list):
        slides = []

    document_summary = _empty_validation_layer_summary()
    page_summary = _empty_validation_layer_summary()
    items: list[dict[str, Any]] = []
    page_has_slides = False
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            continue
        page_number = _slide_page_number(slide, index)
        slide_items, slide_summary = _launch_report_validation_layer_slide_items(
            slide=slide,
            page_number=page_number,
            reading_path=reading_path,
            validation_payload=validation_payload,
            results_by_block=results_by_block,
            results_by_claim_text=results_by_claim_text,
        )
        _add_validation_layer_summary_counts(document_summary, slide_summary)
        if page_number == page:
            page_has_slides = True
            items.extend(slide_items)
            _add_validation_layer_summary_counts(page_summary, slide_summary)

    reading_quality = (
        validation_payload.get("reading_quality")
        if isinstance(validation_payload, dict)
        else None
    )
    return {
        "doc_id": document.doc_id,
        "page": page,
        "available": True,
        "validation_available": validation_payload is not None,
        "reason": "" if page_has_slides else "No mapped text units for this page.",
        "items": items,
        "summary": document_summary,
        "document_summary": document_summary,
        "page_summary": page_summary,
        "state_labels": _LAUNCH_REPORT_LAYER_STATE_LABELS,
        "state_descriptions": _LAUNCH_REPORT_LAYER_STATE_DESCRIPTIONS,
        "reading_quality": reading_quality if isinstance(reading_quality, dict) else {},
    }


def _launch_report_summary_count(summary: object, key: str) -> int:
    if not isinstance(summary, dict):
        return 0
    value = _value_as_int(summary.get(key))
    return value if value is not None else 0


def _launch_report_validation_counts_line(summary: object) -> str:
    if not isinstance(summary, dict):
        return ""

    verified_count = _launch_report_summary_count(summary, "verified_count")
    contradicted_count = _launch_report_summary_count(summary, "contradicted_count")
    partial_count = _launch_report_summary_count(
        summary,
        "partially_backed_count",
    ) + _launch_report_summary_count(summary, "weakly_backed_count")
    claim_count = _launch_report_summary_count(summary, "claim_count")
    if claim_count <= 0:
        claim_count = verified_count + contradicted_count + partial_count
    unresolved_count = _launch_report_summary_count(summary, "unresolved_count")
    non_claim_count = _launch_report_summary_count(summary, "non_claim_count")
    mapping_issue_count = _launch_report_summary_count(summary, "mapping_issue_count")
    image_region_count = _launch_report_summary_count(summary, "image_region_count")
    parts = [
        f"Sure {verified_count}",
        f"not sure {partial_count}",
        f"failed {contradicted_count}",
        f"unknown {unresolved_count}",
    ]
    if non_claim_count:
        parts.append(f"non-claim {non_claim_count}")
    if mapping_issue_count:
        parts.append(f"reading issue {mapping_issue_count}")
    if image_region_count:
        parts.append(f"image region {image_region_count}")
    return f"Document totals: {', '.join(parts)}."


def _launch_report_validation_resolved_line(summary: object) -> str:
    if not isinstance(summary, dict):
        return ""
    claim_count = _launch_report_summary_count(summary, "claim_count")
    if claim_count <= 0:
        claim_count = (
            _launch_report_summary_count(summary, "verified_count")
            + _launch_report_summary_count(summary, "contradicted_count")
            + _launch_report_summary_count(summary, "partially_backed_count")
            + _launch_report_summary_count(summary, "weakly_backed_count")
        )
    non_claim_count = _launch_report_summary_count(summary, "non_claim_count")
    mapping_issue_count = _launch_report_summary_count(summary, "mapping_issue_count")
    unresolved_count = _launch_report_summary_count(summary, "unresolved_count")
    resolved_count = claim_count + non_claim_count + mapping_issue_count
    total_count = resolved_count + unresolved_count
    if total_count <= 0:
        return ""
    resolved_ratio = resolved_count / total_count
    return (
        f"Resolved {resolved_count}/{total_count} text units "
        f"({resolved_ratio:.0%}); unknown threshold is "
        f"{_LAUNCH_REPORT_VALIDATION_MIN_RESOLVED_RATIO:.0%}."
    )


def _first_launch_report_validation_issue(payload: dict[str, Any]) -> str:
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return ""
    for result in claims:
        if not isinstance(result, dict):
            continue
        if _validation_result_state(result) != "failed":
            continue
        claim_text = _compact_tooltip_text(result.get("claim_text"), max_length=120)
        reason = _compact_tooltip_text(_validation_result_reason(result))
        if claim_text and reason:
            return f"First failed claim: {claim_text} ({reason})."
        if claim_text:
            return f"First failed claim: {claim_text}."
        if reason:
            return f"First failed claim: {reason}."
    return ""


def _launch_report_validation_badge_tooltip(
    state: str,
    payload: object | None,
) -> str:
    base_lines = {
        "checked": ["No failed deterministic claims found."],
        "noted": ["No failed deterministic claims, but caution notes remain."],
        "caution": ["One or more deterministic claims disagree with the package."],
        "unknown": [
            "Unknown: too many mapped text units remain unresolved for a report-level status."
        ],
        "summary": ["Summary report: package-level validation is not applicable."],
        "pending": ["Automated validation is not available yet."],
    }
    lines = list(base_lines.get(state, base_lines["pending"]))
    if not isinstance(payload, dict):
        return "\n".join(lines)

    resolver = payload.get("resolver")
    if isinstance(resolver, dict):
        resolver_status = resolver.get("status")
        resolver_reason = resolver.get("reason")
        if resolver_status == "unresolved":
            lines.append("Package matching failed before validation could run.")
        if isinstance(resolver_reason, str) and resolver_reason.strip():
            lines.append(f"Resolver reason: {resolver_reason.strip()}.")

    summary = payload.get("summary")
    counts_line = _launch_report_validation_counts_line(summary)
    if counts_line:
        lines.append(counts_line)
    resolved_line = _launch_report_validation_resolved_line(summary)
    if resolved_line:
        lines.append(resolved_line)
    if state == "caution":
        first_issue = _first_launch_report_validation_issue(payload)
        if first_issue:
            lines.append(first_issue)

    return "\n".join(_dedupe_tooltip_lines(lines, limit=8))


def _launch_report_validation_badge(
    state: str | None,
    payload: object | None = None,
) -> dict[str, str]:
    normalized_state = (
        state if state in _LAUNCH_REPORT_VALIDATION_LABEL_KEYS else "pending"
    )
    badge = {
        "state": normalized_state,
        "label_key": _LAUNCH_REPORT_VALIDATION_LABEL_KEYS[normalized_state],
        "tooltip": _launch_report_validation_badge_tooltip(
            normalized_state,
            payload,
        ),
    }
    short_label_key = _LAUNCH_REPORT_VALIDATION_SHORT_LABEL_KEYS.get(normalized_state)
    if short_label_key is not None:
        badge["short_label_key"] = short_label_key
    return badge


def _library_listing_payload(
    listing: list[PresentationListingItem],
    *,
    library: PdfLibrary,
    validation_states: dict[str, dict[str, str] | str] | None = None,
) -> list[dict[str, object]]:
    child_doc_ids = (
        _LAUNCH_REPORT_CHILD_IDS if library.page_path == "/review/reports/page" else ()
    )
    items: list[dict[str, object]] = []
    for item in listing:
        payload: dict[str, object] = {
            "doc_id": item.doc_id,
            "title": item.title,
            "allowed": item.allowed,
            "indent_level": 1 if item.doc_id in child_doc_ids else 0,
        }
        if validation_states is not None:
            validation_state = validation_states.get(item.doc_id)
            payload["validation"] = (
                validation_state
                if isinstance(validation_state, dict)
                else _launch_report_validation_badge(validation_state)
            )
        items.append(payload)
    return items


def _launch_report_companion_assets(doc_id: str) -> LaunchReportCompanionAssets:
    return LaunchReportCompanionAssets(
        document=_resolve_optional_pdf_document(
            doc_id,
            _launch_report_documents_root(),
        ),
        podcast=_resolve_optional_audio_asset(
            doc_id,
            _launch_report_podcasts_root(),
        ),
        video=_resolve_optional_video_asset(
            doc_id,
            _launch_report_videos_root(),
        ),
    )


def _brand_report_companion_assets(doc_id: str) -> LaunchReportCompanionAssets:
    return LaunchReportCompanionAssets(
        document=_resolve_optional_pdf_document(
            doc_id,
            _brand_report_documents_root(),
        ),
        podcast=_resolve_optional_audio_asset(
            doc_id,
            _brand_report_podcasts_root(),
        ),
        video=None,
    )


def _resolve_launch_report_viewer_documents(
    doc_id: str,
    *,
    variant: LaunchReportViewerVariant,
) -> tuple[PdfDocument, PdfDocument, LaunchReportCompanionAssets]:
    report_document = _resolve_pdf_document(doc_id, _launch_reports_pdf_root())
    companion_assets = _launch_report_companion_assets(report_document.doc_id)
    if variant is LaunchReportViewerVariant.DOCUMENT:
        if companion_assets.document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )
        return report_document, companion_assets.document, companion_assets
    return report_document, report_document, companion_assets


def _resolve_brand_report_viewer_documents(
    doc_id: str,
    *,
    variant: LaunchReportViewerVariant,
) -> tuple[PdfDocument, PdfDocument, LaunchReportCompanionAssets]:
    report_document = _resolve_pdf_document(doc_id, _brand_reports_pdf_root())
    companion_assets = _brand_report_companion_assets(report_document.doc_id)
    if variant is LaunchReportViewerVariant.DOCUMENT:
        if companion_assets.document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )
        return report_document, companion_assets.document, companion_assets
    return report_document, report_document, companion_assets


def _launch_report_cache_namespace(variant: LaunchReportViewerVariant) -> str:
    if variant is LaunchReportViewerVariant.DOCUMENT:
        return "launch_report_documents"
    return "launch_reports"


def _brand_report_cache_namespace(variant: LaunchReportViewerVariant) -> str:
    if variant is LaunchReportViewerVariant.DOCUMENT:
        return "brand_report_documents"
    return "brand_reports"


def _audio_media_type(path: Path) -> str:
    return _AUDIO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _video_media_type(path: Path) -> str:
    return _VIDEO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _invalid_range_response(file_size: int) -> Response:
    return Response(
        status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes */{file_size}",
        },
    )


def _parse_byte_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    match = _HTTP_RANGE.match(range_header.strip())
    if match is None:
        return None

    start_raw, end_raw = match.groups()
    if not start_raw and not end_raw:
        return None

    if not start_raw:
        suffix_length = int(end_raw)
        if suffix_length <= 0:
            return None
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    else:
        start = int(start_raw)
        end = int(end_raw) if end_raw else file_size - 1
        if end >= file_size:
            end = file_size - 1

    if start >= file_size or end < start:
        return None
    return start, end


def _iter_file_bytes(path: Path, start: int, end: int) -> Iterator[bytes]:
    with path.open("rb") as file_obj:
        file_obj.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file_obj.read(min(_MEDIA_STREAM_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _stream_video_response(path: Path, request: Request) -> Response:
    file_size = path.stat().st_size
    if file_size <= 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file is empty.",
        )

    range_header = request.headers.get("range")
    byte_range = _parse_byte_range(range_header, file_size) if range_header else None
    if range_header and byte_range is None:
        return _invalid_range_response(file_size)

    start, end = byte_range if byte_range is not None else (0, file_size - 1)
    content_length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
        "Content-Disposition": f'inline; filename="{path.name}"',
        "Content-Length": str(content_length),
        "Vary": "Cookie",
    }
    status_code = status.HTTP_200_OK
    if byte_range is not None:
        status_code = status.HTTP_206_PARTIAL_CONTENT
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return StreamingResponse(
        _iter_file_bytes(path, start, end),
        status_code=status_code,
        media_type=_video_media_type(path),
        headers=headers,
    )


def _assert_document_allowed(
    document: PdfDocument | str,
    user: AuthenticatedUser | None,
    *,
    permissions_loader: Callable[[], dict[str, set[str]]],
) -> None:
    document_id = document.doc_id if isinstance(document, PdfDocument) else document
    if is_presentation_allowed(
        document_id,
        user.email if user else None,
        permissions_loader(),
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not authorized to view this document.",
    )


def _render_pdf_library_page(
    request: Request,
    lang: str,
    *,
    user: AuthenticatedUser | None,
    library: PdfLibrary,
) -> Any:
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    page_label = get_navigation_label(lang, library.page_path)
    permissions = library.permissions_loader()
    pdf_root = library.pdf_root_resolver()
    documents = _sort_library_documents(
        _list_pdf_documents(pdf_root),
        library=library,
    )
    validation_states = (
        _load_launch_report_validation_states(pdf_root)
        if library.page_path == "/review/reports/page"
        else None
    )
    listing = build_presentation_listing(
        [
            PresentationDocumentInfo(doc_id=document.doc_id, title=document.title)
            for document in documents
        ],
        user.email if user else None,
        permissions,
    )
    response = templates.TemplateResponse(
        request,
        "projects.html",
        {
            "lang": lang,
            "page_label": page_label,
            "copy": get_page_copy(library.page_copy_key, lang),
            "documents": _library_listing_payload(
                listing,
                library=library,
                validation_states=validation_states,
            ),
            "viewer_base_path": library.viewer_base_path,
        },
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Cookie"
    return response


def _render_pdf_document_viewer(
    request: Request,
    doc_id: str,
    *,
    user: AuthenticatedUser | None,
    page: int,
    lang: str,
    library: PdfLibrary,
) -> Any:
    pdf_root = library.pdf_root_resolver()
    document = _resolve_pdf_document(doc_id, pdf_root)
    _assert_document_allowed(
        document,
        user,
        permissions_loader=library.permissions_loader,
    )

    scale = _render_scale()
    cache_dir = _cache_dir_for(library.cache_namespace, document.doc_id)
    meta = _ensure_cache_fresh(document.path, cache_dir, scale=scale)
    page_count = int(meta["page_count"])
    if page > page_count:
        page = page_count

    response = templates.TemplateResponse(
        request,
        "pdf_viewer.html",
        {
            "lang": lang,
            "doc_id": document.doc_id,
            "doc_title": document.title,
            "page": page,
            "page_count": page_count,
            "viewer_email": user.email if user else "",
            "viewer_base_path": library.viewer_base_path,
            "back_path": library.page_path,
        },
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Cookie"
    return response


def _render_pdf_document_page_image(
    doc_id: str,
    page_number: int,
    *,
    user: AuthenticatedUser | None,
    library: PdfLibrary,
) -> FileResponse:
    pdf_root = library.pdf_root_resolver()
    document = _resolve_pdf_document(doc_id, pdf_root)
    _assert_document_allowed(
        document,
        user,
        permissions_loader=library.permissions_loader,
    )
    if page_number < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found."
        )

    scale = _render_scale()
    cache_dir = _cache_dir_for(library.cache_namespace, document.doc_id)
    meta = _ensure_cache_fresh(document.path, cache_dir, scale=scale)
    page_count = int(meta["page_count"])
    if page_number > page_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found."
        )

    output_path = cache_dir / f"{page_number:04d}.png"
    if not output_path.exists():
        _render_pdf_page(
            document.path, page_number=page_number, scale=scale, output_path=output_path
        )

    headers = {
        "Cache-Control": "no-store, private",
        "Pragma": "no-cache",
        "Vary": "Cookie",
    }
    return FileResponse(output_path, media_type="image/png", headers=headers)


def _concept_listing_payload(
    listing: list[PresentationListingItem],
) -> list[dict[str, object]]:
    return [
        {
            "doc_id": item.doc_id,
            "title": item.title,
            "allowed": item.allowed,
            "indent_level": 0,
        }
        for item in listing
    ]


def _render_product_hypotheses_page(
    request: Request,
    lang: str,
    *,
    user: AuthenticatedUser | None,
) -> Any:
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )

    documents = _list_concept_documents(_concept_sites_root())
    permissions = get_concept_permissions()
    listing = build_presentation_listing(
        [
            PresentationDocumentInfo(doc_id=document.doc_id, title=document.title)
            for document in documents
        ],
        user.email if user else None,
        permissions,
    )
    response = templates.TemplateResponse(
        request,
        "projects.html",
        {
            "lang": lang,
            "page_label": get_navigation_label(lang, "/review/product-hypotheses/page"),
            "copy": get_page_copy("product_hypotheses", lang),
            "documents": _concept_listing_payload(listing),
            "viewer_base_path": "/review/product-hypotheses/site",
        },
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Cookie"
    return response


def _resolve_concept_file(
    document: ConceptSiteDocument,
    requested_path: str,
) -> Path:
    relative_path = (
        Path(requested_path.lstrip("/")) if requested_path else Path("index.html")
    )
    target = (document.root / relative_path).resolve()
    try:
        target.relative_to(document.root.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        ) from exc
    if target.is_dir():
        target = (target / "index.html").resolve()
        try:
            target.relative_to(document.root.resolve())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found.",
            ) from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        )
    return target


def _append_concept_site_style(
    soup: BeautifulSoup,
    *,
    style_id: str,
    style: str,
) -> None:
    """Append a generated style tag once."""

    if soup.find(id=style_id) is not None:
        return
    style_tag = soup.new_tag("style", id=style_id)
    style_tag.string = style
    if soup.head is not None:
        soup.head.append(style_tag)
    else:
        soup.insert(0, style_tag)


def _concept_site_media_type(path: Path) -> str:
    """Return the response media type for a concept-site static asset."""

    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _resolve_local_concept_site_image(
    url: str,
    *,
    base_dir: Path,
    asset_root: Path,
) -> Path | None:
    """Resolve a local image reference within a concept-site directory."""

    parsed = urlsplit(url.strip())
    if not parsed.path or parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
        return None
    path = Path(unquote(parsed.path))
    if path.suffix.lower() not in _CONCEPT_SITE_IMAGE_SUFFIXES:
        return None
    target = (base_dir / path).resolve()
    try:
        target.relative_to(asset_root.resolve())
    except ValueError:
        return None
    if not target.exists() or not target.is_file():
        return None
    return target


def _concept_site_image_data_uri(path: Path) -> str:
    """Return a data URI for a local concept-site image."""

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{_concept_site_media_type(path)};base64,{encoded}"


def _inline_concept_site_image_assets(
    soup: BeautifulSoup,
    *,
    image_selectors: list[str],
    base_dir: Path | None,
    asset_root: Path | None,
) -> None:
    """Inline displayed board images while preserving normal image links."""

    if base_dir is None or asset_root is None:
        return
    image_cache: dict[Path, str] = {}

    def data_uri_for(url: str) -> str | None:
        image_path = _resolve_local_concept_site_image(
            url,
            base_dir=base_dir,
            asset_root=asset_root,
        )
        if image_path is None:
            return None
        if image_path not in image_cache:
            image_cache[image_path] = _concept_site_image_data_uri(image_path)
        return image_cache[image_path]

    for image in soup.select(",".join(image_selectors)):
        source = image.get("src")
        if not isinstance(source, str):
            continue
        data_uri = data_uri_for(source)
        if data_uri is not None:
            image["src"] = data_uri

    for link in soup.find_all("a", href=True):
        href = link.get("href")
        if not isinstance(href, str):
            continue
        if "open board image" not in link.get_text(" ", strip=True).lower():
            continue
        if (
            _resolve_local_concept_site_image(
                href,
                base_dir=base_dir,
                asset_root=asset_root,
            )
            is not None
        ):
            link["target"] = "_blank"
            link["rel"] = "noopener"


def _inject_concept_site_image_overlay(
    html: str,
    *,
    base_dir: Path | None = None,
    asset_root: Path | None = None,
) -> str:
    """Prepare product-hypothesis HTML with captions and shared review styling."""

    marker = "mparanza-hypothesis-artifact-watermark"
    style = """
.mparanza-hypothesis-artifact-frame {
  position: relative !important;
}
.mparanza-hypothesis-artifact-figure {
  overflow: visible !important;
}
.mparanza-hypothesis-artifact-figure > img {
  display: block;
  height: auto !important;
}
.mparanza-hypothesis-artifact-watermark {
  display: block;
  width: max-content;
  max-width: calc(100% - 20px);
  box-sizing: border-box;
  margin: 8px 10px 10px auto;
  padding: 4px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.54);
  color: rgba(80, 80, 80, 0.62);
  font: 500 12px/1.2 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0.02em;
  pointer-events: none;
  text-align: right;
  white-space: normal;
  overflow-wrap: anywhere;
  user-select: none;
}
@media (max-width: 640px) {
  .mparanza-hypothesis-artifact-watermark {
    max-width: calc(100% - 20px);
    margin-top: 6px;
    font-size: 9.5px;
  }
}
""".strip()
    review_style = """
:root {
  --mparanza-hypothesis-review-bg: linear-gradient(180deg, #ffffff 0%, #fbfcfd 100%);
  --mparanza-hypothesis-review-surface: #ffffff;
  --mparanza-hypothesis-review-ink: #0e1525;
  --mparanza-hypothesis-review-muted: #667085;
  --mparanza-hypothesis-review-line: rgba(226, 232, 240, 0.82);
  --mparanza-hypothesis-review-shadow: none;
}
body {
  background: var(--mparanza-hypothesis-review-bg) !important;
  color: var(--mparanza-hypothesis-review-ink) !important;
  font-family: "Instrument Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif !important;
  font-size: 1rem !important;
  font-kerning: normal !important;
  line-height: 1.55 !important;
  text-rendering: optimizeLegibility !important;
}
.topbar,
header.topbar {
  background: rgba(255, 255, 255, 0.96) !important;
  border-bottom: 1px solid var(--mparanza-hypothesis-review-line) !important;
  backdrop-filter: none !important;
  box-shadow: none !important;
}
.nav,
.nav-inner {
  min-height: 48px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}
.logo {
  color: var(--mparanza-hypothesis-review-muted) !important;
  font-size: 0.82rem !important;
  font-weight: 650 !important;
  letter-spacing: 0.04em !important;
  text-transform: none !important;
}
.nav-links a,
.navlinks a {
  font-size: 0.86rem !important;
  color: var(--mparanza-hypothesis-review-muted) !important;
  padding: 0.42rem 0.62rem !important;
}
main,
.wrap,
.site-shell > main {
  padding-top: clamp(1rem, 2.5vw, 2rem) !important;
  padding-bottom: clamp(2.25rem, 4vw, 3.5rem) !important;
}
.hero {
  padding-top: clamp(1rem, 2.5vw, 2rem) !important;
  padding-bottom: clamp(1rem, 3vw, 1.8rem) !important;
}
h1,
h2,
h3,
.productTitle {
  font-family: "Instrument Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif !important;
  letter-spacing: -0.015em !important;
}
h1 {
  font-size: clamp(1.65rem, 2.8vw, 2.65rem) !important;
  line-height: 1.16 !important;
  font-weight: 650 !important;
  max-width: 28ch !important;
}
.productTitle {
  font-size: clamp(1.55rem, 2.6vw, 2.4rem) !important;
  line-height: 1.15 !important;
  font-weight: 650 !important;
}
h2 {
  font-size: clamp(1.2rem, 1.8vw, 1.55rem) !important;
  line-height: 1.22 !important;
  font-weight: 650 !important;
}
h3 {
  font-size: clamp(1rem, 1.25vw, 1.15rem) !important;
  line-height: 1.25 !important;
  font-weight: 650 !important;
}
p,
li {
  line-height: 1.58 !important;
}
.lede,
.heroIntro,
.introRead,
.card p,
.frameworkCard p,
.step p,
.note,
.readBox p {
  max-width: 68ch !important;
}
.card,
.frameworkCard,
.hypCard,
.productPanel,
.heroVisual,
.readCard,
.module,
.status,
.lineage,
.explain,
.gate,
.step,
.step-card,
.readBox,
.note,
.intro-card,
.introCard,
.intro-copy,
.chain-card,
.hypothesis-card,
.card-media,
.card-body,
.module-card,
.product-panel,
.status-card,
.balanced-card,
.validation-card,
.purpose-card,
.status .item {
  background: var(--mparanza-hypothesis-review-surface) !important;
  background-image: none !important;
  border-color: var(--mparanza-hypothesis-review-line) !important;
  border-radius: 14px !important;
  box-shadow: var(--mparanza-hypothesis-review-shadow) !important;
}
.card::before,
.card::after,
.frameworkCard::before,
.frameworkCard::after,
.hypCard::before,
.hypCard::after,
.step-card::before,
.step-card::after,
.hypothesis-card::before,
.hypothesis-card::after,
.module-card::before,
.module-card::after {
  content: none !important;
  display: none !important;
}
.body,
.card.pad,
.frameworkCard,
.productPanel,
.product-panel,
.readBox,
.note,
.step,
.step-card,
.moduleBody {
  padding: clamp(1rem, 2vw, 1.35rem) !important;
}
.intro-grid,
.workflow,
.framework,
.section {
  margin-top: clamp(1rem, 3vw, 2rem) !important;
}
.pill,
.confidence,
.metaRow span,
.eyebrow,
.kicker,
.label {
  letter-spacing: 0.06em !important;
  font-weight: 650 !important;
  color: var(--mparanza-hypothesis-review-muted) !important;
}
.btn {
  padding: 0.58rem 0.88rem !important;
  border-radius: 999px !important;
  font-size: 0.88rem !important;
  font-weight: 700 !important;
}
footer {
  color: var(--mparanza-hypothesis-review-muted) !important;
  border-top-color: var(--mparanza-hypothesis-review-line) !important;
}
@media (max-width: 720px) {
  h1,
  .productTitle {
    max-width: none !important;
  }
  .hero,
  main,
  .wrap {
    padding-top: 1.5rem !important;
  }
}
""".strip()
    selectors = [
        ".board-frame > img",
        ".boardImg > img",
        ".card-media > img",
        ".cardMedia > img",
        ".imageWrap > img",
        ".heroVisual > img",
        ".hero-visual > img",
        ".heroImage > img",
        ".hero-image > img",
        ".hero img",
        ".hypCard > a > img",
        ".hypCard > figure > img",
        ".hypCard > .boardImg > img",
        ".hypCard > img",
        "main > figure > img",
        "section > figure > img",
        "article > figure > img",
        ".cardimg > img",
    ]

    soup = BeautifulSoup(html, "html.parser")
    _inline_concept_site_image_assets(
        soup,
        image_selectors=selectors,
        base_dir=base_dir,
        asset_root=asset_root,
    )
    _append_concept_site_style(
        soup,
        style_id="mparanza-hypothesis-artifact-overlay-style",
        style=style,
    )
    _append_concept_site_style(
        soup,
        style_id="mparanza-hypothesis-review-style",
        style=review_style,
    )

    for image in soup.select(",".join(selectors)):
        container = image.parent
        if container is None:
            continue
        container_classes = container.get("class", [])
        insert_target = container if "cardimg" in container_classes else image
        if insert_target.find_next_sibling(class_=marker) is not None:
            continue
        if "mparanza-hypothesis-artifact-frame" not in container_classes:
            container_classes.append("mparanza-hypothesis-artifact-frame")
        if (
            getattr(container, "name", "").lower() == "figure"
            and "mparanza-hypothesis-artifact-figure" not in container_classes
        ):
            container_classes.append("mparanza-hypothesis-artifact-figure")
        if container.get("class") != container_classes:
            container["class"] = container_classes
        watermark = soup.new_tag("div")
        watermark["class"] = marker
        watermark["aria-hidden"] = "true"
        watermark.string = _CONCEPT_SITE_IMAGE_OVERLAY_TEXT
        insert_target.insert_after(watermark)

    return str(soup)


def _serve_concept_file(
    doc_id: str,
    requested_path: str,
    *,
    user: AuthenticatedUser | None,
) -> Response:
    document = _resolve_concept_document(doc_id, _concept_sites_root())
    _assert_document_allowed(
        document.doc_id,
        user,
        permissions_loader=get_concept_permissions,
    )
    target = _resolve_concept_file(document, requested_path)
    headers = {
        "Cache-Control": "no-store, private",
        "Pragma": "no-cache",
        "Vary": "Cookie",
    }
    if target.suffix.lower() in {".html", ".htm"}:
        html = target.read_text(encoding="utf-8", errors="replace")
        return HTMLResponse(
            _inject_concept_site_image_overlay(
                html,
                base_dir=target.parent,
                asset_root=document.root,
            ),
            headers=headers,
        )
    if target.suffix.lower() in _CONCEPT_SITE_IMAGE_SUFFIXES:
        return Response(
            target.read_bytes(),
            media_type=_concept_site_media_type(target),
            headers=headers,
        )
    return FileResponse(target, headers=headers)


def _render_launch_report_document_viewer(
    request: Request,
    doc_id: str,
    *,
    user: AuthenticatedUser | None,
    page: int,
    lang: str,
    variant: LaunchReportViewerVariant,
) -> Any:
    report_document, viewer_document, companion_assets = (
        _resolve_launch_report_viewer_documents(doc_id, variant=variant)
    )
    _assert_document_allowed(
        report_document,
        user,
        permissions_loader=get_launch_report_permissions,
    )

    scale = _render_scale()
    cache_dir = _cache_dir_for(
        _launch_report_cache_namespace(variant),
        report_document.doc_id,
    )
    meta = _ensure_cache_fresh(viewer_document.path, cache_dir, scale=scale)
    page_count = int(meta["page_count"])
    if page > page_count:
        page = page_count

    report_url = ""
    document_url = ""
    if variant is LaunchReportViewerVariant.DOCUMENT:
        report_url = f"/review/reports/pdf/{report_document.doc_id}?lang={lang}&page=1"
    elif companion_assets.document is not None:
        document_url = (
            f"/review/reports/pdf/{report_document.doc_id}"
            f"?lang={lang}&page=1&variant=document"
        )
    podcast_url = ""
    if companion_assets.podcast is not None:
        podcast_url = f"/review/reports/pdf/{report_document.doc_id}/podcast"
    video_url = ""
    if companion_assets.video is not None:
        video_url = f"/review/reports/pdf/{report_document.doc_id}/video"
    validation_layer_url = ""
    if variant is LaunchReportViewerVariant.REPORT:
        validation_layer_url = (
            f"/review/reports/pdf/{report_document.doc_id}/validation-layer"
        )

    response = templates.TemplateResponse(
        request,
        "pdf_viewer.html",
        {
            "lang": lang,
            "doc_id": report_document.doc_id,
            "doc_title": report_document.title,
            "page": page,
            "page_count": page_count,
            "viewer_email": user.email if user else "",
            "viewer_base_path": "/review/reports/pdf",
            "back_path": "/review/reports/page",
            "viewer_variant": variant.value,
            "viewer_variant_label": (
                "Document version"
                if variant is LaunchReportViewerVariant.DOCUMENT
                else "Launch report"
            ),
            "report_switch_url": report_url,
            "document_switch_url": document_url,
            "podcast_url": podcast_url,
            "video_url": video_url,
            "validation_layer_url": validation_layer_url,
            "ai_accuracy_disclaimer": _AI_ACCURACY_DISCLAIMER,
        },
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Cookie"
    return response


def _render_brand_report_document_viewer(
    request: Request,
    doc_id: str,
    *,
    user: AuthenticatedUser | None,
    page: int,
    lang: str,
    variant: LaunchReportViewerVariant,
) -> Any:
    report_document, viewer_document, companion_assets = (
        _resolve_brand_report_viewer_documents(doc_id, variant=variant)
    )
    _assert_document_allowed(
        report_document,
        user,
        permissions_loader=get_brand_report_permissions,
    )

    scale = _render_scale()
    cache_dir = _cache_dir_for(
        _brand_report_cache_namespace(variant),
        report_document.doc_id,
    )
    meta = _ensure_cache_fresh(viewer_document.path, cache_dir, scale=scale)
    page_count = int(meta["page_count"])
    if page > page_count:
        page = page_count

    brand_report_url = f"/review/brand-reports/pdf/{report_document.doc_id}"
    report_url = ""
    document_url = ""
    if variant is LaunchReportViewerVariant.DOCUMENT:
        report_url = f"{brand_report_url}?lang={lang}&page=1"
    elif companion_assets.document is not None:
        document_url = f"{brand_report_url}?lang={lang}&page=1&variant=document"
    podcast_url = ""
    if companion_assets.podcast is not None:
        podcast_url = f"{brand_report_url}/podcast"

    response = templates.TemplateResponse(
        request,
        "pdf_viewer.html",
        {
            "lang": lang,
            "doc_id": report_document.doc_id,
            "doc_title": report_document.title,
            "page": page,
            "page_count": page_count,
            "viewer_email": user.email if user else "",
            "viewer_base_path": "/review/brand-reports/pdf",
            "back_path": "/review/brand-reports/page",
            "viewer_variant": variant.value,
            "viewer_variant_label": (
                "Document version"
                if variant is LaunchReportViewerVariant.DOCUMENT
                else "Brand report"
            ),
            "report_switch_url": report_url,
            "document_switch_url": document_url,
            "podcast_url": podcast_url,
            "video_url": "",
            "validation_layer_url": "",
            "ai_accuracy_disclaimer": _AI_ACCURACY_DISCLAIMER,
        },
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Cookie"
    return response


def _render_launch_report_document_page_image(
    doc_id: str,
    page_number: int,
    *,
    user: AuthenticatedUser | None,
    variant: LaunchReportViewerVariant,
) -> FileResponse:
    report_document, viewer_document, _ = _resolve_launch_report_viewer_documents(
        doc_id,
        variant=variant,
    )
    _assert_document_allowed(
        report_document,
        user,
        permissions_loader=get_launch_report_permissions,
    )
    if page_number < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found."
        )

    scale = _render_scale()
    cache_dir = _cache_dir_for(
        _launch_report_cache_namespace(variant),
        report_document.doc_id,
    )
    meta = _ensure_cache_fresh(viewer_document.path, cache_dir, scale=scale)
    page_count = int(meta["page_count"])
    if page_number > page_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found."
        )

    output_path = cache_dir / f"{page_number:04d}.png"
    if not output_path.exists():
        _render_pdf_page(
            viewer_document.path,
            page_number=page_number,
            scale=scale,
            output_path=output_path,
        )

    headers = {
        "Cache-Control": "no-store, private",
        "Pragma": "no-cache",
        "Vary": "Cookie",
    }
    return FileResponse(output_path, media_type="image/png", headers=headers)


def _render_brand_report_document_page_image(
    doc_id: str,
    page_number: int,
    *,
    user: AuthenticatedUser | None,
    variant: LaunchReportViewerVariant,
) -> FileResponse:
    report_document, viewer_document, _ = _resolve_brand_report_viewer_documents(
        doc_id,
        variant=variant,
    )
    _assert_document_allowed(
        report_document,
        user,
        permissions_loader=get_brand_report_permissions,
    )
    if page_number < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found."
        )

    scale = _render_scale()
    cache_dir = _cache_dir_for(
        _brand_report_cache_namespace(variant),
        report_document.doc_id,
    )
    meta = _ensure_cache_fresh(viewer_document.path, cache_dir, scale=scale)
    page_count = int(meta["page_count"])
    if page_number > page_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found."
        )

    output_path = cache_dir / f"{page_number:04d}.png"
    if not output_path.exists():
        _render_pdf_page(
            viewer_document.path,
            page_number=page_number,
            scale=scale,
            output_path=output_path,
        )

    headers = {
        "Cache-Control": "no-store, private",
        "Pragma": "no-cache",
        "Vary": "Cookie",
    }
    return FileResponse(output_path, media_type="image/png", headers=headers)


@site_router.get("/presentations/page", include_in_schema=False)
def presentations_page(
    request: Request,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> Any:
    lang = resolve_language(request)
    return _render_pdf_library_page(
        request,
        lang,
        user=user,
        library=_presentations_library(),
    )


@site_router.get("/presentations/pdf/{doc_id}", include_in_schema=False)
def pdf_document_viewer(
    request: Request,
    doc_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
    page: int = Query(1, ge=1),
) -> Any:
    lang = resolve_language(request)
    return _render_pdf_document_viewer(
        request,
        doc_id,
        user=user,
        page=page,
        lang=lang,
        library=_presentations_library(),
    )


@site_router.get(
    "/presentations/pdf/{doc_id}/page/{page_number}.png", include_in_schema=False
)
def pdf_document_page_image(
    request: Request,
    doc_id: str,
    page_number: int,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> FileResponse:
    return _render_pdf_document_page_image(
        doc_id,
        page_number,
        user=user,
        library=_presentations_library(),
    )


@site_router.get("/review/product-hypotheses/page", include_in_schema=False)
def product_hypotheses_page(
    request: Request,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> Any:
    lang = resolve_language(request)
    return _render_product_hypotheses_page(request, lang, user=user)


@site_router.get("/review/product-hypotheses/site/{doc_id}", include_in_schema=False)
def product_hypotheses_document_redirect(
    request: Request,
    doc_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> RedirectResponse:
    _assert_document_allowed(
        _slugify(doc_id),
        user,
        permissions_loader=get_concept_permissions,
    )
    location = f"/review/product-hypotheses/site/{_slugify(doc_id)}/"
    if request.url.query:
        location = f"{location}?{request.url.query}"
    response = RedirectResponse(
        url=location, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Cookie"
    return response


@site_router.get(
    "/review/product-hypotheses/site/{doc_id}/",
    include_in_schema=False,
)
@site_router.get(
    "/review/product-hypotheses/site/{doc_id}/{requested_path:path}",
    include_in_schema=False,
)
def product_hypotheses_document_viewer(
    request: Request,
    doc_id: str,
    requested_path: str = "",
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> Response:
    _ = request
    return _serve_concept_file(doc_id, requested_path, user=user)


@site_router.get("/review/brand-reports/page", include_in_schema=False)
def brand_reports_page(
    request: Request,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> Any:
    lang = resolve_language(request)
    return _render_pdf_library_page(
        request,
        lang,
        user=user,
        library=_brand_reports_library(),
    )


@site_router.get("/review/brand-reports/pdf/{doc_id}", include_in_schema=False)
def brand_report_document_viewer(
    request: Request,
    doc_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
    page: int = Query(1, ge=1),
    variant: LaunchReportViewerVariant = Query(LaunchReportViewerVariant.REPORT),
) -> Any:
    lang = resolve_language(request)
    return _render_brand_report_document_viewer(
        request,
        doc_id,
        user=user,
        page=page,
        lang=lang,
        variant=variant,
    )


@site_router.get(
    "/review/brand-reports/pdf/{doc_id}/page/{page_number}.png",
    include_in_schema=False,
)
def brand_report_document_page_image(
    request: Request,
    doc_id: str,
    page_number: int,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
    variant: LaunchReportViewerVariant = Query(LaunchReportViewerVariant.REPORT),
) -> FileResponse:
    _ = request
    return _render_brand_report_document_page_image(
        doc_id,
        page_number,
        user=user,
        variant=variant,
    )


@site_router.get("/review/brand-reports/pdf/{doc_id}/podcast", include_in_schema=False)
def brand_report_podcast(
    request: Request,
    doc_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> FileResponse:
    _ = request
    report_document, _, companion_assets = _resolve_brand_report_viewer_documents(
        doc_id,
        variant=LaunchReportViewerVariant.REPORT,
    )
    _assert_document_allowed(
        report_document,
        user,
        permissions_loader=get_brand_report_permissions,
    )
    podcast_path = companion_assets.podcast
    if podcast_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Podcast not found.",
        )

    headers = {
        "Cache-Control": "no-store, private",
        "Pragma": "no-cache",
        "Vary": "Cookie",
        "Content-Disposition": f'inline; filename="{podcast_path.name}"',
    }
    return FileResponse(
        podcast_path,
        media_type=_audio_media_type(podcast_path),
        headers=headers,
    )


@site_router.get("/review/reports/page", include_in_schema=False)
def launch_reports_page(
    request: Request,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> Any:
    lang = resolve_language(request)
    return _render_pdf_library_page(
        request,
        lang,
        user=user,
        library=_launch_reports_library(),
    )


@site_router.get("/review/reports/pdf/{doc_id}", include_in_schema=False)
def launch_report_document_viewer(
    request: Request,
    doc_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
    page: int = Query(1, ge=1),
    variant: LaunchReportViewerVariant = Query(LaunchReportViewerVariant.REPORT),
) -> Any:
    lang = resolve_language(request)
    return _render_launch_report_document_viewer(
        request,
        doc_id,
        user=user,
        page=page,
        lang=lang,
        variant=variant,
    )


@site_router.get(
    "/review/reports/pdf/{doc_id}/validation-layer", include_in_schema=False
)
def launch_report_validation_layer(
    request: Request,
    doc_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    _ = request
    pdf_root = _launch_reports_pdf_root()
    document = _resolve_pdf_document(doc_id, pdf_root)
    _assert_document_allowed(
        document,
        user,
        permissions_loader=get_launch_report_permissions,
    )
    return _build_launch_report_validation_layer_payload(
        document,
        page=page,
        pdf_root=pdf_root,
    )


@site_router.get(
    "/review/reports/pdf/{doc_id}/page/{page_number}.png", include_in_schema=False
)
def launch_report_document_page_image(
    request: Request,
    doc_id: str,
    page_number: int,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
    variant: LaunchReportViewerVariant = Query(LaunchReportViewerVariant.REPORT),
) -> FileResponse:
    return _render_launch_report_document_page_image(
        doc_id,
        page_number,
        user=user,
        variant=variant,
    )


@site_router.get("/review/reports/pdf/{doc_id}/podcast", include_in_schema=False)
def launch_report_podcast(
    request: Request,
    doc_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> FileResponse:
    _ = request
    report_document, _, companion_assets = _resolve_launch_report_viewer_documents(
        doc_id,
        variant=LaunchReportViewerVariant.REPORT,
    )
    _assert_document_allowed(
        report_document,
        user,
        permissions_loader=get_launch_report_permissions,
    )
    podcast_path = companion_assets.podcast
    if podcast_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Podcast not found.",
        )

    headers = {
        "Cache-Control": "no-store, private",
        "Pragma": "no-cache",
        "Vary": "Cookie",
        "Content-Disposition": f'inline; filename="{podcast_path.name}"',
    }
    return FileResponse(
        podcast_path,
        media_type=_audio_media_type(podcast_path),
        headers=headers,
    )


@site_router.get("/review/reports/pdf/{doc_id}/video", include_in_schema=False)
def launch_report_video(
    request: Request,
    doc_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> Response:
    report_document, _, companion_assets = _resolve_launch_report_viewer_documents(
        doc_id,
        variant=LaunchReportViewerVariant.REPORT,
    )
    _assert_document_allowed(
        report_document,
        user,
        permissions_loader=get_launch_report_permissions,
    )
    video_path = companion_assets.video
    if video_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found.",
        )

    return _stream_video_response(video_path, request)
