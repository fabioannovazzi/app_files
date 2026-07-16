from __future__ import annotations

from bs4 import BeautifulSoup  # type: ignore[import]

from src.slides.html_normalizer import normalizeSlideHtml, update_slide_document


def test_normalize_slide_html_adds_expected_structure() -> None:
    html = """<!DOCTYPE html><html><body><h1>Sample</h1><p>Alpha</p></body></html>"""

    normalized = normalizeSlideHtml(html)

    soup = BeautifulSoup(normalized, "html.parser")
    body = soup.body
    assert body is not None
    container = body.select_one(".slide-container")
    assert container is not None
    title_element = container.select_one('[data-role="title"]')
    assert title_element is not None
    assert title_element.get_text(strip=True) == "Sample"
    slide_body = container.select_one(".slide-body")
    assert slide_body is not None
    assert "<p>Alpha</p>" in slide_body.decode_contents()
    assert container.select_one("aside.slide-notes") is not None
    assert container.select_one("footer.slide-source") is not None


def test_normalize_slide_html_handles_leading_elements_before_body() -> None:
    html = (
        "<!DOCTYPE html><html><body>"
        '<div class="slide-container"><div class="banner"></div>'
        "<h1>Sample</h1><p>Alpha</p></div></body></html>"
    )

    normalized = normalizeSlideHtml(html)

    soup = BeautifulSoup(normalized, "html.parser")
    container = soup.body.select_one(".slide-container")
    assert container is not None
    slide_body = container.select_one(".slide-body")
    assert slide_body is not None
    banner = slide_body.select_one(".banner")
    assert banner is not None
    assert banner.parent is slide_body


def test_update_slide_document_preserves_scripts_and_updates_content() -> None:
    html = (
        "<!DOCTYPE html>\n"
        "<html><body>"
        '<div class="slide-container"><h1 data-role="title">Old</h1>'
        '<script id="chart">init();</script></div>'
        "</body></html>"
    )

    updated = update_slide_document(
        html,
        title_html="<span>New</span>",
        body_html="<p>Body</p>",
        notes_html="<p>Note</p>",
        source_html="",
    )

    soup = BeautifulSoup(updated, "html.parser")
    container = soup.body.select_one(".slide-container")
    assert container is not None
    title_element = container.select_one('[data-role="title"]')
    assert title_element is not None
    assert title_element.decode_contents() == "<span>New</span>"
    slide_body = container.select_one(".slide-body")
    assert slide_body is not None
    assert slide_body.decode_contents() == "<p>Body</p>"
    script = container.find("script", id="chart")
    assert script is not None
    assert script.parent is container
    notes = container.select_one("aside.slide-notes")
    assert notes is not None
    assert notes.decode_contents() == "<p>Note</p>"
    source = container.select_one("footer.slide-source")
    assert source is not None
    assert source.decode_contents() == ""
    document_title = soup.title.string if soup.title else ""
    assert document_title == "New"
