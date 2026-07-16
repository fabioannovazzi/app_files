from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

__all__ = [
    "DEFAULT_PROMPT_STYLE_KEY",
    "NotebookLMStyle",
    "build_notebooklm_css_variables",
    "get_prompt_style_chart_palette",
    "get_available_prompt_style_keys",
    "load_notebooklm_style",
    "resolve_prompt_style_key",
]

_POINTS_PER_INCH = 72
_PIXELS_PER_INCH = 96
DEFAULT_PROMPT_STYLE_KEY = "uniform"
DEFAULT_PROMPT_STYLE_CHART_PALETTE = "greys"


@dataclass(frozen=True)
class NotebookLMStyle:
    """Typed representation of the shared NotebookLM typography tokens."""

    bg_color: str
    text_color: str
    font_family_primary: str
    font_family_fallback: str
    title_size_pt: float
    body_size_pt: float
    line_height: float
    text_align: str
    max_bullets_per_slide: int
    bullet_glyph: str
    bullet_indent_px: int
    bullet_gap_px: int


def _style_token_path() -> Path:
    return Path(__file__).resolve().parents[1] / "shared" / "notebooklm_style.json"


def _pt_to_px(pt: float) -> float:
    return (pt * _PIXELS_PER_INCH) / _POINTS_PER_INCH


def _normalize_style_map(
    payload: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    styles = payload.get("styles")
    if isinstance(styles, Mapping) and styles:
        normalized: dict[str, Mapping[str, object]] = {}
        for key, value in styles.items():
            if not isinstance(value, Mapping):
                continue
            normalized[str(key).strip().lower()] = value
        if normalized:
            return normalized
    return {DEFAULT_PROMPT_STYLE_KEY: payload}


def _resolve_default_key(
    payload: Mapping[str, object], styles: Mapping[str, Mapping[str, object]]
) -> str:
    default_key = payload.get("defaultKey")
    if isinstance(default_key, str):
        candidate = default_key.strip().lower()
        if candidate in styles:
            return candidate
    if DEFAULT_PROMPT_STYLE_KEY in styles:
        return DEFAULT_PROMPT_STYLE_KEY
    return next(iter(styles))


@lru_cache(maxsize=1)
def _load_style_config() -> tuple[str, dict[str, Mapping[str, object]]]:
    payload = json.loads(_style_token_path().read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("NotebookLM style tokens must be a JSON object.")
    styles = _normalize_style_map(payload)
    if not styles:
        raise ValueError("NotebookLM style tokens are empty.")
    default_key = _resolve_default_key(payload, styles)
    return default_key, styles


def get_available_prompt_style_keys() -> tuple[str, ...]:
    """Return the available prompt style keys declared in the shared tokens."""

    _, styles = _load_style_config()
    return tuple(styles.keys())


def resolve_prompt_style_key(prompt_style: str | None, *, strict: bool = False) -> str:
    """Resolve ``prompt_style`` to a known key falling back to the default style."""

    default_key, styles = _load_style_config()
    if prompt_style is None:
        return default_key
    candidate = prompt_style.strip().lower()
    if not candidate:
        return default_key
    if candidate in styles:
        return candidate
    if strict:
        available = ", ".join(sorted(styles))
        raise ValueError(
            f"Unknown prompt style '{prompt_style}'. Available: {available}"
        )
    return default_key


def _style_payload(style_key: str) -> Mapping[str, object]:
    _, styles = _load_style_config()
    return styles[style_key]


def get_prompt_style_chart_palette(
    prompt_style: str | None = None, *, strict: bool = False
) -> str:
    """Return the chart palette key associated with ``prompt_style``."""

    style_key = resolve_prompt_style_key(prompt_style, strict=strict)
    payload = _style_payload(style_key)
    raw_palette = str(payload.get("chartPalette") or "").strip().lower()
    return raw_palette or DEFAULT_PROMPT_STYLE_CHART_PALETTE


def load_notebooklm_style(prompt_style: str | None = None) -> NotebookLMStyle:
    """Load the NotebookLM style tokens resolved from ``prompt_style``."""

    style_key = resolve_prompt_style_key(prompt_style)
    payload = _style_payload(style_key)
    return NotebookLMStyle(
        bg_color=str(payload["bgColor"]),
        text_color=str(payload["textColor"]),
        font_family_primary=str(payload["fontFamilyPrimary"]),
        font_family_fallback=str(payload["fontFamilyFallback"]),
        title_size_pt=float(payload["titleSizePt"]),
        body_size_pt=float(payload["bodySizePt"]),
        line_height=float(payload["lineHeight"]),
        text_align=str(payload["textAlign"]),
        max_bullets_per_slide=int(payload["maxBulletsPerSlide"]),
        bullet_glyph=str(payload["bulletGlyph"]),
        bullet_indent_px=int(payload["bulletIndentPx"]),
        bullet_gap_px=int(payload["bulletGapPx"]),
    )


def build_notebooklm_css_variables(style: NotebookLMStyle) -> str:
    """Return a CSS variable block for NotebookLM typography tokens."""

    font_stack = (
        f'"{style.font_family_primary}", "{style.font_family_fallback}", sans-serif'
    )
    title_px = _pt_to_px(style.title_size_pt)
    body_px = _pt_to_px(style.body_size_pt)
    return (
        ":root {\n"
        f"  --notebooklm-bg-color: {style.bg_color};\n"
        f"  --notebooklm-text-color: {style.text_color};\n"
        f"  --notebooklm-font-stack: {font_stack};\n"
        f"  --notebooklm-title-size-px: {title_px:.2f}px;\n"
        f"  --notebooklm-body-size-px: {body_px:.2f}px;\n"
        f"  --notebooklm-line-height: {style.line_height};\n"
        "}\n"
    )
