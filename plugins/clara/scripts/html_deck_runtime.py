"""Shared fixed-format HTML deck runtime for Clara outputs."""

from __future__ import annotations

import re

__all__ = [
    "apply_fixed_16_9_deck_runtime",
    "apply_html_deck_runtime",
    "assert_fixed_16_9_deck_runtime",
    "assert_html_deck_runtime",
    "fixed_16_9_deck_css",
    "fixed_16_9_deck_js",
]

_DECK_CLASS = "clara-fixed-16-9-deck"
_DECK_MARKER = 'data-clara-fixed-16-9-deck="true"'
_RUNTIME_VERSION = "2"
_PROFILES = {"stacked", "stage"}


def fixed_16_9_deck_css() -> str:
    """Return CSS for stacked pages and immersive fixed-stage decks."""

    return """
    :root {
      --clara-deck-width: min(1120px, calc(100vw - 40px));
    }
    main.clara-fixed-16-9-deck:not([data-clara-deck-mode="stage"]) {
      width: var(--clara-deck-width);
      margin: 24px auto 48px;
      padding: 0;
      display: grid;
      gap: 28px;
    }
    main.clara-fixed-16-9-deck:not([data-clara-deck-mode="stage"]) > section {
      width: 100%;
      min-height: auto;
      aspect-ratio: 16 / 9;
      padding: clamp(24px, 4vw, 40px);
      overflow: hidden;
      display: grid;
      align-content: center;
    }
    main.clara-fixed-16-9-deck[data-clara-deck-mode="stage"] {
      position: fixed;
      top: 50%;
      left: 50%;
      width: var(--clara-deck-width);
      height: calc(var(--clara-deck-width) * .5625);
      margin: 0;
      padding: 0;
      display: block;
      overflow: hidden;
      overflow: clip;
      transform: translate(-50%, -50%);
    }
    main.clara-fixed-16-9-deck[data-clara-deck-mode="stage"] > section {
      width: 100%;
      height: 100%;
      min-height: 0;
      aspect-ratio: auto;
      padding: 0;
      overflow: hidden;
      display: block;
    }
    main.clara-fixed-16-9-deck svg {
      max-width: 100%;
      max-height: 100%;
    }
    @media (max-width: 820px) {
      :root {
        --clara-deck-width: calc(100vw - 24px);
      }
      main.clara-fixed-16-9-deck:not([data-clara-deck-mode="stage"]) {
        margin: 12px auto 28px;
        gap: 14px;
      }
      main.clara-fixed-16-9-deck:not([data-clara-deck-mode="stage"]) > section {
        padding: 22px;
      }
    }
"""


def fixed_16_9_deck_js() -> str:
    """Return JavaScript for fixed geometry and active-slide capture metadata."""

    return """
(() => {
  const DECK_SELECTOR = 'main.clara-fixed-16-9-deck';
  const HANDLE_SOURCE = 'clara_html_deck';
  const RATIO = 16 / 9;
  const MAX_WIDTH = 1120;
  let lastCaptureHandle = '';
  let slideContextFrame = null;

  function fitDeckToViewport() {
    const deck = document.querySelector(DECK_SELECTOR);
    if (!deck) return;
    const stageProfile = deck.dataset.claraDeckMode === 'stage';
    const mobile = window.matchMedia('(max-width: 820px)').matches;
    const sidePad = stageProfile ? 0 : (mobile ? 24 : 40);
    const verticalReserve = stageProfile ? 0 : (mobile ? 40 : 96);
    const viewportWidth = Math.max(240, window.innerWidth - sidePad);
    const viewportHeight = Math.max(135, window.innerHeight - verticalReserve);
    const widthFromHeight = viewportHeight * RATIO;
    const widthCap = stageProfile ? viewportWidth : (mobile ? viewportWidth : MAX_WIDTH);
    const width = Math.floor(Math.max(240, Math.min(viewportWidth, widthFromHeight, widthCap)));
    document.documentElement.style.setProperty('--clara-deck-width', `${width}px`);
  }

  function preserveSvgAspectRatio() {
    document.querySelectorAll(`${DECK_SELECTOR} svg`).forEach((svg) => {
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    });
  }

  function cleanContextText(value, maxLength) {
    return String(value || '').replace(/\\s+/g, ' ').trim().slice(0, maxLength);
  }

  function deckSlides(deck) {
    return Array.from(deck.children).filter((element) => element.matches('section'));
  }

  function activeSlide(slides) {
    const declared = slides.find((slide) =>
      slide.dataset.active === 'true' ||
      slide.classList.contains('is-active') ||
      slide.getAttribute('aria-hidden') === 'false'
    );
    if (declared) return declared;
    const viewportCenter = window.innerHeight / 2;
    return slides.reduce((best, candidate) => {
      const rect = candidate.getBoundingClientRect();
      if (rect.height <= 0) return best;
      const distance = Math.abs(rect.top + rect.height / 2 - viewportCenter);
      if (!best || distance < best.distance) return { element: candidate, distance };
      return best;
    }, null)?.element || null;
  }

  function publishActiveSlideContext() {
    slideContextFrame = null;
    const setCaptureHandleConfig = navigator.mediaDevices?.setCaptureHandleConfig;
    if (typeof setCaptureHandleConfig !== 'function') return;
    const deck = document.querySelector(DECK_SELECTOR);
    if (!deck) return;
    const slides = deckSlides(deck);
    const slide = activeSlide(slides);
    if (!slide) return;
    const slideIndex = slides.indexOf(slide);
    const slideId = cleanContextText(
      slide.dataset.slideId || slide.id || `slide-${slideIndex + 1}`,
      120
    );
    if (!slide.id) slide.id = slideId;
    slide.dataset.claraSlideId = slideId;
    const heading = slide.querySelector('h1, h2, h3, [data-slide-title]');
    const slideTitle = cleanContextText(
      slide.dataset.slideTitle || slide.dataset.title || heading?.textContent || slide.getAttribute('aria-label'),
      240
    );
    const handle = JSON.stringify({
      schema_version: 1,
      source: HANDLE_SOURCE,
      deck_title: cleanContextText(document.title, 160),
      slide_id: slideId,
      slide_title: slideTitle,
      slide_index: slideIndex,
      slide_number: slideIndex + 1,
    });
    if (handle === lastCaptureHandle) return;
    try {
      navigator.mediaDevices.setCaptureHandleConfig({
        handle,
        exposeOrigin: false,
        permittedOrigins: ['*'],
      });
      lastCaptureHandle = handle;
    } catch (error) {
      console.warn('Clara active-slide metadata is unavailable', error);
    }
  }

  function scheduleActiveSlideContext() {
    if (slideContextFrame !== null) return;
    slideContextFrame = window.requestAnimationFrame(publishActiveSlideContext);
  }

  function observeActiveSlideContext() {
    const deck = document.querySelector(DECK_SELECTOR);
    if (!deck) return;
    const slides = deckSlides(deck);
    if ('IntersectionObserver' in window && deck.dataset.claraDeckMode !== 'stage') {
      const observer = new IntersectionObserver(scheduleActiveSlideContext, {
        threshold: [0.25, 0.5, 0.75],
      });
      slides.forEach((slide) => observer.observe(slide));
    }
    if ('MutationObserver' in window) {
      const observer = new MutationObserver(scheduleActiveSlideContext);
      slides.forEach((slide) => observer.observe(slide, {
        attributes: true,
        attributeFilter: ['class', 'aria-hidden', 'data-active'],
      }));
    }
    scheduleActiveSlideContext();
  }

  function initFixedDeckRuntime() {
    preserveSvgAspectRatio();
    fitDeckToViewport();
    observeActiveSlideContext();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFixedDeckRuntime, { once: true });
  } else {
    initFixedDeckRuntime();
  }
  ['resize', 'orientationchange', 'fullscreenchange'].forEach((eventName) => {
    window.addEventListener(eventName, () => {
      fitDeckToViewport();
      scheduleActiveSlideContext();
    });
  });
  ['scroll', 'hashchange', 'clara:slidechange'].forEach((eventName) => {
    window.addEventListener(eventName, scheduleActiveSlideContext, { passive: true });
    document.addEventListener(eventName, scheduleActiveSlideContext, { passive: true });
  });
})();
"""


def apply_html_deck_runtime(html_text: str, *, profile: str = "auto") -> str:
    """Add Clara's versioned runtime to a stacked or stage HTML deck."""

    resolved = _resolve_profile(html_text, profile)
    existing = _runtime_profile(html_text)
    if existing:
        if existing != resolved:
            raise ValueError(
                f"HTML deck already contains the {existing!r} runtime, not {resolved!r}"
            )
        assert_html_deck_runtime(html_text, label="HTML deck", profile=resolved)
        return html_text

    with_deck_marker = _ensure_main_deck_marker(html_text, profile=resolved)
    style = (
        f'\n<style data-clara-deck-runtime="true" '
        f'data-clara-runtime-version="{_RUNTIME_VERSION}" '
        f'data-clara-runtime-profile="{resolved}">\n'
        f"{fixed_16_9_deck_css()}</style>\n"
    )
    with_css = _insert_before_closing_tag(with_deck_marker, "head", style)
    script = (
        f'\n<script data-clara-deck-runtime="true" '
        f'data-clara-runtime-version="{_RUNTIME_VERSION}" '
        f'data-clara-runtime-profile="{resolved}">\n'
        f"{fixed_16_9_deck_js()}</script>\n"
    )
    rendered = _insert_before_closing_tag(with_css, "body", script)
    assert_html_deck_runtime(rendered, label="HTML deck", profile=resolved)
    return rendered


def apply_fixed_16_9_deck_runtime(html_text: str) -> str:
    """Backward-compatible alias that applies the stacked runtime."""

    return apply_html_deck_runtime(html_text, profile="stacked")


def assert_html_deck_runtime(
    html_text: str,
    *,
    label: str,
    profile: str | None = None,
) -> None:
    """Raise when a Clara HTML deck is missing profile-compatible invariants."""

    actual_profile = _runtime_profile(html_text)
    missing: list[str] = []
    if _DECK_MARKER not in html_text:
        missing.append("deck marker")
    if _DECK_CLASS not in html_text:
        missing.append("fixed deck class")
    if actual_profile is None:
        missing.append("versioned runtime style/script markers")
    if profile and actual_profile and actual_profile != profile:
        missing.append(f"{profile} profile (found {actual_profile})")
    if "aspect-ratio: 16 / 9" not in html_text:
        missing.append("16:9 slide aspect ratio")
    if "--clara-deck-width" not in html_text:
        missing.append("viewport-derived deck width")
    if "widthFromHeight" not in html_text or "Math.min(viewportWidth" not in html_text:
        missing.append("width/height fit calculation")
    if "preserveAspectRatio" not in html_text or "xMidYMid meet" not in html_text:
        missing.append("SVG aspect-ratio preservation")
    if "setCaptureHandleConfig" not in html_text or "clara_html_deck" not in html_text:
        missing.append("active-slide capture metadata")
    if "slide_id" not in html_text or "slide_title" not in html_text:
        missing.append("active slide id/title fields")
    if profile == "stage" or actual_profile == "stage":
        if 'data-clara-deck-mode="stage"' not in html_text:
            missing.append("stage deck marker")
        if "is-active" not in html_text or "aria-hidden" not in html_text:
            missing.append("stage active-slide resolution")
        if "MutationObserver" not in html_text or "clara:slidechange" not in html_text:
            missing.append("stage slide-change observation")
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"{label} is missing Clara HTML deck runtime invariants: {joined}")


def assert_fixed_16_9_deck_runtime(html_text: str, *, label: str) -> None:
    """Backward-compatible assertion for the stacked fixed-format runtime."""

    assert_html_deck_runtime(html_text, label=label, profile="stacked")


def _resolve_profile(html_text: str, profile: str) -> str:
    normalized = "stacked" if profile == "stack" else profile
    if normalized == "auto":
        normalized = "stage" if re.search(
            r'<main\b[^>]*data-clara-deck-mode=["\']stage["\']',
            html_text,
            flags=re.IGNORECASE,
        ) else "stacked"
    if normalized not in _PROFILES:
        raise ValueError(f"Unsupported Clara HTML deck profile: {profile!r}")
    return normalized


def _runtime_profile(html_text: str) -> str | None:
    style_match = re.search(
        rf'<style\b[^>]*data-clara-deck-runtime=["\']true["\'][^>]*'
        rf'data-clara-runtime-version=["\']{_RUNTIME_VERSION}["\'][^>]*'
        r'data-clara-runtime-profile=["\'](stacked|stage)["\'][^>]*>',
        html_text,
        flags=re.IGNORECASE,
    )
    script_match = re.search(
        rf'<script\b[^>]*data-clara-deck-runtime=["\']true["\'][^>]*'
        rf'data-clara-runtime-version=["\']{_RUNTIME_VERSION}["\'][^>]*'
        r'data-clara-runtime-profile=["\'](stacked|stage)["\'][^>]*>',
        html_text,
        flags=re.IGNORECASE,
    )
    if not style_match or not script_match:
        return None
    if style_match.group(1).lower() != script_match.group(1).lower():
        raise ValueError("Clara runtime style and script profiles do not match")
    return style_match.group(1).lower()


def _ensure_main_deck_marker(html_text: str, *, profile: str) -> str:
    main_match = re.search(r"<main(?P<attrs>[^>]*)>", html_text, flags=re.IGNORECASE)
    if not main_match:
        raise ValueError("HTML deck is missing a <main> element")
    attrs = main_match.group("attrs")
    updated_attrs = attrs
    if _DECK_MARKER not in attrs:
        updated_attrs += f" {_DECK_MARKER}"
    class_match = re.search(r'class=(?P<quote>["\'])(?P<value>.*?)(?P=quote)', updated_attrs)
    if class_match:
        classes = class_match.group("value").split()
        if _DECK_CLASS not in classes:
            classes.append(_DECK_CLASS)
        class_attr = f'class={class_match.group("quote")}{" ".join(classes)}{class_match.group("quote")}'
        updated_attrs = (
            updated_attrs[: class_match.start()]
            + class_attr
            + updated_attrs[class_match.end() :]
        )
    else:
        updated_attrs += f' class="{_DECK_CLASS}"'
    mode_match = re.search(
        r'data-clara-deck-mode=(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
        updated_attrs,
        flags=re.IGNORECASE,
    )
    if mode_match:
        existing_mode = mode_match.group("value").lower()
        if existing_mode != profile:
            raise ValueError(
                f"Deck declares data-clara-deck-mode={existing_mode!r}, not {profile!r}"
            )
    else:
        updated_attrs += f' data-clara-deck-mode="{profile}"'
    return (
        html_text[: main_match.start()]
        + f"<main{updated_attrs}>"
        + html_text[main_match.end() :]
    )


def _insert_before_closing_tag(html_text: str, tag_name: str, insertion: str) -> str:
    closing_tag = f"</{tag_name}>"
    index = html_text.lower().rfind(closing_tag)
    if index == -1:
        raise ValueError(f"HTML deck is missing {closing_tag}")
    return html_text[:index] + insertion + html_text[index:]
