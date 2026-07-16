from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable

from PIL import Image

__all__ = [
    "SelectionRectImg",
    "SelectionRectPdf",
    "expand_and_clamp",
    "image_point_to_pdf_point",
    "image_rect_to_pdf_rect",
    "pdf_point_rotate",
    "snap_to_ink",
    "view_point_to_image_point",
]


@dataclass(frozen=True)
class SelectionRectImg:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class SelectionRectPdf:
    x: float
    y: float
    w: float
    h: float


def view_point_to_image_point(
    x_view: float,
    y_view: float,
    *,
    zoom: float,
    pan_x: float,
    pan_y: float,
    img_w: float,
    img_h: float,
) -> tuple[float, float]:
    """Map a view-space point to image-space coordinates."""

    x_img = (x_view - pan_x) / zoom
    y_img = (y_view - pan_y) / zoom
    return _clamp(x_img, 0.0, img_w), _clamp(y_img, 0.0, img_h)


def image_point_to_pdf_point(
    x_px: float,
    y_px: float,
    *,
    img_w: float,
    img_h: float,
    crop_w: float,
    crop_h: float,
    crop_x0: float,
    crop_y0: float,
) -> tuple[float, float]:
    """Map a single image point (top-left origin) into PDF coordinates."""

    x_pt = crop_x0 + x_px * (crop_w / img_w)
    y_pt = crop_y0 + (img_h - y_px) * (crop_h / img_h)
    return x_pt, y_pt


def image_rect_to_pdf_rect(
    rect: SelectionRectImg,
    *,
    img_w: float,
    img_h: float,
    crop_w: float,
    crop_h: float,
    crop_x0: float,
    crop_y0: float,
    rotation: int,
) -> SelectionRectPdf:
    """Convert an image-space rectangle to a PDF-space rectangle."""

    scale_x = crop_w / img_w
    scale_y = crop_h / img_h
    x_pt = crop_x0 + rect.x * scale_x
    y_pt = crop_y0 + (img_h - (rect.y + rect.h)) * scale_y
    w_pt = rect.w * scale_x
    h_pt = rect.h * scale_y
    if rotation == 0:
        return SelectionRectPdf(x=x_pt, y=y_pt, w=w_pt, h=h_pt)

    corners = [
        (x_pt, y_pt),
        (x_pt + w_pt, y_pt),
        (x_pt + w_pt, y_pt + h_pt),
        (x_pt, y_pt + h_pt),
    ]
    rotated = [pdf_point_rotate(x, y, rotation, crop_w, crop_h, crop_x0, crop_y0) for x, y in corners]
    xs = [pt[0] for pt in rotated]
    ys = [pt[1] for pt in rotated]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    return SelectionRectPdf(x=min_x, y=min_y, w=max_x - min_x, h=max_y - min_y)


def pdf_point_rotate(
    x_pt: float,
    y_pt: float,
    rotation: int,
    crop_w: float,
    crop_h: float,
    crop_x0: float,
    crop_y0: float,
) -> tuple[float, float]:
    """Rotate a PDF point around the crop box origin."""

    x_rel = x_pt - crop_x0
    y_rel = y_pt - crop_y0
    if rotation == 90:
        return crop_x0 + (crop_h - y_rel), crop_y0 + x_rel
    if rotation == 180:
        return crop_x0 + (crop_w - x_rel), crop_y0 + (crop_h - y_rel)
    if rotation == 270:
        return crop_x0 + y_rel, crop_y0 + (crop_w - x_rel)
    return x_pt, y_pt


def expand_and_clamp(
    rect: SelectionRectImg,
    pad_px: float,
    *,
    img_w: float,
    img_h: float,
) -> SelectionRectImg:
    """Expand a rectangle by padding and clamp within image bounds."""

    x = _clamp(rect.x - pad_px, 0.0, img_w)
    y = _clamp(rect.y - pad_px, 0.0, img_h)
    max_w = max(0.0, img_w - x)
    max_h = max(0.0, img_h - y)
    w = _clamp(rect.w + pad_px * 2, 0.0, max_w)
    h = _clamp(rect.h + pad_px * 2, 0.0, max_h)
    return SelectionRectImg(x=x, y=y, w=w, h=h)


def snap_to_ink(image: Image.Image, rect: SelectionRectImg) -> SelectionRectImg:
    """Tighten a rectangle around foreground pixels inside the selection."""

    if rect.w <= 0 or rect.h <= 0:
        return rect
    rgb = image.convert("RGB")
    img_w, img_h = rgb.size
    ring = _collect_ring_samples(rgb, rect)
    background = _median_color(ring)
    crop = rgb.crop(
        (
            int(rect.x),
            int(rect.y),
            int(rect.x + rect.w),
            int(rect.y + rect.h),
        )
    )
    pixels = list(crop.getdata())
    distances = [_color_distance(pixel, background) for pixel in pixels]
    threshold = _otsu_threshold(distances)
    mask = [distance > threshold for distance in distances]
    if not any(mask):
        return rect
    bbox = _mask_bbox(mask, int(rect.w), int(rect.h))
    if bbox is None:
        return rect
    min_x, min_y, max_x, max_y = bbox
    tightened = SelectionRectImg(
        x=_clamp(rect.x + min_x, 0.0, img_w),
        y=_clamp(rect.y + min_y, 0.0, img_h),
        w=_clamp(max_x - min_x, 0.0, img_w),
        h=_clamp(max_y - min_y, 0.0, img_h),
    )
    return tightened


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _collect_ring_samples(image: Image.Image, rect: SelectionRectImg, ring_px: int = 4) -> Iterable[tuple[int, int, int]]:
    left = max(0, int(rect.x - ring_px))
    right = min(image.width, int(rect.x + rect.w + ring_px))
    top = max(0, int(rect.y - ring_px))
    bottom = min(image.height, int(rect.y + rect.h + ring_px))
    samples = []
    if top < rect.y:
        samples.extend(image.crop((left, top, right, int(rect.y))).getdata())
    if bottom > rect.y + rect.h:
        samples.extend(image.crop((left, int(rect.y + rect.h), right, bottom)).getdata())
    if left < rect.x:
        samples.extend(image.crop((left, int(rect.y), int(rect.x), int(rect.y + rect.h))).getdata())
    if right > rect.x + rect.w:
        samples.extend(image.crop((int(rect.x + rect.w), int(rect.y), right, int(rect.y + rect.h))).getdata())
    return samples or [(255, 255, 255)]


def _median_color(samples: Iterable[tuple[int, int, int]]) -> tuple[int, int, int]:
    reds = [pixel[0] for pixel in samples]
    greens = [pixel[1] for pixel in samples]
    blues = [pixel[2] for pixel in samples]
    return int(median(reds)), int(median(greens)), int(median(blues))


def _color_distance(pixel: tuple[int, int, int], background: tuple[int, int, int]) -> int:
    return int(((pixel[0] - background[0]) ** 2 + (pixel[1] - background[1]) ** 2 + (pixel[2] - background[2]) ** 2) ** 0.5)


def _otsu_threshold(distances: Iterable[int]) -> int:
    hist = [0] * 256
    total = 0
    for distance in distances:
        value = min(255, max(0, distance))
        hist[value] += 1
        total += 1
    sum_total = sum(idx * count for idx, count in enumerate(hist))
    sum_b = 0
    weight_b = 0
    max_variance = 0
    threshold = 0
    for idx, count in enumerate(hist):
        weight_b += count
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += idx * count
        mean_b = sum_b / weight_b
        mean_f = (sum_total - sum_b) / weight_f
        variance = weight_b * weight_f * (mean_b - mean_f) ** 2
        if variance > max_variance:
            max_variance = variance
            threshold = idx
    return threshold


def _mask_bbox(mask: list[bool], width: int, height: int) -> tuple[int, int, int, int] | None:
    xs = []
    ys = []
    for idx, value in enumerate(mask):
        if not value:
            continue
        x = idx % width
        y = idx // width
        xs.append(x)
        ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1
