from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from src.slides.models import Deck, Slide
from src.slides.pptx_post_render import apply_post_render_compare_loop
from src.slides.semantic_pptx import SlidesPptxSlide, SlidesPptxSpec


def _make_png(path: Path, *, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (960, 540), color).save(path)


def test_apply_post_render_compare_loop_promotes_implication_and_rerenders(
    tmp_path: Path,
    monkeypatch,
) -> None:
    deck_path = tmp_path / "deckA"
    asset_path = deck_path / "assets" / "slide1.png"
    _make_png(asset_path, color=(255, 255, 255))
    deck = Deck(
        deck_id="deckA",
        slides=[
            Slide(
                id="slide1.html",
                title_html="",
                body_html="<img src='/slides/deck/deckA/assets/slide1.png' />",
            )
        ],
    )
    spec = SlidesPptxSpec(
        template_key="uniform",
        prompt_style="uniform",
        slides=[
            SlidesPptxSlide(
                slide_id="slide1.html",
                kind="text_visual",
                layout_variant="text_visual_bottom",
                title="Long operating model title",
                body="Intro paragraph.\n\nIMPLICATION: Keep the Italian pilots first.",
                visual_path="assets/slide1.png",
                visual_type="figure",
            )
        ],
    )
    pptx_path = deck_path / "export.pptx"
    pptx_path.parent.mkdir(parents=True, exist_ok=True)
    pptx_path.write_bytes(b"initial-pptx")
    written_specs: list[SlidesPptxSpec] = []
    render_calls: list[Path] = []
    raster_calls: list[Path] = []

    def _fake_rasterize(input_path: Path, output_dir: Path, **_: object) -> list[Path]:
        raster_calls.append(output_dir)
        rendered_path = output_dir / "slide-1.png"
        _make_png(rendered_path, color=(240, 240, 240))
        return [rendered_path]

    responses = [
        [
            {
                "status": "repairable",
                "summary": "Title is too large and implication should be in the bottom banner.",
                "issues": ["title_too_large", "implication_misplaced", "visual_too_small"],
                "repairs": {
                    "titleScale": 0.82,
                    "visualScale": 1.12,
                    "visualAnchor": "top",
                    "layoutVariantOverride": "text_visual_right",
                    "promoteTrailingImplication": True,
                },
            }
        ],
        [
            {
                "status": "ok",
                "summary": "Rendered slide matches the source closely enough.",
                "issues": [],
                "repairs": {},
            }
        ],
    ]

    monkeypatch.setattr(
        "src.slides.pptx_post_render.rasterize_presentation_to_pngs",
        _fake_rasterize,
    )
    monkeypatch.setattr(
        "src.slides.pptx_post_render._build_local_llm_wrapper",
        lambda: object(),
    )
    monkeypatch.setattr(
        "src.slides.pptx_post_render.run_step_json",
        lambda *_args, **_kwargs: responses.pop(0),
    )
    monkeypatch.setattr(
        "src.slides.pptx_post_render.write_slides_pptx_spec",
        lambda _deck_path, repaired_spec: written_specs.append(repaired_spec) or (_deck_path / "slides_pptx_spec.json"),
    )
    monkeypatch.setattr(
        "src.slides.pptx_post_render.render_slides_pptx_from_template",
        lambda rendered_deck_path: render_calls.append(rendered_deck_path) or io.BytesIO(b"repaired-pptx"),
    )

    repaired_spec, report = apply_post_render_compare_loop(
        deck=deck,
        deck_path=deck_path,
        spec=spec,
        pptx_path=pptx_path,
        job_id="job-123",
    )

    assert repaired_spec.slides[0].layout_variant == "text_visual_right"
    assert repaired_spec.slides[0].implication == "IMPLICATION: Keep the Italian pilots first."
    assert repaired_spec.slides[0].body == "Intro paragraph."
    assert repaired_spec.slides[0].repair_hints["title_scale"] == 0.82
    assert repaired_spec.slides[0].repair_hints["visual_scale"] == 1.12
    assert repaired_spec.slides[0].repair_hints["visual_anchor"] == "top"
    assert written_specs and written_specs[0] == repaired_spec
    assert render_calls == [deck_path]
    assert pptx_path.read_bytes() == b"repaired-pptx"
    assert len(report["iterations"]) == 2
    assert report["appliedRepairs"] == [
        {
            "slideId": "slide1.html",
            "repairs": {
                "layout_variant_override": "text_visual_right",
                "title_scale": 0.82,
                "body_scale": 1.0,
                "visual_scale": 1.12,
                "visual_anchor": "top",
                "banner_scale": 1.0,
                "promote_trailing_implication": True,
                "promote_trailing_footer": False,
            },
            "issues": ["title_too_large", "implication_misplaced", "visual_too_small"],
            "summary": "Title is too large and implication should be in the bottom banner.",
        }
    ]
    report_path = deck_path / "pptx_post_render" / "job-123" / "report.json"
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["jobId"] == "job-123"
    assert raster_calls == [
        deck_path / "pptx_post_render" / "job-123" / "initial",
        deck_path / "pptx_post_render" / "job-123" / "final",
    ]


def test_apply_post_render_compare_loop_writes_error_report_when_skipped(
    tmp_path: Path,
    monkeypatch,
) -> None:
    deck_path = tmp_path / "deckB"
    deck = Deck(deck_id="deckB", slides=[])
    spec = SlidesPptxSpec(template_key="uniform", prompt_style="uniform", slides=[])
    pptx_path = deck_path / "export.pptx"
    pptx_path.parent.mkdir(parents=True, exist_ok=True)
    pptx_path.write_bytes(b"pptx")

    monkeypatch.setattr(
        "src.slides.pptx_post_render.rasterize_presentation_to_pngs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no rasterizer")),
    )

    repaired_spec, report = apply_post_render_compare_loop(
        deck=deck,
        deck_path=deck_path,
        spec=spec,
        pptx_path=pptx_path,
        job_id="job-456",
    )

    assert repaired_spec == spec
    assert report["error"] == "no rasterizer"
    report_path = deck_path / "pptx_post_render" / "job-456" / "report.json"
    assert report_path.exists()
