import importlib
import json
import sys
from types import ModuleType

import pytest


def _install_playwright_stub(monkeypatch):
    """Provide minimal playwright stubs so the module can import."""
    pw_pkg = ModuleType("playwright")
    pw_pkg.__path__ = []  # mark as package
    pw_impl = ModuleType("playwright._impl")
    pw_impl.__path__ = []
    pw_errors = ModuleType("playwright._impl._errors")

    class DummyPlaywrightError(Exception):
        pass

    pw_errors.Error = DummyPlaywrightError
    pw_sync = ModuleType("playwright.sync_api")

    def sync_playwright():  # not used in these tests
        class _Dummy:
            def start(self):
                return self

            class chromium:  # pragma: no cover - defensive stub
                @staticmethod
                def launch(headless=True):
                    return None

        return _Dummy()

    pw_sync.sync_playwright = sync_playwright

    monkeypatch.setitem(sys.modules, "playwright", pw_pkg)
    monkeypatch.setitem(sys.modules, "playwright._impl", pw_impl)
    monkeypatch.setitem(sys.modules, "playwright._impl._errors", pw_errors)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", pw_sync)

    # readability (readability_lxml) may depend on optional lxml_html_clean; stub it
    rb = ModuleType("readability")

    class _Doc:
        def __init__(
            self, html
        ):  # pragma: no cover - used only in one test via monkeypatch
            self._html = html

        def summary(self):
            # Minimal valid HTML snippet
            return "<html><body>stub</body></html>"

    rb.Document = _Doc
    monkeypatch.setitem(sys.modules, "readability", rb)


def _import_layers(monkeypatch):
    """Import modules.validation.layers with required stubs installed."""
    _install_playwright_stub(monkeypatch)
    # Import fresh each time to avoid cross‑test state
    if "modules.validation.layers" in sys.modules:
        del sys.modules["modules.validation.layers"]
    return importlib.import_module("modules.validation.layers")


def test_readability_extract_returns_joined_plain_text(monkeypatch):
    """_readability_extract should join the plain text parts"""
    layers = _import_layers(monkeypatch)

    def fake_simple_json_from_html_string(html: str, use_readability: bool = True):
        return {"plain_text": [{"text": "Alpha"}, {"text": "Beta"}]}

    monkeypatch.setattr(
        layers.readability,
        "simple_json_from_html_string",
        fake_simple_json_from_html_string,
        raising=False,
    )

    result = layers._readability_extract("<html></html>")

    assert result == "Alpha Beta"


def test_try_sanity_no_pattern_returns_none(monkeypatch):
    layers = _import_layers(monkeypatch)

    def fake_fetch(url: str, **_):
        return "<html><body>No Sanity link here</body></html>"

    monkeypatch.setattr(layers, "_fetch", fake_fetch)

    out = layers.try_sanity("https://example.com", cite="abc-123")
    assert out is None


def test_try_sanity_extracts_text_when_result_found(monkeypatch):
    layers = _import_layers(monkeypatch)

    # Home contains a Sanity CDN URL we can parse (proj=abc123, dataset=prod)
    home_html = "<html>… https://abc123.apicdn.sanity.io/x/v1/data/query/prod …</html>"

    def fake_fetch(url: str, **_):
        if "?query=" in url:
            # Return a minimal Sanity result payload
            payload = {
                "result": [
                    {
                        "bodyHtml": "<p>Alpha</p>",
                        "sections": [{"bodyHtml": "<div>Beta</div>"}],
                    }
                ]
            }
            return json.dumps(payload)
        return home_html

    monkeypatch.setattr(layers, "_fetch", fake_fetch)

    out = layers.try_sanity("https://site.tld", cite="foo-1")
    assert out == "Alpha Beta"


def test_generic_html_fast_path_uses_readability_text(monkeypatch):
    layers = _import_layers(monkeypatch)

    monkeypatch.setattr(
        layers, "_fetch", lambda url: "<html><body>irrelevant</body></html>"
    )
    # Ensure fast‑path is taken and postprocessed
    monkeypatch.setattr(layers, "_readability_extract", lambda html: " Hello   World\n")

    out = layers.generic_html("https://example.com/page", min_len=5)
    assert out == "Hello World"


def test_generic_html_fallback_to_simple_strip_when_lxml_fails(monkeypatch):
    layers = _import_layers(monkeypatch)

    html_doc = """
        <html><header>head</header>
        <body><script>bad()</script><div> Ok   Text </div></body></html>
    """
    monkeypatch.setattr(layers, "_fetch", lambda url: html_doc)
    monkeypatch.setattr(layers, "_readability_extract", lambda html: "")

    class BoomDoc:  # replaces readability-lxml Document
        def __init__(self, html):
            self._html = html

        def summary(self):  # force the except path
            raise RuntimeError("boom")

    monkeypatch.setattr(layers, "Document", BoomDoc)

    out = layers.generic_html("https://example.com/article", min_len=5)
    assert out == "Ok Text"


def test_generic_html_returns_none_for_non_html_content(monkeypatch):
    layers = _import_layers(monkeypatch)
    monkeypatch.setattr(layers, "_fetch", lambda url: "TITLE: not html")
    assert layers.generic_html("https://example.com/raw") is None


def test_try_pdf_limits_pages_and_returns_text(monkeypatch):
    layers = _import_layers(monkeypatch)

    class Resp:
        headers = {"Content-Type": "application/pdf"}
        content = b"%PDF-1.5 ..."

        def raise_for_status(self):
            return None

    monkeypatch.setattr(layers.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(layers, "extract_pdf_rich", lambda _: "p1\f p2\f p3")

    out = layers.try_pdf("https://example.com/doc.pdf", max_pages=2)
    assert out == "p1\n\n p2"


@pytest.mark.parametrize(
    "url,content_type",
    [
        ("https://example.com/not.txt", "application/pdf"),  # wrong extension
        ("https://example.com/file.pdf", "text/html"),  # not a PDF response
    ],
)
def test_try_pdf_negative_cases_return_none(monkeypatch, url, content_type):
    layers = _import_layers(monkeypatch)

    class Resp:
        headers = {"Content-Type": content_type}
        content = b"dummy"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(layers.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(layers, "extract_pdf_rich", lambda *_: "text")

    assert layers.try_pdf(url) is None
