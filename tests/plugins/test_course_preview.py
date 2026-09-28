"""Exercise the real loopback preview and its asset boundary."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))
from courseware.preview import create_server


@pytest.fixture
def preview(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    kit = tmp_path / "kit with spaces"
    kit.mkdir()
    (kit / "course.html").write_text("<link rel='stylesheet' href='course.css'>")
    (kit / "course.css").write_text("body { color: blue; }")
    (kit / "fonts").mkdir()
    (kit / "fonts/test.woff2").write_bytes(b"font fixture")
    (kit / "files").mkdir()
    (kit / "files/input.csv").write_text("amount\n12\n")
    (kit / "files/result.xlsx").write_bytes(b"\x00\xffnative document bytes")
    (kit / "outputs").mkdir()
    (kit / "outputs/preview.html").write_text("<h1>Invoice</h1>")
    (kit / "decks").mkdir()
    (kit / "decks/result.html").write_text(
        "<h1>Deck</h1><script>/* verified fixture */</script>"
    )
    (kit / "outputs/invoice.xml").write_bytes(
        b"<Invoice><Total>244.00</Total></Invoice>"
    )
    outside = tmp_path / "private.txt"
    outside.write_text("outside kit")
    (kit / "escape").symlink_to(outside)
    with create_server(kit) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{server.server_port}"
        server.shutdown()
        thread.join()


@pytest.mark.parametrize(
    ("path", "expected", "mime"),
    [
        ("course.html", b"<link", "text/html"),
        ("course.css", b"body", "text/css"),
        ("fonts/test.woff2", b"font fixture", "font/woff2"),
        ("files/input.csv", b"amount", "text/csv"),
    ],
)
def test_preview_serves_html_and_relative_assets(preview, path, expected, mime):
    with urlopen(f"{preview}/{path}", timeout=5) as response:
        assert response.headers.get_content_type() == mime
        assert response.read().startswith(expected)


@pytest.mark.parametrize("path", ["escape", "files/", "../private.txt"])
def test_preview_does_not_serve_outside_files_or_directory_lists(preview, path):
    with pytest.raises(HTTPError) as error:
        urlopen(f"{preview}/{path}", timeout=5)
    assert error.value.code in (403, 404)


def test_preview_rejects_directory_without_rendered_course(tmp_path):
    with pytest.raises(OSError, match="course.html"):
        create_server(tmp_path)


def test_preview_binds_distinct_loopback_ports_without_replacing_existing_server(
    tmp_path,
):
    (tmp_path / "course.html").write_text("<h1>Course</h1>")

    with create_server(tmp_path) as first, create_server(tmp_path) as second:
        assert first.server_address[0] == "127.0.0.1"
        assert second.server_address[0] == "127.0.0.1"
        assert first.server_port != second.server_port


def test_preview_downloads_native_document_without_rewriting(preview):
    with urlopen(f"{preview}/files/result.xlsx", timeout=5) as response:
        assert (
            response.headers["Content-Disposition"]
            == "attachment; filename*=UTF-8''result.xlsx"
        )
        assert response.read() == b"\x00\xffnative document bytes"
    with urlopen(f"{preview}/course.html", timeout=5) as response:
        assert response.headers["Content-Disposition"] is None


def test_preview_sandboxes_original_html_result(preview):
    with urlopen(f"{preview}/outputs/preview.html", timeout=5) as response:
        assert response.headers.get_content_type() == "text/html"
        assert response.read() == b"<h1>Invoice</h1>"
        assert (
            response.headers["Content-Security-Policy"]
            == "sandbox; default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
        )
        assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_preview_deck_allows_only_exact_runtime_hash_in_isolated_sandbox(preview):
    import base64
    import hashlib

    expected = base64.b64encode(
        hashlib.sha256(b"/* verified fixture */").digest()
    ).decode()
    with urlopen(f"{preview}/decks/result.html", timeout=5) as response:
        policy = response.headers["Content-Security-Policy"]
        assert f"script-src 'sha256-{expected}'" in policy
        assert "sandbox allow-scripts; default-src 'none'" in policy
        assert "allow-same-origin" not in policy and "allow-popups" not in policy
        assert "form-action 'none'" in policy and "base-uri 'none'" in policy
        assert (
            response.read() == b"<h1>Deck</h1><script>/* verified fixture */</script>"
        )


def test_preview_downloads_xml_without_browser_execution(preview):
    with urlopen(f"{preview}/outputs/invoice.xml", timeout=5) as response:
        assert (
            response.headers["Content-Disposition"]
            == "attachment; filename*=UTF-8''invoice.xml"
        )
        assert response.read() == b"<Invoice><Total>244.00</Total></Invoice>"


def test_preview_website_preserves_css_but_blocks_active_and_external_content(tmp_path):
    (tmp_path / "course.html").write_text("<a href='website/index.html'>Site</a>")
    (tmp_path / "website/assets").mkdir(parents=True)
    (tmp_path / "website/index.html").write_text(
        "<link rel='stylesheet' href='assets/site.css'>"
    )
    (tmp_path / "website/assets/site.css").write_text("body{color:green}")
    with create_server(tmp_path) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_port}/website"
            for path in ("index.html", "assets/site.css"):
                with urlopen(f"{root}/{path}", timeout=5) as response:
                    policy = response.headers["Content-Security-Policy"]
                    assert "sandbox; default-src 'none'" in policy
                    assert "style-src 'self' 'unsafe-inline'" in policy
                    assert "form-action 'none'" in policy
                    assert (
                        "allow-scripts" not in policy and "allow-popups" not in policy
                    )
                    assert "https:" not in policy
        finally:
            server.shutdown()
            thread.join()
