from __future__ import annotations

import hashlib
import io
import math
import os
from html import escape
from pathlib import Path

import fitz  # type: ignore[import-not-found]
from PIL import Image, ImageDraw

from .errors import InvalidDeckError
from .html_normalizer import update_slide_document
from .models import Deck, Slide
from .storage import DeckStorage

__all__ = ["build_image_only_slide_content", "render_pdf_deck"]

_PDF_ALLOWED_DIMENSIONS_PT: tuple[tuple[float, float], ...] = ((1376.0, 768.0),)
_PDF_REQUIRED_DIMENSION_TOLERANCE_PT = 0.5
try:
    _PDF_IMPORT_RASTER_SCALE = max(
        1.0, float(os.getenv("SLIDES_PDF_IMPORT_RASTER_SCALE", "2"))
    )
except ValueError:
    _PDF_IMPORT_RASTER_SCALE = 2.0

_IMAGE_STYLE = (
    "max-width: 100%; "
    "max-height: 100%; "
    "object-fit: contain; "
    "display: block; "
    "margin: 0 auto;"
)


def build_image_only_slide_content(
    deck_id: str,
    image_path: Path,
    *,
    page_index: int,
    crop_w_pt: float,
    crop_h_pt: float,
    crop_x0_pt: float,
    crop_y0_pt: float,
    rotation_deg: int,
) -> tuple[str, str, str]:
    """Return title/body/full HTML for a PDF page rendered as an image slide."""

    normalized_path = _normalize_asset_path(image_path)
    image_src = f"/slides/deck/{deck_id}/assets/{normalized_path.as_posix()}"
    title_html = ""
    alt_text = f"Slide image {page_index + 1}"
    image_html = (
        f'<img src="{escape(image_src)}" '
        f'alt="{escape(alt_text)}" '
        f'data-pdf-crop-w-pt="{crop_w_pt}" '
        f'data-pdf-crop-h-pt="{crop_h_pt}" '
        f'data-pdf-crop-x0-pt="{crop_x0_pt}" '
        f'data-pdf-crop-y0-pt="{crop_y0_pt}" '
        f'data-pdf-rotation="{rotation_deg}" '
        f'style="{_IMAGE_STYLE}" />'
    )
    body_html = (
        '<div style="position: relative; width: 100%; height: 100%;">'
        f"{image_html}"
        "</div>"
    )
    full_html = update_slide_document(
        "",
        title_html=title_html,
        body_html=body_html,
        notes_html="",
        source_html="",
    )
    return title_html, body_html, full_html


def _normalize_asset_path(asset_path: Path) -> Path:
    parts = [part for part in asset_path.parts if part not in {"", ".", ".."}]
    if not parts:
        return Path()
    normalized = Path(*parts)
    if normalized.is_absolute():
        normalized = Path(*normalized.parts[1:])
    if normalized.parts[:1] == ("assets",):
        normalized = Path(*normalized.parts[1:])
    return normalized


def _cover_notebooklm_logo(image: Image.Image) -> None:
    """Cover the NotebookLM logo area with a representative background color."""
    if not image.size:
        return
    width, height = image.size
    if width <= 0 or height <= 0:
        return
    cover_width = max(200, int(math.floor(width * 0.10)))
    cover_height = max(30, int(math.floor(height * 0.03)))
    x0 = max(0, width - cover_width)
    y0 = max(0, height - cover_height)
    x1 = width
    y1 = height
    if x1 <= x0 or y1 <= y0:
        return
    sampling_image = image if image.mode == "RGB" else image.convert("RGB")

    samples: list[tuple[int, int, int]] = []
    filtered_samples: list[tuple[int, int, int]] = []
    for py in range(y0, y1):
        for px in range(x0, x1):
            pixel = sampling_image.getpixel((px, py))
            samples.append(pixel)
            if max(pixel) > 20:
                filtered_samples.append(pixel)

    fill_color = (255, 255, 255)
    sample_set = filtered_samples if filtered_samples else samples
    if sample_set:
        channel_values = [
            sorted(pixel[idx] for pixel in sample_set) for idx in range(3)
        ]
        mid = len(sample_set) // 2
        fill_color = tuple(values[mid] for values in channel_values)
    draw = ImageDraw.Draw(image)
    draw.rectangle([x0, y0, x1, y1], fill=fill_color)


def render_pdf_deck(
    deck_id: str,
    deck_path: Path,
    pdf_bytes: bytes,
    storage: DeckStorage,
    *,
    prompt_style: str,
    owner_email: str | None,
    shared_with: list[str],
) -> None:
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise InvalidDeckError("Uploaded file is not a valid PDF.") from exc
    pdf_path = deck_path / "source.pdf"
    pdf_path.write_bytes(pdf_bytes)
    with doc:
        if doc.page_count == 0:
            raise InvalidDeckError("Uploaded PDF has no pages.")
        selected_dimension: tuple[float, float] | None = None
        for page_number in range(doc.page_count):
            page = doc.load_page(page_number)
            crop_box = page.cropbox
            width_pt = float(crop_box.width)
            height_pt = float(crop_box.height)
            matched_dimension: tuple[float, float] | None = next(
                (
                    (allowed_w, allowed_h)
                    for allowed_w, allowed_h in _PDF_ALLOWED_DIMENSIONS_PT
                    if (
                        abs(width_pt - allowed_w)
                        <= _PDF_REQUIRED_DIMENSION_TOLERANCE_PT
                        and abs(height_pt - allowed_h)
                        <= _PDF_REQUIRED_DIMENSION_TOLERANCE_PT
                    )
                ),
                None,
            )
            if matched_dimension is None:
                allowed_sizes_text = " or ".join(
                    f"{int(width)}x{int(height)}"
                    for width, height in _PDF_ALLOWED_DIMENSIONS_PT
                )
                raise InvalidDeckError(
                    "Uploaded PDF must use NotebookLM slide pages "
                    f"({allowed_sizes_text}). "
                    f"Page {page_number + 1} is "
                    f"{width_pt:.1f}x{height_pt:.1f}."
                )
            if selected_dimension is None:
                selected_dimension = matched_dimension
            elif matched_dimension != selected_dimension:
                raise InvalidDeckError(
                    "Uploaded PDF pages must all have the same dimensions. "
                    f"Page 1 matched {int(selected_dimension[0])}x"
                    f"{int(selected_dimension[1])}, but page {page_number + 1} is "
                    f"{width_pt:.1f}x{height_pt:.1f}."
                )
        slides: list[Slide] = []
        raster_matrix = fitz.Matrix(_PDF_IMPORT_RASTER_SCALE, _PDF_IMPORT_RASTER_SCALE)
        for page_number in range(doc.page_count):
            page = doc.load_page(page_number)
            pix = page.get_pixmap(matrix=raster_matrix, alpha=True)
            crop_box = page.cropbox
            image = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
            flattened = Image.new("RGB", image.size, (255, 255, 255))
            flattened.paste(image, mask=image.split()[-1])
            _cover_notebooklm_logo(flattened)
            buffer = io.BytesIO()
            flattened.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            image_name = f"{image_hash}.png"
            image_path = assets_path / image_name
            image_path.write_bytes(image_bytes)
            slide_id = f"slide-{page_number + 1:03d}.html"
            title_html, body_html, full_html = build_image_only_slide_content(
                deck_id,
                Path(image_name),
                page_index=page_number,
                crop_w_pt=crop_box.width,
                crop_h_pt=crop_box.height,
                crop_x0_pt=crop_box.x0,
                crop_y0_pt=crop_box.y0,
                rotation_deg=page.rotation,
            )
            slides.append(
                Slide(
                    id=slide_id,
                    title_html=title_html,
                    body_html=body_html,
                    full_html=full_html,
                )
            )
    deck = Deck(
        deck_id=deck_id,
        prompt_style=prompt_style,
        owner_email=owner_email,
        shared_with=shared_with,
        slides=slides,
    )
    storage.save_deck(deck)
