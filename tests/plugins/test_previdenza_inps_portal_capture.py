from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = ROOT / "plugins" / "previdenza-inps" / "scripts"
SCRIPT_PATH = SCRIPTS_ROOT / "capture_portal_snapshot.py"
PNG_BYTES = b"\x89PNG\r\n\x1a\nsynthetic-png"


def _load_module(module_name: str = "previdenza_inps_portal_capture") -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_inventory_module() -> ModuleType:
    scripts_path = str(SCRIPTS_ROOT)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    path = SCRIPTS_ROOT / "inventory_case.py"
    spec = importlib.util.spec_from_file_location(
        "previdenza_inps_portal_capture_inventory", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PORTAL = _load_module()


def _approval(**overrides: Any) -> dict[str, Any]:
    approval = {
        "approved": True,
        "approval_id": "APR-001",
        "approved_at": "2026-07-16T10:00:00+02:00",
        "approved_by": "reviewer-001",
        "approved_by_role": "professional_reviewer",
        "reason": "Authorized evidence capture for the synthetic case.",
        "scope": "Read one already-authenticated INPS page.",
        "own_or_authorized_credentials_confirmed": True,
        "human_access_authority_confirmed": True,
        "human_access_authority_basis": "Recorded human authority for this bounded portal view.",
        "portal_profile_authority_confirmed": True,
        "portal_profile_authority_basis": "Recorded authority for the selected professional profile.",
        "delegation_or_subject_authority_confirmed": True,
        "delegation_or_subject_authority_basis": "Recorded client delegation or subject self-access basis.",
        "portal_capture_permission_confirmed": True,
        "portal_permission_basis": "Synthetic service terms permit this test capture.",
        "read_only_capture_confirmed": True,
        "no_credentials_or_session_secrets_visible_confirmed": True,
    }
    approval.update(overrides)
    return approval


class _FakeLocator:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    def inner_text(self, *, timeout: int) -> str:
        self._page.calls.append(("body.inner_text", timeout))
        return self._page.body_text

    def click(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("locator.click must never be called")

    def fill(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("locator.fill must never be called")


class _FakePage:
    def __init__(
        self,
        url: str,
        *,
        title: str = "Synthetic INPS title",
        body_text: str = "Synthetic visible body",
        url_reads: list[str] | None = None,
        title_error: BaseException | None = None,
    ) -> None:
        self._url = url
        self._url_reads = list(url_reads or [])
        self._url_read_index = 0
        self.page_title = title
        self.body_text = body_text
        self.title_error = title_error
        self.calls: list[tuple[str, Any]] = []

    @property
    def url(self) -> str:
        self.calls.append(("url", None))
        if not self._url_reads:
            return self._url
        index = min(self._url_read_index, len(self._url_reads) - 1)
        self._url_read_index += 1
        return self._url_reads[index]

    def title(self) -> str:
        self.calls.append(("title", None))
        if self.title_error is not None:
            raise self.title_error
        return self.page_title

    def locator(self, selector: str) -> _FakeLocator:
        self.calls.append(("locator", selector))
        assert selector == "body"
        return _FakeLocator(self)

    def screenshot(self, **kwargs: Any) -> bytes:
        self.calls.append(("screenshot", kwargs))
        return PNG_BYTES

    def goto(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("page.goto must never be called")

    def click(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("page.click must never be called")

    def fill(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("page.fill must never be called")

    def content(self) -> str:
        raise AssertionError("page.content must never be called")


class _FakeContext:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def cookies(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("context.cookies must never be called")

    def storage_state(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("context.storage_state must never be called")


class _FakeBrowser:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.contexts = [_FakeContext(pages)]
        self.close_called = False

    def close(self) -> None:
        self.close_called = True
        raise AssertionError("browser.close must never be called")


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser) -> None:
        self._browser = browser
        self.connected_urls: list[str] = []

    def connect_over_cdp(self, remote_url: str) -> _FakeBrowser:
        self.connected_urls.append(remote_url)
        return self._browser


class _FakePlaywright:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.browser = _FakeBrowser(pages)
        self.chromium = _FakeChromium(self.browser)
        self.stop_called = False

    def stop(self) -> None:
        self.stop_called = True


@pytest.mark.parametrize(
    "remote_url",
    [
        "https://127.0.0.1:9222",
        "http://0.0.0.0:9222",
        "http://localhost.example:9222",
        "http://user:password@localhost:9222",
        "http://localhost:9222/json/version",
        "http://localhost:9222?secret=value",
        "http://localhost:9222#fragment",
    ],
)
def test_normalize_cdp_url_rejects_non_loopback_or_non_root_endpoints(
    remote_url: str,
) -> None:
    with pytest.raises(PORTAL.PortalCaptureError):
        PORTAL.normalize_cdp_url(remote_url)


@pytest.mark.parametrize(
    ("remote_url", "expected"),
    [
        ("http://localhost:9222/", "http://localhost:9222"),
        ("http://127.0.0.1:9222", "http://127.0.0.1:9222"),
        ("http://[::1]:9222", "http://[::1]:9222"),
    ],
)
def test_normalize_cdp_url_accepts_loopback_endpoints(
    remote_url: str, expected: str
) -> None:
    assert PORTAL.normalize_cdp_url(remote_url) == expected


@pytest.mark.parametrize(
    "approved_origin",
    [
        "http://www.inps.it",
        "https://inps.it.example",
        "https://notinps.it",
        "https://user:password@www.inps.it",
        "https://www.inps.it/area-riservata",
        "https://www.inps.it?token=value",
        "https://www.inps.it:444",
        "https://servizi.inps.gov.it",
    ],
)
def test_normalize_approved_origin_rejects_unsafe_or_inexact_origins(
    approved_origin: str,
) -> None:
    with pytest.raises(PORTAL.PortalCaptureError):
        PORTAL.normalize_approved_origin(approved_origin)


@pytest.mark.parametrize(
    ("approved_origin", "expected"),
    [
        ("https://www.inps.it", "https://www.inps.it"),
        ("https://servizi.inps.it/", "https://servizi.inps.it"),
    ],
)
def test_normalize_approved_origin_accepts_only_inps_https_origins(
    approved_origin: str, expected: str
) -> None:
    assert PORTAL.normalize_approved_origin(approved_origin) == expected


@pytest.mark.parametrize(
    "change",
    [
        {"approval_id": ""},
        {"approved": False},
        {"own_or_authorized_credentials_confirmed": False},
        {"human_access_authority_confirmed": False},
        {"human_access_authority_basis": ""},
        {"portal_profile_authority_confirmed": False},
        {"portal_profile_authority_basis": ""},
        {"delegation_or_subject_authority_confirmed": False},
        {"delegation_or_subject_authority_basis": ""},
        {"portal_capture_permission_confirmed": False},
        {"portal_permission_basis": ""},
        {"read_only_capture_confirmed": False},
        {"no_credentials_or_session_secrets_visible_confirmed": False},
        {"approved_at": "2026-07-16T10:00:00"},
        {"approved_by_role": "administrator"},
        {"unexpected": "field"},
    ],
)
def test_external_approval_rejects_missing_or_invalid_authorization(
    change: dict[str, Any],
) -> None:
    approval = _approval(**change)
    with pytest.raises(PORTAL.PortalCaptureError):
        PORTAL.validate_external_approval(approval)


def test_external_approval_rejects_a_missing_required_field() -> None:
    approval = _approval()
    approval.pop("scope")

    with pytest.raises(PORTAL.PortalCaptureError, match="missing: scope"):
        PORTAL.validate_external_approval(approval)


def test_capture_writes_private_hash_bound_artifacts_without_operating_browser(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    secret_url = (
        "https://servizi.inps.it/posizione?token=top-secret&cf=TSTUSR00A01H501Z"
    )
    secret_title = "Posizione di Example Client - private title"
    visible_body = "Estratto conto previdenziale\r\nPeriodo: 2020-2024"
    page = _FakePage(secret_url, title=secret_title, body_text=visible_body)
    runtime = _FakePlaywright([page])
    output = tmp_path / "portal-capture"
    caplog.set_level("DEBUG")

    manifest = PORTAL.capture_portal_snapshot(
        remote_url="http://127.0.0.1:9222/",
        approved_origin="https://servizi.inps.it",
        output_dir=output,
        external_approval=_approval(),
        timeout_ms=1_234,
        playwright_factory=lambda: runtime,
        captured_at=datetime(2026, 7, 16, 8, 30, tzinfo=timezone.utc),
    )

    manifest_text = (output / PORTAL.MANIFEST_NAME).read_text(encoding="utf-8")
    expected_text = visible_body.replace("\r\n", "\n")
    assert (output / PORTAL.VISIBLE_TEXT_NAME).read_text(encoding="utf-8") == (
        expected_text
    )
    assert (output / PORTAL.SCREENSHOT_NAME).read_bytes() == PNG_BYTES
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir())
    assert (
        manifest["source_url_sha256"]
        == hashlib.sha256(secret_url.encode("utf-8")).hexdigest()
    )
    assert (
        manifest["page_title_sha256"]
        == hashlib.sha256(secret_title.encode("utf-8")).hexdigest()
    )
    assert secret_url not in manifest_text
    assert secret_title not in manifest_text
    assert "top-secret" not in manifest_text
    assert "TSTUSR00A01H501Z" not in manifest_text
    assert runtime.chromium.connected_urls == ["http://127.0.0.1:9222"]
    assert runtime.stop_called is True
    assert runtime.browser.close_called is False
    assert ("locator", "body") in page.calls
    assert ("body.inner_text", 1_234) in page.calls
    assert (
        "screenshot",
        {"type": "png", "full_page": True, "timeout": 1_234},
    ) in page.calls
    assert PORTAL.verify_portal_snapshot(output) == {
        "ok": True,
        "schema_version": PORTAL.SCHEMA_VERSION,
        "capture_id": manifest["capture_id"],
        "artifact_count": 2,
    }
    assert secret_url not in caplog.text
    assert secret_title not in caplog.text
    assert visible_body not in caplog.text


@pytest.mark.parametrize("matching_page_count", [0, 2])
def test_capture_requires_exactly_one_already_open_matching_page(
    tmp_path: Path, matching_page_count: int
) -> None:
    pages = [
        _FakePage(f"https://www.inps.it/page-{index}")
        for index in range(matching_page_count)
    ]
    if not pages:
        pages = [_FakePage("https://example.test/not-inps")]
    runtime = _FakePlaywright(pages)
    output = tmp_path / "portal-capture"

    with pytest.raises(PORTAL.PortalCaptureError, match="exactly one"):
        PORTAL.capture_portal_snapshot(
            remote_url="http://localhost:9222",
            approved_origin="https://www.inps.it",
            output_dir=output,
            external_approval=_approval(),
            playwright_factory=lambda: runtime,
        )

    assert runtime.stop_called is True
    assert runtime.browser.close_called is False
    assert not output.exists()
    assert all(
        call[0] not in {"title", "locator", "screenshot"}
        for page in pages
        for call in page.calls
    )


def test_capture_fails_closed_if_page_url_changes_during_read(
    tmp_path: Path,
) -> None:
    original_url = "https://www.inps.it/area?case=approved"
    changed_url = "https://www.inps.it/area?case=changed"
    page = _FakePage(
        original_url,
        url_reads=[original_url, original_url, changed_url],
    )
    runtime = _FakePlaywright([page])
    output = tmp_path / "portal-capture"

    with pytest.raises(PORTAL.PortalCaptureError, match="changed during capture"):
        PORTAL.capture_portal_snapshot(
            remote_url="http://localhost:9222",
            approved_origin="https://www.inps.it",
            output_dir=output,
            external_approval=_approval(),
            playwright_factory=lambda: runtime,
        )

    assert runtime.stop_called is True
    assert runtime.browser.close_called is False
    assert not output.exists()


def test_capture_sanitizes_browser_errors_and_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "sensitive-title-and-token"
    page = _FakePage(
        "https://www.inps.it/area",
        title_error=RuntimeError(secret),
    )
    runtime = _FakePlaywright([page])
    output = tmp_path / "portal-capture"
    caplog.set_level("DEBUG")

    with pytest.raises(PORTAL.PortalCaptureError) as error:
        PORTAL.capture_portal_snapshot(
            remote_url="http://localhost:9222",
            approved_origin="https://www.inps.it",
            output_dir=output,
            external_approval=_approval(),
            playwright_factory=lambda: runtime,
        )

    assert secret not in str(error.value)
    assert secret not in caplog.text
    assert runtime.stop_called is True
    assert not output.exists()


def test_verifier_rejects_tampered_artifact(tmp_path: Path) -> None:
    page = _FakePage("https://www.inps.it/area")
    runtime = _FakePlaywright([page])
    output = tmp_path / "portal-capture"
    PORTAL.capture_portal_snapshot(
        remote_url="http://localhost:9222",
        approved_origin="https://www.inps.it",
        output_dir=output,
        external_approval=_approval(),
        playwright_factory=lambda: runtime,
    )
    (output / PORTAL.VISIBLE_TEXT_NAME).write_text(
        "tampered visible body", encoding="utf-8"
    )

    with pytest.raises(PORTAL.PortalCaptureError, match="changed"):
        PORTAL.verify_portal_snapshot(output)


def test_verifier_rejects_manifest_that_persists_raw_url(tmp_path: Path) -> None:
    page = _FakePage("https://www.inps.it/area")
    runtime = _FakePlaywright([page])
    output = tmp_path / "portal-capture"
    PORTAL.capture_portal_snapshot(
        remote_url="http://localhost:9222",
        approved_origin="https://www.inps.it",
        output_dir=output,
        external_approval=_approval(),
        playwright_factory=lambda: runtime,
    )
    manifest_path = output / PORTAL.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_url"] = "https://www.inps.it/area?token=forbidden"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PORTAL.PortalCaptureError, match="fields are invalid"):
        PORTAL.verify_portal_snapshot(output)


def test_verifier_rejects_capture_id_without_required_prefix(tmp_path: Path) -> None:
    page = _FakePage("https://www.inps.it/area")
    runtime = _FakePlaywright([page])
    output = tmp_path / "portal-capture"
    PORTAL.capture_portal_snapshot(
        remote_url="http://localhost:9222",
        approved_origin="https://www.inps.it",
        output_dir=output,
        external_approval=_approval(),
        playwright_factory=lambda: runtime,
    )
    manifest_path = output / PORTAL.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["capture_id"] = "550e8400-e29b-41d4-a716-446655440000"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PORTAL.PortalCaptureError, match="capture ID is invalid"):
        PORTAL.verify_portal_snapshot(output)


def test_capture_rejects_output_inside_git_before_browser_connection() -> None:
    factory_called = False

    def _factory() -> _FakePlaywright:
        nonlocal factory_called
        factory_called = True
        return _FakePlaywright([])

    with pytest.raises(PORTAL.PortalCaptureError, match="outside a Git workspace"):
        PORTAL.capture_portal_snapshot(
            remote_url="http://localhost:9222",
            approved_origin="https://www.inps.it",
            output_dir=ROOT / "portal-capture-must-not-exist",
            external_approval=_approval(),
            playwright_factory=_factory,
        )

    assert factory_called is False


def test_module_import_does_not_import_playwright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def _guarded_import(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "playwright" or name.startswith("playwright."):
            raise AssertionError("Playwright must be imported lazily")
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)

    module = _load_module("previdenza_inps_portal_capture_lazy_import")

    assert callable(module.capture_portal_snapshot)


def test_inventory_records_verified_portal_capture_and_excludes_private_receipt(
    tmp_path: Path,
) -> None:
    secret_url = "https://www.inps.it/area?token=never-copy-this"
    capture_dir = tmp_path / "capture"
    PORTAL.capture_portal_snapshot(
        remote_url="http://localhost:9222",
        approved_origin="https://www.inps.it",
        output_dir=capture_dir,
        external_approval=_approval(),
        playwright_factory=lambda: _FakePlaywright(
            [_FakePage(secret_url, body_text="Periodo contributivo 2020-2024")]
        ),
    )
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_module()

    result = inventory_module.main(
        [
            str(capture_dir),
            "--output-dir",
            str(output_dir),
            "--portal-capture-manifest",
            str(capture_dir / PORTAL.MANIFEST_NAME),
            "--no-ocr",
        ]
    )

    assert result == 0
    inventory = json.loads(
        (output_dir / "file_inventory.json").read_text(encoding="utf-8")
    )
    assert {record["relative_path"] for record in inventory["documents"]} == {
        PORTAL.SCREENSHOT_NAME,
        PORTAL.VISIBLE_TEXT_NAME,
    }
    browser_fragments = [
        fragment
        for fragment in inventory["evidence_fragments"]
        if fragment["extraction_method"] == "browser_visible_text"
    ]
    assert len(browser_fragments) == 1
    assert "browser_capture_text_requires_visual_confirmation" in (
        browser_fragments[0]["limitations"]
    )
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    posture = run_intake["data_posture"]
    assert posture["external_connectors_used"] == ["inps_browser_read_only"]
    assert posture["external_execution_approval"]["approved"] is True
    assert posture["portal_capture_receipt"]["case_content_uploaded"] is False
    assert posture["portal_capture_receipt"]["portal_capture_permission_confirmed"]
    assert posture["portal_capture_receipt"]["human_access_authority_confirmed"]
    assert posture["portal_capture_receipt"]["portal_profile_authority_confirmed"]
    assert posture["portal_capture_receipt"][
        "delegation_or_subject_authority_confirmed"
    ]
    assert "access_authority_confirmed" not in posture["portal_capture_receipt"]
    assert secret_url not in json.dumps(run_intake)


def test_inventory_requires_explicit_manifest_argument_for_capture(
    tmp_path: Path,
) -> None:
    capture_dir = tmp_path / "capture"
    PORTAL.capture_portal_snapshot(
        remote_url="http://localhost:9222",
        approved_origin="https://www.inps.it",
        output_dir=capture_dir,
        external_approval=_approval(),
        playwright_factory=lambda: _FakePlaywright(
            [_FakePage("https://www.inps.it/area")]
        ),
    )
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_module()

    result = inventory_module.main(
        [str(capture_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 1
    assert not output_dir.exists()


def test_inventory_rejects_nested_capture_bundle_before_writing_output(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "case"
    capture_dir = input_dir / "nested" / "capture"
    PORTAL.capture_portal_snapshot(
        remote_url="http://localhost:9222",
        approved_origin="https://www.inps.it",
        output_dir=capture_dir,
        external_approval=_approval(),
        playwright_factory=lambda: _FakePlaywright(
            [_FakePage("https://www.inps.it/area")]
        ),
    )
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_module()

    result = inventory_module.main(
        [str(input_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 1
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "reserved_name",
    [PORTAL.VISIBLE_TEXT_NAME, PORTAL.SCREENSHOT_NAME],
)
def test_inventory_rejects_orphan_capture_artifact_before_writing_output(
    tmp_path: Path, reserved_name: str
) -> None:
    input_dir = tmp_path / "case"
    input_dir.mkdir()
    (input_dir / reserved_name).write_bytes(b"orphan connector artifact")
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_module()

    result = inventory_module.main(
        [str(input_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 1
    assert not output_dir.exists()


def test_inventory_rejects_tampered_root_capture_instead_of_inventorying_it(
    tmp_path: Path,
) -> None:
    capture_dir = tmp_path / "capture"
    PORTAL.capture_portal_snapshot(
        remote_url="http://localhost:9222",
        approved_origin="https://www.inps.it",
        output_dir=capture_dir,
        external_approval=_approval(),
        playwright_factory=lambda: _FakePlaywright(
            [_FakePage("https://www.inps.it/area")]
        ),
    )
    manifest_path = capture_dir / PORTAL.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["capture_id"] = "tampered-capture-id"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_module()

    result = inventory_module.main(
        [
            str(capture_dir),
            "--output-dir",
            str(output_dir),
            "--portal-capture-manifest",
            str(capture_dir / PORTAL.MANIFEST_NAME),
            "--no-ocr",
        ]
    )

    assert result == 1
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "receipt_name",
    ["portal_capture_receipt.json", "inps_portal_capture_approval.json"],
)
def test_inventory_rejects_private_capture_receipt_like_files(
    tmp_path: Path, receipt_name: str
) -> None:
    input_dir = tmp_path / "case"
    nested = input_dir / "nested"
    nested.mkdir(parents=True)
    (nested / receipt_name).write_text('{"approved": true}', encoding="utf-8")
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_module()

    result = inventory_module.main(
        [str(input_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 1
    assert not output_dir.exists()


def test_capture_screenshot_is_hashed_but_never_ocr_reprocessed(tmp_path: Path) -> None:
    capture_dir = tmp_path / "capture"
    PORTAL.capture_portal_snapshot(
        remote_url="http://localhost:9222",
        approved_origin="https://www.inps.it",
        output_dir=capture_dir,
        external_approval=_approval(),
        playwright_factory=lambda: _FakePlaywright(
            [_FakePage("https://www.inps.it/area", body_text="Periodo 2020-2024")]
        ),
    )
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_module()

    result = inventory_module.main(
        [
            str(capture_dir),
            "--output-dir",
            str(output_dir),
            "--portal-capture-manifest",
            str(capture_dir / PORTAL.MANIFEST_NAME),
        ]
    )

    assert result == 0
    inventory = json.loads(
        (output_dir / "file_inventory.json").read_text(encoding="utf-8")
    )
    screenshot = next(
        document
        for document in inventory["documents"]
        if document["relative_path"] == PORTAL.SCREENSHOT_NAME
    )
    assert screenshot["sha256"] == hashlib.sha256(PNG_BYTES).hexdigest()
    assert screenshot["ocr_enabled"] is False
    assert inventory["ocr"]["attempted_page_count"] == 0
    screenshot_fragments = [
        fragment
        for fragment in inventory["evidence_fragments"]
        if fragment["document_id"] == screenshot["document_id"]
    ]
    assert len(screenshot_fragments) == 1
    assert screenshot_fragments[0]["extraction_method"] == "none"
    assert "ocr_disabled" in screenshot_fragments[0]["limitations"]
