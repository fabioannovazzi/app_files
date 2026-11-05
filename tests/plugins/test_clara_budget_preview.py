"""Native dashboard previews retain controls without serving unrelated files."""

from __future__ import annotations

import hashlib
import importlib.util
import json
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
        '<a href="java\nscript:alert(1)">Untrusted link</a>',
    ],
)
def test_preview_rejects_active_content_even_with_matching_receipt(
    preview, tmp_path, extra
):
    report = _write_report(preview, tmp_path, extra=extra)
    with pytest.raises(ValueError):
        preview.report_bytes(report)


def _app():
    spec = importlib.util.spec_from_file_location(
        "clara_report_app_test", ROOT / "plugins/clara/scripts/report_mcp.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ReportApp()


def test_native_app_pins_report_and_receipt_and_keeps_content_app_only(
    preview, tmp_path
):
    report = _write_report(preview, tmp_path)
    app = _app()
    launch = app.open(str(report))
    assert launch["structuredContent"] == {"status": "ready"}
    assert "Fictional report" not in json.dumps(launch["content"])
    assert str(tmp_path) not in json.dumps(launch["content"])
    assert launch["_meta"]["report"]["html"] == report.read_text()
    session = launch["_meta"]["report"]["session"]
    assert app.refresh(session) == launch
    _write_report(preview, tmp_path, extra="<p>New revision</p>")
    with pytest.raises(ValueError, match="changed"):
        app.refresh(session)
    assert not hasattr(preview, "make_server")


def test_native_app_refuses_unbound_sessions_and_other_files(preview, tmp_path):
    report = _write_report(preview, tmp_path)
    app = _app()
    with pytest.raises(ValueError, match="Reopen"):
        app.refresh("unbound")
    with pytest.raises(ValueError, match="absolute"):
        app.open(report.name)
    other = tmp_path / "unrelated.html"
    other.write_text("private unrelated content")
    with pytest.raises(ValueError, match="Select the native"):
        app.open(str(other))
    html = app.resource()["contents"][0]["text"]
    assert 'sandbox="allow-scripts"' in html
    assert "allow-modals" not in html
    assert "allow-same-origin" not in html
    assert "connect-src 'none'" in html
    assert "Fictional report" not in html
