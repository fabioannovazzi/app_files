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
def preview(tmp_path):
    kit = tmp_path / "kit with spaces"
    kit.mkdir()
    (kit / "course.html").write_text("<link rel='stylesheet' href='course.css'>")
    (kit / "course.css").write_text("body { color: blue; }")
    (kit / "fonts").mkdir()
    (kit / "fonts/test.woff2").write_bytes(b"font fixture")
    (kit / "files").mkdir()
    (kit / "files/input.csv").write_text("amount\n12\n")
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
