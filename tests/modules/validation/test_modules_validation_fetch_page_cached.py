from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_real_module(tmp_path: Path, monkeypatch):
    """Load the real module under a temporary home to avoid global I/O.

    We patch Path.home() before executing the module so its cache DB is placed
    under the per-test tmp directory. The module is loaded under a unique name
    to avoid interfering with other tests that may stub the package path.
    """
    # Ensure the module places its cache under tmp_path
    from pathlib import Path as _Path

    monkeypatch.setattr(_Path, "home", lambda: tmp_path)

    spec = importlib.util.spec_from_file_location(
        "_fpc_under_test", str(Path("modules/validation/fetch_page_cached.py").resolve())
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


def test_fetch_page_text_success_cleans_html_and_caches(tmp_path, monkeypatch):
    # Arrange: load real module with isolated cache DB
    m = _load_real_module(tmp_path, monkeypatch)

    # Stub network calls
    class Resp:
        def __init__(self, status_code: int, text: str = ""):
            self.status_code = status_code
            self.text = text

    html = (
        "<html><head><title>T</title><style>.x{}</style></head>"
        "<body>Visible <script>hidden()</script> content</body></html>"
    )
    monkeypatch.setattr(m.requests, "head", lambda url, **kw: Resp(200))
    monkeypatch.setattr(m.requests, "get", lambda url, **kw: Resp(200, html))

    # Act
    text, status = m.fetch_page_text("https://example.com")

    # Assert
    assert status == 200
    assert "Visible" in text
    assert "content" in text
    assert "hidden" not in text  # script/style removed
    # Cached value matches the cleaned text
    assert m._cache_get("https://example.com") == text


def test_fetch_page_text_uses_cache_without_network(tmp_path, monkeypatch):
    # Arrange: load real module with isolated cache DB and prefill
    m = _load_real_module(tmp_path, monkeypatch)
    url = "https://cached.example"
    m._cache_put(url, "cached text")

    # Any network call should fail the test if performed
    def _no_call(*args, **kwargs):  # pragma: no cover - should not be hit
        raise AssertionError("Network should not be called when cache hit")

    monkeypatch.setattr(m.requests, "head", _no_call)
    monkeypatch.setattr(m.requests, "get", _no_call)

    # Act
    text, status = m.fetch_page_text(url)

    # Assert
    assert status == 200
    assert text == "cached text"


def test_fetch_page_text_head_error_short_circuits_get(tmp_path, monkeypatch):
    # Arrange
    m = _load_real_module(tmp_path, monkeypatch)

    class Resp:
        def __init__(self, status_code: int):
            self.status_code = status_code

    monkeypatch.setattr(m.requests, "head", lambda url, **kw: Resp(404))

    def _no_get(*args, **kwargs):  # pragma: no cover - should not be hit
        raise AssertionError("GET should not be called after failing HEAD")

    monkeypatch.setattr(m.requests, "get", _no_get)

    # Act
    text, status = m.fetch_page_text("https://missing.example")

    # Assert
    assert text is None and status == 404


def test_fetch_page_text_network_exception_logs_and_returns_599(tmp_path, monkeypatch):
    # Arrange
    m = _load_real_module(tmp_path, monkeypatch)

    # Make HEAD raise a RequestException
    def _boom(url, **kw):  # pragma: no cover - inside function under test
        raise m.requests.RequestException("boom")

    monkeypatch.setattr(m.requests, "head", _boom)

    logged = {}

    def fake_write(*args, **kwargs):  # capture UI write call
        logged["args"] = args

    monkeypatch.setattr(m.ui, "write", fake_write)

    # Act
    text, status = m.fetch_page_text("https://error.example")

    # Assert
    assert text is None and status == 599
    assert logged.get("args") and str(logged["args"][0]).startswith("fetch_page_cached error:")


def test_fetch_page_text_caps_response_text_at_200kb(tmp_path, monkeypatch):
    # Arrange
    m = _load_real_module(tmp_path, monkeypatch)

    class Resp:
        def __init__(self, status_code: int, text: str = ""):
            self.status_code = status_code
            self.text = text

    long_text = "a" * 200_100
    html = f"<html><body><p>{long_text}</p></body></html>"
    monkeypatch.setattr(m.requests, "head", lambda url, **kw: Resp(200))
    monkeypatch.setattr(m.requests, "get", lambda url, **kw: Resp(200, html))

    # Act
    text, status = m.fetch_page_text("https://large.example")

    # Assert
    assert status == 200
    # Capped at or below 200 kB after stripping tags
    assert len(text) <= 200_000
    assert set(text) == {"a"}
