"""Read passive HTML output as escaped, static document structure."""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

__all__ = ["passive_html_body"]

_TAGS = frozenset(
    "html head body title meta style main header footer section article aside nav div span p h1 h2 h3 h4 h5 h6 figure figcaption table caption colgroup col thead tbody tfoot tr th td ul ol li dl dt dd details summary strong b em i small pre code blockquote br hr a sup sub time".split()
)
_ATTRS = frozenset(
    "id class style lang dir title role scope colspan rowspan span start value open datetime width height tabindex data-output-language".split()
)
_LOCAL_AUDIT_LINK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.(?:json|md|csv|txt)\Z")
_READING_CLASSES = frozenset(
    {
        "meta",
        "code",
        "refs",
        "narrative",
        "amount",
        "small",
        "verdict",
        "claim-meta",
        "table-scroll",
    }
)


class _PassiveHTML(HTMLParser):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _TAGS:
            raise ValueError(
                "Unsupported result format: HTML must be a passive document"
            )
        values = dict(attrs)
        if tag == "meta":
            if not (
                "charset" in values
                or values.get("name", "").lower() in {"viewport", "color-scheme"}
                or values.get("http-equiv", "").lower() == "content-security-policy"
            ):
                raise ValueError("Unsupported result format: active HTML metadata")
            if set(values) - {"charset", "name", "http-equiv", "content"}:
                raise ValueError("Unsupported result format: active HTML metadata")
            return
        for name, value in attrs:
            if (
                tag == "a"
                and name == "href"
                and (
                    (value or "").startswith("#")
                    or _LOCAL_AUDIT_LINK.fullmatch(value or "")
                )
            ):
                continue
            if name not in _ATTRS and not name.startswith("aria-"):
                raise ValueError("Unsupported result format: active HTML attribute")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


class _ReadingHTML(_PassiveHTML):
    def __init__(
        self, *, omit_controls: bool = False, report_metadata: bool = False
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed = 0
        self.anchor_tags: list[str] = []
        self.omit_controls = omit_controls
        self.report_metadata = report_metadata
        self.omitted: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Some compiled reports include print controls and embedded payloads.
        # The reading copy omits them entirely; it never executes their code.
        if self.omitted:
            if tag == self.omitted[-1]:
                self.omitted.append(tag)
            return
        if self.omit_controls and tag in {"script", "button"}:
            self.omitted.append(tag)
            return
        if self.report_metadata:
            # Native analytical reports carry audit identifiers and product
            # links. Keep their text, but do not activate external navigation
            # or carry metadata into the passive reading copy.
            external_link = tag == "a" and (dict(attrs).get("href") or "").startswith(
                ("https://", "http://")
            )
            attrs = [
                (name, value)
                for name, value in attrs
                if not name.startswith("data-")
                and not (external_link and name in {"href", "target", "rel"})
            ]
        super().handle_starttag(tag, attrs)
        if tag in {"head", "style", "title"}:
            self.suppressed += 1
        if self.suppressed or tag in {"html", "body", "meta"}:
            return
        href = dict(attrs).get("href") or ""
        if tag == "a":
            tag = "a" if href.startswith("#") else "span"
            self.anchor_tags.append(tag)
        tag = {"main": "div"}.get(tag, tag)
        safe = []
        for name, value in attrs:
            if name == "class":
                classes = [
                    "html-" + token
                    for token in (value or "").split()
                    if token in _READING_CLASSES
                ]
                if classes:
                    safe.append(f" class='{' '.join(classes)}'")
            elif name == "id" and value:
                safe.append(f" id='html-result-{escape(value, quote=True)}'")
            elif tag == "a" and name == "href":
                safe.append(f" href='#html-result-{escape(href[1:], quote=True)}'")
            elif (
                name in {"colspan", "rowspan", "span", "start", "value"}
                and (value or "").isdigit()
            ):
                safe.append(f" {name}='{escape(value or '', quote=True)}'")
            elif name == "scope" and value in {"row", "col", "rowgroup", "colgroup"}:
                safe.append(f" scope='{value}'")
            elif tag == "details" and name == "open":
                safe.append(" open")
            elif name == "tabindex" and value in {"0", "-1"}:
                safe.append(f" tabindex='{value}'")
            elif name == "role" and value == "region":
                safe.append(" role='region'")
            elif name == "aria-labelledby" and value:
                ids = " ".join("html-result-" + token for token in value.split())
                safe.append(f" aria-labelledby='{escape(ids, quote=True)}'")
        self.parts.append(f"<{tag}{''.join(safe)}>")

    def handle_endtag(self, tag: str) -> None:
        if self.omitted:
            if tag == self.omitted[-1]:
                self.omitted.pop()
            return
        if tag in {"head", "style", "title"}:
            self.suppressed = max(0, self.suppressed - 1)
            return
        if self.suppressed or tag in {"html", "body", "meta", "br", "hr", "col"}:
            return
        if tag in _TAGS:
            if tag == "a":
                tag = self.anchor_tags.pop() if self.anchor_tags else "span"
            tag = {"main": "div"}.get(tag, tag)
            self.parts.append(f"</{tag}>")
            if self.report_metadata and tag in {"span", "strong"}:
                self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.suppressed and not self.omitted:
            self.parts.append(escape(data))


def passive_html_body(
    text: str, *, omit_controls: bool = False, report_metadata: bool = False
) -> str:
    """Preserve text and tables; never include scripts, styles or active attributes."""
    parser = _ReadingHTML(omit_controls=omit_controls, report_metadata=report_metadata)
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)
