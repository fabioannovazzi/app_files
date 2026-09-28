"""Native dashboard previews retain controls without serving unrelated files."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def preview():
    path = (
        ROOT / "plugins/clara/modules/reporting-engine/scripts/budget_report_preview.py"
    )
    spec = importlib.util.spec_from_file_location("clara_budget_preview_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_report(preview, root: Path, *, extra: str = "") -> Path:
    script = (preview.COMPONENT / "assets/budget-report.js").read_text()
    report = root / preview.REPORT
    report.write_text(
        f"<!doctype html><h1>Fictional report</h1><script>{script}</script>{extra}"
    )
    content = report.read_bytes()
    (root / "execution_receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "vera.management_control_execution_receipt.v1",
                "workflow_id": "management-control-pack",
                "outputs": [
                    {
                        "path": report.name,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "byte_count": len(content),
                    }
                ],
            }
        )
    )
    return report


def test_preview_rejects_changed_native_bytes(preview, tmp_path):
    report = _write_report(preview, tmp_path)
    assert preview.report_bytes(report) == report.read_bytes()
    report.write_text(report.read_text() + "changed")
    with pytest.raises(ValueError, match="native receipt"):
        preview.report_bytes(report)


@pytest.mark.parametrize(
    "extra",
    [
        "<script>fetch('https://example.com')</script>",
        '<img onerror="alert(1)">',
        '<iframe src="private.html"></iframe>',
    ],
)
def test_preview_rejects_active_content_even_with_matching_receipt(
    preview, tmp_path, extra
):
    report = _write_report(preview, tmp_path, extra=extra)
    with pytest.raises(ValueError):
        preview.report_bytes(report)


def test_preview_serves_only_pinned_report(preview, tmp_path):
    report = _write_report(preview, tmp_path)
    original = report.read_bytes()
    server, url = preview.make_server(report)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            assert response.read() == original
            csp = response.headers["Content-Security-Policy"]
            assert "script-src 'sha256-" in csp
            assert "sandbox allow-scripts" in csp
            assert "allow-same-origin" not in csp
            assert "default-src 'none'" in csp
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(
                url.rsplit("/", 1)[0] + "/execution_receipt.json", timeout=3
            )
        assert error.value.code == 404
        # Updating both the report and receipt cannot replace an open preview.
        _write_report(preview, tmp_path, extra="<p>New revision</p>")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(url, timeout=3)
        assert error.value.code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
