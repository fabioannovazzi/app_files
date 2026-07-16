from __future__ import annotations

from html import escape
from pathlib import Path

from .html_normalizer import update_slide_document

__all__ = ["build_image_only_slide_content"]

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
