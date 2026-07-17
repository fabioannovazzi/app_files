from __future__ import annotations

import base64
import csv
import importlib.util
import json
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "plugins" / "attribute-reporting" / "scripts" / "hydrate_images.py"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "attribute_reporting_hydrate_images_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hydration = _load_module()


def _resolver_for(address: str):
    def resolve(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        return [(2, 1, 6, "", (address, 443))]

    return resolve


def test_public_network_target_rejects_hostname_resolving_to_private_address() -> None:
    with pytest.raises(hydration.HydrationError, match="non-public"):
        hydration._assert_public_network_target(
            "https://cdn.example.test/image.png",
            resolver=_resolver_for("127.0.0.1"),
        )


def test_public_network_target_accepts_globally_routable_resolution() -> None:
    hydration._assert_public_network_target(
        "https://cdn.example.test/image.png",
        resolver=_resolver_for("93.184.216.34"),
    )


def test_default_image_fetch_connects_to_the_vetted_numeric_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connected: list[tuple[str, int, float]] = []
    requests: list[tuple[str, int, str, object]] = []
    pinned_socket = object()

    class FakeHTTPResponse:
        status = 200
        headers = {
            "Content-Type": "image/png",
            "Content-Length": str(len(PNG_BYTES)),
        }

        def read(self, amount: int = -1) -> bytes:
            return PNG_BYTES if amount != 0 else b""

        def close(self) -> None:
            return None

    class FakeHTTPConnection:
        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout
            self.sock: object | None = None

        def request(
            self,
            method: str,
            target: str,
            *,
            headers: dict[str, str],
        ) -> None:
            assert method == "GET"
            requests.append((self.host, self.port, target, self.sock))

        def getresponse(self) -> FakeHTTPResponse:
            return FakeHTTPResponse()

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        hydration,
        "_public_network_target",
        lambda url: ("cdn.example.test", 80, ("93.184.216.34",)),
    )
    monkeypatch.setattr(
        hydration,
        "_connect_pinned_socket",
        lambda address, port, timeout: (
            connected.append((address, port, timeout)) or pinned_socket
        ),
    )
    monkeypatch.setattr(
        hydration.http.client,
        "HTTPConnection",
        FakeHTTPConnection,
    )

    request = urllib.request.Request(
        "http://cdn.example.test/image.png?size=large",
        headers={"Accept": "image/*"},
    )
    with hydration._default_open_url(request, 4.0) as response:
        assert response.geturl() == request.full_url

    assert connected == [("93.184.216.34", 80, 4.0)]
    assert requests == [
        (
            "cdn.example.test",
            80,
            "/image.png?size=large",
            pinned_socket,
        )
    ]


class _FakeResponse:
    def __init__(
        self,
        payload: bytes,
        *,
        url: str = "https://cdn.example.test/final.png",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self._offset = 0
        self._url = url
        self.headers = headers or {
            "Content-Type": "image/png",
            "Content-Length": str(len(payload)),
        }

    def read(self, amount: int = -1) -> bytes:
        if amount < 0:
            amount = len(self._payload) - self._offset
        chunk = self._payload[self._offset : self._offset + amount]
        self._offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _package(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    package = tmp_path / "package"
    package.mkdir()
    (package / "pack_manifest.json").write_text(
        json.dumps({"files": {"products": "product_filter_matrix.csv"}}),
        encoding="utf-8",
    )
    _write_csv(package / "product_filter_matrix.csv", rows)
    return package


def test_hydrate_product_images_downloads_local_sidecar_without_rewriting_csv(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path,
        [
            {
                "parent_product_id": "cashmere/one",
                "product_name": "Cashmere One",
                "hero_image_url": "https://cdn.example.test/one.png",
                "og_image_url": "",
                "pack_image_file": "",
            }
        ],
    )
    source_before = (package / "product_filter_matrix.csv").read_bytes()
    calls: list[str] = []

    def open_url(request: Any, timeout: float) -> _FakeResponse:
        calls.append(request.full_url)
        assert timeout == 3.0
        return _FakeResponse(PNG_BYTES)

    result = hydration.hydrate_product_images(
        package,
        timeout_seconds=3.0,
        open_url=open_url,
    )

    assert calls == ["https://cdn.example.test/one.png"]
    assert result["summary"] == {
        "product_count": 1,
        "available_count": 1,
        "failure_count": 0,
        "unavailable_count": 0,
        "not_attempted_count": 0,
        "status": "complete",
    }
    entry = result["products"][0]
    assert entry["status"] == "downloaded"
    assert entry["source_field"] == "hero_image_url"
    image_path = package / entry["image_path"]
    assert image_path.read_bytes() == PNG_BYTES
    assert result["policy"]["uploaded_to_server"] is False
    assert result["policy"]["analytical_package_files_modified"] is False
    assert (package / "product_filter_matrix.csv").read_bytes() == source_before


def test_hydrate_product_images_uses_swatch_url_when_no_hero_is_available(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path,
        [
            {
                "parent_product_id": "cashmere-swatch",
                "hero_image_url": "",
                "swatch_image_url": "https://cdn.example.test/swatch.png",
                "og_image_url": "",
                "pack_image_file": "",
            }
        ],
    )

    result = hydration.hydrate_product_images(
        package,
        open_url=lambda request, timeout: _FakeResponse(PNG_BYTES),
    )

    assert result["products"][0]["status"] == "downloaded"
    assert result["products"][0]["source_field"] == "swatch_image_url"


def test_brand_fit_image_hydration_keeps_retailer_and_owned_scopes_separate(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "pack_manifest.json").write_text(
        json.dumps({"package_type": "brand_retailer_reference_handoff"}),
        encoding="utf-8",
    )
    _write_csv(
        package / "retailer_brand_anchors.csv",
        [
            {
                "parent_product_id": "shared-id",
                "product_scope": "brand_at_retailer",
                "hero_image_url": "https://cdn.example.test/retailer.png",
            }
        ],
    )
    _write_csv(
        package / "manufacturer_catalog_products.csv",
        [
            {
                "parent_product_id": "shared-id",
                "product_scope": "owned_catalogue",
                "hero_image_url": "https://cdn.example.test/owned.png",
            }
        ],
    )

    result = hydration.hydrate_product_images(
        package,
        open_url=lambda request, timeout: _FakeResponse(
            PNG_BYTES, url=request.full_url
        ),
    )

    assert result["summary"]["product_count"] == 2
    assert {item["product_id"] for item in result["products"]} == {"shared-id"}
    assert len({item["record_id"] for item in result["products"]}) == 2
    assert len({item["image_path"] for item in result["products"]}) == 2


def test_hydrate_product_images_resumes_from_verified_manifest(tmp_path: Path) -> None:
    package = _package(
        tmp_path,
        [
            {
                "parent_product_id": "one",
                "hero_image_url": "https://cdn.example.test/one.png",
                "pack_image_file": "",
            }
        ],
    )
    call_count = 0

    def first_open_url(request: Any, timeout: float) -> _FakeResponse:
        del request, timeout
        nonlocal call_count
        call_count += 1
        return _FakeResponse(PNG_BYTES)

    hydration.hydrate_product_images(package, open_url=first_open_url)

    def unexpected_open_url(request: Any, timeout: float) -> _FakeResponse:
        del request, timeout
        raise AssertionError("resume should not redownload a verified image")

    resumed = hydration.hydrate_product_images(
        package,
        open_url=unexpected_open_url,
    )

    assert call_count == 1
    assert resumed["products"][0]["status"] == "reused"
    assert resumed["summary"]["status"] == "complete"


def test_hydrate_product_images_records_invalid_content_as_partial(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path,
        [
            {
                "parent_product_id": "one",
                "hero_image_url": "https://cdn.example.test/one.txt",
                "pack_image_file": "",
            },
            {
                "parent_product_id": "two",
                "hero_image_url": "",
                "pack_image_file": "",
            },
        ],
    )

    result = hydration.hydrate_product_images(
        package,
        open_url=lambda request, timeout: _FakeResponse(b"not an image"),
    )

    statuses = {item["product_id"]: item["status"] for item in result["products"]}
    assert statuses == {"one": "failed", "two": "unavailable"}
    assert result["summary"]["status"] == "blocked"
    assert result["summary"]["failure_count"] == 1
    assert result["summary"]["unavailable_count"] == 1


@pytest.mark.parametrize(
    "url",
    [
        "file:///private/product.png",
        "http://127.0.0.1/product.png",
        "http://localhost/product.png",
        "not-a-url",
    ],
)
def test_hydrate_product_images_does_not_request_disallowed_urls(
    tmp_path: Path,
    url: str,
) -> None:
    package = _package(
        tmp_path,
        [
            {
                "parent_product_id": "one",
                "hero_image_url": url,
                "pack_image_file": "",
            }
        ],
    )

    def unexpected_open_url(request: Any, timeout: float) -> _FakeResponse:
        del request, timeout
        raise AssertionError("disallowed URL must not be requested")

    result = hydration.hydrate_product_images(
        package,
        open_url=unexpected_open_url,
    )

    assert result["products"][0]["status"] == "unavailable"
    assert result["summary"]["status"] == "blocked"


def test_hydrate_product_images_rejects_manifest_outside_package(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path,
        [
            {
                "parent_product_id": "one",
                "hero_image_url": "https://cdn.example.test/one.png",
                "pack_image_file": "",
            }
        ],
    )

    with pytest.raises(hydration.HydrationError, match="must stay inside"):
        hydration.hydrate_product_images(
            package,
            manifest_path=tmp_path / "outside.json",
        )


def test_bind_images_to_mapping_tasks_adds_only_relative_verified_image_evidence(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path,
        [
            {
                "parent_product_id": "one",
                "hero_image_url": "https://cdn.example.test/one.png",
                "pack_image_file": "",
            }
        ],
    )
    manifest = hydration.hydrate_product_images(
        package,
        open_url=lambda request, timeout: _FakeResponse(PNG_BYTES),
    )
    source_row_sha = manifest["products"][0]["source_rows"]["product_filter_matrix.csv"]
    public_tasks = {
        "schema_version": "attribute_reporting.mapping_tasks.v1",
        "taxonomy_snapshot": {
            "version": "v1",
            "sha256": "a" * 64,
            "category_key": "cashmere",
        },
        "scope": {"source_package": "bridge://evidence/job"},
        "coverage": {"task_count": 1},
        "tasks": [
            {
                "task_id": "map-one",
                "product": {
                    "parent_product_id": "one",
                    "source_row_sha256": source_row_sha,
                    "local_images": [],
                },
                "attribute": {"id": "finish"},
            }
        ],
    }
    tasks_path = tmp_path / "mapping_tasks.json"
    output_path = tmp_path / "mapping_tasks_local.json"
    tasks_path.write_text(json.dumps(public_tasks), encoding="utf-8")

    result = hydration.bind_images_to_mapping_tasks(
        tasks_path,
        package / "local_image_manifest.json",
        output_path,
    )

    local_images = result["mapping_tasks"]["tasks"][0]["product"]["local_images"]
    assert result["image_bound_task_count"] == 1
    assert local_images[0]["path"].startswith("images/local/")
    assert not Path(local_images[0]["path"]).is_absolute()
    assert local_images[0]["sha256"] == manifest["products"][0]["sha256"]
    stripped = json.loads(json.dumps(result["mapping_tasks"]))
    stripped["tasks"][0]["product"]["local_images"] = []
    assert stripped == public_tasks


def test_bind_images_to_mapping_tasks_rejects_stale_source_row(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path,
        [
            {
                "parent_product_id": "one",
                "hero_image_url": "https://cdn.example.test/one.png",
                "pack_image_file": "",
            }
        ],
    )
    hydration.hydrate_product_images(
        package,
        open_url=lambda request, timeout: _FakeResponse(PNG_BYTES),
    )
    tasks = {
        "schema_version": "attribute_reporting.mapping_tasks.v1",
        "tasks": [
            {
                "task_id": "map-one",
                "product": {
                    "parent_product_id": "one",
                    "source_row_sha256": "f" * 64,
                    "local_images": [],
                },
            }
        ],
    }
    tasks_path = tmp_path / "mapping_tasks.json"
    tasks_path.write_text(json.dumps(tasks), encoding="utf-8")

    with pytest.raises(hydration.HydrationError, match="stale"):
        hydration.bind_images_to_mapping_tasks(
            tasks_path,
            package / "local_image_manifest.json",
            tmp_path / "mapping_tasks_local.json",
        )
