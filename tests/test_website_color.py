from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_reserves_blue_for_vera_and_clara() -> None:
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

    assert "--landing-blue:" not in css
    assert "--landing-blue-dark:" not in css
    assert (
        ".landing-home .landing-open-source__links a {\n"
        "  display: inline-flex;\n"
        "  align-items: center;\n"
        "  min-height: 44px;\n"
        "  border-bottom: 1px solid var(--landing-ink);\n"
        "  color: var(--landing-ink);" in css
    )
    assert (
        ".landing-home .landing-security__link {\n"
        "  display: inline-flex;\n"
        "  align-items: center;\n"
        "  gap: 10px;\n"
        "  min-height: 44px;\n"
        "  margin-top: clamp(34px, 4vw, 50px);\n"
        "  border-bottom: 1px solid var(--landing-ink);\n"
        "  color: var(--landing-ink);" in css
    )
    assert (
        ".landing-home .landing-product__link {\n"
        "  display: inline-flex;\n"
        "  align-items: center;\n"
        "  gap: 12px;\n"
        "  min-height: 44px;\n"
        "  margin-top: 30px;\n"
        "  border-bottom: 1px solid var(--landing-product-blue);\n"
        "  color: var(--landing-product-blue);" in css
    )
    assert (
        ".landing-home .landing-logo-link:focus-visible,\n"
        ".landing-home .landing-lang__link:focus-visible,\n"
        ".landing-home .landing-open-source__links a:focus-visible,\n"
        ".landing-home .landing-security__link:focus-visible {\n"
        "  outline: 2px solid var(--landing-ink);" in css
    )


def test_data_handling_page_uses_neutral_ink() -> None:
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

    assert "--data-blue:" not in css
    assert ".data-boundary__arrow {\n  color: var(--data-ink);" in css
    assert (
        ".data-boundary__exclusion {\n"
        "  grid-column: 1 / -1;\n"
        "  margin: 0;\n"
        "  padding: 22px 0 24px;\n"
        "  border-top: 1px solid var(--data-rule);\n"
        "  color: var(--data-ink);" in css
    )
    assert (
        ".data-resources__links a {\n"
        "  display: grid;\n"
        "  grid-template-columns: minmax(0, 1fr) auto;\n"
        "  gap: 18px;\n"
        "  align-items: center;\n"
        "  min-height: 58px;\n"
        "  border-bottom: 1px solid var(--data-rule);\n"
        "  color: var(--data-ink);" in css
    )
    assert (
        ".data-handling-closing {\n"
        "  margin: 0;\n"
        "  max-width: 17ch;\n"
        "  padding: clamp(92px, 12vw, 172px) 0;\n"
        "  color: var(--data-ink);" in css
    )
