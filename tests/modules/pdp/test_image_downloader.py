from __future__ import annotations

import io
import zipfile
from pathlib import Path

import requests

from modules.pdp.image_downloader import (
    archive_variant_images,
    download_variant_images,
)
from modules.pdp.models import Variant


class _FakeResponse:
    def __init__(self, content: bytes, *, status_code: int = 200, headers: dict[str, str] | None = None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "image/jpeg"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class _FakeSession:
    def __init__(self, responses: dict[str, object]):
        self._responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, timeout: float | None = None, **kwargs):  # noqa: D401 - matches requests.Session.get
        self.calls.append((url, kwargs))
        response = self._responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def _make_variant(**overrides: object) -> Variant:
    base = dict(
        retailer="ulta",
        parent_product_id="Parent 123",
        variant_id="SKU 456",
        shade_name_raw=None,
        shade_name_normalized=None,
        size_text_raw=None,
        price_raw=None,
        price=None,
        currency=None,
        barcode=None,
        swatch_image_url="https://example.com/swatch.png",
        hero_image_url="https://example.com/hero.jpg",
        availability=None,
        source_index=None,
        qa_flags=(),
        extras={},
    )
    base.update(overrides)
    return Variant(**base)


def test_download_variant_images_prefers_hero(tmp_path: Path) -> None:
    variant = _make_variant()
    session = _FakeSession(
        {
            "https://example.com/hero.jpg": _FakeResponse(b"hero-bytes"),
        }
    )

    downloaded, errors = download_variant_images([variant], tmp_path, session=session)

    assert not errors
    assert len(downloaded) == 1
    item = downloaded[0]
    assert item.image_type == "hero"
    assert item.path.exists()
    assert item.path.read_bytes() == b"hero-bytes"
    assert item.path.name.startswith("Parent-123_SKU-456_hero")


def test_download_variant_images_falls_back_to_swatch(tmp_path: Path) -> None:
    variant = _make_variant(hero_image_url=None)
    session = _FakeSession(
        {
            "https://example.com/swatch.png": _FakeResponse(
                b"swatch-bytes", headers={"Content-Type": "image/png"}
            ),
        }
    )

    downloaded, errors = download_variant_images([variant], tmp_path, session=session)

    assert not errors
    assert downloaded[0].image_type == "swatch"
    assert downloaded[0].path.suffix == ".png"


def test_download_variant_images_records_failures(tmp_path: Path) -> None:
    variant = _make_variant()
    session = _FakeSession(
        {
            "https://example.com/hero.jpg": requests.ConnectionError("boom"),
            "https://example.com/swatch.png": requests.Timeout("nope"),
        }
    )

    downloaded, errors = download_variant_images([variant], tmp_path, session=session)

    assert not downloaded
    assert len(errors) == 1
    err = errors[0]
    assert "boom" in err.reason or "nope" in err.reason
    assert len(err.attempted_urls) == 2


def test_archive_variant_images_creates_zip(tmp_path: Path) -> None:
    variant = _make_variant()
    session = _FakeSession(
        {
            "https://example.com/hero.jpg": _FakeResponse(b"hero"),
        }
    )

    archive_bytes, metadata, errors = archive_variant_images([variant], session=session)

    assert not errors
    assert metadata
    assert archive_bytes

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert zf.read(names[0]) == b"hero"


def test_download_variant_images_normalizes_unicode_urls(tmp_path: Path) -> None:
    record = {
        "parent_product_id": "Parent 123",
        "variant_id": "SKU 456",
        "hero_image_url": "https:\\u002F\\u002Fexample.com\\u002Fhero.jpg",
        "swatch_image_url": None,
    }
    session = _FakeSession(
        {
            "https://example.com/hero.jpg": _FakeResponse(b"hero"),
        }
    )

    downloaded, errors = download_variant_images([record], tmp_path, session=session)

    assert not errors
    assert downloaded
    assert downloaded[0].url == "https://example.com/hero.jpg"


def test_download_variant_images_sets_headers(tmp_path: Path) -> None:
    variant = _make_variant()
    session = _FakeSession(
        {
            "https://example.com/hero.jpg": _FakeResponse(b"hero-bytes"),
        }
    )

    downloaded, errors = download_variant_images([variant], tmp_path, session=session)

    assert not errors
    assert downloaded
    _, kwargs = session.calls[0]
    sent_headers = kwargs["headers"]
    assert "Mozilla" in sent_headers["User-Agent"]
    assert sent_headers["Referer"] == "https://example.com/"


def test_download_variant_images_skips_existing_when_requested(tmp_path: Path) -> None:
    variant = _make_variant()
    existing = tmp_path / "Parent-123_SKU-456_hero.jpg"
    existing.write_bytes(b"cached")
    session = _FakeSession(
        {
            "https://example.com/hero.jpg": _FakeResponse(b"fresh"),
        }
    )

    downloaded, errors = download_variant_images(
        [variant],
        tmp_path,
        session=session,
        skip_existing=True,
    )

    assert not errors
    assert len(downloaded) == 1
    assert downloaded[0].path == existing
    assert downloaded[0].path.read_bytes() == b"cached"
    assert session.calls == []


def test_download_variant_images_replaces_empty_existing_files(tmp_path: Path) -> None:
    variant = _make_variant()
    existing = tmp_path / "Parent-123_SKU-456_hero.jpg"
    existing.write_bytes(b"")
    session = _FakeSession(
        {
            "https://example.com/hero.jpg": _FakeResponse(b"hero-bytes"),
        }
    )

    downloaded, errors = download_variant_images(
        [variant],
        tmp_path,
        session=session,
        skip_existing=True,
    )

    assert not errors
    assert downloaded[0].path.read_bytes() == b"hero-bytes"


def test_download_variant_images_truncates_overlong_variant_file_names(
    tmp_path: Path,
) -> None:
    very_long_variant = "by voluntarily opting in to Saks Fifth Avenue waitlist text alerts " * 8
    variant = _make_variant(
        parent_product_id="0400026472358",
        variant_id=very_long_variant,
    )
    session = _FakeSession(
        {
            "https://example.com/hero.jpg": _FakeResponse(
                b"hero-bytes", headers={"Content-Type": "image/avif"}
            ),
        }
    )

    downloaded, errors = download_variant_images([variant], tmp_path, session=session)

    assert not errors
    assert len(downloaded) == 1
    assert downloaded[0].path.exists()
    assert downloaded[0].path.suffix in {".avif", ".jpg"}
    assert len(downloaded[0].path.name) < 150
    assert downloaded[0].path.name.startswith("0400026472358_")
    assert "_hero" in downloaded[0].path.name
