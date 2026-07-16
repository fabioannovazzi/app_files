"""Match Clara feedback timeline video frames to PPTX slide candidates."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

__all__ = [
    "SlideFrameMatchError",
    "match_feedback_timeline_to_deck",
    "match_feedback_timeline_to_deck_payload",
    "main",
]

LOGGER = logging.getLogger(__name__)

MATCH_HIGH_SCORE = 0.86
MATCH_MEDIUM_SCORE = 0.74
MATCH_LOW_SCORE = 0.62
MATCH_HIGH_GAP = 0.08
MATCH_MEDIUM_GAP = 0.05
THUMBNAIL_SIZE = (96, 54)
HASH_SIZE = 16


class SlideFrameMatchError(RuntimeError):
    """Raised when timeline-to-slide matching cannot be attempted."""


@dataclass(frozen=True)
class _SlideRender:
    slide_number: int
    path: Path


@dataclass(frozen=True)
class _ImageFeatures:
    mean_values: tuple[int, ...]
    hash_bits: tuple[int, ...]
    edge_values: tuple[int, ...]


@dataclass(frozen=True)
class _PreparedSlideRender:
    slide_number: int
    path: Path
    target_aspect: float
    features: _ImageFeatures


@dataclass(frozen=True)
class _PreparedCrop:
    label: str
    box: tuple[int, int, int, int]
    features: _ImageFeatures


@dataclass(frozen=True)
class _CropScore:
    label: str
    box: tuple[int, int, int, int]
    score: float


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SlideFrameMatchError(f"could not read JSON: {path}") from error
    if not isinstance(payload, dict):
        raise SlideFrameMatchError(f"JSON payload must be an object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _relative_path(path: Path, base_dir: Path | None) -> str:
    if base_dir is None:
        return str(path)
    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def _resolve_path(raw_path: str, *, base_dir: Path | None) -> Path | None:
    clean = raw_path.strip()
    if not clean:
        return None
    path = Path(clean).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve() if path.is_file() else None


def _load_image(path: Path):
    try:
        from PIL import Image
    except ImportError as error:
        raise SlideFrameMatchError("Pillow is required for slide matching") from error
    try:
        return Image.open(path).convert("RGB")
    except OSError as error:
        raise SlideFrameMatchError(f"could not read image: {path}") from error


def _find_soffice(explicit_path: str | None) -> str | None:
    if explicit_path:
        clean = explicit_path.strip()
        return clean or None
    for name in ("soffice", "libreoffice"):
        candidate = shutil.which(name)
        if candidate:
            return candidate
    for candidate in (
        Path("/opt/homebrew/bin/soffice"),
        Path("/usr/local/bin/soffice"),
        Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _render_pdf_pages(
    pdf_path: Path,
    render_dir: Path,
    *,
    rendered_slide_numbers: Sequence[int] | None = None,
) -> list[_SlideRender]:
    try:
        import fitz
    except ImportError as error:
        raise SlideFrameMatchError(
            "PyMuPDF is required to render deck slides"
        ) from error
    renders: list[_SlideRender] = []
    try:
        document = fitz.open(str(pdf_path))
    except Exception as error:
        raise SlideFrameMatchError(
            f"could not open rendered PDF: {pdf_path}"
        ) from error
    try:
        use_slide_numbers = (
            list(rendered_slide_numbers)
            if rendered_slide_numbers
            and len(rendered_slide_numbers) == document.page_count
            else []
        )
        for page_index in range(document.page_count):
            slide_number = (
                use_slide_numbers[page_index] if use_slide_numbers else page_index + 1
            )
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            output_path = render_dir / f"slide-{slide_number:03d}.png"
            pixmap.save(str(output_path))
            renders.append(_SlideRender(slide_number=slide_number, path=output_path))
    finally:
        document.close()
    return renders


def _pptx_visible_slide_numbers(deck_path: Path) -> list[int] | None:
    if deck_path.suffix.lower() != ".pptx":
        return None
    namespaces = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    try:
        with ZipFile(deck_path) as archive:
            presentation = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
            relationships = ElementTree.fromstring(
                archive.read("ppt/_rels/presentation.xml.rels")
            )
            target_by_id = {
                relationship.attrib["Id"]: relationship.attrib["Target"]
                for relationship in relationships
                if "Id" in relationship.attrib and "Target" in relationship.attrib
            }
            slide_ids = presentation.find("p:sldIdLst", namespaces)
            if slide_ids is None:
                return None
            visible_slide_numbers: list[int] = []
            for slide_number, slide_id in enumerate(list(slide_ids), 1):
                relationship_id = slide_id.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                target = target_by_id.get(str(relationship_id))
                if not target:
                    visible_slide_numbers.append(slide_number)
                    continue
                slide_path = (
                    f"ppt/{target}" if not target.startswith("/") else target[1:]
                )
                slide_root = ElementTree.fromstring(archive.read(slide_path))
                if slide_root.attrib.get("show") == "0":
                    continue
                visible_slide_numbers.append(slide_number)
            return visible_slide_numbers
    except (BadZipFile, KeyError, OSError, ElementTree.ParseError):
        return None


def _render_deck_slides(
    deck_path: Path,
    render_dir: Path,
    *,
    soffice_path: str | None = None,
    expected_slide_numbers: set[int] | None = None,
) -> list[_SlideRender]:
    visible_slide_numbers = _pptx_visible_slide_numbers(deck_path)
    expected_numbers = set(expected_slide_numbers or [])
    if expected_numbers and visible_slide_numbers:
        expected_numbers = expected_numbers & set(visible_slide_numbers)
    existing = _load_slide_renders(render_dir)
    if existing:
        if not expected_numbers:
            return existing
        existing_numbers = {slide.slide_number for slide in existing}
        if expected_numbers.issubset(existing_numbers):
            return existing
        LOGGER.info(
            "Ignoring stale slide render cache in %s: found %s of %s expected slides",
            render_dir,
            len(existing_numbers & expected_numbers),
            len(expected_numbers),
        )
        for path in render_dir.glob("slide-*.png"):
            path.unlink(missing_ok=True)
        shutil.rmtree(render_dir / "_pdf", ignore_errors=True)
    if deck_path.suffix.lower() != ".pptx":
        raise SlideFrameMatchError(
            f"deck slide rendering requires a .pptx: {deck_path}"
        )
    executable = _find_soffice(soffice_path)
    if executable is None:
        raise SlideFrameMatchError(
            "LibreOffice/soffice is required to render PPTX slides"
        )
    render_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = render_dir / "_pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    command = [
        executable,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(pdf_dir),
        str(deck_path),
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        detail = (
            result.stderr or result.stdout or "LibreOffice conversion failed"
        ).strip()
        raise SlideFrameMatchError(detail[:800])
    pdf_path = pdf_dir / f"{deck_path.stem}.pdf"
    if not pdf_path.is_file():
        pdf_candidates = sorted(pdf_dir.glob("*.pdf"))
        if not pdf_candidates:
            raise SlideFrameMatchError("LibreOffice did not produce a PDF")
        pdf_path = pdf_candidates[0]
    renders = _render_pdf_pages(
        pdf_path,
        render_dir,
        rendered_slide_numbers=visible_slide_numbers,
    )
    if not renders:
        raise SlideFrameMatchError("deck rendering produced no slide images")
    return renders


def _load_slide_renders(render_dir: Path) -> list[_SlideRender]:
    renders: list[_SlideRender] = []
    for path in sorted(render_dir.glob("slide-*.png")):
        number_text = "".join(
            character for character in path.stem if character.isdigit()
        )
        if not number_text:
            continue
        renders.append(_SlideRender(slide_number=int(number_text), path=path))
    return renders


def _center_aspect_box(
    bounds: tuple[int, int, int, int],
    target_aspect: float,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bounds
    width = max(1, right - left)
    height = max(1, bottom - top)
    current_aspect = width / height
    if current_aspect > target_aspect:
        new_width = int(round(height * target_aspect))
        offset = (width - new_width) // 2
        return (left + offset, top, left + offset + new_width, bottom)
    new_height = int(round(width / target_aspect))
    offset = (height - new_height) // 2
    return (left, top + offset, right, top + offset + new_height)


def _trim_border_box(image) -> tuple[int, int, int, int] | None:
    gray = image.convert("L")
    width, height = gray.size
    if width < 20 or height < 20:
        return None
    step_x = max(1, width // 80)
    step_y = max(1, height // 45)
    edge_values: list[int] = []
    for x in range(0, width, step_x):
        edge_values.append(gray.getpixel((x, 0)))
        edge_values.append(gray.getpixel((x, height - 1)))
    for y in range(0, height, step_y):
        edge_values.append(gray.getpixel((0, y)))
        edge_values.append(gray.getpixel((width - 1, y)))
    edge_values.sort()
    border_value = edge_values[len(edge_values) // 2]

    xs: list[int] = []
    ys: list[int] = []
    threshold = 18
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            if abs(int(gray.getpixel((x, y))) - border_value) > threshold:
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return None
    left = max(0, min(xs) - step_x)
    right = min(width, max(xs) + step_x)
    top = max(0, min(ys) - step_y)
    bottom = min(height, max(ys) + step_y)
    if (right - left) * (bottom - top) < width * height * 0.25:
        return None
    return (left, top, right, bottom)


def _candidate_crop_boxes(
    image, *, target_aspect: float
) -> list[tuple[str, tuple[int, int, int, int]]]:
    width, height = image.size
    full = (0, 0, width, height)
    candidates: list[tuple[str, tuple[int, int, int, int]]] = [
        ("full_frame", full),
        ("center_aspect", _center_aspect_box(full, target_aspect)),
    ]
    for top_ratio in (0.06, 0.10, 0.14):
        bounds = (0, int(height * top_ratio), width, height)
        candidates.append(
            (
                f"center_aspect_without_top_{int(top_ratio * 100)}",
                _center_aspect_box(bounds, target_aspect),
            )
        )
    inset_bounds = (
        int(width * 0.04),
        int(height * 0.04),
        int(width * 0.96),
        int(height * 0.96),
    )
    candidates.append(
        ("inset_center_aspect", _center_aspect_box(inset_bounds, target_aspect))
    )
    trimmed = _trim_border_box(image)
    if trimmed is not None:
        candidates.append(("trimmed_border", trimmed))
        candidates.append(
            ("trimmed_border_aspect", _center_aspect_box(trimmed, target_aspect))
        )

    deduped: list[tuple[str, tuple[int, int, int, int]]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for label, box in candidates:
        left, top, right, bottom = box
        clean = (
            max(0, min(width - 1, left)),
            max(0, min(height - 1, top)),
            max(1, min(width, right)),
            max(1, min(height, bottom)),
        )
        if clean[2] <= clean[0] or clean[3] <= clean[1] or clean in seen:
            continue
        seen.add(clean)
        deduped.append((label, clean))
    return deduped


def _average_hash(image, *, hash_size: int = HASH_SIZE) -> tuple[int, ...]:
    gray = image.convert("L").resize((hash_size, hash_size))
    values = list(gray.getdata())
    average = sum(values) / len(values)
    return tuple(1 if value >= average else 0 for value in values)


def _thumbnail_values(image) -> tuple[int, ...]:
    gray = image.convert("L").resize(THUMBNAIL_SIZE)
    return tuple(int(value) for value in gray.getdata())


def _edge_values(image) -> tuple[int, ...]:
    try:
        from PIL import ImageFilter
    except ImportError:
        return ()
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES).resize(THUMBNAIL_SIZE)
    return tuple(int(value) for value in edges.getdata())


def _image_features(image) -> _ImageFeatures:
    return _ImageFeatures(
        mean_values=_thumbnail_values(image),
        hash_bits=_average_hash(image),
        edge_values=_edge_values(image),
    )


def _hash_similarity_from_bits(
    left_hash: Sequence[int],
    right_hash: Sequence[int],
) -> float:
    if not left_hash or not right_hash:
        return 0.0
    distance = sum(
        1 for left_bit, right_bit in zip(left_hash, right_hash) if left_bit != right_bit
    )
    return 1.0 - (distance / len(left_hash))


def _hash_similarity(left, right) -> float:
    return _hash_similarity_from_bits(_average_hash(left), _average_hash(right))


def _mean_abs_similarity_from_values(
    left_values: Sequence[int],
    right_values: Sequence[int],
) -> float:
    if not left_values:
        return 0.0
    total = sum(
        abs(left_value - right_value)
        for left_value, right_value in zip(left_values, right_values)
    )
    mean_delta = total / len(left_values)
    return max(0.0, 1.0 - (mean_delta / 255.0))


def _mean_abs_similarity(left, right) -> float:
    return _mean_abs_similarity_from_values(
        _thumbnail_values(left),
        _thumbnail_values(right),
    )


def _edge_similarity(left, right) -> float:
    left_edges = _edge_values(left)
    right_edges = _edge_values(right)
    if not left_edges or not right_edges:
        return 0.0
    return _mean_abs_similarity_from_values(left_edges, right_edges)


def _similarity_score_from_features(
    left: _ImageFeatures,
    right: _ImageFeatures,
) -> float:
    edge_score = (
        _mean_abs_similarity_from_values(left.edge_values, right.edge_values)
        if left.edge_values and right.edge_values
        else 0.0
    )
    score = (
        0.45 * _mean_abs_similarity_from_values(left.mean_values, right.mean_values)
        + 0.35 * _hash_similarity_from_bits(left.hash_bits, right.hash_bits)
        + 0.20 * edge_score
    )
    return round(max(0.0, min(1.0, score)), 4)


def _similarity_score(left, right) -> float:
    return _similarity_score_from_features(
        _image_features(left), _image_features(right)
    )


def _prepare_slide_renders(
    slide_renders: Sequence[_SlideRender],
) -> list[_PreparedSlideRender]:
    prepared: list[_PreparedSlideRender] = []
    for slide in slide_renders:
        slide_image = _load_image(slide.path)
        prepared.append(
            _PreparedSlideRender(
                slide_number=slide.slide_number,
                path=slide.path,
                target_aspect=slide_image.size[0] / max(1, slide_image.size[1]),
                features=_image_features(slide_image),
            )
        )
    return prepared


def _prepare_frame_crops(frame, *, target_aspect: float) -> list[_PreparedCrop]:
    crops: list[_PreparedCrop] = []
    for label, box in _candidate_crop_boxes(frame, target_aspect=target_aspect):
        crop = frame.crop(box)
        crops.append(
            _PreparedCrop(
                label=label,
                box=box,
                features=_image_features(crop),
            )
        )
    return crops


def _best_crop_score(
    frame,
    slide_image=None,
    *,
    slide_features: _ImageFeatures | None = None,
    target_aspect: float | None = None,
    prepared_crops: Sequence[_PreparedCrop] | None = None,
) -> _CropScore:
    if slide_features is None:
        if slide_image is None:
            raise SlideFrameMatchError("slide image or features are required")
        slide_features = _image_features(slide_image)
    if target_aspect is None:
        if slide_image is None:
            raise SlideFrameMatchError("target aspect is required")
        target_aspect = slide_image.size[0] / max(1, slide_image.size[1])
    crops = list(
        prepared_crops or _prepare_frame_crops(frame, target_aspect=target_aspect)
    )
    best = _CropScore(label="none", box=(0, 0, frame.size[0], frame.size[1]), score=0.0)
    for crop in crops:
        score = _similarity_score_from_features(crop.features, slide_features)
        if score > best.score:
            best = _CropScore(label=crop.label, box=crop.box, score=score)
    return best


def _confidence(best_score: float, second_score: float) -> str:
    gap = best_score - second_score
    if best_score >= MATCH_HIGH_SCORE and gap >= MATCH_HIGH_GAP:
        return "high"
    if best_score >= MATCH_MEDIUM_SCORE and gap >= MATCH_MEDIUM_GAP:
        return "medium"
    if best_score >= MATCH_LOW_SCORE:
        return "low"
    return "none"


def _match_status(confidence: str) -> str:
    if confidence in {"high", "medium"}:
        return "matched"
    if confidence == "low":
        return "low_confidence"
    return "no_match"


def _match_frame_to_slides(
    *,
    frame_path: Path,
    slide_renders: Sequence[_SlideRender | _PreparedSlideRender],
    base_dir: Path | None,
) -> dict[str, Any]:
    frame = _load_image(frame_path)
    prepared_slides = [
        (
            slide
            if isinstance(slide, _PreparedSlideRender)
            else _prepare_slide_renders([slide])[0]
        )
        for slide in slide_renders
    ]
    crop_cache: dict[float, list[_PreparedCrop]] = {}
    candidates: list[dict[str, Any]] = []
    for slide in prepared_slides:
        aspect_key = round(slide.target_aspect, 6)
        prepared_crops = crop_cache.get(aspect_key)
        if prepared_crops is None:
            prepared_crops = _prepare_frame_crops(
                frame, target_aspect=slide.target_aspect
            )
            crop_cache[aspect_key] = prepared_crops
        crop_score = _best_crop_score(
            frame,
            slide_features=slide.features,
            target_aspect=slide.target_aspect,
            prepared_crops=prepared_crops,
        )
        candidates.append(
            {
                "slide_number": slide.slide_number,
                "score": crop_score.score,
                "crop_label": crop_score.label,
                "crop_box": list(crop_score.box),
                "slide_render_path": _relative_path(slide.path, base_dir),
            }
        )
    candidates.sort(key=lambda item: float(item["score"]), reverse=True)
    best = candidates[0] if candidates else {}
    second_score = float(candidates[1]["score"]) if len(candidates) > 1 else 0.0
    best_score = float(best.get("score", 0.0))
    confidence = _confidence(best_score, second_score)
    status = _match_status(confidence)
    top_candidates = candidates[:5]
    note = (
        "Deterministic visual candidate match from cropped video frame to rendered slide images; "
        "use as slide-location evidence only, not as semantic edit interpretation."
        if status != "no_match"
        else "No rendered slide was similar enough to the video frame; inspect the raw frame/video manually."
    )
    return {
        "status": status,
        "best_slide_number": best.get("slide_number") if status != "no_match" else None,
        "confidence": confidence,
        "score": best_score,
        "score_gap": round(best_score - second_score, 4),
        "best_crop_label": best.get("crop_label") or "",
        "best_crop_box": best.get("crop_box") or [],
        "methods": [
            "candidate_crops",
            "mean_abs_similarity",
            "average_hash",
            "edge_similarity",
        ],
        "candidates": [
            {
                "slide_number": item["slide_number"],
                "score": item["score"],
                "crop_label": item["crop_label"],
                "crop_box": item["crop_box"],
                "slide_render_path": item["slide_render_path"],
            }
            for item in top_candidates
        ],
        "evidence_note": note,
    }


def _entry_slide_match(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for frame in frames:
        if not isinstance(frame, Mapping):
            continue
        raw_match = frame.get("slide_match")
        if isinstance(raw_match, dict) and raw_match.get("status") in {
            "matched",
            "low_confidence",
        }:
            matches.append(dict(raw_match))
    if not matches:
        return {
            "status": "no_match",
            "best_slide_number": None,
            "confidence": "none",
            "evidence_note": "No frame in this feedback unit matched a rendered slide.",
        }
    rank = {"high": 3, "medium": 2, "low": 1, "none": 0}
    matches.sort(
        key=lambda item: (
            rank.get(str(item.get("confidence")), 0),
            float(item.get("score", 0.0)),
        ),
        reverse=True,
    )
    best = matches[0]
    return {
        "status": best["status"],
        "best_slide_number": best.get("best_slide_number"),
        "confidence": best.get("confidence"),
        "score": best.get("score"),
        "score_gap": best.get("score_gap"),
        "evidence_note": best.get("evidence_note"),
    }


def _slide_matching_summary(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    for entry in entries:
        entry_match = entry.get("slide_match")
        if not isinstance(entry_match, Mapping):
            continue
        status = str(entry_match.get("status", "unknown"))
        confidence = str(entry_match.get("confidence", "none"))
        status_counts[status] = status_counts.get(status, 0) + 1
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1
    return {
        "entry_count": len(entries),
        "matched_entries": status_counts.get("matched", 0),
        "low_confidence_entries": status_counts.get("low_confidence", 0),
        "no_match_entries": status_counts.get("no_match", 0),
        "status_counts": status_counts,
        "confidence_counts": confidence_counts,
    }


def _attach_skip(
    payload: dict[str, Any], *, reason: str, now: datetime | None
) -> dict[str, Any]:
    payload["slide_matching"] = {
        "status": "skipped",
        "created_at": _now_iso(now),
        "reason": reason,
        "deterministic_reason": (
            "Slide matching is a mechanical visual candidate search; semantic deck "
            "interpretation remains Clara/Codex work."
        ),
    }
    return payload


def match_feedback_timeline_to_deck_payload(
    *,
    feedback_timeline: Mapping[str, Any],
    deck_path: Path,
    deck_snapshot_path: Path,
    base_dir: Path | None = None,
    output_path: Path | None = None,
    slide_render_dir: Path | None = None,
    soffice_path: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Attach conservative frame-to-slide candidates to a feedback timeline.

    Deterministic matching is justified here because it is limited to mechanical
    visual similarity between extracted frames and rendered slide images. It
    creates candidates and confidence labels; it does not decide what the
    partner meant or which deck edit should be made.
    """

    if not deck_path.is_file():
        raise SlideFrameMatchError(f"deck file is missing: {deck_path}")
    if not deck_snapshot_path.is_file():
        raise SlideFrameMatchError(f"deck snapshot is missing: {deck_snapshot_path}")
    payload = json.loads(json.dumps(feedback_timeline))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise SlideFrameMatchError("feedback timeline entries must be a list")
    render_dir = (
        slide_render_dir
        if slide_render_dir is not None
        else (output_path.parent if output_path else deck_snapshot_path.parent)
        / "slide_renders"
    )
    snapshot = _read_json(deck_snapshot_path)
    slide_numbers = {
        slide.get("slide_number")
        for slide in snapshot.get("slides", [])
        if isinstance(slide, Mapping)
    }
    slide_numbers = {number for number in slide_numbers if isinstance(number, int)}
    try:
        slide_renders = _render_deck_slides(
            deck_path,
            render_dir,
            soffice_path=soffice_path,
            expected_slide_numbers=slide_numbers,
        )
    except SlideFrameMatchError as error:
        return _attach_skip(payload, reason=str(error), now=now)
    slide_renders = [
        slide for slide in slide_renders if slide.slide_number in slide_numbers
    ]
    if not slide_renders:
        return _attach_skip(
            payload,
            reason="no rendered slides matched deck_snapshot slide numbers",
            now=now,
        )
    prepared_slide_renders = _prepare_slide_renders(slide_renders)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        frames = entry.get("frames", [])
        if not isinstance(frames, list):
            entry["slide_match"] = _entry_slide_match([])
            continue
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            if frame.get("status") != "extracted":
                continue
            frame_path = _resolve_path(str(frame.get("path", "")), base_dir=base_dir)
            if frame_path is None:
                frame["slide_match"] = {
                    "status": "frame_missing",
                    "best_slide_number": None,
                    "confidence": "none",
                    "evidence_note": "Frame path was missing or unreadable.",
                }
                continue
            try:
                frame["slide_match"] = _match_frame_to_slides(
                    frame_path=frame_path,
                    slide_renders=prepared_slide_renders,
                    base_dir=base_dir,
                )
            except SlideFrameMatchError as error:
                frame["slide_match"] = {
                    "status": "error",
                    "best_slide_number": None,
                    "confidence": "none",
                    "evidence_note": str(error),
                }
        entry["slide_match"] = _entry_slide_match(
            [frame for frame in frames if isinstance(frame, Mapping)]
        )

    payload["slide_matching"] = {
        "status": "complete",
        "created_at": _now_iso(now),
        "method": "cropped_frame_to_rendered_slide_visual_similarity",
        "deck_path": _relative_path(deck_path, base_dir),
        "deck_snapshot_path": _relative_path(deck_snapshot_path, base_dir),
        "slide_render_dir": _relative_path(render_dir, base_dir),
        "slide_count": len(slide_renders),
        "thresholds": {
            "high_score": MATCH_HIGH_SCORE,
            "medium_score": MATCH_MEDIUM_SCORE,
            "low_score": MATCH_LOW_SCORE,
            "high_gap": MATCH_HIGH_GAP,
            "medium_gap": MATCH_MEDIUM_GAP,
        },
        "deterministic_reason": (
            "The matcher performs mechanical visual comparison of extracted video "
            "frames against rendered slide images using multiple crop candidates. "
            "It outputs slide candidates only; semantic interpretation remains "
            "Clara/Codex work."
        ),
        "summary": _slide_matching_summary(
            [entry for entry in entries if isinstance(entry, Mapping)]
        ),
    }
    return payload


def match_feedback_timeline_to_deck(
    *,
    feedback_timeline_path: Path,
    deck_path: Path,
    deck_snapshot_path: Path,
    base_dir: Path | None = None,
    output_path: Path | None = None,
    slide_render_dir: Path | None = None,
    soffice_path: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    timeline = _read_json(feedback_timeline_path)
    target = output_path or feedback_timeline_path
    payload = match_feedback_timeline_to_deck_payload(
        feedback_timeline=timeline,
        deck_path=deck_path,
        deck_snapshot_path=deck_snapshot_path,
        base_dir=base_dir,
        output_path=target,
        slide_render_dir=slide_render_dir,
        soffice_path=soffice_path,
        now=now,
    )
    _write_json(target, payload)
    return payload


def main() -> int:
    """Run slide matching for a Clara feedback timeline."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feedback_timeline", type=Path)
    parser.add_argument("deck", type=Path)
    parser.add_argument("deck_snapshot", type=Path)
    parser.add_argument("--base-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--slide-render-dir", type=Path)
    parser.add_argument("--soffice-path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    payload = match_feedback_timeline_to_deck(
        feedback_timeline_path=args.feedback_timeline,
        deck_path=args.deck,
        deck_snapshot_path=args.deck_snapshot,
        base_dir=args.base_dir,
        output_path=args.output,
        slide_render_dir=args.slide_render_dir,
        soffice_path=args.soffice_path,
    )
    status = payload.get("slide_matching", {}).get("status")
    LOGGER.info("Slide matching status: %s", status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
