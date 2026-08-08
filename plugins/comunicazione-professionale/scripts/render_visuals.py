#!/usr/bin/env python3
"""Render accepted studio-formatted visual and circular artifacts."""

from __future__ import annotations

import argparse
import html
import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
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
    file_digest,
    load_json,
    recompute_contribution_digest,
    require_accepted_reviews,
    utc_now,
    validate_input_integrity,
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


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATHS[weight]), size=size)


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


def _render_slide(
    slide: dict[str, Any],
    *,
    index: int,
    total: int,
    brand: dict[str, str],
    studio_name: str,
    logo_path: Path | None,
    output_path: Path,
) -> dict[str, Any]:
    background = brand["background_color"]
    primary = brand["primary_color"]
    accent = brand["accent_color"]
    text = brand["text_color"]
    image = Image.new("RGBA", (WIDTH, HEIGHT), background)
    draw = ImageDraw.Draw(image)
    measured_lines: list[tuple[str, ImageFont.FreeTypeFont]] = []

    draw.rectangle((0, 0, 24, HEIGHT), fill=primary)
    draw.rectangle((MARGIN, 104, WIDTH - MARGIN, 110), fill=accent)
    draw.text(
        (MARGIN, 54), slide["eyebrow"].upper(), font=_font("semibold", 25), fill=primary
    )
    draw.text(
        (WIDTH - MARGIN - 78, 54),
        f"{index:02d}/{total:02d}",
        font=_font("medium" if "medium" in FONT_PATHS else "regular", 23),
        fill=primary,
    )

    _draw_logo(
        image, logo_path, x=WIDTH - MARGIN - 200, y=128, max_width=200, max_height=88
    )
    if logo_path is None:
        studio_font, studio_lines, studio_spacing = _fit_lines(
            draw,
            studio_name,
            weight="semibold",
            max_width=320,
            max_height=90,
            start_size=28,
            min_size=20,
        )
        _draw_lines(
            draw,
            (WIDTH - MARGIN - 320, 135),
            studio_lines,
            font=studio_font,
            fill=primary,
            spacing=studio_spacing,
        )
        measured_lines.extend((line, studio_font) for line in studio_lines)

    title_top = 250 if slide["kind"] == "cover" else 230
    title_height = 390 if slide["kind"] == "cover" else 285
    title_font, title_lines, title_spacing = _fit_lines(
        draw,
        slide["title"],
        weight="bold",
        max_width=WIDTH - 2 * MARGIN,
        max_height=title_height,
        start_size=84 if slide["kind"] == "cover" else 70,
        min_size=44,
    )
    y = _draw_lines(
        draw,
        (MARGIN, title_top),
        title_lines,
        font=title_font,
        fill=primary,
        spacing=title_spacing,
    )
    measured_lines.extend((line, title_font) for line in title_lines)

    if slide["highlight"]:
        highlight_font, highlight_lines, highlight_spacing = _fit_lines(
            draw,
            slide["highlight"],
            weight="bold",
            max_width=WIDTH - 2 * MARGIN,
            max_height=150,
            start_size=98,
            min_size=54,
        )
        y += 26
        y = _draw_lines(
            draw,
            (MARGIN, y),
            highlight_lines,
            font=highlight_font,
            fill=accent,
            spacing=highlight_spacing,
        )
        measured_lines.extend((line, highlight_font) for line in highlight_lines)

    y += 34
    if slide["body"]:
        body_font, body_lines, body_spacing = _fit_lines(
            draw,
            slide["body"],
            weight="regular",
            max_width=WIDTH - 2 * MARGIN,
            max_height=310,
            start_size=38,
            min_size=27,
        )
        y = _draw_lines(
            draw,
            (MARGIN, y),
            body_lines,
            font=body_font,
            fill=text,
            spacing=body_spacing,
        )
        measured_lines.extend((line, body_font) for line in body_lines)

    bullet_font = _font("regular", 30)
    for bullet in slide["bullets"]:
        y += 20
        draw.ellipse((MARGIN, y + 10, MARGIN + 12, y + 22), fill=accent)
        bullet_lines = _wrap(draw, bullet, bullet_font, WIDTH - 2 * MARGIN - 42)
        y = _draw_lines(
            draw,
            (MARGIN + 40, y),
            bullet_lines,
            font=bullet_font,
            fill=text,
            spacing=7,
        )
        measured_lines.extend((line, bullet_font) for line in bullet_lines)
        if y > HEIGHT - 165:
            raise ValueError(f"Slide {index} content exceeds safe visual area")

    footer_y = HEIGHT - 112
    if y > footer_y - 44:
        raise ValueError(f"Slide {index} content exceeds safe visual area")
    draw.rectangle((MARGIN, footer_y - 24, WIDTH - MARGIN, footer_y - 21), fill=primary)
    sources = "Fonti: " + ", ".join(slide["source_ids"]) if slide["source_ids"] else ""
    footer_width = WIDTH - 2 * MARGIN
    if sources:
        source_font, source_lines, source_spacing = _fit_lines(
            draw,
            sources,
            weight="regular",
            max_width=int(footer_width * 0.62),
            max_height=48,
            start_size=20,
            min_size=12,
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
    studio_footer_font, studio_footer_lines, studio_footer_spacing = _fit_lines(
        draw,
        studio_name,
        weight="semibold",
        max_width=int(footer_width * 0.32),
        max_height=48,
        start_size=20,
        min_size=12,
    )
    studio_footer_width = max(
        (
            draw.textlength(line, font=studio_footer_font)
            for line in studio_footer_lines
        ),
        default=0,
    )
    _draw_lines(
        draw,
        (int(WIDTH - MARGIN - studio_footer_width), footer_y),
        studio_footer_lines,
        font=studio_footer_font,
        fill=primary,
        spacing=studio_footer_spacing,
    )
    measured_lines.extend((line, studio_footer_font) for line in studio_footer_lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, format="PNG", optimize=True)
    return {
        "overflow_free": True,
        "safe_area": [MARGIN, 54, WIDTH - MARGIN, footer_y - 44],
        "content_bottom": y,
        "footer_top": footer_y - 24,
        "max_line_width_px": max(
            (draw.textlength(line, font=font) for line, font in measured_lines),
            default=0,
        ),
        "available_width_px": WIDTH - 2 * MARGIN,
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


def _render_circular_pdf(
    draft: dict[str, Any],
    *,
    brand: dict[str, str],
    studio_profile: dict[str, Any],
    studio_name: str,
    reference_date: str,
    logo_path: Path | None,
    output_path: Path,
) -> None:
    document_profile = studio_profile["document"]
    font_names = _pdf_font_names(document_profile["font_family"])
    layout = document_profile["layout"]
    primary = HexColor(brand["primary_color"])
    accent = HexColor(brand["accent_color"])
    text_color = HexColor(brand["text_color"])
    use_rail = bool(
        document_profile["use_contact_rail"] and document_profile["contact_rail_lines"]
    )

    class CircularDocument(BaseDocTemplate):
        pass

    doc = CircularDocument(
        str(output_path),
        pagesize=A4,
        leftMargin=layout["left_margin_mm"] * mm,
        rightMargin=layout["right_margin_mm"] * mm,
        topMargin=layout["top_margin_mm"] * mm,
        bottomMargin=layout["bottom_margin_mm"] * mm,
        title=draft["title"],
        author=studio_name,
    )
    page_width, page_height = A4
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
            canvas.drawString(
                layout["left_margin_mm"] * mm,
                page_height - (layout["top_margin_mm"] - 13) * mm,
                studio_name,
            )
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
        canvas.drawCentredString(
            page_width / 2,
            max(5, layout["bottom_margin_mm"] - 9) * mm,
            footer or f"pag. {document.page}",
        )
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
            for index, line in enumerate(document_profile["contact_rail_lines"]):
                if not line:
                    text.moveCursor(0, 4)
                    continue
                text.setFont(
                    font_names["semibold"] if index == 0 else font_names["regular"],
                    8.5,
                )
                text.textLine(line[:70])
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
    story: list[Any] = [
        Paragraph(
            html.escape(
                draft.get("recipient_line") or document_profile["recipient_pattern"]
            ),
            meta,
        ),
        Paragraph(
            html.escape(
                draft.get("date_line")
                or document_profile["date_pattern"].replace("{date}", reference_date)
            ),
            meta,
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            html.escape(
                " ".join(
                    part
                    for part in (
                        document_profile["circular_label"],
                        draft.get("circular_number", ""),
                    )
                    if part
                )
            ),
            ParagraphStyle(
                "Circular",
                parent=meta,
                fontName=font_names["semibold"],
                textColor=primary,
            ),
        ),
        Paragraph(
            html.escape(
                f"{document_profile['subject_prefix']} {draft.get('subject') or draft['title']}"
            ).strip(),
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
    doc.build(story)


def _preview_html(entries: list[dict[str, Any]], *, title: str) -> str:
    cards = "\n".join(
        f'<figure><img src="{html.escape(Path(row["path"]).name)}" alt="Slide {index}"><figcaption>{html.escape(row["kind"])} · {row["width"]} × {row["height"]}</figcaption></figure>'
        for index, row in enumerate(entries, start=1)
        if row["kind"] == "carousel_slide"
    )
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{margin:0;background:#f5f6f8;color:#171816;font-family:"Instrument Sans",Arial,sans-serif}}
main{{max-width:1280px;margin:auto;padding:48px}}h1{{font-size:32px;font-weight:650;margin:0 0 32px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:28px;align-items:start}}
figure{{margin:0;background:#fff;border:1px solid #d9dde4;padding:12px}}img{{display:block;width:100%;height:auto}}
figcaption{{padding:12px 4px 4px;font-size:13px;color:#52606d}}
</style></head><body><main><h1>{html.escape(title)}</h1><div class="grid">{cards}</div></main></body></html>"""


def render_visuals(run_dir: Path) -> Path:
    """Render accepted carousel PNGs and any requested A4 circular."""

    root = run_dir.resolve()
    with workflow_lock(root):
        return _render_visuals_locked(root)


def _render_visuals_locked(root: Path) -> Path:
    """Render while one writer owns the run and all integrity bindings hold."""

    validate_input_integrity(root)
    intake = load_json(root / "run_intake.json")
    workbench = load_json(root / "content_workbench.json")
    recompute_contribution_digest(root)
    contribution = workbench["contribution"]
    if contribution["recommendation"] != "publish":
        raise ValueError("No visual rendering for no_publish recommendation")
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
    visuals_dir = root / "visuals"
    if (root / "visual_manifest.json").exists():
        raise ValueError(
            "Visual output already exists; supersede the contribution to render a new version"
        )
    visuals_dir.mkdir(exist_ok=True)
    entries: list[dict[str, Any]] = []

    slides = contribution["visual_story"]["slides"]
    for index, slide in enumerate(slides, start=1):
        output = visuals_dir / f"slide-{index:02d}.png"
        layout_validation = _render_slide(
            slide,
            index=index,
            total=len(slides),
            brand=brand,
            studio_name=studio_name,
            logo_path=logo,
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
                "layout_validation": layout_validation,
            }
        )

    circular = next(
        (
            draft
            for draft in contribution["channel_drafts"]
            if draft["channel"] == "client_circular"
        ),
        None,
    )
    if circular is not None:
        circular_path = visuals_dir / "circolare-clienti.pdf"
        _render_circular_pdf(
            circular,
            brand=brand,
            studio_profile=studio_profile,
            studio_name=studio_name,
            reference_date=intake["reference_date"],
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
                "layout_validation": {
                    "overflow_free": True,
                    "page_layout_engine": "reportlab_platypus",
                },
            }
        )

    preview = visuals_dir / "visual-preview.html"
    preview_title = contribution["visual_story"]["title"] or (
        circular["title"] if circular else studio_name
    )
    atomic_write_text(
        preview,
        _preview_html(entries, title=preview_title),
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
    manifest = {
        "schema_version": 1,
        "workflow": "comunicazione-professionale",
        "run_id": intake["run_id"],
        "contribution_digest": workbench["contribution_digest"],
        "rendered_at": utc_now(),
        "renderer": "deterministic_pillow_reportlab_v2",
        "font_assets": {name: file_digest(path) for name, path in FONT_PATHS.items()},
        "studio_profile_version": (
            intake["studio_profile"]["payload"]["version"]
            if proposal is None
            else "run_proposal"
        ),
        "outputs": entries,
    }
    manifest["manifest_digest"] = canonical_digest(manifest)
    return atomic_write_json(root / "visual_manifest.json", manifest)


def main(argv: list[str] | None = None) -> int:
    """Render accepted visuals."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        path = render_visuals(args.run_dir)
    except (OSError, ValueError) as exc:
        LOGGER.error("VISUAL_RENDER_FAILED: %s", exc)
        return 1
    LOGGER.info("Rendered visual package: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
