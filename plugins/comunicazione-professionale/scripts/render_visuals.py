#!/usr/bin/env python3
"""Render accepted studio-formatted visual and circular artifacts."""

from __future__ import annotations

import argparse
import html
import logging
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont as FontToolsTTFont
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
)
from workflow_core import (
    PLUGIN_ROOT,
    atomic_write_json,
    atomic_write_text,
    canonical_digest,
    creative_token_application,
    file_digest,
    load_json,
    recompute_contribution_digest,
    require_accepted_reviews,
    utc_now,
    validate_input_integrity,
    verify_creative_direction_decision,
    workflow_lock,
)

__all__ = ["render_visuals", "main"]

LOGGER = logging.getLogger(__name__)
WIDTH = 1080
HEIGHT = 1350
MARGIN = 92
FONT_ROOT = PLUGIN_ROOT / "assets" / "fonts"
FONT_PATHS = {
    "regular": FONT_ROOT / "InstrumentSans-Regular.ttf",
    "semibold": FONT_ROOT / "InstrumentSans-SemiBold.ttf",
    "bold": FONT_ROOT / "InstrumentSans-Bold.ttf",
}
INTERNAL_ID_PATTERN = re.compile(r"\b(?:SRC|HIST|CLAIM)-[A-Za-z0-9_.-]+\b")
SOURCE_HEADINGS = {
    "en": "Sources",
    "fr": "Sources",
    "de": "Quellen",
    "es": "Fuentes",
}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATHS[weight]), size=size)


@lru_cache(maxsize=8)
def _font_codepoints(path: str) -> frozenset[int]:
    """Return the exact cmap for one bundled font asset."""

    font = FontToolsTTFont(path, lazy=True)
    try:
        return frozenset((font.getBestCmap() or {}).keys())
    finally:
        font.close()


def _require_supported_text(text: str, *, weight: str, label: str) -> None:
    """Reject missing glyphs before any partial visual files are written."""

    supported = _font_codepoints(str(FONT_PATHS[weight]))
    missing = sorted(
        {
            character
            for character in text
            if not character.isspace() and ord(character) not in supported
        },
        key=ord,
    )
    if missing:
        details = ", ".join(f"U+{ord(char):04X} {char!r}" for char in missing)
        raise ValueError(f"{label} uses unsupported font glyphs: {details}")


def _identity_visible(placement: str, *, index: int, total: int) -> bool:
    """Apply the accepted Studio identity-placement contract exactly."""

    if placement == "every_slide":
        return True
    if placement == "cover_and_close":
        return index in {1, total}
    if placement == "close_only":
        return index == total
    raise ValueError(f"Unsupported carousel identity placement: {placement}")


def _validate_visual_text_contract(
    slides: list[dict[str, Any]],
    *,
    studio_name: str,
    identity_placement: str,
) -> None:
    """Enforce mechanical public-surface integrity before rendering.

    These checks are deterministic because exact identifier leakage, duplicate
    identity strings, and font coverage are mechanically verifiable. Editorial
    usefulness and overlap with the post remain model-led review questions.
    """

    total = len(slides)
    for index, slide in enumerate(slides, start=1):
        fields = [
            ("eyebrow", slide["eyebrow"], "semibold"),
            ("title", slide["title"], "bold"),
            ("body", slide["body"], "regular"),
            ("highlight", slide["highlight"], "bold"),
            ("source note", slide["source_note"], "regular"),
            *[("bullet", bullet, "regular") for bullet in slide["bullets"]],
        ]
        for field, value, weight in fields:
            if INTERNAL_ID_PATTERN.search(value):
                raise ValueError(
                    f"Visual slide {index} {field} exposes an internal identifier"
                )
            _require_supported_text(
                value,
                weight=weight,
                label=f"Visual slide {index} {field}",
            )
        show_identity = _identity_visible(
            identity_placement,
            index=index,
            total=total,
        )
        identity_mentions = int(show_identity) + sum(
            value.casefold().count(studio_name.casefold())
            for _, value, _ in fields
            if studio_name
        )
        if identity_mentions > 1:
            raise ValueError(
                f"Visual slide {index} repeats Studio identity {identity_mentions} times"
            )
        if show_identity:
            _require_supported_text(
                studio_name,
                weight="semibold",
                label=f"Visual slide {index} Studio identity",
            )


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int
) -> list[str]:
    def split_word(word: str) -> list[str]:
        pieces: list[str] = []
        current = ""
        for character in word:
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > width:
                pieces.append(current)
                current = character
            else:
                current = candidate
            if draw.textlength(current, font=font) > width:
                raise ValueError("One glyph exceeds the visual text width")
        if current:
            pieces.append(current)
        return pieces

    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        words = [
            piece
            for word in paragraph.split()
            for piece in (
                [word]
                if draw.textlength(word, font=font) <= width
                else split_word(word)
            )
        ]
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    if any(draw.textlength(line, font=font) > width for line in lines):
        raise ValueError("Wrapped visual line exceeds the safe width")
    return lines


def _fit_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    weight: str,
    max_width: int,
    max_height: int,
    start_size: int,
    min_size: int,
    spacing_ratio: float = 0.18,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    for size in range(start_size, min_size - 1, -2):
        font = _font(weight, size)
        lines = _wrap(draw, text, font, max_width)
        spacing = max(4, int(size * spacing_ratio))
        line_height = int(size * 1.14)
        height = len(lines) * line_height + max(0, len(lines) - 1) * spacing
        if height <= max_height:
            return font, lines, spacing
    raise ValueError("Text cannot fit visual contract without clipping")


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[str],
    *,
    font: ImageFont.FreeTypeFont,
    fill: str,
    spacing: int,
) -> int:
    x, y = xy
    line_height = int(font.size * 1.14)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height + spacing
    return y


def _logo_path(source_register: dict[str, Any]) -> Path | None:
    logo = source_register.get("brand_logo")
    if not isinstance(logo, dict):
        return None
    path = Path(str(logo.get("snapshot_path", "")))
    return path if path.is_file() else None


def _draw_logo(
    image: Image.Image,
    path: Path | None,
    *,
    x: int,
    y: int,
    max_width: int,
    max_height: int,
) -> None:
    if path is None:
        return
    with Image.open(path) as original:
        logo = original.convert("RGBA")
        logo.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        image.alpha_composite(logo, (x, y))


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    weight: str,
    start_size: int,
    min_size: int,
    fill: str,
    measured_lines: list[tuple[str, ImageFont.FreeTypeFont]],
    spacing_ratio: float = 0.18,
) -> int:
    """Fit and draw one exact text field, returning its lower edge."""

    font, lines, spacing = _fit_lines(
        draw,
        text,
        weight=weight,
        max_width=width,
        max_height=height,
        start_size=start_size,
        min_size=min_size,
        spacing_ratio=spacing_ratio,
    )
    bottom = _draw_lines(
        draw,
        (x, y),
        lines,
        font=font,
        fill=fill,
        spacing=spacing,
    )
    measured_lines.extend((line, font) for line in lines)
    return bottom


def _draw_header(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    *,
    index: int,
    total: int,
    primary: str,
    accent: str,
    inverted: bool = False,
) -> None:
    """Draw the restrained carousel navigation header."""

    header_color = "#FFFFFF" if inverted else primary
    counter = f"{index:02d}/{total:02d}"
    counter_font = _font("regular", 23)
    counter_width = draw.textlength(counter, font=counter_font)
    eyebrow_width = WIDTH - 2 * MARGIN - int(counter_width) - 38
    eyebrow_font = None
    for size in range(25, 17, -1):
        candidate = _font("semibold", size)
        if draw.textlength(slide["eyebrow"].upper(), font=candidate) <= eyebrow_width:
            eyebrow_font = candidate
            break
    if eyebrow_font is None:
        raise ValueError("Carousel eyebrow cannot fit navigation header")
    draw.text(
        (MARGIN, 54),
        slide["eyebrow"].upper(),
        font=eyebrow_font,
        fill=header_color,
    )
    draw.text(
        (WIDTH - MARGIN - counter_width, 56),
        counter,
        font=counter_font,
        fill=header_color,
    )
    draw.rectangle((MARGIN, 104, WIDTH - MARGIN, 110), fill=accent)


def _draw_indexed_rows(
    draw: ImageDraw.ImageDraw,
    bullets: list[str],
    *,
    x: int,
    y: int,
    width: int,
    max_bottom: int,
    primary: str,
    accent: str,
    text: str,
    measured_lines: list[tuple[str, ImageFont.FreeTypeFont]],
    boxed: bool = False,
    row_marker: str = "numeral",
) -> int:
    """Draw exact bullet copy as an editorial register."""

    if not bullets:
        return y
    available = max_bottom - y
    row_height = available // len(bullets)
    if row_height < 92:
        raise ValueError("Indexed rows cannot fit visual contract without clipping")
    number_font = _font("semibold", 22)
    for row_index, bullet in enumerate(bullets, start=1):
        row_top = y + (row_index - 1) * row_height
        row_bottom = row_top + row_height - 12
        if boxed:
            draw.rectangle(
                (x, row_top, x + width, row_bottom),
                outline=primary,
                width=2,
            )
            number_x = x + 24
            copy_x = x + 88
            copy_width = width - 116
        else:
            draw.rectangle((x, row_top, x + width, row_top + 2), fill=primary)
            number_x = x
            copy_x = x + 72
            copy_width = width - 72
        marker_top = row_top + 25
        if row_marker == "numeral":
            draw.text(
                (number_x, marker_top),
                f"{row_index:02d}",
                font=number_font,
                fill=accent,
            )
        elif row_marker == "circle":
            draw.ellipse(
                (number_x, marker_top, number_x + 30, marker_top + 30),
                fill=accent,
            )
        elif row_marker == "bar":
            draw.rectangle(
                (number_x, marker_top, number_x + 9, marker_top + 42),
                fill=accent,
            )
        else:
            raise ValueError(
                f"Unsupported Creative Production row marker: {row_marker}"
            )
        _draw_text_block(
            draw,
            bullet,
            x=copy_x,
            y=row_top + 22,
            width=copy_width,
            height=row_height - 40,
            weight="regular",
            start_size=30,
            min_size=22,
            fill=text,
            measured_lines=measured_lines,
            spacing_ratio=0.10,
        )
    return y + len(bullets) * row_height


def _draw_dual_gate(
    draw: ImageDraw.ImageDraw,
    bullets: list[str],
    *,
    y: int,
    max_bottom: int,
    primary: str,
    accent: str,
    text: str,
    measured_lines: list[tuple[str, ImageFont.FreeTypeFont]],
    row_marker: str = "numeral",
) -> int:
    """Draw two exact conditions as a connected, two-gate sequence."""

    if len(bullets) != 2:
        raise ValueError("dual_gate layout requires exactly two bullet fields")
    line_x = MARGIN + 34
    row_height = (max_bottom - y) // 2
    if row_height < 145:
        raise ValueError("dual_gate layout cannot fit without clipping")
    draw.rectangle((line_x - 1, y + 44, line_x + 1, max_bottom - 44), fill=primary)
    number_font = _font("semibold", 21)
    for row_index, bullet in enumerate(bullets, start=1):
        row_top = y + (row_index - 1) * row_height
        label = f"{row_index:02d}"
        if row_marker == "circle":
            draw.ellipse(
                (line_x - 24, row_top + 18, line_x + 24, row_top + 66),
                fill=accent,
            )
            label_width = draw.textlength(label, font=number_font)
            draw.text(
                (line_x - label_width / 2, row_top + 28),
                label,
                font=number_font,
                fill="#FFFFFF",
            )
        elif row_marker == "bar":
            draw.rectangle(
                (line_x - 8, row_top + 18, line_x + 8, row_top + 66),
                fill=accent,
            )
        elif row_marker == "numeral":
            label_width = draw.textlength(label, font=number_font)
            draw.text(
                (line_x - label_width / 2, row_top + 28),
                label,
                font=number_font,
                fill=accent,
            )
        else:
            raise ValueError(
                f"Unsupported Creative Production row marker: {row_marker}"
            )
        _draw_text_block(
            draw,
            bullet,
            x=MARGIN + 100,
            y=row_top + 12,
            width=WIDTH - 2 * MARGIN - 100,
            height=row_height - 28,
            weight="regular",
            start_size=31,
            min_size=23,
            fill=text,
            measured_lines=measured_lines,
            spacing_ratio=0.10,
        )
    return y + 2 * row_height


def _draw_route_comparison(
    draw: ImageDraw.ImageDraw,
    bullets: list[str],
    *,
    y: int,
    max_bottom: int,
    primary: str,
    accent: str,
    text: str,
    measured_lines: list[tuple[str, ImageFont.FreeTypeFont]],
    row_marker: str = "numeral",
) -> int:
    """Draw two exact routes side by side with an optional shared conclusion."""

    if len(bullets) not in {2, 3}:
        raise ValueError("route_comparison layout requires two or three bullet fields")
    gutter = 36
    column_width = (WIDTH - 2 * MARGIN - gutter) // 2
    comparison_bottom = max_bottom - (150 if len(bullets) == 3 else 0)
    if comparison_bottom - y < 220:
        raise ValueError("route_comparison layout cannot fit without clipping")
    for column_index, bullet in enumerate(bullets[:2]):
        column_x = MARGIN + column_index * (column_width + gutter)
        draw.rectangle((column_x, y, column_x + column_width, y + 8), fill=accent)
        marker_y = y + 28
        if row_marker == "numeral":
            draw.text(
                (column_x, marker_y),
                f"0{column_index + 1}",
                font=_font("semibold", 22),
                fill=primary,
            )
        elif row_marker == "circle":
            draw.ellipse(
                (column_x, marker_y, column_x + 30, marker_y + 30),
                fill=accent,
            )
        elif row_marker == "bar":
            draw.rectangle(
                (column_x, marker_y, column_x + 9, marker_y + 42),
                fill=accent,
            )
        else:
            raise ValueError(
                f"Unsupported Creative Production row marker: {row_marker}"
            )
        _draw_text_block(
            draw,
            bullet,
            x=column_x,
            y=y + 82,
            width=column_width,
            height=comparison_bottom - y - 100,
            weight="regular",
            start_size=31,
            min_size=22,
            fill=text,
            measured_lines=measured_lines,
            spacing_ratio=0.10,
        )
    draw.rectangle(
        (
            MARGIN + column_width + gutter // 2,
            y,
            MARGIN + column_width + gutter // 2 + 2,
            comparison_bottom,
        ),
        fill=primary,
    )
    if len(bullets) == 3:
        draw.rectangle(
            (MARGIN, comparison_bottom + 22, WIDTH - MARGIN, comparison_bottom + 25),
            fill=primary,
        )
        _draw_text_block(
            draw,
            bullets[2],
            x=MARGIN,
            y=comparison_bottom + 48,
            width=WIDTH - 2 * MARGIN,
            height=max_bottom - comparison_bottom - 48,
            weight="semibold",
            start_size=28,
            min_size=22,
            fill=primary,
            measured_lines=measured_lines,
            spacing_ratio=0.08,
        )
    return max_bottom


def _draw_source_footer(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    *,
    primary: str,
    studio_name: str,
    identity_visible: bool,
    measured_lines: list[tuple[str, ImageFont.FreeTypeFont]],
) -> tuple[int, str]:
    """Draw the exact public source note and optional Studio identity."""

    footer_y = HEIGHT - 112
    draw.rectangle((MARGIN, footer_y - 24, WIDTH - MARGIN, footer_y - 21), fill=primary)
    sources = slide["source_note"].strip()
    footer_width = WIDTH - 2 * MARGIN
    show_footer_identity = identity_visible
    if sources:
        source_font, source_lines, source_spacing = _fit_lines(
            draw,
            sources,
            weight="regular",
            max_width=int(footer_width * (0.62 if show_footer_identity else 1.0)),
            max_height=58,
            start_size=22,
            min_size=15,
        )
        _draw_lines(
            draw,
            (MARGIN, footer_y),
            source_lines,
            font=source_font,
            fill=primary,
            spacing=source_spacing,
        )
        measured_lines.extend((line, source_font) for line in source_lines)
    if show_footer_identity:
        studio_font, studio_lines, studio_spacing = _fit_lines(
            draw,
            studio_name,
            weight="semibold",
            max_width=int(footer_width * 0.34),
            max_height=60,
            start_size=20,
            min_size=15,
        )
        studio_width = max(
            (draw.textlength(line, font=studio_font) for line in studio_lines),
            default=0,
        )
        _draw_lines(
            draw,
            (int(WIDTH - MARGIN - studio_width), footer_y),
            studio_lines,
            font=studio_font,
            fill=primary,
            spacing=studio_spacing,
        )
        measured_lines.extend((line, studio_font) for line in studio_lines)
    return footer_y, sources


def _render_slide(
    slide: dict[str, Any],
    *,
    index: int,
    total: int,
    brand: dict[str, str],
    studio_name: str,
    logo_path: Path | None,
    identity_visible: bool,
    creative_tokens: dict[str, str] | None,
    output_path: Path,
) -> dict[str, Any]:
    background = brand["background_color"]
    primary = brand["primary_color"]
    accent = brand["accent_color"]
    text = brand["text_color"]
    image = Image.new("RGBA", (WIDTH, HEIGHT), background)
    draw = ImageDraw.Draw(image)
    row_marker = "numeral"
    rhythm_gap = 0
    if creative_tokens is not None:
        frame = creative_tokens["frame_style"]
        rule = creative_tokens["rule_style"]
        accent_geometry = creative_tokens["accent_geometry"]
        header = creative_tokens["header_treatment"]
        rhythm = creative_tokens["spacing_rhythm"]
        row_marker = creative_tokens["row_marker"]
        rhythm_gap = {"compact": -14, "balanced": 0, "airy": 18}[rhythm]
        stroke = 4
        if frame == "hairline":
            draw.rectangle((22, 22, WIDTH - 22, HEIGHT - 22), outline=primary, width=2)
        elif frame == "inset":
            draw.rectangle(
                (34, 34, WIDTH - 34, HEIGHT - 34), outline=primary, width=stroke
            )
        line_y = 102 if rule != "offset" else 118
        draw.line((MARGIN, line_y, WIDTH - MARGIN, line_y), fill=accent, width=stroke)
        if rule == "double":
            draw.line(
                (MARGIN, line_y + 12, WIDTH - MARGIN, line_y + 12),
                fill=primary,
                width=max(1, stroke // 2),
            )
        if accent_geometry == "corner_stamp":
            draw.rectangle((WIDTH - 116, 0, WIDTH, 116), fill=accent)
        elif accent_geometry == "side_bar":
            draw.rectangle((0, 150, stroke + 8, HEIGHT - 190), fill=accent)
        else:
            draw.rectangle((MARGIN, 126, MARGIN + 210, 126 + stroke), fill=accent)
        if header == "outline":
            draw.rectangle(
                (MARGIN - 20, 58, WIDTH - MARGIN + 20, 146),
                outline=primary,
                width=2,
            )
        elif header == "split":
            draw.rectangle((0, 0, WIDTH // 3, 22), fill=primary)
            draw.rectangle((WIDTH // 3, 0, WIDTH, 22), fill=accent)
    measured_lines: list[tuple[str, ImageFont.FreeTypeFont]] = []
    layout_variant = slide["layout_variant"]
    content_limit = HEIGHT - 156
    inverted_header = layout_variant in {"editorial_cover", "threshold_notice"}
    if inverted_header:
        draw.rectangle((0, 0, WIDTH, 840), fill=primary)
    _draw_header(
        draw,
        slide,
        index=index,
        total=total,
        primary=primary,
        accent=accent,
        inverted=inverted_header,
    )

    if identity_visible and logo_path is not None:
        _draw_logo(
            image,
            logo_path,
            x=WIDTH - MARGIN - 200,
            y=128,
            max_width=200,
            max_height=70,
        )

    if layout_variant == "editorial_cover":
        y = _draw_text_block(
            draw,
            slide["title"],
            x=MARGIN,
            y=190,
            width=WIDTH - 2 * MARGIN,
            height=500,
            weight="bold",
            start_size=84,
            min_size=50,
            fill="#FFFFFF",
            measured_lines=measured_lines,
        )
        if slide["highlight"]:
            y = _draw_text_block(
                draw,
                slide["highlight"],
                x=MARGIN,
                y=y + 20,
                width=WIDTH - 2 * MARGIN,
                height=120,
                weight="bold",
                start_size=74,
                min_size=44,
                fill=accent,
                measured_lines=measured_lines,
            )
        y = _draw_text_block(
            draw,
            slide["body"],
            x=MARGIN,
            y=900 + rhythm_gap,
            width=WIDTH - 2 * MARGIN,
            height=230,
            weight="regular",
            start_size=38,
            min_size=27,
            fill=text,
            measured_lines=measured_lines,
        )
    elif layout_variant == "threshold_notice":
        y = _draw_text_block(
            draw,
            slide["title"],
            x=MARGIN,
            y=170,
            width=WIDTH - 2 * MARGIN,
            height=280,
            weight="bold",
            start_size=66,
            min_size=42,
            fill="#FFFFFF",
            measured_lines=measured_lines,
        )
        y = _draw_text_block(
            draw,
            slide["highlight"],
            x=MARGIN,
            y=y + 26 + rhythm_gap,
            width=WIDTH - 2 * MARGIN,
            height=150,
            weight="bold",
            start_size=94,
            min_size=54,
            fill=accent,
            measured_lines=measured_lines,
        )
        _draw_text_block(
            draw,
            slide["body"],
            x=MARGIN,
            y=y + 40,
            width=WIDTH - 2 * MARGIN,
            height=185,
            weight="regular",
            start_size=32,
            min_size=24,
            fill="#FFFFFF",
            measured_lines=measured_lines,
        )
        y = _draw_indexed_rows(
            draw,
            slide["bullets"],
            x=MARGIN,
            y=875 + rhythm_gap,
            width=WIDTH - 2 * MARGIN,
            max_bottom=content_limit,
            primary=primary,
            accent=accent,
            text=text,
            measured_lines=measured_lines,
            row_marker=row_marker,
        )
    else:
        y = _draw_text_block(
            draw,
            slide["title"],
            x=MARGIN,
            y=170,
            width=WIDTH - 2 * MARGIN,
            height=280,
            weight="bold",
            start_size=70,
            min_size=42,
            fill=primary,
            measured_lines=measured_lines,
        )
        if slide["highlight"]:
            y = _draw_text_block(
                draw,
                slide["highlight"],
                x=MARGIN,
                y=y + 18 + rhythm_gap,
                width=WIDTH - 2 * MARGIN,
                height=120,
                weight="bold",
                start_size=78,
                min_size=46,
                fill=accent,
                measured_lines=measured_lines,
            )
        y = _draw_text_block(
            draw,
            slide["body"],
            x=MARGIN,
            y=y + 26 + rhythm_gap,
            width=WIDTH - 2 * MARGIN,
            height=210,
            weight="regular",
            start_size=36,
            min_size=25,
            fill=text,
            measured_lines=measured_lines,
        )
        y += 26 + rhythm_gap
        if layout_variant == "dual_gate":
            y = _draw_dual_gate(
                draw,
                slide["bullets"],
                y=y,
                max_bottom=content_limit,
                primary=primary,
                accent=accent,
                text=text,
                measured_lines=measured_lines,
                row_marker=row_marker,
            )
        elif layout_variant == "route_comparison":
            y = _draw_route_comparison(
                draw,
                slide["bullets"],
                y=y,
                max_bottom=content_limit,
                primary=primary,
                accent=accent,
                text=text,
                measured_lines=measured_lines,
                row_marker=row_marker,
            )
        else:
            y = _draw_indexed_rows(
                draw,
                slide["bullets"],
                x=MARGIN,
                y=y,
                width=WIDTH - 2 * MARGIN,
                max_bottom=content_limit,
                primary=primary,
                accent=accent,
                text=text,
                measured_lines=measured_lines,
                boxed=layout_variant == "evidence_dossier",
                row_marker=row_marker,
            )

    if y > content_limit:
        raise ValueError(f"Slide {index} content exceeds safe visual area")
    footer_y, sources = _draw_source_footer(
        draw,
        slide,
        primary=primary,
        studio_name=studio_name,
        identity_visible=identity_visible and logo_path is None,
        measured_lines=measured_lines,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, format="PNG", optimize=True)
    return {
        "overflow_free": True,
        "safe_area": [MARGIN, 54, WIDTH - MARGIN, footer_y - 44],
        "content_bottom": y,
        "footer_top": footer_y - 24,
        "layout_variant": layout_variant,
        "max_line_width_px": max(
            (draw.textlength(line, font=font) for line, font in measured_lines),
            default=0,
        ),
        "available_width_px": WIDTH - 2 * MARGIN,
        "identity_visible": identity_visible,
        "public_source_note": sources,
        "internal_id_leakage": False,
        "creative_direction_tokens": creative_tokens,
    }


def _pdf_font_names(font_family: str) -> dict[str, str]:
    """Resolve the approved Studio font family to reproducible PDF font names."""

    if font_family == "Instrument Sans":
        _register_pdf_fonts()
        return {
            "regular": "InstrumentSans",
            "semibold": "InstrumentSans-Semibold",
            "bold": "InstrumentSans-Bold",
        }
    if font_family == "Helvetica":
        return {
            "regular": "Helvetica",
            "semibold": "Helvetica-Bold",
            "bold": "Helvetica-Bold",
        }
    if font_family == "Times":
        return {
            "regular": "Times-Roman",
            "semibold": "Times-Bold",
            "bold": "Times-Bold",
        }
    raise ValueError(f"Unsupported approved Studio font family: {font_family}")


def _register_pdf_fonts() -> None:
    pdfmetrics.registerFont(TTFont("InstrumentSans", str(FONT_PATHS["regular"])))
    pdfmetrics.registerFont(
        TTFont("InstrumentSans-Semibold", str(FONT_PATHS["semibold"]))
    )
    pdfmetrics.registerFont(TTFont("InstrumentSans-Bold", str(FONT_PATHS["bold"])))


def _paragraphs(text: str, style: ParagraphStyle) -> list[Any]:
    rows: list[Any] = []
    for paragraph in [part.strip() for part in text.split("\n\n") if part.strip()]:
        rows.extend(
            (
                Paragraph(html.escape(paragraph).replace("\n", "<br/>"), style),
                Spacer(1, 2.5 * mm),
            )
        )
    return rows


def _wrap_pdf_text(
    value: str, *, font_name: str, font_size: float, max_width: float
) -> list[str]:
    """Wrap exact PDF text by measured glyph width, including long tokens."""

    def pieces(word: str) -> list[str]:
        rows: list[str] = []
        current = ""
        for character in word:
            candidate = current + character
            if (
                current
                and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width
            ):
                rows.append(current)
                current = character
            else:
                current = candidate
            if pdfmetrics.stringWidth(current, font_name, font_size) > max_width:
                raise ValueError("One PDF glyph exceeds the available width")
        if current:
            rows.append(current)
        return rows

    words = [
        part
        for word in value.split()
        for part in (
            [word]
            if pdfmetrics.stringWidth(word, font_name, font_size) <= max_width
            else pieces(word)
        )
    ]
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    if any(
        pdfmetrics.stringWidth(line, font_name, font_size) > max_width for line in lines
    ):
        raise ValueError("Wrapped PDF line exceeds the available width")
    return lines


def _normalized_pdf_text(value: str) -> str:
    return " ".join(value.split())


def _pdf_match_key(value: str) -> str:
    """Normalize extractor-added spacing around punctuation for presence checks."""

    return "".join(character for character in value.casefold() if character.isalnum())


def _render_circular_pdf(
    draft: dict[str, Any],
    *,
    brand: dict[str, str],
    studio_profile: dict[str, Any],
    studio_name: str,
    reference_date: str,
    language: str,
    logo_path: Path | None,
    output_path: Path,
) -> dict[str, Any]:
    document_profile = studio_profile["document"]
    font_names = _pdf_font_names(document_profile["font_family"])
    layout = document_profile["layout"]
    primary = HexColor(brand["primary_color"])
    accent = HexColor(brand["accent_color"])
    text_color = HexColor(brand["text_color"])
    use_rail = bool(
        document_profile["use_contact_rail"] and document_profile["contact_rail_lines"]
    )
    page_width, page_height = A4
    rail_rows: list[tuple[str, list[str]]] = []
    if use_rail:
        rail_width = max(8 * mm, (layout["contact_rail_width_mm"] - 8) * mm)
        rail_height = 0.0
        for index, line in enumerate(document_profile["contact_rail_lines"]):
            font_role = "semibold" if index == 0 else "regular"
            wrapped = (
                _wrap_pdf_text(
                    line,
                    font_name=font_names[font_role],
                    font_size=8.5,
                    max_width=rail_width,
                )
                if line
                else [""]
            )
            rail_rows.append((font_role, wrapped))
            rail_height += len(wrapped) * 11 + (4 if not line else 0)
        if rail_height > page_height - 76 * mm:
            raise ValueError("Studio contact rail cannot fit without omission")

    header_lines: list[str] = []
    if logo_path is None:
        header_lines = _wrap_pdf_text(
            studio_name,
            font_name=font_names["bold"],
            font_size=18,
            max_width=page_width
            - (layout["left_margin_mm"] + layout["right_margin_mm"]) * mm,
        )
        if len(header_lines) > 2:
            raise ValueError("Studio name cannot fit the circular header")

    class CircularDocument(BaseDocTemplate):
        pass

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.", suffix=".pdf", dir=output_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    doc = CircularDocument(
        str(temporary_path),
        pagesize=A4,
        leftMargin=layout["left_margin_mm"] * mm,
        rightMargin=layout["right_margin_mm"] * mm,
        topMargin=layout["top_margin_mm"] * mm,
        bottomMargin=layout["bottom_margin_mm"] * mm,
        title=draft["title"],
        author=studio_name,
    )
    horizontal_margins = (layout["left_margin_mm"] + layout["right_margin_mm"]) * mm
    vertical_margins = (layout["top_margin_mm"] + layout["bottom_margin_mm"]) * mm
    first_width = (
        page_width
        - horizontal_margins
        - (layout["contact_rail_width_mm"] * mm if use_rail else 0)
    )
    first_frame = Frame(
        layout["left_margin_mm"] * mm,
        layout["bottom_margin_mm"] * mm,
        first_width,
        page_height - vertical_margins,
        id="first",
    )
    later_frame = Frame(
        layout["left_margin_mm"] * mm,
        layout["bottom_margin_mm"] * mm,
        page_width - horizontal_margins,
        page_height - vertical_margins,
        id="later",
    )

    def draw_page(canvas: Any, document: Any, *, first: bool) -> None:
        canvas.saveState()
        if logo_path:
            canvas.drawImage(
                str(logo_path),
                layout["left_margin_mm"] * mm,
                page_height - (layout["top_margin_mm"] - 8) * mm,
                width=layout["logo_width_mm"] * mm,
                height=layout["logo_height_mm"] * mm,
                preserveAspectRatio=True,
                anchor="w",
                mask="auto",
            )
        else:
            canvas.setFont(font_names["bold"], 18)
            canvas.setFillColor(primary)
            header_y = page_height - (layout["top_margin_mm"] - 13) * mm
            for line in header_lines:
                canvas.drawString(layout["left_margin_mm"] * mm, header_y, line)
                header_y -= 20
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(layout["rule_width_pt"])
        canvas.line(
            layout["left_margin_mm"] * mm,
            page_height - (layout["top_margin_mm"] - 3) * mm,
            page_width - layout["right_margin_mm"] * mm,
            page_height - (layout["top_margin_mm"] - 3) * mm,
        )
        canvas.setFont(font_names["regular"], 8)
        canvas.setFillColor(text_color)
        footer = document_profile["footer_pattern"].replace(
            "{page}", str(document.page)
        )
        footer_lines = _wrap_pdf_text(
            footer or f"pag. {document.page}",
            font_name=font_names["regular"],
            font_size=8,
            max_width=page_width
            - (layout["left_margin_mm"] + layout["right_margin_mm"]) * mm,
        )
        if len(footer_lines) > 2:
            raise ValueError("Studio footer cannot fit the circular page")
        footer_y = max(5, layout["bottom_margin_mm"] - 9) * mm
        for line in footer_lines:
            canvas.drawCentredString(page_width / 2, footer_y, line)
            footer_y += 9
        if first and use_rail:
            rail_x = (
                page_width
                - (layout["right_margin_mm"] + layout["contact_rail_width_mm"]) * mm
            )
            canvas.setStrokeColor(HexColor("#D9D9D9"))
            canvas.setLineWidth(1.4)
            canvas.line(rail_x, 22 * mm, rail_x, page_height - 43 * mm)
            text = canvas.beginText(rail_x + 4 * mm, page_height - 48 * mm)
            text.setFont(font_names["semibold"], 8.5)
            text.setFillColor(primary)
            for font_role, wrapped_lines in rail_rows:
                if wrapped_lines == [""]:
                    text.moveCursor(0, 4)
                    continue
                text.setFont(font_names[font_role], 8.5)
                for wrapped_line in wrapped_lines:
                    text.textLine(wrapped_line)
            canvas.drawText(text)
        canvas.restoreState()

    doc.addPageTemplates(
        [
            PageTemplate(
                id="first",
                frames=[first_frame],
                onPage=lambda c, d: draw_page(c, d, first=True),
                autoNextPageTemplate="later",
            ),
            PageTemplate(
                id="later",
                frames=[later_frame],
                onPage=lambda c, d: draw_page(c, d, first=False),
            ),
        ]
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=font_names["regular"],
        fontSize=layout["body_font_size_pt"],
        leading=layout["body_leading_pt"],
        textColor=text_color,
        alignment=TA_LEFT,
        spaceAfter=2 * mm,
    )
    meta = ParagraphStyle("Meta", parent=normal, fontSize=9, leading=12)
    subject = ParagraphStyle(
        "Subject",
        parent=normal,
        fontName=font_names["bold"],
        fontSize=layout["subject_font_size_pt"],
        leading=layout["subject_font_size_pt"] * 1.23,
        textColor=primary,
        spaceBefore=3 * mm,
        spaceAfter=6 * mm,
    )
    heading = ParagraphStyle(
        "Heading",
        parent=normal,
        fontName=font_names["bold"],
        fontSize=layout["heading_font_size_pt"],
        leading=layout["heading_font_size_pt"] * 1.27,
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
        keepWithNext=True,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=normal,
        leftIndent=7 * mm,
        firstLineIndent=-4 * mm,
        spaceAfter=1.5 * mm,
    )
    recipient_line = (
        draft.get("recipient_line") or document_profile["recipient_pattern"]
    )
    date_line = draft.get("date_line") or document_profile["date_pattern"].replace(
        "{date}", reference_date
    )
    circular_line = " ".join(
        part
        for part in (
            document_profile["circular_label"],
            draft.get("circular_number", ""),
        )
        if part
    )
    subject_line = " ".join(
        part
        for part in (
            document_profile["subject_prefix"],
            draft.get("subject") or draft["title"],
        )
        if part
    )
    story: list[Any] = [
        Paragraph(
            html.escape(recipient_line),
            meta,
        ),
        Paragraph(
            html.escape(date_line),
            meta,
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            html.escape(circular_line),
            ParagraphStyle(
                "Circular",
                parent=meta,
                fontName=font_names["semibold"],
                textColor=primary,
            ),
        ),
        Paragraph(
            html.escape(subject_line),
            subject,
        ),
    ]
    story.extend(_paragraphs(draft["body"], normal))
    for index, section in enumerate(draft["sections"], start=1):
        section_title = section["heading"]
        if document_profile["section_style"] == "numbered_uppercase":
            section_title = f"{index}  {section_title.upper()}"
        elif document_profile["section_style"] == "numbered_sentence":
            section_title = f"{index}  {section_title}"
        story.append(Paragraph(html.escape(section_title), heading))
        story.extend(_paragraphs(section["body"], normal))
        if section["bullets"]:
            story.extend(
                Paragraph(f"- {html.escape(item)}", bullet_style)
                for item in section["bullets"]
            )
    source_lines = [
        (
            f"{note['text']} — {note['public_url']}"
            if note.get("public_url") and note["public_url"] not in note["text"]
            else note["text"]
        )
        for note in draft["public_source_notes"]
    ]
    source_heading = ""
    if source_lines:
        language_key = language.replace("_", "-").split("-", maxsplit=1)[0].lower()
        source_heading = (
            studio_profile["website"]["source_heading"]
            if language_key == "it"
            else SOURCE_HEADINGS.get(language_key, "Sources")
        )
        story.append(Paragraph(html.escape(source_heading), heading))
        story.extend(Paragraph(html.escape(line), normal) for line in source_lines)
    story.extend(
        (Spacer(1, 6 * mm), Paragraph(html.escape(document_profile["closing"]), normal))
    )
    for line in document_profile["signature_lines"] or [studio_name]:
        story.append(
            Paragraph(
                html.escape(line),
                ParagraphStyle(
                    "Signature", parent=normal, fontName=font_names["semibold"]
                ),
            )
        )
    try:
        doc.build(story)
        reader = PdfReader(str(temporary_path))
        extracted = _normalized_pdf_text(
            "\n".join(page.extract_text() or "" for page in reader.pages)
        )
        required_text = [
            recipient_line,
            date_line,
            circular_line,
            subject_line,
            draft["body"],
            *(
                value
                for section in draft["sections"]
                for value in (
                    section["heading"],
                    section["body"],
                    *section["bullets"],
                )
                if value
            ),
            source_heading,
            *source_lines,
            document_profile["closing"],
            *(line for line in document_profile["signature_lines"] if line),
            *(header_lines if logo_path is None else []),
            *(
                line
                for line in document_profile["contact_rail_lines"]
                if use_rail and line
            ),
            *(
                document_profile["footer_pattern"].replace("{page}", str(page))
                or f"pag. {page}"
                for page in range(1, len(reader.pages) + 1)
            ),
        ]
        missing = [
            value
            for value in required_text
            if _pdf_match_key(value) not in _pdf_match_key(extracted)
        ]
        if missing:
            raise ValueError(
                "Circular PDF omitted reviewed text: " + ", ".join(missing[:3])
            )
        os.chmod(temporary_path, 0o600)
        temporary_path.replace(output_path)
        return {
            "overflow_free": True,
            "page_layout_engine": "reportlab_platypus",
            "page_count": len(reader.pages),
            "text_extraction_verified": True,
            "contact_rail_exact": True,
            "manual_regions_fit": True,
            "silent_truncation": False,
        }
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _preview_html(entries: list[dict[str, Any]], *, title: str, language: str) -> str:
    cards = "\n".join(
        f'<figure><img src="{html.escape(Path(row["path"]).name)}" alt="Slide {index}"><figcaption>{html.escape(row["kind"])} · {row["width"]} × {row["height"]}</figcaption></figure>'
        for index, row in enumerate(entries, start=1)
        if row["kind"] == "carousel_slide"
    )
    return f"""<!doctype html>
<html lang="{html.escape(language.replace('_', '-'), quote=True)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{margin:0;background:#f5f6f8;color:#171816;font-family:"Instrument Sans",Arial,sans-serif}}
main{{max-width:1280px;margin:auto;padding:48px}}h1{{font-size:32px;font-weight:650;margin:0 0 32px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:28px;align-items:start}}
figure{{margin:0;background:#fff;border:1px solid #d9dde4;padding:12px}}img{{display:block;width:100%;height:auto}}
figcaption{{padding:12px 4px 4px;font-size:13px;color:#52606d}}
</style></head><body><main><h1>{html.escape(title)}</h1><div class="grid">{cards}</div></main></body></html>"""


def _visual_review_markdown(
    contribution: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    identity_placement: str,
    render_state: str,
    profile_status: str,
    logo_present: bool,
) -> str:
    """Expose the exact mechanical facts and required model-led review."""

    story = contribution["visual_story"]
    lines = [
        "# Exact visual quality review",
        "",
        f"- Render state: **{render_state}**",
        f"- Studio format status: **{profile_status}**",
        f"- Official logo asset present: **{str(logo_present).lower()}**",
        f"- Visual decision: **{story['decision']}**",
        f"- Decision reason: {story['decision_reason']}",
        f"- Incremental value over the post: {story['incremental_value']}",
        f"- Studio identity placement: `{identity_placement}`",
        "",
        "## Per-slide contract",
        "",
    ]
    slide_entries = [row for row in entries if row["kind"] == "carousel_slide"]
    for index, (slide, entry) in enumerate(
        zip(story["slides"], slide_entries, strict=True), start=1
    ):
        layout = entry["layout_validation"]
        lines.extend(
            [
                f"### Slide {index:02d}",
                "",
                f"- Job: `{slide['kind']}`",
                f"- Composition: `{slide['layout_variant']}`",
                f"- Reader use: {slide['reader_use']}",
                f"- Relationship to post: `{slide['relationship_to_post']}`",
                f"- Public source note: {slide['source_note'] or 'none'}",
                f"- Studio identity visible: `{str(layout['identity_visible']).lower()}`",
                f"- Exact PNG: `{entry['path']}` · `{entry['sha256']}`",
                "",
            ]
        )
    document_entries = [row for row in entries if row["kind"] == "client_circular_pdf"]
    if document_entries:
        lines.extend(("## Rendered documents", ""))
        for entry in document_entries:
            validation = entry["layout_validation"]
            lines.extend(
                (
                    f"- Exact PDF: `{entry['path']}` · `{entry['sha256']}`",
                    f"- Pages: `{validation['page_count']}`",
                    "- Exact text extraction, contact rail, footer, and manual-region fit: `passed`",
                    "",
                )
            )
    lines.extend(
        [
            "## Required model-led inspection",
            "",
            "Do not accept the rendered output until an editor has opened every exact PNG and answered all of these questions from the visible artifact:",
            "",
            "- Does the carousel add useful detail, structure, comparison, sequence, or a decision aid beyond the post? If it only paraphrases the post, return it.",
            "- Does each slide have one non-trivial job, or do title, highlight, body, and bullets repeat the same proposition?",
            "- Are the source notes meaningful to a reader without access to internal manifests?",
            "- Is Studio identity present only where the accepted profile requires it?",
            "- Are checklists explicitly bounded, without implying that a preliminary screen is a sufficient professional conclusion?",
            "- Is the most prominent number or phrase useful for a decision, rather than decorative emphasis?",
            "- At LinkedIn mobile size, are title, body, source note, and footer still legible and balanced?",
            "- Does the output look authored for this Studio, or like a generic AI carousel?",
            "- For every PDF page: are pagination, header, footer, contact rail, source notes, closing, and signature visibly complete and balanced?",
            "",
            "Mechanical checks cannot answer these questions. Record acceptance only after the model-led inspection is complete.",
            "",
        ]
    )
    return "\n".join(lines)


def render_visuals(run_dir: Path, *, qa_preview: bool = False) -> Path:
    """Render an isolated QA preview or accepted release-candidate visuals."""

    root = run_dir.resolve()
    with workflow_lock(root):
        return _render_visuals_locked(root, qa_preview=qa_preview)


def _render_visuals_locked(root: Path, *, qa_preview: bool) -> Path:
    """Render while one writer owns the run and all integrity bindings hold."""

    validate_input_integrity(root)
    intake = load_json(root / "run_intake.json")
    workbench = load_json(root / "content_workbench.json")
    recompute_contribution_digest(root)
    contribution = workbench["contribution"]
    if contribution["recommendation"] != "publish":
        raise ValueError("No visual rendering for no_publish recommendation")
    if not qa_preview:
        require_accepted_reviews(root, workbench["required_review_scopes"])
    source_register = load_json(root / "source_register.json")
    proposal = contribution.get("studio_profile_proposal")
    if proposal is not None:
        studio_profile = proposal
    else:
        stored = intake.get("studio_profile")
        if not isinstance(stored, dict) or not isinstance(stored.get("payload"), dict):
            raise ValueError("Accepted or stored studio profile required for rendering")
        studio_profile = stored["payload"]["profile"]
    brand = intake["brand_profile"]
    studio_name = brand["studio_name"]
    logo = _logo_path(source_register)
    slides = contribution["visual_story"]["slides"]
    creative_direction = verify_creative_direction_decision(root)
    creative_tokens = creative_direction["tokens"]
    applied_creative_tokens, inapplicable_creative_tokens = creative_token_application(
        creative_tokens, slides
    )
    circular = next(
        (
            draft
            for draft in contribution["channel_drafts"]
            if draft["channel"] == "client_circular"
        ),
        None,
    )
    if not slides and circular is None:
        raise ValueError("Contribution correctly omits visual rendering")
    identity_placement = studio_profile["social"]["carousel_identity_placement"]
    _validate_visual_text_contract(
        slides,
        studio_name=studio_name,
        identity_placement=identity_placement,
    )
    render_state = "qa_preview" if qa_preview else "accepted_semantics"
    profile_status = (
        "unreviewed_run_profile_proposal"
        if proposal is not None and qa_preview
        else (
            "accepted_run_profile"
            if proposal is not None
            else "stored_approved_profile"
        )
    )
    profile_provenance_summary = {
        basis: sum(
            len(record["field_paths"])
            for record in studio_profile["field_provenance"]
            if record["basis"] == basis
        )
        for basis in (
            "observed_history",
            "user_supplied",
            "vera_default_proposal",
        )
    }
    visuals_dir = root / ("visuals-preview" if qa_preview else "visuals")
    manifest_path = root / (
        "visual_preview_manifest.json" if qa_preview else "visual_manifest.json"
    )
    if manifest_path.exists():
        raise ValueError(
            f"{render_state} visual output already exists; supersede the contribution to render a new version"
        )
    visuals_dir.mkdir(exist_ok=True)
    entries: list[dict[str, Any]] = []

    for index, slide in enumerate(slides, start=1):
        output = visuals_dir / f"slide-{index:02d}.png"
        layout_validation = _render_slide(
            slide,
            index=index,
            total=len(slides),
            brand=brand,
            studio_name=studio_name,
            logo_path=logo,
            identity_visible=_identity_visible(
                identity_placement,
                index=index,
                total=len(slides),
            ),
            creative_tokens=creative_tokens,
            output_path=output,
        )
        with Image.open(output) as image:
            width, height = image.size
        entries.append(
            {
                "path": str(output.relative_to(root)),
                "kind": "carousel_slide",
                "width": width,
                "height": height,
                "sha256": file_digest(output),
                "size_bytes": output.stat().st_size,
                "source_ids": slide["source_ids"],
                "reader_use": slide["reader_use"],
                "relationship_to_post": slide["relationship_to_post"],
                "layout_validation": layout_validation,
            }
        )

    if circular is not None:
        circular_path = visuals_dir / "circolare-clienti.pdf"
        circular_validation = _render_circular_pdf(
            circular,
            brand=brand,
            studio_profile=studio_profile,
            studio_name=studio_name,
            reference_date=intake["reference_date"],
            language=intake["language"],
            logo_path=logo,
            output_path=circular_path,
        )
        entries.append(
            {
                "path": str(circular_path.relative_to(root)),
                "kind": "client_circular_pdf",
                "sha256": file_digest(circular_path),
                "size_bytes": circular_path.stat().st_size,
                "source_ids": sorted(
                    {
                        source_id
                        for claim in contribution["claims"]
                        if claim["id"] in circular["claim_ids"]
                        for source_id in claim["source_ids"]
                    }
                ),
                "layout_validation": circular_validation,
            }
        )

    preview = visuals_dir / "visual-preview.html"
    preview_title = contribution["visual_story"]["title"] or (
        circular["title"] if circular else studio_name
    )
    atomic_write_text(
        preview,
        _preview_html(entries, title=preview_title, language=intake["language"]),
    )
    entries.append(
        {
            "path": str(preview.relative_to(root)),
            "kind": "visual_preview_html",
            "sha256": file_digest(preview),
            "size_bytes": preview.stat().st_size,
            "source_ids": [],
            "layout_validation": {"overflow_free": True},
        }
    )
    review_path = visuals_dir / "visual-review.md"
    atomic_write_text(
        review_path,
        _visual_review_markdown(
            contribution,
            entries,
            identity_placement=identity_placement,
            render_state=render_state,
            profile_status=profile_status,
            logo_present=logo is not None,
        ),
    )
    entries.append(
        {
            "path": str(review_path.relative_to(root)),
            "kind": "visual_quality_review_md",
            "sha256": file_digest(review_path),
            "size_bytes": review_path.stat().st_size,
            "source_ids": [],
            "layout_validation": {"overflow_free": True},
        }
    )
    manifest = {
        "schema_version": 1,
        "workflow": "comunicazione-professionale",
        "run_id": intake["run_id"],
        "contribution_digest": workbench["contribution_digest"],
        "rendered_at": utc_now(),
        "render_state": render_state,
        "renderer": "deterministic_pillow_reportlab_v5",
        "creative_direction": {
            key: value for key, value in creative_direction.items() if key != "tokens"
        },
        "font_assets": {name: file_digest(path) for name, path in FONT_PATHS.items()},
        "studio_profile_version": (
            intake["studio_profile"]["payload"]["version"]
            if proposal is None
            else "run_proposal"
        ),
        "quality_gate": {
            "mechanical_checks": {
                "font_coverage": "passed",
                "internal_id_leakage": "passed",
                "identity_duplicates": "passed",
                "overflow": "passed",
                "pdf_text_preservation": "passed",
            },
            "model_led_review_required": True,
            "review_artifact": str(review_path.relative_to(root)),
            "visual_decision": contribution["visual_story"]["decision"],
            "incremental_value": contribution["visual_story"]["incremental_value"],
            "identity_placement": identity_placement,
            "studio_format_status": profile_status,
            "studio_format_provenance_summary": profile_provenance_summary,
            "official_logo_asset_present": logo is not None,
            "creative_tokens_consumed": applied_creative_tokens,
            "creative_tokens_not_applicable": inapplicable_creative_tokens,
        },
        "outputs": entries,
    }
    manifest["manifest_digest"] = canonical_digest(manifest)
    return atomic_write_json(manifest_path, manifest)


def main(argv: list[str] | None = None) -> int:
    """Render accepted visuals."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--qa-preview",
        action="store_true",
        help="Render an isolated, non-packageable preview before professional review.",
    )
    args = parser.parse_args(argv)
    try:
        path = render_visuals(args.run_dir, qa_preview=args.qa_preview)
    except (OSError, ValueError) as exc:
        LOGGER.error("VISUAL_RENDER_FAILED: %s", exc)
        return 1
    LOGGER.info("Rendered visual package: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
