from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT_SANS_STYLESHEET = (
    "https://fonts.googleapis.com/css2?"
    "family=Instrument+Sans:wght@400;500;600;700&display=swap"
)


@pytest.mark.parametrize(
    "template_name",
    [
        "base.html",
        "case_notes_voice.html",
        "hosted_interview.html",
        "hosted_interview_output.html",
    ],
)
def test_website_template_loads_instrument_sans(template_name: str) -> None:
    template = (ROOT / "templates" / template_name).read_text(encoding="utf-8")

    assert INSTRUMENT_SANS_STYLESHEET in template


def test_shared_app_css_applies_instrument_sans_to_native_controls() -> None:
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

    assert ':root {\n  font-family: "Instrument Sans", sans-serif;' in css
    assert (
        "button,\ninput,\noptgroup,\nselect,\ntextarea {\n"
        "  font-family: inherit;\n}" in css
    )
    assert 'font-family: "Inter"' not in css
    assert 'font-family: "Roboto"' not in css


def test_homepage_security_lead_uses_body_typography() -> None:
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

    assert (
        ".landing-home .landing-security__lead,\n"
        ".landing-home .landing-security__description {\n"
        "  margin: 0;\n"
        "  max-width: 49ch;\n"
        "  color: var(--landing-muted);\n"
        "  font-size: clamp(1.05rem, 1.5vw, 1.25rem);\n"
        "  line-height: 1.62;\n"
        "  letter-spacing: -0.02em;\n"
        "  text-wrap: pretty;\n"
        "}" in css
    )


def test_homepage_compliance_lead_uses_body_typography() -> None:
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

    assert (
        ".landing-home .landing-compliance__lead,\n"
        ".landing-home .landing-compliance__description,\n"
        ".landing-home .landing-compliance__closing {\n"
        "  margin: 0;\n"
        "  max-width: 51ch;\n"
        "  color: var(--landing-muted);\n"
        "  font-size: clamp(1.05rem, 1.5vw, 1.25rem);\n"
        "  line-height: 1.62;\n"
        "  letter-spacing: -0.02em;\n"
        "  text-wrap: pretty;\n"
        "}" in css
    )
    assert (
        ".landing-home .landing-compliance__lead {\n"
        "  color: var(--landing-ink);\n"
        "}" in css
    )


def test_homepage_design_headings_share_the_display_scale() -> None:
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
    desktop_selector = (
        ".landing-home .landing-open-source h2,\n"
        ".landing-home .landing-free h2,\n"
        ".landing-home .landing-security h2,\n"
        ".landing-home .landing-compliance h2,\n"
        ".landing-home .landing-bridge h2"
    )
    responsive_selector = (
        "  .landing-home .landing-open-source h2,\n"
        "  .landing-home .landing-free h2,\n"
        "  .landing-home .landing-security h2,\n"
        "  .landing-home .landing-compliance h2,\n"
        "  .landing-home .landing-bridge h2"
    )

    assert desktop_selector in css
    assert responsive_selector in css
    assert (
        ".landing-home .landing-section-heading h2,\n"
        ".landing-home .landing-bridge h2" not in css
    )
