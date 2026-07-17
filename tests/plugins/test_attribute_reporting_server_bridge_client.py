from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLIENT_PATH = (
    ROOT / "plugins" / "attribute-reporting" / "scripts" / "server_bridge_client.py"
)


@pytest.fixture
def client_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "attribute_reporting_server_bridge_client_test",
        CLIENT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "url",
    [
        "http://mparanza.com",
        "https://mparanza.com.evil.example",
        "https://user:secret@mparanza.com",
        "https://mparanza.com/private/path",
    ],
)
def test_remote_base_url_is_restricted_to_exact_https_origin(
    client_module: ModuleType,
    url: str,
) -> None:
    with pytest.raises(client_module.ServerBridgeClientError):
        client_module._normalize_base_url(url)


def test_mapping_submission_sends_every_reviewed_artifact(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = client_module.AttributeReportingServerClient(
        object(),
        base_url="https://mparanza.com",
    )
    calls: list[dict[str, Any]] = []

    def request_json(
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append({"path": path, "method": method, "payload": payload})
        return {"operation_id": "f" * 64}

    monkeypatch.setattr(client, "_request_json", request_json)
    tasks = {"schema_version": "attribute_reporting.mapping_tasks.v1"}
    decisions = {"schema_version": "attribute_reporting.mapping_decisions.v1"}
    validated = {"schema_version": "attribute_reporting.validated_mapping_decisions.v1"}
    review = {"schema_version": "attribute_reporting.mapping_review.v1"}

    result = client.submit_mapping_results(
        workset_id="workset-one",
        workset_sha256="a" * 64,
        idempotency_key="b" * 64,
        mapping_tasks=tasks,
        decisions=decisions,
        validated_mappings=validated,
        mapping_review=review,
    )

    assert result == {"operation_id": "f" * 64}
    assert calls == [
        {
            "path": "/mapping-worksets/workset-one/submissions",
            "method": "POST",
            "payload": {
                "workset_sha256": "a" * 64,
                "idempotency_key": "b" * 64,
                "mapping_tasks": tasks,
                "decisions": decisions,
                "validated_mappings": validated,
                "mapping_review": review,
            },
        }
    ]


def test_create_brand_fit_pack_sends_only_report_binding_and_supplied_aliases(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = client_module.AttributeReportingServerClient(
        object(), base_url="https://mparanza.com"
    )
    calls: list[dict[str, Any]] = []

    def request_json(
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append({"path": path, "method": method, "payload": payload})
        return {"job_id": "brand-fit-job"}

    monkeypatch.setattr(client, "_request_json", request_json)

    result = client.create_brand_fit_pack(
        source_evidence_job_id="e" * 32,
        brand_source_retailer="brand-owned",
        brand_name="Example Brand",
        retailer_report_sha256="a" * 64,
        retailer_report_verdict="Correct",
        owned_category_keys=["sweaters"],
    )

    assert result == {"job_id": "brand-fit-job"}
    assert calls == [
        {
            "path": "/brand-fit-packs",
            "method": "POST",
            "payload": {
                "source_evidence_job_id": "e" * 32,
                "brand_source_retailer": "brand-owned",
                "brand_name": "Example Brand",
                "retailer_report_sha256": "a" * 64,
                "retailer_report_verdict": "Correct",
                "owned_category_keys": ["sweaters"],
            },
        }
    ]


def test_create_brand_fit_pack_rejects_unchecked_source_report(
    client_module: ModuleType,
) -> None:
    client = client_module.AttributeReportingServerClient(
        object(), base_url="https://mparanza.com"
    )

    with pytest.raises(client_module.ServerBridgeClientError, match="must be Correct"):
        client.create_brand_fit_pack(
            source_evidence_job_id="e" * 32,
            brand_source_retailer="brand-owned",
            brand_name="Example Brand",
            retailer_report_sha256="a" * 64,
            retailer_report_verdict="Incorrect",
        )


def test_json_request_encoding_is_compact_at_payload_boundaries(
    client_module: ModuleType,
) -> None:
    payload = {"tasks": [{"id": "one"}, {"id": "two"}], "approved": True}

    encoded = client_module._json_bytes(payload)

    assert encoded == (b'{"tasks":[{"id":"one"},{"id":"two"}],"approved":true}')
    assert len(encoded) < len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def test_session_cookie_jar_is_persisted_privately_between_commands(
    client_module: ModuleType,
    tmp_path: Path,
) -> None:
    session_path = tmp_path / "private" / "server-session.cookies"
    jar = client_module._load_session_cookie_jar(session_path)
    jar.set_cookie(
        client_module.http.cookiejar.Cookie(
            version=0,
            name="session",
            value="private-token",
            port=None,
            port_specified=False,
            domain="mparanza.com",
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": None},
            rfc2109=False,
        )
    )

    client_module._save_session_cookie_jar(jar, session_path)
    reloaded = client_module._load_session_cookie_jar(session_path)

    assert oct(session_path.stat().st_mode & 0o777) == "0o600"
    assert client_module._has_session_cookie_for_origin(
        reloaded, "https://mparanza.com"
    )


def test_new_opener_preserves_empty_persistent_cookie_jar(
    client_module: ModuleType,
) -> None:
    jar = client_module.http.cookiejar.MozillaCookieJar()

    opener = client_module._new_opener(jar)

    cookie_processors = [
        handler
        for handler in opener.handlers
        if isinstance(handler, client_module.urllib.request.HTTPCookieProcessor)
    ]
    assert len(cookie_processors) == 1
    assert cookie_processors[0].cookiejar is jar


def test_workset_outputs_include_separate_mapping_tasks_file(
    client_module: ModuleType,
    tmp_path: Path,
) -> None:
    tasks = {"schema_version": "attribute_reporting.mapping_tasks.v1", "tasks": []}
    result = {
        "workset_id": "workset-one",
        "workset_sha256": "a" * 64,
        "mapping_tasks": tasks,
    }

    client_module._write_workset_outputs(
        result,
        envelope_path=tmp_path / "workset.json",
        tasks_path=tmp_path / "mapping_tasks.public.json",
    )

    assert json.loads((tmp_path / "workset.json").read_text(encoding="utf-8")) == result
    assert (
        json.loads((tmp_path / "mapping_tasks.public.json").read_text(encoding="utf-8"))
        == tasks
    )


class _DownloadResponse:
    def __init__(self, payload: bytes, *, url: str, content_type: str) -> None:
        self.payload = payload
        self.offset = 0
        self.url = url
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(payload)),
            "X-Content-SHA256": hashlib.sha256(payload).hexdigest(),
        }

    def read(self, amount: int = -1) -> bytes:
        if amount < 0:
            amount = len(self.payload) - self.offset
        chunk = self.payload[self.offset : self.offset + amount]
        self.offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self.url

    def __enter__(self) -> _DownloadResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _DownloadOpener:
    def __init__(self, response: _DownloadResponse) -> None:
        self.response = response

    def open(self, _request: object, *, timeout: float) -> _DownloadResponse:
        assert timeout > 0
        return self.response


def test_download_evidence_pack_pins_first_party_zip_response(
    client_module: ModuleType,
    tmp_path: Path,
) -> None:
    payload = b"PK\x03\x04example"
    response = _DownloadResponse(
        payload,
        url="https://mparanza.com/case-notes/api/attribute-reporting/evidence-packs/job/download",
        content_type="application/zip",
    )
    client = client_module.AttributeReportingServerClient(_DownloadOpener(response))

    receipt = client.download_evidence_pack("job", tmp_path / "evidence.zip")

    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    assert (tmp_path / "evidence.zip").read_bytes() == payload


def test_download_evidence_pack_rejects_cross_origin_redirect(
    client_module: ModuleType,
    tmp_path: Path,
) -> None:
    response = _DownloadResponse(
        b"PK\x03\x04example",
        url="https://evil.example/evidence.zip",
        content_type="application/zip",
    )
    client = client_module.AttributeReportingServerClient(_DownloadOpener(response))

    with pytest.raises(client_module.ServerBridgeClientError, match="redirected"):
        client.download_evidence_pack("job", tmp_path / "evidence.zip")

    assert not (tmp_path / "evidence.zip").exists()


def test_extract_evidence_pack_writes_only_safe_pinned_files(
    client_module: ModuleType,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidence.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("summary.json", '{"product_count": 2}\n')
        bundle.writestr("tables/products.csv", "id,name\n1,Cardigan\n")

    receipt = client_module.extract_evidence_pack(archive, tmp_path / "package")

    assert receipt["schema_version"] == (
        "attribute_reporting.local_extraction_receipt.v1"
    )
    assert receipt["file_count"] == 2
    assert [item["path"] for item in receipt["files"]] == [
        "summary.json",
        "tables/products.csv",
    ]
    assert (tmp_path / "package" / "summary.json").is_file()
    assert len(receipt["archive_sha256"]) == 64


@pytest.mark.parametrize("unsafe_name", ["../outside.json", "/absolute.json"])
def test_extract_evidence_pack_rejects_unsafe_member_paths(
    client_module: ModuleType,
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(unsafe_name, "unsafe")

    with pytest.raises(client_module.ServerBridgeClientError, match="unsafe member"):
        client_module.extract_evidence_pack(archive, tmp_path / "package")

    assert not (tmp_path / "package").exists()
    assert not (tmp_path / "outside.json").exists()


def test_extract_evidence_pack_rejects_symlink_members(
    client_module: ModuleType,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("linked-summary.json")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(link, "summary.json")

    with pytest.raises(client_module.ServerBridgeClientError, match="unsafe member"):
        client_module.extract_evidence_pack(archive, tmp_path / "package")

    assert not (tmp_path / "package").exists()


def test_extract_evidence_pack_rejects_symlinked_archive_path(
    client_module: ModuleType,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidence.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("summary.json", "{}")
    linked_archive = tmp_path / "linked.zip"
    linked_archive.symlink_to(archive)

    with pytest.raises(client_module.ServerBridgeClientError, match="symlinks"):
        client_module.extract_evidence_pack(
            linked_archive,
            tmp_path / "package",
        )


def test_extract_evidence_pack_rejects_symlinked_destination_parent(
    client_module: ModuleType,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "evidence.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("summary.json", "{}")
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(client_module.ServerBridgeClientError, match="symlinks"):
        client_module.extract_evidence_pack(
            archive,
            linked_parent / "package",
        )

    assert not (real_parent / "package").exists()
