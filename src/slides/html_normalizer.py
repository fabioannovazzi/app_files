from __future__ import annotations

import logging
from typing import Iterable

from bs4 import BeautifulSoup, Doctype, NavigableString, Tag  # type: ignore[import]

__all__ = ["normalizeSlideHtml", "update_slide_document"]

LOGGER = logging.getLogger(__name__)

_DEFAULT_DOCUMENT = (
    "<!DOCTYPE html>\n"
    "<html lang=\"en\">\n"
    "  <head>\n"
    "    <meta charset=\"utf-8\" />\n"
    "    <title></title>\n"
    "  </head>\n"
    "  <body>\n"
    "  </body>\n"
    "</html>\n"
)


def normalizeSlideHtml(html_text: str) -> str:
    """Return ``html_text`` normalised to the expected slide structure."""

    soup = BeautifulSoup(html_text or _DEFAULT_DOCUMENT, "html.parser")
    body = _ensure_body(soup)
    container = _ensure_slide_container(soup, body)
    title_element = _ensure_title(container)
    slide_body = _ensure_body_container(soup, container, title_element)
    _ensure_notes(container, soup)
    _ensure_source(container, soup)
    _tidy_container_children(container, {title_element, slide_body})
    _normalize_bullet_list(slide_body)
    return _serialize_document(soup)


def update_slide_document(
    html_text: str,
    *,
    title_html: str,
    body_html: str,
    notes_html: str,
    source_html: str,
) -> str:
    """Return ``html_text`` updated with the provided content fragments."""

    normalized = normalizeSlideHtml(html_text)
    soup = BeautifulSoup(normalized, "html.parser")
    body = _ensure_body(soup)
    container = _ensure_slide_container(soup, body)

    title_element = _ensure_title(container)
    if title_element is None:
        title_element = soup.new_tag("h1", attrs={"class": "slide-title", "data-role": "title"})
        container.insert(0, title_element)
    _set_inner_html(title_element, title_html)

    slide_body = _ensure_body_container(soup, container, title_element)
    _set_inner_html(slide_body, body_html)
    _normalize_bullet_list(slide_body)

    notes_element = _ensure_notes(container, soup)
    _set_inner_html(notes_element, notes_html)
    _apply_notes_overlay(container, notes_element, body_html=body_html, notes_html=notes_html)

    source_element = _ensure_source(container, soup)
    _set_inner_html(source_element, source_html)

    _update_document_title(soup, title_element)
    return _serialize_document(soup)


def _ensure_body(soup: BeautifulSoup) -> Tag:
    body = soup.body
    if body is None:
        body = soup.new_tag("body")
        html_el = soup.html
        if html_el is None:
            html_el = soup.new_tag("html", attrs={"lang": "en"})
            soup.append(html_el)
        html_el.append(body)
    return body


def _ensure_slide_container(soup: BeautifulSoup, body: Tag) -> Tag:
    containers = body.select(".slide-container")
    container: Tag
    if containers:
        container = containers[0]
        if len(containers) > 1:
            LOGGER.warning("Multiple .slide-container elements found; consolidating")
            for extra in containers[1:]:
                _move_children(extra, container)
                extra.decompose()
    else:
        LOGGER.debug("Creating missing .slide-container wrapper")
        container = soup.new_tag("div", attrs={"class": "slide-container"})
        for child in list(body.contents):
            container.append(child.extract())
        body.append(container)
    if container.parent is not body:
        container.extract()
        body.append(container)
    for child in list(body.contents):
        if child is container:
            continue
        if isinstance(child, NavigableString) and not child.strip():
            child.extract()
            continue
        container.append(child.extract())
    return container


def _ensure_title(container: Tag) -> Tag | None:
    title_element = container.select_one(".slide-title")
    if title_element is None:
        title_element = container.select_one(".title")
    if title_element is None:
        title_element = container.find(["h1", "h2"])
    if title_element is None:
        LOGGER.warning("Slide is missing a clear title element")
        return None
    for other in container.select('[data-role="title"]'):
        if other is title_element:
            continue
        del other.attrs["data-role"]
    title_element.attrs["data-role"] = "title"
    return title_element


def _ensure_body_container(
    soup: BeautifulSoup, container: Tag, title_element: Tag | None
) -> Tag:
    slide_body = container.select_one(".slide-body")
    if slide_body is not None:
        if slide_body.parent is not container:
            ancestor = slide_body.parent
            first_container_child: Tag | None = None
            while isinstance(ancestor, Tag) and ancestor is not container:
                first_container_child = ancestor
                ancestor = ancestor.parent
            if first_container_child is not None and ancestor is container:
                slide_body.extract()
                first_container_child.insert_before(slide_body)
        return slide_body
    if slide_body is None:
        slide_body = soup.new_tag("div", attrs={"class": "slide-body"})
        if title_element is not None:
            title_element.insert_after(slide_body)
        else:
            container.insert(0, slide_body)
    return slide_body


def _ensure_notes(container: Tag, soup: BeautifulSoup) -> Tag:
    notes = container.select_one("aside.slide-notes")
    if notes is None:
        notes = soup.new_tag("aside", attrs={"class": "slide-notes"})
        container.append(notes)
    return notes


def _apply_notes_overlay(
    container: Tag,
    notes: Tag,
    *,
    body_html: str,
    notes_html: str,
) -> None:
    if not notes_html:
        notes.attrs.pop("style", None)
        return
    container_style = container.get("style", "")
    if "position:" not in container_style:
        spacer = "" if not container_style or container_style.strip().endswith(";") else ";"
        container["style"] = f"{container_style}{spacer} position: relative;".strip()
    notes["style"] = (
        "position: absolute; "
        "left: 32px; "
        "right: 32px; "
        "bottom: 0; "
        "font-size: 12px; "
        "line-height: 1.4; "
        "color: #334155; "
    )


def _ensure_source(container: Tag, soup: BeautifulSoup) -> Tag:
    source = container.select_one("footer.slide-source")
    if source is None:
        source = soup.new_tag("footer", attrs={"class": "slide-source"})
        container.append(source)
    return source


def _tidy_container_children(container: Tag, preserved: Iterable[Tag | None]) -> None:
    preserved_tags = [item for item in preserved if item is not None]
    keep_ids = {id(item) for item in preserved_tags}
    slide_body = next(
        (item for item in preserved_tags if item and "slide-body" in (item.get("class") or [])),
        None,
    )
    for child in list(container.contents):
        if id(child) in keep_ids:
            continue
        if isinstance(child, Tag):
            classes = child.get("class", [])
            if "slide-notes" in classes or "slide-source" in classes:
                continue
            if child.name in {"script", "style"}:
                continue
        if isinstance(child, NavigableString) and not child.strip():
            child.extract()
            continue
        if slide_body is not None:
            slide_body.append(child.extract())


def _move_children(source: Tag, target: Tag) -> None:
    for child in list(source.contents):
        target.append(child.extract())


def _set_inner_html(tag: Tag, html_fragment: str) -> None:
    tag.clear()
    if not html_fragment:
        return
    fragment = BeautifulSoup(html_fragment, "html.parser")
    if fragment.body:
        nodes = list(fragment.body.contents)
    else:
        nodes = list(fragment.contents)
    for node in nodes:
        tag.append(node)


def _update_document_title(soup: BeautifulSoup, title_element: Tag | None) -> None:
    if title_element is None:
        return
    document_title = soup.title
    if document_title is None:
        head = soup.head
        if head is None:
            head = soup.new_tag("head")
            html_el = soup.html
            if html_el is None:
                html_el = soup.new_tag("html", attrs={"lang": "en"})
                soup.append(html_el)
            html_el.insert(0, head)
        document_title = soup.new_tag("title")
        head.append(document_title)
    document_title.string = title_element.get_text(strip=True)


def _serialize_document(soup: BeautifulSoup) -> str:
    parts: list[str] = []
    for item in soup.contents:
        if isinstance(item, Doctype):
            parts.append(f"<!DOCTYPE {item}>\n")
        else:
            parts.append(str(item))
    result = "".join(parts)
    if not result.endswith("\n"):
        result += "\n"
    return result


def _normalize_bullet_list(slide_body: Tag) -> None:
    if slide_body is None or slide_body.find(["ul", "ol"]):
        return
    bullet_lines: list[str] = []

    for child in list(slide_body.contents):
        if isinstance(child, NavigableString):
            bullet_lines.extend(_split_lines(str(child)))
            continue
        if not isinstance(child, Tag):
            return
        if child.name == "br":
            continue
        if child.name in {"p", "div", "span"} and not child.find(["ul", "ol"]):
            text = child.get_text("\n", strip=True)
            bullet_lines.extend(_split_lines(text))
            continue
        return

    bullets = _extract_bullets(bullet_lines)
    if not bullets:
        return

    list_tag = slide_body.new_tag("ul")
    for bullet in bullets:
        item = slide_body.new_tag("li")
        item.string = bullet
        list_tag.append(item)
    slide_body.clear()
    slide_body.append(list_tag)


def _split_lines(text: str) -> list[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract_bullets(lines: Iterable[str]) -> list[str]:
    bullets: list[str] = []
    for line in lines:
        if line.startswith("* "):
            bullets.append(line[2:].strip())
        elif line.startswith("- "):
            bullets.append(line[2:].strip())
        elif line.startswith("• "):
            bullets.append(line[2:].strip())
        else:
            return []
    return bullets
