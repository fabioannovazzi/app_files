from __future__ import annotations

from pathlib import Path

import pytest

from modules.pdp.api import _get_landing_page_content


@pytest.mark.parametrize(
    ("lang", "title"),
    [
        ("en", "Compliant by design."),
        ("it", "Conformità per progettazione."),
        ("fr", "Conformes par conception."),
        ("de", "Compliance by Design."),
    ],
)
def test_homepage_content_includes_localized_compliance_section(
    lang: str, title: str
) -> None:
    content = _get_landing_page_content(lang)["compliance"]

    assert content["id"] == "compliance"
    assert content["title"] == title
    assert len(content["principles"]) == 3
    assert content["cta_href"] == "/data-handling"
    assert "Mparanza" not in content["closing"]


def test_homepage_content_states_the_llm_context_boundary_honestly() -> None:
    content = _get_landing_page_content("en")["compliance"]

    assert "what reaches the model" in content["lead"]
    assert "may enter the LLM context" in content["principles"][2]["blurb"]
    assert "No additional data-processing intermediary" in content["closing"]


def test_homepage_template_places_compliance_after_security_before_plugins() -> None:
    template = Path("templates/index.html").read_text(encoding="utf-8")

    assert template.index("{% if security %}") < template.index("{% if compliance %}")
    assert template.index("{% if compliance %}") < template.index("{% if bridge %}")
    assert 'class="landing-compliance__principles"' in template
